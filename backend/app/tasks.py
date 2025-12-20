"""Celery tasks for background processing"""

import asyncio
import io
import traceback
import uuid
from datetime import datetime
from typing import Dict, Any
from celery import Task
from celery.exceptions import Terminated
from sqlalchemy import select, func

from app.celery_app import celery_app
from app.db.session import CeleryAsyncSessionLocal
# Import from db.base to ensure all models are loaded in correct order
from app.db.base import AsyncTask, User, Agency
from app.models.task import TaskStatus, TaskType
from app.services.gtfs_service import gtfs_service
from app.services.gtfs_validator import GTFSValidator
from app.schemas.gtfs_import import GTFSImportOptions


class TaskCancelledException(Exception):
    """Exception raised when a task has been cancelled"""
    pass


async def check_task_cancelled(db, task_db_id: int) -> bool:
    """
    Check if a task has been cancelled in the database.
    Call this periodically in long-running tasks.

    Returns True if the task should stop (cancelled or not found).
    """
    result = await db.execute(
        select(AsyncTask.status).where(AsyncTask.id == task_db_id)
    )
    status = result.scalar_one_or_none()

    if status is None:
        return True  # Task not found, stop

    return status == TaskStatus.CANCELLED.value


async def mark_task_cancelled(db, task) -> None:
    """Mark a task as cancelled with proper cleanup"""
    task.status = TaskStatus.CANCELLED.value
    task.completed_at = datetime.utcnow().isoformat() + 'Z'
    task.error_message = "Task was cancelled"
    await db.commit()


class DatabaseTask(Task):
    """Base task that provides database session"""

    _session = None

    @property
    def session(self):
        if self._session is None:
            self._session = CeleryAsyncSessionLocal()
        return self._session


@celery_app.task(name="app.tasks.cleanup_old_tasks")
def cleanup_old_tasks():
    """
    Cleanup old completed tasks from the database.
    Removes completed/failed tasks older than 30 days.
    """
    from datetime import timedelta
    from sqlalchemy import delete, and_

    async def run_cleanup():
        async with CeleryAsyncSessionLocal() as db:
            try:
                cutoff_date = datetime.utcnow() - timedelta(days=30)

                # Delete old completed/failed tasks
                result = await db.execute(
                    delete(AsyncTask).where(
                        and_(
                            AsyncTask.status.in_([
                                TaskStatus.COMPLETED.value,
                                TaskStatus.FAILED.value,
                                TaskStatus.CANCELLED.value
                            ]),
                            AsyncTask.completed_at < cutoff_date.isoformat()
                        )
                    )
                )

                deleted_count = result.rowcount
                await db.commit()

                return {"status": "success", "deleted_count": deleted_count}

            except Exception as e:
                await db.rollback()
                return {"status": "error", "message": str(e)}

    # Create a new event loop for each task run to avoid loop conflicts
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_cleanup())
    finally:
        loop.close()


@celery_app.task(name="app.tasks.check_orphaned_tasks")
def check_orphaned_tasks():
    """
    Periodic task to check for orphaned tasks.
    Orphaned tasks include:
    1. Tasks that have been 'running' for more than 30 minutes without progress (worker died)
    2. Tasks that have been 'pending' for more than 1 hour (Celery task was lost/never picked up)
    """
    from datetime import timedelta
    from sqlalchemy import select, or_

    async def run_check():
        async with CeleryAsyncSessionLocal() as db:
            try:
                now = datetime.utcnow()
                running_cutoff = now - timedelta(minutes=30)
                pending_cutoff = now - timedelta(hours=1)

                # Find tasks that are running or pending
                result = await db.execute(
                    select(AsyncTask).where(
                        or_(
                            AsyncTask.status == TaskStatus.RUNNING.value,
                            AsyncTask.status == TaskStatus.PENDING.value,
                        )
                    )
                )
                tasks = result.scalars().all()

                orphaned_running = 0
                orphaned_pending = 0

                for task in tasks:
                    if task.status == TaskStatus.RUNNING.value:
                        # Check running tasks - 30 minutes without progress
                        last_update = task.updated_at if task.updated_at else task.started_at
                        if last_update:
                            if isinstance(last_update, str):
                                last_update_dt = datetime.fromisoformat(
                                    last_update.replace('Z', '+00:00')
                                ).replace(tzinfo=None)
                            else:
                                last_update_dt = last_update.replace(tzinfo=None) if last_update.tzinfo else last_update

                            if last_update_dt < running_cutoff:
                                task.status = TaskStatus.FAILED.value
                                task.completed_at = now.isoformat() + 'Z'
                                task.error_message = (
                                    "Task timed out - no progress updates for 30+ minutes. "
                                    f"Progress was at {task.progress:.1f}%. "
                                    "The worker may have crashed. You may retry the operation."
                                )
                                task.result_data = {
                                    **(task.result_data or {}),
                                    "orphaned": True,
                                    "orphan_type": "running_timeout",
                                    "orphaned_at": now.isoformat() + 'Z',
                                    "last_progress": task.progress,
                                    "can_retry": True,
                                }
                                orphaned_running += 1

                    elif task.status == TaskStatus.PENDING.value:
                        # Check pending tasks - 1 hour without being picked up
                        created_at = task.created_at
                        if created_at:
                            if isinstance(created_at, str):
                                created_at_dt = datetime.fromisoformat(
                                    created_at.replace('Z', '+00:00')
                                ).replace(tzinfo=None)
                            else:
                                created_at_dt = created_at.replace(tzinfo=None) if created_at.tzinfo else created_at

                            if created_at_dt < pending_cutoff:
                                task.status = TaskStatus.FAILED.value
                                task.completed_at = now.isoformat() + 'Z'
                                task.error_message = (
                                    "Task was never started - pending for over 1 hour. "
                                    "The Celery task may have been lost or the worker was unavailable. "
                                    "You may retry the operation."
                                )
                                task.result_data = {
                                    **(task.result_data or {}),
                                    "orphaned": True,
                                    "orphan_type": "pending_lost",
                                    "orphaned_at": now.isoformat() + 'Z',
                                    "can_retry": True,
                                }
                                orphaned_pending += 1

                total_orphaned = orphaned_running + orphaned_pending
                if total_orphaned > 0:
                    await db.commit()

                return {
                    "status": "success",
                    "orphaned_count": total_orphaned,
                    "orphaned_running": orphaned_running,
                    "orphaned_pending": orphaned_pending,
                }

            except Exception as e:
                await db.rollback()
                return {"status": "error", "message": str(e)}

    # Create a new event loop for each task run to avoid loop conflicts
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_check())
    finally:
        loop.close()


@celery_app.task(name="app.tasks.import_gtfs", bind=True)
def import_gtfs(
    self,
    task_db_id: int,
    file_content: bytes,
    agency_id: int,
    replace_existing: bool = False,
    validate_only: bool = False,
    skip_shapes: bool = False,
    stop_on_error: bool = False,
    feed_name: str | None = None,
    feed_description: str | None = None,
    feed_version: str | None = None,
):
    """
    Import GTFS data from a file asynchronously

    Args:
        task_db_id: AsyncTask record ID in database
        file_content: GTFS ZIP file content as bytes
        agency_id: Agency ID to import data for
        replace_existing: Replace existing GTFS data
        validate_only: Only validate, don't import
        skip_shapes: Skip importing shapes.txt
        stop_on_error: Stop import if validation errors found
        feed_name: Name for the GTFS feed
        feed_description: Description for the GTFS feed
        feed_version: Version identifier for the GTFS feed
    """

    async def run_import():
        """Async function to run the import"""
        task = None
        async with CeleryAsyncSessionLocal() as db:
            try:
                # Get the task record
                result = await db.execute(
                    select(AsyncTask).where(AsyncTask.id == task_db_id)
                )
                task = result.scalar_one_or_none()

                if not task:
                    return {
                        "success": False,
                        "error": f"Task record {task_db_id} not found"
                    }

                # Check if task was cancelled before we even started
                if task.status == TaskStatus.CANCELLED.value:
                    return {
                        "success": False,
                        "error": "Task was cancelled before starting",
                        "task_id": task_db_id,
                    }

                # Update task status to RUNNING
                task.status = TaskStatus.RUNNING.value
                task.started_at = datetime.utcnow().isoformat() + 'Z'
                task.progress = 0.0
                await db.commit()

                # Create file object from bytes
                file_obj = io.BytesIO(file_content)

                # Create import options
                options = GTFSImportOptions(
                    agency_id=agency_id,
                    replace_existing=replace_existing,
                    validate_only=validate_only,
                    skip_shapes=skip_shapes,
                    stop_on_error=stop_on_error,
                )

                # Get filename from task input_data if available
                filename = "gtfs.zip"
                if task.input_data and 'filename' in task.input_data:
                    filename = task.input_data['filename']

                # Track progress through file imports
                files_to_import = ["routes.txt", "stops.txt", "calendar.txt",
                                  "trips.txt", "stop_times.txt", "calendar_dates.txt"]
                if not skip_shapes:
                    files_to_import.append("shapes.txt")

                total_files = len(files_to_import)

                # Update progress: validation phase
                task.progress = 5.0
                await db.commit()

                # Define progress callback to update task during import
                last_progress_update = [0.0]  # Use list for mutable in closure

                async def update_progress(progress: float, message: str):
                    """Update task progress in database during import"""
                    # Only update if progress changed by at least 1%
                    if progress - last_progress_update[0] >= 1.0:
                        task.progress = progress
                        task.result_data = {
                            **(task.result_data or {}),
                            "current_step": message
                        }
                        await db.commit()
                        last_progress_update[0] = progress
                        print(f"[IMPORT TASK {task_db_id}] Progress: {progress:.1f}% - {message}")

                # Run the import with progress callback
                import_result = await gtfs_service.import_gtfs_zip(
                    file_obj, options, db, filename,
                    feed_name=feed_name,
                    feed_description=feed_description,
                    feed_version=feed_version,
                    progress_callback=update_progress
                )

                # Calculate final progress based on files processed
                files_processed = len(import_result.files_processed)
                progress = min(90.0, (files_processed / total_files) * 90)
                task.progress = progress
                await db.commit()

                # Run validation if import was successful and not in validate_only mode
                validation_result = None
                if import_result.success and not validate_only:
                    task.progress = 95.0
                    await db.commit()

                    # Get the feed_id from the import result
                    if hasattr(import_result, 'feed_id') and import_result.feed_id:
                        validator = GTFSValidator(db)
                        validation_result = await validator.validate_feed(import_result.feed_id)

                # Update task with result
                if import_result.success:
                    task.status = TaskStatus.COMPLETED.value
                    task.progress = 100.0
                    result_data = {
                        "success": True,
                        "total_imported": import_result.total_imported,
                        "total_updated": import_result.total_updated,
                        "total_skipped": import_result.total_skipped,
                        "total_errors": import_result.total_errors,
                        "files_processed": [
                            {
                                "filename": f.filename,
                                "imported": f.imported,
                                "updated": f.updated,
                                "skipped": f.skipped,
                                "errors": f.errors,
                            }
                            for f in import_result.files_processed
                        ],
                        "validation_warnings": import_result.validation_warnings,
                        "duration_seconds": import_result.duration_seconds,
                    }

                    # Add validation results if available
                    if validation_result:
                        result_data["validation"] = validation_result.to_dict()

                    task.result_data = result_data
                else:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = "; ".join(import_result.validation_errors or ["Import failed"])
                    task.result_data = {
                        "success": False,
                        "validation_errors": import_result.validation_errors,
                        "validation_warnings": import_result.validation_warnings,
                        "total_errors": import_result.total_errors,
                    }

                task.completed_at = datetime.utcnow().isoformat() + 'Z'
                await db.commit()

                return {
                    "success": import_result.success,
                    "task_id": task_db_id,
                }

            except Exception as e:
                # Update task as failed (only if task was found)
                if task:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = str(e)
                    task.error_traceback = traceback.format_exc()
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()

                return {
                    "success": False,
                    "error": str(e),
                    "task_id": task_db_id,
                }

    # Always use asyncio.run() for clean event loop management
    return asyncio.run(run_import())


@celery_app.task(name="app.tasks.export_gtfs")
def export_gtfs(agency_id: int):
    """
    Export GTFS data to a file (async version) - DEPRECATED.

    Note: Use generate_gtfs_export_task instead for the export wizard.
    """
    return {
        "status": "deprecated",
        "message": "Use generate_gtfs_export_task instead",
        "agency_id": agency_id,
    }


