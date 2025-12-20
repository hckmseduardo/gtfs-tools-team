"""Authentication schemas"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional


class Token(BaseModel):
    """Access token response"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token payload data"""

    user_id: Optional[int] = None
    email: Optional[str] = None


class LoginRequest(BaseModel):
    """Login request for development/testing"""

    email: EmailStr
    password: str = Field(min_length=8)


class RegisterRequest(BaseModel):
    """User registration request - Creates user in Microsoft Entra ID"""

    email: EmailStr = Field(description="User email (must include domain, e.g., user@yourdomain.com)")
    display_name: str = Field(min_length=2, max_length=100, description="User's display name")
    password: str = Field(
        min_length=8,
        description="Initial password (user will be prompted to change on first login)",
    )
    force_change_password: bool = Field(
        default=True,
        description="Whether user must change password on first login",
    )


class EntraIDUserResponse(BaseModel):
    """Response after creating user in Entra ID"""

    id: int  # Local database ID
    email: str
    full_name: str
    azure_ad_object_id: str
    is_active: bool
    message: str = "User created successfully in Microsoft Entra ID"


class AzureADAuthRequest(BaseModel):
    """Azure AD authentication request"""

    code: str = Field(description="Authorization code from Azure AD")
    redirect_uri: str = Field(description="Redirect URI used in authorization request")


class AzureADTokenResponse(BaseModel):
    """Azure AD token response"""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: Optional[str] = None
    id_token: str


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""

    refresh_token: str


class UserInfo(BaseModel):
    """User information from token"""

    id: int
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    azure_ad_object_id: Optional[str] = None

    class Config:
        from_attributes = True
