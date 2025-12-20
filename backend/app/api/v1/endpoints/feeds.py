"""
GTFS Feeds endpoints
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, verify_agency_access, verify_feed_access
from app.models.user import UserRole
from app.models.user import User
from app.models.gtfs import GTFSFeed, Route, Stop, Trip, Calendar
from app.models.agency import Agency
from app.models.audit import AuditAction
from app.services.gtfs_validator import GTFSValidator
from app.schemas.feed import (
    GTFSFeedCreate,
    GTFSFeedUpdate,
    GTFSFeedResponse,
    GTFSFeedListResponse,
)
from app.utils.audit import create_audit_log, serialize_model

router = APIRouter()


@router.post("/", response_model=GTFSFeedResponse, status_code=status.HTTP_201_CREATED)
async def create_feed(
    feed_data: GTFSFeedCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new empty GTFS feed from scratch.

    This creates a feed without importing any data, allowing users to build
    GTFS data manually by adding routes, stops, trips, etc.

    - **agency_id**: Agency this feed belongs to (required)
    - **name**: Descriptive name for this feed (required)
    - **description**: Optional description
    - **version**: Optional version identifier
    """
    from app.models.user import user_agencies
    from app.models.team import TeamMember, Workspace, workspace_agencies
    from datetime import datetime

    # Verify user has access to the agency (direct or team-based)
    direct_access = await db.execute(
        select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed_data.agency_id,
        )
    )
    team_access = await db.execute(
        select(workspace_agencies.c.agency_id)
        .select_from(TeamMember)
        .join(Workspace, TeamMember.team_id == Workspace.team_id)
        .join(workspace_agencies, Workspace.id == workspace_agencies.c.workspace_id)
        .where(
            TeamMember.user_id == current_user.id,
            workspace_agencies.c.agency_id == feed_data.agency_id
        )
    )
    if not direct_access.first() and not team_access.first():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to create feeds for this agency",
        )

    # Verify agency exists
    agency_query = select(Agency).where(Agency.id == feed_data.agency_id)
    agency_result = await db.execute(agency_query)
    if not agency_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agency {feed_data.agency_id} not found",
        )

    # Create the empty feed
    feed = GTFSFeed(
        agency_id=feed_data.agency_id,
        name=feed_data.name,
        description=feed_data.description,
        version=feed_data.version,
        filename=feed_data.filename,
        imported_at=datetime.utcnow().isoformat(),
        imported_by=current_user.id,
        is_active=False,  # New feeds start as inactive
        total_routes=0,
        total_stops=0,
        total_trips=0,
    )

    db.add(feed)
    await db.commit()
    await db.refresh(feed)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="gtfs_feed",
        entity_id=str(feed.id),
        description=f"Created empty GTFS feed '{feed.name}' from scratch",
        new_values=serialize_model(feed),
        agency_id=feed.agency_id,
        request=request,
    )

    return feed


