"""API dependencies for authentication and authorization"""

from typing import Optional, AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import verify_token
from app.db.session import AsyncSessionLocal
from app.db.base import User, Agency
from app.models.user import UserRole
from app.schemas.auth import TokenData

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="api/v1/auth/login",
    auto_error=True,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get database session

    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get current user from JWT token

    Args:
        token: JWT access token
        db: Database session

    Returns:
        User: Current authenticated user

    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Verify token
    payload = verify_token(token)
    if payload is None:
        raise credentials_exception

    # Check token type
    if payload.get("type") != "access":
        raise credentials_exception

    # Get user ID from token
    user_id: Optional[int] = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    # Get user from database
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get current active user (alias for get_current_user)

    Args:
        current_user: Current user from token

    Returns:
        User: Active user
    """
    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Require superuser privileges

    Args:
        current_user: Current user from token

    Returns:
        User: Superuser

    Raises:
        HTTPException: If user is not a superuser
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges",
        )
    return current_user


def require_role(required_role: UserRole):
    """
    Create a dependency that requires a specific role for an agency

    Args:
        required_role: The minimum required role

    Returns:
        Dependency function
    """

    async def role_checker(
        agency_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        """
        Check if user has required role for agency

        Access is granted if:
        1. User is a direct member with sufficient role
        2. User has team-based access (team role maps to agency permission)

        Note: Superusers must also be explicitly assigned to agencies.

        Args:
            agency_id: Agency ID to check access for
            current_user: Current authenticated user
            db: Database session

        Returns:
            User: User with required permissions

        Raises:
            HTTPException: If user doesn't have required role
        """
        # Check user-agency relationship
        from app.models.user import user_agencies
        from app.models.team import TeamMember, Workspace, workspace_agencies, workspace_members, TEAM_ROLE_HIERARCHY, TeamRole
        from sqlalchemy import or_, and_, exists

        # Agency role hierarchy
        agency_role_hierarchy = {
            UserRole.SUPER_ADMIN: 4,
            UserRole.AGENCY_ADMIN: 3,
            UserRole.EDITOR: 2,
            UserRole.VIEWER: 1,
        }

        result = await db.execute(
            select(user_agencies.c.role).where(
                user_agencies.c.user_id == current_user.id,
                user_agencies.c.agency_id == agency_id,
            )
        )
        user_role = result.scalar_one_or_none()
        effective_permission_level = 0

        if user_role is not None:
            # Direct membership - use the role directly
            effective_permission_level = agency_role_hierarchy.get(UserRole(user_role), 0)
        else:
            # Check team-based access with workspace membership
            # Owners have access to all workspaces, Editors/Viewers need explicit workspace access
            team_access = await db.execute(
                select(TeamMember.role)
                .select_from(TeamMember)
                .join(Workspace, TeamMember.team_id == Workspace.team_id)
                .join(workspace_agencies, Workspace.id == workspace_agencies.c.workspace_id)
                .where(
                    TeamMember.user_id == current_user.id,
                    workspace_agencies.c.agency_id == agency_id,
                    # Owners have access to all workspaces, others need explicit membership
                    or_(
                        TeamMember.role == TeamRole.OWNER,
                        exists(
                            select(workspace_members.c.workspace_id)
                            .where(
                                workspace_members.c.workspace_id == Workspace.id,
                                workspace_members.c.user_id == current_user.id
                            )
                        )
                    )
                )
            )
            team_roles = team_access.scalars().all()

            if not team_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No access to this agency",
                )

            # Get the highest permission level from team roles
            for team_role in team_roles:
                team_permission = TEAM_ROLE_HIERARCHY.get(TeamRole(team_role), 1)
                if team_permission > effective_permission_level:
                    effective_permission_level = team_permission

        # Check if user has sufficient permission
        required_level = agency_role_hierarchy.get(required_role, 0)
        if effective_permission_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role.value} role or higher",
            )

        return current_user

    return role_checker


# Pre-defined role dependencies
require_viewer = require_role(UserRole.VIEWER)
require_editor = require_role(UserRole.EDITOR)
require_agency_admin = require_role(UserRole.AGENCY_ADMIN)


async def verify_agency_access(
    agency_id: int,
    db: AsyncSession,
    current_user: User,
    required_role: UserRole = UserRole.VIEWER,
) -> bool:
    """
    Verify that a user has access to an agency.

    Access is granted if:
    1. User is a direct member of the agency via user_agencies
    2. User is a member of a team that has the agency in a workspace
       (team role maps to agency permission level)

    Note: Superusers must also be explicitly assigned to agencies.

    Args:
        agency_id: Agency ID to check access for
        db: Database session
        current_user: Current authenticated user
        required_role: Minimum required role (default: VIEWER for read-only access)

    Returns:
        True if user has access

    Raises:
        HTTPException: If user doesn't have access
    """
    from app.models.user import user_agencies
    from app.models.team import TeamMember, Workspace, workspace_agencies, workspace_members, TEAM_ROLE_HIERARCHY, TeamRole
    from sqlalchemy import or_, exists

    # Agency role hierarchy
    agency_role_hierarchy = {
        UserRole.SUPER_ADMIN: 4,
        UserRole.AGENCY_ADMIN: 3,
        UserRole.EDITOR: 2,
        UserRole.VIEWER: 1,
    }

    # Check direct membership in user_agencies
    result = await db.execute(
        select(user_agencies.c.role).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == agency_id,
        )
    )
    user_role = result.scalar_one_or_none()
    effective_permission_level = 0

    if user_role is not None:
        # Direct membership - use the role directly
        effective_permission_level = agency_role_hierarchy.get(UserRole(user_role), 0)
    else:
        # Check team-based access with workspace membership
        # Owners have access to all workspaces, Editors/Viewers need explicit workspace access
        team_access = await db.execute(
            select(TeamMember.role)
            .select_from(TeamMember)
            .join(Workspace, TeamMember.team_id == Workspace.team_id)
            .join(workspace_agencies, Workspace.id == workspace_agencies.c.workspace_id)
            .where(
                TeamMember.user_id == current_user.id,
                workspace_agencies.c.agency_id == agency_id,
                # Owners have access to all workspaces, others need explicit membership
                or_(
                    TeamMember.role == TeamRole.OWNER,
                    exists(
                        select(workspace_members.c.workspace_id)
                        .where(
                            workspace_members.c.workspace_id == Workspace.id,
                            workspace_members.c.user_id == current_user.id
                        )
                    )
                )
            )
        )
        team_roles = team_access.scalars().all()

        if not team_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this agency",
            )

        # Get the highest permission level from team roles
        for team_role in team_roles:
            team_permission = TEAM_ROLE_HIERARCHY.get(TeamRole(team_role), 1)
            if team_permission > effective_permission_level:
                effective_permission_level = team_permission

    # Check if user has sufficient permission
    required_level = agency_role_hierarchy.get(required_role, 0)
    if effective_permission_level < required_level:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires {required_role.value} role or higher for this agency",
        )

    return True


async def verify_feed_access(
    feed_id: int,
    db: AsyncSession,
    current_user: User,
    required_role: UserRole = UserRole.VIEWER,
) -> int:
    """
    Verify that a user has access to a feed.

    Access is granted (in order of priority):
    1. User has direct feed access via feed_users table
    2. User's team has feed access via feed_teams table
    3. User has access to the feed's agency (via user_agencies or team)

    Note: Superusers must also be explicitly assigned to feeds or agencies.

    Args:
        feed_id: Feed ID to check access for
        db: Database session
        current_user: Current authenticated user
        required_role: Minimum required role

    Returns:
        The agency_id of the feed

    Raises:
        HTTPException: If feed not found or user doesn't have access
    """
    from app.models.gtfs import GTFSFeed
    from app.models.team import (
        feed_users, feed_teams, TeamMember,
        FeedRole, FEED_ROLE_HIERARCHY
    )

    # Get feed and its agency_id
    result = await db.execute(
        select(GTFSFeed.agency_id).where(GTFSFeed.id == feed_id)
    )
    agency_id = result.scalar_one_or_none()

    if agency_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Feed role to agency role mapping (permission levels)
    feed_role_to_agency_level = {
        FeedRole.OWNER: 3,       # Equivalent to AGENCY_ADMIN
        FeedRole.ADMIN: 3,       # Equivalent to AGENCY_ADMIN
        FeedRole.CONTRIBUTOR: 2,  # Equivalent to EDITOR
        FeedRole.READ_ONLY: 1,   # Equivalent to VIEWER
    }

    agency_role_hierarchy = {
        UserRole.SUPER_ADMIN: 4,
        UserRole.AGENCY_ADMIN: 3,
        UserRole.EDITOR: 2,
        UserRole.VIEWER: 1,
    }

    effective_permission_level = 0

    # 1. Check direct feed access via feed_users
    result = await db.execute(
        select(feed_users.c.role).where(
            feed_users.c.feed_id == feed_id,
            feed_users.c.user_id == current_user.id,
        )
    )
    feed_user_role = result.scalar_one_or_none()

    if feed_user_role is not None:
        effective_permission_level = max(
            effective_permission_level,
            feed_role_to_agency_level.get(FeedRole(feed_user_role), 1)
        )

    # 2. Check team-based feed access via feed_teams
    result = await db.execute(
        select(feed_teams.c.role)
        .select_from(feed_teams)
        .join(TeamMember, feed_teams.c.team_id == TeamMember.team_id)
        .where(
            feed_teams.c.feed_id == feed_id,
            TeamMember.user_id == current_user.id,
        )
    )
    feed_team_roles = result.scalars().all()

    for role in feed_team_roles:
        effective_permission_level = max(
            effective_permission_level,
            feed_role_to_agency_level.get(FeedRole(role), 1)
        )

    # 3. If no direct feed access, check agency-level access
    if effective_permission_level == 0:
        # This will raise HTTPException if no access
        await verify_agency_access(agency_id, db, current_user, required_role)
        return agency_id

    # Check if user has sufficient permission from feed-level access
    required_level = agency_role_hierarchy.get(required_role, 0)
    if effective_permission_level < required_level:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires {required_role.value} role or higher for this feed",
        )

    return agency_id
