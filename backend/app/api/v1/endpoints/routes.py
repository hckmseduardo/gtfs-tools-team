"""Route (GTFS) management endpoints"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, cast, String, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import get_db
from app.models.user import User, UserRole, user_agencies
from app.models.agency import Agency
from app.models.gtfs import Route, Trip, GTFSFeed
from app.models.audit import AuditAction
from app.schemas.route import (
    RouteCreate,
    RouteUpdate,
    RouteResponse,
    RouteWithStats,
    RouteList,
    RouteListWithStats,
)
from app.utils.audit import create_audit_log, serialize_model

router = APIRouter()


@router.get("", response_model=RouteList)
async def list_routes(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=50000),
    route_type: Optional[int] = Query(None, ge=0, le=7),
    search: Optional[str] = None,
) -> RouteList:
    """
    List routes for a specific feed with pagination and filtering.

    - Super admins can see all routes
    - Other users see only routes from feeds in agencies they belong to
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

    # Check user access to the feed's agency
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

    # Build query for routes in this specific feed
    query = select(Route).where(Route.feed_id == feed_id)

    if route_type is not None:
        query = query.where(Route.route_type == route_type)

    if search:
        query = query.where(
            or_(
                Route.route_short_name.ilike(f"%{search}%"),
                Route.route_long_name.ilike(f"%{search}%"),
                Route.route_id.ilike(f"%{search}%"),
            )
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Route.route_short_name)
    result = await db.execute(query)
    routes = result.scalars().all()

    return RouteList(
        items=[RouteResponse.model_validate(route) for route in routes],
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.get("/stats", response_model=RouteListWithStats)
async def list_routes_with_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    agency_id: Optional[int] = None,
) -> RouteListWithStats:
    """
    List routes with statistics (trip counts).
    """
    # Build base query
    query = select(Route)

    # Filter by agency access through feeds
    if not current_user.is_superuser:
        user_agency_ids = select(user_agencies.c.agency_id).where(
            user_agencies.c.user_id == current_user.id
        )
        feed_ids_subquery = select(GTFSFeed.id).where(GTFSFeed.agency_id.in_(user_agency_ids))
        query = query.where(Route.feed_id.in_(feed_ids_subquery))

    if agency_id:
        # Verify user has access to this agency
        await deps.verify_agency_access(agency_id, db, current_user)
        feed_ids_subquery = select(GTFSFeed.id).where(GTFSFeed.agency_id == agency_id)
        query = query.where(Route.feed_id.in_(feed_ids_subquery))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Route.route_short_name)
    result = await db.execute(query)
    routes = result.scalars().all()

    # Get trip counts for each route
    route_ids = [route.id for route in routes]
    trip_counts_query = (
        select(Trip.route_id, func.count(Trip.trip_id))
        .where(Trip.route_id.in_(route_ids))
        .group_by(Trip.route_id)
    )
    trip_counts_result = await db.execute(trip_counts_query)
    trip_counts = dict(trip_counts_result.all())

    # Build response with stats
    items = []
    for route in routes:
        route_data = RouteResponse.model_validate(route)
        items.append(
            RouteWithStats(
                **route_data.model_dump(),
                trip_count=trip_counts.get(route.id, 0),
                active_trips=0,  # TODO: Implement active trips calculation
            )
        )

    return RouteListWithStats(
        items=items,
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.post("", response_model=RouteResponse, status_code=status.HTTP_201_CREATED)
async def create_route(
    feed_id: int,
    route_in: RouteCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Route:
    """
    Create a new route in a specific feed.

    - Super admins can create routes for any agency
    - Agency admins and editors can create routes for their agencies
    """
    # Verify feed exists
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check permissions through the feed's agency
    if not current_user.is_superuser:
        # Check if user is at least editor for this agency
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
            cast(user_agencies.c.role, String).in_([UserRole.AGENCY_ADMIN.value, UserRole.EDITOR.value]),
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create routes for this agency",
            )

    # Check if route_id already exists in this feed
    existing_route = await db.execute(
        select(Route).where(
            Route.feed_id == feed_id,
            Route.route_id == route_in.route_id,
        )
    )
    if existing_route.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Route with route_id '{route_in.route_id}' already exists in this feed",
        )

    # Create route
    route_data = route_in.model_dump(exclude={'agency_id'})
    route = Route(**route_data, feed_id=feed_id, agency_id=feed.agency_id)
    db.add(route)
    await db.commit()
    await db.refresh(route)

    # Create audit log with composite key format
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="route",
        entity_id=f"{route.feed_id}:{route.route_id}",
        description=f"Created route '{route.route_short_name or route.route_long_name}' ({route.route_id})",
        new_values=serialize_model(route),
        agency_id=feed.agency_id,
        request=request,
    )

    return route


