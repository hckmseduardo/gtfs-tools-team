"""Agency schemas for API requests and responses"""

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

from app.models.user import UserRole


class AgencyBase(BaseModel):
    """Base agency schema"""

    name: str = Field(..., min_length=1, max_length=255, description="Agency name (GTFS agency_name)")
    slug: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9_-]+$",
        description="URL-friendly identifier (lowercase, hyphens and underscores allowed)",
    )
    is_active: bool = Field(default=True, description="Whether agency is active")

    # GTFS agency.txt fields
    agency_id: Optional[str] = Field(
        None, max_length=100, description="GTFS agency_id - unique identifier for GTFS export"
    )
    agency_url: Optional[str] = Field(
        None, max_length=500, description="GTFS agency_url - agency website URL (required for GTFS)"
    )
    agency_timezone: Optional[str] = Field(
        None, max_length=100, description="GTFS agency_timezone - IANA timezone e.g. America/New_York (required for GTFS)"
    )
    agency_lang: Optional[str] = Field(
        None, max_length=10, description="GTFS agency_lang - ISO 639-1 language code e.g. en, fr, pt"
    )
    agency_phone: Optional[str] = Field(
        None, max_length=50, description="GTFS agency_phone - voice telephone number"
    )
    agency_fare_url: Optional[str] = Field(
        None, max_length=500, description="GTFS agency_fare_url - URL for fare information"
    )
    agency_email: Optional[str] = Field(
        None, max_length=255, description="GTFS agency_email - customer service email"
    )

    # Legacy fields (kept for backwards compatibility)
    contact_email: Optional[str] = Field(None, max_length=255, description="Legacy contact email")
    contact_phone: Optional[str] = Field(None, max_length=50, description="Legacy contact phone")
    website: Optional[str] = Field(None, max_length=500, description="Legacy website URL")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate slug format"""
        if not v:
            raise ValueError("Slug cannot be empty")
        if not v.islower():
            raise ValueError("Slug must be lowercase")
        if not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError("Slug can only contain lowercase letters, numbers, hyphens, and underscores")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("Slug cannot start or end with a hyphen")
        if "--" in v:
            raise ValueError("Slug cannot contain consecutive hyphens")
        return v


class AgencyCreate(AgencyBase):
    """Schema for creating a new agency"""

    pass


class AgencyUpdate(BaseModel):
    """Schema for updating an agency"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9_-]+$",
        description="URL-friendly identifier (lowercase, hyphens and underscores allowed)",
    )
    is_active: Optional[bool] = None

    # GTFS agency.txt fields
    agency_id: Optional[str] = Field(None, max_length=100)
    agency_url: Optional[str] = Field(None, max_length=500)
    agency_timezone: Optional[str] = Field(None, max_length=100)
    agency_lang: Optional[str] = Field(None, max_length=10)
    agency_phone: Optional[str] = Field(None, max_length=50)
    agency_fare_url: Optional[str] = Field(None, max_length=500)
    agency_email: Optional[str] = Field(None, max_length=255)

    # Legacy fields (kept for backwards compatibility)
    contact_email: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=50)
    website: Optional[str] = Field(None, max_length=500)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        """Validate slug format"""
        if v is None:
            return v
        if not v:
            raise ValueError("Slug cannot be empty")
        if not v.islower():
            raise ValueError("Slug must be lowercase")
        if not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError("Slug can only contain lowercase letters, numbers, hyphens, and underscores")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("Slug cannot start or end with a hyphen")
        if "--" in v:
            raise ValueError("Slug cannot contain consecutive hyphens")
        return v


class AgencyResponse(AgencyBase):
    """Schema for agency response"""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AgencyWithStats(AgencyResponse):
    """Agency response with statistics"""

    user_count: int = Field(default=0, description="Number of users with access")
    route_count: int = Field(default=0, description="Number of routes")
    stop_count: int = Field(default=0, description="Number of stops")
    trip_count: int = Field(default=0, description="Number of trips")


# User-Agency relationship schemas


class UserAgencyRole(BaseModel):
    """User's role for a specific agency"""

    user_id: int
    agency_id: int
    role: UserRole

    class Config:
        from_attributes = True


class AgencyMemberBase(BaseModel):
    """Base schema for agency member"""

    user_id: int = Field(..., description="User ID")
    role: UserRole = Field(default=UserRole.VIEWER, description="User role for this agency")


class AgencyMemberCreate(AgencyMemberBase):
    """Schema for adding a member to an agency"""

    pass


class AgencyMemberAdd(AgencyMemberBase):
    """Schema for adding a member to an agency (alias for backwards compatibility)"""

    pass


class AgencyMemberUpdate(BaseModel):
    """Schema for updating a member's role or status"""

    role: Optional[UserRole] = Field(None, description="New role for the user")
    is_active: Optional[bool] = Field(None, description="Whether user is active in this agency")


class AgencyMember(AgencyMemberBase):
    """Schema for agency member response"""

    user_id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool = True  # Default to True for backwards compatibility

    class Config:
        from_attributes = True


class AgencyMemberList(BaseModel):
    """List of agency members"""

    items: List[AgencyMember] = Field(..., description="List of agency members")
    total: int = Field(..., description="Total number of members")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


# List and pagination schemas


class AgencyList(BaseModel):
    """Paginated list of agencies"""

    items: List[AgencyResponse] = Field(..., description="List of agencies")
    total: int = Field(..., description="Total number of agencies")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


class AgencyListWithStats(BaseModel):
    """Paginated list of agencies with statistics"""

    items: List[AgencyWithStats] = Field(..., description="List of agencies with stats")
    total: int = Field(..., description="Total number of agencies")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")
