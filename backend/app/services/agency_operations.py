"""
Agency Operations Service

Provides functionality for merging and splitting agencies as specified in claude.md.
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.gtfs import Route, Stop, Trip, Calendar, Shape, GTFSFeed
from app.models.agency import Agency

logger = logging.getLogger(__name__)


class MergeValidationError(Exception):
    """Raised when merge validation fails"""
    pass


class SplitValidationError(Exception):
    """Raised when split validation fails"""
    pass


class AgencyOperations:
    """
    Service for agency merge and split operations

    Per claude.md requirements:
    - Merge agencies with validation of unique shape_ids, route_ids, trip_ids
    - Split agencies by selecting routes to move to a new agency
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def validate_merge(
        self,
        source_agency_id: int,
        target_agency_id: int,
        source_feed_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Validate if two agencies can be merged

        Per claude.md line 99-102:
        - validate unique shape_ids first
        - validate unique route_ids first
        - validate unique trip_ids first

        Args:
            source_agency_id: Agency to merge from
            target_agency_id: Agency to merge into
            source_feed_id: Optional specific feed to merge (default: all feeds)

        Returns:
            Dictionary with validation results and conflicts

        Raises:
            MergeValidationError: If validation fails
        """
        logger.info(f"Validating merge: agency {source_agency_id} -> {target_agency_id}")

        # Verify both agencies exist
        source_agency = await self.db.get(Agency, source_agency_id)
        target_agency = await self.db.get(Agency, target_agency_id)

        if not source_agency:
            raise MergeValidationError(f"Source agency {source_agency_id} not found")
        if not target_agency:
            raise MergeValidationError(f"Target agency {target_agency_id} not found")

        conflicts = {
            'route_ids': [],
            'shape_ids': [],
            'trip_ids': []
        }

        # Get feeds to check
        if source_feed_id:
            source_feeds = [source_feed_id]
        else:
            stmt = select(GTFSFeed.id).where(GTFSFeed.agency_id == source_agency_id)
            result = await self.db.execute(stmt)
            source_feeds = [row[0] for row in result.all()]

        # Get target feeds
        stmt = select(GTFSFeed.id).where(GTFSFeed.agency_id == target_agency_id)
        result = await self.db.execute(stmt)
        target_feeds = [row[0] for row in result.all()]

        # Validate unique route_ids
        logger.debug("Validating route_ids")
        source_route_stmt = select(Route.route_id).where(Route.feed_id.in_(source_feeds)).distinct()
        source_route_result = await self.db.execute(source_route_stmt)
        source_route_ids = set(row[0] for row in source_route_result.all())

        target_route_stmt = select(Route.route_id).where(Route.feed_id.in_(target_feeds)).distinct()
        target_route_result = await self.db.execute(target_route_stmt)
        target_route_ids = set(row[0] for row in target_route_result.all())

        route_conflicts = source_route_ids & target_route_ids
        if route_conflicts:
            conflicts['route_ids'] = list(route_conflicts)
            logger.warning(f"Found {len(route_conflicts)} conflicting route_ids")

        # Validate unique shape_ids
        logger.debug("Validating shape_ids")
        source_shape_stmt = select(Shape.shape_id).where(Shape.feed_id.in_(source_feeds)).distinct()
        source_shape_result = await self.db.execute(source_shape_stmt)
        source_shape_ids = set(row[0] for row in source_shape_result.all())

        target_shape_stmt = select(Shape.shape_id).where(Shape.feed_id.in_(target_feeds)).distinct()
        target_shape_result = await self.db.execute(target_shape_stmt)
        target_shape_ids = set(row[0] for row in target_shape_result.all())

        shape_conflicts = source_shape_ids & target_shape_ids
        if shape_conflicts:
            conflicts['shape_ids'] = list(shape_conflicts)
            logger.warning(f"Found {len(shape_conflicts)} conflicting shape_ids")

        # Validate unique trip_ids
        logger.debug("Validating trip_ids")
        source_trip_stmt = select(Trip.trip_id).where(Trip.feed_id.in_(source_feeds)).distinct()
        source_trip_result = await self.db.execute(source_trip_stmt)
        source_trip_ids = set(row[0] for row in source_trip_result.all())

        target_trip_stmt = select(Trip.trip_id).where(Trip.feed_id.in_(target_feeds)).distinct()
        target_trip_result = await self.db.execute(target_trip_stmt)
        target_trip_ids = set(row[0] for row in target_trip_result.all())

        trip_conflicts = source_trip_ids & target_trip_ids
        if trip_conflicts:
            conflicts['trip_ids'] = list(trip_conflicts)
            logger.warning(f"Found {len(trip_conflicts)} conflicting trip_ids")

        has_conflicts = any(len(v) > 0 for v in conflicts.values())

        result = {
            'valid': not has_conflicts,
            'conflicts': conflicts,
            'source_agency': {
                'id': source_agency_id,
                'name': source_agency.name,
                'feeds': len(source_feeds)
            },
            'target_agency': {
                'id': target_agency_id,
                'name': target_agency.name,
                'feeds': len(target_feeds)
            }
        }

        if has_conflicts:
            total_conflicts = sum(len(v) for v in conflicts.values())
            result['message'] = f"Found {total_conflicts} conflicts. Resolve conflicts before merging."
        else:
            result['message'] = "Validation passed. Agencies can be merged."

        return result

    async def merge_agencies(
        self,
        source_agency_id: int,
        target_agency_id: int,
        source_feed_id: Optional[int] = None,
        skip_validation: bool = False
    ) -> Dict[str, Any]:
        """
        Merge one agency into another

        Args:
            source_agency_id: Agency to merge from
            target_agency_id: Agency to merge into
            source_feed_id: Optional specific feed to merge (default: all feeds)
            skip_validation: Skip validation (use with caution)

        Returns:
            Dictionary with merge results

        Raises:
            MergeValidationError: If validation fails
        """
        logger.info(f"Merging agency {source_agency_id} into {target_agency_id}")

        # Validate merge unless skipped
        if not skip_validation:
            validation = await self.validate_merge(source_agency_id, target_agency_id, source_feed_id)
            if not validation['valid']:
                raise MergeValidationError(f"Merge validation failed: {validation['message']}")

        # Get feeds to merge
        if source_feed_id:
            stmt = select(GTFSFeed).where(GTFSFeed.id == source_feed_id)
            result = await self.db.execute(stmt)
            feeds_to_merge = result.scalars().all()
        else:
            stmt = select(GTFSFeed).where(GTFSFeed.agency_id == source_agency_id)
            result = await self.db.execute(stmt)
            feeds_to_merge = result.scalars().all()

        merged_feeds = 0
        for feed in feeds_to_merge:
            # Update feed to point to target agency
            feed.agency_id = target_agency_id
            merged_feeds += 1

        await self.db.commit()

        logger.info(f"Successfully merged {merged_feeds} feeds from agency {source_agency_id} to {target_agency_id}")

        return {
            'success': True,
            'merged_feeds': merged_feeds,
            'source_agency_id': source_agency_id,
            'target_agency_id': target_agency_id
        }

    async def validate_split(
        self,
        source_agency_id: int,
        route_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Validate if routes can be split from an agency

        Args:
            source_agency_id: Agency to split from
            route_ids: List of route_ids to move to new agency

        Returns:
            Dictionary with validation results

        Raises:
            SplitValidationError: If validation fails
        """
        logger.info(f"Validating split of {len(route_ids)} routes from agency {source_agency_id}")

        # Verify agency exists
        source_agency = await self.db.get(Agency, source_agency_id)
        if not source_agency:
            raise SplitValidationError(f"Source agency {source_agency_id} not found")

        # Get all feeds for this agency
        stmt = select(GTFSFeed.id).where(GTFSFeed.agency_id == source_agency_id)
        result = await self.db.execute(stmt)
        agency_feeds = [row[0] for row in result.all()]

        if not agency_feeds:
            raise SplitValidationError(f"Agency {source_agency_id} has no feeds")

        # Verify all route_ids exist
        stmt = select(Route.route_id, Route.route_short_name, Route.feed_id).where(
            Route.feed_id.in_(agency_feeds),
            Route.route_id.in_(route_ids)
        )
        result = await self.db.execute(stmt)
        found_routes = result.all()

        found_route_ids = set(row[0] for row in found_routes)
        missing_route_ids = set(route_ids) - found_route_ids

        if missing_route_ids:
            raise SplitValidationError(
                f"Route IDs not found in agency: {', '.join(missing_route_ids)}"
            )

        # Count trips that would be moved
        stmt = select(Trip.trip_id).join(Route).where(
            Trip.feed_id.in_(agency_feeds),
            Route.route_id.in_(route_ids)
        )
        result = await self.db.execute(stmt)
        trips_to_move = len(result.all())

        return {
            'valid': True,
            'source_agency': {
                'id': source_agency_id,
                'name': source_agency.name,
                'feeds': len(agency_feeds)
            },
            'routes_to_move': len(found_routes),
            'trips_to_move': trips_to_move,
            'message': f"Can split {len(found_routes)} routes with {trips_to_move} trips"
        }

    async def split_agency(
        self,
        source_agency_id: int,
        new_agency_name: str,
        new_agency_slug: str,
        route_ids: List[str],
        skip_validation: bool = False
    ) -> Dict[str, Any]:
        """
        Split routes from an agency into a new agency

        Per claude.md line 104-105:
        - allow to select multiple routes to split in a new agency

        Args:
            source_agency_id: Agency to split from
            new_agency_name: Name for the new agency
            new_agency_slug: Slug for the new agency
            route_ids: List of route_ids to move to new agency
            skip_validation: Skip validation (use with caution)

        Returns:
            Dictionary with split results

        Raises:
            SplitValidationError: If validation fails
        """
        logger.info(f"Splitting {len(route_ids)} routes from agency {source_agency_id} to new agency '{new_agency_name}'")

        # Validate split unless skipped
        if not skip_validation:
            validation = await self.validate_split(source_agency_id, route_ids)
            if not validation['valid']:
                raise SplitValidationError(f"Split validation failed: {validation['message']}")

        # Create new agency
        new_agency = Agency(
            name=new_agency_name,
            slug=new_agency_slug,
            is_active=True
        )
        self.db.add(new_agency)
        await self.db.flush()  # Get new_agency.id

        logger.info(f"Created new agency {new_agency.id}: {new_agency_name}")

        # Get all feeds from source agency
        stmt = select(GTFSFeed).where(GTFSFeed.agency_id == source_agency_id)
        result = await self.db.execute(stmt)
        source_feeds = result.scalars().all()

        # Create new feed for each source feed (to maintain feed structure)
        new_feeds = []
        for source_feed in source_feeds:
            new_feed = GTFSFeed(
                agency_id=new_agency.id,
                name=f"{source_feed.name} (Split)",
                description=f"Split from {source_agency_id}",
                version=source_feed.version,
                is_active=source_feed.is_active
            )
            self.db.add(new_feed)
            await self.db.flush()
            new_feeds.append((source_feed.id, new_feed.id))

        feed_mapping = dict(new_feeds)

        # Move routes to new feeds
        moved_routes = 0
        for source_feed_id, new_feed_id in new_feeds:
            stmt = update(Route).where(
                Route.feed_id == source_feed_id,
                Route.route_id.in_(route_ids)
            ).values(feed_id=new_feed_id)
            result = await self.db.execute(stmt)
            moved_routes += result.rowcount

        # Move trips associated with moved routes
        # First get the trip IDs grouped by source feed
        stmt = select(Trip.trip_id, Trip.feed_id).join(Route).where(
            Trip.feed_id == Route.feed_id,
            Route.route_id.in_(route_ids)
        )
        result = await self.db.execute(stmt)
        trip_ids_by_feed: dict[int, list[str]] = {}
        for trip_id, trip_feed_id in result.all():
            trip_ids_by_feed.setdefault(trip_feed_id, []).append(trip_id)

        # Update trips to new feeds
        moved_trips = 0
        for source_feed_id, new_feed_id in new_feeds:
            trip_ids_to_move = trip_ids_by_feed.get(source_feed_id, [])
            if not trip_ids_to_move:
                continue
            stmt = update(Trip).where(
                Trip.feed_id == source_feed_id,
                Trip.trip_id.in_(trip_ids_to_move)
            ).values(feed_id=new_feed_id)
            result = await self.db.execute(stmt)
            moved_trips += result.rowcount

        await self.db.commit()

        logger.info(
            f"Successfully split {moved_routes} routes and {moved_trips} trips "
            f"from agency {source_agency_id} to new agency {new_agency.id}"
        )

        return {
            'success': True,
            'new_agency': {
                'id': new_agency.id,
                'name': new_agency.name,
                'slug': new_agency.slug
            },
            'moved_routes': moved_routes,
            'moved_trips': moved_trips,
            'new_feeds': len(new_feeds),
            'source_agency_id': source_agency_id
        }
