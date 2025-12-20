"""Asynchronous task management endpoints"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import get_db
from app.models.user import User
from app.models.task import AsyncTask, TaskStatus, TaskType
from app.schemas.task import TaskResponse, TaskList, TaskUpdate
from app.celery_app import celery_app

router = APIRouter()


@router.get("/", response_model=TaskList)
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[TaskStatus] = None,
    task_type: Optional[TaskType] = None,
    agency_id: Optional[int] = None,
) -> TaskList:
    """
    List tasks for the current user.

    - Super admins can see all tasks
    - Other users see only their own tasks
    """
    # Build base query
    query = select(AsyncTask)

    # Filter by user (non-superusers can only see their own tasks)
    if not current_user.is_superuser:
        query = query.where(AsyncTask.user_id == current_user.id)

    # Apply filters
    if status:
        query = query.where(cast(AsyncTask.status, String) == status.value)

    if task_type:
        query = query.where(cast(AsyncTask.task_type, String) == task_type.value)

    if agency_id:
        query = query.where(AsyncTask.agency_id == agency_id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results (newest first)
    query = query.offset(skip).limit(limit).order_by(AsyncTask.created_at.desc())
    result = await db.execute(query)
    tasks = result.scalars().all()

    return TaskList(
        items=[TaskResponse.model_validate(task) for task in tasks],
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.get("/active/count", response_model=dict)
async def get_active_task_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict:
    """
    Get count of active (pending + running) tasks for the current user.
    """
    query = select(func.count()).select_from(AsyncTask).where(
        AsyncTask.user_id == current_user.id,
        cast(AsyncTask.status, String).in_([TaskStatus.PENDING.value, TaskStatus.RUNNING.value])
    )

    count = await db.scalar(query)

    return {
        "active_tasks": count or 0
    }


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> AsyncTask:
    """
    Get task details by ID.
    """
    result = await db.execute(select(AsyncTask).where(AsyncTask.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    # Check access (users can only see their own tasks unless superuser)
    if not current_user.is_superuser and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )

    return task


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task_in: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> AsyncTask:
    """
    Update task status and progress.

    This endpoint is primarily used by Celery tasks to update their status.
    """
    result = await db.execute(select(AsyncTask).where(AsyncTask.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    # Check access
    if not current_user.is_superuser and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )

    # Update task
    update_data = task_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        # Convert enum values to their string representation
        if isinstance(value, (TaskStatus, TaskType)):
            value = value.value
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)

    return task


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> AsyncTask:
    """
    Retry a failed import task.

    This will re-trigger the import from the original feed source.
    Only works for failed import tasks that have a feed_source_id in input_data.
    """
    from app.models.feed_source import ExternalFeedSource

    result = await db.execute(select(AsyncTask).where(AsyncTask.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    # Check access
    if not current_user.is_superuser and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )

    # Can only retry failed tasks
    if task.status != TaskStatus.FAILED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only retry failed tasks. Current status: {task.status}",
        )

    # Check if result_data indicates this task can be retried
    if not task.result_data or not task.result_data.get("can_retry"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This task cannot be retried. Missing retry information.",
        )

    # For import tasks, we need feed_source_id to retry
    if task.task_type == TaskType.IMPORT_GTFS.value:
        import httpx
        import uuid
        from datetime import datetime
        from app.tasks import import_gtfs

        feed_source_id = task.input_data.get("feed_source_id") if task.input_data else None

        if not feed_source_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot retry: missing feed source information.",
            )

        # Get the feed source
        source_result = await db.execute(
            select(ExternalFeedSource).where(ExternalFeedSource.id == feed_source_id)
        )
        feed_source = source_result.scalar_one_or_none()

        if not feed_source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Feed source {feed_source_id} not found.",
            )

        # Download the GTFS file from the feed source
        try:
            headers = {"User-Agent": "GTFS-Tools/1.0"}
            if feed_source.auth_type == "api_key" and feed_source.auth_header and feed_source.auth_value:
                headers[feed_source.auth_header] = feed_source.auth_value
            elif feed_source.auth_type == "bearer" and feed_source.auth_value:
                headers["Authorization"] = f"Bearer {feed_source.auth_value}"

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.get(feed_source.url, headers=headers, follow_redirects=True)
                response.raise_for_status()
                file_content = response.content
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to download GTFS file from feed source: {str(e)}",
            )

        # Create a new task record first
        new_task = AsyncTask(
            celery_task_id=str(uuid.uuid4()),  # Temporary, will be replaced
            task_type=TaskType.IMPORT_GTFS.value,
            task_name=f"Retry: {task.task_name}",
            description=f"Retry of failed task #{task.id}",
            user_id=current_user.id,
            agency_id=feed_source.agency_id,
            status=TaskStatus.PENDING.value,
            progress=0.0,
            input_data={
                "feed_source_id": feed_source_id,
                "retry_of_task_id": task.id,
                "feed_name": task.input_data.get("feed_name", f"Retry - {datetime.utcnow().strftime('%Y-%m-%d')}"),
            },
        )
        db.add(new_task)
        await db.flush()  # Get the task ID

        # Queue the import task
        celery_result = import_gtfs.apply_async(
            kwargs={
                "task_db_id": new_task.id,
                "file_content": file_content,
                "agency_id": feed_source.agency_id,
                "replace_existing": task.input_data.get("replace_existing", False) if task.input_data else False,
                "skip_shapes": task.input_data.get("skip_shapes", False) if task.input_data else False,
                "feed_name": task.input_data.get("feed_name", f"Retry - {datetime.utcnow().strftime('%Y-%m-%d')}") if task.input_data else f"Retry - {datetime.utcnow().strftime('%Y-%m-%d')}",
            }
        )

        # Update the task with the real Celery task ID
        new_task.celery_task_id = celery_result.id
        await db.commit()
        await db.refresh(new_task)

        return new_task

    # For delete feed tasks, we need feed_id to retry
    if task.task_type == TaskType.DELETE_FEED.value:
        import uuid
        from app.models.gtfs import GTFSFeed
        from app.tasks import delete_feed as delete_feed_task

        feed_id = task.input_data.get("feed_id") if task.input_data else None

        if not feed_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot retry: missing feed ID information.",
            )

        # Check if the feed still exists
        feed_result = await db.execute(
            select(GTFSFeed).where(GTFSFeed.id == feed_id)
        )
        feed = feed_result.scalar_one_or_none()

        if not feed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Feed {feed_id} not found. It may have already been deleted.",
            )

        # Create a new task record
        new_task = AsyncTask(
            celery_task_id=str(uuid.uuid4()),  # Temporary, will be replaced
            task_type=TaskType.DELETE_FEED.value,
            task_name=f"Retry: {task.task_name}",
            description=f"Retry of failed task #{task.id}",
            user_id=current_user.id,
            agency_id=task.agency_id,
            status=TaskStatus.PENDING.value,
            progress=0.0,
            input_data={
                "feed_id": feed_id,
                "feed_name": task.input_data.get("feed_name", feed.name),
                "retry_of_task_id": task.id,
            },
        )
        db.add(new_task)
        await db.flush()  # Get the task ID

        # Queue the delete feed task
        celery_result = delete_feed_task.apply_async(
            args=[new_task.id, feed_id],
            task_id=f"delete_feed_{feed_id}_{new_task.id}"
        )

        # Update the task with the real Celery task ID
        new_task.celery_task_id = celery_result.id
        await db.commit()
        await db.refresh(new_task)

        return new_task

    # For validation tasks, retry with the stored file
    if task.task_type == TaskType.VALIDATE_GTFS.value:
        import uuid
        from pathlib import Path
        from app.tasks import validate_gtfs_file_mobilitydata

        # Get file path from input_data or result_data
        gtfs_file_path = None
        filename = None
        country_code = ""

        if task.input_data:
            gtfs_file_path = task.input_data.get("gtfs_file_path")
            filename = task.input_data.get("filename")
            country_code = task.input_data.get("country_code", "")

        if not gtfs_file_path and task.result_data:
            gtfs_file_path = task.result_data.get("gtfs_file_path")
            filename = task.result_data.get("filename")

        if not gtfs_file_path or not Path(gtfs_file_path).exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot retry: GTFS file no longer available. Please upload again.",
            )

        # Read the file content
        with open(gtfs_file_path, 'rb') as f:
            file_content = f.read()

        # Create a new task record
        new_task = AsyncTask(
            celery_task_id=str(uuid.uuid4()),  # Temporary, will be replaced
            task_type=TaskType.VALIDATE_GTFS.value,
            task_name=f"Retry: {task.task_name}",
            description=f"Retry of failed task #{task.id}",
            user_id=current_user.id,
            agency_id=task.agency_id,
            status=TaskStatus.PENDING.value,
            progress=0.0,
            input_data={
                "filename": filename,
                "country_code": country_code,
                "retry_of_task_id": task.id,
            },
        )
        db.add(new_task)
        await db.flush()  # Get the task ID

        # Queue the validation task
        celery_result = validate_gtfs_file_mobilitydata.apply_async(
            kwargs={
                "task_db_id": new_task.id,
                "file_content": file_content,
                "filename": filename or "upload.zip",
                "country_code": country_code,
            }
        )

        # Update the task with the real Celery task ID
        new_task.celery_task_id = celery_result.id
        await db.commit()
        await db.refresh(new_task)

        return new_task

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Retry not supported for task type: {task.task_type}",
    )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Cancel a running task.

    - Users can cancel their own tasks
    - Super admins can cancel any task
    - This will immediately terminate the Celery worker processing this task
    """
    result = await db.execute(select(AsyncTask).where(AsyncTask.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    # Check access
    if not current_user.is_superuser and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this task",
        )

    # Can only cancel pending or running tasks
    # Note: task.status is read from DB as a string, so compare directly
    if task.status not in [TaskStatus.PENDING.value, TaskStatus.RUNNING.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel task with status: {task.status}",
        )

    # Revoke the Celery task immediately with terminate=True to kill the worker
    if task.celery_task_id:
        celery_app.control.revoke(task.celery_task_id, terminate=True, signal='SIGKILL')

    # Update task status to cancelled
    task.status = TaskStatus.CANCELLED.value
    from datetime import datetime
    task.completed_at = datetime.utcnow().isoformat() + 'Z'
    task.error_message = "Task cancelled by user"
    await db.commit()
