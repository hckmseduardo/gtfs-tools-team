"""Stop (GTFS) management endpoints with geospatial support"""

from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, cast, String, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_MakePoint, ST_SetSRID

from app.api import deps
from app.api.deps import get_db
from app.models.user import User, UserRole, user_agencies
from app.models.agency import Agency
from app.models.gtfs import Stop, GTFSFeed
from app.models.audit import AuditAction
from app.schemas.stop import (
    StopCreate,
    StopUpdate,
    StopResponse,
    StopWithDistance,
    StopList,
    StopListWithDistance,
    StopNearbyQuery,
    StopBoundsQuery,
)
from app.utils.audit import create_audit_log, serialize_model

router = APIRouter()


@router.get("", response_model=StopList)
async def list_stops(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=50000),
    search: Optional[str] = None,
    wheelchair_accessible: Optional[bool] = None,
    location_type: Optional[int] = Query(None, ge=0, le=4, description="Filter by location type (0=stop, 1=station, 2=entrance, 3=node, 4=boarding area)"),
) -> StopList:
    """
    List stops for a specific feed with pagination and filtering.

    - Super admins can see all stops
    - Other users see only stops from feeds in agencies they belong to
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

    # Build query for stops in this specific feed
    query = select(Stop).where(Stop.feed_id == feed_id)

    if search:
        query = query.where(
            or_(
                Stop.stop_name.ilike(f"%{search}%"),
                Stop.stop_code.ilike(f"%{search}%"),
                Stop.stop_id.ilike(f"%{search}%"),
            )
        )

    if wheelchair_accessible is not None:
        query = query.where(Stop.wheelchair_boarding == (1 if wheelchair_accessible else 2))

    if location_type is not None:
        query = query.where(Stop.location_type == location_type)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Stop.stop_name)
    result = await db.execute(query)
    stops = result.scalars().all()

    return StopList(
        items=[StopResponse.model_validate(stop) for stop in stops],
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.post("/nearby", response_model=StopListWithDistance)
async def find_nearby_stops(
    query_params: StopNearbyQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    agency_id: Optional[int] = None,
) -> StopListWithDistance:
    """
    Find stops near a geographic point using PostGIS.

    Returns stops within the specified radius, ordered by distance.
    """
    # Create point geometry from lat/lon
    point = ST_SetSRID(
        ST_MakePoint(float(query_params.longitude), float(query_params.latitude)),
        4326  # WGS84 SRID
    )

    # Build query with distance calculation
    distance = ST_Distance(
        Stop.geom,
        point,
        type_=True  # Use geography for accurate meter distances
    )

    query = (
        select(Stop, distance.label("distance"))
        .where(
            ST_DWithin(
                Stop.geom,
                point,
                query_params.radius_meters,
                type_=True  # Use geography
            )
        )
    )

    # Filter by agency access through feeds
    if not current_user.is_superuser:
        user_agency_ids = select(user_agencies.c.agency_id).where(
            user_agencies.c.user_id == current_user.id
        )
        feed_ids_subquery = select(GTFSFeed.id).where(GTFSFeed.agency_id.in_(user_agency_ids))
        query = query.where(Stop.feed_id.in_(feed_ids_subquery))

    if agency_id:
        # Verify user has access to this agency
        await deps.verify_agency_access(agency_id, db, current_user)
        feed_ids_subquery = select(GTFSFeed.id).where(GTFSFeed.agency_id == agency_id)
        query = query.where(Stop.feed_id.in_(feed_ids_subquery))

    # Order by distance and limit
    query = query.order_by(distance).limit(query_params.limit)

    result = await db.execute(query)
    rows = result.all()

    items = []
    for stop, dist in rows:
        stop_data = StopResponse.model_validate(stop)
        items.append(
            StopWithDistance(
                **stop_data.model_dump(),
                distance_meters=float(dist) if dist else None,
            )
        )

    return StopListWithDistance(
        items=items,
        total=len(items),
    )


@router.post("/in-bounds", response_model=StopList)
async def find_stops_in_bounds(
    bounds: StopBoundsQuery,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    agency_id: Optional[int] = None,
) -> StopList:
    """
    Find all stops within a bounding box.

    Useful for map-based interfaces showing stops in a visible area.
    """
    # Build query with bounding box filter
    query = select(Stop).where(
        Stop.stop_lat >= bounds.min_lat,
        Stop.stop_lat <= bounds.max_lat,
        Stop.stop_lon >= bounds.min_lon,
        Stop.stop_lon <= bounds.max_lon,
    )

    # Filter by agency access through feeds
    if not current_user.is_superuser:
        user_agency_ids = select(user_agencies.c.agency_id).where(
            user_agencies.c.user_id == current_user.id
        )
        feed_ids_subquery = select(GTFSFeed.id).where(GTFSFeed.agency_id.in_(user_agency_ids))
        query = query.where(Stop.feed_id.in_(feed_ids_subquery))

    if agency_id:
        # Verify user has access to this agency
        await deps.verify_agency_access(agency_id, db, current_user)
        feed_ids_subquery = select(GTFSFeed.id).where(GTFSFeed.agency_id == agency_id)
        query = query.where(Stop.feed_id.in_(feed_ids_subquery))

    # Get results
    result = await db.execute(query)
    stops = result.scalars().all()

    return StopList(
        items=[StopResponse.model_validate(stop) for stop in stops],
        total=len(stops),
        page=1,
        page_size=len(stops),
        pages=1,
    )


@router.post("", response_model=StopResponse, status_code=status.HTTP_201_CREATED)
async def create_stop(
    feed_id: int,
    stop_in: StopCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Stop:
    """
    Create a new stop in a specific feed.

    - Super admins can create stops for any agency
    - Agency admins and editors can create stops for their agencies
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
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
            cast(user_agencies.c.role, String).in_([UserRole.AGENCY_ADMIN.value, UserRole.EDITOR.value]),
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create stops for this feed",
            )

    # Check if stop_id already exists in this feed
    existing_stop = await db.execute(
        select(Stop).where(
            Stop.feed_id == feed_id,
            Stop.stop_id == stop_in.stop_id,
        )
    )
    if existing_stop.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stop with stop_id '{stop_in.stop_id}' already exists in this feed",
        )

    # Create stop
    stop_data = stop_in.model_dump(exclude={'agency_id'})
    stop = Stop(**stop_data, feed_id=feed_id)

    # Create PostGIS geometry from lat/lon
    stop.geom = func.ST_SetSRID(
        func.ST_MakePoint(float(stop_in.stop_lon), float(stop_in.stop_lat)),
        4326
    )

    db.add(stop)
    await db.commit()
    await db.refresh(stop)

    # Create audit log with composite key format
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="stop",
        entity_id=f"{stop.feed_id}:{stop.stop_id}",
        description=f"Created stop '{stop.stop_name}' ({stop.stop_id})",
        new_values=serialize_model(stop, exclude_fields=['geom']),
        agency_id=feed.agency_id,
        request=request,
    )

    return stop


