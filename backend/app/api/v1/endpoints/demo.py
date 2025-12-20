"""Demo endpoints for simulated GTFS-RT data"""

import math
import time
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.session import get_db
from app.models.gtfs import GTFSFeed, Route, Trip, Stop, StopTime, Shape

router = APIRouter()


def interpolate_position(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
    progress: float
) -> tuple[float, float]:
    """Interpolate position between two points based on progress (0-1)"""
    lat = lat1 + (lat2 - lat1) * progress
    lon = lon1 + (lon2 - lon1) * progress
    return lat, lon


def get_simulated_vehicle_position(
    trip_id: str,
    route_type: int,
    shape_points: list[tuple[float, float]],
    cycle_seconds: int = 60
) -> tuple[float, float, float, float]:
    """
    Calculate simulated vehicle position based on current time.

    Vehicles complete the route every cycle_seconds (default 60 seconds).
    This means positions update visibly every 15 seconds.

    Returns: (latitude, longitude, bearing, speed)
    """
    # Get current time in seconds since midnight
    now = datetime.now()
    seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second

    # Calculate progress through the route based on time
    # Use modulo to cycle through the route (completes every cycle_seconds)
    cycle_progress = (seconds_since_midnight % cycle_seconds) / cycle_seconds

    # Offset each vehicle slightly based on trip_id hash so they don't overlap
    offset = hash(trip_id) % 100 / 100 * 0.25
    adjusted_progress = (cycle_progress + offset) % 1.0

    if not shape_points:
        return (45.5088, -73.5540, 0.0, 0.0)  # Default Montreal position

    # Calculate which segment we're on
    num_segments = len(shape_points) - 1
    if num_segments <= 0:
        return (shape_points[0][0], shape_points[0][1], 0.0, 0.0)

    segment_index = int(adjusted_progress * num_segments)
    segment_progress = (adjusted_progress * num_segments) % 1.0

    # Ensure we don't go out of bounds
    segment_index = min(segment_index, num_segments - 1)

    # Get the two points for interpolation
    point1 = shape_points[segment_index]
    point2 = shape_points[segment_index + 1] if segment_index + 1 < len(shape_points) else shape_points[-1]

    # Interpolate position
    lat, lon = interpolate_position(
        point1[0], point1[1],
        point2[0], point2[1],
        segment_progress
    )

    # Calculate bearing
    lat1_rad = math.radians(point1[0])
    lat2_rad = math.radians(point2[0])
    lon_diff = math.radians(point2[1] - point1[1])

    x = math.sin(lon_diff) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(lon_diff)
    bearing = math.degrees(math.atan2(x, y))
    bearing = (bearing + 360) % 360

    # Speed in m/s (estimate based on route type)
    speed = 15.0 if route_type == 3 else 25.0  # Bus vs Rail

    return (lat, lon, bearing, speed)


def build_gtfs_rt_vehicle_positions(
    vehicles: list[dict],
    agency_id: str
) -> bytes:
    """
    Build a GTFS-RT VehiclePositions feed as Protocol Buffers.

    For simplicity, we return JSON-like structure since we don't have
    the protobuf library installed. In production, you'd use gtfs-realtime-bindings.
    """
    # Build a simple text representation that can be parsed
    # In production, use: from google.transit import gtfs_realtime_pb2

    timestamp = int(time.time())

    # Build feed header and entities as JSON for now
    # The frontend can parse this format
    feed = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "incrementality": "FULL_DATASET",
            "timestamp": timestamp
        },
        "entity": []
    }

    for i, vehicle in enumerate(vehicles):
        entity = {
            "id": f"vehicle_{i+1}",
            "vehicle": {
                "trip": {
                    "trip_id": vehicle["trip_id"],
                    "route_id": vehicle["route_id"],
                    "schedule_relationship": "SCHEDULED"
                },
                "vehicle": {
                    "id": vehicle["vehicle_id"],
                    "label": vehicle["vehicle_label"]
                },
                "position": {
                    "latitude": vehicle["latitude"],
                    "longitude": vehicle["longitude"],
                    "bearing": vehicle["bearing"],
                    "speed": vehicle["speed"]
                },
                "current_status": "IN_TRANSIT_TO",
                "timestamp": timestamp,
                "congestion_level": "RUNNING_SMOOTHLY"
            }
        }
        feed["entity"].append(entity)

    import json
    return json.dumps(feed).encode('utf-8')


