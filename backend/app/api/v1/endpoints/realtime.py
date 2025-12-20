"""API endpoints for GTFS-Realtime data (on-demand fetching)"""

import asyncio
import httpx
from datetime import datetime
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.models.agency import Agency
from app.models.feed_source import ExternalFeedSource, FeedSourceType
from app.models.gtfs import Route

from google.transit import gtfs_realtime_pb2

from app.protos import parse_gtfs_rt_trip_modifications_feed

router = APIRouter()


def parse_gtfs_rt_feed(content: bytes) -> gtfs_realtime_pb2.FeedMessage:
    """Parse GTFS-RT protobuf content"""
    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(content)
    except Exception as e:
        # Check if content looks like HTML (error page)
        content_preview = content[:200].decode('utf-8', errors='ignore')
        if content_preview.strip().startswith('<!') or content_preview.strip().startswith('<html'):
            raise ValueError(f"Received HTML instead of protobuf - API may be returning an error page")
        raise ValueError(f"Failed to parse protobuf: {e}")
    return feed


def is_demo_feed_url(url: str) -> bool:
    """Check if URL is a local demo feed endpoint"""
    return url.startswith("/api/v1/demo/")


def get_demo_agency_id(url: str) -> int | None:
    """Extract agency_id from demo URL"""
    import re
    match = re.search(r'/api/v1/demo/agency/(\d+)/', url)
    if match:
        return int(match.group(1))
    return None


async def fetch_demo_feed(url: str, db: AsyncSession) -> list[dict[str, Any]]:
    """Fetch vehicle positions from internal demo endpoint"""
    agency_id = get_demo_agency_id(url)
    if not agency_id:
        return []

    # Import and call the demo function directly instead of HTTP request
    from app.models.gtfs import GTFSFeed, Trip, Shape

    # Get the agency's feeds
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.agency_id == agency_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        return []

    # Get all trips with their routes
    trips_result = await db.execute(
        select(Trip, Route)
        .join(Route, and_(Trip.feed_id == Route.feed_id, Trip.route_id == Route.route_id))
        .where(Trip.feed_id == feed.id)
        .limit(4)
    )
    trips_with_routes = trips_result.all()

    vehicles = []

    for i, (trip, route) in enumerate(trips_with_routes):
        # Get shape points for this trip
        shape_points = []
        if trip.shape_id:
            # Get all points for this shape_id
            shape_result = await db.execute(
                select(Shape)
                .where(
                    Shape.feed_id == feed.id,
                    Shape.shape_id == trip.shape_id
                )
                .order_by(Shape.shape_pt_sequence)
            )
            shapes = shape_result.scalars().all()
            shape_points = [(float(s.shape_pt_lat), float(s.shape_pt_lon)) for s in shapes]

        # Calculate vehicle position using same logic as demo endpoint
        import math
        now = datetime.now()
        seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
        cycle_seconds = 60
        cycle_progress = (seconds_since_midnight % cycle_seconds) / cycle_seconds
        offset = hash(trip.trip_id) % 100 / 100 * 0.25
        adjusted_progress = (cycle_progress + offset) % 1.0

        if shape_points:
            num_segments = len(shape_points) - 1
            if num_segments > 0:
                segment_index = min(int(adjusted_progress * num_segments), num_segments - 1)
                segment_progress = (adjusted_progress * num_segments) % 1.0
                point1 = shape_points[segment_index]
                point2 = shape_points[min(segment_index + 1, len(shape_points) - 1)]
                lat = point1[0] + (point2[0] - point1[0]) * segment_progress
                lon = point1[1] + (point2[1] - point1[1]) * segment_progress

                # Calculate bearing
                lat1_rad = math.radians(point1[0])
                lat2_rad = math.radians(point2[0])
                lon_diff = math.radians(point2[1] - point1[1])
                x = math.sin(lon_diff) * math.cos(lat2_rad)
                y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(lon_diff)
                bearing = (math.degrees(math.atan2(x, y)) + 360) % 360
            else:
                lat, lon = shape_points[0]
                bearing = 0
        else:
            lat, lon, bearing = 40.7128, -74.0060, 0

        speed = 15.0 if route.route_type == 3 else 25.0
        vehicle_type = "Bus" if route.route_type == 3 else "Train"

        vehicles.append({
            "id": f"vehicle_{i+1}",
            "vehicle_id": f"demo_{agency_id}_{i+1}",
            "vehicle_label": f"{vehicle_type} {route.route_short_name}-{i+1:02d}",
            "latitude": lat,
            "longitude": lon,
            "bearing": bearing,
            "speed": speed,
            "trip_id": trip.trip_id,
            "route_id": route.route_id,
            "current_status": "in_transit_to",
            "congestion_level": "running_smoothly",
            "timestamp": int(datetime.now().timestamp()),
        })

    return vehicles


