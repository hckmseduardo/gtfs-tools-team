"""Audit log schemas"""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime


class AuditLogBase(BaseModel):
    """Base audit log schema"""

    action: str
    entity_type: str
    entity_id: str
    description: Optional[str] = None
    old_values: Optional[dict[str, Any]] = None
    new_values: Optional[dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AuditLogCreate(AuditLogBase):
    """Schema for creating an audit log"""

    user_id: int
    agency_id: Optional[int] = None


class AuditLogResponse(AuditLogBase):
    """Schema for audit log response"""

    id: int
    user_id: int
    agency_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogList(BaseModel):
    """Paginated list of audit logs"""

    items: list[AuditLogResponse]
    total: int
    skip: int
    limit: int


class AuditLogStats(BaseModel):
    """Audit log statistics"""

    total_logs: int
    action_counts: dict[str, int]
    entity_type_counts: dict[str, int]
