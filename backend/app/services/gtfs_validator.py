"""
GTFS Validation Service

Implements comprehensive GTFS validation rules as specified in project requirements.
Validates data integrity, relationships, and compliance with GTFS specification.
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.gtfs import (
    Route, Stop, Trip, Calendar, Shape, GTFSFeed,
    CalendarDate, StopTime, FareAttribute, FeedInfo
)
from app.models.agency import Agency
from app.models.validation import AgencyValidationPreferences

logger = logging.getLogger(__name__)


class ValidationIssue:
    """Represents a single validation issue"""

    def __init__(
        self,
        severity: str,  # 'error', 'warning', 'info'
        category: str,  # 'routes', 'shapes', 'stops', etc.
        message: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.severity = severity
        self.category = category
        self.message = message
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.field = field
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            'severity': self.severity,
            'category': self.category,
            'message': self.message,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'field': self.field,
            'details': self.details
        }


class ValidationResult:
    """Container for validation results"""

    def __init__(self):
        self.issues: List[ValidationIssue] = []
        self.error_count = 0
        self.warning_count = 0
        self.info_count = 0

    def add_issue(self, issue: ValidationIssue):
        """Add a validation issue"""
        self.issues.append(issue)

        if issue.severity == 'error':
            self.error_count += 1
        elif issue.severity == 'warning':
            self.warning_count += 1
        elif issue.severity == 'info':
            self.info_count += 1

    def add_error(self, category: str, message: str, **kwargs):
        """Convenience method to add an error"""
        self.add_issue(ValidationIssue('error', category, message, **kwargs))

    def add_warning(self, category: str, message: str, **kwargs):
        """Convenience method to add a warning"""
        self.add_issue(ValidationIssue('warning', category, message, **kwargs))

    def add_info(self, category: str, message: str, **kwargs):
        """Convenience method to add an info"""
        self.add_issue(ValidationIssue('info', category, message, **kwargs))

    def is_valid(self) -> bool:
        """Check if validation passed (no errors)"""
        return self.error_count == 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            'valid': self.is_valid(),
            'error_count': self.error_count,
            'warning_count': self.warning_count,
            'info_count': self.info_count,
            'issues': [issue.to_dict() for issue in self.issues],
            'summary': self._generate_summary()
        }

    def _generate_summary(self) -> str:
        """Generate human-readable summary"""
        if self.is_valid():
            if self.warning_count == 0:
                return "Validation passed with no issues"
            return f"Validation passed with {self.warning_count} warning(s)"
        return f"Validation failed with {self.error_count} error(s) and {self.warning_count} warning(s)"


class GTFSValidator:
    """
    Enhanced GTFS validation rules

    Implements validation rules specified in claude.md:
    - Routes: valid agency, duplicated route_id, mandatory fields
    - Shapes: shape_dist_traveled, shape_pt_sequence, mandatory fields
    """

    # GTFS mandatory fields per specification
    # Note: Only checking actual string/value fields in models, not integer FK relationships
    # Relationships are validated separately (e.g., trip.route, trip.service)
    ROUTE_MANDATORY_FIELDS = ['route_id', 'route_short_name', 'route_type']
    SHAPE_MANDATORY_FIELDS = ['shape_id', 'shape_pt_lat', 'shape_pt_lon', 'shape_pt_sequence']
    CALENDAR_MANDATORY_FIELDS = ['service_id', 'start_date', 'end_date']
    CALENDAR_DATE_MANDATORY_FIELDS = ['date', 'exception_type']  # service_id is FK
    STOP_MANDATORY_FIELDS = ['stop_id', 'stop_name']
    TRIP_MANDATORY_FIELDS = ['trip_id']  # route_id and service_id are FKs, validated separately
    STOP_TIME_MANDATORY_FIELDS = ['arrival_time', 'departure_time', 'stop_sequence']  # trip_id and stop_id are FKs
    FARE_ATTRIBUTE_MANDATORY_FIELDS = ['fare_id', 'price', 'currency_type', 'payment_method']
    FEED_INFO_MANDATORY_FIELDS = ['feed_publisher_name', 'feed_publisher_url', 'feed_lang']

    def __init__(self, db: AsyncSession):
        self.db = db
        self.preferences: Optional[AgencyValidationPreferences] = None

    async def _load_validation_preferences(self, agency_id: int) -> None:
        """
        Load validation preferences for an agency.
        Uses defaults (all enabled) if no preferences exist.

        Per claude.md line 49: configurable validation per agency
        """
        prefs_query = select(AgencyValidationPreferences).where(
            AgencyValidationPreferences.agency_id == agency_id
        )
        result = await self.db.execute(prefs_query)
        preferences = result.scalar_one_or_none()

        if preferences:
            self.preferences = preferences
            logger.debug(f"Loaded validation preferences for agency {agency_id}")
        else:
            # Use defaults (all enabled)
            self.preferences = AgencyValidationPreferences(agency_id=agency_id)
            logger.debug(f"Using default validation preferences for agency {agency_id}")

    async def validate_feed(self, feed_id: int) -> ValidationResult:
        """
        Run all validation rules for a feed

        Args:
            feed_id: ID of the feed to validate

        Returns:
            ValidationResult with all issues found
        """
        logger.info(f"Starting validation for feed {feed_id}")
        result = ValidationResult()

        # Verify feed exists and load agency preferences
        feed_stmt = select(GTFSFeed).where(GTFSFeed.id == feed_id)
        feed_result = await self.db.execute(feed_stmt)
        feed = feed_result.scalar_one_or_none()

        if not feed:
            result.add_error('general', f'Feed with ID {feed_id} not found')
            return result

        # Load validation preferences for the agency
        await self._load_validation_preferences(feed.agency_id)

        # Run validation categories (each will check preferences internally)
        await self._validate_routes(feed_id, result)
        await self._validate_shapes(feed_id, result)
        await self._validate_calendar(feed_id, result)
        await self._validate_calendar_dates(feed_id, result)
        await self._validate_stops(feed_id, result)
        await self._validate_trips(feed_id, result)
        await self._validate_stop_times(feed_id, result)
        await self._validate_fare_attributes(feed_id, result)
        await self._validate_feed_info(feed_id, result)

        logger.info(
            f"Validation complete for feed {feed_id}: "
            f"{result.error_count} errors, {result.warning_count} warnings"
        )

        return result

    async def _validate_routes(self, feed_id: int, result: ValidationResult):
        """
        Validate routes for a feed

        Checks:
        1. Route has valid agency reference
        2. No duplicated route_id within feed
        3. GTFS mandatory fields are filled (not just present)
        """
        logger.debug(f"Validating routes for feed {feed_id}")

        # Fetch all routes for this feed
        stmt = select(Route).where(Route.feed_id == feed_id)
        route_result = await self.db.execute(stmt)
        routes = route_result.scalars().all()

        if not routes:
            result.add_info('routes', f'No routes found for feed {feed_id}')
            return

        # Track route_ids to check for duplicates
        route_ids_seen = {}

        for route in routes:
            # Check 1: Mandatory fields are filled (not empty)
            if self.preferences.validate_route_mandatory:
                for field in self.ROUTE_MANDATORY_FIELDS:
                    value = getattr(route, field, None)
                    if value is None or (isinstance(value, str) and value.strip() == ''):
                        result.add_error(
                            'routes',
                            f'Route missing mandatory field: {field}',
                            entity_type='route',
                            entity_id=route.route_id,
                            field=field
                        )

            # Check 2: Duplicated route_id
            if self.preferences.validate_route_duplicates:
                if route.route_id in route_ids_seen:
                    result.add_error(
                        'routes',
                        f'Duplicated route_id: {route.route_id}',
                        entity_type='route',
                        entity_id=route.route_id,
                        field='route_id',
                        details={
                            'first_occurrence': route_ids_seen[route.route_id],
                            'duplicate': route.route_id
                        }
                    )
                else:
                    route_ids_seen[route.route_id] = route.route_id
            else:
                # Still need to track for Check 3 even if duplicates check is disabled
                route_ids_seen[route.route_id] = route.route_id

            # Check 3: Route's agency has required GTFS fields
            if self.preferences.validate_route_agency:
                # Verify agency has required GTFS fields (agency_id FK is enforced by database)
                agency = await self.db.get(Agency, route.agency_id)
                if agency:
                    # Check for required GTFS agency fields
                    if not agency.agency_timezone:
                        result.add_warning(
                            'routes',
                            f'Route\'s agency is missing agency_timezone (required by GTFS)',
                            entity_type='route',
                            entity_id=route.route_id,
                            field='agency_id',
                            details={'agency_id': route.agency_id, 'agency_name': agency.name}
                        )

        result.add_info('routes', f'Validated {len(routes)} routes')

    async def _validate_shapes(self, feed_id: int, result: ValidationResult):
        """
        Validate shapes for a feed

        Checks:
        1. shape_dist_traveled is filled where expected
        2. shape_dist_traveled makes sense considering lat/long
        3. shape_pt_sequence is filled and sequential
        4. GTFS mandatory fields are filled
        """
        logger.debug(f"Validating shapes for feed {feed_id}")

        # Fetch all shapes for this feed, ordered by shape_id and sequence
        stmt = select(Shape).where(Shape.feed_id == feed_id).order_by(
            Shape.shape_id,
            Shape.shape_pt_sequence
        )
        shape_result = await self.db.execute(stmt)
        shapes = shape_result.scalars().all()

        if not shapes:
            result.add_info('shapes', f'No shapes found for feed {feed_id}')
            return

        # Group shapes by shape_id
        shapes_by_id: Dict[str, List[Shape]] = {}
        for shape in shapes:
            if shape.shape_id not in shapes_by_id:
                shapes_by_id[shape.shape_id] = []
            shapes_by_id[shape.shape_id].append(shape)

        # Validate each shape sequence
        for shape_id, shape_points in shapes_by_id.items():
            self._validate_shape_sequence(shape_id, shape_points, result)

        result.add_info('shapes', f'Validated {len(shapes_by_id)} shapes with {len(shapes)} points')

    def _validate_shape_sequence(
        self,
        shape_id: str,
        shape_points: List[Shape],
        result: ValidationResult
    ):
        """
        Validate a single shape sequence

        Args:
            shape_id: The shape ID being validated
            shape_points: List of shape points, should be ordered by sequence
            result: ValidationResult to add issues to
        """
        prev_point = None
        prev_sequence = None
        total_calculated_distance = 0.0
        has_dist_traveled = False

        for i, point in enumerate(shape_points):
            # Check mandatory fields
            if self.preferences.validate_shape_mandatory:
                for field in self.SHAPE_MANDATORY_FIELDS:
                    value = getattr(point, field, None)
                    if value is None:
                        result.add_error(
                            'shapes',
                            f'Shape point missing mandatory field: {field}',
                            entity_type='shape',
                            entity_id=shape_id,
                            field=field,
                            details={'sequence': point.shape_pt_sequence}
                        )

            # Check shape_pt_sequence is filled and sequential
            if self.preferences.validate_shape_sequence:
                if point.shape_pt_sequence is None:
                    result.add_error(
                        'shapes',
                        f'Shape point missing shape_pt_sequence',
                        entity_type='shape',
                        entity_id=shape_id,
                        field='shape_pt_sequence',
                        details={'point_index': i}
                    )
                elif prev_sequence is not None:
                    if point.shape_pt_sequence <= prev_sequence:
                        result.add_error(
                            'shapes',
                            f'Shape point sequence not increasing: {prev_sequence} -> {point.shape_pt_sequence}',
                            entity_type='shape',
                            entity_id=shape_id,
                            field='shape_pt_sequence',
                            details={
                                'previous_sequence': prev_sequence,
                                'current_sequence': point.shape_pt_sequence
                            }
                        )

            # Track if any points have shape_dist_traveled
            if point.shape_dist_traveled is not None:
                has_dist_traveled = True

            # Calculate distance from previous point (Haversine formula)
            if prev_point and point.shape_pt_lat and point.shape_pt_lon:
                distance = self._calculate_distance(
                    prev_point.shape_pt_lat,
                    prev_point.shape_pt_lon,
                    point.shape_pt_lat,
                    point.shape_pt_lon
                )
                total_calculated_distance += distance

                # Check if shape_dist_traveled makes sense
                if self.preferences.validate_shape_dist_accuracy:
                    if point.shape_dist_traveled is not None and prev_point.shape_dist_traveled is not None:
                        reported_distance = point.shape_dist_traveled - prev_point.shape_dist_traveled

                        # Allow 20% tolerance for reported vs calculated distance
                        if abs(reported_distance - distance) > distance * 0.2:
                            result.add_warning(
                                'shapes',
                                f'Shape distance mismatch: reported {reported_distance:.2f}m vs calculated {distance:.2f}m',
                                entity_type='shape',
                                entity_id=shape_id,
                                field='shape_dist_traveled',
                                details={
                                    'sequence': point.shape_pt_sequence,
                                    'reported_distance': reported_distance,
                                    'calculated_distance': distance,
                                    'difference_percent': abs(reported_distance - distance) / distance * 100
                                }
                            )

            prev_point = point
            prev_sequence = point.shape_pt_sequence

        # Check if shape_dist_traveled is filled consistently
        if self.preferences.validate_shape_dist_traveled and len(shape_points) > 0:
            points_with_dist = sum(1 for p in shape_points if p.shape_dist_traveled is not None)

            if points_with_dist > 0 and points_with_dist < len(shape_points):
                result.add_warning(
                    'shapes',
                    f'Shape has incomplete shape_dist_traveled: {points_with_dist}/{len(shape_points)} points',
                    entity_type='shape',
                    entity_id=shape_id,
                    field='shape_dist_traveled',
                    details={
                        'points_with_distance': points_with_dist,
                        'total_points': len(shape_points)
                    }
                )

    async def _validate_calendar(self, feed_id: int, result: ValidationResult):
        """
        Validate calendar for a feed

        Checks:
        1. GTFS mandatory fields are filled
        """
        logger.debug(f"Validating calendar for feed {feed_id}")

        stmt = select(Calendar).where(Calendar.feed_id == feed_id)
        calendar_result = await self.db.execute(stmt)
        calendars = calendar_result.scalars().all()

        if not calendars:
            result.add_info('calendar', f'No calendars found for feed {feed_id}')
            return

        for calendar in calendars:
            # Check mandatory fields
            if self.preferences.validate_calendar_mandatory:
                for field in self.CALENDAR_MANDATORY_FIELDS:
                    value = getattr(calendar, field, None)
                    if value is None or (isinstance(value, str) and value.strip() == ''):
                        result.add_error(
                            'calendar',
                            f'Calendar missing mandatory field: {field}',
                            entity_type='calendar',
                            entity_id=calendar.service_id,
                            field=field
                        )

        result.add_info('calendar', f'Validated {len(calendars)} calendars')

    async def _validate_calendar_dates(self, feed_id: int, result: ValidationResult):
        """
        Validate calendar_dates for a feed

        Checks:
        1. GTFS mandatory fields are filled
        """
        logger.debug(f"Validating calendar_dates for feed {feed_id}")

        # CalendarDate has service_id FK to Calendar, need to join to get feed_id
        stmt = select(CalendarDate).join(Calendar).where(Calendar.feed_id == feed_id)
        calendar_date_result = await self.db.execute(stmt)
        calendar_dates = calendar_date_result.scalars().all()

        if not calendar_dates:
            result.add_info('calendar_dates', f'No calendar_dates found for feed {feed_id}')
            return

        for calendar_date in calendar_dates:
            # Check mandatory fields
            if self.preferences.validate_calendar_date_mandatory:
                for field in self.CALENDAR_DATE_MANDATORY_FIELDS:
                    value = getattr(calendar_date, field, None)
                    if value is None or (isinstance(value, str) and value.strip() == ''):
                        result.add_error(
                            'calendar_dates',
                            f'CalendarDate missing mandatory field: {field}',
                            entity_type='calendar_date',
                            entity_id=f"{calendar_date.service_id}_{calendar_date.date}",
                            field=field,
                            details={'service_id': calendar_date.service_id, 'date': str(calendar_date.date)}
                        )

        result.add_info('calendar_dates', f'Validated {len(calendar_dates)} calendar_dates')

    async def _validate_stops(self, feed_id: int, result: ValidationResult):
        """
        Validate stops for a feed

        Checks:
        1. stop_id is not duplicated
        2. GTFS mandatory fields are filled
        """
        logger.debug(f"Validating stops for feed {feed_id}")

        stmt = select(Stop).where(Stop.feed_id == feed_id)
        stop_result = await self.db.execute(stmt)
        stops = stop_result.scalars().all()

        if not stops:
            result.add_info('stops', f'No stops found for feed {feed_id}')
            return

        # Track stop_ids to check for duplicates
        stop_ids_seen = {}

        for stop in stops:
            # Check mandatory fields
            if self.preferences.validate_stop_mandatory:
                for field in self.STOP_MANDATORY_FIELDS:
                    value = getattr(stop, field, None)
                    if value is None or (isinstance(value, str) and value.strip() == ''):
                        result.add_error(
                            'stops',
                            f'Stop missing mandatory field: {field}',
                            entity_type='stop',
                            entity_id=stop.stop_id,
                            field=field
                        )

            # Check for duplicated stop_id
            if self.preferences.validate_stop_duplicates:
                if stop.stop_id in stop_ids_seen:
                    result.add_error(
                        'stops',
                        f'Duplicated stop_id: {stop.stop_id}',
                        entity_type='stop',
                        entity_id=stop.stop_id,
                        field='stop_id',
                        details={
                            'first_occurrence': stop_ids_seen[stop.stop_id],
                            'duplicate': stop.stop_id
                        }
                    )
                else:
                    stop_ids_seen[stop.stop_id] = stop.stop_id
            else:
                stop_ids_seen[stop.stop_id] = stop.stop_id

        result.add_info('stops', f'Validated {len(stops)} stops')

    async def _validate_trips(self, feed_id: int, result: ValidationResult):
        """
        Validate trips for a feed

        Checks:
        1. service_id is declared on calendar or calendar_dates
        2. trip_id is unique
        3. shape_id is a valid shape on shapes (if present)
        4. GTFS mandatory fields are filled
        """
        logger.debug(f"Validating trips for feed {feed_id}")

        # Get all trips with service relationship loaded (shape_id is a field, not a relationship)
        stmt = select(Trip).options(
            selectinload(Trip.service)
        ).where(Trip.feed_id == feed_id)
        trip_result = await self.db.execute(stmt)
        trips = trip_result.scalars().all()

        if not trips:
            result.add_info('trips', f'No trips found for feed {feed_id}')
            return

        # Get all valid service_ids from calendar and calendar_dates
        calendar_stmt = select(Calendar.service_id).where(Calendar.feed_id == feed_id).distinct()
        calendar_result = await self.db.execute(calendar_stmt)
        calendar_service_ids = set(row[0] for row in calendar_result.all())

        # CalendarDate has feed_id, query directly
        calendar_date_stmt = select(CalendarDate.service_id).where(
            CalendarDate.feed_id == feed_id
        ).distinct()
        calendar_date_result = await self.db.execute(calendar_date_stmt)
        calendar_date_service_ids = set(row[0] for row in calendar_date_result.all())

        valid_service_ids = calendar_service_ids | calendar_date_service_ids

        # Get all valid shape_ids
        shape_stmt = select(Shape.shape_id).where(Shape.feed_id == feed_id).distinct()
        shape_result = await self.db.execute(shape_stmt)
        valid_shape_ids = set(row[0] for row in shape_result.all())

        # Track trip_ids to check for duplicates
        trip_ids_seen = {}

        for trip in trips:
            # Check mandatory fields
            if self.preferences.validate_trip_mandatory:
                for field in self.TRIP_MANDATORY_FIELDS:
                    value = getattr(trip, field, None)
                    if value is None or (isinstance(value, str) and value.strip() == ''):
                        result.add_error(
                            'trips',
                            f'Trip missing mandatory field: {field}',
                            entity_type='trip',
                            entity_id=trip.trip_id,
                            field=field
                        )

            # Check for duplicated trip_id
            if self.preferences.validate_trip_duplicates:
                if trip.trip_id in trip_ids_seen:
                    result.add_error(
                        'trips',
                        f'Duplicated trip_id: {trip.trip_id}',
                        entity_type='trip',
                        entity_id=trip.trip_id,
                        field='trip_id',
                        details={
                            'first_occurrence': trip_ids_seen[trip.trip_id],
                            'duplicate': trip.trip_id
                        }
                    )
                else:
                    trip_ids_seen[trip.trip_id] = trip.trip_id
            else:
                trip_ids_seen[trip.trip_id] = trip.trip_id

            # Check service_id is valid
            if self.preferences.validate_trip_service:
                # Get service_id from the Calendar relationship
                if hasattr(trip, 'service') and trip.service:
                    service_id = trip.service.service_id
                else:
                    service_id = None

                if service_id and service_id not in valid_service_ids:
                    result.add_error(
                        'trips',
                        f'Trip references non-existent service_id: {service_id}',
                        entity_type='trip',
                        entity_id=trip.trip_id,
                        field='service_id',
                        details={'service_id': service_id}
                    )

            # Check shape_id is valid (if present)
            if self.preferences.validate_trip_shape:
                if trip.shape_id and trip.shape_id not in valid_shape_ids:
                    result.add_error(
                        'trips',
                        f'Trip references non-existent shape_id: {trip.shape_id}',
                        entity_type='trip',
                        entity_id=trip.trip_id,
                        field='shape_id',
                        details={'shape_id': trip.shape_id}
                    )

        result.add_info('trips', f'Validated {len(trips)} trips')

    async def _validate_stop_times(self, feed_id: int, result: ValidationResult):
        """
        Validate stop_times for a feed using memory-efficient database queries.

        Checks:
        1. trip_id is valid and in trips list
        2. stop_id is valid and one of the stops
        3. stop_sequence makes sense (increasing)
        4. GTFS mandatory fields are filled

        Note: Uses aggregate queries instead of loading all stop_times into memory
        to handle large feeds (millions of rows).
        """
        from sqlalchemy import text

        logger.debug(f"Validating stop_times for feed {feed_id}")

        # First, get the total count efficiently
        count_stmt = select(func.count()).select_from(StopTime).where(StopTime.feed_id == feed_id)
        count_result = await self.db.execute(count_stmt)
        total_count = count_result.scalar() or 0

        if total_count == 0:
            result.add_info('stop_times', f'No stop_times found for feed {feed_id}')
            return

        logger.debug(f"Validating {total_count} stop_times for feed {feed_id}")

        # Get all valid trip IDs (needed for reference)
        trip_stmt = select(Trip.trip_id).where(Trip.feed_id == feed_id)
        trip_result = await self.db.execute(trip_stmt)
        valid_trip_ids = set(row[0] for row in trip_result.all())

        # Get all valid stop IDs
        stop_stmt = select(Stop.stop_id).where(Stop.feed_id == feed_id)
        stop_result = await self.db.execute(stop_stmt)
        valid_stop_ids = set(row[0] for row in stop_result.all())

        # 1. Check mandatory fields using COUNT with NULL checks (memory efficient)
        if self.preferences.validate_stop_time_mandatory:
            for field in self.STOP_TIME_MANDATORY_FIELDS:
                null_count_stmt = (
                    select(func.count())
                    .select_from(StopTime)
                    .where(
                        StopTime.feed_id == feed_id,
                        getattr(StopTime, field).is_(None)
                    )
                )
                null_result = await self.db.execute(null_count_stmt)
                null_count = null_result.scalar() or 0

                if null_count > 0:
                    result.add_error(
                        'stop_times',
                        f'{null_count} stop_times missing mandatory field: {field}',
                        entity_type='stop_time',
                        field=field,
                        details={'missing_count': null_count, 'total_count': total_count}
                    )

        # 2. Check for invalid trip_id references
        if self.preferences.validate_stop_time_trip:
            # Find stop_times with trip_id not in valid trips for this feed
            # Use raw SQL for efficiency with composite keys
            invalid_trip_sql = text("""
                SELECT COUNT(*)
                FROM gtfs_stop_times st
                WHERE st.feed_id = :feed_id
                AND NOT EXISTS (
                    SELECT 1 FROM gtfs_trips t
                    WHERE t.feed_id = st.feed_id AND t.trip_id = st.trip_id
                )
            """)
            invalid_trip_result = await self.db.execute(invalid_trip_sql, {"feed_id": feed_id})
            invalid_trip_count = invalid_trip_result.scalar() or 0

            if invalid_trip_count > 0:
                result.add_error(
                    'stop_times',
                    f'{invalid_trip_count} stop_times reference non-existent trips',
                    entity_type='stop_time',
                    field='trip_id',
                    details={'invalid_count': invalid_trip_count}
                )

        # 3. Check for invalid stop_id references using LEFT JOIN
        if self.preferences.validate_stop_time_stop:
            # Use raw SQL for efficiency - find stop_times referencing non-existent stops
            invalid_stop_sql = text("""
                SELECT COUNT(*)
                FROM gtfs_stop_times st
                WHERE st.feed_id = :feed_id
                AND NOT EXISTS (
                    SELECT 1 FROM gtfs_stops s
                    WHERE s.feed_id = st.feed_id AND s.stop_id = st.stop_id
                )
            """)
            invalid_stop_result = await self.db.execute(invalid_stop_sql, {"feed_id": feed_id})
            invalid_stop_count = invalid_stop_result.scalar() or 0

            if invalid_stop_count > 0:
                result.add_error(
                    'stop_times',
                    f'{invalid_stop_count} stop_times reference non-existent stops',
                    entity_type='stop_time',
                    field='stop_id',
                    details={'invalid_count': invalid_stop_count}
                )

        # 4. Check stop_sequence ordering using window functions (database-side)
        if self.preferences.validate_stop_time_sequence:
            # Use raw SQL with window function to find sequence violations
            sequence_check_sql = text("""
                WITH sequenced AS (
                    SELECT
                        st.trip_id,
                        st.stop_sequence,
                        LAG(st.stop_sequence) OVER (PARTITION BY st.trip_id ORDER BY st.stop_sequence) as prev_sequence
                    FROM gtfs_stop_times st
                    WHERE st.feed_id = :feed_id
                )
                SELECT COUNT(*)
                FROM sequenced
                WHERE prev_sequence IS NOT NULL AND stop_sequence <= prev_sequence
            """)
            sequence_result = await self.db.execute(sequence_check_sql, {"feed_id": feed_id})
            sequence_violations = sequence_result.scalar() or 0

            if sequence_violations > 0:
                result.add_warning(
                    'stop_times',
                    f'{sequence_violations} stop_times have non-increasing stop_sequence',
                    entity_type='stop_time',
                    field='stop_sequence',
                    details={'violation_count': sequence_violations}
                )

        result.add_info('stop_times', f'Validated {total_count} stop_times (using efficient aggregate queries)')

    @staticmethod
    def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two points using Haversine formula

        Returns distance in meters
        """
        import math

        # Earth radius in meters
        R = 6371000

        # Convert to radians
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        # Haversine formula
        a = math.sin(delta_lat / 2) ** 2 + \
            math.cos(lat1_rad) * math.cos(lat2_rad) * \
            math.sin(delta_lon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    async def _validate_fare_attributes(self, feed_id: int, result: ValidationResult):
        """
        Validate fare_attributes for a feed

        Checks:
        1. GTFS mandatory fields are filled
        """
        logger.debug(f"Validating fare_attributes for feed {feed_id}")

        stmt = select(FareAttribute).where(FareAttribute.feed_id == feed_id)
        fare_result = await self.db.execute(stmt)
        fare_attributes = fare_result.scalars().all()

        if not fare_attributes:
            result.add_info('fare_attributes', f'No fare_attributes found for feed {feed_id}')
            return

        for fare_attr in fare_attributes:
            # Check mandatory fields
            if self.preferences.validate_fare_attribute_mandatory:
                for field in self.FARE_ATTRIBUTE_MANDATORY_FIELDS:
                    value = getattr(fare_attr, field, None)
                    if value is None or (isinstance(value, str) and value.strip() == ''):
                        result.add_error(
                            'fare_attributes',
                            f'FareAttribute missing mandatory field: {field}',
                            entity_type='fare_attribute',
                            entity_id=fare_attr.fare_id,
                            field=field,
                            details={'fare_id': fare_attr.fare_id}
                        )

        result.add_info('fare_attributes', f'Validated {len(fare_attributes)} fare_attributes')

    async def _validate_feed_info(self, feed_id: int, result: ValidationResult):
        """
        Validate feed_info for a feed

        Checks:
        1. GTFS mandatory fields are filled
        """
        logger.debug(f"Validating feed_info for feed {feed_id}")

        stmt = select(FeedInfo).where(FeedInfo.feed_id == feed_id)
        feed_info_result = await self.db.execute(stmt)
        feed_info = feed_info_result.scalar_one_or_none()

        if not feed_info:
            result.add_info('feed_info', f'No feed_info found for feed {feed_id}')
            return

        # Check mandatory fields
        if self.preferences.validate_feed_info_mandatory:
            for field in self.FEED_INFO_MANDATORY_FIELDS:
                value = getattr(feed_info, field, None)
                if value is None or (isinstance(value, str) and value.strip() == ''):
                    result.add_error(
                        'feed_info',
                        f'FeedInfo missing mandatory field: {field}',
                        entity_type='feed_info',
                        entity_id=str(feed_info.feed_id),
                        field=field
                    )

        result.add_info('feed_info', 'Validated feed_info')