@router.get("/agency/{agency_id}/vehicle-positions")
async def get_demo_vehicle_positions(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Get simulated GTFS-RT vehicle positions for a demo agency.

    Returns 4 simulated vehicles (2 for each route) moving along their
    respective shapes based on current time.
    """
    # Get the agency's feeds
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.agency_id == agency_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        return Response(
            content=build_gtfs_rt_vehicle_positions([], str(agency_id)),
            media_type="application/json"
        )

    # Get all trips with their routes
    trips_result = await db.execute(
        select(Trip, Route)
        .join(Route, and_(Trip.feed_id == Route.feed_id, Trip.route_id == Route.route_id))
        .where(Trip.feed_id == feed.id)
        .limit(8)  # Get up to 8 trips for demo (2 per route for 4 routes)
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

        # Calculate vehicle position
        lat, lon, bearing, speed = get_simulated_vehicle_position(
            trip.trip_id,
            route.route_type,
            shape_points,
            cycle_seconds=60  # Complete route every 60 seconds for visible movement
        )

        # Determine vehicle label based on route type
        if route.route_type == 1:  # Metro
            vehicle_type = "Métro"
        elif route.route_type == 3:  # Bus
            vehicle_type = "Bus"
        else:
            vehicle_type = "Train"

        vehicles.append({
            "vehicle_id": f"demo_{agency_id}_{i+1}",
            "vehicle_label": f"{vehicle_type} {route.route_short_name}-{i+1:02d}",
            "trip_id": trip.trip_id,
            "route_id": route.route_id,
            "latitude": lat,
            "longitude": lon,
            "bearing": bearing,
            "speed": speed
        })

    content = build_gtfs_rt_vehicle_positions(vehicles, str(agency_id))

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-GTFS-RT-Demo": "true"
        }
    )


@router.get("/agency/{agency_id}/vehicle-positions/status")
async def get_demo_vehicle_status(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get status information about the demo vehicle positions feed.
    """
    # Get the agency's feeds
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.agency_id == agency_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        return {
            "status": "no_feed",
            "message": "No GTFS feed found for this agency",
            "vehicle_count": 0
        }

    # Count trips
    trips_result = await db.execute(
        select(Trip).where(Trip.feed_id == feed.id)
    )
    trips = trips_result.scalars().all()

    return {
        "status": "active",
        "message": "Demo vehicle positions feed is active",
        "vehicle_count": min(len(trips), 8),
        "feed_id": feed.id,
        "agency_id": agency_id,
        "refresh_interval_seconds": 5,
        "endpoint": f"/api/v1/demo/agency/{agency_id}/vehicle-positions"
    }


# ============================================================================
# Trip Updates Demo Endpoint
# ============================================================================

def build_gtfs_rt_trip_updates(
    trip_updates: list[dict],
    agency_id: str
) -> bytes:
    """Build a GTFS-RT TripUpdates feed as JSON."""
    import json
    timestamp = int(time.time())

    feed = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "incrementality": "FULL_DATASET",
            "timestamp": timestamp
        },
        "entity": []
    }

    for i, update in enumerate(trip_updates):
        entity = {
            "id": f"trip_update_{i+1}",
            "trip_update": {
                "trip": {
                    "trip_id": update["trip_id"],
                    "route_id": update["route_id"],
                    "schedule_relationship": update.get("schedule_relationship", "SCHEDULED")
                },
                "vehicle": {
                    "id": update.get("vehicle_id", f"vehicle_{i+1}"),
                    "label": update.get("vehicle_label", f"Vehicle {i+1}")
                },
                "stop_time_update": update.get("stop_time_updates", []),
                "timestamp": timestamp,
                "delay": update.get("delay", 0)
            }
        }
        feed["entity"].append(entity)

    return json.dumps(feed).encode('utf-8')