@celery_app.task(name="app.tasks.generate_gtfs_export_task", bind=True)
def generate_gtfs_export_task(
    self,
    task_db_id: int,
    export_id: str,
    feed_id: int,
):
    """
    Generate GTFS export and validate it (Export Wizard Step 1).

    This task:
    1. Exports the feed to a temporary GTFS ZIP file
    2. Validates the ZIP using MobilityData validator
    3. Stores both files for download in the export wizard

    Args:
        task_db_id: AsyncTask record ID in database
        export_id: Unique ID for this export (used for file storage)
        feed_id: ID of the GTFS feed to export
    """

    async def run_export():
        """Async function to run the export and validation"""
        task = None
        async with CeleryAsyncSessionLocal() as db:
            try:
                # Get the task record
                result = await db.execute(
                    select(AsyncTask).where(AsyncTask.id == task_db_id)
                )
                task = result.scalar_one_or_none()

                if not task:
                    return {
                        "success": False,
                        "error": f"Task record {task_db_id} not found"
                    }

                # Check if task was cancelled before we even started
                if task.status == TaskStatus.CANCELLED.value:
                    return {
                        "success": False,
                        "error": "Task was cancelled before starting",
                        "task_id": task_db_id,
                    }

                # Update task status to RUNNING
                task.status = TaskStatus.RUNNING.value
                task.started_at = datetime.utcnow().isoformat() + 'Z'
                task.progress = 0.0
                task.result_data = {"status": "Starting export..."}
                await db.commit()

                # Get the feed
                from app.models.gtfs import GTFSFeed
                feed_query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
                feed_result = await db.execute(feed_query)
                feed = feed_result.scalar_one_or_none()

                if not feed:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = f"Feed {feed_id} not found"
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()
                    return {"success": False, "error": f"Feed {feed_id} not found"}

                task.progress = 10.0
                task.result_data = {"status": "Exporting GTFS feed to ZIP..."}
                await db.commit()

                # Create output directory for this export
                from app.services.mobilitydata_validator import mobilitydata_validator
                from pathlib import Path
                import json

                output_dir = mobilitydata_validator.output_base_path / f"export_{export_id}"
                output_dir.mkdir(parents=True, exist_ok=True)

                # Export the feed to a temporary GTFS ZIP file
                from app.services.gtfs_service import GTFSService
                from app.schemas.gtfs_import import GTFSExportOptions

                export_options = GTFSExportOptions(
                    agency_id=feed.agency_id,
                    feed_id=feed_id
                )

                try:
                    zip_content = await GTFSService.export_gtfs_zip(export_options, db)
                except Exception as e:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = f"Failed to export feed: {str(e)}"
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()
                    return {"success": False, "error": f"Failed to export feed: {str(e)}"}

                # Save the GTFS ZIP file
                gtfs_file = output_dir / "gtfs.zip"
                with open(gtfs_file, 'wb') as f:
                    f.write(zip_content)

                # Save metadata
                metadata = {
                    "export_id": export_id,
                    "feed_id": feed_id,
                    "feed_name": feed.name,
                    "agency_id": feed.agency_id,
                    "exported_at": datetime.utcnow().isoformat() + 'Z',
                    "file_size": len(zip_content),
                }
                with open(output_dir / "metadata.json", 'w') as f:
                    json.dump(metadata, f, indent=2)

                task.progress = 40.0
                task.result_data = {
                    "status": "Validating GTFS file...",
                    "gtfs_file_size": len(zip_content),
                }
                await db.commit()

                # Validate the exported GTFS file
                try:
                    validation_result = await mobilitydata_validator.validate_feed_file(
                        gtfs_zip_path=str(gtfs_file),
                        feed_name=feed.name,
                    )
                except Exception as e:
                    logger.warning(f"Validation failed, but export is still available: {e}")
                    validation_result = {
                        "success": False,
                        "error": str(e),
                    }

                task.progress = 80.0
                task.result_data = {
                    "status": "Processing validation results...",
                    "gtfs_file_size": len(zip_content),
                }
                await db.commit()

                # If validation was successful, copy the reports to our export directory
                if validation_result.get("success"):
                    import shutil

                    val_output_dir = Path(validation_result.get("output_dir", ""))
                    if val_output_dir.exists():
                        # Copy report files
                        for report_file in ["report.json", "report.html", "report_branded.html"]:
                            src = val_output_dir / report_file
                            if src.exists():
                                shutil.copy(src, output_dir / report_file)

                    validation_summary = {
                        "valid": validation_result.get("report_json", {}).get("notices", []) == [] or
                                 not any(n.get("severity") == "ERROR" for n in validation_result.get("report_json", {}).get("notices", [])),
                        "error_count": sum(1 for n in validation_result.get("report_json", {}).get("notices", []) if n.get("severity") == "ERROR"),
                        "warning_count": sum(1 for n in validation_result.get("report_json", {}).get("notices", []) if n.get("severity") == "WARNING"),
                        "info_count": sum(1 for n in validation_result.get("report_json", {}).get("notices", []) if n.get("severity") == "INFO"),
                        "duration_seconds": validation_result.get("duration_seconds", 0),
                    }
                else:
                    validation_summary = {
                        "valid": False,
                        "error": validation_result.get("error", "Validation failed"),
                        "error_count": 0,
                        "warning_count": 0,
                        "info_count": 0,
                    }

                # Complete the task
                task.status = TaskStatus.COMPLETED.value
                task.progress = 100.0
                task.completed_at = datetime.utcnow().isoformat() + 'Z'
                task.result_data = {
                    "success": True,
                    "export_id": export_id,
                    "feed_id": feed_id,
                    "feed_name": feed.name,
                    "gtfs_file_size": len(zip_content),
                    "validation": validation_summary,
                }
                await db.commit()

                return task.result_data

            except Exception as e:
                logger.exception(f"Export task failed: {e}")
                if task:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = str(e)
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()
                return {"success": False, "error": str(e)}

    # Always use asyncio.run() for clean event loop management
    return asyncio.run(run_export())


@celery_app.task(name="app.tasks.validate_gtfs", bind=True)
def validate_gtfs(
    self,
    task_db_id: int,
    feed_id: int,
    agency_id: int,
):
    """
    Validate GTFS data for a feed asynchronously.

    Uses the agency's validation preferences to run enabled validations
    and stores results in the task record.

    Args:
        task_db_id: AsyncTask record ID in database
        feed_id: ID of the GTFS feed to validate
        agency_id: ID of the agency (for validation preferences)
    """

    async def run_validation():
        """Async function to run the validation"""
        task = None
        async with CeleryAsyncSessionLocal() as db:
            try:
                # Get the task record
                result = await db.execute(
                    select(AsyncTask).where(AsyncTask.id == task_db_id)
                )
                task = result.scalar_one_or_none()

                if not task:
                    return {
                        "success": False,
                        "error": f"Task record {task_db_id} not found"
                    }

                # Check if task was cancelled before we even started
                if task.status == TaskStatus.CANCELLED.value:
                    return {
                        "success": False,
                        "error": "Task was cancelled before starting",
                        "task_id": task_db_id,
                    }

                # Update task status to RUNNING
                task.status = TaskStatus.RUNNING.value
                task.started_at = datetime.utcnow().isoformat() + 'Z'
                task.progress = 0.0
                await db.commit()

                # Get the feed to validate
                from app.models.gtfs import GTFSFeed
                feed_query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
                feed_result = await db.execute(feed_query)
                feed = feed_result.scalar_one_or_none()

                if not feed:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = f"Feed {feed_id} not found"
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()
                    return {
                        "success": False,
                        "error": f"Feed {feed_id} not found",
                    }

                task.progress = 10.0
                await db.commit()

                # Run validation using the GTFSValidator service
                validator = GTFSValidator(db)

                # Update progress during validation phases
                task.progress = 20.0
                task.result_data = {"status": "Running validations..."}
                await db.commit()

                # Run the actual validation
                validation_result = await validator.validate_feed(feed_id)

                task.progress = 90.0
                await db.commit()

                # Convert validation result to dict
                result_dict = validation_result.to_dict()

                # Update task with result
                task.status = TaskStatus.COMPLETED.value
                task.progress = 100.0
                task.completed_at = datetime.utcnow().isoformat() + 'Z'
                task.result_data = {
                    "success": True,
                    "feed_id": feed_id,
                    "feed_name": feed.name,
                    "validation": result_dict,
                    "valid": result_dict.get("valid", False),
                    "error_count": result_dict.get("error_count", 0),
                    "warning_count": result_dict.get("warning_count", 0),
                    "info_count": result_dict.get("info_count", 0),
                    "summary": result_dict.get("summary", ""),
                }
                await db.commit()

                return {
                    "success": True,
                    "task_id": task_db_id,
                    "feed_id": feed_id,
                    "valid": result_dict.get("valid", False),
                }

            except Exception as e:
                # Update task as failed (only if task was found)
                if task:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = str(e)
                    task.error_traceback = traceback.format_exc()
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()

                return {
                    "success": False,
                    "error": str(e),
                    "task_id": task_db_id,
                }

    # Always use asyncio.run() for clean event loop management
    return asyncio.run(run_validation())


