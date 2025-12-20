"""Team and Workspace schemas for API requests and responses"""

from typing import Optional, List, Union
from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime

from app.models.team import TeamRole, InvitationStatus


def validate_team_role(v: Union[str, TeamRole]) -> TeamRole:
    """Validate and normalize TeamRole, accepting both lowercase and uppercase values"""
    if isinstance(v, TeamRole):
        return v
    if isinstance(v, str):
        # Try lowercase value match first (owner, editor, viewer)
        try:
            return TeamRole(v.lower())
        except ValueError:
            pass
        # Try uppercase enum name (OWNER, EDITOR, VIEWER)
        try:
            return TeamRole[v.upper()]
        except KeyError:
            pass
    raise ValueError(f"Invalid team role: {v}. Must be one of: owner, editor, viewer")


# ==================== Team Schemas ====================


class TeamBase(BaseModel):
    """Base team schema"""

    name: str = Field(..., min_length=1, max_length=255, description="Team name")
    slug: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9-]+$",
        description="URL-friendly identifier (lowercase, hyphens only)",
    )
    description: Optional[str] = Field(None, max_length=2000, description="Team description")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate slug format"""
        if not v:
            raise ValueError("Slug cannot be empty")
        if not v.islower():
            raise ValueError("Slug must be lowercase")
        if not all(c.isalnum() or c == "-" for c in v):
            raise ValueError("Slug can only contain lowercase letters, numbers, and hyphens")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("Slug cannot start or end with a hyphen")
        if "--" in v:
            raise ValueError("Slug cannot contain consecutive hyphens")
        return v


class TeamCreate(TeamBase):
    """Schema for creating a new team"""

    pass


class TeamUpdate(BaseModel):
    """Schema for updating a team"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9-]+$",
    )
    description: Optional[str] = Field(None, max_length=2000)
    is_active: Optional[bool] = None

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
        if not all(c.isalnum() or c == "-" for c in v):
            raise ValueError("Slug can only contain lowercase letters, numbers, and hyphens")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("Slug cannot start or end with a hyphen")
        if "--" in v:
            raise ValueError("Slug cannot contain consecutive hyphens")
        return v


class TeamMemberInfo(BaseModel):
    """Basic team member info for team response"""

    id: int
    user_id: int
    email: str
    full_name: str
    role: TeamRole

    class Config:
        from_attributes = True


class WorkspaceSummary(BaseModel):
    """Summary workspace info for team response"""

    id: int
    name: str
    slug: str
    is_active: bool
    agency_count: int = 0

    class Config:
        from_attributes = True


class TeamResponse(TeamBase):
    """Schema for team response"""

    id: int
    is_active: bool
    created_by_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TeamWithDetails(TeamResponse):
    """Team response with members and workspaces"""

    members: List[TeamMemberInfo] = Field(default_factory=list)
    workspaces: List[WorkspaceSummary] = Field(default_factory=list)
    member_count: int = 0
    workspace_count: int = 0


class TeamList(BaseModel):
    """Paginated list of teams"""

    items: List[TeamResponse] = Field(..., description="List of teams")
    total: int = Field(..., description="Total number of teams")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


# ==================== Team Member Schemas ====================


class TeamMemberBase(BaseModel):
    """Base team member schema"""

    user_id: int = Field(..., description="User ID")
    role: TeamRole = Field(default=TeamRole.EDITOR, description="Role in the team")

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v):
        return validate_team_role(v)


class TeamMemberCreate(TeamMemberBase):
    """Schema for adding a member to a team"""

    pass


class TeamMemberUpdate(BaseModel):
    """Schema for updating a member's role"""

    role: TeamRole = Field(..., description="New role for the member")

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v):
        return validate_team_role(v)


class TeamMemberResponse(BaseModel):
    """Schema for team member response"""

    id: int
    team_id: int
    user_id: int
    role: TeamRole
    email: str
    full_name: str
    created_at: datetime

    class Config:
        from_attributes = True


