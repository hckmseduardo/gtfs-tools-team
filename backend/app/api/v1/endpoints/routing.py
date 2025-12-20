"""Routing endpoints for OSM-based shape improvements"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import get_db
from app.models.user import User, UserRole, user_agencies
from app.models.gtfs import Shape, GTFSFeed
from app.schemas.routing import (
    SnapToRoadRequest,
    AutoRouteRequest,
    RoutingResult,
    RoutingHealthResponse,
    RoutingPointOutput,
    TransitMode,
)
from app.services.routing_service import (
    routing_service,
    RoutingPoint,
    TransitMode as ServiceTransitMode,
    RoutingError,
)

router = APIRouter()


def _map_transit_mode(mode: TransitMode) -> ServiceTransitMode:
    """Map API transit mode to service transit mode"""
    mapping = {
        TransitMode.BUS: ServiceTransitMode.BUS,
        TransitMode.RAIL: ServiceTransitMode.RAIL,
        TransitMode.TRAM: ServiceTransitMode.TRAM,
        TransitMode.FERRY: ServiceTransitMode.FERRY,
    }
    return mapping.get(mode, ServiceTransitMode.BUS)


@router.get("/health", response_model=RoutingHealthResponse)
async def check_routing_health():
    """
    Check if the routing service (Valhalla) is available.

    This endpoint is public and doesn't require authentication.
    """
    is_healthy = await routing_service.check_health()
    return RoutingHealthResponse(
        available=is_healthy,
        message="Routing service is available" if is_healthy else "Routing service is unavailable - tile building may be in progress"
    )


@router.post("/snap-to-road", response_model=RoutingResult)
async def snap_shape_to_road(
    request: SnapToRoadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Snap an existing shape to the road/rail network.

    Takes the current shape points and uses Valhalla's map-matching
    to align them to the nearest road/rail network based on the
    selected transport mode.

    Requires EDITOR role or higher.
    """
    # Verify feed access and role
    await _verify_feed_access(request.feed_id, current_user, db, UserRole.EDITOR)

    # Get existing shape points
    result = await db.execute(
        select(Shape)
        .where(Shape.feed_id == request.feed_id, Shape.shape_id == request.shape_id)
        .order_by(Shape.shape_pt_sequence)
    )
    shapes = result.scalars().all()

    if not shapes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shape '{request.shape_id}' not found in feed"
        )

    if len(shapes) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shape must have at least 2 points to snap"
        )

    # Convert to routing points
    points = [
        RoutingPoint(lat=float(s.shape_pt_lat), lon=float(s.shape_pt_lon))
        for s in shapes
    ]

    try:
        # Call routing service
        routed = await routing_service.snap_to_road(
            points=points,
            mode=_map_transit_mode(request.mode)
        )

        # Format response
        output_points = [
            RoutingPointOutput(lat=p.lat, lon=p.lon, sequence=i)
            for i, p in enumerate(routed.points)
        ]

        return RoutingResult(
            success=True,
            shape_id=request.shape_id,
            points=output_points,
            point_count=len(output_points),
            distance_meters=routed.distance_meters,
            confidence=routed.confidence,
            message=f"Snapped {len(shapes)} points to {len(output_points)} road-aligned points"
        )

    except RoutingError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Routing failed: {e.message}"
        )


@router.post("/auto-route", response_model=RoutingResult)
async def auto_route_waypoints(
    request: AutoRouteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Generate a route from waypoints following the road network.

    User provides a list of waypoints (minimum 2), and Valhalla
    generates the optimal route between them following the road
    network appropriate for the selected transport mode.

    Requires EDITOR role or higher.
    """
    # Verify feed access and role
    await _verify_feed_access(request.feed_id, current_user, db, UserRole.EDITOR)

    # Convert waypoints to routing points
    waypoints = [
        RoutingPoint(lat=w.lat, lon=w.lon)
        for w in request.waypoints
    ]

    try:
        # Call routing service
        routed = await routing_service.auto_route(
            waypoints=waypoints,
            mode=_map_transit_mode(request.mode)
        )

        if not routed.points:
            # Fallback: return straight-line path through waypoints instead of failing
            fallback_points = [
                RoutingPointOutput(lat=w.lat, lon=w.lon, sequence=i)
                for i, w in enumerate(waypoints)
            ]
            return RoutingResult(
                success=True,
                shape_id=request.shape_id,
                points=fallback_points,
                point_count=len(fallback_points),
                distance_meters=0,
                message=f"Routing unavailable; returned straight line through {len(waypoints)} waypoints",
            )

        # Format response
        output_points = [
            RoutingPointOutput(lat=p.lat, lon=p.lon, sequence=i)
            for i, p in enumerate(routed.points)
        ]

        return RoutingResult(
            success=True,
            shape_id=request.shape_id,
            points=output_points,
            point_count=len(output_points),
            distance_meters=routed.distance_meters,
            message=f"Generated route with {len(output_points)} points from {len(waypoints)} waypoints"
        )

    except RoutingError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Routing failed: {e.message}"
        )


async def _verify_feed_access(
    feed_id: int,
    current_user: User,
    db: AsyncSession,
    required_role: UserRole = None,
) -> GTFSFeed:
    """
    Verify user has access to the feed and meets role requirements.

    Args:
        feed_id: Feed ID to check access for
        current_user: Current authenticated user
        db: Database session
        required_role: Minimum role required (optional)

    Returns:
        GTFSFeed if access is granted

    Raises:
        HTTPException if access is denied
    """
    # Get the feed
    result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Superusers have full access
    if current_user.is_superuser:
        return feed

    # Check agency membership
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
        role_hierarchy = {
            UserRole.SUPER_ADMIN: 4,
            UserRole.AGENCY_ADMIN: 3,
            UserRole.EDITOR: 2,
            UserRole.VIEWER: 1,
        }
        user_role_level = role_hierarchy.get(UserRole(membership.role), 0)
        required_role_level = role_hierarchy.get(required_role, 0)

        if user_role_level < required_role_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role.value} role or higher",
            )

    return feed