def get_simulated_delay(trip_id: str, route_type: int) -> int:
    """
    Calculate simulated delay based on current time and trip ID.

    Delays vary between -60 (early) and +300 seconds (late).
    Bus routes tend to have more variability than trains.
    """
    now = datetime.now()
    seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second

    # Use trip_id hash for consistent but varying delays
    trip_hash = hash(trip_id)

    # Create time-varying delay (changes every minute)
    time_factor = (seconds_since_midnight // 60) % 10
    base_delay = (trip_hash % 7 - 3) * 30  # -90 to +90 seconds base

    # Add time-varying component
    variation = int(math.sin(time_factor * 0.6) * 60)

    # Buses have more delay variability
    if route_type == 3:  # Bus
        variation *= 2

    delay = base_delay + variation

    # Clamp to reasonable range
    return max(-60, min(300, delay))


@router.get("/agency/{agency_id}/trip-updates")
async def get_demo_trip_updates(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Get simulated GTFS-RT trip updates for a demo agency.

    Returns delay information for all trips, simulating realistic
    transit delays that vary over time.
    """
    # Get the agency's feeds
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.agency_id == agency_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        return Response(
            content=build_gtfs_rt_trip_updates([], str(agency_id)),
            media_type="application/json"
        )

    # Get all trips with their routes and stop times
    trips_result = await db.execute(
        select(Trip, Route)
        .join(Route, and_(Trip.feed_id == Route.feed_id, Trip.route_id == Route.route_id))
        .where(Trip.feed_id == feed.id)
    )
    trips_with_routes = trips_result.all()

    trip_updates = []

    for trip, route in trips_with_routes:
        delay = get_simulated_delay(trip.trip_id, route.route_type)

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
            # Add some variation per stop (recovery or additional delay)
            stop_variation = (hash(f"{trip.trip_id}_{stop.stop_id}") % 30) - 15
            cumulative_delay = max(-30, cumulative_delay + stop_variation)

            stop_time_updates.append({
                "stop_sequence": stop_time.stop_sequence,
                "stop_id": stop.stop_id,
                "arrival": {
                    "delay": cumulative_delay,
                    "time": int(time.time()) + cumulative_delay
                },
                "departure": {
                    "delay": cumulative_delay,
                    "time": int(time.time()) + cumulative_delay + 30
                },
                "schedule_relationship": "SCHEDULED"
            })

        vehicle_type = "Bus" if route.route_type == 3 else "Train"
        trip_updates.append({
            "trip_id": trip.trip_id,
            "route_id": route.route_id,
            "vehicle_id": f"demo_{agency_id}_{trip.trip_id}",
            "vehicle_label": f"{vehicle_type} {route.route_short_name}",
            "delay": delay,
            "schedule_relationship": "SCHEDULED",
            "stop_time_updates": stop_time_updates
        })

    content = build_gtfs_rt_trip_updates(trip_updates, str(agency_id))

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-GTFS-RT-Demo": "true"
        }
    )


# ============================================================================
# Service Alerts Demo Endpoint
# ============================================================================

def build_gtfs_rt_alerts(
    alerts: list[dict],
    agency_id: str
) -> bytes:
    """Build a GTFS-RT Alerts feed as JSON."""
    import json
    timestamp = int(time.time())

    feed = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "incrementality": "FULL_DATASET",
            "timestamp": timestamp
        },
        "entity": []
    }

    for i, alert in enumerate(alerts):
        entity = {
            "id": alert.get("alert_id", f"alert_{i+1}"),
            "alert": {
                "active_period": alert.get("active_period", []),
                "informed_entity": alert.get("informed_entity", []),
                "cause": alert.get("cause", "OTHER_CAUSE"),
                "effect": alert.get("effect", "OTHER_EFFECT"),
                "header_text": {
                    "translation": [
                        {"text": alert.get("header_text", "Service Alert"), "language": "en"}
                    ]
                },
                "description_text": {
                    "translation": [
                        {"text": alert.get("description_text", ""), "language": "en"}
                    ]
                },
                "severity_level": alert.get("severity_level", "INFO")
            }
        }
        feed["entity"].append(entity)

    return json.dumps(feed).encode('utf-8')


# Demo alerts that rotate based on time - Montreal themed
DEMO_ALERTS = [
    {
        "alert_id": "demo_alert_weather",
        "cause": "WEATHER",
        "effect": "SIGNIFICANT_DELAYS",
        "severity_level": "WARNING",
        "header_text": "Avis météo / Weather Advisory",
        "description_text": "En raison des conditions météorologiques hivernales, attendez-vous à des retards de 15 minutes sur toutes les lignes. / Due to winter weather conditions, expect delays of up to 15 minutes on all lines.",
        "affects": "all"
    },
    {
        "alert_id": "demo_alert_maintenance",
        "cause": "MAINTENANCE",
        "effect": "MODIFIED_SERVICE",
        "severity_level": "INFO",
        "header_text": "Travaux de maintenance / Scheduled Maintenance",
        "description_text": "Travaux de maintenance prévus ce week-end sur la Ligne Orange. Service de navettes entre Berri-UQAM et Montmorency. / Track maintenance on Orange Line this weekend. Shuttle buses between Berri-UQAM and Montmorency.",
        "affects": "metro"
    },
    {
        "alert_id": "demo_alert_construction",
        "cause": "CONSTRUCTION",
        "effect": "DETOUR",
        "severity_level": "WARNING",
        "header_text": "Détour 747 Aéroport / 747 Airport Detour",
        "description_text": "En raison de travaux sur l'autoroute 20, le 747 emprunte un détour via Côte-de-Liesse. / Due to construction on Highway 20, the 747 is detouring via Côte-de-Liesse.",
        "affects": "bus"
    },
    {
        "alert_id": "demo_alert_special",
        "cause": "HOLIDAY",
        "effect": "ADDITIONAL_SERVICE",
        "severity_level": "INFO",
        "header_text": "Festival de Jazz / Jazz Festival",
        "description_text": "Service supplémentaire pour le Festival de Jazz. Métros toutes les 3 minutes. / Additional service for Jazz Festival. Metros every 3 minutes.",
        "affects": "all"
    },
    {
        "alert_id": "demo_alert_accessibility",
        "cause": "TECHNICAL_PROBLEM",
        "effect": "ACCESSIBILITY_ISSUE",
        "severity_level": "WARNING",
        "header_text": "Ascenseur hors service / Elevator Out of Service",
        "description_text": "L'ascenseur à la station Berri-UQAM (sortie Place Dupuis) est temporairement hors service. Utilisez l'entrée accessible rue Sainte-Catherine. / Elevator at Berri-UQAM station (Place Dupuis exit) temporarily out of service.",
        "affects": "metro"
    }
]


@router.get("/agency/{agency_id}/alerts")
async def get_demo_alerts(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Get simulated GTFS-RT service alerts for a demo agency.

    Returns a rotating set of realistic service alerts that change
    based on the current time (different alerts active at different hours).
    """
    # Get the agency's feeds
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.agency_id == agency_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        return Response(
            content=build_gtfs_rt_alerts([], str(agency_id)),
            media_type="application/json"
        )

    # Get routes for entity references
    routes_result = await db.execute(
        select(Route).where(Route.feed_id == feed.id)
    )
    routes = routes_result.scalars().all()

    bus_routes = [r for r in routes if r.route_type == 3]
    metro_routes = [r for r in routes if r.route_type == 1]
    train_routes = [r for r in routes if r.route_type == 2]

    # Select active alerts based on current hour
    now = datetime.now()
    current_hour = now.hour

    # Different alerts are "active" at different times
    # This creates variety throughout the day
    active_alert_indices = [
        current_hour % len(DEMO_ALERTS),
        (current_hour + 2) % len(DEMO_ALERTS)
    ]

    alerts = []
    timestamp = int(time.time())

    for idx in active_alert_indices:
        alert_template = DEMO_ALERTS[idx]

        # Build informed entities based on what the alert affects
        informed_entity = []
        if alert_template["affects"] == "all":
            informed_entity = [{"agency_id": "demo_agency"}]
        elif alert_template["affects"] == "bus" and bus_routes:
            informed_entity = [{"route_id": r.route_id} for r in bus_routes]
        elif alert_template["affects"] == "metro" and metro_routes:
            informed_entity = [{"route_id": r.route_id} for r in metro_routes]
        elif alert_template["affects"] == "train" and train_routes:
            informed_entity = [{"route_id": r.route_id} for r in train_routes]
        else:
            informed_entity = [{"agency_id": "demo_agency"}]

        alerts.append({
            "alert_id": f"{alert_template['alert_id']}_{agency_id}",
            "cause": alert_template["cause"],
            "effect": alert_template["effect"],
            "severity_level": alert_template["severity_level"],
            "header_text": alert_template["header_text"],
            "description_text": alert_template["description_text"],
            "informed_entity": informed_entity,
            "active_period": [{
                "start": timestamp - 3600,  # Started 1 hour ago
                "end": timestamp + 7200     # Ends in 2 hours
            }]
        })

    content = build_gtfs_rt_alerts(alerts, str(agency_id))

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-GTFS-RT-Demo": "true"
        }
    )


