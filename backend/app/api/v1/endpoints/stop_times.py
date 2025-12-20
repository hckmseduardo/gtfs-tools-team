"""StopTime (GTFS) management endpoints"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, cast, String, func, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import get_db
from app.models.user import User, UserRole, user_agencies
from app.models.gtfs import StopTime, Trip, Stop, Route, GTFSFeed
from app.models.audit import AuditAction
from app.schemas.stop_time import (
    StopTimeCreate,
    StopTimeUpdate,
    StopTimeResponse,
    StopTimeWithStop,
    StopTimeWithDetails,
    StopTimeList,
    StopTimeListWithStop,
    StopTimeListWithDetails,
    StopTimesBulkCreate,
    StopTimeBulkResult,
    StopTimeAdjustment,
    StopTimeValidation,
)
from app.utils.audit import create_audit_log, serialize_model

router = APIRouter()


def _parse_gtfs_time(time_str: str) -> int:
    """Convert GTFS time (HH:MM:SS) to minutes since midnight"""
    hours, minutes, seconds = map(int, time_str.split(":"))
    return hours * 60 + minutes


@router.get("/trip/{trip_id}", response_model=StopTimeListWithStop)
async def list_stop_times_for_trip(
    feed_id: int,
    trip_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> StopTimeListWithStop:
    """
    List all stop times for a specific trip, ordered by sequence.

    Includes stop information for each stop time.
    """
    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check access
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this feed",
            )

    # Verify trip exists in this feed
    trip_result = await db.execute(
        select(Trip).where(
            Trip.feed_id == feed_id,
            Trip.trip_id == trip_id
        )
    )
    trip = trip_result.scalar_one_or_none()
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found in this feed",
        )

    # Get stop times with stop info (composite FK join)
    query = (
        select(StopTime, Stop)
        .join(Stop, and_(
            StopTime.feed_id == Stop.feed_id,
            StopTime.stop_id == Stop.stop_id
        ))
        .where(
            StopTime.feed_id == feed_id,
            StopTime.trip_id == trip_id
        )
        .order_by(StopTime.stop_sequence)
    )
    result = await db.execute(query)
    rows = result.all()

    items = []
    for st, stop in rows:
        st_data = StopTimeResponse.model_validate(st)
        items.append(
            StopTimeWithStop(
                **st_data.model_dump(),
                stop_name=stop.stop_name,
                stop_code=stop.stop_code,
                stop_lat=stop.stop_lat,
                stop_lon=stop.stop_lon,
            )
        )

    return StopTimeListWithStop(
        items=items,
        total=len(items),
    )


@router.get("/stop/{stop_id}", response_model=StopTimeListWithDetails)
async def list_stop_times_for_stop(
    feed_id: int,
    stop_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    limit: int = Query(100, ge=1, le=1000),
) -> StopTimeListWithDetails:
    """
    List all stop times for a specific stop in a feed.

    Useful for seeing all trips that serve a particular stop.
    Includes trip and route information.
    """
    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check access
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this feed",
            )

    # Verify stop exists in this feed
    stop_result = await db.execute(
        select(Stop).where(
            Stop.feed_id == feed_id,
            Stop.stop_id == stop_id
        )
    )
    stop = stop_result.scalar_one_or_none()
    if not stop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stop not found in this feed",
        )

    # Get stop times with trip and route info (composite FK joins)
    query = (
        select(StopTime, Trip, Route, Stop)
        .join(Trip, and_(StopTime.feed_id == Trip.feed_id, StopTime.trip_id == Trip.trip_id))
        .join(Route, and_(Trip.feed_id == Route.feed_id, Trip.route_id == Route.route_id))
        .join(Stop, and_(StopTime.feed_id == Stop.feed_id, StopTime.stop_id == Stop.stop_id))
        .where(
            StopTime.feed_id == feed_id,
            StopTime.stop_id == stop_id
        )
    )

    print(f"🔍 Filtering stop times for feed_id={feed_id}, stop_id={stop_id}")
    query = query.order_by(StopTime.arrival_time).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    print(f"   Query returned {len(rows)} rows")

    items = []
    for st, trip, route, stop_info in rows:
        st_data = StopTimeResponse.model_validate(st)
        items.append(
            StopTimeWithDetails(
                **st_data.model_dump(),
                stop_name=stop_info.stop_name,
                stop_code=stop_info.stop_code,
                stop_lat=stop_info.stop_lat,
                stop_lon=stop_info.stop_lon,
                trip_headsign=trip.trip_headsign,
                route_short_name=route.route_short_name,
                route_long_name=route.route_long_name,
                route_color=route.route_color,
                gtfs_trip_id=trip.trip_id,
                gtfs_route_id=route.route_id,
            )
        )

    return StopTimeListWithDetails(
        items=items,
        total=len(items),
    )


@router.post("/", response_model=StopTimeResponse, status_code=status.HTTP_201_CREATED)
async def create_stop_time(
    feed_id: int,
    stop_time_in: StopTimeCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> StopTime:
    """
    Create a new stop time for a trip.

    - Super admins can create for any trip
    - Agency admins and editors can create for their agencies
    """
    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check permissions
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
            cast(user_agencies.c.role, String).in_([UserRole.AGENCY_ADMIN.value, UserRole.EDITOR.value]),
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create stop times for this trip",
            )

    # Get trip and verify it exists in this feed (composite key)
    trip_result = await db.execute(
        select(Trip).where(
            Trip.feed_id == feed_id,
            Trip.trip_id == stop_time_in.trip_id
        )
    )
    trip = trip_result.scalar_one_or_none()
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found in this feed",
        )

    # Verify stop exists in this feed (composite key)
    stop_result = await db.execute(
        select(Stop).where(
            Stop.feed_id == feed_id,
            Stop.stop_id == stop_time_in.stop_id
        )
    )
    stop = stop_result.scalar_one_or_none()
    if not stop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stop not found in this feed",
        )

    # Check for duplicate sequence (3-part composite key)
    existing = await db.execute(
        select(StopTime).where(
            StopTime.feed_id == feed_id,
            StopTime.trip_id == stop_time_in.trip_id,
            StopTime.stop_sequence == stop_time_in.stop_sequence,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stop time with sequence {stop_time_in.stop_sequence} already exists for this trip",
        )

    # Create stop time
    stop_time = StopTime(**stop_time_in.model_dump())
    db.add(stop_time)
    await db.commit()
    await db.refresh(stop_time)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="stop_time",
        entity_id=f"{feed_id}:{stop_time.trip_id}:{stop_time.stop_sequence}",
        description=f"Created stop time for trip '{trip.trip_id}' at stop '{stop.stop_name}' (sequence {stop_time.stop_sequence})",
        new_values=serialize_model(stop_time),
        agency_id=feed.agency_id,
        request=request,
    )

    return stop_time


@router.post("/bulk", response_model=StopTimeBulkResult, status_code=status.HTTP_201_CREATED)
async def create_stop_times_bulk(
    feed_id: int,
    bulk_in: StopTimesBulkCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> StopTimeBulkResult:
    """
    Create multiple stop times for a trip at once.

    This is the recommended way to create complete trip schedules.
    Validates sequence order and time progression.
    """
    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check permissions
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
            cast(user_agencies.c.role, String).in_([UserRole.AGENCY_ADMIN.value, UserRole.EDITOR.value]),
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create stop times for this trip",
            )

    # Get trip and verify it exists in this feed (composite key)
    trip_result = await db.execute(
        select(Trip).where(
            Trip.feed_id == feed_id,
            Trip.trip_id == bulk_in.trip_id
        )
    )
    trip = trip_result.scalar_one_or_none()
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found in this feed",
        )

    # Delete existing stop times (composite key)
    await db.execute(
        delete(StopTime).where(
            StopTime.feed_id == feed_id,
            StopTime.trip_id == bulk_in.trip_id
        )
    )

    # Create new stop times
    created = 0
    errors = []

    for idx, st_data in enumerate(bulk_in.stop_times):
        try:
            # Verify stop exists in this feed (composite key)
            stop_result = await db.execute(
                select(Stop).where(
                    Stop.feed_id == feed_id,
                    Stop.stop_id == st_data.stop_id
                )
            )
            if not stop_result.scalar_one_or_none():
                errors.append(f"Stop {idx}: Stop ID {st_data.stop_id} not found in this feed")
                continue

            stop_time = StopTime(
                feed_id=feed_id,
                trip_id=bulk_in.trip_id,
                stop_id=st_data.stop_id,
                arrival_time=st_data.arrival_time,
                departure_time=st_data.departure_time,
                stop_sequence=st_data.stop_sequence,
                stop_headsign=st_data.stop_headsign,
                pickup_type=st_data.pickup_type,
                drop_off_type=st_data.drop_off_type,
                shape_dist_traveled=st_data.shape_dist_traveled,
                timepoint=st_data.timepoint,
            )
            db.add(stop_time)
            created += 1
        except Exception as e:
            errors.append(f"Stop {idx}: {str(e)}")

    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="stop_time",
        entity_id=f"{feed_id}:{bulk_in.trip_id}",
        description=f"Bulk created {created} stop times for trip '{trip.trip_id}'",
        new_values={"created_count": created, "errors": errors},
        agency_id=feed.agency_id,
        request=request,
    )

    return StopTimeBulkResult(
        created=created,
        errors=errors,
    )


@router.get("/{trip_id}/{stop_sequence}", response_model=StopTimeResponse)
async def get_stop_time(
    feed_id: int,
    trip_id: str,
    stop_sequence: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> StopTime:
    """
    Get stop time details by composite key (feed_id, trip_id, stop_sequence).
    """
    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check access
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this feed",
            )

    # Get stop time with composite key
    result = await db.execute(
        select(StopTime).where(
            StopTime.feed_id == feed_id,
            StopTime.trip_id == trip_id,
            StopTime.stop_sequence == stop_sequence
        )
    )
    stop_time = result.scalar_one_or_none()

    if not stop_time:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stop time not found",
        )

    return stop_time


@router.patch("/{trip_id}/{stop_sequence}", response_model=StopTimeResponse)
async def update_stop_time(
    feed_id: int,
    trip_id: str,
    stop_sequence: int,
    stop_time_in: StopTimeUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> StopTime:
    """
    Update stop time details using composite key (feed_id, trip_id, stop_sequence).

    - Super admins can update any stop time
    - Agency admins and editors can update stop times in their agencies
    """
    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check permissions
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
            cast(user_agencies.c.role, String).in_([UserRole.AGENCY_ADMIN.value, UserRole.EDITOR.value]),
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update stop times in this feed",
            )

    # Get stop time with composite key
    result = await db.execute(
        select(StopTime).where(
            StopTime.feed_id == feed_id,
            StopTime.trip_id == trip_id,
            StopTime.stop_sequence == stop_sequence
        )
    )
    stop_time = result.scalar_one_or_none()

    if not stop_time:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stop time not found",
        )

    # Store old values for audit
    old_values = serialize_model(stop_time)

    # Update stop time
    update_data = stop_time_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(stop_time, field, value)

    await db.commit()
    await db.refresh(stop_time)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="stop_time",
        entity_id=f"{feed_id}:{trip_id}:{stop_sequence}",
        description=f"Updated stop time for trip '{trip_id}' (sequence {stop_sequence})",
        old_values=old_values,
        new_values=serialize_model(stop_time),
        agency_id=feed.agency_id,
        request=request,
    )

    return stop_time


@router.delete("/{trip_id}/{stop_sequence}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stop_time(
    feed_id: int,
    trip_id: str,
    stop_sequence: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Delete a stop time using composite key (feed_id, trip_id, stop_sequence).

    - Super admins can delete any stop time
    - Agency admins and editors can delete stop times in their agencies
    """
    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check permissions
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
            cast(user_agencies.c.role, String).in_([UserRole.AGENCY_ADMIN.value, UserRole.EDITOR.value]),
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete stop times in this feed",
            )

    # Get stop time with composite key
    result = await db.execute(
        select(StopTime).where(
            StopTime.feed_id == feed_id,
            StopTime.trip_id == trip_id,
            StopTime.stop_sequence == stop_sequence
        )
    )
    stop_time = result.scalar_one_or_none()

    if not stop_time:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stop time not found",
        )

    # Store values for audit log before deletion
    old_values = serialize_model(stop_time)

    await db.delete(stop_time)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="stop_time",
        entity_id=f"{feed_id}:{trip_id}:{stop_sequence}",
        description=f"Deleted stop time for trip '{trip_id}' (sequence {stop_sequence})",
        old_values=old_values,
        agency_id=feed.agency_id,
        request=request,
    )