async def fetch_demo_trip_updates(url: str, db: AsyncSession) -> list[dict[str, Any]]:
    """Fetch trip updates from internal demo endpoint"""
    agency_id = get_demo_agency_id(url)
    if not agency_id:
        return []

    from app.models.gtfs import GTFSFeed, Trip, Stop, StopTime
    import math
    import time

    # Get the agency's feeds
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.agency_id == agency_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        return []

    # Get all trips with their routes and stop times
    trips_result = await db.execute(
        select(Trip, Route)
        .join(Route, and_(Trip.feed_id == Route.feed_id, Trip.route_id == Route.route_id))
        .where(Trip.feed_id == feed.id)
    )
    trips_with_routes = trips_result.all()

    trip_updates = []

    for trip, route in trips_with_routes:
        # Calculate simulated delay
        now = datetime.now()
        seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
        trip_hash = hash(trip.trip_id)
        time_factor = (seconds_since_midnight // 60) % 10
        base_delay = (trip_hash % 7 - 3) * 30
        variation = int(math.sin(time_factor * 0.6) * 60)
        if route.route_type == 3:  # Bus
            variation *= 2
        delay = max(-60, min(300, base_delay + variation))

        # Get stop times for this trip
        stop_times_result = await db.execute(
            select(StopTime, Stop)
            .join(Stop, and_(StopTime.feed_id == Stop.feed_id, StopTime.stop_id == Stop.stop_id))
            .where(StopTime.feed_id == feed.id, StopTime.trip_id == trip.trip_id)
            .order_by(StopTime.stop_sequence)
        )
        stop_times_with_stops = stop_times_result.all()

        # Build stop time updates with propagating delays
        stop_time_updates = []
        cumulative_delay = delay

        for stop_time, stop in stop_times_with_stops:
            stop_variation = (hash(f"{trip.trip_id}_{stop.stop_id}") % 30) - 15
            cumulative_delay = max(-30, cumulative_delay + stop_variation)

            stop_time_updates.append({
                "stop_sequence": stop_time.stop_sequence,
                "stop_id": stop.stop_id,
                "arrival_delay": cumulative_delay,
                "arrival_time": int(time.time()) + cumulative_delay,
                "departure_delay": cumulative_delay,
                "departure_time": int(time.time()) + cumulative_delay + 30,
            })

        vehicle_type = "Bus" if route.route_type == 3 else "Train"
        trip_updates.append({
            "id": f"trip_update_{trip.id}",
            "trip_id": trip.trip_id,
            "route_id": route.route_id,
            "vehicle_id": f"demo_{agency_id}_{trip.id}",
            "vehicle_label": f"{vehicle_type} {route.route_short_name}",
            "delay": delay,
            "schedule_relationship": "scheduled",
            "timestamp": int(time.time()),
            "stop_time_updates": stop_time_updates,
        })

    return trip_updates


async def fetch_demo_alerts(url: str, db: AsyncSession) -> list[dict[str, Any]]:
    """Fetch service alerts from internal demo endpoint"""
    agency_id = get_demo_agency_id(url)
    if not agency_id:
        return []

    from app.models.gtfs import GTFSFeed
    import time

    # Get the agency's feeds
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.agency_id == agency_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        return []

    # Get routes for entity references
    routes_result = await db.execute(
        select(Route).where(Route.feed_id == feed.id)
    )
    routes = routes_result.scalars().all()

    bus_routes = [r for r in routes if r.route_type == 3]
    train_routes = [r for r in routes if r.route_type == 2]

    # Demo alerts that rotate based on time
    DEMO_ALERTS = [
        {
            "alert_id": "demo_alert_weather",
            "cause": "weather",
            "effect": "significant_delays",
            "severity_level": "WARNING",
            "header_text": {"en": "Weather Advisory"},
            "description_text": {"en": "Due to inclement weather, expect delays of up to 15 minutes on all routes."},
            "affects": "all"
        },
        {
            "alert_id": "demo_alert_maintenance",
            "cause": "maintenance",
            "effect": "modified_service",
            "severity_level": "INFO",
            "header_text": {"en": "Scheduled Maintenance"},
            "description_text": {"en": "Track maintenance scheduled this weekend. Train services will operate on a modified schedule."},
            "affects": "train"
        },
        {
            "alert_id": "demo_alert_construction",
            "cause": "construction",
            "effect": "detour",
            "severity_level": "WARNING",
            "header_text": {"en": "Bus Route Detour"},
            "description_text": {"en": "Due to road construction, buses are detouring via Central Avenue."},
            "affects": "bus"
        },
        {
            "alert_id": "demo_alert_special",
            "cause": "holiday",
            "effect": "additional_service",
            "severity_level": "INFO",
            "header_text": {"en": "Special Event Service"},
            "description_text": {"en": "Additional service running for the downtown festival."},
            "affects": "all"
        },
        {
            "alert_id": "demo_alert_accessibility",
            "cause": "technical_problem",
            "effect": "accessibility_issue",
            "severity_level": "WARNING",
            "header_text": {"en": "Elevator Out of Service"},
            "description_text": {"en": "Elevator at Main Station temporarily out of service."},
            "affects": "train"
        }
    ]

    now = datetime.now()
    current_hour = now.hour
    timestamp = int(time.time())

    # Different alerts are "active" at different times
    active_alert_indices = [
        current_hour % len(DEMO_ALERTS),
        (current_hour + 2) % len(DEMO_ALERTS)
    ]

    alerts = []
    for idx in active_alert_indices:
        alert_template = DEMO_ALERTS[idx]

        # Build informed entities based on what the alert affects
        informed_entities = []
        if alert_template["affects"] == "all":
            informed_entities = [{"agency_id": "demo_agency"}]
        elif alert_template["affects"] == "bus" and bus_routes:
            informed_entities = [{"route_id": r.route_id} for r in bus_routes]
        elif alert_template["affects"] == "train" and train_routes:
            informed_entities = [{"route_id": r.route_id} for r in train_routes]
        else:
            informed_entities = [{"agency_id": "demo_agency"}]

        alerts.append({
            "id": f"{alert_template['alert_id']}_{agency_id}",
            "cause": alert_template["cause"],
            "effect": alert_template["effect"],
            "header_text": alert_template["header_text"],
            "description_text": alert_template["description_text"],
            "informed_entities": informed_entities,
            "active_periods": [{
                "start": timestamp - 3600,
                "end": timestamp + 7200
            }]
        })

    return alerts


async def fetch_demo_trip_modifications(url: str, db: AsyncSession) -> list[dict[str, Any]]:
    """Fetch trip modifications from internal demo endpoint"""
    agency_id = get_demo_agency_id(url)
    if not agency_id:
        return []

    from app.models.gtfs import GTFSFeed, Stop

    # Get the agency's feeds
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.agency_id == agency_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        return []

    # Get routes and stops
    routes_result = await db.execute(
        select(Route).where(Route.feed_id == feed.id)
    )
    routes = routes_result.scalars().all()

    stops_result = await db.execute(
        select(Stop).where(Stop.feed_id == feed.id)
    )
    stops = stops_result.scalars().all()

    bus_routes = [r for r in routes if r.route_type == 3]
    bus_stops = [s for s in stops if s.stop_id.startswith("bus_")]

    modifications = []
    now = datetime.now()
    today = now.strftime("%Y%m%d")

    # Only show modifications during certain hours (simulating active detours)
    if 6 <= now.hour <= 22 and bus_routes and len(bus_stops) >= 2:
        bus_route = bus_routes[0]

        modifications.append({
            "id": f"demo_detour_{agency_id}",
            "modification_id": f"demo_detour_{agency_id}",
            "route_id": bus_route.route_id,
            "selected_trips": [{
                "trip_ids": [],
                "shape_id": None
            }],
            "service_dates": [today],
            "modifications": [{
                "start_stop": {"stop_id": bus_stops[0].stop_id},
                "end_stop": {"stop_id": bus_stops[-1].stop_id if len(bus_stops) > 1 else bus_stops[0].stop_id},
                "propagated_delay": 180,
                "replacement_stops": [{
                    "stop_id": f"temp_stop_{agency_id}",
                    "travel_time": 300
                }]
            }],
            "affected_stop_ids": [bus_stops[0].stop_id, bus_stops[-1].stop_id] if len(bus_stops) > 1 else [bus_stops[0].stop_id],
            "replacement_stops": [{
                "stop_id": f"temp_stop_{agency_id}",
                "stop_name": "Temporary Detour Stop",
                "stop_lat": float(bus_stops[0].stop_lat + bus_stops[-1].stop_lat) / 2 + 0.002,
                "stop_lon": float(bus_stops[0].stop_lon + bus_stops[-1].stop_lon) / 2 + 0.002,
            }]
        })

    return modifications


async def fetch_demo_shapes(url: str, db: AsyncSession) -> list[dict[str, Any]]:
    """Fetch realtime shapes from internal demo endpoint for trip modifications"""
    agency_id = get_demo_agency_id(url)
    if not agency_id:
        return []

    from app.models.gtfs import GTFSFeed, Stop

    # Get the agency's feeds
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.agency_id == agency_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        return []

    # Get routes for generating detour shapes
    routes_result = await db.execute(
        select(Route).where(Route.feed_id == feed.id)
    )
    routes = routes_result.scalars().all()

    bus_routes = [r for r in routes if r.route_type == 3]

    shapes = []
    now = datetime.now()

    # Only show detour shapes during certain hours (simulating active detours)
    if 6 <= now.hour <= 22 and bus_routes:
        bus_route = bus_routes[0]

        # Create a tight local detour (1-2 blocks) to simulate a short route modification
        # This represents a small rectangular detour around a street closure
        detour_shape_points = [
            {"lat": 45.4850, "lon": -73.5820, "sequence": 0},  # Detour start
            {"lat": 45.4855, "lon": -73.5835, "sequence": 1},  # Turn 1 block
            {"lat": 45.4860, "lon": -73.5840, "sequence": 2},  # Continue
            {"lat": 45.4865, "lon": -73.5830, "sequence": 3},  # Turn back
            {"lat": 45.4870, "lon": -73.5815, "sequence": 4},  # Reconnect to main route
        ]

        shapes.append({
            "id": f"demo_detour_shape_{agency_id}",
            "shape_id": f"demo_detour_shape_{agency_id}",
            "shape_points": detour_shape_points,
            "modification_id": f"demo_detour_{agency_id}",
            "route_id": bus_route.route_id,
            "timestamp": int(now.timestamp()),
        })

    return shapes


async def fetch_demo_stops(url: str, db: AsyncSession) -> list[dict[str, Any]]:
    """Fetch realtime stops from internal demo endpoint for trip modifications"""
    agency_id = get_demo_agency_id(url)
    if not agency_id:
        return []

    from app.models.gtfs import GTFSFeed, Stop

    # Get the agency's feeds
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.agency_id == agency_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        return []

    # Get routes
    routes_result = await db.execute(
        select(Route).where(Route.feed_id == feed.id)
    )
    routes = routes_result.scalars().all()

    bus_routes = [r for r in routes if r.route_type == 3]

    rt_stops = []
    now = datetime.now()

    # Only show temporary stops during certain hours (simulating active detours)
    if 6 <= now.hour <= 22 and bus_routes:
        bus_route = bus_routes[0]

        # Create a single temporary stop for the tight local detour
        # This represents a temporary stop along the detour route
        temporary_stops = [
            {
                "id": f"temp_stop_1_{agency_id}",
                "stop_id": f"temp_stop_1_{agency_id}",
                "stop_name": "Temporary Stop - Detour / Arrêt temporaire - Détour",
                "stop_lat": 45.4860,
                "stop_lon": -73.5840,
                "stop_code": "TEMP_DETOUR",
                "stop_desc": "Temporary stop due to street closure / Arrêt temporaire en raison de la fermeture de rue",
                "modification_id": f"demo_detour_{agency_id}",
                "route_id": bus_route.route_id,
                "is_replacement": True,
                "wheelchair_boarding": 1,
                "timestamp": int(now.timestamp()),
            }
        ]

        rt_stops.extend(temporary_stops)

    return rt_stops


async def fetch_gtfs_rt(
    url: str,
    auth_type: Optional[str] = None,
    auth_header: Optional[str] = None,
    auth_value: Optional[str] = None,
    timeout: float = 10.0,
) -> bytes:
    """Fetch GTFS-RT feed from URL"""
    headers = {"User-Agent": "GTFS-Tools/1.0"}

    if auth_type == "api_key" and auth_header and auth_value:
        headers[auth_header] = auth_value
    elif auth_type == "bearer" and auth_value:
        headers["Authorization"] = f"Bearer {auth_value}"
    elif auth_type == "basic" and auth_value:
        headers["Authorization"] = f"Basic {auth_value}"

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, headers=headers, follow_redirects=True)
        if response.status_code == 429:
            raise ValueError(f"Rate limited (429 Too Many Requests) - please wait before retrying")
        if response.status_code >= 400:
            raise ValueError(f"HTTP error {response.status_code}: {response.reason_phrase}")
        return response.content


