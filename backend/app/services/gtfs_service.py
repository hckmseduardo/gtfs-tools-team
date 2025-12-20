"""GTFS Import/Export Service"""

import csv
import io
import zipfile
import logging
from typing import Dict, List, Optional, BinaryIO
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

from app.models.gtfs import (
    Route, Stop, Trip, StopTime, Calendar, CalendarDate, Shape, GTFSFeed,
    FareAttribute, FareRule, FeedInfo
)
from app.models.agency import Agency
from app.schemas.gtfs_import import (
    GTFSImportOptions,
    GTFSImportResult,
    GTFSExportOptions,
    GTFSExportResult,
    GTFSFileStats,
    GTFSValidationResult,
    GTFSValidationIssue,
)


class GTFSService:
    """Service for GTFS file import/export operations"""

    # Batch size for bulk inserts (configurable for performance tuning)
    # PostgreSQL asyncpg limits query parameters to 32,767
    # Stop_times has ~10 columns, so max batch = 32767/10 ≈ 3000
    BULK_INSERT_BATCH_SIZE = 2500

    # Max IDs for IN clause queries (must stay under 32,767)
    MAX_IN_CLAUSE_IDS = 30000

    # Required GTFS files
    REQUIRED_FILES = ["agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"]

    # Optional GTFS files (complete list per GTFS specification)
    OPTIONAL_FILES = [
        "calendar.txt", "calendar_dates.txt", "shapes.txt", "frequencies.txt",
        "fare_attributes.txt", "fare_rules.txt", "timeframes.txt", "fare_media.txt",
        "fare_products.txt", "fare_leg_rules.txt", "fare_transfer_rules.txt",
        "areas.txt", "stop_areas.txt", "networks.txt", "route_networks.txt",
        "transfers.txt", "pathways.txt", "levels.txt", "location_groups.txt",
        "location_group_stops.txt", "booking_rules.txt", "translations.txt",
        "feed_info.txt", "attributions.txt"
    ]

    # All valid GTFS files (required + optional)
    VALID_GTFS_FILES = set(REQUIRED_FILES + OPTIONAL_FILES)

    @staticmethod
    def _safe_int(value: str | None, default: int = 0) -> int:
        """Safely convert a string to int, handling None and empty strings"""
        if not value or value.strip() == "":
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_float(value: str | None, default: float = 0.0) -> float:
        """Safely convert a string to float, handling None and empty strings"""
        if not value or value.strip() == "":
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    async def validate_gtfs_zip(
        zip_file: BinaryIO,
        db: AsyncSession,
    ) -> GTFSValidationResult:
        """
        Validate a GTFS zip file without importing it.

        Checks for:
        - Required files present
        - Valid CSV format
        - Required fields present
        - Basic data integrity
        """
        issues: List[GTFSValidationIssue] = []
        files_checked: List[str] = []

        try:
            with zipfile.ZipFile(zip_file, 'r') as zf:
                available_files = zf.namelist()

                # Check required files
                for required in GTFSService.REQUIRED_FILES:
                    if required not in available_files:
                        issues.append(GTFSValidationIssue(
                            severity="error",
                            file=required,
                            message=f"Required file {required} is missing from GTFS archive"
                        ))

                # Validate each file's structure (only GTFS-specified files)
                for filename in available_files:
                    if not filename.endswith('.txt'):
                        continue

                    # Skip non-GTFS files (supplementary files like version_chrono.txt, __Licence.txt, etc.)
                    # Generate an info-level notice but don't block import
                    if filename not in GTFSService.VALID_GTFS_FILES:
                        issues.append(GTFSValidationIssue(
                            severity="info",
                            file=filename,
                            message=f"Skipping non-GTFS file '{filename}' (supplementary file not part of GTFS specification)"
                        ))
                        continue

                    files_checked.append(filename)

                    try:
                        content = zf.read(filename).decode('utf-8-sig')
                        reader = csv.DictReader(io.StringIO(content))

                        # Check if file is empty
                        first_row = next(reader, None)
                        if first_row is None:
                            issues.append(GTFSValidationIssue(
                                severity="warning",
                                file=filename,
                                message=f"File {filename} is empty"
                            ))
                            continue

                        # Validate required fields based on GTFS spec
                        if filename == "routes.txt":
                            required_fields = ["route_id", "route_short_name", "route_long_name", "route_type"]
                            for field in required_fields:
                                if field not in reader.fieldnames:
                                    issues.append(GTFSValidationIssue(
                                        severity="error",
                                        file=filename,
                                        field=field,
                                        message=f"Required field '{field}' missing in {filename}"
                                    ))

                        elif filename == "stops.txt":
                            required_fields = ["stop_id", "stop_name", "stop_lat", "stop_lon"]
                            for field in required_fields:
                                if field not in reader.fieldnames:
                                    issues.append(GTFSValidationIssue(
                                        severity="error",
                                        file=filename,
                                        field=field,
                                        message=f"Required field '{field}' missing in {filename}"
                                    ))

                        elif filename == "trips.txt":
                            required_fields = ["route_id", "service_id", "trip_id"]
                            for field in required_fields:
                                if field not in reader.fieldnames:
                                    issues.append(GTFSValidationIssue(
                                        severity="error",
                                        file=filename,
                                        field=field,
                                        message=f"Required field '{field}' missing in {filename}"
                                    ))

                        elif filename == "stop_times.txt":
                            required_fields = ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]
                            for field in required_fields:
                                if field not in reader.fieldnames:
                                    issues.append(GTFSValidationIssue(
                                        severity="error",
                                        file=filename,
                                        field=field,
                                        message=f"Required field '{field}' missing in {filename}"
                                    ))

                    except UnicodeDecodeError:
                        issues.append(GTFSValidationIssue(
                            severity="error",
                            file=filename,
                            message=f"File {filename} has invalid encoding (must be UTF-8)"
                        ))
                    except csv.Error as e:
                        issues.append(GTFSValidationIssue(
                            severity="error",
                            file=filename,
                            message=f"CSV parsing error in {filename}: {str(e)}"
                        ))

        except zipfile.BadZipFile:
            issues.append(GTFSValidationIssue(
                severity="error",
                file="archive",
                message="Invalid ZIP file format"
            ))

        # Count issues by severity
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        info_count = sum(1 for i in issues if i.severity == "info")

        valid = error_count == 0

        # Generate summary
        if valid:
            summary = f"GTFS validation passed with {warning_count} warnings"
        else:
            summary = f"GTFS validation failed with {error_count} errors and {warning_count} warnings"

        return GTFSValidationResult(
            valid=valid,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            issues=issues,
            files_checked=files_checked,
            summary=summary,
        )

    @staticmethod
    async def import_gtfs_zip(
        zip_file: BinaryIO,
        options: GTFSImportOptions,
        db: AsyncSession,
        filename: str = "gtfs.zip",
        feed_name: str | None = None,
        feed_description: str | None = None,
        feed_version: str | None = None,
        progress_callback: callable = None,
    ) -> GTFSImportResult:
        """
        Import GTFS data from a ZIP file.

        Process:
        1. Validate ZIP structure
        2. Create GTFSFeed record
        3. Clear existing data if replace_existing=True
        4. Import files in dependency order:
           - routes.txt
           - stops.txt
           - calendar.txt
           - trips.txt
           - stop_times.txt
           - calendar_dates.txt
           - shapes.txt (if not skipped)
        5. Update feed statistics
        """
        logger.warning("========== import_gtfs_zip CALLED ==========")
        logger.warning(f"filename={filename}, agency_id={options.agency_id}")
        started_at = datetime.utcnow()
        files_processed: List[GTFSFileStats] = []
        total_imported = 0
        total_updated = 0
        total_skipped = 0
        total_errors = 0
        feed = None

        try:
            logger.warning("Starting try block...")
            # First validate
            validation = await GTFSService.validate_gtfs_zip(zip_file, db)

            if not validation.valid and options.stop_on_error:
                completed_at = datetime.utcnow()
                return GTFSImportResult(
                    success=False,
                    agency_id=options.agency_id,
                    files_processed=[],
                    validation_errors=[i.message for i in validation.issues if i.severity == "error"],
                    validation_warnings=[i.message for i in validation.issues if i.severity == "warning"],
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_seconds=(completed_at - started_at).total_seconds(),
                )

            if options.validate_only:
                completed_at = datetime.utcnow()
                return GTFSImportResult(
                    success=validation.valid,
                    agency_id=options.agency_id,
                    files_processed=[],
                    validation_errors=[i.message for i in validation.issues if i.severity == "error"],
                    validation_warnings=[i.message for i in validation.issues if i.severity == "warning"],
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_seconds=(completed_at - started_at).total_seconds(),
                )

            # Create GTFSFeed record
            # New feeds are active by default so they're immediately visible
            feed = GTFSFeed(
                agency_id=options.agency_id,
                name=feed_name or f"GTFS Import {started_at.strftime('%Y-%m-%d %H:%M:%S')}",
                description=feed_description or "GTFS data import",
                version=feed_version,
                filename=filename,
                imported_at=started_at.isoformat() + 'Z',
                is_active=True,  # Active by default for better UX
            )
            db.add(feed)
            await db.flush()  # Get feed.id

            logger.warning(f"Created feed {feed.id} '{feed.name}' for agency {options.agency_id}")

            # Clear existing data if requested
            if options.replace_existing:
                # Delete all feeds for this agency (cascade will delete all related data)
                await db.execute(
                    delete(GTFSFeed).where(
                        GTFSFeed.agency_id == options.agency_id,
                        GTFSFeed.id != feed.id  # Keep the newly created feed
                    )
                )
                await db.commit()
                logger.warning(f"Cleared existing feeds for agency {options.agency_id}")

            # Import GTFS files in dependency order
            with zipfile.ZipFile(zip_file, 'r') as zf:
                available_files = zf.namelist()

                # Process agency.txt FIRST (updates the primary Agency with GTFS data)
                if "agency.txt" in available_files:
                    stats = await GTFSService._process_agency_txt(
                        zf, feed.id, db
                    )
                    files_processed.append(stats)
                    total_imported += stats.imported
                    total_updated += stats.updated
                    total_skipped += stats.skipped
                    total_errors += stats.errors
                    await db.flush()
                    if progress_callback:
                        await progress_callback(5.0, "agency.txt imported")

                # Import routes.txt
                if "routes.txt" in available_files:
                    stats = await GTFSService._import_routes(
                        zf, feed.id, db
                    )
                    files_processed.append(stats)
                    total_imported += stats.imported
                    total_updated += stats.updated
                    total_skipped += stats.skipped
                    total_errors += stats.errors
                    await db.flush()  # Make routes visible to trips import
                    if progress_callback:
                        await progress_callback(10.0, "routes.txt imported")

                # Import stops.txt
                logger.warning(f"Checking if stops.txt in available_files: {'stops.txt' in available_files}")
                if "stops.txt" in available_files:
                    logger.warning(f"CALLING _import_stops for feed {feed.id}")
                    stats = await GTFSService._import_stops(
                        zf, feed.id, db
                    )
                    logger.warning(f"_import_stops returned: imported={stats.imported}, errors={stats.errors}")
                    files_processed.append(stats)
                    total_imported += stats.imported
                    total_updated += stats.updated
                    total_skipped += stats.skipped
                    total_errors += stats.errors
                    await db.flush()  # Make stops visible to stop_times import
                    if progress_callback:
                        await progress_callback(20.0, "stops.txt imported")
                else:
                    logger.error(f"stops.txt NOT FOUND in available_files: {available_files}")

                # Import calendar.txt
                if "calendar.txt" in available_files:
                    stats = await GTFSService._import_calendar(zf, feed.id, db)
                    files_processed.append(stats)
                    total_imported += stats.imported
                    total_updated += stats.updated
                    total_skipped += stats.skipped
                    total_errors += stats.errors
                    await db.flush()  # Make calendar records visible to trips import
                    if progress_callback:
                        await progress_callback(30.0, "calendar.txt imported")

                # Import calendar_dates.txt to create service_ids if calendar.txt is empty
                if "calendar_dates.txt" in available_files:
                    stats = await GTFSService._import_calendar_dates(zf, feed.id, db)
                    files_processed.append(stats)
                    total_imported += stats.imported
                    total_updated += stats.updated
                    total_skipped += stats.skipped
                    total_errors += stats.errors
                    await db.flush()  # Make service_ids visible to trips import
                    if progress_callback:
                        await progress_callback(35.0, "calendar_dates.txt imported")

                # Import shapes.txt BEFORE trips (trips reference shape_ids)
                if "shapes.txt" in available_files and not options.skip_shapes:
                    if progress_callback:
                        await progress_callback(35.0, "Importing shapes.txt...")
                    stats = await GTFSService._import_shapes(
                        zf, feed.id, db
                    )
                    files_processed.append(stats)
                    total_imported += stats.imported
                    total_updated += stats.updated
                    total_skipped += stats.skipped
                    total_errors += stats.errors
                    await db.flush()  # Make shapes visible to trips import

                    # Verify shapes are visible after flush
                    verify_shapes = await db.execute(
                        select(Shape.shape_id).where(Shape.feed_id == feed.id).distinct()
                    )
                    shape_count = len([s for (s,) in verify_shapes])
                    logger.warning(f"[GTFS IMPORT] VERIFICATION: {shape_count} distinct shape_ids visible after flush for feed {feed.id}")

                    if progress_callback:
                        await progress_callback(40.0, "shapes.txt imported")

                # Import trips.txt
                if "trips.txt" in available_files:
                    stats = await GTFSService._import_trips(
                        zf, feed.id, db
                    )
                    files_processed.append(stats)
                    total_imported += stats.imported
                    total_updated += stats.updated
                    total_skipped += stats.skipped
                    total_errors += stats.errors
                    await db.flush()  # Make trips visible to stop_times import
                    if progress_callback:
                        await progress_callback(45.0, "trips.txt imported")

                # Import stop_times.txt (largest file, 45-85%)
                if "stop_times.txt" in available_files:
                    if progress_callback:
                        await progress_callback(45.0, "Importing stop_times.txt...")
                    stats = await GTFSService._import_stop_times(zf, feed.id, db, progress_callback)
                    files_processed.append(stats)
                    total_imported += stats.imported
                    total_updated += stats.updated
                    total_skipped += stats.skipped
                    total_errors += stats.errors
                    if progress_callback:
                        await progress_callback(85.0, "stop_times.txt imported")

                # Import fare_attributes.txt (optional GTFS file)
                if "fare_attributes.txt" in available_files:
                    if progress_callback:
                        await progress_callback(88.0, "Importing fare_attributes.txt...")
                    stats = await GTFSService._import_fare_attributes(
                        zf, feed.id, db
                    )
                    files_processed.append(stats)
                    total_imported += stats.imported
                    total_updated += stats.updated
                    total_skipped += stats.skipped
                    total_errors += stats.errors
                    if progress_callback:
                        await progress_callback(90.0, "fare_attributes.txt imported")

                # Import fare_rules.txt (optional GTFS file, must come after fare_attributes)
                if "fare_rules.txt" in available_files:
                    if progress_callback:
                        await progress_callback(90.0, "Importing fare_rules.txt...")
                    stats = await GTFSService._import_fare_rules(
                        zf, feed.id, db
                    )
                    files_processed.append(stats)
                    total_imported += stats.imported
                    total_updated += stats.updated
                    total_skipped += stats.skipped
                    total_errors += stats.errors
                    if progress_callback:
                        await progress_callback(92.0, "fare_rules.txt imported")

                # Import feed_info.txt (optional GTFS file)
                if "feed_info.txt" in available_files:
                    if progress_callback:
                        await progress_callback(92.0, "Importing feed_info.txt...")
                    stats = await GTFSService._import_feed_info(
                        zf, feed.id, db
                    )
                    files_processed.append(stats)
                    total_imported += stats.imported
                    total_updated += stats.updated
                    total_skipped += stats.skipped
                    total_errors += stats.errors
                    if progress_callback:
                        await progress_callback(95.0, "feed_info.txt imported")

            # Update feed statistics
            if feed:
                # Count routes, stops, trips
                routes_count = await db.execute(
                    select(Route).where(Route.feed_id == feed.id)
                )
                feed.total_routes = len(routes_count.scalars().all())

                stops_count = await db.execute(
                    select(Stop).where(Stop.feed_id == feed.id)
                )
                feed.total_stops = len(stops_count.scalars().all())

                trips_count = await db.execute(
                    select(Trip).where(Trip.feed_id == feed.id)
                )
                feed.total_trips = len(trips_count.scalars().all())

                logger.warning(f"Feed {feed.id} stats: {feed.total_routes} routes, {feed.total_stops} stops, {feed.total_trips} trips")

            # Commit all changes
            await db.commit()

            completed_at = datetime.utcnow()
            return GTFSImportResult(
                success=total_errors == 0,
                agency_id=options.agency_id,
                feed_id=feed.id,
                files_processed=files_processed,
                total_imported=total_imported,
                total_updated=total_updated,
                total_skipped=total_skipped,
                total_errors=total_errors,
                validation_errors=[i.message for i in validation.issues if i.severity == "error"],
                validation_warnings=[i.message for i in validation.issues if i.severity == "warning"],
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=(completed_at - started_at).total_seconds(),
            )

        except Exception as e:
            await db.rollback()
            completed_at = datetime.utcnow()
            logger.error(f"Import failed: {str(e)}", exc_info=True)
            return GTFSImportResult(
                success=False,
                agency_id=options.agency_id,
                files_processed=files_processed,
                total_imported=total_imported,
                total_updated=total_updated,
                total_skipped=total_skipped,
                total_errors=total_errors + 1,
                validation_errors=[f"Import failed: {str(e)}"],
                validation_warnings=[],
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=(completed_at - started_at).total_seconds(),
            )

    @staticmethod
    async def export_gtfs_zip(
        options: GTFSExportOptions,
        db: AsyncSession,
    ) -> bytes:
        """
        Export GTFS data to a ZIP file.

        Uses feed_id if provided, otherwise finds the active feed for the agency.
        Returns the ZIP file as bytes.
        """
        # Determine which feed to export
        feed_id = options.feed_id
        if not feed_id:
            # Find the active feed for the agency
            feed_query = select(GTFSFeed).where(
                GTFSFeed.agency_id == options.agency_id,
                GTFSFeed.is_active == True
            ).order_by(GTFSFeed.imported_at.desc()).limit(1)
            feed_result = await db.execute(feed_query)
            feed = feed_result.scalar_one_or_none()
            if feed:
                feed_id = feed.id
            else:
                # No active feed, return empty zip
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    pass
                zip_buffer.seek(0)
                return zip_buffer.getvalue()

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Export agency.txt - get distinct agencies from routes in this feed
            agencies_result = await db.execute(
                select(Agency).join(Route, Route.agency_id == Agency.id)
                .where(Route.feed_id == feed_id)
                .distinct()
            )
            agencies = agencies_result.scalars().all()

            # If no routes, fall back to the feed's primary agency
            if not agencies:
                feed = await db.get(GTFSFeed, feed_id)
                if feed:
                    primary_agency = await db.get(Agency, feed.agency_id)
                    if primary_agency:
                        agencies = [primary_agency]

            if agencies:
                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=[
                    'agency_id', 'agency_name', 'agency_url', 'agency_timezone',
                    'agency_lang', 'agency_phone', 'agency_fare_url', 'agency_email'
                ])
                writer.writeheader()

                for agency in agencies:
                    writer.writerow({
                        'agency_id': agency.agency_id or '',
                        'agency_name': agency.name,
                        'agency_url': agency.agency_url or '',
                        'agency_timezone': agency.agency_timezone or '',
                        'agency_lang': agency.agency_lang or '',
                        'agency_phone': agency.agency_phone or '',
                        'agency_fare_url': agency.agency_fare_url or '',
                        'agency_email': agency.agency_email or '',
                    })

                zf.writestr('agency.txt', csv_buffer.getvalue())

            # Export routes.txt
            routes_result = await db.execute(
                select(Route).where(Route.feed_id == feed_id).options(selectinload(Route.agency))
            )
            routes = routes_result.scalars().all()

            if routes:
                # Collect all custom field keys from all routes
                custom_field_keys = set()
                for route in routes:
                    if route.custom_fields:
                        custom_field_keys.update(route.custom_fields.keys())

                # Standard GTFS fields + custom fields
                base_fields = [
                    'route_id', 'agency_id', 'route_short_name', 'route_long_name', 'route_desc',
                    'route_type', 'route_url', 'route_color', 'route_text_color',
                    'route_sort_order'
                ]
                fieldnames = base_fields + sorted(custom_field_keys)

                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
                writer.writeheader()

                for route in routes:
                    row = {
                        'route_id': route.route_id,
                        'agency_id': route.agency.agency_id if route.agency else '',
                        'route_short_name': route.route_short_name,
                        'route_long_name': route.route_long_name,
                        'route_desc': route.route_desc or '',
                        'route_type': route.route_type,
                        'route_url': route.route_url or '',
                        'route_color': route.route_color or '',
                        'route_text_color': route.route_text_color or '',
                        'route_sort_order': route.route_sort_order or '',
                    }
                    # Add custom fields
                    if route.custom_fields:
                        for key, value in route.custom_fields.items():
                            row[key] = value if value is not None else ''
                    writer.writerow(row)

                zf.writestr('routes.txt', csv_buffer.getvalue())

            # Export stops.txt
            stops_result = await db.execute(
                select(Stop).where(Stop.feed_id == feed_id)
            )
            stops = stops_result.scalars().all()

            if stops:
                # Collect all custom field keys from all stops
                custom_field_keys = set()
                for stop in stops:
                    if stop.custom_fields:
                        custom_field_keys.update(stop.custom_fields.keys())

                # Standard GTFS fields + custom fields
                base_fields = [
                    'stop_id', 'stop_code', 'stop_name', 'stop_desc',
                    'stop_lat', 'stop_lon', 'zone_id', 'stop_url',
                    'location_type', 'parent_station', 'stop_timezone',
                    'wheelchair_boarding', 'level_id', 'platform_code'
                ]
                fieldnames = base_fields + sorted(custom_field_keys)

                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
                writer.writeheader()

                for stop in stops:
                    row = {
                        'stop_id': stop.stop_id,
                        'stop_code': stop.stop_code or '',
                        'stop_name': stop.stop_name,
                        'stop_desc': stop.stop_desc or '',
                        'stop_lat': str(stop.stop_lat),
                        'stop_lon': str(stop.stop_lon),
                        'zone_id': stop.zone_id or '',
                        'stop_url': stop.stop_url or '',
                        'location_type': stop.location_type if stop.location_type is not None else '',
                        'parent_station': stop.parent_station or '',
                        'stop_timezone': stop.stop_timezone or '',
                        'wheelchair_boarding': stop.wheelchair_boarding if stop.wheelchair_boarding is not None else '',
                        'level_id': getattr(stop, 'level_id', None) or '',
                        'platform_code': getattr(stop, 'platform_code', None) or '',
                    }
                    # Add custom fields
                    if stop.custom_fields:
                        for key, value in stop.custom_fields.items():
                            row[key] = value if value is not None else ''
                    writer.writerow(row)

                zf.writestr('stops.txt', csv_buffer.getvalue())

            # Export calendar.txt
            calendars_result = await db.execute(
                select(Calendar).where(Calendar.feed_id == feed_id)
            )
            calendars = calendars_result.scalars().all()

            if calendars:
                # Collect all custom field keys from all calendars
                custom_field_keys = set()
                for calendar in calendars:
                    if calendar.custom_fields:
                        custom_field_keys.update(calendar.custom_fields.keys())

                # Standard GTFS fields + custom fields
                base_fields = [
                    'service_id', 'monday', 'tuesday', 'wednesday', 'thursday',
                    'friday', 'saturday', 'sunday', 'start_date', 'end_date'
                ]
                fieldnames = base_fields + sorted(custom_field_keys)

                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
                writer.writeheader()

                for calendar in calendars:
                    row = {
                        'service_id': calendar.service_id,
                        'monday': '1' if calendar.monday else '0',
                        'tuesday': '1' if calendar.tuesday else '0',
                        'wednesday': '1' if calendar.wednesday else '0',
                        'thursday': '1' if calendar.thursday else '0',
                        'friday': '1' if calendar.friday else '0',
                        'saturday': '1' if calendar.saturday else '0',
                        'sunday': '1' if calendar.sunday else '0',
                        'start_date': calendar.start_date,
                        'end_date': calendar.end_date,
                    }
                    # Add custom fields
                    if calendar.custom_fields:
                        for key, value in calendar.custom_fields.items():
                            row[key] = value if value is not None else ''
                    writer.writerow(row)

                zf.writestr('calendar.txt', csv_buffer.getvalue())

            # Export trips.txt
            trips_result = await db.execute(
                select(Trip).where(Trip.feed_id == feed_id)
                .options(selectinload(Trip.route), selectinload(Trip.service))
            )
            trips = trips_result.scalars().all()

            if trips:
                # Collect all custom field keys from all trips
                custom_field_keys = set()
                for trip in trips:
                    if trip.custom_fields:
                        custom_field_keys.update(trip.custom_fields.keys())

                # Standard GTFS fields + custom fields
                base_fields = [
                    'route_id', 'service_id', 'trip_id', 'trip_headsign',
                    'trip_short_name', 'direction_id', 'block_id', 'shape_id',
                    'wheelchair_accessible', 'bikes_allowed'
                ]
                fieldnames = base_fields + sorted(custom_field_keys)

                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
                writer.writeheader()

                for trip in trips:
                    row = {
                        'route_id': trip.route.route_id if trip.route else '',
                        'service_id': trip.service.service_id if trip.service else '',
                        'trip_id': trip.trip_id,
                        'trip_headsign': trip.trip_headsign or '',
                        'trip_short_name': trip.trip_short_name or '',
                        'direction_id': trip.direction_id if trip.direction_id is not None else '',
                        'block_id': trip.block_id or '',
                        'shape_id': trip.shape_id or '',
                        'wheelchair_accessible': trip.wheelchair_accessible if trip.wheelchair_accessible is not None else '',
                        'bikes_allowed': trip.bikes_allowed if trip.bikes_allowed is not None else '',
                    }
                    # Add custom fields
                    if trip.custom_fields:
                        for key, value in trip.custom_fields.items():
                            row[key] = value if value is not None else ''
                    writer.writerow(row)

                zf.writestr('trips.txt', csv_buffer.getvalue())

            # Export stop_times.txt
            if trips:
                trip_ids = [trip.trip_id for trip in trips]
                stop_times_result = await db.execute(
                    select(StopTime).where(
                        StopTime.feed_id == feed_id,
                        StopTime.trip_id.in_(trip_ids)
                    )
                    .options(selectinload(StopTime.trip), selectinload(StopTime.stop))
                    .order_by(StopTime.trip_id, StopTime.stop_sequence)
                )
                stop_times = stop_times_result.scalars().all()

                if stop_times:
                    csv_buffer = io.StringIO()
                    writer = csv.DictWriter(csv_buffer, fieldnames=[
                        'trip_id', 'arrival_time', 'departure_time', 'stop_id',
                        'stop_sequence', 'stop_headsign', 'pickup_type',
                        'drop_off_type', 'shape_dist_traveled', 'timepoint'
                    ])
                    writer.writeheader()

                    for stop_time in stop_times:
                        writer.writerow({
                            'trip_id': stop_time.trip.trip_id if stop_time.trip else '',
                            'arrival_time': stop_time.arrival_time,
                            'departure_time': stop_time.departure_time,
                            'stop_id': stop_time.stop.stop_id if stop_time.stop else '',
                            'stop_sequence': stop_time.stop_sequence,
                            'stop_headsign': stop_time.stop_headsign or '',
                            'pickup_type': stop_time.pickup_type or 0,
                            'drop_off_type': stop_time.drop_off_type or 0,
                            'shape_dist_traveled': str(stop_time.shape_dist_traveled) if stop_time.shape_dist_traveled else '',
                            'timepoint': stop_time.timepoint if stop_time.timepoint is not None else 1,
                        })

                    zf.writestr('stop_times.txt', csv_buffer.getvalue())

            # Export calendar_dates.txt (if requested)
            if options.include_calendar_dates:
                # Get calendar IDs for this feed
                calendar_service_ids = [c.service_id for c in calendars] if calendars else []
                if calendar_service_ids:
                    calendar_dates_result = await db.execute(
                        select(CalendarDate).where(
                            CalendarDate.feed_id == feed_id,
                            CalendarDate.service_id.in_(calendar_service_ids)
                        )
                        .options(selectinload(CalendarDate.service))
                    )
                    calendar_dates = calendar_dates_result.scalars().all()
                else:
                    calendar_dates = []

                if calendar_dates:
                    csv_buffer = io.StringIO()
                    writer = csv.DictWriter(csv_buffer, fieldnames=[
                        'service_id', 'date', 'exception_type'
                    ])
                    writer.writeheader()

                    for calendar_date in calendar_dates:
                        writer.writerow({
                            'service_id': calendar_date.service.service_id if calendar_date.service else '',
                            'date': calendar_date.date,
                            'exception_type': calendar_date.exception_type,
                        })

                    zf.writestr('calendar_dates.txt', csv_buffer.getvalue())

            # Export shapes.txt (if requested)
            if options.include_shapes:
                shapes_result = await db.execute(
                    select(Shape).where(Shape.feed_id == feed_id)
                    .order_by(Shape.shape_id, Shape.shape_pt_sequence)
                )
                shapes = shapes_result.scalars().all()

                if shapes:
                    csv_buffer = io.StringIO()
                    writer = csv.DictWriter(csv_buffer, fieldnames=[
                        'shape_id', 'shape_pt_lat', 'shape_pt_lon',
                        'shape_pt_sequence', 'shape_dist_traveled'
                    ])
                    writer.writeheader()

                    for shape in shapes:
                        writer.writerow({
                            'shape_id': shape.shape_id,
                            'shape_pt_lat': str(shape.shape_pt_lat),
                            'shape_pt_lon': str(shape.shape_pt_lon),
                            'shape_pt_sequence': shape.shape_pt_sequence,
                            'shape_dist_traveled': str(shape.shape_dist_traveled) if shape.shape_dist_traveled else '',
                        })

                    zf.writestr('shapes.txt', csv_buffer.getvalue())

            # Export fare_attributes.txt
            fare_attrs_result = await db.execute(
                select(FareAttribute).where(FareAttribute.feed_id == feed_id)
            )
            fare_attrs = fare_attrs_result.scalars().all()

            if fare_attrs:
                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=[
                    'fare_id', 'price', 'currency_type', 'payment_method',
                    'transfers', 'agency_id', 'transfer_duration'
                ])
                writer.writeheader()

                for fare in fare_attrs:
                    writer.writerow({
                        'fare_id': fare.fare_id,
                        'price': str(fare.price),
                        'currency_type': fare.currency_type,
                        'payment_method': fare.payment_method,
                        'transfers': fare.transfers if fare.transfers is not None else '',
                        'agency_id': fare.agency_id or '',
                        'transfer_duration': fare.transfer_duration or '',
                    })

                zf.writestr('fare_attributes.txt', csv_buffer.getvalue())

            # Export feed_info.txt
            feed_info_result = await db.execute(
                select(FeedInfo).where(FeedInfo.feed_id == feed_id)
            )
            feed_info = feed_info_result.scalar_one_or_none()

            if feed_info:
                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=[
                    'feed_publisher_name', 'feed_publisher_url', 'feed_lang',
                    'default_lang', 'feed_start_date', 'feed_end_date',
                    'feed_version', 'feed_contact_email', 'feed_contact_url'
                ])
                writer.writeheader()

                writer.writerow({
                    'feed_publisher_name': feed_info.feed_publisher_name,
                    'feed_publisher_url': feed_info.feed_publisher_url,
                    'feed_lang': feed_info.feed_lang,
                    'default_lang': feed_info.default_lang or '',
                    'feed_start_date': feed_info.feed_start_date or '',
                    'feed_end_date': feed_info.feed_end_date or '',
                    'feed_version': feed_info.feed_version or '',
                    'feed_contact_email': feed_info.feed_contact_email or '',
                    'feed_contact_url': feed_info.feed_contact_url or '',
                })

                zf.writestr('feed_info.txt', csv_buffer.getvalue())

        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    # Helper methods for importing specific GTFS files

    @staticmethod
    async def _process_agency_txt(
        zf: zipfile.ZipFile,
        feed_id: int,
        db: AsyncSession,
    ) -> GTFSFileStats:
        """
        Process agency.txt and update the feed's primary Agency with GTFS data.

        For single-agency feeds: Updates the feed's Agency with agency.txt data.
        For multi-agency feeds: Currently maps all routes to the feed's primary Agency.

        Note: This replaces the old _import_gtfs_agencies method.
        The gtfs_agencies table has been removed - Agency is now the single source of truth.
        """
        imported = 0
        updated = 0
        skipped = 0
        errors = 0

        try:
            # Get the feed and its primary agency
            feed = await db.get(GTFSFeed, feed_id)
            if not feed:
                raise ValueError(f"Feed {feed_id} not found")

            primary_agency = await db.get(Agency, feed.agency_id)
            if not primary_agency:
                raise ValueError(f"Agency {feed.agency_id} not found")

            content = zf.read("agency.txt").decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))

            # For the first agency in the file, update the primary agency's GTFS fields
            first_agency = True
            for row in reader:
                try:
                    if first_agency:
                        # Update the primary agency with GTFS data from first agency row
                        primary_agency.agency_id = row.get('agency_id', '') or primary_agency.agency_id
                        primary_agency.agency_url = row.get('agency_url', '') or primary_agency.agency_url
                        primary_agency.agency_timezone = row.get('agency_timezone', '') or primary_agency.agency_timezone
                        primary_agency.agency_lang = row.get('agency_lang') or primary_agency.agency_lang
                        primary_agency.agency_phone = row.get('agency_phone') or primary_agency.agency_phone
                        primary_agency.agency_fare_url = row.get('agency_fare_url') or primary_agency.agency_fare_url
                        primary_agency.agency_email = row.get('agency_email') or primary_agency.agency_email

                        # Also update name if not already set
                        if not primary_agency.name or primary_agency.name == "New Agency":
                            primary_agency.name = row.get('agency_name', '') or primary_agency.name

                        updated += 1
                        first_agency = False
                    else:
                        # Additional agencies in multi-agency GTFS - log and skip for now
                        # In future, could create separate Agency records
                        logger.info(f"Skipping additional agency in GTFS: {row.get('agency_id', 'unknown')}")
                        skipped += 1

                except Exception as e:
                    logger.error(f"Error processing agency row {row.get('agency_id', 'unknown')}: {str(e)}")
                    errors += 1

            await db.flush()

        except Exception as e:
            logger.error(f"Error reading agency.txt: {str(e)}")
            errors += 1

        return GTFSFileStats(
            filename="agency.txt",
            imported=imported,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    @staticmethod
    async def _import_routes(
        zf: zipfile.ZipFile,
        feed_id: int,
        db: AsyncSession,
    ) -> GTFSFileStats:
        """Import routes.txt"""
        imported = 0
        updated = 0
        skipped = 0
        errors = 0

        try:
            # Get the feed's agency_id
            feed = await db.get(GTFSFeed, feed_id)
            if not feed:
                raise ValueError(f"Feed {feed_id} not found")
            agency_id = feed.agency_id

            content = zf.read("routes.txt").decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))

            # Standard GTFS route fields
            standard_fields = {
                'route_id', 'agency_id', 'route_short_name', 'route_long_name', 'route_desc',
                'route_type', 'route_url', 'route_color', 'route_text_color', 'route_sort_order'
            }

            for row in reader:
                try:
                    # Extract custom fields (any field not in standard GTFS spec)
                    custom_fields = {k: v for k, v in row.items() if k not in standard_fields and v}

                    # Check if route already exists in this feed
                    existing = await db.execute(
                        select(Route).where(
                            Route.feed_id == feed_id,
                            Route.route_id == row['route_id']
                        )
                    )
                    route = existing.scalar_one_or_none()

                    if route:
                        # Update existing
                        route.agency_id = agency_id  # Set agency_id from feed
                        route.route_short_name = row.get('route_short_name', '')
                        route.route_long_name = row.get('route_long_name', '')
                        route.route_desc = row.get('route_desc')
                        route.route_type = GTFSService._safe_int(row.get('route_type'), 0)
                        route.route_url = row.get('route_url')
                        route.route_color = row.get('route_color')
                        route.route_text_color = row.get('route_text_color')
                        route.route_sort_order = GTFSService._safe_int(row.get('route_sort_order')) if row.get('route_sort_order') else None
                        route.custom_fields = custom_fields if custom_fields else None
                        updated += 1
                    else:
                        # Create new
                        route = Route(
                            feed_id=feed_id,
                            agency_id=agency_id,  # Set agency_id from feed
                            route_id=row['route_id'],
                            route_short_name=row.get('route_short_name', ''),
                            route_long_name=row.get('route_long_name', ''),
                            route_desc=row.get('route_desc'),
                            route_type=GTFSService._safe_int(row.get('route_type'), 0),
                            route_url=row.get('route_url'),
                            route_color=row.get('route_color'),
                            route_text_color=row.get('route_text_color'),
                            route_sort_order=GTFSService._safe_int(row.get('route_sort_order')) if row.get('route_sort_order') else None,
                            custom_fields=custom_fields if custom_fields else None,
                        )
                        db.add(route)
                        imported += 1
                except Exception as e:
                    print(f"[GTFS IMPORT] Error importing route row {row.get('route_id', 'unknown')}: {str(e)}")
                    errors += 1

        except Exception as e:
            print(f"[GTFS IMPORT] Error reading routes.txt: {str(e)}")
            errors += 1

        return GTFSFileStats(
            filename="routes.txt",
            imported=imported,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    @staticmethod
    async def _import_stops(
        zf: zipfile.ZipFile,
        feed_id: int,
        db: AsyncSession,
    ) -> GTFSFileStats:
        """Import stops.txt - OPTIMIZED with pre-loading and bulk insert"""
        logger.warning(f"_import_stops CALLED for feed_id={feed_id}")
        imported = 0
        updated = 0
        skipped = 0
        errors = 0

        try:
            logger.warning("Reading stops.txt file...")
            content = zf.read("stops.txt").decode('utf-8-sig')
            logger.warning(f"stops.txt decoded, size={len(content)} bytes")
            reader = csv.DictReader(io.StringIO(content))
            logger.warning("CSV reader created")

            # OPTIMIZATION: Pre-load all existing stops into memory for fast lookup
            existing_stops = {}
            all_stops = await db.execute(
                select(Stop).where(Stop.feed_id == feed_id)
            )
            for stop in all_stops.scalars():
                existing_stops[stop.stop_id] = stop

            print(f"[GTFS IMPORT] Loaded {len(existing_stops)} existing stops into memory")

            # Standard GTFS stop fields
            standard_fields = {
                'stop_id', 'stop_code', 'stop_name', 'stop_desc', 'stop_lat', 'stop_lon',
                'zone_id', 'stop_url', 'location_type', 'parent_station', 'stop_timezone',
                'wheelchair_boarding'
            }

            # Batch new records for bulk insert
            new_stops = []
            row_count = 0

            for row in reader:
                row_count += 1
                try:
                    # Extract custom fields (any field not in standard GTFS spec)
                    custom_fields = {k: v for k, v in row.items() if k not in standard_fields and v}

                    if row_count <= 3:  # Log first 3 rows for debugging
                        logger.warning(f"Processing stop {row_count}: stop_id={row.get('stop_id')}, custom_fields={custom_fields}")

                    # O(1) lookup in memory instead of database query
                    stop_id = row['stop_id']
                    stop = existing_stops.get(stop_id)

                    if stop:
                        # Update existing
                        stop.stop_code = row.get('stop_code') or None
                        stop.stop_name = row['stop_name']
                        stop.stop_desc = row.get('stop_desc') or None
                        stop.stop_lat = float(row['stop_lat'])
                        stop.stop_lon = float(row['stop_lon'])
                        stop.zone_id = row.get('zone_id') or None
                        stop.stop_url = row.get('stop_url') or None
                        stop.location_type = GTFSService._safe_int(row.get('location_type'), 0)
                        stop.parent_station = row.get('parent_station') or None
                        stop.wheelchair_boarding = GTFSService._safe_int(row.get('wheelchair_boarding'), 0)
                        stop.custom_fields = custom_fields if custom_fields else None
                        updated += 1
                    else:
                        # Queue for bulk insert - store as dict for Core insert
                        new_stops.append({
                            'feed_id': feed_id,
                            'stop_id': stop_id,
                            'stop_code': row.get('stop_code') or None,
                            'stop_name': row['stop_name'],
                            'stop_desc': row.get('stop_desc') or None,
                            'stop_lat': float(row['stop_lat']),
                            'stop_lon': float(row['stop_lon']),
                            'zone_id': row.get('zone_id') or None,
                            'stop_url': row.get('stop_url') or None,
                            'location_type': GTFSService._safe_int(row.get('location_type'), 0),
                            'parent_station': row.get('parent_station') or None,
                            'wheelchair_boarding': GTFSService._safe_int(row.get('wheelchair_boarding'), 0),
                            'custom_fields': custom_fields if custom_fields else None,
                        })
                        imported += 1

                    # Bulk insert every N records using Core insert (true bulk)
                    if len(new_stops) >= GTFSService.BULK_INSERT_BATCH_SIZE:
                        await db.execute(
                            Stop.__table__.insert(),
                            new_stops
                        )
                        await db.flush()
                        print(f"[GTFS IMPORT] Bulk inserted {len(new_stops)} stops (progress: {row_count} rows)")
                        new_stops = []

                except Exception as e:
                    logger.error(f"Error importing stop row {row.get('stop_id', 'unknown')}: {str(e)}", exc_info=True)
                    errors += 1

            # Insert any remaining records using Core insert (true bulk)
            if new_stops:
                await db.execute(
                    Stop.__table__.insert(),
                    new_stops
                )
                await db.flush()
                print(f"[GTFS IMPORT] Final bulk insert of {len(new_stops)} stops")

            logger.warning(f"Stops import complete: {row_count} rows processed, {imported} imported, {updated} updated, {errors} errors")

        except Exception as e:
            logger.error(f"Error reading stops.txt: {str(e)}", exc_info=True)
            traceback.print_exc()
            errors += 1

        return GTFSFileStats(
            filename="stops.txt",
            imported=imported,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    @staticmethod
    async def _import_calendar(
        zf: zipfile.ZipFile,
        feed_id: int,
        db: AsyncSession,
    ) -> GTFSFileStats:
        """Import calendar.txt"""
        imported = 0
        updated = 0
        skipped = 0
        errors = 0

        try:
            content = zf.read("calendar.txt").decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))

            # Standard GTFS calendar fields
            standard_fields = {
                'service_id', 'monday', 'tuesday', 'wednesday', 'thursday',
                'friday', 'saturday', 'sunday', 'start_date', 'end_date'
            }

            for row in reader:
                try:
                    # Extract custom fields (any field not in standard GTFS spec)
                    custom_fields = {k: v for k, v in row.items() if k not in standard_fields and v}

                    # Check if calendar already exists in this feed
                    existing = await db.execute(
                        select(Calendar).where(
                            Calendar.feed_id == feed_id,
                            Calendar.service_id == row['service_id']
                        )
                    )
                    calendar = existing.scalar_one_or_none()

                    if calendar:
                        # Update existing
                        calendar.monday = bool(GTFSService._safe_int(row.get('monday'), 0))
                        calendar.tuesday = bool(GTFSService._safe_int(row.get('tuesday'), 0))
                        calendar.wednesday = bool(GTFSService._safe_int(row.get('wednesday'), 0))
                        calendar.thursday = bool(GTFSService._safe_int(row.get('thursday'), 0))
                        calendar.friday = bool(GTFSService._safe_int(row.get('friday'), 0))
                        calendar.saturday = bool(GTFSService._safe_int(row.get('saturday'), 0))
                        calendar.sunday = bool(GTFSService._safe_int(row.get('sunday'), 0))
                        calendar.start_date = row['start_date']
                        calendar.end_date = row['end_date']
                        calendar.custom_fields = custom_fields if custom_fields else None
                        updated += 1
                    else:
                        # Create new
                        calendar = Calendar(
                            feed_id=feed_id,
                            service_id=row['service_id'],
                            monday=bool(GTFSService._safe_int(row.get('monday'), 0)),
                            tuesday=bool(GTFSService._safe_int(row.get('tuesday'), 0)),
                            wednesday=bool(GTFSService._safe_int(row.get('wednesday'), 0)),
                            thursday=bool(GTFSService._safe_int(row.get('thursday'), 0)),
                            friday=bool(GTFSService._safe_int(row.get('friday'), 0)),
                            saturday=bool(GTFSService._safe_int(row.get('saturday'), 0)),
                            sunday=bool(GTFSService._safe_int(row.get('sunday'), 0)),
                            start_date=row['start_date'],
                            end_date=row['end_date'],
                            custom_fields=custom_fields if custom_fields else None,
                        )
                        db.add(calendar)
                        imported += 1
                except Exception as e:
                    print(f"[GTFS IMPORT] Error importing calendar row {row.get('service_id', 'unknown')}: {str(e)}")
                    errors += 1

        except Exception as e:
            print(f"[GTFS IMPORT] Error reading calendar.txt: {str(e)}")
            errors += 1

        return GTFSFileStats(
            filename="calendar.txt",
            imported=imported,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    @staticmethod
    async def _import_trips(
        zf: zipfile.ZipFile,
        feed_id: int,
        db: AsyncSession,
    ) -> GTFSFileStats:
        """Import trips.txt"""
        imported = 0
        updated = 0
        skipped = 0
        errors = 0

        try:
            content = zf.read("trips.txt").decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))

            # With composite keys, we just need to validate that routes/services/shapes exist
            # No need to map to auto-increment IDs - we use the GTFS IDs directly

            # Build sets of valid GTFS IDs within this feed for validation
            valid_route_ids = set()
            routes_result = await db.execute(
                select(Route.route_id).where(Route.feed_id == feed_id)
            )
            for (route_id,) in routes_result:
                valid_route_ids.add(route_id)

            valid_service_ids = set()
            # Get service_ids from calendar.txt
            services_result = await db.execute(
                select(Calendar.service_id).where(Calendar.feed_id == feed_id)
            )
            for (service_id,) in services_result:
                valid_service_ids.add(service_id)

            print(f"[GTFS IMPORT] Found {len(valid_service_ids)} service_ids for feed {feed_id}: {list(valid_service_ids)}")

            # Get valid shape_ids for validation
            valid_shape_ids = set()
            shapes_result = await db.execute(
                select(Shape.shape_id).where(Shape.feed_id == feed_id).distinct()
            )
            for (shape_id,) in shapes_result:
                valid_shape_ids.add(shape_id)

            print(f"[GTFS IMPORT] Found {len(valid_shape_ids)} valid shape_ids for feed {feed_id}")
            if len(valid_shape_ids) <= 10:
                print(f"[GTFS IMPORT] Shape IDs: {list(valid_shape_ids)}")

            # OPTIMIZATION: Pre-load all existing trips into memory for fast lookup
            existing_trips = {}
            all_trips = await db.execute(
                select(Trip).where(Trip.feed_id == feed_id)
            )
            for trip in all_trips.scalars():
                existing_trips[trip.trip_id] = trip

            print(f"[GTFS IMPORT] Loaded {len(existing_trips)} existing trips into memory")

            # Track missing references for debugging
            missing_services = set()
            missing_routes = set()
            missing_shapes = set()

            # Standard GTFS trip fields
            standard_fields = {
                'route_id', 'service_id', 'trip_id', 'trip_headsign', 'trip_short_name',
                'direction_id', 'block_id', 'shape_id', 'wheelchair_accessible', 'bikes_allowed'
            }

            # Batch new records for bulk insert
            new_trips = []
            row_count = 0

            for row in reader:
                row_count += 1
                try:
                    # Extract custom fields (any field not in standard GTFS spec)
                    custom_fields = {k: v for k, v in row.items() if k not in standard_fields and v}

                    # With composite keys, we use GTFS IDs directly (no mapping needed)
                    route_id = row['route_id']
                    service_id = row['service_id']

                    # Validate that referenced entities exist
                    if route_id not in valid_route_ids or service_id not in valid_service_ids:
                        if route_id not in valid_route_ids:
                            missing_routes.add(route_id)
                        if service_id not in valid_service_ids:
                            missing_services.add(service_id)
                        skipped += 1
                        continue

                    # O(1) lookup in memory instead of database query
                    trip_id = row['trip_id']
                    trip = existing_trips.get(trip_id)

                    # Get shape_id (just the GTFS string, no DB mapping needed)
                    shape_id = row.get('shape_id') or None
                    if shape_id and shape_id not in valid_shape_ids:
                        # Shape doesn't exist, track it and set to None
                        missing_shapes.add(shape_id)
                        shape_id = None

                    if trip:
                        # Update existing
                        trip.route_id = route_id
                        trip.service_id = service_id
                        trip.trip_headsign = row.get('trip_headsign')
                        trip.trip_short_name = row.get('trip_short_name')
                        trip.direction_id = int(row['direction_id']) if row.get('direction_id') else None
                        trip.block_id = row.get('block_id')
                        trip.shape_id = shape_id
                        trip.wheelchair_accessible = int(row.get('wheelchair_accessible', 0))
                        trip.bikes_allowed = int(row.get('bikes_allowed', 0))
                        trip.custom_fields = custom_fields if custom_fields else None
                        updated += 1
                    else:
                        # Queue for bulk insert - store as dict for Core insert
                        new_trips.append({
                            'feed_id': feed_id,
                            'route_id': route_id,
                            'service_id': service_id,
                            'trip_id': trip_id,
                            'trip_headsign': row.get('trip_headsign'),
                            'trip_short_name': row.get('trip_short_name'),
                            'direction_id': int(row['direction_id']) if row.get('direction_id') else None,
                            'block_id': row.get('block_id'),
                            'shape_id': shape_id,
                            'wheelchair_accessible': int(row.get('wheelchair_accessible', 0)),
                            'bikes_allowed': int(row.get('bikes_allowed', 0)),
                            'custom_fields': custom_fields if custom_fields else None,
                        })
                        imported += 1

                    # Bulk insert every N records using Core insert (true bulk)
                    if len(new_trips) >= GTFSService.BULK_INSERT_BATCH_SIZE:
                        await db.execute(
                            Trip.__table__.insert(),
                            new_trips
                        )
                        await db.flush()
                        print(f"[GTFS IMPORT] Bulk inserted {len(new_trips)} trips (progress: {row_count} rows)")
                        new_trips = []

                except Exception as e:
                    print(f"[GTFS IMPORT] Error importing trip row {row.get('trip_id', 'unknown')}: {str(e)}")
                    errors += 1

            # Insert any remaining records using Core insert (true bulk)
            if new_trips:
                await db.execute(
                    Trip.__table__.insert(),
                    new_trips
                )
                await db.flush()
                print(f"[GTFS IMPORT] Final bulk insert of {len(new_trips)} trips")

            # Log missing references for debugging
            if missing_services:
                print(f"[GTFS IMPORT] Trips skipped due to missing service_ids: {sorted(missing_services)}")
            if missing_routes:
                print(f"[GTFS IMPORT] Trips skipped due to missing route_ids: {sorted(missing_routes)}")
            if missing_shapes:
                print(f"[GTFS IMPORT] WARNING: {len(missing_shapes)} trips had shape_ids not found in shapes table!")
                print(f"[GTFS IMPORT] Missing shape_ids (first 20): {sorted(missing_shapes)[:20]}")

        except Exception as e:
            print(f"[GTFS IMPORT] Error reading trips.txt: {str(e)}")
            errors += 1

        return GTFSFileStats(
            filename="trips.txt",
            imported=imported,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    @staticmethod
    async def _import_stop_times(
        zf: zipfile.ZipFile,
        feed_id: int,
        db: AsyncSession,
        progress_callback: callable = None,
    ) -> GTFSFileStats:
        """Import stop_times.txt using optimized bulk operations

        Args:
            zf: ZIP file containing GTFS data
            feed_id: Feed ID to import into
            db: Database session
            progress_callback: Optional callback(progress: float, message: str) for progress updates
                               Progress for stop_times is reported in range 45-85%
        """
        imported = 0
        updated = 0
        skipped = 0
        errors = 0

        try:
            content = zf.read("stop_times.txt").decode('utf-8-sig')

            # Count total lines for progress reporting (fast line count)
            total_lines = content.count('\n')
            print(f"[GTFS IMPORT] stop_times.txt has ~{total_lines} lines")

            reader = csv.DictReader(io.StringIO(content))

            # With composite keys, we just validate that trips/stops exist
            # No need to map to auto-increment IDs - we use GTFS IDs directly

            # Build sets of valid GTFS IDs within this feed for validation
            valid_trip_ids = set()
            trips_result = await db.execute(select(Trip.trip_id).where(Trip.feed_id == feed_id))
            for (trip_id,) in trips_result:
                valid_trip_ids.add(trip_id)

            valid_stop_ids = set()
            stops_result = await db.execute(select(Stop.stop_id).where(Stop.feed_id == feed_id))
            for (stop_id,) in stops_result:
                valid_stop_ids.add(stop_id)

            print(f"[GTFS IMPORT] Stop times import starting: {len(valid_trip_ids)} trips, {len(valid_stop_ids)} stops in database (feed_id={feed_id})")

            # Load existing stop_times for THIS FEED
            # With composite PK (feed_id, trip_id, stop_sequence)
            existing_stop_times = {}
            all_stop_times = await db.execute(
                select(StopTime).where(StopTime.feed_id == feed_id)
            )
            for st in all_stop_times.scalars():
                key = (st.trip_id, st.stop_sequence)  # trip_id is the GTFS ID string now
                existing_stop_times[key] = st

            print(f"[GTFS IMPORT] Loaded {len(existing_stop_times)} existing stop_times for feed {feed_id}")

            row_count = 0
            missing_trips = set()
            missing_stops = set()
            new_stop_times = []

            for row in reader:
                row_count += 1
                try:
                    # With composite keys, use GTFS IDs directly
                    trip_id = row['trip_id']
                    stop_id = row['stop_id']

                    # Validate that referenced entities exist
                    if trip_id not in valid_trip_ids or stop_id not in valid_stop_ids:
                        if trip_id not in valid_trip_ids:
                            missing_trips.add(trip_id)
                        if stop_id not in valid_stop_ids:
                            missing_stops.add(stop_id)
                        skipped += 1
                        continue

                    stop_sequence = int(row['stop_sequence'])
                    key = (trip_id, stop_sequence)

                    # Check in-memory map for existing stop_time
                    stop_time = existing_stop_times.get(key)

                    if stop_time:
                        # Update existing
                        stop_time.arrival_time = row['arrival_time']
                        stop_time.departure_time = row['departure_time']
                        stop_time.stop_id = stop_id
                        stop_time.stop_headsign = row.get('stop_headsign')
                        stop_time.pickup_type = int(row.get('pickup_type', 0))
                        stop_time.drop_off_type = int(row.get('drop_off_type', 0))
                        stop_time.shape_dist_traveled = float(row['shape_dist_traveled']) if row.get('shape_dist_traveled') else None
                        stop_time.timepoint = int(row.get('timepoint', 1))
                        updated += 1
                    else:
                        # Queue for bulk insert - store as dict for Core insert
                        # With composite PK: (feed_id, trip_id, stop_sequence)
                        new_stop_times.append({
                            'feed_id': feed_id,
                            'trip_id': trip_id,
                            'stop_id': stop_id,
                            'stop_sequence': stop_sequence,
                            'arrival_time': row['arrival_time'],
                            'departure_time': row['departure_time'],
                            'stop_headsign': row.get('stop_headsign'),
                            'pickup_type': int(row.get('pickup_type', 0)),
                            'drop_off_type': int(row.get('drop_off_type', 0)),
                            'shape_dist_traveled': float(row['shape_dist_traveled']) if row.get('shape_dist_traveled') else None,
                            'timepoint': int(row.get('timepoint', 1)),
                        })
                        imported += 1

                        # Bulk insert every N records using Core insert (true bulk)
                        if len(new_stop_times) >= GTFSService.BULK_INSERT_BATCH_SIZE:
                            await db.execute(
                                StopTime.__table__.insert(),
                                new_stop_times
                            )
                            await db.flush()

                            # Calculate and report progress (stop_times is 45-85%, 40% range)
                            if total_lines > 0 and progress_callback:
                                progress_pct = 45.0 + (row_count / total_lines) * 40.0
                                await progress_callback(
                                    min(84.0, progress_pct),
                                    f"Importing stop_times: {row_count:,} / ~{total_lines:,} rows"
                                )

                            print(f"[GTFS IMPORT] Bulk inserted {len(new_stop_times)} stop_times ({row_count:,}/{total_lines:,} rows, {row_count*100//max(1,total_lines)}%)")
                            new_stop_times = []

                except Exception as e:
                    print(f"[GTFS IMPORT] Error importing stop_time row (trip: {row.get('trip_id', 'unknown')}, seq: {row.get('stop_sequence', 'unknown')}): {str(e)}")
                    import traceback
                    traceback.print_exc()
                    errors += 1

            # Insert any remaining records using Core insert (true bulk)
            if new_stop_times:
                await db.execute(
                    StopTime.__table__.insert(),
                    new_stop_times
                )
                await db.flush()
                print(f"[GTFS IMPORT] Final bulk insert of {len(new_stop_times)} stop_times")

            # Log summary
            print(f"[GTFS IMPORT] Stop times import complete: {row_count} rows, {imported} imported, {updated} updated, {skipped} skipped, {errors} errors")
            if missing_stops:
                print(f"[GTFS IMPORT] Missing stop_ids (first 10): {list(missing_stops)[:10]}")
            if missing_trips:
                print(f"[GTFS IMPORT] Missing trip_ids (first 10): {list(missing_trips)[:10]}")

        except Exception as e:
            print(f"[GTFS IMPORT] Error reading stop_times.txt: {str(e)}")
            import traceback
            traceback.print_exc()
            errors += 1

        return GTFSFileStats(
            filename="stop_times.txt",
            imported=imported,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    @staticmethod
    async def _import_calendar_dates(
        zf: zipfile.ZipFile,
        feed_id: int,
        db: AsyncSession,
    ) -> GTFSFileStats:
        """Import calendar_dates.txt - OPTIMIZED with pre-loading and bulk insert

        If calendar.txt is empty, this will create Calendar entries for service_ids
        found in calendar_dates.txt (dates-only services).

        With composite keys, we use string service_id directly (no DB ID mapping).
        """
        imported = 0
        updated = 0
        skipped = 0
        errors = 0

        try:
            content = zf.read("calendar_dates.txt").decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))

            # With composite keys, we just need to validate that services exist
            # Build set of valid service_ids (string IDs, not DB IDs)
            valid_service_ids = set()
            services_result = await db.execute(
                select(Calendar.service_id).where(Calendar.feed_id == feed_id)
            )
            for (service_id,) in services_result:
                valid_service_ids.add(service_id)

            # OPTIMIZATION: Pre-load all existing calendar_dates into memory for fast lookup
            # CalendarDate has composite PK: (feed_id, service_id, date)
            existing_calendar_dates = {}
            all_calendar_dates = await db.execute(
                select(CalendarDate).where(CalendarDate.feed_id == feed_id)
            )
            for cd in all_calendar_dates.scalars():
                key = (cd.service_id, cd.date)  # Within feed, service_id + date is unique
                existing_calendar_dates[key] = cd

            print(f"[GTFS IMPORT] Loaded {len(existing_calendar_dates)} existing calendar_dates into memory")

            # Track service_ids we've created in this import
            created_services = set()

            # Batch new records for bulk insert
            new_calendar_dates = []
            row_count = 0

            for row in reader:
                row_count += 1
                try:
                    service_id_str = row['service_id']

                    # Auto-create Calendar entry if it doesn't exist
                    # This handles GTFS feeds with empty calendar.txt that use only calendar_dates.txt
                    if service_id_str not in valid_service_ids and service_id_str not in created_services:
                        # Create a minimal Calendar entry (all days False, dummy dates)
                        new_calendar = Calendar(
                            feed_id=feed_id,
                            service_id=service_id_str,
                            monday=False,
                            tuesday=False,
                            wednesday=False,
                            thursday=False,
                            friday=False,
                            saturday=False,
                            sunday=False,
                            start_date="19700101",  # Dummy date, actual dates come from calendar_dates
                            end_date="20991231",
                        )
                        db.add(new_calendar)
                        await db.flush()
                        valid_service_ids.add(service_id_str)
                        created_services.add(service_id_str)
                        print(f"[GTFS IMPORT] Auto-created Calendar entry for service_id '{service_id_str}' (dates-only service)")

                    if service_id_str not in valid_service_ids:
                        skipped += 1
                        continue

                    # O(1) lookup in memory instead of database query
                    date_str = row['date']
                    key = (service_id_str, date_str)
                    calendar_date = existing_calendar_dates.get(key)

                    if calendar_date:
                        # Update existing
                        calendar_date.exception_type = int(row['exception_type'])
                        updated += 1
                    else:
                        # Queue for bulk insert - use GTFS IDs directly
                        new_calendar_dates.append({
                            'feed_id': feed_id,  # Part of composite PK
                            'service_id': service_id_str,  # String GTFS ID, part of composite PK
                            'date': date_str,  # Part of composite PK
                            'exception_type': int(row['exception_type']),
                        })
                        imported += 1

                    # Bulk insert every N records using Core insert (true bulk)
                    if len(new_calendar_dates) >= GTFSService.BULK_INSERT_BATCH_SIZE:
                        await db.execute(
                            CalendarDate.__table__.insert(),
                            new_calendar_dates
                        )
                        await db.flush()
                        print(f"[GTFS IMPORT] Bulk inserted {len(new_calendar_dates)} calendar_dates (progress: {row_count} rows)")
                        new_calendar_dates = []

                except Exception as e:
                    print(f"[GTFS IMPORT] Error importing calendar_date row: {str(e)}")
                    errors += 1

            # Insert any remaining records using Core insert (true bulk)
            if new_calendar_dates:
                await db.execute(
                    CalendarDate.__table__.insert(),
                    new_calendar_dates
                )
                await db.flush()
                print(f"[GTFS IMPORT] Final bulk insert of {len(new_calendar_dates)} calendar_dates")

        except Exception as e:
            print(f"[GTFS IMPORT] Error reading calendar_dates.txt: {str(e)}")
            errors += 1

        return GTFSFileStats(
            filename="calendar_dates.txt",
            imported=imported,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    @staticmethod
    async def _import_shapes(
        zf: zipfile.ZipFile,
        feed_id: int,
        db: AsyncSession,
    ) -> GTFSFileStats:
        """Import shapes.txt - OPTIMIZED with pre-loading and bulk insert"""
        imported = 0
        updated = 0
        skipped = 0
        errors = 0

        try:
            content = zf.read("shapes.txt").decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))

            # OPTIMIZATION: Pre-load all existing shapes into memory for fast lookup
            # This eliminates N+1 queries (one SELECT per row)
            existing_shapes = {}
            all_shapes = await db.execute(
                select(Shape).where(Shape.feed_id == feed_id)
            )
            for shape in all_shapes.scalars():
                key = (shape.shape_id, shape.shape_pt_sequence)
                existing_shapes[key] = shape

            print(f"[GTFS IMPORT] Loaded {len(existing_shapes)} existing shape points into memory")

            # Batch new records for bulk insert
            new_shapes = []
            row_count = 0
            unique_shape_ids = set()  # Track unique shape_ids being imported

            for row in reader:
                row_count += 1
                try:
                    shape_id = row['shape_id']
                    unique_shape_ids.add(shape_id)  # Track for logging
                    shape_pt_sequence = int(row['shape_pt_sequence'])
                    key = (shape_id, shape_pt_sequence)

                    # O(1) lookup in memory instead of database query
                    shape = existing_shapes.get(key)

                    if shape:
                        # Update existing
                        shape.shape_pt_lat = float(row['shape_pt_lat'])
                        shape.shape_pt_lon = float(row['shape_pt_lon'])
                        shape.shape_dist_traveled = float(row['shape_dist_traveled']) if row.get('shape_dist_traveled') else None
                        updated += 1
                    else:
                        # Queue for bulk insert - store as dict for Core insert
                        new_shapes.append({
                            'feed_id': feed_id,
                            'shape_id': shape_id,
                            'shape_pt_lat': float(row['shape_pt_lat']),
                            'shape_pt_lon': float(row['shape_pt_lon']),
                            'shape_pt_sequence': shape_pt_sequence,
                            'shape_dist_traveled': float(row['shape_dist_traveled']) if row.get('shape_dist_traveled') else None,
                        })
                        imported += 1

                    # Bulk insert every N records using Core insert (true bulk)
                    if len(new_shapes) >= GTFSService.BULK_INSERT_BATCH_SIZE:
                        await db.execute(
                            Shape.__table__.insert(),
                            new_shapes
                        )
                        await db.flush()
                        print(f"[GTFS IMPORT] Bulk inserted {len(new_shapes)} shapes (progress: {row_count} rows)")
                        new_shapes = []

                except Exception as e:
                    print(f"[GTFS IMPORT] Error importing shape row (shape: {row.get('shape_id', 'unknown')}, seq: {row.get('shape_pt_sequence', 'unknown')}): {str(e)}")
                    errors += 1

            # Insert any remaining records using Core insert (true bulk)
            if new_shapes:
                await db.execute(
                    Shape.__table__.insert(),
                    new_shapes
                )
                await db.flush()
                print(f"[GTFS IMPORT] Final bulk insert of {len(new_shapes)} shapes")

            # Log summary
            print(f"[GTFS IMPORT] Shapes import complete: {row_count} points, {len(unique_shape_ids)} unique shape_ids, {imported} imported, {updated} updated")
            if len(unique_shape_ids) <= 20:
                print(f"[GTFS IMPORT] Shape IDs imported: {sorted(unique_shape_ids)}")

        except Exception as e:
            print(f"[GTFS IMPORT] Error reading shapes.txt: {str(e)}")
            errors += 1

        return GTFSFileStats(
            filename="shapes.txt",
            imported=imported,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    @staticmethod
    async def _import_fare_attributes(
        zf: zipfile.ZipFile,
        feed_id: int,
        db: AsyncSession,
    ) -> GTFSFileStats:
        """Import fare_attributes.txt"""
        imported = 0
        updated = 0
        skipped = 0
        errors = 0

        try:
            content = zf.read("fare_attributes.txt").decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))

            # Standard GTFS fare_attributes fields
            standard_fields = {
                'fare_id', 'price', 'currency_type', 'payment_method',
                'transfers', 'agency_id', 'transfer_duration'
            }

            for row in reader:
                try:
                    # Extract custom fields
                    custom_fields = {k: v for k, v in row.items() if k not in standard_fields and v}

                    # Check if fare already exists in this feed
                    existing = await db.execute(
                        select(FareAttribute).where(
                            FareAttribute.feed_id == feed_id,
                            FareAttribute.fare_id == row['fare_id']
                        )
                    )
                    fare = existing.scalar_one_or_none()

                    if fare:
                        # Update existing
                        fare.price = GTFSService._safe_decimal(row.get('price'), 0)
                        fare.currency_type = row.get('currency_type', 'USD')
                        fare.payment_method = GTFSService._safe_int(row.get('payment_method'), 0)
                        fare.transfers = GTFSService._safe_int(row.get('transfers'))
                        fare.agency_id = row.get('agency_id')
                        fare.transfer_duration = GTFSService._safe_int(row.get('transfer_duration'))
                        fare.custom_fields = custom_fields if custom_fields else None
                        updated += 1
                    else:
                        # Create new fare attribute
                        fare = FareAttribute(
                            feed_id=feed_id,
                            fare_id=row['fare_id'],
                            price=GTFSService._safe_decimal(row.get('price'), 0),
                            currency_type=row.get('currency_type', 'USD'),
                            payment_method=GTFSService._safe_int(row.get('payment_method'), 0),
                            transfers=GTFSService._safe_int(row.get('transfers')),
                            agency_id=row.get('agency_id'),
                            transfer_duration=GTFSService._safe_int(row.get('transfer_duration')),
                            custom_fields=custom_fields if custom_fields else None,
                        )
                        db.add(fare)
                        imported += 1

                except Exception as e:
                    print(f"[GTFS IMPORT] Error importing fare_attribute row: {str(e)}")
                    errors += 1

            await db.flush()

        except KeyError:
            # fare_attributes.txt not in ZIP - that's OK, it's optional
            pass
        except Exception as e:
            print(f"[GTFS IMPORT] Error reading fare_attributes.txt: {str(e)}")
            errors += 1

        return GTFSFileStats(
            filename="fare_attributes.txt",
            imported=imported,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    @staticmethod
    async def _import_fare_rules(
        zf: zipfile.ZipFile,
        feed_id: int,
        db: AsyncSession,
    ) -> GTFSFileStats:
        """Import fare_rules.txt - OPTIMIZED with bulk insert

        FareRule has a complex composite PK: (feed_id, fare_id, route_id, origin_id, destination_id, contains_id)
        """
        imported = 0
        updated = 0
        skipped = 0
        errors = 0

        try:
            content = zf.read("fare_rules.txt").decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))

            # Standard GTFS fare_rules fields
            standard_fields = {
                'fare_id', 'route_id', 'origin_id', 'destination_id', 'contains_id'
            }

            # Pre-load existing fare_rules for this feed
            existing_fare_rules = {}
            all_fare_rules = await db.execute(
                select(FareRule).where(FareRule.feed_id == feed_id)
            )
            for fr in all_fare_rules.scalars():
                key = (fr.fare_id, fr.route_id, fr.origin_id, fr.destination_id, fr.contains_id)
                existing_fare_rules[key] = fr

            print(f"[GTFS IMPORT] Loaded {len(existing_fare_rules)} existing fare_rules into memory")

            # Batch new records for bulk insert
            new_fare_rules = []
            row_count = 0

            for row in reader:
                row_count += 1
                try:
                    # Extract custom fields
                    custom_fields = {k: v for k, v in row.items() if k not in standard_fields and v}

                    # Get fields (use empty string as default for optional fields per GTFS spec)
                    fare_id = row.get('fare_id', '')
                    route_id = row.get('route_id', '')
                    origin_id = row.get('origin_id', '')
                    destination_id = row.get('destination_id', '')
                    contains_id = row.get('contains_id', '')

                    # Create lookup key
                    key = (fare_id, route_id, origin_id, destination_id, contains_id)

                    # Check if this exact fare rule already exists
                    fare_rule = existing_fare_rules.get(key)

                    if fare_rule:
                        # Update existing (though fare rules usually don't change)
                        fare_rule.custom_fields = custom_fields if custom_fields else None
                        updated += 1
                    else:
                        # Queue for bulk insert
                        new_fare_rules.append({
                            'feed_id': feed_id,
                            'fare_id': fare_id,
                            'route_id': route_id,
                            'origin_id': origin_id,
                            'destination_id': destination_id,
                            'contains_id': contains_id,
                            'custom_fields': custom_fields if custom_fields else None,
                        })
                        imported += 1

                    # Bulk insert every N records
                    if len(new_fare_rules) >= GTFSService.BULK_INSERT_BATCH_SIZE:
                        await db.execute(
                            FareRule.__table__.insert(),
                            new_fare_rules
                        )
                        await db.flush()
                        print(f"[GTFS IMPORT] Bulk inserted {len(new_fare_rules)} fare_rules (progress: {row_count} rows)")
                        new_fare_rules = []

                except Exception as e:
                    print(f"[GTFS IMPORT] Error importing fare_rule row: {str(e)}")
                    errors += 1

            # Insert any remaining records
            if new_fare_rules:
                await db.execute(
                    FareRule.__table__.insert(),
                    new_fare_rules
                )
                await db.flush()
                print(f"[GTFS IMPORT] Final bulk insert of {len(new_fare_rules)} fare_rules")

        except KeyError:
            # fare_rules.txt not in ZIP - that's OK, it's optional
            pass
        except Exception as e:
            print(f"[GTFS IMPORT] Error reading fare_rules.txt: {str(e)}")
            errors += 1

        return GTFSFileStats(
            filename="fare_rules.txt",
            imported=imported,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    @staticmethod
    async def _import_feed_info(
        zf: zipfile.ZipFile,
        feed_id: int,
        db: AsyncSession,
    ) -> GTFSFileStats:
        """Import feed_info.txt"""
        imported = 0
        updated = 0
        skipped = 0
        errors = 0

        try:
            content = zf.read("feed_info.txt").decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))

            # Standard GTFS feed_info fields
            standard_fields = {
                'feed_publisher_name', 'feed_publisher_url', 'feed_lang',
                'default_lang', 'feed_start_date', 'feed_end_date',
                'feed_version', 'feed_contact_email', 'feed_contact_url'
            }

            for row in reader:
                try:
                    # Extract custom fields
                    custom_fields = {k: v for k, v in row.items() if k not in standard_fields and v}

                    # Check if feed_info already exists for this feed (should be only one)
                    existing = await db.execute(
                        select(FeedInfo).where(FeedInfo.feed_id == feed_id)
                    )
                    feed_info = existing.scalar_one_or_none()

                    if feed_info:
                        # Update existing
                        feed_info.feed_publisher_name = row.get('feed_publisher_name', '')
                        feed_info.feed_publisher_url = row.get('feed_publisher_url', '')
                        feed_info.feed_lang = row.get('feed_lang', 'en')
                        feed_info.default_lang = row.get('default_lang')
                        feed_info.feed_start_date = row.get('feed_start_date')
                        feed_info.feed_end_date = row.get('feed_end_date')
                        feed_info.feed_version = row.get('feed_version')
                        feed_info.feed_contact_email = row.get('feed_contact_email')
                        feed_info.feed_contact_url = row.get('feed_contact_url')
                        feed_info.custom_fields = custom_fields if custom_fields else None
                        updated += 1
                    else:
                        # Create new feed info
                        feed_info = FeedInfo(
                            feed_id=feed_id,
                            feed_publisher_name=row.get('feed_publisher_name', ''),
                            feed_publisher_url=row.get('feed_publisher_url', ''),
                            feed_lang=row.get('feed_lang', 'en'),
                            default_lang=row.get('default_lang'),
                            feed_start_date=row.get('feed_start_date'),
                            feed_end_date=row.get('feed_end_date'),
                            feed_version=row.get('feed_version'),
                            feed_contact_email=row.get('feed_contact_email'),
                            feed_contact_url=row.get('feed_contact_url'),
                            custom_fields=custom_fields if custom_fields else None,
                        )
                        db.add(feed_info)
                        imported += 1

                    # Only one feed_info row per feed
                    break

                except Exception as e:
                    print(f"[GTFS IMPORT] Error importing feed_info row: {str(e)}")
                    errors += 1

            await db.flush()

        except KeyError:
            # feed_info.txt not in ZIP - that's OK, it's optional
            pass
        except Exception as e:
            print(f"[GTFS IMPORT] Error reading feed_info.txt: {str(e)}")
            errors += 1

        return GTFSFileStats(
            filename="feed_info.txt",
            imported=imported,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    @staticmethod
    def _safe_decimal(value, default=None):
        """Safely convert a value to Decimal"""
        from decimal import Decimal, InvalidOperation
        if value is None or value == '':
            return default
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return default


# Singleton instance
gtfs_service = GTFSService()
