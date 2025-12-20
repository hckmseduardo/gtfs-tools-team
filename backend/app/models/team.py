"""Team and Workspace models for collaborative GTFS editing"""

from typing import List, Optional
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Table, Column, ForeignKey, Enum as SQLEnum, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.base_class import Base, TimestampMixin


class TeamRole(str, enum.Enum):
    """
    Roles within a team.

    - OWNER: Full control (invite users, change roles, create workspaces, full access)
    - ADMIN: Can manage members (except owners), invite users, full workspace access
    - EDITOR: Can edit data in workspaces they have access to
    - VIEWER: Read-only access in workspaces they have access to
    """
    OWNER = "owner"    # Full control, can manage team, workspaces, and all members
    ADMIN = "admin"    # Can manage members (except owners), invite users
    EDITOR = "editor"  # Can edit data in workspaces they have access to
    VIEWER = "viewer"  # Read-only access in workspaces they have access to


# Role hierarchy mapping: TeamRole -> permission level
TEAM_ROLE_HIERARCHY = {
    TeamRole.OWNER: 4,   # Full control
    TeamRole.ADMIN: 3,   # Can manage members (except owners)
    TeamRole.EDITOR: 2,  # Can edit
    TeamRole.VIEWER: 1,  # Read-only
}


class InvitationStatus(str, enum.Enum):
    """Status of team invitations"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


# Association table for workspaces and agencies
workspace_agencies = Table(
    "workspace_agencies",
    Base.metadata,
    Column("workspace_id", Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
    Column("agency_id", Integer, ForeignKey("agencies.id", ondelete="CASCADE"), primary_key=True),
)


# Association table for workspace member access
# This tracks which non-owner team members can access which workspaces
# Owners automatically have access to all workspaces in their team
workspace_members = Table(
    "workspace_members",
    Base.metadata,
    Column("workspace_id", Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class FeedRole(str, enum.Enum):
    """Roles for feed-level access"""
    OWNER = "owner"  # Full control, can delete feed
    ADMIN = "admin"  # Can manage feed settings and permissions
    CONTRIBUTOR = "contributor"  # Can edit feed data
    READ_ONLY = "read_only"  # Can view feed data only


# Feed role hierarchy
FEED_ROLE_HIERARCHY = {
    FeedRole.OWNER: 4,
    FeedRole.ADMIN: 3,
    FeedRole.CONTRIBUTOR: 2,
    FeedRole.READ_ONLY: 1,
}


# Association table for feed-user permissions
feed_users = Table(
    "feed_users",
    Base.metadata,
    Column("feed_id", Integer, ForeignKey("gtfs_feeds.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "role",
        SQLEnum(FeedRole, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=FeedRole.READ_ONLY,
        comment="User role for this feed",
    ),
)


# Association table for feed-team permissions
feed_teams = Table(
    "feed_teams",
    Base.metadata,
    Column("feed_id", Integer, ForeignKey("gtfs_feeds.id", ondelete="CASCADE"), primary_key=True),
    Column("team_id", Integer, ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "role",
        SQLEnum(FeedRole, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=FeedRole.READ_ONLY,
        comment="Team role for this feed",
    ),
)


class Team(Base, TimestampMixin):
    """Team model - groups of users who collaborate on GTFS data"""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False, comment="URL-friendly identifier"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Creator of the team
    created_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id]
    )
    members: Mapped[List["TeamMember"]] = relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan"
    )
    workspaces: Mapped[List["Workspace"]] = relationship(
        "Workspace", back_populates="team", cascade="all, delete-orphan"
    )
    invitations: Mapped[List["TeamInvitation"]] = relationship(
        "TeamInvitation", back_populates="team", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Team {self.name}>"


class TeamMember(Base, TimestampMixin):
    """Association between users and teams with roles"""

    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[TeamRole] = mapped_column(
        SQLEnum(TeamRole, name="teamrole", create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=TeamRole.EDITOR
    )

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="members")
    user: Mapped["User"] = relationship("User")

    # Unique constraint: user can only be in a team once
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )

    def __repr__(self) -> str:
        return f"<TeamMember team_id={self.team_id} user_id={self.user_id} role={self.role}>"


class Workspace(Base, TimestampMixin):
    """Workspace model - containers for organizing agencies within a team"""

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(
        String(100), index=True, nullable=False, comment="URL-friendly identifier"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="workspaces")
    agencies: Mapped[List["Agency"]] = relationship(
        "Agency", secondary=workspace_agencies, backref="workspaces"
    )
    # Members who have explicit access to this workspace (non-owners)
    members: Mapped[List["User"]] = relationship(
        "User", secondary=workspace_members, backref="accessible_workspaces"
    )

    # Unique constraint: slug must be unique within a team
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )

    def __repr__(self) -> str:
        return f"<Workspace {self.name}>"


class TeamInvitation(Base, TimestampMixin):
    """Invitation to join a team"""

    __tablename__ = "team_invitations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[TeamRole] = mapped_column(
        SQLEnum(TeamRole, name="teamrole", create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=TeamRole.EDITOR
    )
    status: Mapped[InvitationStatus] = mapped_column(
        SQLEnum(InvitationStatus, name="invitationstatus", create_type=False),
        nullable=False, default=InvitationStatus.PENDING
    )

    # Token for accepting invitation
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Who sent the invitation
    invited_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Expiration
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # If accepted, which user accepted
    accepted_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="invitations")
    invited_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[invited_by_id])
    accepted_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[accepted_by_id])

    def __repr__(self) -> str:
        return f"<TeamInvitation team_id={self.team_id} email={self.email} status={self.status}>"