def extract_vehicle_positions(feed: gtfs_realtime_pb2.FeedMessage) -> list[dict[str, Any]]:
    """Extract vehicle positions from GTFS-RT feed"""
    positions = []

    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue

        vehicle = entity.vehicle
        position = vehicle.position if vehicle.HasField("position") else None
        trip = vehicle.trip if vehicle.HasField("trip") else None
        vehicle_desc = vehicle.vehicle if vehicle.HasField("vehicle") else None

        if not position:
            continue

        position_data = {
            "id": entity.id,
            "vehicle_id": vehicle_desc.id if vehicle_desc and vehicle_desc.id else entity.id,
            "vehicle_label": vehicle_desc.label if vehicle_desc and vehicle_desc.label else None,
            "license_plate": vehicle_desc.license_plate if vehicle_desc and vehicle_desc.license_plate else None,
            "latitude": position.latitude,
            "longitude": position.longitude,
            "bearing": position.bearing if position.HasField("bearing") else None,
            "speed": position.speed if position.HasField("speed") else None,
            "trip_id": trip.trip_id if trip and trip.trip_id else None,
            "route_id": trip.route_id if trip and trip.route_id else None,
            "direction_id": trip.direction_id if trip and trip.HasField("direction_id") else None,
            "start_time": trip.start_time if trip and trip.start_time else None,
            "start_date": trip.start_date if trip and trip.start_date else None,
            "current_stop_sequence": vehicle.current_stop_sequence if vehicle.HasField("current_stop_sequence") else None,
            "stop_id": vehicle.stop_id if vehicle.HasField("stop_id") else None,
            "current_status": get_vehicle_stop_status(vehicle.current_status) if vehicle.HasField("current_status") else None,
            "congestion_level": get_congestion_level(vehicle.congestion_level) if vehicle.HasField("congestion_level") else None,
            "occupancy_status": get_occupancy_status(vehicle.occupancy_status) if vehicle.HasField("occupancy_status") else None,
            "timestamp": vehicle.timestamp if vehicle.HasField("timestamp") else None,
        }
        positions.append(position_data)

    return positions