@celery_app.task(name="app.tasks.merge_agencies", bind=True)
def merge_agencies(
    self,
    task_db_id: int,
    source_feed_ids: list[int],
    target_agency_id: int,
    merge_strategy: str,
    feed_name: str,
    feed_description: str | None = None,
    activate_on_success: bool = False,
):
    """
    Merge multiple source feeds into a target agency.

    This creates a new feed in the target agency and copies all GTFS data
    from the source feeds, handling ID conflicts based on merge_strategy.

    Args:
        task_db_id: AsyncTask record ID in database
        source_feed_ids: List of source feed IDs to merge
        target_agency_id: Target agency ID to receive merged data
        merge_strategy: 'fail_on_conflict' or 'auto_prefix'
        feed_name: Name for the new merged feed
        feed_description: Optional description for the feed
        activate_on_success: Whether to activate the feed on success
    """

    async def run_merge():
        """Async function to run the merge"""
        task = None
        async with CeleryAsyncSessionLocal() as db:
            try:
                # Get task record
                result = await db.execute(
                    select(AsyncTask).where(AsyncTask.id == task_db_id)
                )
                task = result.scalar_one_or_none()

                if not task:
                    return {
                        "success": False,
                        "error": f"Task record {task_db_id} not found"
                    }

                # Check if task was cancelled before we even started
                if task.status == TaskStatus.CANCELLED.value:
                    return {
                        "success": False,
                        "error": "Task was cancelled before starting",
                        "task_id": task_db_id,
                    }

                # Update task status
                task.status = TaskStatus.RUNNING.value
                task.started_at = datetime.utcnow().isoformat() + 'Z'
                task.progress = 0.0
                await db.commit()

                # Import models
                from app.models.gtfs import (
                    GTFSFeed, Route, Trip, Stop, StopTime,
                    Calendar, CalendarDate, Shape, FareAttribute, FareRule, FeedInfo
                )
                from sqlalchemy import func

                # Create new feed in target agency
                task.progress = 5.0
                await db.commit()

                new_feed = GTFSFeed(
                    agency_id=target_agency_id,
                    name=feed_name,
                    description=feed_description or f"Merged from {len(source_feed_ids)} feeds",
                    is_active=activate_on_success,
                    imported_at=datetime.utcnow().isoformat() + 'Z',
                )
                db.add(new_feed)
                await db.flush()

                new_feed_id = new_feed.id

                # source_feed_ids are already provided as parameter
                task.progress = 10.0
                await db.commit()

                # Track statistics
                stats = {
                    "routes_copied": 0,
                    "trips_copied": 0,
                    "stops_copied": 0,
                    "stop_times_copied": 0,
                    "calendars_copied": 0,
                    "shapes_copied": 0,
                }

                # All routes in the merged feed will reference the target agency
                # (No GTFSAgency copying needed - agencies table is the single source of truth)
                task.progress = 20.0
                await db.commit()

                # Step 1: Copy Stops with deduplication (30%)
                # With composite PK, we track stop_id strings, not database IDs
                # Map: (source_feed_id, stop_id) -> new_stop_id (potentially prefixed)
                stop_id_remap = {}
                seen_stop_ids = set()

                stops_result = await db.execute(
                    select(Stop).where(Stop.feed_id.in_(source_feed_ids))
                )
                stops = stops_result.scalars().all()

                for stop in stops:
                    # Check if this stop_id has been seen already
                    if stop.stop_id in seen_stop_ids:
                        # Conflict! Apply merge strategy
                        if merge_strategy == 'auto_prefix':
                            # Prefix with source feed ID to make unique
                            new_stop_id = f"feed{stop.feed_id}_{stop.stop_id}"
                        else:
                            # Skip duplicate (fail_on_conflict should have been caught in validation)
                            continue
                    else:
                        new_stop_id = stop.stop_id
                        seen_stop_ids.add(stop.stop_id)

                    # Create new stop with new feed_id and potentially renamed stop_id
                    new_stop = Stop(
                        feed_id=new_feed_id,
                        stop_id=new_stop_id,
                        stop_code=stop.stop_code,
                        stop_name=stop.stop_name,
                        stop_desc=stop.stop_desc,
                        stop_lat=stop.stop_lat,
                        stop_lon=stop.stop_lon,
                        zone_id=stop.zone_id,
                        stop_url=stop.stop_url,
                        location_type=stop.location_type,
                        parent_station=stop.parent_station,
                        stop_timezone=stop.stop_timezone,
                        wheelchair_boarding=stop.wheelchair_boarding,
                    )
                    db.add(new_stop)

                    # Track the mapping: (old_feed_id, old_stop_id) -> new_stop_id
                    stop_id_remap[(stop.feed_id, stop.stop_id)] = new_stop_id
                    stats["stops_copied"] += 1

                await db.commit()
                task.progress = 30.0
                await db.commit()

                # Step 3: Copy Calendars (40%)
                # Map: (source_feed_id, service_id) -> new_service_id
                service_id_remap = {}
                seen_service_ids = set()

                calendars_result = await db.execute(
                    select(Calendar).where(Calendar.feed_id.in_(source_feed_ids))
                )
                calendars = calendars_result.scalars().all()

                for calendar in calendars:
                    # Check for conflicts
                    if calendar.service_id in seen_service_ids:
                        if merge_strategy == 'auto_prefix':
                            new_service_id = f"feed{calendar.feed_id}_{calendar.service_id}"
                        else:
                            continue
                    else:
                        new_service_id = calendar.service_id
                        seen_service_ids.add(calendar.service_id)

                    new_calendar = Calendar(
                        feed_id=new_feed_id,
                        service_id=new_service_id,
                        monday=calendar.monday,
                        tuesday=calendar.tuesday,
                        wednesday=calendar.wednesday,
                        thursday=calendar.thursday,
                        friday=calendar.friday,
                        saturday=calendar.saturday,
                        sunday=calendar.sunday,
                        start_date=calendar.start_date,
                        end_date=calendar.end_date,
                    )
                    db.add(new_calendar)
                    service_id_remap[(calendar.feed_id, calendar.service_id)] = new_service_id
                    stats["calendars_copied"] += 1

                await db.commit()
                task.progress = 40.0
                await db.commit()

                # Copy CalendarDates
                calendar_dates_result = await db.execute(
                    select(CalendarDate).where(CalendarDate.feed_id.in_(source_feed_ids))
                )
                calendar_dates = calendar_dates_result.scalars().all()

                for cal_date in calendar_dates:
                    new_service_id = service_id_remap.get((cal_date.feed_id, cal_date.service_id))
                    if new_service_id:
                        new_cal_date = CalendarDate(
                            feed_id=new_feed_id,
                            service_id=new_service_id,
                            date=cal_date.date,
                            exception_type=cal_date.exception_type,
                        )
                        db.add(new_cal_date)

                await db.commit()

                # Step 4: Copy Shapes (50%)
                # Map: (source_feed_id, shape_id) -> new_shape_id
                shape_id_remap = {}
                seen_shape_ids = set()

                shapes_result = await db.execute(
                    select(Shape).where(Shape.feed_id.in_(source_feed_ids))
                    .order_by(Shape.feed_id, Shape.shape_id, Shape.shape_pt_sequence)
                )
                shapes = shapes_result.scalars().all()

                for shape in shapes:
                    # Check if we've seen this shape_id before
                    if shape.shape_id in seen_shape_ids:
                        # We have a conflict - check if we already remapped this feed's shape
                        if (shape.feed_id, shape.shape_id) in shape_id_remap:
                            new_shape_id = shape_id_remap[(shape.feed_id, shape.shape_id)]
                        elif merge_strategy == 'auto_prefix':
                            new_shape_id = f"feed{shape.feed_id}_{shape.shape_id}"
                            shape_id_remap[(shape.feed_id, shape.shape_id)] = new_shape_id
                        else:
                            continue
                    else:
                        new_shape_id = shape.shape_id
                        seen_shape_ids.add(shape.shape_id)
                        shape_id_remap[(shape.feed_id, shape.shape_id)] = new_shape_id

                    new_shape = Shape(
                        feed_id=new_feed_id,
                        shape_id=new_shape_id,
                        shape_pt_lat=shape.shape_pt_lat,
                        shape_pt_lon=shape.shape_pt_lon,
                        shape_pt_sequence=shape.shape_pt_sequence,
                        shape_dist_traveled=shape.shape_dist_traveled,
                    )
                    db.add(new_shape)
                    stats["shapes_copied"] += 1

                await db.commit()
                task.progress = 50.0
                await db.commit()

                # Step 5: Copy Routes (60%)
                # Map: (source_feed_id, route_id) -> new_route_id
                route_id_remap = {}
                seen_route_ids = set()

                routes_result = await db.execute(
                    select(Route).where(Route.feed_id.in_(source_feed_ids))
                )
                routes = routes_result.scalars().all()

                for route in routes:
                    # Check for conflicts
                    if route.route_id in seen_route_ids:
                        if merge_strategy == 'auto_prefix':
                            new_route_id = f"feed{route.feed_id}_{route.route_id}"
                        else:
                            continue
                    else:
                        new_route_id = route.route_id
                        seen_route_ids.add(route.route_id)

                    new_route = Route(
                        feed_id=new_feed_id,
                        route_id=new_route_id,
                        agency_id=target_agency_id,  # Link to target agency
                        route_short_name=route.route_short_name,
                        route_long_name=route.route_long_name,
                        route_desc=route.route_desc,
                        route_type=route.route_type,
                        route_url=route.route_url,
                        route_color=route.route_color,
                        route_text_color=route.route_text_color,
                        route_sort_order=route.route_sort_order,
                        custom_fields=route.custom_fields,
                    )
                    db.add(new_route)
                    route_id_remap[(route.feed_id, route.route_id)] = new_route_id
                    stats["routes_copied"] += 1

                await db.commit()
                task.progress = 60.0
                await db.commit()

                # Step 6: Copy Trips (70%)
                # Map: (source_feed_id, trip_id) -> new_trip_id
                trip_id_remap = {}
                seen_trip_ids = set()

                trips_result = await db.execute(
                    select(Trip).where(Trip.feed_id.in_(source_feed_ids))
                )
                trips = trips_result.scalars().all()

                for trip in trips:
                    # Look up the remapped route and service IDs
                    new_route_id = route_id_remap.get((trip.feed_id, trip.route_id))
                    new_service_id = service_id_remap.get((trip.feed_id, trip.service_id))

                    if not new_route_id or not new_service_id:
                        # Skip trips with missing references
                        continue

                    # Check for trip_id conflicts
                    if trip.trip_id in seen_trip_ids:
                        if merge_strategy == 'auto_prefix':
                            new_trip_id = f"feed{trip.feed_id}_{trip.trip_id}"
                        else:
                            continue
                    else:
                        new_trip_id = trip.trip_id
                        seen_trip_ids.add(trip.trip_id)

                    # Look up remapped shape_id if present
                    new_shape_id = None
                    if trip.shape_id:
                        new_shape_id = shape_id_remap.get((trip.feed_id, trip.shape_id))

                    new_trip = Trip(
                        feed_id=new_feed_id,
                        trip_id=new_trip_id,
                        route_id=new_route_id,
                        service_id=new_service_id,
                        trip_headsign=trip.trip_headsign,
                        trip_short_name=trip.trip_short_name,
                        direction_id=trip.direction_id,
                        block_id=trip.block_id,
                        shape_id=new_shape_id,
                        wheelchair_accessible=trip.wheelchair_accessible,
                        bikes_allowed=trip.bikes_allowed,
                        custom_fields=trip.custom_fields,
                    )
                    db.add(new_trip)
                    trip_id_remap[(trip.feed_id, trip.trip_id)] = new_trip_id
                    stats["trips_copied"] += 1

                await db.commit()
                task.progress = 70.0
                await db.commit()

                # Step 7: Copy StopTimes in batches (70-95%)
                # Query stop times from source feeds
                stop_times_result = await db.execute(
                    select(StopTime).where(StopTime.feed_id.in_(source_feed_ids))
                    .order_by(StopTime.feed_id, StopTime.trip_id, StopTime.stop_sequence)
                )
                stop_times = stop_times_result.scalars().all()

                # Batch size limited by asyncpg 32,767 parameter limit
                # StopTime has ~12 columns, so max batch ≈ 2500
                batch_size = 2500
                stop_times_batch = []
                total_stop_times = len(stop_times)

                for idx, stop_time in enumerate(stop_times):
                    # Look up the remapped trip and stop IDs
                    new_trip_id = trip_id_remap.get((stop_time.feed_id, stop_time.trip_id))
                    new_stop_id = stop_id_remap.get((stop_time.feed_id, stop_time.stop_id))

                    if new_trip_id and new_stop_id:
                        stop_times_batch.append({
                            'feed_id': new_feed_id,
                            'trip_id': new_trip_id,
                            'stop_id': new_stop_id,
                            'stop_sequence': stop_time.stop_sequence,
                            'arrival_time': stop_time.arrival_time,
                            'departure_time': stop_time.departure_time,
                            'stop_headsign': stop_time.stop_headsign,
                            'pickup_type': stop_time.pickup_type,
                            'drop_off_type': stop_time.drop_off_type,
                            'shape_dist_traveled': stop_time.shape_dist_traveled,
                            'timepoint': stop_time.timepoint,
                        })
                        stats["stop_times_copied"] += 1

                    # Bulk insert when batch is full
                    if len(stop_times_batch) >= batch_size:
                        await db.execute(
                            StopTime.__table__.insert(),
                            stop_times_batch
                        )
                        stop_times_batch = []

                        # Update progress (70-95%)
                        progress = 70.0 + (idx / total_stop_times) * 25.0
                        task.progress = min(95.0, progress)
                        await db.commit()

                # Insert remaining stop_times
                if stop_times_batch:
                    await db.execute(
                        StopTime.__table__.insert(),
                        stop_times_batch
                    )
                    await db.commit()

                task.progress = 95.0
                await db.commit()

                # Step 8: Copy FareAttributes (96%)
                # Apply merge_strategy for conflicts, similar to other entities
                fare_attrs_result = await db.execute(
                    select(FareAttribute).where(FareAttribute.feed_id.in_(source_feed_ids))
                )
                fare_attrs = fare_attrs_result.scalars().all()

                seen_fare_ids = set()
                fare_id_remap = {}  # (source_feed_id, fare_id) -> new_fare_id
                fare_attrs_copied = 0
                fare_attrs_prefixed = 0

                for fare_attr in fare_attrs:
                    new_fare_id = fare_attr.fare_id

                    # Check for conflicts
                    if fare_attr.fare_id in seen_fare_ids:
                        if merge_strategy == 'auto_prefix':
                            new_fare_id = f"feed{fare_attr.feed_id}_{fare_attr.fare_id}"
                            fare_attrs_prefixed += 1
                        else:
                            # Skip duplicate when not using auto_prefix
                            continue

                    seen_fare_ids.add(new_fare_id)
                    fare_id_remap[(fare_attr.feed_id, fare_attr.fare_id)] = new_fare_id

                    new_fare_attr = FareAttribute(
                        feed_id=new_feed_id,
                        fare_id=new_fare_id,
                        price=fare_attr.price,
                        currency_type=fare_attr.currency_type,
                        payment_method=fare_attr.payment_method,
                        transfers=fare_attr.transfers,
                        agency_id=fare_attr.agency_id,
                        transfer_duration=fare_attr.transfer_duration,
                    )
                    db.add(new_fare_attr)
                    fare_attrs_copied += 1

                await db.commit()
                stats["fare_attributes_copied"] = fare_attrs_copied
                stats["fare_attributes_prefixed"] = fare_attrs_prefixed
                task.progress = 96.0
                await db.commit()

                # Step 9: Copy FareRules (96.5%)
                # Use remapped fare_ids and route_ids
                fare_rules_result = await db.execute(
                    select(FareRule).where(FareRule.feed_id.in_(source_feed_ids))
                )
                fare_rules = fare_rules_result.scalars().all()

                seen_fare_rules = set()
                fare_rules_copied = 0
                fare_rules_skipped = 0

                for fare_rule in fare_rules:
                    # Get remapped fare_id
                    new_fare_id = fare_id_remap.get(
                        (fare_rule.feed_id, fare_rule.fare_id),
                        fare_rule.fare_id
                    )

                    # Get remapped route_id (if fare_rule has one)
                    new_route_id = fare_rule.route_id
                    if fare_rule.route_id:
                        new_route_id = route_id_remap.get(
                            (fare_rule.feed_id, fare_rule.route_id),
                            fare_rule.route_id
                        )

                    # Create a unique key for this fare rule with remapped IDs
                    rule_key = (
                        new_fare_id,
                        new_route_id,
                        fare_rule.origin_id,
                        fare_rule.destination_id,
                        fare_rule.contains_id,
                    )

                    # Skip duplicates (same rule after remapping)
                    if rule_key in seen_fare_rules:
                        fare_rules_skipped += 1
                        continue
                    seen_fare_rules.add(rule_key)

                    new_fare_rule = FareRule(
                        feed_id=new_feed_id,
                        fare_id=new_fare_id,
                        route_id=new_route_id,
                        origin_id=fare_rule.origin_id,
                        destination_id=fare_rule.destination_id,
                        contains_id=fare_rule.contains_id,
                        custom_fields=fare_rule.custom_fields,
                    )
                    db.add(new_fare_rule)
                    fare_rules_copied += 1

                await db.commit()
                stats["fare_rules_copied"] = fare_rules_copied
                stats["fare_rules_skipped_duplicates"] = fare_rules_skipped
                task.progress = 96.5
                await db.commit()

                # Step 10: Copy FeedInfo (97%)
                feed_info_result = await db.execute(
                    select(FeedInfo).where(FeedInfo.feed_id.in_(source_feed_ids))
                )
                feed_infos = feed_info_result.scalars().all()

                for feed_info in feed_infos:
                    new_feed_info = FeedInfo(
                        feed_id=new_feed_id,
                        feed_publisher_name=feed_info.feed_publisher_name,
                        feed_publisher_url=feed_info.feed_publisher_url,
                        feed_lang=feed_info.feed_lang,
                        feed_start_date=feed_info.feed_start_date,
                        feed_end_date=feed_info.feed_end_date,
                        feed_version=feed_info.feed_version,
                        feed_contact_email=feed_info.feed_contact_email,
                        feed_contact_url=feed_info.feed_contact_url,
                    )
                    db.add(new_feed_info)
                    # Only keep one FeedInfo record - use the first one
                    break

                await db.commit()
                stats["feed_info_copied"] = min(1, len(feed_infos))
                task.progress = 97.0
                await db.commit()

                # Step 11: Post-merge validation - verify entity counts (98%)
                validation_warnings = []

                # Count actual entities in merged feed (composite PKs don't have .id)
                actual_routes = await db.scalar(
                    select(func.count()).select_from(Route).where(Route.feed_id == new_feed_id)
                ) or 0
                actual_trips = await db.scalar(
                    select(func.count()).select_from(Trip).where(Trip.feed_id == new_feed_id)
                ) or 0
                actual_stops = await db.scalar(
                    select(func.count()).select_from(Stop).where(Stop.feed_id == new_feed_id)
                ) or 0
                actual_calendars = await db.scalar(
                    select(func.count()).select_from(Calendar).where(Calendar.feed_id == new_feed_id)
                ) or 0
                actual_fare_attributes = await db.scalar(
                    select(func.count()).select_from(FareAttribute).where(FareAttribute.feed_id == new_feed_id)
                ) or 0
                actual_fare_rules = await db.scalar(
                    select(func.count()).select_from(FareRule).where(FareRule.feed_id == new_feed_id)
                ) or 0

                # Verify counts match expected (from stats)
                count_mismatches = []
                if actual_routes != stats["routes_copied"]:
                    mismatch_msg = f"Routes: expected {stats['routes_copied']}, got {actual_routes}"
                    validation_warnings.append(mismatch_msg)
                    count_mismatches.append("routes")

                if actual_trips != stats["trips_copied"]:
                    mismatch_msg = f"Trips: expected {stats['trips_copied']}, got {actual_trips}"
                    validation_warnings.append(mismatch_msg)
                    count_mismatches.append("trips")

                if actual_stops != stats["stops_copied"]:
                    mismatch_msg = f"Stops: expected {stats['stops_copied']}, got {actual_stops}"
                    validation_warnings.append(mismatch_msg)
                    count_mismatches.append("stops")

                task.progress = 98.0
                await db.commit()

                # Update feed statistics
                new_feed.total_routes = actual_routes
                new_feed.total_stops = actual_stops
                new_feed.total_trips = actual_trips
                await db.commit()

                # Complete task
                task.status = TaskStatus.COMPLETED.value
                task.progress = 100.0
                task.completed_at = datetime.utcnow().isoformat() + 'Z'
                task.result_data = {
                    "success": True,
                    "new_feed_id": new_feed_id,
                    "feed_name": feed_name,
                    "statistics": {
                        **stats,
                        "actual_routes": actual_routes,
                        "actual_trips": actual_trips,
                        "actual_stops": actual_stops,
                        "actual_calendars": actual_calendars,
                        "actual_fare_attributes": actual_fare_attributes,
                        "actual_fare_rules": actual_fare_rules,
                        "count_mismatches": count_mismatches,
                    },
                    "validation_warnings": validation_warnings,
                }
                await db.commit()

                return {
                    "success": True,
                    "task_id": task_db_id,
                    "new_feed_id": new_feed_id,
                    "statistics": task.result_data["statistics"],
                    "validation_warnings": validation_warnings,
                }

            except Exception as e:
                # Rollback any pending transaction before updating task status
                try:
                    await db.rollback()
                except Exception:
                    pass  # Ignore rollback errors

                if task:
                    try:
                        # Re-fetch task to get a clean state
                        result = await db.execute(
                            select(AsyncTask).where(AsyncTask.id == task_db_id)
                        )
                        task = result.scalar_one_or_none()
                        if task:
                            task.status = TaskStatus.FAILED.value
                            task.error_message = str(e)
                            task.error_traceback = traceback.format_exc()
                            task.completed_at = datetime.utcnow().isoformat() + 'Z'
                            await db.commit()
                    except Exception as update_err:
                        # Log but don't fail if we can't update the task
                        print(f"Failed to update task status: {update_err}")

                return {
                    "success": False,
                    "error": str(e),
                    "task_id": task_db_id,
                }

    # Run the async merge
    # Always use asyncio.run() for clean event loop management
    # This avoids conflicts with asyncpg connections bound to other event loops
    return asyncio.run(run_merge())


