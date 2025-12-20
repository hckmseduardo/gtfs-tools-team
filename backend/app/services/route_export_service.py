"""Route Export Service - handles atomic creation of routes from Route Creator"""

import math
from typing import List, Dict, Any, Callable, Awaitable, Optional
from decimal import Decimal
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth using the Haversine formula.

    Args:
        lat1, lon1: Latitude and longitude of the first point (in degrees)
        lat2, lon2: Latitude and longitude of the second point (in degrees)

    Returns:
        Distance in meters
    """
    # Earth's radius in meters
    R = 6371000

    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    # Haversine formula
    a = math.sin(delta_lat / 2) ** 2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

from app.models.gtfs import Route, Stop, Trip, StopTime, Shape, Calendar, GTFSFeed
from app.models.audit import AuditLog, AuditAction
from app.schemas.route_export import (
    RouteExportPayload,
    RouteExportResult,
    RouteExportValidation,
)


class RouteExportService:
    """Service for exporting routes from Route Creator to GTFS feed"""

    async def validate_payload(
        self,
        db: AsyncSession,
        payload: RouteExportPayload,
    ) -> RouteExportValidation:
        """
        Validate export payload before processing.
        Returns validation result with errors, warnings, and summary.
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Check feed exists
        feed_result = await db.execute(
            select(GTFSFeed).where(GTFSFeed.id == payload.feed_id)
        )
        feed = feed_result.scalar_one_or_none()
        if not feed:
            errors.append(f"Feed with ID {payload.feed_id} not found")

        # Check service_ids exist (Calendar uses composite key: feed_id + service_id)
        for service_id in payload.service_ids:
            calendar_result = await db.execute(
                select(Calendar).where(
                    and_(
                        Calendar.service_id == service_id,
                        Calendar.feed_id == payload.feed_id
                    )
                )
            )
            if not calendar_result.scalar_one_or_none():
                errors.append(f"Calendar with service_id '{service_id}' not found in feed")

        # Check route_id doesn't already exist in feed
        existing_route = await db.execute(
            select(Route).where(
                and_(
                    Route.feed_id == payload.feed_id,
                    Route.route_id == payload.route.route_id
                )
            )
        )
        if existing_route.scalar_one_or_none():
            errors.append(f"Route with route_id '{payload.route.route_id}' already exists in feed")

        # Check shape_id doesn't already exist (Shape uses composite key: feed_id, shape_id, shape_pt_sequence)
        existing_shape = await db.execute(
            select(Shape.shape_id).where(
                and_(
                    Shape.feed_id == payload.feed_id,
                    Shape.shape_id == payload.shape_id
                )
            ).limit(1)
        )
        if existing_shape.scalar_one_or_none():
            errors.append(f"Shape with shape_id '{payload.shape_id}' already exists in feed")

        # Check for duplicate stop_ids in new stops
        new_stop_ids = [s.stop_id for s in payload.new_stops]
        if len(new_stop_ids) != len(set(new_stop_ids)):
            errors.append("Duplicate stop_id found in new stops list")

        # Check new stops don't already exist
        for new_stop in payload.new_stops:
            existing_stop = await db.execute(
                select(Stop).where(
                    and_(
                        Stop.feed_id == payload.feed_id,
                        Stop.stop_id == new_stop.stop_id
                    )
                )
            )
            if existing_stop.scalar_one_or_none():
                errors.append(f"Stop with stop_id '{new_stop.stop_id}' already exists in feed")

        # Check trip_ids are unique
        trip_ids = [t.trip_id for t in payload.trips]
        if len(trip_ids) != len(set(trip_ids)):
            errors.append("Duplicate trip_id found in trips list")

        # Validate stop_times reference valid stop_ids
        all_stop_ids = set(new_stop_ids)
        # Get existing stops in feed for validation
        existing_stops_result = await db.execute(
            select(Stop.stop_id).where(Stop.feed_id == payload.feed_id)
        )
        existing_stop_ids = {row[0] for row in existing_stops_result.fetchall()}
        all_stop_ids.update(existing_stop_ids)

        for st in payload.stop_times:
            if st.stop_id not in all_stop_ids:
                errors.append(f"Stop time references unknown stop_id '{st.stop_id}'")

        # Validate stop_times reference valid trip_ids
        trip_id_set = set(trip_ids)
        for st in payload.stop_times:
            if st.trip_id not in trip_id_set:
                errors.append(f"Stop time references unknown trip_id '{st.trip_id}'")

        # Warnings for potential issues
        if len(payload.shape_points) < 10:
            warnings.append("Shape has fewer than 10 points - may appear coarse on map")

        if len(payload.trips) * len(payload.service_ids) > 100:
            warnings.append(f"This will create {len(payload.trips) * len(payload.service_ids)} trips - large operation")

        # Build summary
        summary = {
            "route_id": payload.route.route_id,
            "route_short_name": payload.route.route_short_name,
            "new_stops_count": len(payload.new_stops),
            "shape_points_count": len(payload.shape_points),
            "trip_patterns_count": len(payload.trips),
            "service_calendars_count": len(payload.service_ids),
            "total_trips": len(payload.trips) * len(payload.service_ids),
            "stop_times_per_trip": len(set(st.stop_id for st in payload.stop_times)),
            "total_stop_times": len(payload.stop_times) * len(payload.service_ids),
        }

        return RouteExportValidation(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            summary=summary,
        )

    async def export_route(
        self,
        db: AsyncSession,
        payload: RouteExportPayload,
        user_id: int,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> RouteExportResult:
        """
        Export route data to GTFS feed in a single atomic transaction.

        Progress stages:
        - 0-10%: Creating route
        - 10-25%: Creating stops
        - 25-45%: Creating shape
        - 45-80%: Creating trips
        - 80-100%: Creating stop times
        """
        warnings: List[str] = []

        async def update_progress(progress: float, message: str):
            if progress_callback:
                await progress_callback(progress, message)

        await update_progress(0, "Starting route export")

        # Get feed for agency_id lookup
        feed_result = await db.execute(
            select(GTFSFeed).where(GTFSFeed.id == payload.feed_id)
        )
        feed = feed_result.scalar_one()
        agency_id = feed.agency_id

        # 1. Create Route (0-10%)
        await update_progress(5, "Creating route")

        route = Route(
            feed_id=payload.feed_id,
            route_id=payload.route.route_id,
            agency_id=agency_id,  # Required field - link to agency
            route_short_name=payload.route.route_short_name or "",
            route_long_name=payload.route.route_long_name or "",
            route_type=payload.route.route_type,
            route_color=payload.route.route_color,
            route_text_color=payload.route.route_text_color,
            route_desc=payload.route.route_desc,
            custom_fields=payload.route.custom_fields,
        )
        db.add(route)
        await db.flush()

        # Create audit log directly (no User object needed in Celery tasks)
        # Route uses composite key (feed_id, route_id)
        audit_log = AuditLog(
            user_id=user_id,
            agency_id=agency_id,
            action=AuditAction.CREATE.value,
            entity_type="Route",
            entity_id=f"{payload.feed_id}:{route.route_id}",
            new_values={"route_id": route.route_id, "route_short_name": route.route_short_name}
        )
        db.add(audit_log)

        await update_progress(10, f"Route '{route.route_id}' created")

        # 2. Create new stops (10-25%)
        stops_created = 0
        valid_stop_ids: set = set()

        # First, get all existing stops in this feed for reference
        existing_stops_result = await db.execute(
            select(Stop.stop_id).where(Stop.feed_id == payload.feed_id)
        )
        for row in existing_stops_result.fetchall():
            valid_stop_ids.add(row[0])

        # Create new stops
        total_new_stops = len(payload.new_stops)
        for idx, stop_data in enumerate(payload.new_stops):
            progress = 10 + (15 * (idx + 1) / max(total_new_stops, 1))
            await update_progress(progress, f"Creating stop {idx + 1}/{total_new_stops}")

            # Skip if stop already exists (shouldn't happen after validation)
            if stop_data.stop_id in valid_stop_ids:
                warnings.append(f"Stop '{stop_data.stop_id}' already exists, skipping")
                continue

            stop = Stop(
                feed_id=payload.feed_id,
                stop_id=stop_data.stop_id,
                stop_name=stop_data.stop_name,
                stop_lat=stop_data.stop_lat,
                stop_lon=stop_data.stop_lon,
                stop_code=stop_data.stop_code,
                stop_desc=stop_data.stop_desc,
                wheelchair_boarding=stop_data.wheelchair_boarding,
                custom_fields=stop_data.custom_fields,
            )
            db.add(stop)
            await db.flush()
            valid_stop_ids.add(stop.stop_id)
            stops_created += 1

            # Stop uses composite key (feed_id, stop_id)
            audit_log = AuditLog(
                user_id=user_id,
                agency_id=agency_id,
                action=AuditAction.CREATE.value,
                entity_type="Stop",
                entity_id=f"{payload.feed_id}:{stop.stop_id}",
                new_values={"stop_id": stop.stop_id, "stop_name": stop.stop_name}
            )
            db.add(audit_log)

        await update_progress(25, f"{stops_created} stops created")

        # 3. Create shape points (25-45%)
        await update_progress(30, "Creating shape")

        shape_points_created = 0
        total_shape_points = len(payload.shape_points)

        # Sort shape points by sequence to ensure correct distance calculation
        sorted_shape_points = sorted(payload.shape_points, key=lambda p: p.sequence)

        # Calculate cumulative shape_dist_traveled if not provided
        cumulative_distance = Decimal("0")
        prev_lat: float | None = None
        prev_lon: float | None = None

        for idx, point in enumerate(sorted_shape_points):
            if idx % 50 == 0:  # Update progress every 50 points
                progress = 25 + (20 * (idx + 1) / max(total_shape_points, 1))
                await update_progress(progress, f"Creating shape point {idx + 1}/{total_shape_points}")

            # Calculate distance from previous point
            if prev_lat is not None and prev_lon is not None:
                segment_distance = haversine_distance(
                    prev_lat, prev_lon,
                    float(point.lat), float(point.lon)
                )
                cumulative_distance += Decimal(str(segment_distance))

            # Use provided dist_traveled if available, otherwise use calculated value
            dist_traveled = point.dist_traveled if point.dist_traveled is not None else cumulative_distance

            shape = Shape(
                feed_id=payload.feed_id,
                shape_id=payload.shape_id,
                shape_pt_lat=point.lat,
                shape_pt_lon=point.lon,
                shape_pt_sequence=point.sequence,
                shape_dist_traveled=dist_traveled,
            )
            db.add(shape)
            shape_points_created += 1

            # Store current point for next iteration
            prev_lat = float(point.lat)
            prev_lon = float(point.lon)

        await db.flush()

        # Shape uses composite key (feed_id, shape_id, shape_pt_sequence)
        audit_log = AuditLog(
            user_id=user_id,
            agency_id=agency_id,
            action=AuditAction.CREATE.value,
            entity_type="Shape",
            entity_id=f"{payload.feed_id}:{payload.shape_id}",
            new_values={"shape_id": payload.shape_id, "points": shape_points_created}
        )
        db.add(audit_log)

        await update_progress(45, f"Shape with {shape_points_created} points created")

        # 4. Create trips (45-80%)
        # For each trip pattern, create a trip for each service_id
        trips_created = 0
        # Map original trip_id + service_id -> unique_trip_id string
        trip_id_mapping: Dict[str, Dict[str, str]] = {}

        total_trips = len(payload.trips) * len(payload.service_ids)
        trip_counter = 0

        for trip_data in payload.trips:
            trip_id_mapping[trip_data.trip_id] = {}

            for service_id in payload.service_ids:
                trip_counter += 1
                progress = 45 + (35 * trip_counter / max(total_trips, 1))
                await update_progress(progress, f"Creating trip {trip_counter}/{total_trips}")

                # Generate unique trip_id for each service
                if len(payload.service_ids) > 1:
                    # Append service_id to make unique if multiple calendars
                    unique_trip_id = f"{trip_data.trip_id}_{service_id}"
                else:
                    unique_trip_id = trip_data.trip_id

                # Trip uses composite key (feed_id, trip_id)
                # route_id and shape_id are GTFS string IDs, not database integer IDs
                trip = Trip(
                    feed_id=payload.feed_id,
                    route_id=payload.route.route_id,  # GTFS route_id string
                    service_id=service_id,  # GTFS service_id string
                    trip_id=unique_trip_id,
                    trip_headsign=trip_data.trip_headsign,
                    direction_id=trip_data.direction_id,
                    shape_id=payload.shape_id,  # GTFS shape_id string
                    wheelchair_accessible=trip_data.wheelchair_accessible,
                    bikes_allowed=trip_data.bikes_allowed,
                    custom_fields=trip_data.custom_fields,
                )
                db.add(trip)
                trip_id_mapping[trip_data.trip_id][service_id] = unique_trip_id
                trips_created += 1

        await db.flush()

        audit_log = AuditLog(
            user_id=user_id,
            agency_id=agency_id,
            action=AuditAction.CREATE.value,
            entity_type="Trip",
            entity_id=f"{payload.feed_id}:{payload.route.route_id}",
            new_values={"route_id": payload.route.route_id, "trips_created": trips_created}
        )
        db.add(audit_log)

        await update_progress(80, f"{trips_created} trips created")

        # 5. Create stop_times (80-100%)
        stop_times_created = 0
        total_stop_times = len(payload.stop_times) * len(payload.service_ids)
        st_counter = 0

        for st_data in payload.stop_times:
            # Verify stop exists
            if st_data.stop_id not in valid_stop_ids:
                warnings.append(f"Could not find stop '{st_data.stop_id}', skipping stop_time")
                continue

            # Create stop_time for each trip instance (one per service_id)
            for service_id in payload.service_ids:
                st_counter += 1
                if st_counter % 50 == 0:  # Update every 50 stop_times
                    progress = 80 + (20 * st_counter / max(total_stop_times, 1))
                    await update_progress(progress, f"Creating stop_time {st_counter}/{total_stop_times}")

                # Get the unique trip_id for this service
                unique_trip_id = trip_id_mapping.get(st_data.trip_id, {}).get(service_id)
                if not unique_trip_id:
                    warnings.append(f"Could not find trip '{st_data.trip_id}' for service {service_id}")
                    continue

                # StopTime uses composite key (feed_id, trip_id, stop_sequence)
                # All IDs are GTFS string IDs
                stop_time = StopTime(
                    feed_id=payload.feed_id,
                    trip_id=unique_trip_id,  # GTFS trip_id string
                    stop_id=st_data.stop_id,  # GTFS stop_id string
                    stop_sequence=st_data.stop_sequence,
                    arrival_time=st_data.arrival_time,
                    departure_time=st_data.departure_time,
                    stop_headsign=st_data.stop_headsign,
                    pickup_type=st_data.pickup_type,
                    drop_off_type=st_data.drop_off_type,
                    shape_dist_traveled=st_data.shape_dist_traveled,
                    timepoint=st_data.timepoint,
                )
                db.add(stop_time)
                stop_times_created += 1

        await db.flush()

        # Update feed statistics
        feed.total_routes = (feed.total_routes or 0) + 1
        feed.total_stops = (feed.total_stops or 0) + stops_created
        feed.total_trips = (feed.total_trips or 0) + trips_created

        await update_progress(100, "Export completed successfully")

        return RouteExportResult(
            route_id=payload.route.route_id,
            feed_id=payload.feed_id,
            stops_created=stops_created,
            stops_linked=len(valid_stop_ids) - stops_created,
            shape_points_created=shape_points_created,
            trips_created=trips_created,
            stop_times_created=stop_times_created,
            warnings=warnings,
        )


# Singleton instance
route_export_service = RouteExportService()
