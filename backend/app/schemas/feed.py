"""
GTFS Feed schemas
"""

from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_serializer, ConfigDict


class GTFSFeedBase(BaseModel):
    """Base schema for GTFS Feed"""
    name: str = Field(..., description="Descriptive name for this feed")
    description: Optional[str] = Field(None, description="Optional description")
    version: Optional[str] = Field(None, description="Optional version identifier")


class GTFSFeedCreate(GTFSFeedBase):
    """Schema for creating a GTFS Feed"""
    agency_id: int = Field(..., description="Agency this feed belongs to")
    filename: Optional[str] = Field(None, description="Original filename")


class GTFSFeedUpdate(BaseModel):
    """Schema for updating a GTFS Feed"""
    name: Optional[str] = Field(None, description="Update feed name")
    description: Optional[str] = Field(None, description="Update description")
    version: Optional[str] = Field(None, description="Update version")
    is_active: Optional[bool] = Field(None, description="Activate or deactivate feed")


class GTFSFeedResponse(GTFSFeedBase):
    """Schema for GTFS Feed response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    agency_id: int
    imported_at: str
    imported_by: Optional[int] = None
    is_active: bool
    filename: Optional[str] = None
    total_routes: Optional[int] = None
    total_stops: Optional[int] = None
    total_trips: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, dt: datetime, _info) -> str:
        """Serialize datetime to ISO format string"""
        if dt.tzinfo:
            return dt.isoformat()
        return dt.isoformat() + 'Z'


class GTFSFeedListResponse(BaseModel):
    """Schema for paginated list of GTFS Feeds"""
    feeds: List[GTFSFeedResponse]
    total: int
    skip: int
    limit: int