@celery_app.task(name="app.tasks.split_agency", bind=True)
def split_agency(
    self,
    task_db_id: int,
    source_agency_id: int,
    feed_id: int,
    route_ids: list[str],
    new_agency_name: str,
    new_agency_description: str | None = None,
    new_feed_name: str = "Initial Feed",
    copy_users: bool = False,
    remove_from_source: bool = False,
    user_id: int | None = None,
):
    """
    Split routes from an agency into a new agency.

    Creates a new agency with selected routes and their dependencies
    (trips, stops, calendars, shapes). Optionally removes from source.

    Args:
        task_db_id: AsyncTask record ID in database
        source_agency_id: Source agency ID
        feed_id: Feed ID containing routes to split
        route_ids: List of route_ids (strings) to split
        new_agency_name: Name for the new agency
        new_agency_description: Optional description
        new_feed_name: Name for the initial feed in new agency
        copy_users: Copy users from source agency
        remove_from_source: Remove routes from source after split
        user_id: ID of user initiating the split (will be added as admin)
    """

    async def run_split():
        """Async function to run the split"""
        task = None
        async with CeleryAsyncSessionLocal() as db:
            try:
                # Get task record
                result = await db.execute(
                    select(AsyncTask).where(AsyncTask.id == task_db_id)
                )
                task = result.scalar_one_or_none()

                if not task:
                    return {
                        "success": False,
                        "error": f"Task record {task_db_id} not found"
                    }

                # Check if task was cancelled before we even started
                if task.status == TaskStatus.CANCELLED.value:
                    return {
                        "success": False,
                        "error": "Task was cancelled before starting",
                        "task_id": task_db_id,
                    }

                # Update task status
                task.status = TaskStatus.RUNNING.value
                task.started_at = datetime.utcnow().isoformat() + 'Z'
                task.progress = 0.0
                await db.commit()

                # Import models
                from app.models.gtfs import (
                    GTFSFeed, Route, Trip, Stop, StopTime,
                    Calendar, CalendarDate, Shape, FareAttribute, FeedInfo
                )
                from app.models.user import user_agencies

                # Create new agency
                task.progress = 5.0
                await db.commit()

                new_agency = Agency(
                    name=new_agency_name,
                    slug=new_agency_name.lower().replace(" ", "_"),
                )
                db.add(new_agency)
                await db.flush()
                new_agency_id = new_agency.id

                # Create new feed
                new_feed = GTFSFeed(
                    agency_id=new_agency_id,
                    name=new_feed_name,
                    description=f"Split from agency {source_agency_id}",
                    is_active=True,
                    imported_at=datetime.utcnow().isoformat(),
                )
                db.add(new_feed)
                await db.flush()
                new_feed_id = new_feed.id

                task.progress = 10.0
                await db.commit()

                # Always add the initiating user as admin of the new agency
                from app.models.user import UserRole
                added_user_ids = set()

                if user_id:
                    stmt = user_agencies.insert().values(
                        user_id=user_id,
                        agency_id=new_agency_id,
                        role=UserRole.AGENCY_ADMIN.value,
                    )
                    await db.execute(stmt)
                    added_user_ids.add(user_id)
                    await db.commit()

                # Copy other users if requested
                if copy_users:
                    users_result = await db.execute(
                        select(user_agencies).where(user_agencies.c.agency_id == source_agency_id)
                    )
                    existing_users = users_result.all()

                    for row in existing_users:
                        # Skip if already added (e.g., the initiating user)
                        if row.user_id in added_user_ids:
                            continue
                        stmt = user_agencies.insert().values(
                            user_id=row.user_id,
                            agency_id=new_agency_id,
                            role=row.role,
                        )
                        await db.execute(stmt)
                        added_user_ids.add(row.user_id)

                    await db.commit()

                task.progress = 15.0
                await db.commit()

                # Track statistics
                stats = {
                    "routes_copied": 0,
                    "trips_copied": 0,
                    "stops_copied": 0,
                    "stop_times_copied": 0,
                    "calendars_copied": 0,
                    "shapes_copied": 0,
                }

                # Get source routes to split
                routes_result = await db.execute(
                    select(Route).where(
                        Route.feed_id == feed_id,
                        Route.route_id.in_(route_ids)
                    )
                )
                source_routes = routes_result.scalars().all()

                if not source_routes:
                    raise ValueError(f"No routes found with IDs: {route_ids}")

                task.progress = 20.0
                await db.commit()

                # Collect all dependencies
                source_route_db_ids = [r.route_id for r in source_routes]

                # Get all trips for these routes
                trips_result = await db.execute(
                    select(Trip).where(
                        Trip.feed_id == feed_id,
                        Trip.route_id.in_(source_route_db_ids)
                    )
                )
                source_trips = trips_result.scalars().all()
                source_trip_db_ids = [t.trip_id for t in source_trips]

                task.progress = 25.0
                await db.commit()

                # Get all stop_times for these trips
                # Use subquery to avoid parameter limit (32,767 max with asyncpg)
                # Get unique stop IDs directly from database to avoid loading all stop_times
                # Use subquery to avoid parameter limit (32,767 max with asyncpg)
                unique_stop_ids_result = await db.execute(
                    select(StopTime.stop_id).distinct().where(
                        StopTime.trip_id.in_(
                            select(Trip.trip_id).where(
                                Trip.feed_id == feed_id,
                                Trip.route_id.in_(source_route_db_ids)
                            )
                        )
                    )
                )
                unique_stop_db_ids = set(row[0] for row in unique_stop_ids_result.all())

                task.progress = 30.0
                await db.commit()

                # Get all stops
                stops_result = await db.execute(
                    select(Stop).where(
                        Stop.feed_id == feed_id,
                        Stop.stop_id.in_(unique_stop_db_ids)
                    )
                )
                source_stops = stops_result.scalars().all()

                # Collect unique service IDs
                unique_service_ids = set(t.service_id for t in source_trips)

                task.progress = 35.0
                await db.commit()

                # Get all calendars
                calendars_result = await db.execute(
                    select(Calendar).where(
                        Calendar.feed_id == feed_id,
                        Calendar.service_id.in_(unique_service_ids)
                    )
                )
                source_calendars = calendars_result.scalars().all()

                # Get calendar_dates
                calendar_dates_result = await db.execute(
                    select(CalendarDate).where(
                        CalendarDate.feed_id == feed_id,
                        CalendarDate.service_id.in_(unique_service_ids)
                    )
                )
                source_calendar_dates = calendar_dates_result.scalars().all()

                task.progress = 40.0
                await db.commit()

                # Get all shapes
                # Trip.shape_id is a FK to Shape.id, so we need to get the GTFS shape_id strings first
                unique_shape_db_ids = set(t.shape_id for t in source_trips if t.shape_id)
                source_shapes = []
                if unique_shape_db_ids:
                    # Look up the GTFS shape_id strings from the database IDs
                    shapes_result = await db.execute(
                        select(Shape).where(
                            Shape.feed_id == feed_id,
                            Shape.shape_id.in_(unique_shape_db_ids)
                        ).order_by(Shape.shape_id, Shape.shape_pt_sequence)
                    )
                    source_shapes = shapes_result.scalars().all()

                task.progress = 45.0
                await db.commit()

                # No GTFSAgency copying needed - agencies table is the single source of truth
                # The new agency already exists and routes will reference it directly
                task.progress = 50.0
                await db.commit()

                # Copy Stops (55%)
                stop_id_map = {}
                for stop in source_stops:
                    new_stop = Stop(
                        feed_id=new_feed_id,
                        stop_id=stop.stop_id,
                        stop_code=stop.stop_code,
                        stop_name=stop.stop_name,
                        stop_desc=stop.stop_desc,
                        stop_lat=stop.stop_lat,
                        stop_lon=stop.stop_lon,
                        zone_id=stop.zone_id,
                        stop_url=stop.stop_url,
                        location_type=stop.location_type,
                        parent_station=stop.parent_station,
                        stop_timezone=stop.stop_timezone,
                        wheelchair_boarding=stop.wheelchair_boarding,
                    )
                    db.add(new_stop)
                    await db.flush()
                    stop_id_map[stop.stop_id] = new_stop.stop_id
                    stats["stops_copied"] += 1

                await db.commit()
                task.progress = 55.0
                await db.commit()

                # Copy Calendars (60%)
                calendar_id_map = {}
                for calendar in source_calendars:
                    new_calendar = Calendar(
                        feed_id=new_feed_id,
                        service_id=calendar.service_id,
                        monday=calendar.monday,
                        tuesday=calendar.tuesday,
                        wednesday=calendar.wednesday,
                        thursday=calendar.thursday,
                        friday=calendar.friday,
                        saturday=calendar.saturday,
                        sunday=calendar.sunday,
                        start_date=calendar.start_date,
                        end_date=calendar.end_date,
                    )
                    db.add(new_calendar)
                    await db.flush()
                    calendar_id_map[calendar.service_id] = new_calendar.service_id
                    stats["calendars_copied"] += 1

                # Copy CalendarDates
                for cal_date in source_calendar_dates:
                    new_service_id = calendar_id_map.get(cal_date.service_id)
                    if new_service_id:
                        new_cal_date = CalendarDate(
                            feed_id=new_feed_id,
                            service_id=new_service_id,
                            date=cal_date.date,
                            exception_type=cal_date.exception_type,
                        )
                        db.add(new_cal_date)

                await db.commit()
                task.progress = 60.0
                await db.commit()

                # Copy Shapes (65%)
                for shape in source_shapes:
                    new_shape = Shape(
                        feed_id=new_feed_id,
                        shape_id=shape.shape_id,
                        shape_pt_lat=shape.shape_pt_lat,
                        shape_pt_lon=shape.shape_pt_lon,
                        shape_pt_sequence=shape.shape_pt_sequence,
                        shape_dist_traveled=shape.shape_dist_traveled,
                    )
                    db.add(new_shape)
                    stats["shapes_copied"] += 1

                await db.commit()
                task.progress = 65.0
                await db.commit()

                # Copy Routes (70%)
                route_id_map = {}
                for route in source_routes:
                    new_route = Route(
                        feed_id=new_feed_id,
                        route_id=route.route_id,
                        agency_id=new_agency_id,  # Link to the new agency
                        route_short_name=route.route_short_name,
                        route_long_name=route.route_long_name,
                        route_desc=route.route_desc,
                        route_type=route.route_type,
                        route_url=route.route_url,
                        route_color=route.route_color,
                        route_text_color=route.route_text_color,
                        route_sort_order=route.route_sort_order,
                    )
                    db.add(new_route)
                    await db.flush()
                    # Map old GTFS route_id to new GTFS route_id (composite key, no surrogate id)
                    route_id_map[route.route_id] = new_route.route_id
                    stats["routes_copied"] += 1

                await db.commit()
                task.progress = 70.0
                await db.commit()

                # Copy Trips (75%)
                trip_id_map = {}
                for trip in source_trips:
                    new_route_id = route_id_map.get(trip.route_id)
                    new_service_id = calendar_id_map.get(trip.service_id)

                    if new_route_id and new_service_id:
                        new_trip = Trip(
                            feed_id=new_feed_id,
                            route_id=new_route_id,
                            service_id=new_service_id,
                            trip_id=trip.trip_id,
                            trip_headsign=trip.trip_headsign,
                            trip_short_name=trip.trip_short_name,
                            direction_id=trip.direction_id,
                            block_id=trip.block_id,
                            shape_id=trip.shape_id,
                            wheelchair_accessible=trip.wheelchair_accessible,
                            bikes_allowed=trip.bikes_allowed,
                        )
                        db.add(new_trip)
                        await db.flush()
                        # Map old GTFS trip_id to new GTFS trip_id (composite key, no surrogate id)
                        trip_id_map[trip.trip_id] = new_trip.trip_id
                        stats["trips_copied"] += 1

                await db.commit()
                task.progress = 75.0
                await db.commit()

                # Copy StopTimes in batches (75-90%)
                # Iterate over trips in chunks to avoid large queries and allow commits
                source_trip_ids = list(trip_id_map.keys())
                total_trips = len(source_trip_ids)
                trip_batch_size = 100  # Number of trips to process per batch
                
                # Calculate total stop times for progress estimation
                # We already have counting logic if needed, but we can just map progress to trips processed
                
                for i in range(0, total_trips, trip_batch_size):
                    trip_chunk = source_trip_ids[i:i + trip_batch_size]
                    
                    # Fetch stop times for this chunk of trips
                    chunk_stop_times_stmt = select(StopTime).where(
                        StopTime.feed_id == feed_id,
                        StopTime.trip_id.in_(trip_chunk)
                    ).order_by(StopTime.trip_id, StopTime.stop_sequence)
                    
                    chunk_stop_times_result = await db.execute(chunk_stop_times_stmt)
                    chunk_stop_times = chunk_stop_times_result.scalars().all()
                    
                    if not chunk_stop_times:
                        continue

                    # Transform records
                    stop_times_batch = []
                    for stop_time in chunk_stop_times:
                        new_trip_id = trip_id_map.get(stop_time.trip_id)
                        new_stop_id = stop_id_map.get(stop_time.stop_id)

                        if new_trip_id and new_stop_id:
                            stop_times_batch.append({
                                'feed_id': new_feed_id,
                                'trip_id': new_trip_id,
                                'stop_id': new_stop_id,
                                'stop_sequence': stop_time.stop_sequence,
                                'arrival_time': stop_time.arrival_time,
                                'departure_time': stop_time.departure_time,
                                'stop_headsign': stop_time.stop_headsign,
                                'pickup_type': stop_time.pickup_type,
                                'drop_off_type': stop_time.drop_off_type,
                                'shape_dist_traveled': stop_time.shape_dist_traveled,
                                'timepoint': stop_time.timepoint,
                            })
                            stats["stop_times_copied"] += 1
                    
                    # Bulk insert this batch
                    if stop_times_batch:
                        await db.execute(
                            StopTime.__table__.insert(),
                            stop_times_batch
                        )
                    
                    # Update progress and commit
                    progress = 75.0 + ((i + len(trip_chunk)) / total_trips) * 15.0
                    task.progress = min(90.0, progress)
                    await db.commit()

                task.progress = 90.0
                await db.commit()

                # Remove from source if requested (90-95%)
                if remove_from_source:
                    from sqlalchemy import delete as sql_delete

                    # Delete in reverse order of dependencies
                    # Use subqueries to avoid parameter limit (32,767 max with asyncpg)
                    await db.execute(
                        sql_delete(StopTime).where(
                            StopTime.feed_id == feed_id,
                            StopTime.trip_id.in_(
                                select(Trip.trip_id).where(
                                    Trip.feed_id == feed_id,
                                    Trip.route_id.in_(source_route_db_ids)
                                )
                            )
                        )
                    )
                    await db.execute(
                        sql_delete(Trip).where(
                            Trip.feed_id == feed_id,
                            Trip.route_id.in_(source_route_db_ids)
                        )
                    )
                    await db.execute(
                        sql_delete(Route).where(
                            Route.feed_id == feed_id,
                            Route.route_id.in_(source_route_db_ids)
                        )
                    )
                    await db.commit()

                task.progress = 95.0
                await db.commit()

                # Complete task
                task.status = TaskStatus.COMPLETED.value
                task.progress = 100.0
                task.completed_at = datetime.utcnow().isoformat() + 'Z'
                task.result_data = {
                    "success": True,
                    "new_agency_id": new_agency_id,
                    "new_feed_id": new_feed_id,
                    "agency_name": new_agency_name,
                    "statistics": stats,
                    "removed_from_source": remove_from_source,
                }
                await db.commit()

                return {
                    "success": True,
                    "task_id": task_db_id,
                    "new_agency_id": new_agency_id,
                    "new_feed_id": new_feed_id,
                    "statistics": stats,
                }

            except Exception as e:
                # Rollback any pending transaction before updating task status
                try:
                    await db.rollback()
                except Exception:
                    pass  # Ignore rollback errors

                if task:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = str(e)
                    task.error_traceback = traceback.format_exc()
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()

                return {
                    "success": False,
                    "error": str(e),
                    "task_id": task_db_id,
                }

    # Run the async split - always use asyncio.run() for clean event loop management
    # This avoids conflicts with asyncpg connections bound to other event loops
    return asyncio.run(run_split())


