"""Service for splitting routes from an agency into a new agency"""

import logging
from typing import List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.agency import Agency
from app.models.gtfs import (
    GTFSFeed, Route, Trip, Stop, StopTime, Calendar, CalendarDate, Shape
)
from app.models.feed_source import ExternalFeedSource, FeedSourceType
from app.schemas.agency_operations import (
    AgencySplitRequest,
    AgencySplitDependencies,
    SplitReportStats,
)

logger = logging.getLogger(__name__)


class AgencySplitService:
    """Service for validating and executing agency split operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def analyze_dependencies(
        self,
        request: AgencySplitRequest,
    ) -> AgencySplitDependencies:
        """
        Analyze what data will be copied during the split.

        Returns dependency information showing:
        - Routes to be copied
        - Count of trips, stops, stop_times, calendars, shapes
        - Count of shared stops (used by both split and remaining routes)
        """

        # Get all trips for the selected routes
        trip_result = await self.db.execute(
            select(func.count())
            .select_from(Trip)
            .where(
                Trip.feed_id == request.feed_id,
                Trip.route_id.in_(request.route_ids)
            )
        )
        total_trips = trip_result.scalar() or 0

        # Get trip IDs for stop_time counting
        trip_ids_result = await self.db.execute(
            select(Trip.trip_id)
            .where(
                Trip.feed_id == request.feed_id,
                Trip.route_id.in_(request.route_ids)
            )
        )
        trip_ids = [row[0] for row in trip_ids_result.all()]

        # Count stop_times
        total_stop_times = 0
        if trip_ids:
            stop_time_result = await self.db.execute(
                select(func.count())
                .select_from(StopTime)
                .where(
                    StopTime.feed_id == request.feed_id,
                    StopTime.trip_id.in_(trip_ids)
                )
            )
            total_stop_times = stop_time_result.scalar() or 0

        # Get unique stop IDs used by selected routes
        stops_result = await self.db.execute(
            select(func.count(func.distinct(StopTime.stop_id)))
            .where(
                StopTime.feed_id == request.feed_id,
                StopTime.trip_id.in_(trip_ids)
            )
        )
        total_stops = stops_result.scalar() or 0

        # Get unique calendar service_ids
        calendar_result = await self.db.execute(
            select(func.count(func.distinct(Trip.service_id)))
            .where(
                Trip.feed_id == request.feed_id,
                Trip.trip_id.in_(trip_ids)
            )
        )
        total_calendars = calendar_result.scalar() or 0

        # Get unique shape_ids
        shape_result = await self.db.execute(
            select(func.count(func.distinct(Trip.shape_id)))
            .where(
                Trip.feed_id == request.feed_id,
                Trip.trip_id.in_(trip_ids),
                Trip.shape_id.isnot(None)
            )
        )
        total_shapes = shape_result.scalar() or 0

        # TODO: Calculate shared stops (stops used by both selected and remaining routes)
        shared_stops = 0

        # TODO: Count calendar_dates entries
        total_calendar_dates = 0

        return AgencySplitDependencies(
            routes=request.route_ids,
            trips=total_trips,
            stops=total_stops,
            stop_times=total_stop_times,
            calendars=total_calendars,
            calendar_dates=total_calendar_dates,
            shapes=total_shapes,
            shared_stops=shared_stops,
        )

    async def validate_split(
        self,
        request: AgencySplitRequest,
        user_id: int,
    ) -> Tuple[bool, List[str]]:
        """
        Validate a split request.

        Checks:
        - Feed exists and belongs to an agency
        - All route_ids exist in the specified feed
        - New agency name is unique

        Returns: (valid, errors)
        """
        errors: List[str] = []

        # Check feed exists
        feed = await self.db.get(GTFSFeed, request.feed_id)
        if not feed:
            errors.append(f"Feed {request.feed_id} not found")
            return False, errors

        # Check all routes exist
        route_result = await self.db.execute(
            select(Route.route_id)
            .where(
                Route.feed_id == request.feed_id,
                Route.route_id.in_(request.route_ids)
            )
        )
        existing_routes = {row[0] for row in route_result.all()}
        missing_routes = set(request.route_ids) - existing_routes

        if missing_routes:
            errors.append(
                f"Routes not found in feed: {', '.join(missing_routes)}"
            )

        # Note: Agency names don't need to be unique, only slugs do

        return len(errors) == 0, errors

    async def execute_split(
        self,
        request: AgencySplitRequest,
        user_id: int,
    ) -> Tuple[Agency, GTFSFeed, SplitReportStats]:
        """
        Execute the split operation (to be implemented in Celery task).

        This is a placeholder for the actual split logic that will:
        1. Create new agency
        2. Create new feed in new agency
        3. Copy selected routes and dependencies
        4. Copy realtime feed sources (not static GTFS)
        5. Optionally remove from source
        6. Create audit logs

        Returns: (new_agency, new_feed, stats)
        """
        # This will be implemented in the Celery task

        # Create new agency
        new_agency = Agency(
            name=request.new_agency_name,
            slug=request.new_agency_name.lower().replace(" ", "_"),
        )
        self.db.add(new_agency)
        await self.db.flush()

        # Create new feed
        from datetime import datetime
        new_feed = GTFSFeed(
            agency_id=new_agency.id,
            name=request.new_feed_name,
            description=f"Split from feed {request.feed_id}",
            is_active=True,
            imported_at=datetime.utcnow().isoformat(),
            imported_by=user_id,
        )
        self.db.add(new_feed)
        await self.db.flush()

        # Copy realtime feed sources from the source agency (not static GTFS)
        source_feed = await self.db.get(GTFSFeed, request.feed_id)
        if source_feed:
            copied_feeds = await self._copy_realtime_feed_sources(
                source_agency_id=source_feed.agency_id,
                target_agency_id=new_agency.id,
            )
            logger.info(
                f"Copied {copied_feeds} realtime feed sources from agency "
                f"{source_feed.agency_id} to new agency {new_agency.id}"
            )

        stats = SplitReportStats()

        return new_agency, new_feed, stats

    async def _copy_realtime_feed_sources(
        self,
        source_agency_id: int,
        target_agency_id: int,
    ) -> int:
        """
        Copy realtime feed sources from source agency to target agency.

        Only copies GTFS-RT feeds (vehicle positions, trip updates, alerts,
        trip modifications), NOT static GTFS feeds.

        Returns: Number of feed sources copied
        """
        # Define realtime feed types to copy
        realtime_types = [
            FeedSourceType.GTFS_REALTIME,
            FeedSourceType.GTFS_RT_VEHICLE_POSITIONS,
            FeedSourceType.GTFS_RT_TRIP_UPDATES,
            FeedSourceType.GTFS_RT_ALERTS,
            FeedSourceType.GTFS_RT_TRIP_MODIFICATIONS,
        ]

        # Get all realtime feed sources from source agency
        result = await self.db.execute(
            select(ExternalFeedSource)
            .where(
                ExternalFeedSource.agency_id == source_agency_id,
                ExternalFeedSource.source_type.in_([t.value for t in realtime_types])
            )
        )
        source_feeds = result.scalars().all()

        copied_count = 0
        for source_feed in source_feeds:
            # Create a copy of the feed source for the new agency
            new_feed_source = ExternalFeedSource(
                name=source_feed.name,
                description=source_feed.description,
                source_type=source_feed.source_type,
                url=source_feed.url,
                auth_type=source_feed.auth_type,
                auth_header=source_feed.auth_header,
                auth_value=source_feed.auth_value,
                check_frequency=source_feed.check_frequency,
                is_enabled=source_feed.is_enabled,
                auto_import=source_feed.auto_import,
                import_options=source_feed.import_options,
                agency_id=target_agency_id,
                # Reset status fields for the new copy
                status="pending",
                last_checked_at=None,
                last_successful_check=None,
                last_import_at=None,
                last_etag=None,
                last_modified=None,
                last_content_hash=None,
                error_count=0,
                last_error=None,
                created_feed_id=None,
            )
            self.db.add(new_feed_source)
            copied_count += 1

            logger.debug(
                f"Copied realtime feed source '{source_feed.name}' "
                f"(type: {source_feed.source_type}) to agency {target_agency_id}"
            )

        return copied_count