@router.get("/{stop_id}", response_model=StopResponse)
async def get_stop(
    feed_id: int,
    stop_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Stop:
    """
    Get stop details by composite key (feed_id, stop_id).
    """
    # Query with composite primary key
    result = await db.execute(
        select(Stop).where(
            Stop.feed_id == feed_id,
            Stop.stop_id == stop_id
        )
    )
    stop = result.scalar_one_or_none()

    if not stop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stop '{stop_id}' not found in feed {feed_id}",
        )

    # Check access through the feed's agency
    if not current_user.is_superuser:
        # Get the feed to check agency_id
        feed_result = await db.execute(
            select(GTFSFeed).where(GTFSFeed.id == feed_id)
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
                detail="You don't have access to this stop",
            )

    return stop


@router.patch("/{stop_id}", response_model=StopResponse)
async def update_stop(
    feed_id: int,
    stop_id: str,
    stop_in: StopUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Stop:
    """
    Update stop details using composite key (feed_id, stop_id).

    - Super admins can update any stop
    - Agency admins and editors can update stops in their agencies
    """
    # Query with composite primary key
    result = await db.execute(
        select(Stop).where(
            Stop.feed_id == feed_id,
            Stop.stop_id == stop_id
        )
    )
    stop = result.scalar_one_or_none()

    if not stop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stop '{stop_id}' not found in feed {feed_id}",
        )

    # Store old values for audit
    old_values = serialize_model(stop, exclude_fields=['geom'])

    # Get the feed to check agency_id
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == stop.feed_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check permissions through the feed's agency
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
                detail="You don't have permission to update this stop",
            )

    # Check if stop_id is being changed and if it conflicts
    if stop_in.stop_id and stop_in.stop_id != stop.stop_id:
        existing_stop = await db.execute(
            select(Stop).where(
                Stop.feed_id == feed_id,
                Stop.stop_id == stop_in.stop_id,
            )
        )
        if existing_stop.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stop with stop_id '{stop_in.stop_id}' already exists in this feed",
            )

    # Update stop
    update_data = stop_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(stop, field, value)

    # Update geometry if coordinates changed
    if stop_in.stop_lat is not None or stop_in.stop_lon is not None:
        stop.geom = func.ST_SetSRID(
            func.ST_MakePoint(float(stop.stop_lon), float(stop.stop_lat)),
            4326
        )

    await db.commit()
    await db.refresh(stop)

    # Create audit log with composite key format
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="stop",
        entity_id=f"{stop.feed_id}:{stop.stop_id}",
        description=f"Updated stop '{stop.stop_name}' ({stop.stop_id})",
        old_values=old_values,
        new_values=serialize_model(stop, exclude_fields=['geom']),
        agency_id=feed.agency_id,
        request=request,
    )

    return stop


@router.delete("/{stop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stop(
    feed_id: int,
    stop_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Delete a stop using composite key (feed_id, stop_id).

    - Super admins can delete any stop
    - Agency admins can delete stops in their agencies
    - This will cascade delete all stop times for this stop
    """
    # Query with composite primary key
    result = await db.execute(
        select(Stop).where(
            Stop.feed_id == feed_id,
            Stop.stop_id == stop_id
        )
    )
    stop = result.scalar_one_or_none()

    if not stop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stop '{stop_id}' not found in feed {feed_id}",
        )

    # Store values for audit log before deletion
    old_values = serialize_model(stop, exclude_fields=['geom'])
    stop_name = stop.stop_name
    stop_gtfs_id = stop.stop_id

    # Get the feed to check agency_id
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == stop.feed_id)
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
                detail="Only agency admins can delete stops",
            )

    await db.delete(stop)
    await db.commit()

    # Create audit log with composite key format
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="stop",
        entity_id=f"{feed_id}:{stop_gtfs_id}",
        description=f"Deleted stop '{stop_name}' ({stop_gtfs_id})",
        old_values=old_values,
        agency_id=feed.agency_id,
        request=request,
    )
