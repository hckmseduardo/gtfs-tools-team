"""
Team context endpoints for multi-tenant architecture.

These endpoints operate on the current team (determined by subdomain).
Unlike /teams/{team_id}/* endpoints, these don't require team_id in the path.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.deps import get_db
from app.models.user import User
from app.models.team import Team, TeamMember, TeamInvitation, TeamRole, InvitationStatus
from app.models.audit import AuditAction
from app.schemas.team import (
    TeamMemberUpdate,
    TeamMemberResponse,
    TeamInvitationCreate,
    TeamInvitationResponse,
)
from app.utils.audit import create_audit_log
from app.services.email_service import email_service

# Import from teams.py
from app.api.v1.endpoints.teams import (
    generate_invitation_token,
    send_invitation_email_task,
    INVITATION_VALIDITY_DAYS,
)
from datetime import timedelta

logger = logging.getLogger(__name__)

router = APIRouter()

# Portal API URL for token validation and membership registration
DOMAIN = os.environ.get("DOMAIN", "app.gtfs-tools.com")
PORTAL_API_URL = os.environ.get("PORTAL_API_URL", f"https://{DOMAIN}/api")
TEAM_SLUG = os.environ.get("TEAM_SLUG", "")


async def get_current_team(db: AsyncSession) -> Team:
    """
    Get the current team from environment (set by team template).
    In multi-tenant setup, TEAM_SLUG env var identifies the team.
    """
    team_slug = os.environ.get("TEAM_SLUG")
    if not team_slug:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Team context not configured (TEAM_SLUG not set)",
        )

    result = await db.execute(
        select(Team).where(Team.slug == team_slug)
    )
    team = result.scalar_one_or_none()

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{team_slug}' not found",
        )

    return team


async def require_team_owner(
    db: AsyncSession,
    user: User,
    team: Team,
) -> TeamMember:
    """Require user to be a team owner."""
    if user.is_superuser:
        return None  # Superuser has implicit access

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id,
            TeamMember.user_id == user.id,
            TeamMember.role == TeamRole.OWNER,
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can perform this action",
        )

    return member


# ==================== SSO Token Exchange Endpoint ====================


@router.post("/auth/exchange")
async def exchange_portal_token(token: str = Query(..., description="Portal SSO token")):
    """
    Exchange portal SSO token for user info by validating with portal API.
    This endpoint is public (no auth required) - used during invitation acceptance flow.

    The portal token is a cross-domain SSO token that must be exchanged via
    the portal's /auth/exchange endpoint (not /users/me).
    """
    try:
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            # Exchange the cross-domain SSO token via portal's /auth/exchange endpoint
            response = await client.post(
                f"{PORTAL_API_URL}/auth/exchange",
                params={"token": token},
            )

            if response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                )

            if response.status_code != 200:
                logger.error(f"Portal token validation failed: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to validate token with portal",
                )

            data = response.json()
            # Portal /auth/exchange returns { access_token, token_type, user: {...} }
            user_data = data.get("user", data)  # Fallback to data if no nested user
            return {
                "user": {
                    "id": user_data["id"],
                    "email": user_data["email"],
                    "display_name": user_data.get("display_name") or user_data.get("full_name"),
                    "avatar_url": user_data.get("avatar_url"),
                }
            }
    except httpx.RequestError as e:
        logger.error(f"Could not connect to portal: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not connect to portal: {str(e)}",
        )


@router.post("/auth/sso")
async def sso_login(
    token: str = Query(..., description="Portal SSO token"),
    db: AsyncSession = Depends(get_db),
):
    """
    SSO login endpoint - exchanges portal cross-domain token for team JWT.
    This is called by the frontend when user navigates from portal to team subdomain.

    Flow:
    1. Receive cross-domain SSO token from portal
    2. Exchange token with portal's /auth/exchange endpoint to get user info
    3. Create or sync user in team's database
    4. Return team-valid JWT tokens
    """
    from app.core.security import create_access_token, create_refresh_token

    try:
        # Step 1: Exchange cross-domain token with portal
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            response = await client.post(
                f"{PORTAL_API_URL}/auth/exchange",
                params={"token": token},
            )

            if response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired SSO token",
                )

            if response.status_code != 200:
                logger.error(f"Portal SSO exchange failed: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to validate SSO token with portal",
                )

            data = response.json()
            user_data = data.get("user", data)

        # Step 2: Create or sync user in team database
        email = user_data["email"]
        display_name = user_data.get("display_name") or user_data.get("full_name") or email.split("@")[0]

        # Check if user exists
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            # Create new user
            user = User(
                email=email,
                full_name=display_name,
                is_active=True,
                is_superuser=False,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info(f"Created new user via SSO: {email}")
        else:
            # Update display name if changed
            if user.full_name != display_name:
                user.full_name = display_name
                await db.commit()
                await db.refresh(user)

        # Step 3: Ensure user is a team member
        team = await get_current_team(db)
        member_result = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id,
                TeamMember.user_id == user.id
            )
        )
        member = member_result.scalar_one_or_none()

        if not member:
            # User is not a member of this team - check if they should be auto-added
            # For now, we'll allow SSO users who were authenticated by portal
            # This assumes portal validated the user's access to this team subdomain
            logger.warning(f"User {email} authenticated via SSO but not a team member - creating viewer membership")
            member = TeamMember(
                team_id=team.id,
                user_id=user.id,
                role=TeamRole.VIEWER,  # Default to viewer for SSO users
            )
            db.add(member)
            await db.commit()

        # Step 4: Generate team JWT tokens
        access_token = create_access_token(subject=user.id)
        refresh_token = create_refresh_token(subject=user.id)

        logger.info(f"SSO login successful for user {email} in team {team.slug}")

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": member.role.value if member else "viewer",
            }
        }

    except httpx.RequestError as e:
        logger.error(f"Could not connect to portal for SSO: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not connect to portal: {str(e)}",
        )


# ==================== Team Settings Endpoints ====================


@router.get("/settings")
async def get_team_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get current team settings."""
    team = await get_current_team(db)

    return {
        "id": team.id,
        "name": team.name,
        "slug": team.slug,
        "description": team.description,
        "badge": getattr(team, 'badge', None),
        "is_active": team.is_active,
        "created_at": team.created_at,
    }


