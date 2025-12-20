"""Shape (GTFS) management endpoints"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.api import deps
from app.api.deps import get_db
from app.models.user import User, UserRole, user_agencies
from app.models.gtfs import Shape, GTFSFeed, Trip
from app.models.audit import AuditAction
from app.schemas.shape import (
    ShapeCreate,
    ShapeUpdate,
    ShapeResponse,
    ShapePoint,
    ShapeWithPoints,
    ShapeList,
    ShapesByIdList,
    ShapeBulkCreate,
)
from app.utils.audit import create_audit_log

router = APIRouter()


@router.get("/", response_model=ShapeList)
async def list_shapes(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=50000),
    shape_id: Optional[str] = None,
) -> ShapeList:
    """
    List shape points with pagination and filtering.

    - Super admins can see all shapes
    - Other users see only shapes from feeds they have access to
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

    # Build query for shapes in this specific feed
    query = select(Shape).where(Shape.feed_id == feed_id)

    if shape_id:
        query = query.where(Shape.shape_id == shape_id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results, ordered by shape_id and sequence
    query = query.offset(skip).limit(limit).order_by(Shape.shape_id, Shape.shape_pt_sequence)
    result = await db.execute(query)
    shapes = result.scalars().all()

    return ShapeList(
        items=[ShapeResponse.model_validate(shape) for shape in shapes],
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.get("/by-shape-id", response_model=ShapesByIdList)
async def get_shapes_by_id(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    shape_ids: Optional[str] = Query(None, description="Comma-separated shape IDs"),
) -> ShapesByIdList:
    """
    Get shapes grouped by shape_id with all points.
    Useful for drawing route paths on a map.

    - shape_ids: Optional comma-separated list of shape IDs to filter
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

    # Build query for shapes in this feed
    query = select(Shape).where(Shape.feed_id == feed_id)

    if shape_ids:
        shape_id_list = [sid.strip() for sid in shape_ids.split(",")]
        query = query.where(Shape.shape_id.in_(shape_id_list))

    # Order by shape_id and sequence
    query = query.order_by(Shape.shape_id, Shape.shape_pt_sequence)
    result = await db.execute(query)
    shapes = result.scalars().all()

    # Group by shape_id
    shapes_dict: dict[str, list] = {}
    for shape in shapes:
        if shape.shape_id not in shapes_dict:
            shapes_dict[shape.shape_id] = []
        shapes_dict[shape.shape_id].append(
            ShapePoint(
                lat=float(shape.shape_pt_lat),
                lon=float(shape.shape_pt_lon),
                sequence=shape.shape_pt_sequence,
            )
        )

    # Convert to response format
    items = [
        ShapeWithPoints(
            shape_id=shape_id,
            points=points,
            total_points=len(points),
        )
        for shape_id, points in shapes_dict.items()
    ]

    return ShapesByIdList(
        items=items,
        total=len(items),
    )


@router.get("/{shape_id}/{shape_pt_sequence}", response_model=ShapeResponse)
async def get_shape(
    feed_id: int,
    shape_id: str,
    shape_pt_sequence: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Shape:
    """Get shape point details by composite key (feed_id, shape_id, shape_pt_sequence)."""
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

    # Get shape point with composite key
    result = await db.execute(
        select(Shape).where(
            Shape.feed_id == feed_id,
            Shape.shape_id == shape_id,
            Shape.shape_pt_sequence == shape_pt_sequence
        )
    )
    shape = result.scalar_one_or_none()

    if not shape:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shape point not found",
        )

    return shape


@router.delete("/{shape_id}/{shape_pt_sequence}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shape(
    feed_id: int,
    shape_id: str,
    shape_pt_sequence: int,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Delete a shape point using composite key (feed_id, shape_id, shape_pt_sequence).

    - Super admins can delete any shape point
    - Agency admins can delete shape points in their agencies
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

    # Check permissions (only admins can delete)
    if not current_user.is_superuser:
        from app.models.user import UserRole
        from sqlalchemy import cast
        from sqlalchemy.types import String

        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
            cast(user_agencies.c.role, String) == UserRole.AGENCY_ADMIN.value,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only agency admins can delete shapes",
            )

    # Get shape point with composite key
    result = await db.execute(
        select(Shape).where(
            Shape.feed_id == feed_id,
            Shape.shape_id == shape_id,
            Shape.shape_pt_sequence == shape_pt_sequence
        )
    )
    shape = result.scalar_one_or_none()

    if not shape:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shape point not found",
        )

    # Store values for audit log before deletion
    old_values = {
        "shape_id": shape.shape_id,
        "sequence": shape.shape_pt_sequence,
        "lat": str(shape.shape_pt_lat),
        "lon": str(shape.shape_pt_lon),
    }

    await db.delete(shape)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="shape_point",
        entity_id=f"{feed_id}:{shape_id}:{shape_pt_sequence}",
        description=f"Deleted shape point from shape '{shape_id}' (sequence {shape_pt_sequence})",
        old_values=old_values,
        agency_id=feed.agency_id,
        request=request,
    )


@router.post("/", response_model=ShapeResponse, status_code=status.HTTP_201_CREATED)
async def create_shape_point(
    shape_in: ShapeCreate,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> ShapeResponse:
    """
    Create a new shape point.
    """
    # Verify feed exists and user has EDITOR role
    feed = await _verify_feed_access(shape_in.feed_id, current_user, db, UserRole.EDITOR)

    # Create shape point
    shape = Shape(
        feed_id=shape_in.feed_id,
        shape_id=shape_in.shape_id,
        shape_pt_lat=shape_in.shape_pt_lat,
        shape_pt_lon=shape_in.shape_pt_lon,
        shape_pt_sequence=shape_in.shape_pt_sequence,
        shape_dist_traveled=shape_in.shape_dist_traveled,
    )

    db.add(shape)
    await db.commit()
    await db.refresh(shape)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="shape_point",
        entity_id=f"{shape.feed_id}:{shape.shape_id}:{shape.shape_pt_sequence}",
        description=f"Created shape point for shape '{shape.shape_id}' at sequence {shape.shape_pt_sequence}",
        new_values=shape_in.model_dump(),
        agency_id=feed.agency_id,
        request=request,
    )

    return ShapeResponse.model_validate(shape)


@router.patch("/{shape_id}/{shape_pt_sequence}", response_model=ShapeResponse)
async def update_shape_point(
    feed_id: int,
    shape_id: str,
    shape_pt_sequence: int,
    shape_in: ShapeUpdate,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> ShapeResponse:
    """
    Update a shape point using composite key (feed_id, shape_id, shape_pt_sequence).
    """
    # Verify user has EDITOR role for the feed
    feed = await _verify_feed_access(feed_id, current_user, db, UserRole.EDITOR)

    # Get shape point with composite key
    result = await db.execute(
        select(Shape).where(
            Shape.feed_id == feed_id,
            Shape.shape_id == shape_id,
            Shape.shape_pt_sequence == shape_pt_sequence
        )
    )
    shape = result.scalar_one_or_none()

    if not shape:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shape point not found",
        )

    # Store old values for audit
    old_values = {
        "shape_pt_lat": str(shape.shape_pt_lat),
        "shape_pt_lon": str(shape.shape_pt_lon),
        "shape_pt_sequence": shape.shape_pt_sequence,
        "shape_dist_traveled": str(shape.shape_dist_traveled) if shape.shape_dist_traveled else None,
    }

    # Update fields
    update_data = shape_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(shape, field, value)

    await db.commit()
    await db.refresh(shape)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="shape_point",
        entity_id=f"{feed_id}:{shape_id}:{shape_pt_sequence}",
        description=f"Updated shape point for shape '{shape.shape_id}' at sequence {shape.shape_pt_sequence}",
        old_values=old_values,
        new_values=update_data,
        agency_id=feed.agency_id,
        request=request,
    )

    return ShapeResponse.model_validate(shape)


@router.post("/bulk", response_model=List[ShapeResponse], status_code=status.HTTP_201_CREATED)
async def bulk_create_shape(
    shape_bulk: ShapeBulkCreate,
    replace_existing: bool = Query(False, description="Replace existing shape points if shape_id exists"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> List[ShapeResponse]:
    """
    Bulk create shape points for a shape.

    If replace_existing is True, all existing points for this shape_id will be deleted first.
    """
    # Verify feed exists and user has EDITOR role
    feed = await _verify_feed_access(shape_bulk.feed_id, current_user, db, UserRole.EDITOR)

    deleted_count = 0
    if replace_existing:
        # Count existing shape points
        result = await db.execute(
            select(func.count()).select_from(
                select(Shape).where(
                    Shape.feed_id == shape_bulk.feed_id,
                    Shape.shape_id == shape_bulk.shape_id,
                ).subquery()
            )
        )
        deleted_count = result.scalar() or 0

        # Delete existing shape points
        await db.execute(
            delete(Shape).where(
                Shape.feed_id == shape_bulk.feed_id,
                Shape.shape_id == shape_bulk.shape_id,
            )
        )

    # Create new shape points
    shapes = []
    for point in shape_bulk.points:
        shape = Shape(
            feed_id=shape_bulk.feed_id,
            shape_id=shape_bulk.shape_id,
            shape_pt_lat=point.lat,
            shape_pt_lon=point.lon,
            shape_pt_sequence=point.sequence,
            shape_dist_traveled=point.dist_traveled,
        )
        db.add(shape)
        shapes.append(shape)

    await db.commit()

    # Refresh all shapes
    for shape in shapes:
        await db.refresh(shape)

    # Create audit log
    action_desc = f"Bulk created {len(shapes)} points for shape '{shape_bulk.shape_id}'"
    if deleted_count > 0:
        action_desc = f"Replaced shape '{shape_bulk.shape_id}' ({deleted_count} old points → {len(shapes)} new points)"

    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE if not replace_existing else AuditAction.UPDATE,
        entity_type="shape",
        entity_id=f"{shape_bulk.feed_id}:{shape_bulk.shape_id}",
        description=action_desc,
        new_values={
            "shape_id": shape_bulk.shape_id,
            "points_count": len(shapes),
            "replaced": replace_existing,
        },
        agency_id=feed.agency_id,
        request=request,
    )

    return [ShapeResponse.model_validate(shape) for shape in shapes]


@router.delete("/by-shape-id/{shape_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shape_by_id(
    feed_id: int,
    shape_id: str,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Delete all points for a shape_id.
    """
    # Verify feed exists and user has AGENCY_ADMIN role
    feed = await _verify_feed_access(feed_id, current_user, db, UserRole.AGENCY_ADMIN)

    # Count existing points
    result = await db.execute(
        select(func.count()).select_from(
            select(Shape).where(
                Shape.feed_id == feed_id,
                Shape.shape_id == shape_id,
            ).subquery()
        )
    )
    count = result.scalar() or 0

    if count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shape '{shape_id}' not found in this feed",
        )

    # Delete all points
    await db.execute(
        delete(Shape).where(
            Shape.feed_id == feed_id,
            Shape.shape_id == shape_id,
        )
    )
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="shape",
        entity_id=f"{feed_id}:{shape_id}",
        description=f"Deleted shape '{shape_id}' ({count} points)",
        old_values={"shape_id": shape_id, "points_count": count},
        agency_id=feed.agency_id,
        request=request,
    )


async def _verify_feed_access(
    feed_id: int,
    current_user: User,
    db: AsyncSession,
    required_role: UserRole = None,
) -> GTFSFeed:
    """Verify that the feed exists and the user has access to it.

    Args:
        feed_id: The feed ID to check access for
        current_user: The current authenticated user
        db: Database session
        required_role: Optional minimum role required (e.g., EDITOR, AGENCY_ADMIN)
    """
    result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Superusers have access to everything
    if current_user.is_superuser:
        return feed

    # Check user has access to the agency
    membership_query = select(user_agencies).where(
        user_agencies.c.user_id == current_user.id,
        user_agencies.c.agency_id == feed.agency_id,
    )
    membership_result = await db.execute(membership_query)
    membership = membership_result.first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this feed",
        )

    # Check role if required
    if required_role:
        user_role = membership.role
        role_hierarchy = {
            UserRole.SUPER_ADMIN: 4,
            UserRole.AGENCY_ADMIN: 3,
            UserRole.EDITOR: 2,
            UserRole.VIEWER: 1,
        }

        if role_hierarchy.get(UserRole(user_role), 0) < role_hierarchy.get(required_role, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role.value} role or higher",
            )

    return feed