@celery_app.task(name="app.tasks.delete_feed", bind=True)
def delete_feed(self, task_db_id: int, feed_id: int):
    """
    Delete a GTFS feed and all related data asynchronously.

    This task handles the cascading deletion of:
    - Routes
    - Stops
    - Trips
    - Stop Times
    - Calendars
    - Shapes
    - Finally, the feed itself

    Args:
        task_db_id: Database ID of the AsyncTask tracking this operation
        feed_id: ID of the GTFS feed to delete
    """

    async def run_deletion():
        async with CeleryAsyncSessionLocal() as db:
            try:
                # Get the task record
                task_query = select(AsyncTask).where(AsyncTask.id == task_db_id)
                task_result = await db.execute(task_query)
                task = task_result.scalar_one_or_none()

                if not task:
                    return {
                        "success": False,
                        "error": f"Task {task_db_id} not found",
                    }

                # Check if task was cancelled before we even started
                if task.status == TaskStatus.CANCELLED.value:
                    return {
                        "success": False,
                        "error": "Task was cancelled before starting",
                        "task_id": task_db_id,
                    }

                # Update task status to running
                task.status = TaskStatus.RUNNING.value
                task.started_at = datetime.utcnow().isoformat() + 'Z'
                task.progress = 0.0
                await db.commit()

                # Import GTFSFeed model
                from app.models.gtfs import GTFSFeed

                # Get the feed
                feed_query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
                feed_result = await db.execute(feed_query)
                feed = feed_result.scalar_one_or_none()

                if not feed:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = f"Feed {feed_id} not found"
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()
                    return {
                        "success": False,
                        "error": f"Feed {feed_id} not found",
                    }

                # Store feed info for result
                feed_name = feed.name
                agency_id = feed.agency_id

                # Update progress: Starting deletion
                task.progress = 10.0
                await db.commit()

                # Count related records for progress tracking
                from app.models.gtfs import Route, Stop, Trip, StopTime, Calendar, Shape, CalendarDate
                from sqlalchemy import func, delete as sql_delete

                # Use SQL COUNT instead of loading all records into memory
                route_count_query = select(func.count()).select_from(Route).where(Route.feed_id == feed_id)
                route_count = (await db.execute(route_count_query)).scalar()

                stop_count_query = select(func.count()).select_from(Stop).where(Stop.feed_id == feed_id)
                stop_count = (await db.execute(stop_count_query)).scalar()

                trip_count_query = select(func.count()).select_from(Trip).where(Trip.feed_id == feed_id)
                trip_count = (await db.execute(trip_count_query)).scalar()

                calendar_count_query = select(func.count()).select_from(Calendar).where(Calendar.feed_id == feed_id)
                calendar_count = (await db.execute(calendar_count_query)).scalar()

                shape_count_query = select(func.count()).select_from(Shape).where(Shape.feed_id == feed_id)
                shape_count = (await db.execute(shape_count_query)).scalar()

                # Note: StopTime count would be huge, we'll just cascade delete it

                total_records = route_count + stop_count + trip_count + calendar_count + shape_count

                task.progress = 20.0
                task.result_data = {
                    "feed_name": feed_name,
                    "feed_id": feed_id,
                    "agency_id": agency_id,
                    "records_to_delete": {
                        "routes": route_count,
                        "stops": stop_count,
                        "trips": trip_count,
                        "calendars": calendar_count,
                        "shapes": shape_count,
                        "total": total_records,
                    }
                }
                await db.commit()

                # Delete related records directly with DELETE statements (faster than ORM cascade)
                # Most tables have feed_id, so we delete directly with WHERE feed_id = X
                # Only stop_times and calendar_dates need subqueries (no feed_id column)
                task.progress = 30.0
                await db.commit()

                # 1. Delete stop_times (no feed_id - uses subquery on trip_id)
                task.progress = 40.0
                await db.commit()
                await db.execute(
                    sql_delete(StopTime).where(
                        StopTime.feed_id == feed_id,
                        StopTime.trip_id.in_(
                            select(Trip.trip_id).where(Trip.feed_id == feed_id)
                        )
                    )
                )

                # 2. Delete calendar_dates (no feed_id - uses subquery on service_id)
                task.progress = 50.0
                await db.commit()
                await db.execute(
                    sql_delete(CalendarDate).where(
                        CalendarDate.feed_id == feed_id,
                        CalendarDate.service_id.in_(
                            select(Calendar.service_id).where(Calendar.feed_id == feed_id)
                        )
                    )
                )

                # 3-7. Delete all tables with feed_id (simple WHERE feed_id = X)
                task.progress = 60.0
                await db.commit()
                await db.execute(sql_delete(Trip).where(Trip.feed_id == feed_id))

                task.progress = 70.0
                await db.commit()
                await db.execute(sql_delete(Route).where(Route.feed_id == feed_id))

                task.progress = 75.0
                await db.commit()
                await db.execute(sql_delete(Stop).where(Stop.feed_id == feed_id))

                task.progress = 80.0
                await db.commit()
                await db.execute(sql_delete(Calendar).where(Calendar.feed_id == feed_id))

                task.progress = 90.0
                await db.commit()

                # Delete shapes - use direct delete by feed_id
                # Shape uses composite PK (feed_id, shape_id, shape_pt_sequence)
                await db.execute(sql_delete(Shape).where(Shape.feed_id == feed_id))
                await db.commit()

                # 8. Finally delete the feed itself
                task.progress = 95.0
                await db.commit()
                await db.delete(feed)
                await db.commit()

                # Mark task as completed
                task.status = TaskStatus.COMPLETED.value
                task.progress = 100.0
                task.completed_at = datetime.utcnow().isoformat() + 'Z'
                task.result_data["success"] = True
                task.result_data["message"] = f"Successfully deleted feed '{feed_name}' and all related data"
                await db.commit()

                return {
                    "success": True,
                    "feed_id": feed_id,
                    "feed_name": feed_name,
                    "records_deleted": total_records,
                }

            except Exception as e:
                # Update task as failed
                if task:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = str(e)
                    task.error_traceback = traceback.format_exc()
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    # Set can_retry to allow retrying the deletion
                    if task.result_data:
                        task.result_data["can_retry"] = True
                    else:
                        task.result_data = {"can_retry": True}
                    await db.commit()

                return {
                    "success": False,
                    "error": str(e),
                    "task_id": task_db_id,
                }

    # Always use asyncio.run() for clean event loop management
    return asyncio.run(run_deletion())


