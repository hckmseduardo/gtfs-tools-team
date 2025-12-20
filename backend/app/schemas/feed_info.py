"""FeedInfo (GTFS) schemas for API requests and responses"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class FeedInfoBase(BaseModel):
    """Base feed info schema"""

    feed_publisher_name: str = Field(..., min_length=1, max_length=255, description="Publisher name")
    feed_publisher_url: str = Field(..., min_length=1, max_length=500, description="Publisher URL")
    feed_lang: str = Field(..., min_length=2, max_length=10, description="ISO 639-1 language code")
    default_lang: Optional[str] = Field(None, max_length=10, description="Default language code")
    feed_start_date: Optional[str] = Field(
        None, pattern=r"^\d{8}$", description="Feed start date (YYYYMMDD)"
    )
    feed_end_date: Optional[str] = Field(
        None, pattern=r"^\d{8}$", description="Feed end date (YYYYMMDD)"
    )
    feed_version: Optional[str] = Field(None, max_length=100, description="Feed version string")
    feed_contact_email: Optional[str] = Field(None, max_length=255, description="Contact email")
    feed_contact_url: Optional[str] = Field(None, max_length=500, description="Contact URL")
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields from GTFS")


class FeedInfoCreate(FeedInfoBase):
    """Schema for creating feed info"""

    feed_id: int = Field(..., description="Feed ID this info belongs to")


class FeedInfoUpdate(BaseModel):
    """Schema for updating feed info"""

    feed_publisher_name: Optional[str] = Field(None, min_length=1, max_length=255)
    feed_publisher_url: Optional[str] = Field(None, min_length=1, max_length=500)
    feed_lang: Optional[str] = Field(None, min_length=2, max_length=10)
    default_lang: Optional[str] = Field(None, max_length=10)
    feed_start_date: Optional[str] = Field(None, pattern=r"^\d{8}$")
    feed_end_date: Optional[str] = Field(None, pattern=r"^\d{8}$")
    feed_version: Optional[str] = Field(None, max_length=100)
    feed_contact_email: Optional[str] = Field(None, max_length=255)
    feed_contact_url: Optional[str] = Field(None, max_length=500)
    custom_fields: Optional[Dict[str, Any]] = None


class FeedInfoResponse(FeedInfoBase):
    """Schema for feed info response"""

    feed_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