# ============================================================================
# Trip Modifications Demo Endpoint
# ============================================================================

def build_gtfs_rt_trip_modifications(
    modifications: list[dict],
    agency_id: str
) -> bytes:
    """Build a GTFS-RT TripModifications feed as JSON."""
    import json
    timestamp = int(time.time())

    feed = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "incrementality": "FULL_DATASET",
            "timestamp": timestamp
        },
        "entity": []
    }

    for i, mod in enumerate(modifications):
        entity = {
            "id": mod.get("modification_id", f"modification_{i+1}"),
            "trip_modifications": {
                "selected_trips": mod.get("selected_trips", []),
                "start_times": mod.get("start_times", []),
                "service_dates": mod.get("service_dates", []),
                "modifications": mod.get("modifications", [])
            }
        }
        feed["entity"].append(entity)

    return json.dumps(feed).encode('utf-8')


@router.get("/agency/{agency_id}/trip-modifications")
async def get_demo_trip_modifications(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Get simulated GTFS-RT trip modifications for a demo agency.

    Returns simulated detours and route modifications that demonstrate
    the trip modifications extension (experimental GTFS-RT feature).
    """
    # Get the agency's feeds
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.agency_id == agency_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        return Response(
            content=build_gtfs_rt_trip_modifications([], str(agency_id)),
            media_type="application/json"
        )

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

        # Create a demo detour for the 747 Airport Express
        # This demonstrates a complete trip modification with:
        # - A replacement shape (detour via Côte-de-Liesse)
        # - Three temporary stops along the detour
        # - A 5-minute delay due to the longer route
        modifications.append({
            "modification_id": f"demo_detour_{agency_id}",
            "selected_trips": [{
                "route_id": bus_route.route_id,
                "direction_id": 0
            }],
            "start_times": ["06:00:00", "07:00:00", "08:00:00"],
            "service_dates": [today],
            "modifications": [{
                "start_stop_selector": {
                    "stop_id": bus_stops[0].stop_id  # Gare d'autocars
                },
                "end_stop_selector": {
                    "stop_id": bus_stops[-1].stop_id if len(bus_stops) > 1 else bus_stops[0].stop_id  # Airport
                },
                "propagated_modification_delay": 300,  # 5 minute delay from detour via Côte-de-Liesse
                "replacement_shape_id": f"demo_detour_shape_{agency_id}",  # Reference to the detour shape
                "replacement_stops": [
                    {
                        "travel_time_to_stop": 120,  # 2 minutes
                        "stop_id": f"temp_stop_1_{agency_id}",
                        "stop_name": "Temporary Stop - Detour / Arrêt temporaire - Détour",
                        "stop_lat": 45.4860,
                        "stop_lon": -73.5840
                    }
                ]
            }]
        })

    content = build_gtfs_rt_trip_modifications(modifications, str(agency_id))

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-GTFS-RT-Demo": "true"
        }
    )


# ============================================================================
# Shapes Demo Endpoint (Detour Shapes - experimental)
# ============================================================================

def build_gtfs_rt_shapes(
    shapes: list[dict],
    agency_id: str
) -> bytes:
    """Build a GTFS-RT Shapes feed as JSON."""
    import json
    timestamp = int(time.time())

    feed = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "incrementality": "FULL_DATASET",
            "timestamp": timestamp
        },
        "entity": []
    }

    for i, shape_data in enumerate(shapes):
        entity = {
            "id": shape_data.get("shape_id", f"shape_{i+1}"),
            "shape": {
                "shape_id": shape_data["shape_id"],
                "encoded_polyline": shape_data.get("encoded_polyline", ""),
                "shape_points": shape_data.get("shape_points", [])
            }
        }
        feed["entity"].append(entity)

    return json.dumps(feed).encode('utf-8')


@router.get("/agency/{agency_id}/shapes")
async def get_demo_shapes(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Get simulated GTFS-RT replacement shapes for a demo agency.

    Returns detour shapes that demonstrate the shapes extension
    (experimental GTFS-RT feature) for trip modifications.
    """
    # Get the agency's feeds
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.agency_id == agency_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        return Response(
            content=build_gtfs_rt_shapes([], str(agency_id)),
            media_type="application/json"
        )

    # Get routes
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

        # Create a tight local detour - just 1-2 blocks around street closure
        # Small rectangular loop to avoid construction (like the black line in the image)
        detour_shape_points = [
            {"lat": 45.4850, "lon": -73.5820, "sequence": 0},  # Detour start point
            {"lat": 45.4855, "lon": -73.5835, "sequence": 1},  # Turn north/west 1 block
            {"lat": 45.4860, "lon": -73.5840, "sequence": 2},  # Continue around
            {"lat": 45.4865, "lon": -73.5830, "sequence": 3},  # Turn back east
            {"lat": 45.4870, "lon": -73.5815, "sequence": 4},  # Reconnect to route
        ]

        shapes.append({
            "shape_id": f"demo_detour_shape_{agency_id}",
            "shape_points": detour_shape_points
        })

    content = build_gtfs_rt_shapes(shapes, str(agency_id))

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-GTFS-RT-Demo": "true"
        }
    )