def extract_trip_updates(feed: gtfs_realtime_pb2.FeedMessage) -> list[dict[str, Any]]:
    """Extract trip updates from GTFS-RT feed"""
    updates = []

    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue

        trip_update = entity.trip_update
        trip = trip_update.trip if trip_update.HasField("trip") else None
        vehicle = trip_update.vehicle if trip_update.HasField("vehicle") else None

        if not trip:
            continue

        # Extract stop time updates
        stop_time_updates = []
        for stu in trip_update.stop_time_update:
            stu_data = {
                "stop_sequence": stu.stop_sequence if stu.HasField("stop_sequence") else None,
                "stop_id": stu.stop_id if stu.HasField("stop_id") else None,
            }
            if stu.HasField("arrival"):
                stu_data["arrival_delay"] = stu.arrival.delay if stu.arrival.HasField("delay") else None
                stu_data["arrival_time"] = stu.arrival.time if stu.arrival.HasField("time") else None
            if stu.HasField("departure"):
                stu_data["departure_delay"] = stu.departure.delay if stu.departure.HasField("delay") else None
                stu_data["departure_time"] = stu.departure.time if stu.departure.HasField("time") else None
            stop_time_updates.append(stu_data)

        update_data = {
            "id": entity.id,
            "trip_id": trip.trip_id,
            "route_id": trip.route_id if trip.HasField("route_id") else None,
            "direction_id": trip.direction_id if trip.HasField("direction_id") else None,
            "start_time": trip.start_time if trip.HasField("start_time") else None,
            "start_date": trip.start_date if trip.HasField("start_date") else None,
            "schedule_relationship": get_schedule_relationship(trip.schedule_relationship) if trip.HasField("schedule_relationship") else "scheduled",
            "vehicle_id": vehicle.id if vehicle and vehicle.id else None,
            "vehicle_label": vehicle.label if vehicle and vehicle.label else None,
            "delay": trip_update.delay if trip_update.HasField("delay") else None,
            "timestamp": trip_update.timestamp if trip_update.HasField("timestamp") else None,
            "stop_time_updates": stop_time_updates,
        }
        updates.append(update_data)

    return updates


def extract_alerts(feed: gtfs_realtime_pb2.FeedMessage) -> list[dict[str, Any]]:
    """Extract alerts from GTFS-RT feed"""
    alerts = []

    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue

        alert = entity.alert

        # Extract active periods
        active_periods = []
        for period in alert.active_period:
            active_periods.append({
                "start": period.start if period.HasField("start") else None,
                "end": period.end if period.HasField("end") else None,
            })

        # Extract informed entities
        informed_entities = []
        for ie in alert.informed_entity:
            entity_data = {}
            if ie.HasField("agency_id"):
                entity_data["agency_id"] = ie.agency_id
            if ie.HasField("route_id"):
                entity_data["route_id"] = ie.route_id
            if ie.HasField("route_type"):
                entity_data["route_type"] = ie.route_type
            if ie.HasField("stop_id"):
                entity_data["stop_id"] = ie.stop_id
            if ie.HasField("trip"):
                entity_data["trip_id"] = ie.trip.trip_id
            if entity_data:
                informed_entities.append(entity_data)

        # Extract text
        header_text = extract_translated_string(alert.header_text) if alert.HasField("header_text") else None
        description_text = extract_translated_string(alert.description_text) if alert.HasField("description_text") else None

        alert_data = {
            "id": entity.id,
            "active_periods": active_periods,
            "informed_entities": informed_entities,
            "cause": get_alert_cause(alert.cause) if alert.HasField("cause") else None,
            "effect": get_alert_effect(alert.effect) if alert.HasField("effect") else None,
            "header_text": header_text,
            "description_text": description_text,
            "url": extract_translated_string(alert.url).get("en") if alert.HasField("url") else None,
        }
        alerts.append(alert_data)

    return alerts


def extract_translated_string(ts) -> dict[str, str]:
    """Extract translated string to dict"""
    result = {}
    for translation in ts.translation:
        lang = translation.language if translation.language else "en"
        result[lang] = translation.text
    return result


def get_schedule_relationship(sr) -> str:
    mapping = {0: "scheduled", 1: "added", 2: "unscheduled", 3: "canceled", 5: "replacement"}
    return mapping.get(sr, "scheduled")


def get_vehicle_stop_status(status) -> str:
    mapping = {0: "incoming_at", 1: "stopped_at", 2: "in_transit_to"}
    return mapping.get(status, "in_transit_to")


def get_congestion_level(level) -> str:
    mapping = {0: "unknown", 1: "running_smoothly", 2: "stop_and_go", 3: "congestion", 4: "severe_congestion"}
    return mapping.get(level, "unknown")


def get_occupancy_status(status) -> str:
    mapping = {0: "empty", 1: "many_seats_available", 2: "few_seats_available", 3: "standing_room_only", 4: "crushed_standing_room_only", 5: "full", 6: "not_accepting_passengers"}
    return mapping.get(status, "empty")


def get_alert_cause(cause) -> str:
    mapping = {1: "unknown_cause", 2: "other_cause", 3: "technical_problem", 4: "strike", 5: "demonstration", 6: "accident", 7: "holiday", 8: "weather", 9: "maintenance", 10: "construction", 11: "police_activity", 12: "medical_emergency"}
    return mapping.get(cause, "unknown_cause")


def get_alert_effect(effect) -> str:
    mapping = {1: "no_service", 2: "reduced_service", 3: "significant_delays", 4: "detour", 5: "additional_service", 6: "modified_service", 7: "other_effect", 8: "unknown_effect", 9: "stop_moved", 10: "no_effect", 11: "accessibility_issue"}
    return mapping.get(effect, "unknown_effect")


