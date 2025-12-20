"""Pydantic schemas for external feed source management"""

from typing import Optional, Any
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime

from app.models.feed_source import FeedSourceStatus, FeedSourceType, CheckFrequency


class FeedSourceBase(BaseModel):
    """Base schema for feed source"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    source_type: FeedSourceType = FeedSourceType.GTFS_STATIC
    url: str = Field(..., max_length=2000)
    auth_type: Optional[str] = Field(None, max_length=50)
    auth_header: Optional[str] = Field(None, max_length=100)
    auth_value: Optional[str] = Field(None, max_length=500)
    check_frequency: CheckFrequency = CheckFrequency.DAILY
    is_enabled: bool = True
    auto_import: bool = False
    import_options: Optional[dict[str, Any]] = None


class FeedSourceCreate(FeedSourceBase):
    """Schema for creating a feed source"""
    agency_id: int


class FeedSourceUpdate(BaseModel):
    """Schema for updating a feed source"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    source_type: Optional[FeedSourceType] = None
    url: Optional[str] = Field(None, max_length=2000)
    auth_type: Optional[str] = Field(None, max_length=50)
    auth_header: Optional[str] = Field(None, max_length=100)
    auth_value: Optional[str] = Field(None, max_length=500)
    check_frequency: Optional[CheckFrequency] = None
    is_enabled: Optional[bool] = None
    auto_import: Optional[bool] = None
    import_options: Optional[dict[str, Any]] = None


class FeedSourceResponse(FeedSourceBase):
    """Schema for feed source response"""
    id: int
    agency_id: int
    status: FeedSourceStatus
    last_checked_at: Optional[datetime] = None
    last_successful_check: Optional[datetime] = None
    last_import_at: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None
    created_feed_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FeedSourceListResponse(BaseModel):
    """Schema for list response"""
    items: list[FeedSourceResponse]
    total: int


class FeedSourceCheckRequest(BaseModel):
    """Request to manually trigger a check"""
    force_import: bool = Field(False, description="Import even if no changes detected")


class FeedSourceCheckResponse(BaseModel):
    """Response from a manual check"""
    success: bool
    message: str
    content_changed: bool = False
    import_triggered: bool = False
    task_id: Optional[str] = None


class FeedSourceCheckLogResponse(BaseModel):
    """Schema for check log response"""
    id: int
    feed_source_id: int
    checked_at: datetime
    success: bool
    http_status: Optional[int] = None
    content_changed: bool = False
    content_size: Optional[int] = None
    import_triggered: bool = False
    import_task_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FeedSourceCheckLogListResponse(BaseModel):
    """Schema for check log list response"""
    items: list[FeedSourceCheckLogResponse]
    total: int