@celery_app.task(name="app.tasks.delete_agency", bind=True)
def delete_agency(
    self,
    task_db_id: int,
    agency_id: int,
    agency_name: str,
    user_id: int,
):
    """
    Delete an agency and all related data asynchronously.

    This task handles the cascading deletion of:
    - All GTFS feeds and their data
    - User-agency memberships
    - Audit logs
    - Validation preferences
    - The agency itself

    Args:
        task_db_id: Database ID of the AsyncTask tracking this operation
        agency_id: ID of the agency to delete
        agency_name: Name of the agency (for audit log)
        user_id: ID of the user performing the deletion
    """

    async def run_deletion():
        async with CeleryAsyncSessionLocal() as db:
            task = None
            try:
                # Get the task record
                task_query = select(AsyncTask).where(AsyncTask.id == task_db_id)
                task_result = await db.execute(task_query)
                task = task_result.scalar_one_or_none()

                if not task:
                    return {
                        "success": False,
                        "error": f"Task {task_db_id} not found",
                    }

                # Check if task was cancelled before we even started
                if task.status == TaskStatus.CANCELLED.value:
                    return {
                        "success": False,
                        "error": "Task was cancelled before starting",
                        "task_id": task_db_id,
                    }

                # Update task status to running
                task.status = TaskStatus.RUNNING.value
                task.started_at = datetime.utcnow().isoformat() + 'Z'
                task.progress = 0.0
                await db.commit()

                # Get the agency
                agency_query = select(Agency).where(Agency.id == agency_id)
                agency_result = await db.execute(agency_query)
                agency = agency_result.scalar_one_or_none()

                if not agency:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = f"Agency {agency_id} not found"
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()
                    return {
                        "success": False,
                        "error": f"Agency {agency_id} not found",
                    }

                task.progress = 5.0
                await db.commit()

                # Import models
                from app.models.gtfs import (
                    GTFSFeed, Route, Trip, Stop, StopTime,
                    Calendar, CalendarDate, Shape, FareAttribute, FareRule, FeedInfo
                )
                from app.models.user import user_agencies
                from app.models.audit import AuditLog, AuditAction
                from app.models.validation import AgencyValidationPreferences
                from sqlalchemy import func, delete as sql_delete

                # Count records for progress tracking
                feed_ids_query = select(GTFSFeed.id).where(GTFSFeed.agency_id == agency_id)
                feed_ids_result = await db.execute(feed_ids_query)
                feed_ids = [row[0] for row in feed_ids_result.all()]

                feed_count = len(feed_ids)

                # Count GTFS records
                route_count = 0
                stop_count = 0
                trip_count = 0
                calendar_count = 0
                shape_count = 0

                if feed_ids:
                    route_count_query = select(func.count()).select_from(Route).where(Route.feed_id.in_(feed_ids))
                    route_count = (await db.execute(route_count_query)).scalar() or 0

                    stop_count_query = select(func.count()).select_from(Stop).where(Stop.feed_id.in_(feed_ids))
                    stop_count = (await db.execute(stop_count_query)).scalar() or 0

                    trip_count_query = select(func.count()).select_from(Trip).where(Trip.feed_id.in_(feed_ids))
                    trip_count = (await db.execute(trip_count_query)).scalar() or 0

                    calendar_count_query = select(func.count()).select_from(Calendar).where(Calendar.feed_id.in_(feed_ids))
                    calendar_count = (await db.execute(calendar_count_query)).scalar() or 0

                    shape_count_query = select(func.count()).select_from(Shape).where(Shape.feed_id.in_(feed_ids))
                    shape_count = (await db.execute(shape_count_query)).scalar() or 0

                total_records = route_count + stop_count + trip_count + calendar_count + shape_count

                task.progress = 10.0
                task.result_data = {
                    "agency_name": agency_name,
                    "agency_id": agency_id,
                    "records_to_delete": {
                        "feeds": feed_count,
                        "routes": route_count,
                        "stops": stop_count,
                        "trips": trip_count,
                        "calendars": calendar_count,
                        "shapes": shape_count,
                        "total": total_records,
                    }
                }
                await db.commit()

                # Delete GTFS data for each feed
                # With composite PKs, all GTFS tables have feed_id, so we can delete directly by feed_id
                if feed_ids:
                    task.progress = 15.0
                    await db.commit()

                    # 1. Delete stop_times (has feed_id in composite PK)
                    await db.execute(
                        sql_delete(StopTime).where(StopTime.feed_id.in_(feed_ids))
                    )
                    task.progress = 25.0
                    await db.commit()

                    # 2. Delete calendar_dates (has feed_id in composite PK)
                    await db.execute(
                        sql_delete(CalendarDate).where(CalendarDate.feed_id.in_(feed_ids))
                    )
                    task.progress = 30.0
                    await db.commit()

                    # 3. Delete trips (has feed_id in composite PK)
                    await db.execute(sql_delete(Trip).where(Trip.feed_id.in_(feed_ids)))
                    task.progress = 40.0
                    await db.commit()

                    # 4. Delete routes (has feed_id in composite PK)
                    await db.execute(sql_delete(Route).where(Route.feed_id.in_(feed_ids)))
                    task.progress = 50.0
                    await db.commit()

                    # 5. Delete stops (has feed_id in composite PK)
                    await db.execute(sql_delete(Stop).where(Stop.feed_id.in_(feed_ids)))
                    task.progress = 55.0
                    await db.commit()

                    # 6. Delete calendars (has feed_id in composite PK)
                    await db.execute(sql_delete(Calendar).where(Calendar.feed_id.in_(feed_ids)))
                    task.progress = 60.0
                    await db.commit()

                    # 7. Delete shapes (has feed_id in composite PK)
                    await db.execute(sql_delete(Shape).where(Shape.feed_id.in_(feed_ids)))
                    task.progress = 65.0
                    await db.commit()

                    # 8. Delete fare_attributes (has feed_id in composite PK)
                    await db.execute(sql_delete(FareAttribute).where(FareAttribute.feed_id.in_(feed_ids)))
                    task.progress = 67.0
                    await db.commit()

                    # 9. Delete fare_rules (has feed_id in composite PK)
                    await db.execute(sql_delete(FareRule).where(FareRule.feed_id.in_(feed_ids)))
                    task.progress = 68.0
                    await db.commit()

                    # 10. Delete feed_info (has feed_id as PK)
                    await db.execute(sql_delete(FeedInfo).where(FeedInfo.feed_id.in_(feed_ids)))
                    task.progress = 70.0
                    await db.commit()

                    # 11. Delete feeds
                    await db.execute(sql_delete(GTFSFeed).where(GTFSFeed.agency_id == agency_id))
                    task.progress = 75.0
                    await db.commit()

                # Delete validation preferences
                await db.execute(
                    sql_delete(AgencyValidationPreferences).where(
                        AgencyValidationPreferences.agency_id == agency_id
                    )
                )
                task.progress = 80.0
                await db.commit()

                # Delete audit logs for this agency (they would be deleted anyway by cascade)
                await db.execute(
                    sql_delete(AuditLog).where(AuditLog.agency_id == agency_id)
                )
                task.progress = 85.0
                await db.commit()

                # Delete user-agency associations
                await db.execute(
                    user_agencies.delete().where(user_agencies.c.agency_id == agency_id)
                )
                task.progress = 90.0
                await db.commit()

                # Delete the agency itself
                await db.delete(agency)
                task.progress = 95.0
                await db.commit()

                # Create a global audit log (without agency_id so it persists)
                audit_log = AuditLog(
                    user_id=user_id,
                    action=AuditAction.DELETE,
                    entity_type="agency",
                    entity_id=str(agency_id),
                    description=f"Permanently deleted agency '{agency_name}' (ID: {agency_id})",
                    old_values={
                        "agency_id": agency_id,
                        "agency_name": agency_name,
                        "feeds_deleted": feed_count,
                        "total_records_deleted": total_records,
                    },
                    agency_id=None,  # No agency_id so it survives
                )
                db.add(audit_log)
                await db.commit()

                # Mark task as completed
                task.status = TaskStatus.COMPLETED.value
                task.progress = 100.0
                task.completed_at = datetime.utcnow().isoformat() + 'Z'
                task.result_data["success"] = True
                task.result_data["message"] = f"Successfully deleted agency '{agency_name}' and all related data"
                await db.commit()

                return {
                    "success": True,
                    "agency_id": agency_id,
                    "agency_name": agency_name,
                    "records_deleted": total_records,
                }

            except Exception as e:
                # Update task as failed
                if task:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = str(e)
                    task.error_traceback = traceback.format_exc()
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()

                return {
                    "success": False,
                    "error": str(e),
                    "task_id": task_db_id,
                }

    # Always use asyncio.run() for clean event loop management
    return asyncio.run(run_deletion())


@celery_app.task(name="app.tasks.check_feed_sources")
def check_feed_sources():
    """
    Periodic task to check all enabled external feed sources for updates.

    This task runs on a schedule (e.g., every hour) and checks each enabled
    feed source based on its configured check_frequency.
    """
    import hashlib
    import httpx

    async def run_check():
        from app.models.feed_source import (
            ExternalFeedSource,
            FeedSourceCheckLog,
            FeedSourceStatus,
            CheckFrequency,
        )

        async with CeleryAsyncSessionLocal() as db:
            try:
                # Get all enabled feed sources
                query = select(ExternalFeedSource).where(
                    ExternalFeedSource.is_enabled == True,
                    ExternalFeedSource.status != FeedSourceStatus.PAUSED.value,
                )
                result = await db.execute(query)
                sources = result.scalars().all()

                now = datetime.utcnow()
                checked_count = 0
                updated_count = 0
                error_count = 0

                for source in sources:
                    # Determine if this source should be checked based on frequency
                    should_check = False

                    if source.last_checked_at is None:
                        should_check = True
                    else:
                        try:
                            last_check = datetime.fromisoformat(source.last_checked_at.replace('Z', '+00:00').replace('+00:00', ''))
                            hours_since_check = (now - last_check).total_seconds() / 3600

                            if source.check_frequency == CheckFrequency.HOURLY.value:
                                should_check = hours_since_check >= 1
                            elif source.check_frequency == CheckFrequency.DAILY.value:
                                should_check = hours_since_check >= 24
                            elif source.check_frequency == CheckFrequency.WEEKLY.value:
                                should_check = hours_since_check >= 168  # 7 * 24
                            # MANUAL frequency is never auto-checked
                        except:
                            should_check = True  # Check if we can't parse the date

                    if not should_check:
                        continue

                    # Create check log
                    now_str = now.isoformat() + 'Z'
                    check_log = FeedSourceCheckLog(
                        feed_source_id=source.id,
                        checked_at=now_str,
                        success=False,
                    )

                    try:
                        # Build headers
                        headers = {"User-Agent": "GTFS-Tools/1.0"}
                        if source.auth_type == "api_key" and source.auth_header and source.auth_value:
                            headers[source.auth_header] = source.auth_value
                        elif source.auth_type == "bearer" and source.auth_value:
                            headers["Authorization"] = f"Bearer {source.auth_value}"

                        # Add conditional headers
                        if source.last_etag:
                            headers["If-None-Match"] = source.last_etag
                        if source.last_modified:
                            headers["If-Modified-Since"] = source.last_modified

                        async with httpx.AsyncClient(timeout=60.0) as client:
                            response = await client.get(source.url, headers=headers, follow_redirects=True)

                        check_log.http_status = response.status_code

                        if response.status_code == 304:
                            # Not modified
                            check_log.success = True
                            check_log.content_changed = False
                            source.status = FeedSourceStatus.ACTIVE.value
                            source.last_checked_at = now_str
                            source.last_successful_check = now_str
                            source.error_count = 0
                            checked_count += 1

                        elif response.status_code == 200:
                            content = response.content
                            content_hash = hashlib.sha256(content).hexdigest()
                            check_log.content_size = len(content)
                            check_log.content_hash = content_hash

                            content_changed = content_hash != source.last_content_hash
                            check_log.content_changed = content_changed
                            check_log.success = True

                            source.status = FeedSourceStatus.ACTIVE.value
                            source.last_checked_at = now_str
                            source.last_successful_check = now_str
                            source.last_content_hash = content_hash
                            source.error_count = 0

                            if "etag" in response.headers:
                                source.last_etag = response.headers["etag"]
                            if "last-modified" in response.headers:
                                source.last_modified = response.headers["last-modified"]

                            checked_count += 1
                            if content_changed:
                                updated_count += 1

                                # Auto-import if enabled
                                if source.auto_import:
                                    # Queue import task (using first admin user)
                                    from app.models.user import User
                                    user_query = select(User).where(User.is_superuser == True).limit(1)
                                    user_result = await db.execute(user_query)
                                    admin_user = user_result.scalar_one_or_none()

                                    if admin_user:
                                        task_record = AsyncTask(
                                            celery_task_id=str(uuid.uuid4()),  # Temporary UUID, will be replaced
                                            task_name=f"Auto-import: {source.name}",
                                            description=f"Automatic import from {source.url}",
                                            task_type=TaskType.IMPORT_GTFS.value,
                                            user_id=admin_user.id,
                                            agency_id=source.agency_id,
                                            status=TaskStatus.PENDING.value,
                                            progress=0.0,
                                            input_data={"feed_source_id": source.id},
                                        )
                                        db.add(task_record)
                                        await db.flush()

                                        celery_result = import_gtfs.apply_async(
                                            kwargs={
                                                "task_db_id": task_record.id,
                                                "agency_id": source.agency_id,
                                                "file_content": content,
                                                "feed_name": f"{source.name} - {now_str[:10]}",
                                            }
                                        )
                                        task_record.celery_task_id = celery_result.id
                                        check_log.import_triggered = True
                                        check_log.import_task_id = str(task_record.id)
                                        source.last_import_at = now_str

                        else:
                            raise Exception(f"HTTP {response.status_code}")

                    except Exception as e:
                        check_log.success = False
                        check_log.error_message = str(e)[:1000]
                        source.status = FeedSourceStatus.ERROR.value
                        source.last_checked_at = now_str
                        source.error_count += 1
                        source.last_error = str(e)[:1000]
                        error_count += 1

                    db.add(check_log)
                    await db.commit()

                return {
                    "success": True,
                    "sources_checked": checked_count,
                    "sources_updated": updated_count,
                    "errors": error_count,
                }

            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    # Always use asyncio.run() for clean event loop management
    return asyncio.run(run_check())


