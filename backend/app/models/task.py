"""Asynchronous task tracking models"""

from typing import Any
from sqlalchemy import String, Integer, ForeignKey, Text, JSON, Float, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.base_class import Base, TimestampMixin


class TaskStatus(str, enum.Enum):
    """Task status"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, enum.Enum):
    """Task types"""

    IMPORT_GTFS = "import_gtfs"
    EXPORT_GTFS = "export_gtfs"
    VALIDATE_GTFS = "validate_gtfs"
    BULK_UPDATE = "bulk_update"
    BULK_DELETE = "bulk_delete"
    DELETE_FEED = "delete_feed"
    DELETE_AGENCY = "delete_agency"
    MERGE_AGENCIES = "merge_agencies"
    SPLIT_AGENCY = "split_agency"
    CLONE_FEED = "clone_feed"
    ROUTE_EXPORT = "route_export"


class AsyncTask(Base, TimestampMixin):
    """Asynchronous task tracking"""

    __tablename__ = "async_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Task identification
    celery_task_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False, comment="Celery task ID"
    )
    task_type: Mapped[str] = mapped_column(Enum(TaskType, native_enum=True, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Task ownership
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agency_id: Mapped[int | None] = mapped_column(
        ForeignKey("agencies.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Task status
    status: Mapped[str] = mapped_column(
        Enum(TaskStatus, native_enum=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TaskStatus.PENDING.value,
        index=True
    )
    progress: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="Progress percentage (0-100)"
    )

    # Task execution
    started_at: Mapped[str | None] = mapped_column(String(100), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Task data
    input_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Input parameters"
    )
    result_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Result data"
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    agency: Mapped["Agency | None"] = relationship("Agency")

    def __repr__(self) -> str:
        return f"<AsyncTask {self.task_name} ({self.status})>"