def extract_trip_modifications(feed: gtfs_realtime_pb2.FeedMessage, raw_content: bytes = None) -> list[dict[str, Any]]:
    """
    Extract trip modifications from GTFS-RT feed.

    TripModifications is an experimental GTFS-RT extension that allows agencies
    to communicate about detours, skipped stops, and service changes.

    Since the standard protobuf library doesn't include the TripModifications extension,
    we use a custom parser to extract the data from raw bytes.
    """
    # First, try using the custom raw bytes parser if we have raw content
    # This handles the experimental extension that isn't in the standard protobuf
    if raw_content:
        try:
            modifications = parse_gtfs_rt_trip_modifications_feed(raw_content)
            if modifications:
                return modifications
        except Exception as e:
            # Fall through to standard parsing if custom parser fails
            pass

    # Standard parsing (for future when protobuf might include trip_modifications)
    modifications = []

    for entity in feed.entity:
        # Check if entity has trip_modifications field (experimental)
        if not hasattr(entity, 'trip_modifications'):
            continue

        try:
            if not entity.HasField("trip_modifications"):
                continue
        except ValueError:
            # Field doesn't exist in this protobuf definition
            continue

        trip_mod = entity.trip_modifications

        # Extract selected trips (trips affected by this modification)
        selected_trips = []
        if hasattr(trip_mod, 'selected_trips'):
            for st in trip_mod.selected_trips:
                trip_info = {}
                if hasattr(st, 'trip_ids'):
                    trip_info['trip_ids'] = list(st.trip_ids)
                if hasattr(st, 'shape_id') and st.HasField('shape_id'):
                    trip_info['shape_id'] = st.shape_id
                selected_trips.append(trip_info)

        # Extract modifications (what changes are made)
        mods_list = []
        affected_stops = []
        replacement_stops = []

        if hasattr(trip_mod, 'modifications'):
            for mod in trip_mod.modifications:
                mod_data = {}

                # Start stop selector
                if hasattr(mod, 'start_stop_selector') and mod.HasField('start_stop_selector'):
                    start_sel = mod.start_stop_selector
                    mod_data['start_stop'] = {
                        'stop_sequence': start_sel.stop_sequence if hasattr(start_sel, 'stop_sequence') and start_sel.HasField('stop_sequence') else None,
                        'stop_id': start_sel.stop_id if hasattr(start_sel, 'stop_id') and start_sel.HasField('stop_id') else None,
                    }
                    if start_sel.stop_id:
                        affected_stops.append(start_sel.stop_id)

                # End stop selector
                if hasattr(mod, 'end_stop_selector') and mod.HasField('end_stop_selector'):
                    end_sel = mod.end_stop_selector
                    mod_data['end_stop'] = {
                        'stop_sequence': end_sel.stop_sequence if hasattr(end_sel, 'stop_sequence') and end_sel.HasField('stop_sequence') else None,
                        'stop_id': end_sel.stop_id if hasattr(end_sel, 'stop_id') and end_sel.HasField('stop_id') else None,
                    }
                    if end_sel.stop_id:
                        affected_stops.append(end_sel.stop_id)

                # Propagated modification delay
                if hasattr(mod, 'propagated_modification_delay') and mod.HasField('propagated_modification_delay'):
                    mod_data['propagated_delay'] = mod.propagated_modification_delay

                # Replacement stops
                if hasattr(mod, 'replacement_stops'):
                    for rs in mod.replacement_stops:
                        rs_data = {}
                        if hasattr(rs, 'stop_id') and rs.HasField('stop_id'):
                            rs_data['stop_id'] = rs.stop_id
                        if hasattr(rs, 'travel_time_to_stop') and rs.HasField('travel_time_to_stop'):
                            rs_data['travel_time'] = rs.travel_time_to_stop
                        replacement_stops.append(rs_data)
                        mod_data.setdefault('replacement_stops', []).append(rs_data)

                # Service alert ID reference
                if hasattr(mod, 'service_alert_id') and mod.HasField('service_alert_id'):
                    mod_data['service_alert_id'] = mod.service_alert_id

                # Last modified time
                if hasattr(mod, 'last_modified_time') and mod.HasField('last_modified_time'):
                    mod_data['last_modified_time'] = mod.last_modified_time

                mods_list.append(mod_data)

        # Extract service dates
        service_dates = []
        if hasattr(trip_mod, 'service_dates'):
            for sd in trip_mod.service_dates:
                service_dates.append(sd)

        # Build the modification object
        mod_data = {
            "id": entity.id,
            "modification_id": entity.id,
            "selected_trips": selected_trips,
            "service_dates": service_dates if service_dates else None,
            "modifications": mods_list,
            "affected_stop_ids": list(set(affected_stops)) if affected_stops else None,
            "replacement_stops": replacement_stops if replacement_stops else None,
        }

        # Extract route_id if available from first selected trip
        if selected_trips and 'trip_ids' in selected_trips[0] and selected_trips[0]['trip_ids']:
            mod_data['trip_id'] = selected_trips[0]['trip_ids'][0]

        modifications.append(mod_data)

    return modifications


def extract_realtime_shapes(feed: gtfs_realtime_pb2.FeedMessage, raw_content: bytes = None) -> list[dict[str, Any]]:
    """
    Extract shapes from GTFS-RT Shapes feed (experimental extension).

    This is part of the GTFS-RT Trip Modifications extension that allows agencies
    to communicate replacement shapes for detours.
    """
    shapes = []

    # The shapes feed is an experimental extension, so standard protobuf may not have it
    # We'll try to parse what we can from the feed
    for entity in feed.entity:
        # Check if entity has shape field (experimental extension)
        if not hasattr(entity, 'shape'):
            continue

        try:
            if not entity.HasField("shape"):
                continue
        except ValueError:
            # Field doesn't exist in this protobuf definition
            continue

        shape = entity.shape

        shape_data = {
            "id": entity.id,
            "shape_id": entity.id,
        }

        # Extract encoded polyline if available
        if hasattr(shape, 'encoded_polyline') and shape.encoded_polyline:
            shape_data["encoded_polyline"] = shape.encoded_polyline

        # Extract shape points if available
        if hasattr(shape, 'shape_points'):
            points = []
            for pt in shape.shape_points:
                point = {
                    "lat": pt.latitude if hasattr(pt, 'latitude') else None,
                    "lon": pt.longitude if hasattr(pt, 'longitude') else None,
                }
                if hasattr(pt, 'shape_pt_sequence'):
                    point["sequence"] = pt.shape_pt_sequence
                if hasattr(pt, 'shape_dist_traveled'):
                    point["dist_traveled"] = pt.shape_dist_traveled
                points.append(point)
            shape_data["shape_points"] = points

        shapes.append(shape_data)

    return shapes


def extract_realtime_stops(feed: gtfs_realtime_pb2.FeedMessage, raw_content: bytes = None) -> list[dict[str, Any]]:
    """
    Extract stops from GTFS-RT Stops feed (experimental extension).

    This is part of the GTFS-RT Trip Modifications extension that allows agencies
    to communicate replacement/temporary stops for detours.
    """
    stops = []

    # The stops feed is an experimental extension, so standard protobuf may not have it
    for entity in feed.entity:
        # Check if entity has stop field (experimental extension)
        if not hasattr(entity, 'stop'):
            continue

        try:
            if not entity.HasField("stop"):
                continue
        except ValueError:
            # Field doesn't exist in this protobuf definition
            continue

        stop = entity.stop

        stop_data = {
            "id": entity.id,
            "stop_id": stop.stop_id if hasattr(stop, 'stop_id') and stop.stop_id else entity.id,
        }

        # Extract stop properties
        if hasattr(stop, 'stop_name') and stop.stop_name:
            stop_data["stop_name"] = stop.stop_name
        if hasattr(stop, 'stop_lat'):
            stop_data["stop_lat"] = stop.stop_lat
        if hasattr(stop, 'stop_lon'):
            stop_data["stop_lon"] = stop.stop_lon
        if hasattr(stop, 'stop_code') and stop.stop_code:
            stop_data["stop_code"] = stop.stop_code
        if hasattr(stop, 'stop_desc') and stop.stop_desc:
            stop_data["stop_desc"] = stop.stop_desc
        if hasattr(stop, 'zone_id') and stop.zone_id:
            stop_data["zone_id"] = stop.zone_id
        if hasattr(stop, 'wheelchair_boarding'):
            stop_data["wheelchair_boarding"] = stop.wheelchair_boarding

        stop_data["is_replacement"] = True  # All RT stops are assumed to be replacement stops

        stops.append(stop_data)

    return stops