@celery_app.task(name="app.tasks.clone_feed", bind=True)
def clone_feed(
    self,
    task_db_id: int,
    source_feed_id: int,
    new_name: str,
    target_agency_id: int,
):
    """
    Clone a GTFS feed asynchronously.

    Creates a complete copy of the feed including all routes, stops, trips,
    stop_times, calendars, and shapes. The new feed is created as inactive.

    Args:
        task_db_id: AsyncTask record ID in database
        source_feed_id: ID of the feed to clone
        new_name: Name for the cloned feed
        target_agency_id: Agency ID for the cloned feed
    """

    async def run_clone():
        """Async function to run the clone"""
        task = None
        async with CeleryAsyncSessionLocal() as db:
            try:
                # Get task record
                result = await db.execute(
                    select(AsyncTask).where(AsyncTask.id == task_db_id)
                )
                task = result.scalar_one_or_none()

                if not task:
                    return {
                        "success": False,
                        "error": f"Task record {task_db_id} not found"
                    }

                # Check if task was cancelled before we started
                if task.status == TaskStatus.CANCELLED.value:
                    return {
                        "success": False,
                        "error": "Task was cancelled before starting",
                        "task_id": task_db_id,
                    }

                # Update task status
                task.status = TaskStatus.RUNNING.value
                task.started_at = datetime.utcnow().isoformat() + 'Z'
                task.progress = 0.0
                await db.commit()

                # Import models
                from app.models.gtfs import (
                    GTFSFeed, Route, Trip, Stop, StopTime,
                    Calendar, CalendarDate, Shape, FareAttribute, FeedInfo
                )

                # Get source feed
                source_feed_result = await db.execute(
                    select(GTFSFeed).where(GTFSFeed.id == source_feed_id)
                )
                source_feed = source_feed_result.scalar_one_or_none()

                if not source_feed:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = f"Source feed {source_feed_id} not found"
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()
                    return {
                        "success": False,
                        "error": f"Source feed {source_feed_id} not found"
                    }

                task.progress = 5.0
                await db.commit()

                # Create new feed
                new_feed = GTFSFeed(
                    agency_id=target_agency_id,
                    name=new_name,
                    description=f"Cloned from {source_feed.name}",
                    is_active=False,
                    imported_at=datetime.utcnow().isoformat() + 'Z',
                )
                db.add(new_feed)
                await db.flush()
                new_feed_id = new_feed.id

                task.progress = 10.0
                await db.commit()

                # Track statistics
                stats = {
                    "routes_copied": 0,
                    "trips_copied": 0,
                    "stops_copied": 0,
                    "stop_times_copied": 0,
                    "calendars_copied": 0,
                    "shapes_copied": 0,
                }

                # No GTFSAgency copying needed - agencies table is the single source of truth
                # Routes in the new feed will reference the target agency
                task.progress = 15.0
                await db.commit()

                # Step 1: Copy Stops (25%)
                stop_id_map = {}  # old_id -> new_id
                stops_result = await db.execute(
                    select(Stop).where(Stop.feed_id == source_feed_id)
                )
                stops = stops_result.scalars().all()

                for stop in stops:
                    new_stop = Stop(
                        feed_id=new_feed_id,
                        stop_id=stop.stop_id,
                        stop_code=stop.stop_code,
                        stop_name=stop.stop_name,
                        stop_desc=stop.stop_desc,
                        stop_lat=stop.stop_lat,
                        stop_lon=stop.stop_lon,
                        zone_id=stop.zone_id,
                        stop_url=stop.stop_url,
                        location_type=stop.location_type,
                        parent_station=stop.parent_station,
                        stop_timezone=stop.stop_timezone,
                        wheelchair_boarding=stop.wheelchair_boarding,
                    )
                    db.add(new_stop)
                    await db.flush()
                    stop_id_map[stop.id] = new_stop.id
                    stats["stops_copied"] += 1

                await db.commit()
                task.progress = 25.0
                await db.commit()

                # Step 3: Copy Calendars (35%)
                calendar_id_map = {}
                calendars_result = await db.execute(
                    select(Calendar).where(Calendar.feed_id == source_feed_id)
                )
                calendars = calendars_result.scalars().all()

                for calendar in calendars:
                    new_calendar = Calendar(
                        feed_id=new_feed_id,
                        service_id=calendar.service_id,
                        monday=calendar.monday,
                        tuesday=calendar.tuesday,
                        wednesday=calendar.wednesday,
                        thursday=calendar.thursday,
                        friday=calendar.friday,
                        saturday=calendar.saturday,
                        sunday=calendar.sunday,
                        start_date=calendar.start_date,
                        end_date=calendar.end_date,
                    )
                    db.add(new_calendar)
                    await db.flush()
                    calendar_id_map[calendar.id] = new_calendar.id
                    stats["calendars_copied"] += 1

                await db.commit()
                task.progress = 35.0
                await db.commit()

                # Copy CalendarDates
                calendar_dates_result = await db.execute(
                    select(CalendarDate).where(
                        CalendarDate.service_id.in_(calendar_id_map.keys())
                    )
                )
                calendar_dates = calendar_dates_result.scalars().all()

                for cal_date in calendar_dates:
                    new_service_id = calendar_id_map.get(cal_date.service_id)
                    if new_service_id:
                        new_cal_date = CalendarDate(
                            service_id=new_service_id,
                            date=cal_date.date,
                            exception_type=cal_date.exception_type,
                        )
                        db.add(new_cal_date)

                await db.commit()

                # Step 4: Copy Shapes (45%)
                shapes_result = await db.execute(
                    select(Shape).where(Shape.feed_id == source_feed_id)
                    .order_by(Shape.shape_id, Shape.shape_pt_sequence)
                )
                shapes = shapes_result.scalars().all()

                for shape in shapes:
                    new_shape = Shape(
                        feed_id=new_feed_id,
                        shape_id=shape.shape_id,
                        shape_pt_lat=shape.shape_pt_lat,
                        shape_pt_lon=shape.shape_pt_lon,
                        shape_pt_sequence=shape.shape_pt_sequence,
                        shape_dist_traveled=shape.shape_dist_traveled,
                    )
                    db.add(new_shape)
                    stats["shapes_copied"] += 1

                await db.commit()
                task.progress = 45.0
                await db.commit()

                # Step 5: Copy Routes (55%)
                route_id_map = {}
                routes_result = await db.execute(
                    select(Route).where(Route.feed_id == source_feed_id)
                )
                routes = routes_result.scalars().all()

                for route in routes:
                    new_route = Route(
                        feed_id=new_feed_id,
                        route_id=route.route_id,
                        agency_id=target_agency_id,  # Link to target agency
                        route_short_name=route.route_short_name,
                        route_long_name=route.route_long_name,
                        route_desc=route.route_desc,
                        route_type=route.route_type,
                        route_url=route.route_url,
                        route_color=route.route_color,
                        route_text_color=route.route_text_color,
                        route_sort_order=route.route_sort_order,
                        custom_fields=route.custom_fields,
                    )
                    db.add(new_route)
                    await db.flush()
                    route_id_map[route.route_id] = new_route.route_id
                    stats["routes_copied"] += 1

                await db.commit()
                task.progress = 55.0
                await db.commit()

                # Step 6: Copy Trips (65%)
                trip_id_map = {}
                trips_result = await db.execute(
                    select(Trip).where(Trip.feed_id == source_feed_id)
                )
                trips = trips_result.scalars().all()

                for trip in trips:
                    new_route_id = route_id_map.get(trip.route_id)
                    new_service_id = calendar_id_map.get(trip.service_id)

                    if new_route_id and new_service_id:
                        new_trip = Trip(
                            feed_id=new_feed_id,
                            route_id=new_route_id,
                            service_id=new_service_id,
                            trip_id=trip.trip_id,
                            trip_headsign=trip.trip_headsign,
                            trip_short_name=trip.trip_short_name,
                            direction_id=trip.direction_id,
                            block_id=trip.block_id,
                            shape_id=trip.shape_id,
                            wheelchair_accessible=trip.wheelchair_accessible,
                            bikes_allowed=trip.bikes_allowed,
                        )
                        db.add(new_trip)
                        await db.flush()
                        trip_id_map[trip.trip_id] = new_trip.trip_id
                        stats["trips_copied"] += 1

                await db.commit()
                task.progress = 65.0
                await db.commit()

                # Step 7: Copy StopTimes in batches (65-95%)
                # Use subquery to avoid parameter limit (32,767 max with asyncpg)
                stop_times_result = await db.execute(
                    select(StopTime).where(
                        StopTime.feed_id == source_feed_id,
                        StopTime.trip_id.in_(
                            select(Trip.trip_id).where(Trip.feed_id == source_feed_id)
                        )
                    )
                    .order_by(StopTime.trip_id, StopTime.stop_sequence)
                )
                stop_times = stop_times_result.scalars().all()

                # Batch size limited by asyncpg 32,767 parameter limit
                # Stop_times has 10 columns, so max batch ≈ 3000
                batch_size = 2500
                stop_times_batch = []
                total_stop_times = len(stop_times)

                for idx, stop_time in enumerate(stop_times):
                    new_trip_id = trip_id_map.get(stop_time.trip_id)
                    new_stop_id = stop_id_map.get(stop_time.stop_id)

                    if new_trip_id and new_stop_id:
                        stop_times_batch.append({
                            'feed_id': new_feed_id,
                            'trip_id': new_trip_id,
                            'stop_id': new_stop_id,
                            'stop_sequence': stop_time.stop_sequence,
                            'arrival_time': stop_time.arrival_time,
                            'departure_time': stop_time.departure_time,
                            'stop_headsign': stop_time.stop_headsign,
                            'pickup_type': stop_time.pickup_type,
                            'drop_off_type': stop_time.drop_off_type,
                            'shape_dist_traveled': stop_time.shape_dist_traveled,
                            'timepoint': stop_time.timepoint,
                        })
                        stats["stop_times_copied"] += 1

                    # Bulk insert when batch is full
                    if len(stop_times_batch) >= batch_size:
                        await db.execute(
                            StopTime.__table__.insert(),
                            stop_times_batch
                        )
                        stop_times_batch = []

                        # Update progress (65-95%)
                        progress = 65.0 + (idx / total_stop_times) * 30.0 if total_stop_times > 0 else 95.0
                        task.progress = min(95.0, progress)
                        await db.commit()

                # Insert remaining stop_times
                if stop_times_batch:
                    await db.execute(
                        StopTime.__table__.insert(),
                        stop_times_batch
                    )
                    await db.commit()

                task.progress = 95.0
                await db.commit()

                # Update feed statistics
                new_feed_result = await db.execute(
                    select(GTFSFeed).where(GTFSFeed.id == new_feed_id)
                )
                new_feed_record = new_feed_result.scalar_one()
                new_feed_record.total_routes = stats["routes_copied"]
                new_feed_record.total_stops = stats["stops_copied"]
                new_feed_record.total_trips = stats["trips_copied"]
                await db.commit()

                # Complete task
                task.status = TaskStatus.COMPLETED.value
                task.progress = 100.0
                task.completed_at = datetime.utcnow().isoformat() + 'Z'
                task.result_data = {
                    "success": True,
                    "new_feed_id": new_feed_id,
                    "new_feed_name": new_name,
                    "source_feed_id": source_feed_id,
                    "source_feed_name": source_feed.name,
                    "statistics": stats,
                }
                await db.commit()

                return {
                    "success": True,
                    "task_id": task_db_id,
                    "new_feed_id": new_feed_id,
                    "statistics": stats,
                }

            except Exception as e:
                if task:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = str(e)
                    task.error_traceback = traceback.format_exc()
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()

                return {
                    "success": False,
                    "error": str(e),
                    "task_id": task_db_id,
                }

    # Always use asyncio.run() for clean event loop management
    return asyncio.run(run_clone())