@router.get("/route-stops-map", response_model=dict)
async def get_route_stops_map(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict:
    """
    Get a mapping of route_ids to their stop_ids.

    This is used for filtering stops on the map based on selected routes.
    The relationship is: Route -> Trip -> StopTimes -> Stop

    Returns:
        {
            "route_id_1": ["stop_id_1", "stop_id_2", ...],
            "route_id_2": ["stop_id_3", "stop_id_4", ...],
            ...
        }
    """
    from app.models.gtfs import StopTime

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

    # Check user access to the feed's agency
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id
        )
        membership_result = await db.execute(membership_query)
        if not membership_result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this feed",
            )

    # Query to get route_id -> stop_ids mapping
    # Join Route -> Trip -> StopTime to get the relationships
    query = (
        select(
            Trip.route_id,
            func.array_agg(func.distinct(StopTime.stop_id)).label('stop_ids')
        )
        .join(StopTime, (StopTime.feed_id == Trip.feed_id) & (StopTime.trip_id == Trip.trip_id))
        .where(Trip.feed_id == feed_id)
        .group_by(Trip.route_id)
    )

    result = await db.execute(query)
    rows = result.fetchall()

    # Build the mapping
    route_stops_map = {}
    for row in rows:
        route_stops_map[row.route_id] = list(row.stop_ids) if row.stop_ids else []

    return route_stops_map


@router.get("/{route_id}", response_model=RouteResponse)
async def get_route(
    feed_id: int,
    route_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Route:
    """
    Get route details by composite key (feed_id, route_id).
    """
    # Query with composite primary key
    result = await db.execute(
        select(Route).where(
            Route.feed_id == feed_id,
            Route.route_id == route_id
        )
    )
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route '{route_id}' not found in feed {feed_id}",
        )

    # Check access through the feed's agency
    if not current_user.is_superuser:
        # Get the feed to check agency_id
        feed_result = await db.execute(
            select(GTFSFeed).where(GTFSFeed.id == route.feed_id)
        )
        feed = feed_result.scalar_one_or_none()

        if not feed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feed not found",
            )

        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this route",
            )

    return route


@router.patch("/{route_id}", response_model=RouteResponse)
async def update_route(
    feed_id: int,
    route_id: str,
    route_in: RouteUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Route:
    """
    Update route details using composite key (feed_id, route_id).

    - Super admins can update any route
    - Agency admins and editors can update routes in their agencies
    """
    # Query with composite primary key
    result = await db.execute(
        select(Route).where(
            Route.feed_id == feed_id,
            Route.route_id == route_id
        )
    )
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route '{route_id}' not found in feed {feed_id}",
        )

    # Store old values for audit
    old_values = serialize_model(route)

    # Check permissions through the feed's agency
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == route.feed_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

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
                detail="You don't have permission to update this route",
            )

    # Check if route_id is being changed and if it conflicts
    if route_in.route_id and route_in.route_id != route.route_id:
        existing_route = await db.execute(
            select(Route).where(
                Route.feed_id == route.feed_id,
                Route.route_id == route_in.route_id,
                Route.id != route_id,
            )
        )
        if existing_route.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Route with route_id '{route_in.route_id}' already exists in this feed",
            )

    # Update route
    update_data = route_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(route, field, value)

    await db.commit()
    await db.refresh(route)

    # Create audit log with composite key format
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="route",
        entity_id=f"{route.feed_id}:{route.route_id}",
        description=f"Updated route '{route.route_short_name or route.route_long_name}' ({route.route_id})",
        old_values=old_values,
        new_values=serialize_model(route),
        agency_id=feed.agency_id,
        request=request,
    )

    return route


@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_route(
    feed_id: int,
    route_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Delete a route using composite key (feed_id, route_id).

    - Super admins can delete any route
    - Agency admins can delete routes in their agencies
    - This will cascade delete all trips and stop times for this route
    """
    # Query with composite primary key
    result = await db.execute(
        select(Route).where(
            Route.feed_id == feed_id,
            Route.route_id == route_id
        )
    )
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route '{route_id}' not found in feed {feed_id}",
        )

    # Store values for audit log before deletion
    old_values = serialize_model(route)
    route_name = route.route_short_name or route.route_long_name
    route_gtfs_id = route.route_id

    # Get the feed to check agency_id
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == route.feed_id)
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
                detail="Only agency admins can delete routes",
            )

    # Delete route (cascade will handle trips and stop times)
    await db.delete(route)
    await db.commit()

    # Create audit log with composite key format
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="route",
        entity_id=f"{feed_id}:{route_gtfs_id}",
        description=f"Deleted route '{route_name}' ({route_gtfs_id})",
        old_values=old_values,
        agency_id=feed.agency_id,
        request=request,
    )


@router.get("/{route_id}/stats", response_model=RouteWithStats)
async def get_route_stats(
    feed_id: int,
    route_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> RouteWithStats:
    """
    Get route details with statistics using composite key (feed_id, route_id).
    """
    # Query with composite primary key
    result = await db.execute(
        select(Route).where(
            Route.feed_id == feed_id,
            Route.route_id == route_id
        )
    )
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route '{route_id}' not found in feed {feed_id}",
        )

    # Check access through the feed's agency
    if not current_user.is_superuser:
        # Get the feed to check agency_id
        feed_result = await db.execute(
            select(GTFSFeed).where(GTFSFeed.id == route.feed_id)
        )
        feed = feed_result.scalar_one_or_none()

        if not feed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feed not found",
            )

        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this route",
            )

    # Get trip count
    trip_count_query = select(func.count(Trip.trip_id)).where(Trip.route_id == route_id)
    trip_count = await db.scalar(trip_count_query)

    route_data = RouteResponse.model_validate(route)
    return RouteWithStats(
        **route_data.model_dump(),
        trip_count=trip_count or 0,
        active_trips=0,  # TODO: Implement active trips calculation
    )