@router.get("/agency/{agency_id}/vehicles")
async def get_realtime_vehicles(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """
    Get real-time vehicle positions for an agency.
    Fetches data directly from configured GTFS-RT feed sources.
    """
    # Verify agency exists
    agency = await db.get(Agency, agency_id)
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agency {agency_id} not found",
        )

    # Verify user has access to this agency
    await deps.verify_agency_access(agency_id, db, current_user)

    # Get all enabled GTFS-RT feed sources for this agency (vehicles can come from any RT feed)
    rt_types = [
        FeedSourceType.GTFS_REALTIME.value,
        FeedSourceType.GTFS_RT_VEHICLE_POSITIONS.value,
    ]
    query = select(ExternalFeedSource).where(
        ExternalFeedSource.agency_id == agency_id,
        ExternalFeedSource.is_enabled == True,
        ExternalFeedSource.source_type.in_(rt_types),
    )
    result = await db.execute(query)
    feed_sources = result.scalars().all()

    if not feed_sources:
        return {
            "agency_id": agency_id,
            "timestamp": datetime.utcnow().isoformat(),
            "vehicles": [],
            "message": "No GTFS-RT feed sources configured for this agency",
        }

    # Get route info for enrichment
    route_query = select(Route).where(Route.feed_id.in_(
        select(Route.feed_id).where(Route.feed_id.isnot(None))
    ))
    route_result = await db.execute(
        select(Route).join(
            Agency, Route.feed_id.isnot(None)
        ).limit(1000)
    )
    routes_data = {}
    # We'll fetch routes separately if needed

    all_vehicles = []
    errors = []

    for source in feed_sources:
        try:
            # Handle internal demo feeds differently
            if is_demo_feed_url(source.url):
                vehicles = await fetch_demo_feed(source.url, db)
            else:
                content = await fetch_gtfs_rt(
                    url=source.url,
                    auth_type=source.auth_type,
                    auth_header=source.auth_header,
                    auth_value=source.auth_value,
                )
                feed = parse_gtfs_rt_feed(content)
                vehicles = extract_vehicle_positions(feed)

            # Add source info to each vehicle
            for v in vehicles:
                v["feed_source_id"] = source.id
                v["feed_source_name"] = source.name

            all_vehicles.extend(vehicles)

        except Exception as e:
            errors.append({
                "feed_source_id": source.id,
                "feed_source_name": source.name,
                "error": str(e),
            })

    return {
        "agency_id": agency_id,
        "timestamp": datetime.utcnow().isoformat(),
        "vehicles": all_vehicles,
        "vehicle_count": len(all_vehicles),
        "errors": errors if errors else None,
    }


@router.get("/agency/{agency_id}/trip-updates")
async def get_realtime_trip_updates(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """
    Get real-time trip updates for an agency.
    Fetches data directly from configured GTFS-RT feed sources.
    """
    agency = await db.get(Agency, agency_id)
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agency {agency_id} not found",
        )

    # Verify user has access to this agency
    await deps.verify_agency_access(agency_id, db, current_user)

    rt_types = [
        FeedSourceType.GTFS_REALTIME.value,
        FeedSourceType.GTFS_RT_TRIP_UPDATES.value,
    ]
    query = select(ExternalFeedSource).where(
        ExternalFeedSource.agency_id == agency_id,
        ExternalFeedSource.is_enabled == True,
        ExternalFeedSource.source_type.in_(rt_types),
    )
    result = await db.execute(query)
    feed_sources = result.scalars().all()

    if not feed_sources:
        return {
            "agency_id": agency_id,
            "timestamp": datetime.utcnow().isoformat(),
            "trip_updates": [],
            "message": "No GTFS-RT feed sources configured for this agency",
        }

    all_updates = []
    errors = []

    for source in feed_sources:
        try:
            # Handle internal demo feeds differently
            if is_demo_feed_url(source.url):
                updates = await fetch_demo_trip_updates(source.url, db)
            else:
                content = await fetch_gtfs_rt(
                    url=source.url,
                    auth_type=source.auth_type,
                    auth_header=source.auth_header,
                    auth_value=source.auth_value,
                )
                feed = parse_gtfs_rt_feed(content)
                updates = extract_trip_updates(feed)

            for u in updates:
                u["feed_source_id"] = source.id
                u["feed_source_name"] = source.name

            all_updates.extend(updates)

        except Exception as e:
            errors.append({
                "feed_source_id": source.id,
                "feed_source_name": source.name,
                "error": str(e),
            })

    return {
        "agency_id": agency_id,
        "timestamp": datetime.utcnow().isoformat(),
        "trip_updates": all_updates,
        "update_count": len(all_updates),
        "errors": errors if errors else None,
    }


@router.get("/agency/{agency_id}/alerts")
async def get_realtime_alerts(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """
    Get real-time service alerts for an agency.
    Fetches data directly from configured GTFS-RT feed sources.
    """
    agency = await db.get(Agency, agency_id)
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agency {agency_id} not found",
        )

    # Verify user has access to this agency
    await deps.verify_agency_access(agency_id, db, current_user)

    rt_types = [
        FeedSourceType.GTFS_REALTIME.value,
        FeedSourceType.GTFS_RT_ALERTS.value,
    ]
    query = select(ExternalFeedSource).where(
        ExternalFeedSource.agency_id == agency_id,
        ExternalFeedSource.is_enabled == True,
        ExternalFeedSource.source_type.in_(rt_types),
    )
    result = await db.execute(query)
    feed_sources = result.scalars().all()

    if not feed_sources:
        return {
            "agency_id": agency_id,
            "timestamp": datetime.utcnow().isoformat(),
            "alerts": [],
            "message": "No GTFS-RT feed sources configured for this agency",
        }

    all_alerts = []
    errors = []

    for source in feed_sources:
        try:
            # Handle internal demo feeds differently
            if is_demo_feed_url(source.url):
                alerts = await fetch_demo_alerts(source.url, db)
            else:
                content = await fetch_gtfs_rt(
                    url=source.url,
                    auth_type=source.auth_type,
                    auth_header=source.auth_header,
                    auth_value=source.auth_value,
                )
                feed = parse_gtfs_rt_feed(content)
                alerts = extract_alerts(feed)

            for a in alerts:
                a["feed_source_id"] = source.id
                a["feed_source_name"] = source.name

            all_alerts.extend(alerts)

        except Exception as e:
            errors.append({
                "feed_source_id": source.id,
                "feed_source_name": source.name,
                "error": str(e),
            })

    return {
        "agency_id": agency_id,
        "timestamp": datetime.utcnow().isoformat(),
        "alerts": all_alerts,
        "alert_count": len(all_alerts),
        "errors": errors if errors else None,
    }


