"""API endpoints for external GTFS feed source management"""

import hashlib
import httpx
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.models.agency import Agency
from app.models.feed_source import (
    ExternalFeedSource,
    FeedSourceCheckLog,
    FeedSourceStatus,
)
from app.schemas.feed_source import (
    FeedSourceCreate,
    FeedSourceUpdate,
    FeedSourceResponse,
    FeedSourceListResponse,
    FeedSourceCheckRequest,
    FeedSourceCheckResponse,
    FeedSourceCheckLogResponse,
    FeedSourceCheckLogListResponse,
)

router = APIRouter()


@router.get("/", response_model=FeedSourceListResponse)
async def list_feed_sources(
    agency_id: Optional[int] = Query(None, description="Filter by agency ID"),
    is_enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    status_filter: Optional[FeedSourceStatus] = Query(None, alias="status", description="Filter by status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FeedSourceListResponse:
    """List external feed sources"""
    from app.models.user import user_agencies

    query = select(ExternalFeedSource)

    # Filter by user's accessible agencies (unless superuser)
    if not current_user.is_superuser:
        user_agency_ids = select(user_agencies.c.agency_id).where(
            user_agencies.c.user_id == current_user.id
        )
        query = query.where(ExternalFeedSource.agency_id.in_(user_agency_ids))

    if agency_id:
        # Verify user has access to this specific agency
        await deps.verify_agency_access(agency_id, db, current_user)
        query = query.where(ExternalFeedSource.agency_id == agency_id)
    if is_enabled is not None:
        query = query.where(ExternalFeedSource.is_enabled == is_enabled)
    if status_filter:
        query = query.where(ExternalFeedSource.status == status_filter.value)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get items
    query = query.offset(skip).limit(limit).order_by(ExternalFeedSource.created_at.desc())
    result = await db.execute(query)
    items = result.scalars().all()

    return FeedSourceListResponse(
        items=[FeedSourceResponse.model_validate(item) for item in items],
        total=total,
    )


@router.post("/", response_model=FeedSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_feed_source(
    feed_source: FeedSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FeedSourceResponse:
    """Create a new external feed source"""
    from app.models.user import UserRole

    # Verify agency exists
    agency = await db.get(Agency, feed_source.agency_id)
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agency {feed_source.agency_id} not found",
        )

    # Verify user has editor access to this agency
    await deps.verify_agency_access(feed_source.agency_id, db, current_user, UserRole.EDITOR)

    # Create feed source
    db_feed_source = ExternalFeedSource(
        name=feed_source.name,
        description=feed_source.description,
        source_type=feed_source.source_type.value,
        url=feed_source.url,
        auth_type=feed_source.auth_type,
        auth_header=feed_source.auth_header,
        auth_value=feed_source.auth_value,
        check_frequency=feed_source.check_frequency.value,
        is_enabled=feed_source.is_enabled,
        auto_import=feed_source.auto_import,
        import_options=feed_source.import_options,
        agency_id=feed_source.agency_id,
        status=FeedSourceStatus.PENDING.value,
    )

    db.add(db_feed_source)
    await db.commit()
    await db.refresh(db_feed_source)

    return FeedSourceResponse.model_validate(db_feed_source)


@router.get("/{feed_source_id}", response_model=FeedSourceResponse)
async def get_feed_source(
    feed_source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FeedSourceResponse:
    """Get a specific feed source"""

    feed_source = await db.get(ExternalFeedSource, feed_source_id)
    if not feed_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed source {feed_source_id} not found",
        )

    # Verify user has access to this feed source's agency
    await deps.verify_agency_access(feed_source.agency_id, db, current_user)

    return FeedSourceResponse.model_validate(feed_source)


@router.patch("/{feed_source_id}", response_model=FeedSourceResponse)
async def update_feed_source(
    feed_source_id: int,
    feed_source_update: FeedSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FeedSourceResponse:
    """Update a feed source"""
    from app.models.user import UserRole

    feed_source = await db.get(ExternalFeedSource, feed_source_id)
    if not feed_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed source {feed_source_id} not found",
        )

    # Verify user has editor access to this feed source's agency
    await deps.verify_agency_access(feed_source.agency_id, db, current_user, UserRole.EDITOR)

    # Update fields
    update_data = feed_source_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(feed_source, field):
            if field in ("source_type", "check_frequency") and value is not None:
                setattr(feed_source, field, value.value)
            else:
                setattr(feed_source, field, value)

    await db.commit()
    await db.refresh(feed_source)

    return FeedSourceResponse.model_validate(feed_source)


@router.delete("/{feed_source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feed_source(
    feed_source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """Delete a feed source"""
    from app.models.user import UserRole

    feed_source = await db.get(ExternalFeedSource, feed_source_id)
    if not feed_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed source {feed_source_id} not found",
        )

    # Verify user has admin access to this feed source's agency
    await deps.verify_agency_access(feed_source.agency_id, db, current_user, UserRole.AGENCY_ADMIN)

    await db.delete(feed_source)
    await db.commit()


@router.post("/{feed_source_id}/check", response_model=FeedSourceCheckResponse)
async def check_feed_source(
    feed_source_id: int,
    check_request: FeedSourceCheckRequest = FeedSourceCheckRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FeedSourceCheckResponse:
    """Manually trigger a check for a feed source"""
    from app.models.user import UserRole

    feed_source = await db.get(ExternalFeedSource, feed_source_id)
    if not feed_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed source {feed_source_id} not found",
        )

    # Verify user has editor access to trigger checks
    await deps.verify_agency_access(feed_source.agency_id, db, current_user, UserRole.EDITOR)

    # Perform the check
    now = datetime.utcnow().isoformat()
    check_log = FeedSourceCheckLog(
        feed_source_id=feed_source_id,
        checked_at=now,
        success=False,
    )

    try:
        # Build headers
        headers = {"User-Agent": "GTFS-Tools/1.0"}
        if feed_source.auth_type == "api_key" and feed_source.auth_header and feed_source.auth_value:
            headers[feed_source.auth_header] = feed_source.auth_value
        elif feed_source.auth_type == "bearer" and feed_source.auth_value:
            headers["Authorization"] = f"Bearer {feed_source.auth_value}"

        # Add conditional headers for change detection
        # Skip conditional headers if:
        # - force_import is True (want fresh content)
        # - last_import_at is None (first time import - need full content to import)
        needs_full_content = check_request.force_import or feed_source.last_import_at is None
        if not needs_full_content:
            if feed_source.last_etag:
                headers["If-None-Match"] = feed_source.last_etag
            if feed_source.last_modified:
                headers["If-Modified-Since"] = feed_source.last_modified

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(feed_source.url, headers=headers, follow_redirects=True)

        check_log.http_status = response.status_code

        if response.status_code == 304:
            # Not modified
            check_log.success = True
            check_log.content_changed = False
            feed_source.status = FeedSourceStatus.ACTIVE.value
            feed_source.last_checked_at = now
            feed_source.last_successful_check = now
            feed_source.error_count = 0

            db.add(check_log)
            await db.commit()

            return FeedSourceCheckResponse(
                success=True,
                message="Feed has not changed since last check",
                content_changed=False,
                import_triggered=False,
            )

        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text[:500]}")

        # Calculate content hash
        content = response.content
        content_hash = hashlib.sha256(content).hexdigest()
        check_log.content_size = len(content)
        check_log.content_hash = content_hash

        # Check if content changed
        content_changed = content_hash != feed_source.last_content_hash
        check_log.content_changed = content_changed

        # Update feed source
        feed_source.status = FeedSourceStatus.ACTIVE.value
        feed_source.last_checked_at = now
        feed_source.last_successful_check = now
        feed_source.last_content_hash = content_hash
        feed_source.error_count = 0

        # Store ETag and Last-Modified for future checks
        if "etag" in response.headers:
            feed_source.last_etag = response.headers["etag"]
        if "last-modified" in response.headers:
            feed_source.last_modified = response.headers["last-modified"]

        check_log.success = True

        # Trigger import if:
        # 1. First time check (no prior import) - always import on first successful check
        # 2. Content changed and auto_import is enabled
        # 3. Force import is requested
        import_triggered = False
        task_id = None
        is_first_check = feed_source.last_import_at is None

        if is_first_check or (content_changed and feed_source.auto_import) or check_request.force_import:
            # Import the Celery task
            from app.tasks import import_gtfs

            # Create import task
            from app.db.base import AsyncTask
            from app.models.task import TaskStatus, TaskType

            task_record = AsyncTask(
                celery_task_id=str(uuid.uuid4()),  # Temporary UUID, will be replaced with Celery task ID
                task_name=f"Import from {feed_source.name}",
                description=f"Automatic import from external feed source: {feed_source.url}",
                task_type=TaskType.IMPORT_GTFS.value,
                user_id=current_user.id,
                agency_id=feed_source.agency_id,
                status=TaskStatus.PENDING.value,
                progress=0.0,
                input_data={
                    "feed_source_id": feed_source_id,
                    "feed_name": f"{feed_source.name} - {now[:10]}",
                },
            )
            db.add(task_record)
            await db.flush()

            # Queue import task - pass content as bytes directly
            celery_result = import_gtfs.apply_async(
                kwargs={
                    "task_db_id": task_record.id,
                    "file_content": content,
                    "agency_id": feed_source.agency_id,
                    "feed_name": f"{feed_source.name} - {now[:10]}",
                    "feed_description": f"Imported from {feed_source.url}",
                }
            )

            task_record.celery_task_id = celery_result.id
            task_id = str(task_record.id)
            import_triggered = True

            check_log.import_triggered = True
            check_log.import_task_id = task_id

            feed_source.last_import_at = now

        db.add(check_log)
        await db.commit()

        return FeedSourceCheckResponse(
            success=True,
            message="Feed checked successfully" + (" - content changed" if content_changed else " - no changes"),
            content_changed=content_changed,
            import_triggered=import_triggered,
            task_id=task_id,
        )

    except Exception as e:
        # Log the error
        check_log.success = False
        check_log.error_message = str(e)[:1000]

        feed_source.status = FeedSourceStatus.ERROR.value
        feed_source.last_checked_at = now
        feed_source.error_count += 1
        feed_source.last_error = str(e)[:1000]

        db.add(check_log)
        await db.commit()

        return FeedSourceCheckResponse(
            success=False,
            message=f"Check failed: {str(e)[:200]}",
            content_changed=False,
            import_triggered=False,
        )


@router.get("/{feed_source_id}/logs", response_model=FeedSourceCheckLogListResponse)
async def list_feed_source_logs(
    feed_source_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FeedSourceCheckLogListResponse:
    """Get check history for a feed source"""

    feed_source = await db.get(ExternalFeedSource, feed_source_id)
    if not feed_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed source {feed_source_id} not found",
        )

    # Verify user has access to this feed source's agency
    await deps.verify_agency_access(feed_source.agency_id, db, current_user)

    # Count total
    count_query = select(func.count(FeedSourceCheckLog.id)).where(
        FeedSourceCheckLog.feed_source_id == feed_source_id
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get logs
    query = (
        select(FeedSourceCheckLog)
        .where(FeedSourceCheckLog.feed_source_id == feed_source_id)
        .order_by(FeedSourceCheckLog.checked_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    logs = result.scalars().all()

    return FeedSourceCheckLogListResponse(
        items=[FeedSourceCheckLogResponse.model_validate(log) for log in logs],
        total=total,
    )


@router.post("/{feed_source_id}/enable", response_model=FeedSourceResponse)
async def enable_feed_source(
    feed_source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FeedSourceResponse:
    """Enable a feed source"""
    from app.models.user import UserRole

    feed_source = await db.get(ExternalFeedSource, feed_source_id)
    if not feed_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed source {feed_source_id} not found",
        )

    # Verify user has editor access to enable feed sources
    await deps.verify_agency_access(feed_source.agency_id, db, current_user, UserRole.EDITOR)

    feed_source.is_enabled = True
    feed_source.status = FeedSourceStatus.PENDING.value
    await db.commit()
    await db.refresh(feed_source)

    return FeedSourceResponse.model_validate(feed_source)


@router.post("/{feed_source_id}/disable", response_model=FeedSourceResponse)
async def disable_feed_source(
    feed_source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FeedSourceResponse:
    """Disable a feed source"""
    from app.models.user import UserRole

    feed_source = await db.get(ExternalFeedSource, feed_source_id)
    if not feed_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feed source {feed_source_id} not found",
        )

    # Verify user has editor access to disable feed sources
    await deps.verify_agency_access(feed_source.agency_id, db, current_user, UserRole.EDITOR)

    feed_source.is_enabled = False
    feed_source.status = FeedSourceStatus.PAUSED.value
    await db.commit()
    await db.refresh(feed_source)

    return FeedSourceResponse.model_validate(feed_source)