@router.get("/", response_model=GTFSFeedListResponse)
async def list_feeds(
    agency_id: int | None = None,
    is_active: bool | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List GTFS feeds with optional filtering.

    - **agency_id**: Filter by agency
    - **is_active**: Filter by active status
    - **skip**: Number of records to skip
    - **limit**: Maximum number of records to return

    Users only see feeds from agencies they belong to (directly or through teams).
    """
    from app.models.user import user_agencies
    from app.models.team import TeamMember, Workspace, workspace_agencies

    # Build query
    query = select(GTFSFeed)

    # Apply filters
    filters = []

    # Get agencies where user is a direct member
    direct_agency_ids = select(user_agencies.c.agency_id).where(
        user_agencies.c.user_id == current_user.id
    )

    # Get agencies where user has access through team membership
    team_agency_ids = (
        select(workspace_agencies.c.agency_id)
        .select_from(TeamMember)
        .join(Workspace, TeamMember.team_id == Workspace.team_id)
        .join(workspace_agencies, Workspace.id == workspace_agencies.c.workspace_id)
        .where(TeamMember.user_id == current_user.id)
    )

    # Filter feeds by accessible agencies
    filters.append(
        or_(
            GTFSFeed.agency_id.in_(direct_agency_ids),
            GTFSFeed.agency_id.in_(team_agency_ids)
        )
    )

    if agency_id is not None:
        # Check if user has access to this specific agency
        direct_check = await db.execute(
            select(user_agencies.c.agency_id).where(
                user_agencies.c.user_id == current_user.id,
                user_agencies.c.agency_id == agency_id,
            )
        )
        team_check = await db.execute(
            select(workspace_agencies.c.agency_id)
            .select_from(TeamMember)
            .join(Workspace, TeamMember.team_id == Workspace.team_id)
            .join(workspace_agencies, Workspace.id == workspace_agencies.c.workspace_id)
            .where(
                TeamMember.user_id == current_user.id,
                workspace_agencies.c.agency_id == agency_id
            )
        )
        if not direct_check.first() and not team_check.first():
            # User doesn't have access to this agency, return empty result
            return GTFSFeedListResponse(
                feeds=[],
                total=0,
                skip=skip,
                limit=limit,
            )
        filters.append(GTFSFeed.agency_id == agency_id)

    if is_active is not None:
        filters.append(GTFSFeed.is_active == is_active)

    if filters:
        query = query.where(and_(*filters))

    # Add ordering
    query = query.order_by(GTFSFeed.imported_at.desc())

    # Get total count
    count_query = select(func.count()).select_from(GTFSFeed)
    if filters:
        count_query = count_query.where(and_(*filters))
    result = await db.execute(count_query)
    total = result.scalar_one()

    # Apply pagination
    query = query.offset(skip).limit(limit)

    # Execute query
    result = await db.execute(query)
    feeds = result.scalars().all()

    return GTFSFeedListResponse(
        feeds=feeds,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{feed_id}", response_model=GTFSFeedResponse)
async def get_feed(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get a specific GTFS feed by ID.
    """
    # Verify access (handles direct and team-based access)
    await verify_feed_access(feed_id, db, current_user, UserRole.VIEWER)

    query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
    result = await db.execute(query)
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed {feed_id} not found",
        )

    return feed


@router.patch("/{feed_id}", response_model=GTFSFeedResponse)
async def update_feed(
    feed_id: int,
    feed_update: GTFSFeedUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update a GTFS feed.

    - **name**: Update the feed name
    - **description**: Update the feed description
    - **is_active**: Activate or deactivate the feed
    """
    # Verify access (requires EDITOR role for updates)
    await verify_feed_access(feed_id, db, current_user, UserRole.EDITOR)

    query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
    result = await db.execute(query)
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed {feed_id} not found",
        )

    # Store old values for audit
    old_values = serialize_model(feed)

    # Update fields
    update_data = feed_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(feed, field, value)

    await db.commit()
    await db.refresh(feed)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="gtfs_feed",
        entity_id=str(feed.id),
        description=f"Updated GTFS feed '{feed.name}'",
        old_values=old_values,
        new_values=serialize_model(feed),
        agency_id=feed.agency_id,
        request=request,
    )

    return feed


@router.delete("/{feed_id}")
async def delete_feed(
    feed_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Queue an asynchronous task to delete a GTFS feed.

    This will cascade delete all related GTFS data (routes, stops, trips, stop_times,
    calendars, shapes). Since this can take a significant amount of time for large
    feeds, it's processed asynchronously and you can track progress via the Task Manager.

    Returns:
        Task information with task_id for tracking progress
    """
    from app.models.task import AsyncTask, TaskStatus, TaskType
    from app.tasks import delete_feed as delete_feed_task
    from datetime import datetime

    # Check if feed exists
    query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
    result = await db.execute(query)
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed {feed_id} not found",
        )

    # Check if user has access to this feed (requires AGENCY_ADMIN role for deletion)
    await verify_feed_access(feed_id, db, current_user, UserRole.AGENCY_ADMIN)

    # Create audit log for feed deletion
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="gtfs_feed",
        entity_id=str(feed.id),
        description=f"Queued deletion of GTFS feed '{feed.name}' (ID: {feed_id})",
        old_values=serialize_model(feed),
        agency_id=feed.agency_id,
        request=request,
    )

    # Create task record
    task = AsyncTask(
        celery_task_id="",  # Will be updated after Celery task is created
        task_type=TaskType.DELETE_FEED,
        task_name=f"Delete Feed: {feed.name}",
        description=f"Deleting GTFS feed '{feed.name}' (ID: {feed_id}) and all related data",
        user_id=current_user.id,
        agency_id=feed.agency_id,
        status=TaskStatus.PENDING,
        progress=0.0,
        input_data={
            "feed_id": feed_id,
            "feed_name": feed.name,
        }
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Queue Celery task
    celery_task = delete_feed_task.apply_async(
        args=[task.id, feed_id],
        task_id=f"delete_feed_{feed_id}_{task.id}"
    )

    # Update task with Celery task ID
    task.celery_task_id = celery_task.id
    await db.commit()

    return {
        "task_id": task.id,
        "celery_task_id": celery_task.id,
        "status": "queued",
        "message": f"Feed deletion queued. Track progress in Task Manager.",
        "feed_id": feed_id,
        "feed_name": feed.name,
    }


@router.post("/{feed_id}/activate", response_model=GTFSFeedResponse)
async def activate_feed(
    feed_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Activate a GTFS feed.

    This sets is_active=True for the feed.
    """
    # Verify access (requires EDITOR role)
    await verify_feed_access(feed_id, db, current_user, UserRole.EDITOR)

    query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
    result = await db.execute(query)
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed {feed_id} not found",
        )

    feed.is_active = True
    await db.commit()
    await db.refresh(feed)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="gtfs_feed",
        entity_id=str(feed.id),
        description=f"Activated GTFS feed '{feed.name}'",
        new_values={"is_active": True},
        agency_id=feed.agency_id,
        request=request,
    )

    return feed


@router.post("/{feed_id}/deactivate", response_model=GTFSFeedResponse)
async def deactivate_feed(
    feed_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deactivate a GTFS feed.

    This sets is_active=False for the feed.
    """
    # Verify access (requires EDITOR role)
    await verify_feed_access(feed_id, db, current_user, UserRole.EDITOR)

    query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
    result = await db.execute(query)
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed {feed_id} not found",
        )

    feed.is_active = False
    await db.commit()
    await db.refresh(feed)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="gtfs_feed",
        entity_id=str(feed.id),
        description=f"Deactivated GTFS feed '{feed.name}'",
        new_values={"is_active": False},
        agency_id=feed.agency_id,
        request=request,
    )

    return feed