@celery_app.task(name="app.tasks.validate_gtfs_mobilitydata", bind=True)
def validate_gtfs_mobilitydata(
    self,
    task_db_id: int,
    feed_id: int,
    agency_id: int,
    country_code: str = "",
):
    """
    Validate GTFS data using MobilityData GTFS Validator.

    Runs the official MobilityData GTFS Validator in a Docker container
    and generates comprehensive validation reports.

    Args:
        task_db_id: AsyncTask record ID in database
        feed_id: ID of the GTFS feed to validate
        agency_id: ID of the agency (for context)
        country_code: Optional ISO country code for location-specific validations
    """
    import tempfile
    import os
    import zipfile
    from io import BytesIO

    async def run_validation():
        """Async function to run the MobilityData validation"""
        task = None
        async with CeleryAsyncSessionLocal() as db:
            try:
                # Get task record
                result = await db.execute(
                    select(AsyncTask).where(AsyncTask.id == task_db_id)
                )
                task = result.scalar_one_or_none()

                if not task:
                    return {
                        "success": False,
                        "error": f"Task record {task_db_id} not found"
                    }

                # Check if task was cancelled
                if task.status == TaskStatus.CANCELLED.value:
                    return {
                        "success": False,
                        "error": "Task was cancelled before starting",
                        "task_id": task_db_id,
                    }

                # Update task status
                task.status = TaskStatus.RUNNING.value
                task.started_at = datetime.utcnow().isoformat() + 'Z'
                task.progress = 0.0
                task.result_data = {"status": "Starting MobilityData validation..."}
                await db.commit()

                # Get the feed
                from app.models.gtfs import GTFSFeed
                feed_query = select(GTFSFeed).where(GTFSFeed.id == feed_id)
                feed_result = await db.execute(feed_query)
                feed = feed_result.scalar_one_or_none()

                if not feed:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = f"Feed {feed_id} not found"
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()
                    return {"success": False, "error": f"Feed {feed_id} not found"}

                task.progress = 10.0
                task.result_data = {"status": "Exporting GTFS feed..."}
                await db.commit()

                # Export the feed to a temporary GTFS ZIP file
                from app.services.gtfs_service import GTFSService
                from app.schemas.gtfs_import import GTFSExportOptions

                # Create export options
                export_options = GTFSExportOptions(
                    agency_id=feed.agency_id,
                    feed_id=feed_id
                )

                # Export the feed to bytes
                try:
                    zip_content = await GTFSService.export_gtfs_zip(export_options, db)
                except Exception as e:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = f"Failed to export feed for validation: {str(e)}"
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()
                    return {"success": False, "error": f"Failed to export feed: {str(e)}"}

                if not zip_content:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = "Failed to export feed for validation - empty content"
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()
                    return {"success": False, "error": "Failed to export feed - empty content"}

                task.progress = 30.0
                task.result_data = {"status": "Running MobilityData validator..."}
                await db.commit()

                # Save to temporary file in the shared validation directory
                # (needed for Docker-in-Docker volume mounts to work)
                from app.services.mobilitydata_validator import mobilitydata_validator
                validation_base_dir = mobilitydata_validator.output_base_path
                temp_dir = validation_base_dir / f"input_{feed_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
                temp_dir.mkdir(parents=True, exist_ok=True)
                gtfs_zip_path = str(temp_dir / f"feed_{feed_id}.zip")

                with open(gtfs_zip_path, 'wb') as f:
                    f.write(zip_content)

                task.progress = 40.0
                await db.commit()

                # Run MobilityData validator

                validation_result = await mobilitydata_validator.validate_feed_file(
                    gtfs_zip_path=gtfs_zip_path,
                    feed_name=feed.name or f"feed_{feed_id}",
                    country_code=country_code,
                )

                task.progress = 90.0
                await db.commit()

                # Cleanup temp file and directory
                try:
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass

                # Update task with results
                if validation_result.get("success"):
                    report_json = validation_result.get("report_json", {})
                    notices = report_json.get("notices", [])

                    # Count by severity
                    error_count = len([n for n in notices if n.get("severity") == "ERROR"])
                    warning_count = len([n for n in notices if n.get("severity") == "WARNING"])
                    info_count = len([n for n in notices if n.get("severity") == "INFO"])

                    is_valid = error_count == 0

                    task.status = TaskStatus.COMPLETED.value
                    task.progress = 100.0
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    task.result_data = {
                        "success": True,
                        "valid": is_valid,
                        "feed_id": feed_id,
                        "feed_name": feed.name,
                        "validation_id": validation_result.get("validation_id"),
                        "error_count": error_count,
                        "warning_count": warning_count,
                        "info_count": info_count,
                        "total_notices": len(notices),
                        "duration_seconds": validation_result.get("duration_seconds"),
                        "report_html_path": validation_result.get("report_html_path"),
                        "report_json": report_json,
                        "validator": "mobilitydata",
                    }
                    await db.commit()

                    return {
                        "success": True,
                        "valid": is_valid,
                        "task_id": task_db_id,
                        "validation_id": validation_result.get("validation_id"),
                    }
                else:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = validation_result.get("error", "Validation failed")
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    task.result_data = {
                        "success": False,
                        "error": validation_result.get("error"),
                        "validator": "mobilitydata",
                    }
                    await db.commit()

                    return {
                        "success": False,
                        "error": validation_result.get("error"),
                        "task_id": task_db_id,
                    }

            except Exception as e:
                if task:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = str(e)
                    task.error_traceback = traceback.format_exc()
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    await db.commit()

                return {
                    "success": False,
                    "error": str(e),
                    "task_id": task_db_id,
                }

    # Always use asyncio.run() for clean event loop management
    return asyncio.run(run_validation())


@celery_app.task(name="app.tasks.validate_gtfs_file_mobilitydata", bind=True)
def validate_gtfs_file_mobilitydata(
    self,
    task_db_id: int,
    file_content: bytes,
    filename: str,
    country_code: str = "",
):
    """
    Validate an uploaded GTFS file using MobilityData GTFS Validator.

    This task validates a file BEFORE import, allowing users to see validation
    results and decide whether to proceed with the import.

    Args:
        task_db_id: AsyncTask record ID in database
        file_content: The GTFS ZIP file content as bytes
        filename: Original filename for reporting
        country_code: Optional ISO country code for location-specific validations
    """
    import tempfile
    import os

    async def run_file_validation():
        """Async function to run the MobilityData validation on uploaded file"""
        task = None
        async with CeleryAsyncSessionLocal() as db:
            try:
                # Get task record
                result = await db.execute(
                    select(AsyncTask).where(AsyncTask.id == task_db_id)
                )
                task = result.scalar_one_or_none()

                if not task:
                    return {
                        "success": False,
                        "error": f"Task record {task_db_id} not found"
                    }

                # Check if task was cancelled
                if task.status == TaskStatus.CANCELLED.value:
                    return {
                        "success": False,
                        "error": "Task was cancelled before starting",
                        "task_id": task_db_id,
                    }

                # Update task status
                task.status = TaskStatus.RUNNING.value
                task.started_at = datetime.utcnow().isoformat() + 'Z'
                task.progress = 10.0
                task.result_data = {"status": "Starting MobilityData validation..."}
                await db.commit()

                # Save file content to temporary file in the shared validation directory
                # (needed for Docker-in-Docker volume mounts to work)
                from app.services.mobilitydata_validator import mobilitydata_validator
                validation_base_dir = mobilitydata_validator.output_base_path
                temp_dir = validation_base_dir / f"input_file_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
                temp_dir.mkdir(parents=True, exist_ok=True)
                gtfs_zip_path = str(temp_dir / (filename or "upload.zip"))

                task.progress = 20.0
                task.result_data = {"status": "Saving uploaded file..."}
                await db.commit()

                with open(gtfs_zip_path, 'wb') as f:
                    f.write(file_content)

                task.progress = 30.0
                task.result_data = {"status": "Running MobilityData validator..."}
                await db.commit()

                # Run MobilityData validator

                feed_name = filename.replace('.zip', '') if filename else 'upload'
                validation_result = await mobilitydata_validator.validate_feed_file(
                    gtfs_zip_path=gtfs_zip_path,
                    feed_name=feed_name,
                    country_code=country_code,
                )

                task.progress = 90.0
                await db.commit()

                # Move GTFS file to validation output directory for later access
                # (don't delete - keep for report viewing and potential retry)
                validation_id = validation_result.get("validation_id")
                gtfs_file_final_path = None
                if validation_id:
                    output_dir = validation_base_dir / validation_id
                    output_dir.mkdir(parents=True, exist_ok=True)
                    gtfs_file_final_path = str(output_dir / (filename or "upload.zip"))
                    try:
                        import shutil
                        shutil.move(gtfs_zip_path, gtfs_file_final_path)
                        # Remove empty temp directory
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    except Exception:
                        gtfs_file_final_path = gtfs_zip_path  # Keep original if move fails

                # Update task with results
                if validation_result.get("success"):
                    report_json = validation_result.get("report_json", {})
                    notices = report_json.get("notices", [])

                    # Count by severity
                    error_count = len([n for n in notices if n.get("severity") == "ERROR"])
                    warning_count = len([n for n in notices if n.get("severity") == "WARNING"])
                    info_count = len([n for n in notices if n.get("severity") == "INFO"])

                    is_valid = error_count == 0

                    task.status = TaskStatus.COMPLETED.value
                    task.progress = 100.0
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    task.result_data = {
                        "success": True,
                        "valid": is_valid,
                        "filename": filename,
                        "validation_id": validation_result.get("validation_id"),
                        "error_count": error_count,
                        "warning_count": warning_count,
                        "info_count": info_count,
                        "total_notices": len(notices),
                        "duration_seconds": validation_result.get("duration_seconds"),
                        "report_html_path": validation_result.get("report_html_path"),
                        "gtfs_file_path": gtfs_file_final_path,
                        "report_json": report_json,
                        "validator": "mobilitydata",
                        "pre_import": True,
                        "can_retry": True,  # Allow retry even for successful validation
                    }
                    await db.commit()

                    return {
                        "success": True,
                        "valid": is_valid,
                        "task_id": task_db_id,
                        "validation_id": validation_result.get("validation_id"),
                        "error_count": error_count,
                        "warning_count": warning_count,
                    }
                else:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = validation_result.get("error", "Validation failed")
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    task.result_data = {
                        "success": False,
                        "error": validation_result.get("error"),
                        "filename": filename,
                        "gtfs_file_path": gtfs_file_final_path,
                        "validator": "mobilitydata",
                        "pre_import": True,
                        "can_retry": True,  # Enable retry for failed validation
                    }
                    # Store file info in input_data for retry
                    task.input_data = {
                        **(task.input_data or {}),
                        "gtfs_file_path": gtfs_file_final_path,
                        "filename": filename,
                        "country_code": country_code,
                    }
                    await db.commit()

                    return {
                        "success": False,
                        "error": validation_result.get("error"),
                        "task_id": task_db_id,
                    }

            except Exception as e:
                if task:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = str(e)
                    task.error_traceback = traceback.format_exc()
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    task.result_data = {
                        **(task.result_data or {}),
                        "success": False,
                        "error": str(e),
                        "can_retry": True,  # Enable retry for failed validation
                    }
                    await db.commit()

                return {
                    "success": False,
                    "error": str(e),
                    "task_id": task_db_id,
                }

    # Always use asyncio.run() for clean event loop management
    return asyncio.run(run_file_validation())


@celery_app.task(name="app.tasks.export_route", bind=True)
def export_route(
    self,
    task_db_id: int,
    payload_dict: Dict[str, Any],
    user_id: int,
):
    """
    Export a route from Route Creator to GTFS feed asynchronously.

    Creates route, stops (new only), shapes, trips, and stop_times
    in a single atomic transaction with progress tracking.

    Args:
        task_db_id: AsyncTask record ID in database
        payload_dict: RouteExportPayload as dict
        user_id: User ID performing the export
    """
    from app.schemas.route_export import RouteExportPayload
    from app.services.route_export_service import route_export_service

    async def run_export():
        """Async function to run the route export"""
        task = None
        async with CeleryAsyncSessionLocal() as db:
            try:
                # Get the task record
                result = await db.execute(
                    select(AsyncTask).where(AsyncTask.id == task_db_id)
                )
                task = result.scalar_one_or_none()

                if not task:
                    return {
                        "success": False,
                        "error": f"Task record {task_db_id} not found"
                    }

                # Check if task was cancelled before we even started
                if task.status == TaskStatus.CANCELLED.value:
                    return {
                        "success": False,
                        "error": "Task was cancelled before starting",
                        "task_id": task_db_id,
                    }

                # Update task status to RUNNING
                task.status = TaskStatus.RUNNING.value
                task.started_at = datetime.utcnow().isoformat() + 'Z'
                task.progress = 0.0
                await db.commit()

                # Parse payload from dict
                payload = RouteExportPayload(**payload_dict)

                # Define progress callback
                last_progress = [0.0]

                async def update_progress(progress: float, message: str):
                    """Update task progress in database"""
                    # Only update if progress changed by at least 1%
                    if progress - last_progress[0] >= 1.0:
                        # Check if cancelled periodically
                        if await check_task_cancelled(db, task_db_id):
                            raise TaskCancelledException("Task was cancelled")

                        task.progress = progress
                        task.result_data = {
                            **(task.result_data or {}),
                            "current_step": message
                        }
                        await db.commit()
                        last_progress[0] = progress
                        print(f"[ROUTE EXPORT TASK {task_db_id}] Progress: {progress:.1f}% - {message}")

                # Validate payload first
                validation = await route_export_service.validate_payload(db, payload)
                if not validation.valid:
                    task.status = TaskStatus.FAILED.value
                    task.error_message = "; ".join(validation.errors)
                    task.completed_at = datetime.utcnow().isoformat() + 'Z'
                    task.result_data = {
                        "success": False,
                        "errors": validation.errors,
                        "warnings": validation.warnings,
                        "can_retry": True,
                    }
                    await db.commit()
                    return {
                        "success": False,
                        "error": "Validation failed",
                        "errors": validation.errors,
                        "task_id": task_db_id,
                    }

                # Run the export
                export_result = await route_export_service.export_route(
                    db=db,
                    payload=payload,
                    user_id=user_id,
                    progress_callback=update_progress,
                )

                # Commit the transaction
                await db.commit()

                # Update task as completed
                task.status = TaskStatus.COMPLETED.value
                task.progress = 100.0
                task.completed_at = datetime.utcnow().isoformat() + 'Z'
                task.result_data = {
                    "success": True,
                    "route_id": export_result.route_id,
                    "feed_id": export_result.feed_id,
                    "stops_created": export_result.stops_created,
                    "stops_linked": export_result.stops_linked,
                    "shape_points_created": export_result.shape_points_created,
                    "trips_created": export_result.trips_created,
                    "stop_times_created": export_result.stop_times_created,
                    "warnings": export_result.warnings,
                }
                await db.commit()

                return {
                    "success": True,
                    "task_id": task_db_id,
                    "route_id": export_result.route_id,
                }

            except TaskCancelledException:
                if task:
                    await mark_task_cancelled(db, task)
                return {
                    "success": False,
                    "error": "Task was cancelled",
                    "task_id": task_db_id,
                }

            except Exception as e:
                # Rollback the transaction on error
                await db.rollback()

                error_msg = str(e)
                error_tb = traceback.format_exc()

                # Update task as failed - refetch to avoid expired attributes
                if task:
                    try:
                        # Refetch the task to get a fresh instance
                        result = await db.execute(
                            select(AsyncTask).where(AsyncTask.id == task_db_id)
                        )
                        task = result.scalar_one_or_none()
                        if task:
                            task.status = TaskStatus.FAILED.value
                            task.error_message = error_msg
                            task.error_traceback = error_tb
                            task.completed_at = datetime.utcnow().isoformat() + 'Z'
                            task.result_data = {
                                "success": False,
                                "error": error_msg,
                                "can_retry": True,
                            }
                            await db.commit()
                    except Exception as update_error:
                        print(f"[ROUTE EXPORT TASK {task_db_id}] Failed to update task status: {update_error}")

                return {
                    "success": False,
                    "error": error_msg,
                    "task_id": task_db_id,
                }

    # Always use asyncio.run() for clean event loop management
    return asyncio.run(run_export())