@router.patch("/settings")
async def update_team_settings(
    data: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Update team settings (name, description, badge)."""
    team = await get_current_team(db)
    await require_team_owner(db, current_user, team)

    # Only allow certain fields to be updated
    allowed_fields = {"name", "description", "badge"}
    update_data = {k: v for k, v in data.items() if k in allowed_fields}

    # Apply updates
    for field, value in update_data.items():
        setattr(team, field, value)

    await db.commit()
    await db.refresh(team)

    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="team",
        entity_id=str(team.id),
        description=f"Updated team settings",
        new_values=update_data,
        request=request,
    )

    # Sync settings to portal so they're reflected in the dashboard
    portal_sync_fields = {"name", "description", "badge"}
    portal_update = {k: v for k, v in update_data.items() if k in portal_sync_fields}
    if portal_update and TEAM_SLUG:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                await client.post(
                    f"{PORTAL_API_URL}/teams/{TEAM_SLUG}/sync-settings",
                    json=portal_update,
                )
        except Exception as e:
            logger.warning(f"Failed to sync settings to portal: {e}")

    return {
        "id": team.id,
        "name": team.name,
        "slug": team.slug,
        "description": team.description,
        "badge": getattr(team, 'badge', None),
        "is_active": team.is_active,
    }


# ==================== Team Members Endpoints ====================


@router.get("/members")
async def list_team_members(
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """List members of the current team."""
    team = await get_current_team(db)

    query = (
        select(TeamMember)
        .where(TeamMember.team_id == team.id)
        .options(selectinload(TeamMember.user))
    )

    result = await db.execute(query)
    members = result.scalars().all()

    # Count by role
    owners = sum(1 for m in members if m.role == TeamRole.OWNER)
    admins = sum(1 for m in members if m.role == TeamRole.ADMIN)
    editors = sum(1 for m in members if m.role == TeamRole.EDITOR)
    viewers = sum(1 for m in members if m.role == TeamRole.VIEWER)

    return {
        "members": [
            {
                "id": str(m.id),
                "email": m.user.email,
                "name": m.user.full_name,
                "role": m.role.value,
                "is_active": m.user.is_active,
                "created_at": m.created_at.isoformat(),
            }
            for m in members
            if include_inactive or m.user.is_active
        ],
        "count": len(members),
        "by_role": {
            "owners": owners,
            "admins": admins,
            "editors": editors,
            "viewers": viewers,
        }
    }


@router.patch("/members/{member_id}")
async def update_team_member(
    member_id: str,
    data: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Update a team member's role or status."""
    team = await get_current_team(db)
    await require_team_owner(db, current_user, team)

    # Get member
    result = await db.execute(
        select(TeamMember)
        .where(
            TeamMember.id == int(member_id),
            TeamMember.team_id == team.id,
        )
        .options(selectinload(TeamMember.user))
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    # Update role if provided
    if "role" in data:
        new_role = TeamRole(data["role"])

        # Prevent removing last owner
        if member.role == TeamRole.OWNER and new_role != TeamRole.OWNER:
            owner_count = await db.scalar(
                select(func.count()).where(
                    TeamMember.team_id == team.id,
                    TeamMember.role == TeamRole.OWNER,
                )
            )
            if owner_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot demote the last owner",
                )

        member.role = new_role

    # Update user active status if provided
    if "is_active" in data:
        member.user.is_active = data["is_active"]

    await db.commit()
    await db.refresh(member)

    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="team_member",
        entity_id=str(member.id),
        description=f"Updated team member {member.user.email}",
        new_values=data,
        request=request,
    )

    return {
        "id": str(member.id),
        "email": member.user.email,
        "name": member.user.full_name,
        "role": member.role.value,
        "is_active": member.user.is_active,
    }


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    member_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Remove a member from the team."""
    team = await get_current_team(db)
    await require_team_owner(db, current_user, team)

    result = await db.execute(
        select(TeamMember)
        .where(
            TeamMember.id == int(member_id),
            TeamMember.team_id == team.id,
        )
        .options(selectinload(TeamMember.user))
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    # Prevent removing last owner
    if member.role == TeamRole.OWNER:
        owner_count = await db.scalar(
            select(func.count()).where(
                TeamMember.team_id == team.id,
                TeamMember.role == TeamRole.OWNER,
            )
        )
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner",
            )

    email = member.user.email
    user_id = str(member.user_id)
    await db.delete(member)
    await db.commit()

    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="team_member",
        entity_id=str(member_id),
        description=f"Removed {email} from team",
        request=request,
    )

    # Sync removal to portal so user no longer sees this team in their dashboard
    if TEAM_SLUG:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                await client.post(
                    f"{PORTAL_API_URL}/teams/{TEAM_SLUG}/unregister-member",
                    json={"user_id": user_id},
                )
        except Exception as e:
            logger.warning(f"Failed to unregister member from portal: {e}")


# ==================== Team Invitations Endpoints ====================


@router.get("/invitations")
async def list_team_invitations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """List pending invitations for the current team."""
    team = await get_current_team(db)
    await require_team_owner(db, current_user, team)

    result = await db.execute(
        select(TeamInvitation)
        .where(TeamInvitation.team_id == team.id)
        .options(selectinload(TeamInvitation.invited_by))
    )
    invitations = result.scalars().all()

    return {
        "invitations": [
            {
                "id": str(inv.id),
                "email": inv.email,
                "role": inv.role.value,
                "status": inv.status.value,
                "created_at": inv.created_at.isoformat(),
                "expires_at": inv.expires_at.isoformat(),
            }
            for inv in invitations
        ]
    }


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
async def create_team_invitation(
    data: dict,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Create an invitation to join the current team."""
    team = await get_current_team(db)
    await require_team_owner(db, current_user, team)

    email = data.get("email")
    role_str = data.get("role", "editor")
    message = data.get("message", "")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required",
        )

    # Map role string to enum
    role_map = {
        "owner": TeamRole.OWNER,
        "editor": TeamRole.EDITOR,
        "viewer": TeamRole.VIEWER,
    }
    role = role_map.get(role_str.lower(), TeamRole.EDITOR)

    # Check if already a member
    result = await db.execute(
        select(User).where(User.email == email)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        result = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id,
                TeamMember.user_id == existing_user.id,
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this team",
            )

    # Check for existing pending invitation
    result = await db.execute(
        select(TeamInvitation).where(
            TeamInvitation.team_id == team.id,
            TeamInvitation.email == email,
            TeamInvitation.status == InvitationStatus.PENDING,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing
        existing.role = role
        existing.token = generate_invitation_token()
        existing.expires_at = datetime.now(timezone.utc) + timedelta(days=INVITATION_VALIDITY_DAYS)
        existing.invited_by_id = current_user.id
        await db.commit()
        invitation = existing
    else:
        # Create new
        invitation = TeamInvitation(
            team_id=team.id,
            email=email,
            role=role,
            status=InvitationStatus.PENDING,
            token=generate_invitation_token(),
            invited_by_id=current_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=INVITATION_VALIDITY_DAYS),
        )
        db.add(invitation)
        await db.commit()
        await db.refresh(invitation)

    # Send email
    if email_service.is_enabled():
        background_tasks.add_task(
            send_invitation_email_task,
            email=email,
            team_name=team.name,
            inviter_name=current_user.full_name,
            role=role.value,
            token=invitation.token,
            expires_at=invitation.expires_at,
        )

    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="team_invitation",
        entity_id=str(invitation.id),
        description=f"Invited {email} to team as {role.value}",
        request=request,
    )

    return {
        "id": str(invitation.id),
        "email": invitation.email,
        "role": invitation.role.value,
        "status": invitation.status.value,
        "created_at": invitation.created_at.isoformat(),
        "expires_at": invitation.expires_at.isoformat(),
    }