# ============================================================================
# Stops Demo Endpoint (Temporary/Replacement Stops - experimental)
# ============================================================================

def build_gtfs_rt_stops(
    stops: list[dict],
    agency_id: str
) -> bytes:
    """Build a GTFS-RT Stops feed as JSON."""
    import json
    timestamp = int(time.time())

    feed = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "incrementality": "FULL_DATASET",
            "timestamp": timestamp
        },
        "entity": []
    }

    for i, stop_data in enumerate(stops):
        entity = {
            "id": stop_data.get("stop_id", f"stop_{i+1}"),
            "stop": {
                "stop_id": stop_data["stop_id"],
                "stop_name": stop_data.get("stop_name", ""),
                "stop_lat": stop_data.get("stop_lat", 0.0),
                "stop_lon": stop_data.get("stop_lon", 0.0),
                "stop_desc": stop_data.get("stop_desc", ""),
                "wheelchair_boarding": stop_data.get("wheelchair_boarding", 0)
            }
        }
        feed["entity"].append(entity)

    return json.dumps(feed).encode('utf-8')


@router.get("/agency/{agency_id}/stops")
async def get_demo_stops(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Get simulated GTFS-RT temporary/replacement stops for a demo agency.

    Returns temporary stops that demonstrate the stops extension
    (experimental GTFS-RT feature) for trip modifications with detours.
    """
    # Get the agency's feeds
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.agency_id == agency_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        return Response(
            content=build_gtfs_rt_stops([], str(agency_id)),
            media_type="application/json"
        )

    # Get routes
    routes_result = await db.execute(
        select(Route).where(Route.feed_id == feed.id)
    )
    routes = routes_result.scalars().all()

    bus_routes = [r for r in routes if r.route_type == 3]

    stops = []
    now = datetime.now()

    # Only show temporary stops during certain hours (simulating active detours)
    if 6 <= now.hour <= 22 and bus_routes:
        bus_route = bus_routes[0]

        # Create 1-2 temporary stops along the tight detour
        temporary_stops = [
            {
                "stop_id": f"temp_stop_1_{agency_id}",
                "stop_name": "Temporary Stop - Detour / Arrêt temporaire - Détour",
                "stop_lat": 45.4860,
                "stop_lon": -73.5840,
                "stop_desc": "Temporary stop due to street closure / Arrêt temporaire en raison de fermeture de rue",
                "wheelchair_boarding": 1
            }
        ]

        stops.extend(temporary_stops)

    content = build_gtfs_rt_stops(stops, str(agency_id))

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-GTFS-RT-Demo": "true"
        }
    )