@router.get("/agency/{agency_id}/trip-modifications")
async def get_realtime_trip_modifications(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """
    Get real-time trip modifications (detours, service changes) for an agency.
    Fetches data directly from configured GTFS-RT feed sources.

    Trip modifications is an experimental GTFS-RT extension for communicating
    about detours, skipped stops, and other service changes.
    """
    agency = await db.get(Agency, agency_id)
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agency {agency_id} not found",
        )

    # Verify user has access to this agency
    await deps.verify_agency_access(agency_id, db, current_user)

    rt_types = [
        FeedSourceType.GTFS_REALTIME.value,
        FeedSourceType.GTFS_RT_TRIP_MODIFICATIONS.value,
    ]
    query = select(ExternalFeedSource).where(
        ExternalFeedSource.agency_id == agency_id,
        ExternalFeedSource.is_enabled == True,
        ExternalFeedSource.source_type.in_(rt_types),
    )
    result = await db.execute(query)
    feed_sources = result.scalars().all()

    if not feed_sources:
        return {
            "agency_id": agency_id,
            "timestamp": datetime.utcnow().isoformat(),
            "trip_modifications": [],
            "message": "No GTFS-RT feed sources configured for this agency",
        }

    all_modifications = []
    errors = []

    for source in feed_sources:
        try:
            # Handle internal demo feeds differently
            if is_demo_feed_url(source.url):
                modifications = await fetch_demo_trip_modifications(source.url, db)
            else:
                content = await fetch_gtfs_rt(
                    url=source.url,
                    auth_type=source.auth_type,
                    auth_header=source.auth_header,
                    auth_value=source.auth_value,
                )
                feed = parse_gtfs_rt_feed(content)
                modifications = extract_trip_modifications(feed, raw_content=content)

            for m in modifications:
                m["feed_source_id"] = source.id
                m["feed_source_name"] = source.name

            all_modifications.extend(modifications)

        except Exception as e:
            errors.append({
                "feed_source_id": source.id,
                "feed_source_name": source.name,
                "error": str(e),
            })

    return {
        "agency_id": agency_id,
        "timestamp": datetime.utcnow().isoformat(),
        "trip_modifications": all_modifications,
        "modification_count": len(all_modifications),
        "errors": errors if errors else None,
    }


@router.get("/agency/{agency_id}/shapes")
async def get_realtime_shapes(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """
    Get real-time shapes (modified/detour shapes) for an agency.
    Fetches data directly from configured GTFS-RT feed sources.

    Real-time shapes is an experimental GTFS-RT extension for communicating
    replacement shapes during detours and service modifications.
    """
    agency = await db.get(Agency, agency_id)
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agency {agency_id} not found",
        )

    # Verify user has access to this agency
    await deps.verify_agency_access(agency_id, db, current_user)

    rt_types = [
        FeedSourceType.GTFS_REALTIME.value,
        FeedSourceType.GTFS_RT_SHAPES.value,
    ]
    query = select(ExternalFeedSource).where(
        ExternalFeedSource.agency_id == agency_id,
        ExternalFeedSource.is_enabled == True,
        ExternalFeedSource.source_type.in_(rt_types),
    )
    result = await db.execute(query)
    feed_sources = result.scalars().all()

    if not feed_sources:
        return {
            "agency_id": agency_id,
            "timestamp": datetime.utcnow().isoformat(),
            "shapes": [],
            "message": "No GTFS-RT feed sources configured for this agency",
        }

    all_shapes = []
    errors = []

    for source in feed_sources:
        try:
            # Handle internal demo feeds differently
            if is_demo_feed_url(source.url):
                shapes = await fetch_demo_shapes(source.url, db)
            else:
                content = await fetch_gtfs_rt(
                    url=source.url,
                    auth_type=source.auth_type,
                    auth_header=source.auth_header,
                    auth_value=source.auth_value,
                )
                feed = parse_gtfs_rt_feed(content)
                shapes = extract_realtime_shapes(feed, raw_content=content)

            for s in shapes:
                s["feed_source_id"] = source.id
                s["feed_source_name"] = source.name

            all_shapes.extend(shapes)

        except Exception as e:
            errors.append({
                "feed_source_id": source.id,
                "feed_source_name": source.name,
                "error": str(e),
            })

    return {
        "agency_id": agency_id,
        "timestamp": datetime.utcnow().isoformat(),
        "shapes": all_shapes,
        "shape_count": len(all_shapes),
        "errors": errors if errors else None,
    }


@router.get("/agency/{agency_id}/stops")
async def get_realtime_stops(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """
    Get real-time stops (replacement/temporary stops) for an agency.
    Fetches data directly from configured GTFS-RT feed sources.

    Real-time stops is an experimental GTFS-RT extension for communicating
    temporary stops during detours and service modifications.
    """
    agency = await db.get(Agency, agency_id)
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agency {agency_id} not found",
        )

    # Verify user has access to this agency
    await deps.verify_agency_access(agency_id, db, current_user)

    rt_types = [
        FeedSourceType.GTFS_REALTIME.value,
        FeedSourceType.GTFS_RT_STOPS.value,
    ]
    query = select(ExternalFeedSource).where(
        ExternalFeedSource.agency_id == agency_id,
        ExternalFeedSource.is_enabled == True,
        ExternalFeedSource.source_type.in_(rt_types),
    )
    result = await db.execute(query)
    feed_sources = result.scalars().all()

    if not feed_sources:
        return {
            "agency_id": agency_id,
            "timestamp": datetime.utcnow().isoformat(),
            "stops": [],
            "message": "No GTFS-RT feed sources configured for this agency",
        }

    all_stops = []
    errors = []

    for source in feed_sources:
        try:
            # Handle internal demo feeds differently
            if is_demo_feed_url(source.url):
                stops = await fetch_demo_stops(source.url, db)
            else:
                content = await fetch_gtfs_rt(
                    url=source.url,
                    auth_type=source.auth_type,
                    auth_header=source.auth_header,
                    auth_value=source.auth_value,
                )
                feed = parse_gtfs_rt_feed(content)
                stops = extract_realtime_stops(feed, raw_content=content)

            for s in stops:
                s["feed_source_id"] = source.id
                s["feed_source_name"] = source.name

            all_stops.extend(stops)

        except Exception as e:
            errors.append({
                "feed_source_id": source.id,
                "feed_source_name": source.name,
                "error": str(e),
            })

    return {
        "agency_id": agency_id,
        "timestamp": datetime.utcnow().isoformat(),
        "stops": all_stops,
        "stop_count": len(all_stops),
        "errors": errors if errors else None,
    }


