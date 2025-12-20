"""Route Creator endpoints for exporting routes from the in-memory Route Creator"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api import deps
from app.api.deps import get_db
from app.db.base import AsyncTask
from app.models.user import User
from app.models.task import TaskStatus, TaskType
from app.models.gtfs import GTFSFeed
from app.schemas.route_export import (
    RouteExportPayload,
    RouteExportRequest,
    RouteExportTaskResponse,
    RouteExportValidation,
)
from app.services.route_export_service import route_export_service
from app.tasks import export_route as export_route_task

router = APIRouter()


@router.post("/validate", response_model=RouteExportValidation)
async def validate_route_export(
    payload: RouteExportPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> RouteExportValidation:
    """
    Validate route export payload before submitting.

    Performs validation checks:
    - Feed exists and is accessible
    - Service calendars exist in the feed
    - Route ID doesn't already exist
    - Shape ID doesn't already exist
    - New stops don't already exist
    - Trip IDs are unique
    - Stop times reference valid stops and trips

    Returns validation result with errors, warnings, and data summary.
    """
    # Check feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == payload.feed_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed with ID {payload.feed_id} not found",
        )

    # Run validation
    validation = await route_export_service.validate_payload(db, payload)

    return validation


@router.post("/export", response_model=RouteExportTaskResponse)
async def export_route(
    request: RouteExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> RouteExportTaskResponse:
    """
    Export a route from Route Creator to a GTFS feed.

    Creates an async task that will:
    1. Create the route
    2. Create new stops (deduplicate existing)
    3. Create the shape
    4. Create trips for each selected service calendar
    5. Create stop_times for each trip

    All operations are atomic - if any step fails, everything is rolled back.

    Returns a task ID that can be used to track progress in Task Manager.
    """
    payload = request.payload

    # Check feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == payload.feed_id)
    )
    feed = feed_result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed with ID {payload.feed_id} not found",
        )

    # Quick validation before queuing
    validation = await route_export_service.validate_payload(db, payload)
    if not validation.valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Validation failed",
                "errors": validation.errors,
                "warnings": validation.warnings,
            },
        )

    # Create task record with temporary UUID (will be updated with actual Celery task ID)
    task_record = AsyncTask(
        celery_task_id=str(uuid.uuid4()),
        task_name=f"Export Route: {payload.route.route_short_name or payload.route.route_id}",
        description=(
            f"Creating route '{payload.route.route_id}' with "
            f"{len(payload.new_stops)} new stops, "
            f"{len(payload.shape_points)} shape points, "
            f"{len(payload.trips) * len(payload.service_ids)} trips"
        ),
        task_type=TaskType.ROUTE_EXPORT.value,
        user_id=current_user.id,
        agency_id=feed.agency_id,
        status=TaskStatus.PENDING.value,
        progress=0.0,
        input_data={
            "feed_id": payload.feed_id,
            "route_id": payload.route.route_id,
            "route_short_name": payload.route.route_short_name,
            "new_stops_count": len(payload.new_stops),
            "shape_points_count": len(payload.shape_points),
            "trips_count": len(payload.trips),
            "service_ids_count": len(payload.service_ids),
            "total_trips": len(payload.trips) * len(payload.service_ids),
            "stop_times_count": len(payload.stop_times),
        },
    )

    db.add(task_record)
    await db.commit()
    await db.refresh(task_record)

    # Queue the Celery task
    celery_result = export_route_task.apply_async(
        kwargs={
            "task_db_id": task_record.id,
            "payload_dict": payload.model_dump(mode="json"),
            "user_id": current_user.id,
        },
        task_id=f"export_route_{task_record.id}"
    )

    # Update task record with Celery task ID
    task_record.celery_task_id = celery_result.id
    await db.commit()

    return RouteExportTaskResponse(
        task_id=task_record.id,
        celery_task_id=celery_result.id,
        message=(
            f"Route export started. Creating '{payload.route.route_id}' with "
            f"{len(payload.trips) * len(payload.service_ids)} trips. "
            "Track progress in Task Manager."
        ),
    )
