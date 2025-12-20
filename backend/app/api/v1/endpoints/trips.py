"""Trip (GTFS) management endpoints"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, cast, String, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import get_db
from app.models.user import User, UserRole, user_agencies
from app.models.agency import Agency
from app.models.audit import AuditAction
from app.models.gtfs import Trip, Route, Calendar, StopTime, Stop, GTFSFeed, Shape
from app.schemas.trip import (
    TripCreate,
    TripUpdate,
    TripResponse,
    TripWithRoute,
    TripWithDetails,
    TripWithStopTimes,
    TripList,
    TripListWithRoute,
    TripListWithDetails,
    TripStopTimeReference,
    TripCopy,
)
from app.utils.audit import create_audit_log, serialize_model

router = APIRouter()


@router.get("/", response_model=TripList)
async def list_trips(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=50000),
    route_id: Optional[str] = None,
    service_id: Optional[str] = None,
    direction_id: Optional[int] = Query(None, ge=0, le=1),
    search: Optional[str] = None,
) -> TripList:
    """
    List trips for a specific feed with pagination and filtering.

    - Super admins can see all trips
    - Other users see only trips from agencies they belong to
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

    # Build query for trips in this specific feed
    query = select(Trip).where(Trip.feed_id == feed_id)

    # Apply filters
    if route_id:
        query = query.where(Trip.route_id == route_id)

    if service_id:
        query = query.where(Trip.service_id == service_id)

    if direction_id is not None:
        query = query.where(Trip.direction_id == direction_id)

    if search:
        query = query.where(
            or_(
                Trip.trip_id.ilike(f"%{search}%"),
                Trip.trip_headsign.ilike(f"%{search}%"),
                Trip.trip_short_name.ilike(f"%{search}%"),
            )
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Trip.trip_id)
    result = await db.execute(query)
    trips = result.scalars().all()

    return TripList(
        items=[TripResponse.model_validate(trip) for trip in trips],
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.get("/with-routes", response_model=TripListWithRoute)
async def list_trips_with_routes(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=10000),
    route_id: Optional[str] = None,
) -> TripListWithRoute:
    """
    List trips with route information for a specific feed.
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

    # Build query with route join (composite FK)
    query = (
        select(Trip, Route, Trip.shape_id.label("gtfs_shape_id"))
        .join(Route, and_(Trip.feed_id == Route.feed_id, Trip.route_id == Route.route_id))
        .where(Trip.feed_id == feed_id)
    )

    if route_id:
        query = query.where(Trip.route_id == route_id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Trip.trip_id)
    result = await db.execute(query)
    rows = result.all()

    items = []
    for trip, route, gtfs_shape_id in rows:
        trip_data = TripResponse.model_validate(trip)
        items.append(
            TripWithRoute(
                **trip_data.model_dump(),
                gtfs_route_id=route.route_id,
                gtfs_shape_id=gtfs_shape_id,
                route_short_name=route.route_short_name,
                route_long_name=route.route_long_name,
                route_type=route.route_type,
                route_color=route.route_color,
            )
        )

    return TripListWithRoute(
        items=items,
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.get("/with-details", response_model=TripListWithDetails)
async def list_trips_with_details(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    route_id: Optional[str] = None,
) -> TripListWithDetails:
    """
    List trips with full details including stop counts and times for a specific feed.
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

    # Build query with route join (composite FK)
    query = (
        select(Trip, Route, Trip.shape_id.label("gtfs_shape_id"))
        .join(Route, and_(Trip.feed_id == Route.feed_id, Trip.route_id == Route.route_id))
        .where(Trip.feed_id == feed_id)
    )

    if route_id:
        query = query.where(Trip.route_id == route_id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Trip.trip_id)
    result = await db.execute(query)
    rows = result.all()

    # Get trip_ids (string) for fetching stop time stats
    trip_string_ids = [trip.trip_id for trip, _, _ in rows]

    # Get stop counts and time ranges using composite key
    stop_stats_query = (
        select(
            StopTime.trip_id,
            func.count().label("stop_count"),
            func.min(StopTime.departure_time).label("first_departure"),
            func.max(StopTime.arrival_time).label("last_arrival"),
        )
        .where(
            StopTime.feed_id == feed_id,
            StopTime.trip_id.in_(trip_string_ids)
        )
        .group_by(StopTime.trip_id)
    )
    stop_stats_result = await db.execute(stop_stats_query)
    stop_stats = {
        trip_id: (count, first_dep, last_arr)
        for trip_id, count, first_dep, last_arr in stop_stats_result.all()
    }

    items = []
    for trip, route, gtfs_shape_id in rows:
        trip_data = TripResponse.model_validate(trip)
        stats = stop_stats.get(trip.trip_id, (0, None, None))
        items.append(
            TripWithDetails(
                **trip_data.model_dump(),
                gtfs_route_id=route.route_id,
                gtfs_shape_id=gtfs_shape_id,
                route_short_name=route.route_short_name or "",
                route_long_name=route.route_long_name or "",
                route_type=route.route_type,
                route_color=route.route_color,
                stop_count=stats[0],
                first_departure=stats[1],
                last_arrival=stats[2],
            )
        )

    return TripListWithDetails(
        items=items,
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.post("/", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def create_trip(
    trip_in: TripCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Trip:
    """
    Create a new trip.

    - Super admins can create trips for any feed
    - Agency admins and editors can create trips for their agencies' feeds
    """
    # Verify feed exists and get its agency
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == trip_in.feed_id)
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
                detail="You don't have permission to create trips for this agency",
            )

    # Verify route exists in this feed (composite key)
    route_result = await db.execute(
        select(Route).where(
            Route.feed_id == trip_in.feed_id,
            Route.route_id == trip_in.route_id
        )
    )
    route = route_result.scalar_one_or_none()
    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route not found in this feed",
        )

    # Verify service exists in this feed (composite key)
    service_result = await db.execute(
        select(Calendar).where(
            Calendar.feed_id == trip_in.feed_id,
            Calendar.service_id == trip_in.service_id
        )
    )
    if not service_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service/Calendar not found in this feed",
        )

    # Check if trip_id already exists for this feed
    existing_trip = await db.execute(
        select(Trip).where(
            Trip.feed_id == trip_in.feed_id,
            Trip.trip_id == trip_in.trip_id,
        )
    )
    if existing_trip.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trip with trip_id '{trip_in.trip_id}' already exists for this feed",
        )

    # Create trip
    trip = Trip(**trip_in.model_dump())
    db.add(trip)
    await db.commit()
    await db.refresh(trip)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="trip",
        entity_id=f"{trip.feed_id}:{trip.trip_id}",
        description=f"Created trip '{trip.trip_id}' for route {route.route_short_name or route.route_long_name}",
        new_values=serialize_model(trip),
        agency_id=feed.agency_id,
        request=request,
    )

    return trip


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    feed_id: int,
    trip_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Trip:
    """
    Get trip details by composite key (feed_id, trip_id).
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

    # Get trip with composite key
    result = await db.execute(
        select(Trip).where(
            Trip.feed_id == feed_id,
            Trip.trip_id == trip_id
        )
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    return trip


@router.get("/{trip_id}/with-stop-times", response_model=TripWithStopTimes)
async def get_trip_with_stop_times(
    feed_id: int,
    trip_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> TripWithStopTimes:
    """
    Get trip with all stop times using composite key (feed_id, trip_id).
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

    # Get trip with route (composite FK join)
    result = await db.execute(
        select(Trip, Route)
        .join(Route, and_(Trip.feed_id == Route.feed_id, Trip.route_id == Route.route_id))
        .where(
            Trip.feed_id == feed_id,
            Trip.trip_id == trip_id
        )
    )
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    trip, route = row

    # Get stop times with stop info (composite FK joins)
    stop_times_query = (
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
    stop_times_result = await db.execute(stop_times_query)
    stop_times_rows = stop_times_result.all()

    stop_times = [
        TripStopTimeReference(
            stop_id=stop.stop_id,
            stop_name=stop.stop_name,
            stop_sequence=st.stop_sequence,
            arrival_time=st.arrival_time,
            departure_time=st.departure_time,
        )
        for st, stop in stop_times_rows
    ]

    trip_data = TripResponse.model_validate(trip)
    return TripWithStopTimes(
        **trip_data.model_dump(),
        route_short_name=route.route_short_name,
        route_long_name=route.route_long_name,
        route_type=route.route_type,
        route_color=route.route_color,
        stop_times=stop_times,
    )


@router.patch("/{trip_id}", response_model=TripResponse)
async def update_trip(
    feed_id: int,
    trip_id: str,
    trip_in: TripUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Trip:
    """
    Update trip details.

    - Super admins can update any trip
    - Agency admins and editors can update trips in their agencies
    """
    # Verify feed exists and get agency
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
                detail="You don't have permission to update trips in this feed",
            )

    # Get trip with composite key
    result = await db.execute(
        select(Trip).where(
            Trip.feed_id == feed_id,
            Trip.trip_id == trip_id
        )
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    # Verify route if being changed
    if trip_in.route_id and trip_in.route_id != trip.route_id:
        route_result = await db.execute(
            select(Route).where(
                Route.feed_id == feed_id,
                Route.route_id == trip_in.route_id
            )
        )
        route = route_result.scalar_one_or_none()
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Route not found in this feed",
            )

    # Check if trip_id is being changed and if it conflicts
    if trip_in.trip_id and trip_in.trip_id != trip.trip_id:
        existing_trip = await db.execute(
            select(Trip).where(
                Trip.feed_id == feed_id,
                Trip.trip_id == trip_in.trip_id,
            )
        )
        if existing_trip.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Trip with trip_id '{trip_in.trip_id}' already exists for this feed",
            )

    # Store old values for audit
    old_values = serialize_model(trip)

    # Update trip
    update_data = trip_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(trip, field, value)

    await db.commit()
    await db.refresh(trip)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="trip",
        entity_id=f"{trip.feed_id}:{trip.trip_id}",
        description=f"Updated trip '{trip.trip_id}'",
        old_values=old_values,
        new_values=serialize_model(trip),
        agency_id=feed.agency_id,
        request=request,
    )

    return trip


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(
    feed_id: int,
    trip_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Delete a trip.

    - Super admins can delete any trip
    - Agency admins can delete trips in their agencies
    - This will cascade delete all stop times for this trip
    """
    # Verify feed exists and get agency
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check permissions (only admins can delete)
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
            user_agencies.c.role == UserRole.AGENCY_ADMIN.value,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only agency admins can delete trips",
            )

    # Get trip with composite key
    result = await db.execute(
        select(Trip).where(
            Trip.feed_id == feed_id,
            Trip.trip_id == trip_id
        )
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    # Create audit log before deletion
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="trip",
        entity_id=f"{trip.feed_id}:{trip.trip_id}",
        description=f"Deleted trip '{trip.trip_id}'",
        old_values=serialize_model(trip),
        agency_id=feed.agency_id,
        request=request,
    )

    await db.delete(trip)
    await db.commit()


@router.post("/{trip_id}/copy", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def copy_trip(
    feed_id: int,
    trip_id: str,
    copy_params: TripCopy,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Trip:
    """
    Copy a trip (optionally with all stop times).

    Useful for creating similar trips with different IDs.
    """
    # Verify feed exists and get agency
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
                detail="You don't have permission to copy trips for this feed",
            )

    # Get original trip with composite key
    result = await db.execute(
        select(Trip).where(
            Trip.feed_id == feed_id,
            Trip.trip_id == trip_id
        )
    )
    original_trip = result.scalar_one_or_none()

    if not original_trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found",
        )

    # Check if new trip_id already exists
    existing_trip = await db.execute(
        select(Trip).where(
            Trip.feed_id == feed_id,
            Trip.trip_id == copy_params.new_trip_id,
        )
    )
    if existing_trip.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trip with trip_id '{copy_params.new_trip_id}' already exists",
        )

    # Create new trip
    new_trip = Trip(
        feed_id=original_trip.feed_id,
        route_id=original_trip.route_id,
        service_id=original_trip.service_id,
        trip_id=copy_params.new_trip_id,
        trip_headsign=original_trip.trip_headsign,
        trip_short_name=original_trip.trip_short_name,
        direction_id=original_trip.direction_id,
        block_id=original_trip.block_id,
        shape_id=original_trip.shape_id,
        wheelchair_accessible=original_trip.wheelchair_accessible,
        bikes_allowed=original_trip.bikes_allowed,
    )
    db.add(new_trip)
    await db.flush()  # Ensure trip is persisted before copying stop times

    # Copy stop times if requested
    if copy_params.copy_stop_times:
        stop_times_result = await db.execute(
            select(StopTime).where(
                StopTime.feed_id == feed_id,
                StopTime.trip_id == trip_id
            ).order_by(StopTime.stop_sequence)
        )
        original_stop_times = stop_times_result.scalars().all()

        for st in original_stop_times:
            new_stop_time = StopTime(
                feed_id=new_trip.feed_id,
                trip_id=new_trip.trip_id,
                arrival_time=st.arrival_time,
                departure_time=st.departure_time,
                stop_id=st.stop_id,
                stop_sequence=st.stop_sequence,
                stop_headsign=st.stop_headsign,
                pickup_type=st.pickup_type,
                drop_off_type=st.drop_off_type,
                shape_dist_traveled=st.shape_dist_traveled,
                timepoint=st.timepoint,
            )
            db.add(new_stop_time)

    await db.commit()
    await db.refresh(new_trip)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="trip",
        entity_id=f"{new_trip.feed_id}:{new_trip.trip_id}",
        description=f"Copied trip '{original_trip.trip_id}' to new trip '{new_trip.trip_id}'" + (" (with stop times)" if copy_params.copy_stop_times else ""),
        old_values={"source_trip": f"{original_trip.feed_id}:{original_trip.trip_id}"},
        new_values=serialize_model(new_trip),
        agency_id=feed.agency_id,
        request=request,
    )

    return new_trip
