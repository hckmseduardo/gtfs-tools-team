"""Celery application configuration"""

import asyncio
import logging
from datetime import datetime

from celery import Celery
from celery.signals import worker_ready
from app.core.config import settings

logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery(
    "gtfs_editor",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks"],  # Import tasks module
)

# Track worker startup time for orphan detection
WORKER_STARTUP_TIME: datetime | None = None


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    """
    Signal handler that runs when the Celery worker is ready.
    Detects and marks orphaned tasks (tasks that were 'running' when worker restarted).
    """
    global WORKER_STARTUP_TIME
    WORKER_STARTUP_TIME = datetime.utcnow()

    logger.info("Celery worker started. Checking for orphaned tasks...")

    # Run orphan detection asynchronously
    try:
        asyncio.run(_cleanup_orphaned_tasks())
    except Exception as e:
        logger.error(f"Error during orphan cleanup: {e}")


async def _cleanup_orphaned_tasks():
    """
    Find and mark orphaned tasks as failed.
    Orphaned tasks are those with status='running' that were started before
    the current worker startup.
    """
    from app.db.session import CeleryAsyncSessionLocal
    from app.models.task import TaskStatus
    from sqlalchemy import select, update, and_

    # Import the model here to avoid circular imports
    from app.db.base import AsyncTask

    async with CeleryAsyncSessionLocal() as db:
        try:
            # Find all tasks that are still marked as 'running'
            result = await db.execute(
                select(AsyncTask).where(
                    AsyncTask.status == TaskStatus.RUNNING.value
                )
            )
            orphaned_tasks = result.scalars().all()

            if not orphaned_tasks:
                logger.info("No orphaned tasks found.")
                return

            logger.warning(f"Found {len(orphaned_tasks)} orphaned task(s)")

            for task in orphaned_tasks:
                logger.warning(
                    f"Marking task {task.id} ({task.task_name}) as failed - "
                    f"was at {task.progress:.1f}% progress"
                )

                task.status = TaskStatus.FAILED.value
                task.completed_at = datetime.utcnow().isoformat() + 'Z'
                task.error_message = (
                    "Task was interrupted by worker restart. "
                    f"Progress was at {task.progress:.1f}%. "
                    "You may retry the operation."
                )
                task.error_traceback = (
                    "Worker restarted while task was in progress. "
                    "This can happen due to deployment, container restart, or system issues."
                )

                # Store recovery info in result_data
                task.result_data = {
                    **(task.result_data or {}),
                    "orphaned": True,
                    "orphaned_at": datetime.utcnow().isoformat() + 'Z',
                    "last_progress": task.progress,
                    "can_retry": True,
                }

            await db.commit()
            logger.info(f"Successfully marked {len(orphaned_tasks)} orphaned task(s) as failed")

        except Exception as e:
            logger.error(f"Error cleaning up orphaned tasks: {e}")
            await db.rollback()
            raise

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    # Acknowledge tasks immediately so they won't be requeued on worker restart
    task_acks_late=False,
    # Don't reject tasks on worker shutdown - they're already acked
    task_reject_on_worker_lost=False,
    # Store revoked task IDs so they won't restart
    worker_state_db='/tmp/celery_worker_state',
    # Keep revoked tasks in memory
    task_acks_on_failure_or_timeout=True,
)

# Optional: Configure periodic tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    # Example: cleanup old tasks every day at midnight
    "cleanup-old-tasks": {
        "task": "app.tasks.cleanup_old_tasks",
        "schedule": 86400.0,  # 24 hours in seconds
    },
    # Check external feed sources for updates every hour
    "check-feed-sources": {
        "task": "app.tasks.check_feed_sources",
        "schedule": 3600.0,  # 1 hour in seconds
    },
    # Check for orphaned tasks every 5 minutes (backup for worker_ready signal)
    "check-orphaned-tasks": {
        "task": "app.tasks.check_orphaned_tasks",
        "schedule": 300.0,  # 5 minutes in seconds
    },
}