@router.post("/invitations/{invitation_id}/resend")
async def resend_team_invitation(
    invitation_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Resend an invitation email."""
    team = await get_current_team(db)
    await require_team_owner(db, current_user, team)

    result = await db.execute(
        select(TeamInvitation).where(
            TeamInvitation.id == int(invitation_id),
            TeamInvitation.team_id == team.id,
        )
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    # Regenerate token and extend expiration
    invitation.token = generate_invitation_token()
    invitation.expires_at = datetime.now(timezone.utc) + timedelta(days=INVITATION_VALIDITY_DAYS)
    await db.commit()

    # Send email
    if email_service.is_enabled():
        background_tasks.add_task(
            send_invitation_email_task,
            email=invitation.email,
            team_name=team.name,
            inviter_name=current_user.full_name,
            role=invitation.role.value,
            token=invitation.token,
            expires_at=invitation.expires_at,
        )

    return {"message": "Invitation resent"}


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_team_invitation(
    invitation_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Cancel/delete an invitation."""
    team = await get_current_team(db)
    await require_team_owner(db, current_user, team)

    result = await db.execute(
        select(TeamInvitation).where(
            TeamInvitation.id == int(invitation_id),
            TeamInvitation.team_id == team.id,
        )
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    email = invitation.email
    await db.delete(invitation)
    await db.commit()

    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="team_invitation",
        entity_id=str(invitation_id),
        description=f"Cancelled invitation for {email}",
        request=request,
    )


# ==================== Public Invitation Endpoints (for JoinTeam page) ====================


@router.get("/invitations/by-token")
async def get_invitation_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get invitation details by token (public endpoint for JoinTeam page).
    No authentication required - anyone with the token can view the invitation.
    """
    team = await get_current_team(db)

    result = await db.execute(
        select(TeamInvitation)
        .where(
            TeamInvitation.team_id == team.id,
            TeamInvitation.token == token,
        )
        .options(selectinload(TeamInvitation.invited_by))
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invitation token",
        )

    # Check expiry
    if datetime.now(timezone.utc) > invitation.expires_at:
        invitation.status = InvitationStatus.EXPIRED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has expired",
        )

    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation is no longer valid",
        )

    # Get inviter name if available
    invited_by_name = None
    if invitation.invited_by:
        invited_by_name = invitation.invited_by.full_name or invitation.invited_by.email

    return {
        "email": invitation.email,
        "role": invitation.role.value,
        "team_name": team.name,
        "team_slug": team.slug,
        "invited_by_name": invited_by_name,
        "expires_at": invitation.expires_at.isoformat(),
    }


@router.post("/join")
async def join_team(
    token: str = Query(..., description="Invitation token"),
    user_id: Optional[str] = Query(None, description="User ID from portal"),
    user_email: Optional[str] = Query(None, description="User email from portal"),
    user_name: Optional[str] = Query(None, description="User display name from portal"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Accept an invitation and join the team.

    This endpoint does NOT require authentication. It accepts user details
    from the portal SSO flow (user_id, user_email, user_name) passed via query params.

    Flow:
    1. User clicks invite link -> JoinTeam page
    2. User clicks "Login with Microsoft" -> redirects to portal auth
    3. Portal authenticates and redirects back with portal token
    4. Frontend exchanges portal token for user info via /auth/exchange
    5. Frontend calls /team/join with invitation token + user details
    """
    team = await get_current_team(db)

    # Get invitation by token
    result = await db.execute(
        select(TeamInvitation).where(
            TeamInvitation.team_id == team.id,
            TeamInvitation.token == token,
        )
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invitation token",
        )

    # Check expiry
    if datetime.now(timezone.utc) > invitation.expires_at:
        invitation.status = InvitationStatus.EXPIRED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has expired",
        )

    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation is no longer valid",
        )

    # Use provided user details or fall back to invitation email
    member_email = user_email or invitation.email
    member_name = user_name or member_email.split("@")[0]

    # Find or create user in local database
    result = await db.execute(
        select(User).where(User.email == member_email)
    )
    user = result.scalar_one_or_none()

    if not user:
        # Create a new user record for this team member
        user = User(
            email=member_email,
            full_name=member_name,
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        await db.flush()  # Get user.id without committing

    # Check if user is already a member
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id,
            TeamMember.user_id == user.id,
        )
    )
    existing_member = result.scalar_one_or_none()

    if existing_member:
        # Mark invitation as accepted anyway
        invitation.status = InvitationStatus.ACCEPTED
        await db.commit()
        return {
            "message": "You are already a member of this team",
            "member": {
                "id": str(existing_member.id),
                "email": user.email,
                "name": user.full_name,
                "role": existing_member.role.value,
            }
        }

    # Create team member
    new_member = TeamMember(
        team_id=team.id,
        user_id=user.id,
        role=invitation.role,
    )
    db.add(new_member)

    # Mark invitation as accepted
    invitation.status = InvitationStatus.ACCEPTED
    await db.commit()
    await db.refresh(new_member)

    # Register membership in portal so user can see the team in their dashboard
    if user_id and TEAM_SLUG:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                await client.post(
                    f"{PORTAL_API_URL}/teams/{TEAM_SLUG}/register-member",
                    json={"user_id": user_id, "role": invitation.role.value},
                )
        except Exception as e:
            # Log but don't fail - local membership is already created
            logger.warning(f"Failed to register membership in portal: {e}")

    # Create audit log (with user if available)
    await create_audit_log(
        db=db,
        user=user,
        action=AuditAction.CREATE,
        entity_type="team_member",
        entity_id=str(new_member.id),
        description=f"Joined team via invitation as {invitation.role.value}",
        request=request,
    )

    return {
        "message": "Welcome to the team!",
        "member": {
            "id": str(new_member.id),
            "email": user.email,
            "name": user.full_name,
            "role": new_member.role.value,
        }
    }