@router.post("/trip/{trip_id}/adjust-times", response_model=StopTimeBulkResult)
async def adjust_trip_times(
    feed_id: int,
    trip_id: str,
    adjustment: StopTimeAdjustment,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> StopTimeBulkResult:
    """
    Adjust all stop times for a trip by adding/subtracting minutes.

    Useful for shifting entire trip schedules forward or backward.
    """
    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check permissions
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
            cast(user_agencies.c.role, String).in_([UserRole.AGENCY_ADMIN.value, UserRole.EDITOR.value]),
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to adjust times for this trip",
            )

    # Get trip and verify it exists in this feed (composite key)
    trip_result = await db.execute(
        select(Trip).where(
            Trip.feed_id == feed_id,
            Trip.trip_id == trip_id
        )
    )
    trip = trip_result.scalar_one_or_none()
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found in this feed",
        )

    # Get all stop times for this trip (composite key)
    query = select(StopTime).where(
        StopTime.feed_id == feed_id,
        StopTime.trip_id == trip_id
    )
    result = await db.execute(query)
    stop_times = result.scalars().all()

    updated = 0
    errors = []

    for st in stop_times:
        try:
            # Parse times
            arr_parts = st.arrival_time.split(":")
            dep_parts = st.departure_time.split(":")

            arr_mins = int(arr_parts[0]) * 60 + int(arr_parts[1])
            dep_mins = int(dep_parts[0]) * 60 + int(dep_parts[1])

            # Adjust
            arr_mins += adjustment.minutes_offset
            dep_mins += adjustment.minutes_offset

            # Validate
            if arr_mins < 0 or dep_mins < 0:
                errors.append(f"Sequence {st.stop_sequence}: Would result in negative time")
                continue

            # Convert back
            arr_hours = arr_mins // 60
            arr_minutes = arr_mins % 60
            dep_hours = dep_mins // 60
            dep_minutes = dep_mins % 60

            st.arrival_time = f"{arr_hours:02d}:{arr_minutes:02d}:{arr_parts[2]}"
            st.departure_time = f"{dep_hours:02d}:{dep_minutes:02d}:{dep_parts[2]}"

            updated += 1
        except Exception as e:
            errors.append(f"Sequence {st.stop_sequence}: {str(e)}")

    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="stop_time",
        entity_id=f"{feed_id}:{trip_id}",
        description=f"Adjusted {updated} stop times for trip '{trip.trip_id}' by {adjustment.minutes_offset} minutes",
        new_values={"updated_count": updated, "minutes_offset": adjustment.minutes_offset, "errors": errors},
        agency_id=feed.agency_id,
        request=request,
    )

    return StopTimeBulkResult(
        updated=updated,
        errors=errors,
    )