@router.get("/{feed_id}/stats")
async def get_feed_stats(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed statistics for a GTFS feed.
    """
    # Verify access (VIEWER role is sufficient for read operations)
    await verify_feed_access(feed_id, db, current_user, UserRole.VIEWER)

    query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
    result = await db.execute(query)
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed {feed_id} not found",
        )

    # Get detailed counts
    routes_result = await db.execute(
        select(func.count()).select_from(Route).where(Route.feed_id == feed_id)
    )
    routes_count = routes_result.scalar_one()

    stops_result = await db.execute(
        select(func.count()).select_from(Stop).where(Stop.feed_id == feed_id)
    )
    stops_count = stops_result.scalar_one()

    trips_result = await db.execute(
        select(func.count()).select_from(Trip).where(Trip.feed_id == feed_id)
    )
    trips_count = trips_result.scalar_one()

    calendars_result = await db.execute(
        select(func.count()).select_from(Calendar).where(Calendar.feed_id == feed_id)
    )
    calendars_count = calendars_result.scalar_one()

    return {
        "feed_id": feed.id,
        "name": feed.name,
        "imported_at": feed.imported_at,
        "is_active": feed.is_active,
        "stats": {
            "routes": routes_count,
            "stops": stops_count,
            "trips": trips_count,
            "calendars": calendars_count,
        }
    }


@router.post("/{feed_id}/validate")
async def validate_feed(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Queue an asynchronous task to validate GTFS data for a feed.

    Uses the agency's validation preferences to determine which validations to run.
    Since validation can take time for large feeds, it runs asynchronously.
    Track progress via the Task Manager.

    Returns:
        Task information with task_id for tracking progress
    """
    from app.models.task import AsyncTask, TaskStatus, TaskType
    from app.tasks import validate_gtfs as validate_gtfs_task

    # Verify access (requires EDITOR role to run validations)
    await verify_feed_access(feed_id, db, current_user, UserRole.EDITOR)

    # Check if feed exists
    query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
    result = await db.execute(query)
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed {feed_id} not found",
        )

    # Create task record
    task = AsyncTask(
        celery_task_id="",  # Will be updated after Celery task is created
        task_type=TaskType.VALIDATE_GTFS,
        task_name=f"Validate Feed: {feed.name}",
        description=f"Running GTFS validations on feed '{feed.name}' (ID: {feed_id})",
        user_id=current_user.id,
        agency_id=feed.agency_id,
        status=TaskStatus.PENDING,
        progress=0.0,
        input_data={
            "feed_id": feed_id,
            "feed_name": feed.name,
        }
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Queue Celery task
    celery_task = validate_gtfs_task.apply_async(
        args=[task.id, feed_id, feed.agency_id],
        task_id=f"validate_gtfs_{feed_id}_{task.id}"
    )

    # Update task with Celery task ID
    task.celery_task_id = celery_task.id
    await db.commit()

    return {
        "task_id": task.id,
        "celery_task_id": celery_task.id,
        "status": "queued",
        "message": f"Validation queued. Track progress in Task Manager.",
        "feed_id": feed_id,
        "feed_name": feed.name,
    }


@router.post("/{feed_id}/validate-mobilitydata")
async def validate_feed_mobilitydata(
    feed_id: int,
    country_code: str = Query(
        default="",
        description="ISO country code for location-specific validations (e.g., 'US', 'CA', 'FR')"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Queue an asynchronous task to validate GTFS data using MobilityData Validator.

    This uses the official MobilityData GTFS Validator (https://github.com/MobilityData/gtfs-validator)
    which runs in a Docker container and provides comprehensive validation with detailed reports.

    The validation generates:
    - JSON report with machine-readable results
    - HTML report with a custom-branded visual report

    Args:
        feed_id: ID of the feed to validate
        country_code: Optional ISO country code for location-specific rules

    Returns:
        Task information with task_id for tracking progress
    """
    from app.models.task import AsyncTask, TaskStatus, TaskType
    from app.tasks import validate_gtfs_mobilitydata as validate_gtfs_mobilitydata_task

    # Verify access (requires EDITOR role to run validations)
    await verify_feed_access(feed_id, db, current_user, UserRole.EDITOR)

    # Check if feed exists
    query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
    result = await db.execute(query)
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed {feed_id} not found",
        )

    # Create task record
    task = AsyncTask(
        celery_task_id="",  # Will be updated after Celery task is created
        task_type=TaskType.VALIDATE_GTFS,
        task_name=f"MobilityData Validation: {feed.name}",
        description=f"Running MobilityData GTFS Validator on feed '{feed.name}' (ID: {feed_id})",
        user_id=current_user.id,
        agency_id=feed.agency_id,
        status=TaskStatus.PENDING,
        progress=0.0,
        input_data={
            "feed_id": feed_id,
            "feed_name": feed.name,
            "country_code": country_code,
            "validator": "mobilitydata",
        }
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Queue Celery task
    celery_task = validate_gtfs_mobilitydata_task.apply_async(
        args=[task.id, feed_id, feed.agency_id, country_code],
        task_id=f"validate_mobilitydata_{feed_id}_{task.id}"
    )

    # Update task with Celery task ID
    task.celery_task_id = celery_task.id
    await db.commit()

    return {
        "task_id": task.id,
        "celery_task_id": celery_task.id,
        "status": "queued",
        "message": "MobilityData validation queued. Track progress in Task Manager.",
        "feed_id": feed_id,
        "feed_name": feed.name,
        "validator": "mobilitydata",
    }


@router.get("/{feed_id}/validation-report/{validation_id}")
async def get_validation_report(
    feed_id: int,
    validation_id: str,
    report_type: str = Query(
        default="branded",
        description="Report type: 'branded' (custom HTML), 'original' (MobilityData HTML), or 'json'"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get a validation report for a feed.

    Returns the validation report in the specified format.
    """
    from fastapi.responses import FileResponse, JSONResponse
    from app.services.mobilitydata_validator import mobilitydata_validator

    # Verify access
    await verify_feed_access(feed_id, db, current_user, UserRole.VIEWER)

    # Get report path
    report_path = mobilitydata_validator.get_report_path(validation_id, report_type)

    if not report_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Validation report not found: {validation_id}",
        )

    if report_type == "json":
        import json
        with open(report_path, 'r', encoding='utf-8') as f:
            return JSONResponse(content=json.load(f))
    else:
        return FileResponse(
            path=str(report_path),
            media_type="text/html",
            filename=f"validation_report_{validation_id}.html",
        )


@router.post("/{feed_id}/clone")
async def clone_feed(
    feed_id: int,
    new_name: str | None = None,
    target_agency_id: int | None = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Queue an asynchronous task to clone a GTFS feed.

    Creates a complete copy of the feed including all routes, stops, trips,
    stop_times, calendars, and shapes. The new feed is created as inactive.

    - **new_name**: Name for the cloned feed (defaults to "Copy of {original_name}")
    - **target_agency_id**: Agency to clone into (defaults to same agency)

    Returns:
        Task information with task_id for tracking progress
    """
    from app.models.task import AsyncTask, TaskStatus, TaskType
    from app.tasks import clone_feed as clone_feed_task

    # Verify access to source feed (requires VIEWER role to read)
    await verify_feed_access(feed_id, db, current_user, UserRole.VIEWER)

    # Check if feed exists
    query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
    result = await db.execute(query)
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed {feed_id} not found",
        )

    # Set defaults
    clone_name = new_name or f"Copy of {feed.name}"
    clone_agency_id = target_agency_id or feed.agency_id

    # Verify target agency exists and user has EDITOR access
    if target_agency_id:
        agency_query = select(Agency).where(Agency.id == target_agency_id)
        agency_result = await db.execute(agency_query)
        if not agency_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target agency {target_agency_id} not found",
            )
        await verify_agency_access(target_agency_id, db, current_user, UserRole.EDITOR)
    else:
        # Cloning to same agency requires EDITOR access
        await verify_agency_access(feed.agency_id, db, current_user, UserRole.EDITOR)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="gtfs_feed",
        entity_id=str(feed_id),
        description=f"Queued clone of GTFS feed '{feed.name}' as '{clone_name}'",
        new_values={
            "source_feed_id": feed_id,
            "source_feed_name": feed.name,
            "new_name": clone_name,
            "target_agency_id": clone_agency_id,
        },
        agency_id=clone_agency_id,
        request=request,
    )

    # Create task record
    task = AsyncTask(
        celery_task_id="",
        task_type=TaskType.CLONE_FEED,
        task_name=f"Clone Feed: {feed.name}",
        description=f"Cloning GTFS feed '{feed.name}' as '{clone_name}'",
        user_id=current_user.id,
        agency_id=clone_agency_id,
        status=TaskStatus.PENDING,
        progress=0.0,
        input_data={
            "source_feed_id": feed_id,
            "source_feed_name": feed.name,
            "new_name": clone_name,
            "target_agency_id": clone_agency_id,
        }
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Queue Celery task
    celery_task = clone_feed_task.apply_async(
        kwargs={
            "task_db_id": task.id,
            "source_feed_id": feed_id,
            "new_name": clone_name,
            "target_agency_id": clone_agency_id,
        },
        task_id=f"clone_feed_{feed_id}_{task.id}"
    )

    # Update task with Celery task ID
    task.celery_task_id = celery_task.id
    await db.commit()

    return {
        "task_id": task.id,
        "celery_task_id": celery_task.id,
        "status": "queued",
        "message": f"Feed clone queued. Track progress in Task Manager.",
        "source_feed_id": feed_id,
        "new_name": clone_name,
        "target_agency_id": clone_agency_id,
    }


@router.get("/{feed_id}/compare/{other_feed_id}")
async def compare_feeds(
    feed_id: int,
    other_feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compare two GTFS feeds and return a summary of differences.

    Compares routes, stops, trips, and calendars between two feeds.
    Useful for comparing different versions of GTFS data.

    Returns:
        Comparison summary with counts of added, removed, and modified entities
    """
    from app.models.gtfs import Calendar, Shape, StopTime

    # Verify access to both feeds
    await verify_feed_access(feed_id, db, current_user, UserRole.VIEWER)
    await verify_feed_access(other_feed_id, db, current_user, UserRole.VIEWER)

    # Get both feeds
    feed1_query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
    feed1_result = await db.execute(feed1_query)
    feed1 = feed1_result.scalar_one_or_none()

    feed2_query = select(GTFSFeed).where(GTFSFeed.id == other_feed_id)
    feed2_result = await db.execute(feed2_query)
    feed2 = feed2_result.scalar_one_or_none()

    if not feed1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed {feed_id} not found",
        )
    if not feed2:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed {other_feed_id} not found",
        )

    # Compare routes
    routes1_query = select(Route.route_id).where(Route.feed_id == feed_id)
    routes1_result = await db.execute(routes1_query)
    routes1 = set(row[0] for row in routes1_result.all())

    routes2_query = select(Route.route_id).where(Route.feed_id == other_feed_id)
    routes2_result = await db.execute(routes2_query)
    routes2 = set(row[0] for row in routes2_result.all())

    routes_added = routes2 - routes1
    routes_removed = routes1 - routes2
    routes_common = routes1 & routes2

    # Compare stops
    stops1_query = select(Stop.stop_id).where(Stop.feed_id == feed_id)
    stops1_result = await db.execute(stops1_query)
    stops1 = set(row[0] for row in stops1_result.all())

    stops2_query = select(Stop.stop_id).where(Stop.feed_id == other_feed_id)
    stops2_result = await db.execute(stops2_query)
    stops2 = set(row[0] for row in stops2_result.all())

    stops_added = stops2 - stops1
    stops_removed = stops1 - stops2
    stops_common = stops1 & stops2

    # Compare trips
    trips1_query = select(Trip.trip_id).where(Trip.feed_id == feed_id)
    trips1_result = await db.execute(trips1_query)
    trips1 = set(row[0] for row in trips1_result.all())

    trips2_query = select(Trip.trip_id).where(Trip.feed_id == other_feed_id)
    trips2_result = await db.execute(trips2_query)
    trips2 = set(row[0] for row in trips2_result.all())

    trips_added = trips2 - trips1
    trips_removed = trips1 - trips2
    trips_common = trips1 & trips2

    # Compare calendars
    calendars1_query = select(Calendar.service_id).where(Calendar.feed_id == feed_id)
    calendars1_result = await db.execute(calendars1_query)
    calendars1 = set(row[0] for row in calendars1_result.all())

    calendars2_query = select(Calendar.service_id).where(Calendar.feed_id == other_feed_id)
    calendars2_result = await db.execute(calendars2_query)
    calendars2 = set(row[0] for row in calendars2_result.all())

    calendars_added = calendars2 - calendars1
    calendars_removed = calendars1 - calendars2
    calendars_common = calendars1 & calendars2

    # Compare shapes
    shapes1_query = select(Shape.shape_id).where(Shape.feed_id == feed_id).distinct()
    shapes1_result = await db.execute(shapes1_query)
    shapes1 = set(row[0] for row in shapes1_result.all())

    shapes2_query = select(Shape.shape_id).where(Shape.feed_id == other_feed_id).distinct()
    shapes2_result = await db.execute(shapes2_query)
    shapes2 = set(row[0] for row in shapes2_result.all())

    shapes_added = shapes2 - shapes1
    shapes_removed = shapes1 - shapes2
    shapes_common = shapes1 & shapes2

    return {
        "feed1": {
            "id": feed1.id,
            "name": feed1.name,
            "imported_at": feed1.imported_at,
        },
        "feed2": {
            "id": feed2.id,
            "name": feed2.name,
            "imported_at": feed2.imported_at,
        },
        "comparison": {
            "routes": {
                "feed1_count": len(routes1),
                "feed2_count": len(routes2),
                "added": len(routes_added),
                "removed": len(routes_removed),
                "common": len(routes_common),
                "added_ids": list(routes_added)[:50],  # Limit to first 50
                "removed_ids": list(routes_removed)[:50],
            },
            "stops": {
                "feed1_count": len(stops1),
                "feed2_count": len(stops2),
                "added": len(stops_added),
                "removed": len(stops_removed),
                "common": len(stops_common),
                "added_ids": list(stops_added)[:50],
                "removed_ids": list(stops_removed)[:50],
            },
            "trips": {
                "feed1_count": len(trips1),
                "feed2_count": len(trips2),
                "added": len(trips_added),
                "removed": len(trips_removed),
                "common": len(trips_common),
            },
            "calendars": {
                "feed1_count": len(calendars1),
                "feed2_count": len(calendars2),
                "added": len(calendars_added),
                "removed": len(calendars_removed),
                "common": len(calendars_common),
                "added_ids": list(calendars_added)[:50],
                "removed_ids": list(calendars_removed)[:50],
            },
            "shapes": {
                "feed1_count": len(shapes1),
                "feed2_count": len(shapes2),
                "added": len(shapes_added),
                "removed": len(shapes_removed),
                "common": len(shapes_common),
            },
        },
        "summary": {
            "total_changes": (
                len(routes_added) + len(routes_removed) +
                len(stops_added) + len(stops_removed) +
                len(trips_added) + len(trips_removed) +
                len(calendars_added) + len(calendars_removed) +
                len(shapes_added) + len(shapes_removed)
            ),
            "has_changes": (
                bool(routes_added or routes_removed or
                     stops_added or stops_removed or
                     trips_added or trips_removed or
                     calendars_added or calendars_removed or
                     shapes_added or shapes_removed)
            ),
        }
    }
