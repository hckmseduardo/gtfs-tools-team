"""User schemas for API requests and responses"""

from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

from app.models.user import UserRole


class UserBase(BaseModel):
    """Base user schema"""

    email: EmailStr = Field(..., description="User email address")
    full_name: str = Field(..., min_length=1, max_length=255, description="User's full name")


class UserCreate(UserBase):
    """Schema for creating a new user"""

    password: str = Field(..., min_length=8, max_length=100, description="User password (min 8 chars)")


class UserUpdate(BaseModel):
    """Schema for updating a user"""

    email: Optional[EmailStr] = Field(None, description="User email address")
    full_name: Optional[str] = Field(None, min_length=1, max_length=255, description="User's full name")
    is_active: Optional[bool] = Field(None, description="Whether user is active")


class UserPasswordUpdate(BaseModel):
    """Schema for updating user password"""

    current_password: str = Field(..., description="Current password for verification")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password (min 8 chars)")


class UserResponse(BaseModel):
    """Schema for user response"""

    id: int
    email: str = Field(..., description="User email address")  # Use str to allow synthetic emails
    full_name: str = Field(..., description="User's full name")
    is_active: bool
    is_superuser: bool
    role: Optional[UserRole] = Field(None, description="Global user role (if superuser)")
    azure_ad_object_id: Optional[str] = None
    azure_ad_tenant_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserWithAgencies(UserResponse):
    """User response with their agency memberships"""

    agencies: List["UserAgencyMembership"] = Field(default_factory=list, description="User's agency memberships")


class UserAgencyMembership(BaseModel):
    """Schema for user's membership in an agency"""

    agency_id: int = Field(..., description="Agency ID")
    agency_name: str = Field(..., description="Agency name")
    agency_slug: str = Field(..., description="Agency slug")
    role: UserRole = Field(..., description="User's role in this agency")
    is_active: bool = Field(..., description="Whether membership is active")

    class Config:
        from_attributes = True


# Update forward references
UserWithAgencies.model_rebuild()


# List and pagination schemas


class UserList(BaseModel):
    """Paginated list of users"""

    items: List[UserResponse] = Field(..., description="List of users")
    total: int = Field(..., description="Total number of users")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


class UserListWithAgencies(BaseModel):
    """Paginated list of users with agency info"""

    items: List[UserWithAgencies] = Field(..., description="List of users with agencies")
    total: int = Field(..., description="Total number of users")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")