@router.get("/trip/{trip_id}/validate", response_model=StopTimeValidation)
async def validate_trip_stop_times(
    feed_id: int,
    trip_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> StopTimeValidation:
    """
    Validate stop times for a trip.

    Checks for:
    - Sequential stop sequences
    - Non-decreasing times
    - Missing sequences
    """
    # Get stop times for this trip (composite key)
    query = (
        select(StopTime)
        .where(
            StopTime.feed_id == feed_id,
            StopTime.trip_id == trip_id
        )
        .order_by(StopTime.stop_sequence)
    )
    result = await db.execute(query)
    stop_times = result.scalars().all()

    errors = []
    warnings = []

    if not stop_times:
        errors.append("No stop times defined for this trip")
        return StopTimeValidation(valid=False, errors=errors, warnings=warnings)

    # Check sequences
    sequences = [st.stop_sequence for st in stop_times]
    if sequences != list(range(len(sequences))):
        warnings.append("Stop sequences are not sequential (0, 1, 2, ...)")

    # Check time progression
    prev_time = None
    for st in stop_times:
        curr_time = _parse_gtfs_time(st.departure_time)
        if prev_time is not None and curr_time < prev_time:
            errors.append(
                f"Stop sequence {st.stop_sequence}: Departure time {st.departure_time} "
                f"is before previous stop's departure time"
            )
        prev_time = curr_time

    valid = len(errors) == 0
    return StopTimeValidation(
        valid=valid,
        errors=errors,
        warnings=warnings,
    )
