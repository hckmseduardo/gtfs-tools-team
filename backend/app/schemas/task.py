"""Task management schemas"""

from typing import Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.models.task import TaskStatus, TaskType


def parse_datetime(value: Any) -> Optional[datetime]:
    """Parse datetime from various formats"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Handle PostgreSQL timestamp format: '2025-11-28 13:29:46.652393+00'
        value = value.replace(' ', 'T').replace('+00', 'Z').replace('+00:00', 'Z')
        if not value.endswith('Z') and '+' not in value:
            value += 'Z'
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value


class TaskBase(BaseModel):
    """Base task schema"""

    task_name: str
    description: Optional[str] = None
    task_type: TaskType


class TaskCreate(TaskBase):
    """Create task schema"""

    celery_task_id: str
    user_id: int
    agency_id: Optional[int] = None
    input_data: Optional[dict[str, Any]] = None


class TaskUpdate(BaseModel):
    """Update task schema"""

    status: Optional[TaskStatus] = None
    progress: Optional[float] = Field(None, ge=0, le=100)
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    result_data: Optional[dict[str, Any]] = None


class TaskResponse(TaskBase):
    """Task response schema"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    celery_task_id: str
    user_id: int
    agency_id: Optional[int] = None
    status: TaskStatus
    progress: float
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    input_data: Optional[dict[str, Any]] = None
    result_data: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    @field_validator('started_at', 'completed_at', 'created_at', 'updated_at', mode='before')
    @classmethod
    def parse_datetime_fields(cls, v):
        return parse_datetime(v)


class TaskList(BaseModel):
    """Paginated task list"""

    items: list[TaskResponse]
    total: int
    page: int
    page_size: int
    pages: int