@router.get("/agency/{agency_id}/all")
async def get_all_realtime_data(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """
    Get all real-time data (vehicles, trip updates, alerts, trip modifications, shapes, stops) for an agency in one call.
    More efficient than making separate requests.
    """
    agency = await db.get(Agency, agency_id)
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agency {agency_id} not found",
        )

    # Verify user has access to this agency
    await deps.verify_agency_access(agency_id, db, current_user)

    rt_types = [
        FeedSourceType.GTFS_REALTIME.value,
        FeedSourceType.GTFS_RT_VEHICLE_POSITIONS.value,
        FeedSourceType.GTFS_RT_TRIP_UPDATES.value,
        FeedSourceType.GTFS_RT_ALERTS.value,
        FeedSourceType.GTFS_RT_TRIP_MODIFICATIONS.value,
        FeedSourceType.GTFS_RT_SHAPES.value,
        FeedSourceType.GTFS_RT_STOPS.value,
    ]
    query = select(ExternalFeedSource).where(
        ExternalFeedSource.agency_id == agency_id,
        ExternalFeedSource.is_enabled == True,
        ExternalFeedSource.source_type.in_(rt_types),
    )
    result = await db.execute(query)
    feed_sources = result.scalars().all()

    if not feed_sources:
        return {
            "agency_id": agency_id,
            "timestamp": datetime.utcnow().isoformat(),
            "vehicles": [],
            "trip_updates": [],
            "alerts": [],
            "trip_modifications": [],
            "shapes": [],
            "stops": [],
            "message": "No GTFS-RT feed sources configured for this agency",
        }

    all_vehicles = []
    all_updates = []
    all_alerts = []
    all_modifications = []
    all_shapes = []
    all_stops = []
    errors = []

    # Group feed sources by URL to avoid duplicate fetches
    # (same URL might be configured for vehicle positions, trip updates, etc.)
    url_to_sources: dict[str, list] = {}
    for source in feed_sources:
        if source.url not in url_to_sources:
            url_to_sources[source.url] = []
        url_to_sources[source.url].append(source)

    # Fetch each unique URL once, with delay between fetches to avoid rate limiting
    is_first_fetch = True
    for url, sources in url_to_sources.items():
        # Add delay between fetches to avoid rate limiting (429 errors)
        if not is_first_fetch:
            await asyncio.sleep(2.0)  # 2 second delay between different URLs
        is_first_fetch = False

        source = sources[0]  # Use first source for auth info
        try:
            # Handle internal demo feeds differently
            if is_demo_feed_url(url):
                # Determine which demo feed to fetch based on URL
                if "vehicle-positions" in url:
                    vehicles = await fetch_demo_feed(url, db)
                    updates = []
                    alerts = []
                    modifications = []
                    shapes = []
                    stops = []
                elif "trip-updates" in url:
                    vehicles = []
                    updates = await fetch_demo_trip_updates(url, db)
                    alerts = []
                    modifications = []
                    shapes = []
                    stops = []
                elif "alerts" in url:
                    vehicles = []
                    updates = []
                    alerts = await fetch_demo_alerts(url, db)
                    modifications = []
                    shapes = []
                    stops = []
                elif "trip-modifications" in url:
                    vehicles = []
                    updates = []
                    alerts = []
                    modifications = await fetch_demo_trip_modifications(url, db)
                    shapes = []
                    stops = []
                elif "shapes" in url:
                    vehicles = []
                    updates = []
                    alerts = []
                    modifications = []
                    shapes = await fetch_demo_shapes(url, db)
                    stops = []
                elif "stops" in url:
                    vehicles = []
                    updates = []
                    alerts = []
                    modifications = []
                    shapes = []
                    stops = await fetch_demo_stops(url, db)
                else:
                    vehicles = []
                    updates = []
                    alerts = []
                    modifications = []
                    shapes = []
                    stops = []
            else:
                content = await fetch_gtfs_rt(
                    url=url,
                    auth_type=source.auth_type,
                    auth_header=source.auth_header,
                    auth_value=source.auth_value,
                )
                feed = parse_gtfs_rt_feed(content)

                # Extract all data types
                vehicles = extract_vehicle_positions(feed)
                updates = extract_trip_updates(feed)
                alerts = extract_alerts(feed)
                modifications = extract_trip_modifications(feed, raw_content=content)
                shapes = extract_realtime_shapes(feed, raw_content=content)
                stops = extract_realtime_stops(feed, raw_content=content)

            # Add source info (use all sources that share this URL)
            for v in vehicles:
                v["feed_source_id"] = source.id
                v["feed_source_name"] = source.name
            for u in updates:
                u["feed_source_id"] = source.id
                u["feed_source_name"] = source.name
            for a in alerts:
                a["feed_source_id"] = source.id
                a["feed_source_name"] = source.name
            for m in modifications:
                m["feed_source_id"] = source.id
                m["feed_source_name"] = source.name
            for s in shapes:
                s["feed_source_id"] = source.id
                s["feed_source_name"] = source.name
            for s in stops:
                s["feed_source_id"] = source.id
                s["feed_source_name"] = source.name

            all_vehicles.extend(vehicles)
            all_updates.extend(updates)
            all_alerts.extend(alerts)
            all_modifications.extend(modifications)
            all_shapes.extend(shapes)
            all_stops.extend(stops)

        except Exception as e:
            # Report error for all sources using this URL
            for s in sources:
                errors.append({
                    "feed_source_id": s.id,
                    "feed_source_name": s.name,
                    "error": str(e),
                })

    return {
        "agency_id": agency_id,
        "timestamp": datetime.utcnow().isoformat(),
        "vehicles": all_vehicles,
        "vehicle_count": len(all_vehicles),
        "trip_updates": all_updates,
        "trip_update_count": len(all_updates),
        "alerts": all_alerts,
        "alert_count": len(all_alerts),
        "trip_modifications": all_modifications,
        "trip_modification_count": len(all_modifications),
        "shapes": all_shapes,
        "shape_count": len(all_shapes),
        "stops": all_stops,
        "stop_count": len(all_stops),
        "errors": errors if errors else None,
    }


@router.get("/feed-source/{feed_source_id}/test")
async def test_feed_source(
    feed_source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict[str, Any]:
    """
    Test a GTFS-RT feed source connection and return sample data.
    """
    feed_source = await db.get(ExternalFeedSource, feed_source_id)
    if not feed_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed source {feed_source_id} not found",
        )

    # Verify user has access to this feed source's agency
    await deps.verify_agency_access(feed_source.agency_id, db, current_user)

    try:
        content = await fetch_gtfs_rt(
            url=feed_source.url,
            auth_type=feed_source.auth_type,
            auth_header=feed_source.auth_header,
            auth_value=feed_source.auth_value,
        )
        feed = parse_gtfs_rt_feed(content)

        vehicles = extract_vehicle_positions(feed)
        updates = extract_trip_updates(feed)
        alerts = extract_alerts(feed)
        modifications = extract_trip_modifications(feed, raw_content=content)
        shapes = extract_realtime_shapes(feed, raw_content=content)
        stops = extract_realtime_stops(feed, raw_content=content)

        return {
            "success": True,
            "feed_source_id": feed_source_id,
            "feed_timestamp": feed.header.timestamp if feed.header.HasField("timestamp") else None,
            "gtfs_realtime_version": feed.header.gtfs_realtime_version if feed.header.HasField("gtfs_realtime_version") else None,
            "entity_count": len(feed.entity),
            "vehicle_count": len(vehicles),
            "trip_update_count": len(updates),
            "alert_count": len(alerts),
            "trip_modification_count": len(modifications),
            "shape_count": len(shapes),
            "stop_count": len(stops),
            "sample_vehicles": vehicles[:5],
            "sample_trip_updates": updates[:5],
            "sample_alerts": alerts[:5],
            "sample_trip_modifications": modifications[:5],
            "sample_shapes": shapes[:5],
            "sample_stops": stops[:5],
        }

    except Exception as e:
        return {
            "success": False,
            "feed_source_id": feed_source_id,
            "error": str(e),
        }
