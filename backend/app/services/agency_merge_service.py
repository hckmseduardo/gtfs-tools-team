"""Service for merging multiple agencies into one"""

import logging
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.agency import Agency
from app.models.gtfs import (
    GTFSFeed, Route, Trip, Stop, StopTime, Calendar, CalendarDate, Shape, FareAttribute, FareRule
)
from app.schemas.agency_operations import (
    AgencyMergeRequest,
    AgencyMergeValidationResult,
    IDConflict,
    MergeReportStats,
    FeedEntityCounts,
)

logger = logging.getLogger(__name__)


class AgencyMergeService:
    """Service for validating and executing agency merge operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_feed_entity_counts(self, feed_ids: List[int]) -> List[FeedEntityCounts]:
        """
        Get entity counts for each feed.

        Returns a list of FeedEntityCounts with counts for all entity types.
        """
        feed_counts_list = []

        for feed_id in feed_ids:
            # Get feed info
            feed = await self.db.get(GTFSFeed, feed_id)
            if not feed:
                continue

            # Get agency info
            agency = await self.db.get(Agency, feed.agency_id)
            if not agency:
                continue

            # Count routes
            routes_result = await self.db.execute(
                select(func.count()).select_from(Route).where(Route.feed_id == feed_id)
            )
            routes_count = routes_result.scalar() or 0

            # Count trips
            trips_result = await self.db.execute(
                select(func.count()).select_from(Trip).where(Trip.feed_id == feed_id)
            )
            trips_count = trips_result.scalar() or 0

            # Count stops
            stops_result = await self.db.execute(
                select(func.count()).select_from(Stop).where(Stop.feed_id == feed_id)
            )
            stops_count = stops_result.scalar() or 0

            # Count stop times
            stop_times_result = await self.db.execute(
                select(func.count()).select_from(StopTime).where(StopTime.feed_id == feed_id)
            )
            stop_times_count = stop_times_result.scalar() or 0

            # Count unique shapes
            shapes_result = await self.db.execute(
                select(func.count(func.distinct(Shape.shape_id)))
                .where(Shape.feed_id == feed_id)
            )
            shapes_count = shapes_result.scalar() or 0

            # Count calendars
            calendars_result = await self.db.execute(
                select(func.count()).select_from(Calendar).where(Calendar.feed_id == feed_id)
            )
            calendars_count = calendars_result.scalar() or 0

            # Count calendar dates
            calendar_dates_result = await self.db.execute(
                select(func.count()).select_from(CalendarDate).where(CalendarDate.feed_id == feed_id)
            )
            calendar_dates_count = calendar_dates_result.scalar() or 0

            # Count fare attributes
            fare_attributes_result = await self.db.execute(
                select(func.count()).select_from(FareAttribute).where(FareAttribute.feed_id == feed_id)
            )
            fare_attributes_count = fare_attributes_result.scalar() or 0

            # Count fare rules
            fare_rules_result = await self.db.execute(
                select(func.count()).select_from(FareRule).where(FareRule.feed_id == feed_id)
            )
            fare_rules_count = fare_rules_result.scalar() or 0

            feed_counts_list.append(FeedEntityCounts(
                feed_id=feed.id,
                feed_name=feed.name,
                agency_id=agency.id,
                agency_name=agency.name,
                routes=routes_count,
                trips=trips_count,
                stops=stops_count,
                stop_times=stop_times_count,
                shapes=shapes_count,
                calendars=calendars_count,
                calendar_dates=calendar_dates_count,
                fare_attributes=fare_attributes_count,
                fare_rules=fare_rules_count,
            ))

        return feed_counts_list

    async def validate_merge(
        self,
        request: AgencyMergeRequest,
        user_id: int,
    ) -> AgencyMergeValidationResult:
        """
        Validate a merge request and detect ID conflicts.

        Phase 1: Validation
        - Check that all feeds exist
        - Check user has access to target agency (or validate new agency creation)
        - Detect ID conflicts (route_id, trip_id, shape_id, stop_id)

        Returns validation result with conflicts if any.
        """
        errors: List[str] = []
        warnings: List[str] = []
        conflicts: List[IDConflict] = []

        # Validate feeds exist and collect feed -> agency mapping
        source_feed_ids = request.source_feed_ids
        feed_to_agency: Dict[int, int] = {}

        for feed_id in source_feed_ids:
            feed = await self.db.get(GTFSFeed, feed_id)
            if not feed:
                errors.append(f"Source feed {feed_id} not found")
            else:
                feed_to_agency[feed_id] = feed.agency_id

        # Validate target: either existing agency or new agency creation
        target_agency = None
        if request.create_new_agency:
            # Validate new agency fields
            if not request.new_agency_name or not request.new_agency_name.strip():
                errors.append("New agency name is required when creating a new agency")
            # Note: Agency names don't need to be unique, only slugs do
        else:
            # Validate existing target agency
            if not request.target_agency_id:
                errors.append("Target agency ID is required when not creating a new agency")
            else:
                target_agency = await self.db.get(Agency, request.target_agency_id)
                if not target_agency:
                    errors.append(f"Target agency {request.target_agency_id} not found")

        # If basic validation failed, return early
        if errors:
            return AgencyMergeValidationResult(
                valid=False,
                errors=errors,
                warnings=warnings,
                conflicts=conflicts,
            )

        if not source_feed_ids:
            errors.append("No feeds selected for merge")
            return AgencyMergeValidationResult(
                valid=False,
                errors=errors,
                warnings=warnings,
                conflicts=conflicts,
            )

        # Check for ID conflicts
        route_conflicts = await self._check_route_id_conflicts(source_feed_ids, feed_to_agency)
        trip_conflicts = await self._check_trip_id_conflicts(source_feed_ids, feed_to_agency)
        shape_conflicts = await self._check_shape_id_conflicts(source_feed_ids, feed_to_agency)
        stop_conflicts = await self._check_stop_id_conflicts(source_feed_ids, feed_to_agency)
        service_conflicts = await self._check_service_id_conflicts(source_feed_ids, feed_to_agency)
        fare_conflicts = await self._check_fare_id_conflicts(source_feed_ids, feed_to_agency)

        conflicts.extend(route_conflicts)
        conflicts.extend(trip_conflicts)
        conflicts.extend(shape_conflicts)
        conflicts.extend(stop_conflicts)
        conflicts.extend(service_conflicts)
        conflicts.extend(fare_conflicts)

        # Get per-feed entity counts
        feed_counts = await self.get_feed_entity_counts(source_feed_ids)

        # Calculate expected totals
        total_routes = sum(fc.routes for fc in feed_counts)
        total_trips = sum(fc.trips for fc in feed_counts)
        total_stops = sum(fc.stops for fc in feed_counts)
        total_stop_times = sum(fc.stop_times for fc in feed_counts)
        total_shapes = sum(fc.shapes for fc in feed_counts)
        total_calendars = sum(fc.calendars for fc in feed_counts)
        total_calendar_dates = sum(fc.calendar_dates for fc in feed_counts)
        total_fare_attributes = sum(fc.fare_attributes for fc in feed_counts)
        total_fare_rules = sum(fc.fare_rules for fc in feed_counts)

        # Determine if valid based on merge strategy
        valid = True
        if request.merge_strategy == "fail_on_conflict" and conflicts:
            valid = False
            errors.append(
                f"Found {len(conflicts)} ID conflicts. "
                "Resolve conflicts or use 'auto_prefix' strategy."
            )

        if conflicts and request.merge_strategy == "auto_prefix":
            warnings.append(
                f"Found {len(conflicts)} ID conflicts. "
                "IDs will be automatically prefixed with feed ID."
            )

        return AgencyMergeValidationResult(
            valid=valid,
            conflicts=conflicts,
            feed_counts=feed_counts,
            total_routes=total_routes,
            total_trips=total_trips,
            total_stops=total_stops,
            total_stop_times=total_stop_times,
            total_shapes=total_shapes,
            total_calendars=total_calendars,
            total_calendar_dates=total_calendar_dates,
            total_fare_attributes=total_fare_attributes,
            total_fare_rules=total_fare_rules,
            warnings=warnings,
            errors=errors,
        )

    async def _check_route_id_conflicts(self, feed_ids: List[int], feed_to_agency: Dict[int, int]) -> List[IDConflict]:
        """Check for duplicate route_ids across feeds"""
        conflicts = []

        # Get all route_ids grouped by feed
        result = await self.db.execute(
            select(Route.route_id, Route.feed_id, func.count().label('count'))
            .where(Route.feed_id.in_(feed_ids))
            .group_by(Route.route_id, Route.feed_id)
        )
        route_data = result.all()

        # Group by route_id to find duplicates across different agencies
        route_groups: Dict[str, Set[int]] = defaultdict(set)
        for route_id, feed_id, _ in route_data:
            agency_id = feed_to_agency.get(feed_id, feed_id)
            route_groups[route_id].add(agency_id)

        # Find route_ids that appear in multiple agencies
        for route_id, agency_ids in route_groups.items():
            if len(agency_ids) > 1:
                conflicts.append(IDConflict(
                    entity_type="route",
                    conflicting_id=route_id,
                    source_agencies=list(agency_ids),
                    count=len(agency_ids)
                ))

        return conflicts

    async def _check_trip_id_conflicts(self, feed_ids: List[int], feed_to_agency: Dict[int, int]) -> List[IDConflict]:
        """Check for duplicate trip_ids across feeds"""
        conflicts = []

        result = await self.db.execute(
            select(Trip.trip_id, Trip.feed_id, func.count().label('count'))
            .where(Trip.feed_id.in_(feed_ids))
            .group_by(Trip.trip_id, Trip.feed_id)
        )
        trip_data = result.all()

        trip_groups: Dict[str, Set[int]] = defaultdict(set)
        for trip_id, feed_id, _ in trip_data:
            agency_id = feed_to_agency.get(feed_id, feed_id)
            trip_groups[trip_id].add(agency_id)

        for trip_id, agency_ids in trip_groups.items():
            if len(agency_ids) > 1:
                conflicts.append(IDConflict(
                    entity_type="trip",
                    conflicting_id=trip_id,
                    source_agencies=list(agency_ids),
                    count=len(agency_ids)
                ))

        return conflicts

    async def _check_shape_id_conflicts(self, feed_ids: List[int], feed_to_agency: Dict[int, int]) -> List[IDConflict]:
        """Check for duplicate shape_ids across feeds"""
        conflicts = []

        result = await self.db.execute(
            select(Shape.shape_id, Shape.feed_id)
            .where(Shape.feed_id.in_(feed_ids))
            .distinct()
        )
        shape_data = result.all()

        shape_groups: Dict[str, Set[int]] = defaultdict(set)
        for shape_id, feed_id in shape_data:
            agency_id = feed_to_agency.get(feed_id, feed_id)
            shape_groups[shape_id].add(agency_id)

        for shape_id, agency_ids in shape_groups.items():
            if len(agency_ids) > 1:
                conflicts.append(IDConflict(
                    entity_type="shape",
                    conflicting_id=shape_id,
                    source_agencies=list(agency_ids),
                    count=len(agency_ids)
                ))

        return conflicts

    async def _check_stop_id_conflicts(self, feed_ids: List[int], feed_to_agency: Dict[int, int]) -> List[IDConflict]:
        """Check for duplicate stop_ids across feeds"""
        conflicts = []

        result = await self.db.execute(
            select(Stop.stop_id, Stop.feed_id, func.count().label('count'))
            .where(Stop.feed_id.in_(feed_ids))
            .group_by(Stop.stop_id, Stop.feed_id)
        )
        stop_data = result.all()

        stop_groups: Dict[str, Set[int]] = defaultdict(set)
        for stop_id, feed_id, _ in stop_data:
            agency_id = feed_to_agency.get(feed_id, feed_id)
            stop_groups[stop_id].add(agency_id)

        for stop_id, agency_ids in stop_groups.items():
            if len(agency_ids) > 1:
                conflicts.append(IDConflict(
                    entity_type="stop",
                    conflicting_id=stop_id,
                    source_agencies=list(agency_ids),
                    count=len(agency_ids)
                ))

        return conflicts

    async def _check_service_id_conflicts(self, feed_ids: List[int], feed_to_agency: Dict[int, int]) -> List[IDConflict]:
        """Check for duplicate service_ids (calendars) across feeds"""
        conflicts = []

        result = await self.db.execute(
            select(Calendar.service_id, Calendar.feed_id)
            .where(Calendar.feed_id.in_(feed_ids))
        )
        calendar_data = result.all()

        service_groups: Dict[str, Set[int]] = defaultdict(set)
        for service_id, feed_id in calendar_data:
            agency_id = feed_to_agency.get(feed_id, feed_id)
            service_groups[service_id].add(agency_id)

        for service_id, agency_ids in service_groups.items():
            if len(agency_ids) > 1:
                conflicts.append(IDConflict(
                    entity_type="calendar",
                    conflicting_id=service_id,
                    source_agencies=list(agency_ids),
                    count=len(agency_ids)
                ))

        return conflicts

    async def _check_fare_id_conflicts(self, feed_ids: List[int], feed_to_agency: Dict[int, int]) -> List[IDConflict]:
        """Check for duplicate fare_ids across feeds"""
        conflicts = []

        result = await self.db.execute(
            select(FareAttribute.fare_id, FareAttribute.feed_id)
            .where(FareAttribute.feed_id.in_(feed_ids))
        )
        fare_data = result.all()

        fare_groups: Dict[str, Set[int]] = defaultdict(set)
        for fare_id, feed_id in fare_data:
            agency_id = feed_to_agency.get(feed_id, feed_id)
            fare_groups[fare_id].add(agency_id)

        for fare_id, agency_ids in fare_groups.items():
            if len(agency_ids) > 1:
                conflicts.append(IDConflict(
                    entity_type="fare",
                    conflicting_id=fare_id,
                    source_agencies=list(agency_ids),
                    count=len(agency_ids)
                ))

        return conflicts

    async def _get_merge_totals(self, feed_ids: List[int]) -> Dict[str, int]:
        """Get total counts of entities to be merged"""

        # Count routes
        route_result = await self.db.execute(
            select(func.count()).select_from(Route).where(Route.feed_id.in_(feed_ids))
        )
        total_routes = route_result.scalar() or 0

        # Count trips
        trip_result = await self.db.execute(
            select(func.count()).select_from(Trip).where(Trip.feed_id.in_(feed_ids))
        )
        total_trips = trip_result.scalar() or 0

        # Count stops
        stop_result = await self.db.execute(
            select(func.count()).select_from(Stop).where(Stop.feed_id.in_(feed_ids))
        )
        total_stops = stop_result.scalar() or 0

        # Count shapes (count distinct shape_ids)
        shape_result = await self.db.execute(
            select(func.count(func.distinct(Shape.shape_id))).where(Shape.feed_id.in_(feed_ids))
        )
        total_shapes = shape_result.scalar() or 0

        return {
            "routes": total_routes,
            "trips": total_trips,
            "stops": total_stops,
            "shapes": total_shapes,
        }

    async def execute_merge(
        self,
        request: AgencyMergeRequest,
        user_id: int,
    ) -> Tuple[GTFSFeed, MergeReportStats]:
        """
        Execute the merge operation (to be implemented in Celery task).

        This is a placeholder for the actual merge logic that will:
        1. Create new feed in target agency
        2. Copy and remap all GTFS entities
        3. Handle ID conflicts based on strategy
        4. Create audit logs

        Returns: (new_feed, stats)
        """
        # This will be implemented in the Celery task
        # For now, just create the feed structure

        target_agency = await self.db.get(Agency, request.target_agency_id)

        # Create new merged feed
        new_feed = GTFSFeed(
            agency_id=target_agency.id,
            name=request.feed_name,
            description=request.feed_description or f"Merged from agencies: {request.source_agency_ids}",
            is_active=request.activate_on_success,
        )
        self.db.add(new_feed)
        await self.db.flush()

        stats = MergeReportStats()

        return new_feed, stats
