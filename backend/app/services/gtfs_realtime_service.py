"""Service for parsing and storing GTFS-Realtime data"""

import httpx
from datetime import datetime
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from google.transit import gtfs_realtime_pb2

from app.models.gtfs_realtime import (
    RealtimeVehiclePosition,
    RealtimeTripUpdate,
    RealtimeAlert,
)
from app.models.feed_source import ExternalFeedSource, FeedSourceStatus


class GTFSRealtimeService:
    """Service for fetching and parsing GTFS-Realtime feeds"""

    async def fetch_feed(
        self,
        url: str,
        auth_type: Optional[str] = None,
        auth_header: Optional[str] = None,
        auth_value: Optional[str] = None,
        timeout: float = 30.0,
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
            response.raise_for_status()
            return response.content

    def parse_feed(self, content: bytes) -> gtfs_realtime_pb2.FeedMessage:
        """Parse GTFS-RT protobuf content"""
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(content)
        return feed

    async def process_vehicle_positions(
        self,
        db: AsyncSession,
        feed_source_id: int,
        feed: gtfs_realtime_pb2.FeedMessage,
    ) -> int:
        """Process and store vehicle positions from GTFS-RT feed"""
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
                "feed_source_id": feed_source_id,
                "vehicle_id": vehicle_desc.id if vehicle_desc else entity.id,
                "vehicle_label": vehicle_desc.label if vehicle_desc else None,
                "license_plate": vehicle_desc.license_plate if vehicle_desc else None,
                "latitude": position.latitude,
                "longitude": position.longitude,
                "bearing": position.bearing if position.HasField("bearing") else None,
                "speed": position.speed if position.HasField("speed") else None,
                "odometer": position.odometer if position.HasField("odometer") else None,
                "trip_id": trip.trip_id if trip else None,
                "route_id": trip.route_id if trip else None,
                "direction_id": trip.direction_id if trip and trip.HasField("direction_id") else None,
                "start_time": trip.start_time if trip else None,
                "start_date": trip.start_date if trip else None,
                "schedule_relationship": self._get_schedule_relationship(trip.schedule_relationship) if trip else None,
                "current_stop_sequence": vehicle.current_stop_sequence if vehicle.HasField("current_stop_sequence") else None,
                "stop_id": vehicle.stop_id if vehicle.HasField("stop_id") else None,
                "current_status": self._get_vehicle_stop_status(vehicle.current_status) if vehicle.HasField("current_status") else None,
                "congestion_level": self._get_congestion_level(vehicle.congestion_level) if vehicle.HasField("congestion_level") else None,
                "occupancy_status": self._get_occupancy_status(vehicle.occupancy_status) if vehicle.HasField("occupancy_status") else None,
                "occupancy_percentage": vehicle.occupancy_percentage if vehicle.HasField("occupancy_percentage") else None,
                "timestamp": vehicle.timestamp if vehicle.HasField("timestamp") else None,
            }
            positions.append(position_data)

        if positions:
            # Upsert positions
            stmt = pg_insert(RealtimeVehiclePosition).values(positions)
            stmt = stmt.on_conflict_do_update(
                index_elements=["feed_source_id", "vehicle_id"],
                set_={
                    "vehicle_label": stmt.excluded.vehicle_label,
                    "license_plate": stmt.excluded.license_plate,
                    "latitude": stmt.excluded.latitude,
                    "longitude": stmt.excluded.longitude,
                    "bearing": stmt.excluded.bearing,
                    "speed": stmt.excluded.speed,
                    "odometer": stmt.excluded.odometer,
                    "trip_id": stmt.excluded.trip_id,
                    "route_id": stmt.excluded.route_id,
                    "direction_id": stmt.excluded.direction_id,
                    "start_time": stmt.excluded.start_time,
                    "start_date": stmt.excluded.start_date,
                    "schedule_relationship": stmt.excluded.schedule_relationship,
                    "current_stop_sequence": stmt.excluded.current_stop_sequence,
                    "stop_id": stmt.excluded.stop_id,
                    "current_status": stmt.excluded.current_status,
                    "congestion_level": stmt.excluded.congestion_level,
                    "occupancy_status": stmt.excluded.occupancy_status,
                    "occupancy_percentage": stmt.excluded.occupancy_percentage,
                    "timestamp": stmt.excluded.timestamp,
                    "updated_at": datetime.utcnow(),
                },
            )
            await db.execute(stmt)
            await db.commit()

        return len(positions)

    async def process_trip_updates(
        self,
        db: AsyncSession,
        feed_source_id: int,
        feed: gtfs_realtime_pb2.FeedMessage,
    ) -> int:
        """Process and store trip updates from GTFS-RT feed"""
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
                if stu.HasField("schedule_relationship"):
                    stu_data["schedule_relationship"] = self._get_stop_time_relationship(stu.schedule_relationship)
                stop_time_updates.append(stu_data)

            update_data = {
                "feed_source_id": feed_source_id,
                "trip_id": trip.trip_id,
                "route_id": trip.route_id if trip.HasField("route_id") else None,
                "direction_id": trip.direction_id if trip.HasField("direction_id") else None,
                "start_time": trip.start_time if trip.HasField("start_time") else None,
                "start_date": trip.start_date if trip.HasField("start_date") else None,
                "schedule_relationship": self._get_schedule_relationship(trip.schedule_relationship) if trip.HasField("schedule_relationship") else None,
                "vehicle_id": vehicle.id if vehicle else None,
                "vehicle_label": vehicle.label if vehicle else None,
                "delay": trip_update.delay if trip_update.HasField("delay") else None,
                "timestamp": trip_update.timestamp if trip_update.HasField("timestamp") else None,
                "raw_data": {"stop_time_updates": stop_time_updates} if stop_time_updates else None,
            }
            updates.append(update_data)

        if updates:
            stmt = pg_insert(RealtimeTripUpdate).values(updates)
            stmt = stmt.on_conflict_do_update(
                index_elements=["feed_source_id", "trip_id"],
                set_={
                    "route_id": stmt.excluded.route_id,
                    "direction_id": stmt.excluded.direction_id,
                    "start_time": stmt.excluded.start_time,
                    "start_date": stmt.excluded.start_date,
                    "schedule_relationship": stmt.excluded.schedule_relationship,
                    "vehicle_id": stmt.excluded.vehicle_id,
                    "vehicle_label": stmt.excluded.vehicle_label,
                    "delay": stmt.excluded.delay,
                    "timestamp": stmt.excluded.timestamp,
                    "raw_data": stmt.excluded.raw_data,
                    "updated_at": datetime.utcnow(),
                },
            )
            await db.execute(stmt)
            await db.commit()

        return len(updates)

    async def process_alerts(
        self,
        db: AsyncSession,
        feed_source_id: int,
        feed: gtfs_realtime_pb2.FeedMessage,
    ) -> int:
        """Process and store alerts from GTFS-RT feed"""
        alerts = []

        for entity in feed.entity:
            if not entity.HasField("alert"):
                continue

            alert = entity.alert

            # Extract active periods
            active_start = None
            active_end = None
            if alert.active_period:
                period = alert.active_period[0]
                active_start = period.start if period.HasField("start") else None
                active_end = period.end if period.HasField("end") else None

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
            header_text = self._extract_translated_string(alert.header_text) if alert.HasField("header_text") else None
            description_text = self._extract_translated_string(alert.description_text) if alert.HasField("description_text") else None

            alert_data = {
                "feed_source_id": feed_source_id,
                "alert_id": entity.id,
                "active_period_start": active_start,
                "active_period_end": active_end,
                "informed_entities": informed_entities if informed_entities else None,
                "cause": self._get_alert_cause(alert.cause) if alert.HasField("cause") else None,
                "effect": self._get_alert_effect(alert.effect) if alert.HasField("effect") else None,
                "severity_level": self._get_severity_level(alert.severity_level) if alert.HasField("severity_level") else None,
                "header_text": header_text,
                "description_text": description_text,
                "url": self._extract_translated_string(alert.url).get("en") if alert.HasField("url") else None,
            }
            alerts.append(alert_data)

        if alerts:
            # First delete old alerts for this feed source
            await db.execute(
                delete(RealtimeAlert).where(RealtimeAlert.feed_source_id == feed_source_id)
            )

            # Insert new alerts
            stmt = pg_insert(RealtimeAlert).values(alerts)
            stmt = stmt.on_conflict_do_update(
                index_elements=["feed_source_id", "alert_id"],
                set_={
                    "active_period_start": stmt.excluded.active_period_start,
                    "active_period_end": stmt.excluded.active_period_end,
                    "informed_entities": stmt.excluded.informed_entities,
                    "cause": stmt.excluded.cause,
                    "effect": stmt.excluded.effect,
                    "severity_level": stmt.excluded.severity_level,
                    "header_text": stmt.excluded.header_text,
                    "description_text": stmt.excluded.description_text,
                    "url": stmt.excluded.url,
                    "updated_at": datetime.utcnow(),
                },
            )
            await db.execute(stmt)
            await db.commit()

        return len(alerts)

    def _extract_translated_string(self, ts) -> dict[str, str]:
        """Extract translated string to dict"""
        result = {}
        for translation in ts.translation:
            lang = translation.language if translation.language else "en"
            result[lang] = translation.text
        return result

    def _get_schedule_relationship(self, sr) -> str:
        """Convert schedule relationship enum to string"""
        mapping = {
            0: "scheduled",
            1: "added",
            2: "unscheduled",
            3: "canceled",
            5: "replacement",
        }
        return mapping.get(sr, "scheduled")

    def _get_vehicle_stop_status(self, status) -> str:
        """Convert vehicle stop status to string"""
        mapping = {
            0: "incoming_at",
            1: "stopped_at",
            2: "in_transit_to",
        }
        return mapping.get(status, "in_transit_to")

    def _get_congestion_level(self, level) -> str:
        """Convert congestion level to string"""
        mapping = {
            0: "unknown",
            1: "running_smoothly",
            2: "stop_and_go",
            3: "congestion",
            4: "severe_congestion",
        }
        return mapping.get(level, "unknown")

    def _get_occupancy_status(self, status) -> str:
        """Convert occupancy status to string"""
        mapping = {
            0: "empty",
            1: "many_seats_available",
            2: "few_seats_available",
            3: "standing_room_only",
            4: "crushed_standing_room_only",
            5: "full",
            6: "not_accepting_passengers",
        }
        return mapping.get(status, "empty")

    def _get_stop_time_relationship(self, sr) -> str:
        """Convert stop time schedule relationship to string"""
        mapping = {
            0: "scheduled",
            1: "skipped",
            2: "no_data",
        }
        return mapping.get(sr, "scheduled")

    def _get_alert_cause(self, cause) -> str:
        """Convert alert cause to string"""
        mapping = {
            1: "unknown_cause",
            2: "other_cause",
            3: "technical_problem",
            4: "strike",
            5: "demonstration",
            6: "accident",
            7: "holiday",
            8: "weather",
            9: "maintenance",
            10: "construction",
            11: "police_activity",
            12: "medical_emergency",
        }
        return mapping.get(cause, "unknown_cause")

    def _get_alert_effect(self, effect) -> str:
        """Convert alert effect to string"""
        mapping = {
            1: "no_service",
            2: "reduced_service",
            3: "significant_delays",
            4: "detour",
            5: "additional_service",
            6: "modified_service",
            7: "other_effect",
            8: "unknown_effect",
            9: "stop_moved",
            10: "no_effect",
            11: "accessibility_issue",
        }
        return mapping.get(effect, "unknown_effect")

    def _get_severity_level(self, level) -> str:
        """Convert severity level to string"""
        mapping = {
            1: "unknown",
            2: "info",
            3: "warning",
            4: "severe",
        }
        return mapping.get(level, "unknown")


# Singleton instance
gtfs_realtime_service = GTFSRealtimeService()