class TeamMemberList(BaseModel):
    """List of team members"""

    items: List[TeamMemberResponse] = Field(..., description="List of team members")
    total: int = Field(..., description="Total number of members")


# ==================== Workspace Schemas ====================


class WorkspaceBase(BaseModel):
    """Base workspace schema"""

    name: str = Field(..., min_length=1, max_length=255, description="Workspace name")
    slug: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9-]+$",
        description="URL-friendly identifier (lowercase, hyphens only)",
    )
    description: Optional[str] = Field(None, max_length=2000, description="Workspace description")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate slug format"""
        if not v:
            raise ValueError("Slug cannot be empty")
        if not v.islower():
            raise ValueError("Slug must be lowercase")
        if not all(c.isalnum() or c == "-" for c in v):
            raise ValueError("Slug can only contain lowercase letters, numbers, and hyphens")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("Slug cannot start or end with a hyphen")
        if "--" in v:
            raise ValueError("Slug cannot contain consecutive hyphens")
        return v


class WorkspaceCreate(WorkspaceBase):
    """Schema for creating a new workspace"""

    pass


class WorkspaceUpdate(BaseModel):
    """Schema for updating a workspace"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9-]+$",
    )
    description: Optional[str] = Field(None, max_length=2000)
    is_active: Optional[bool] = None

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
        if not all(c.isalnum() or c == "-" for c in v):
            raise ValueError("Slug can only contain lowercase letters, numbers, and hyphens")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("Slug cannot start or end with a hyphen")
        if "--" in v:
            raise ValueError("Slug cannot contain consecutive hyphens")
        return v


class AgencySummary(BaseModel):
    """Summary agency info for workspace response"""

    id: int
    name: str
    slug: str
    is_active: bool

    class Config:
        from_attributes = True


class WorkspaceResponse(WorkspaceBase):
    """Schema for workspace response"""

    id: int
    team_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkspaceWithDetails(WorkspaceResponse):
    """Workspace response with agencies"""

    agencies: List[AgencySummary] = Field(default_factory=list)
    agency_count: int = 0


class WorkspaceList(BaseModel):
    """Paginated list of workspaces"""

    items: List[WorkspaceResponse] = Field(..., description="List of workspaces")
    total: int = Field(..., description="Total number of workspaces")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


class WorkspaceAgencyAdd(BaseModel):
    """Schema for adding an agency to a workspace"""

    agency_id: int = Field(..., description="Agency ID to add to the workspace")


class WorkspaceAgencyRemove(BaseModel):
    """Schema for removing an agency from a workspace"""

    agency_id: int = Field(..., description="Agency ID to remove from the workspace")


# ==================== Team Invitation Schemas ====================


class TeamInvitationCreate(BaseModel):
    """Schema for creating a team invitation"""

    email: EmailStr = Field(..., description="Email address to invite")
    role: TeamRole = Field(default=TeamRole.EDITOR, description="Role to assign when accepted")

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v):
        return validate_team_role(v)


class TeamInvitationResponse(BaseModel):
    """Schema for team invitation response"""

    id: int
    team_id: int
    email: str
    role: TeamRole
    status: InvitationStatus
    invited_by_id: Optional[int]
    invited_by_name: Optional[str] = None
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class TeamInvitationList(BaseModel):
    """List of team invitations"""

    items: List[TeamInvitationResponse] = Field(..., description="List of invitations")
    total: int = Field(..., description="Total number of invitations")


class TeamInvitationAccept(BaseModel):
    """Schema for accepting a team invitation"""

    token: str = Field(..., description="Invitation token")


class TeamInvitationPublic(BaseModel):
    """Public schema for invitation (used when accepting)"""

    team_name: str
    team_slug: str
    role: TeamRole
    invited_by_name: Optional[str]
    expires_at: datetime
    is_expired: bool = False

    class Config:
        from_attributes = True
