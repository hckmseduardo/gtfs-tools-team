"""Team management endpoints"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, BackgroundTasks
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.deps import get_db
from app.models.user import User
from app.models.team import Team, TeamMember, TeamInvitation, TeamRole, InvitationStatus
from app.models.audit import AuditAction
from app.schemas.team import (
    TeamCreate,
    TeamUpdate,
    TeamResponse,
    TeamWithDetails,
    TeamList,
    TeamMemberCreate,
    TeamMemberUpdate,
    TeamMemberResponse,
    TeamMemberList,
    TeamMemberInfo,
    WorkspaceSummary,
    TeamInvitationCreate,
    TeamInvitationResponse,
    TeamInvitationList,
    TeamInvitationAccept,
    TeamInvitationPublic,
)
from app.utils.audit import create_audit_log, serialize_model
from app.services.email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Invitation validity period (7 days)
INVITATION_VALIDITY_DAYS = 7


def generate_invitation_token() -> str:
    """Generate a secure random token for invitations"""
    return secrets.token_urlsafe(32)


async def send_invitation_email_task(
    email: str,
    team_name: str,
    inviter_name: str,
    role: str,
    token: str,
    expires_at: datetime,
) -> None:
    """Background task to send invitation email"""
    try:
        expires_str = expires_at.strftime("%B %d, %Y at %H:%M UTC")
        success = await email_service.send_team_invitation(
            to_email=email,
            team_name=team_name,
            inviter_name=inviter_name or "A team member",
            role=role,
            invitation_token=token,
            expires_at=expires_str,
        )
        if success:
            logger.info(f"Invitation email sent to {email}")
        else:
            logger.warning(f"Failed to send invitation email to {email}")
    except Exception as e:
        logger.error(f"Error sending invitation email to {email}: {e}")


async def check_team_permission(
    db: AsyncSession,
    user: User,
    team_id: int,
    required_roles: list[TeamRole],
) -> TeamMember | None:
    """Check if user has required role in team"""
    if user.is_superuser:
        return True

    query = select(TeamMember).where(
        TeamMember.team_id == team_id,
        TeamMember.user_id == user.id,
        TeamMember.role.in_(required_roles),
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


# ==================== Team Endpoints ====================


@router.get("/", response_model=TeamList)
async def list_teams(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> TeamList:
    """
    List teams the current user belongs to.

    - Super admins see all teams
    - Other users see only teams they are members of
    """
    query = select(Team)

    # Filter by membership for non-superusers
    if not current_user.is_superuser:
        query = query.join(TeamMember).where(TeamMember.user_id == current_user.id)

    # Apply search filter
    if search:
        query = query.where(
            or_(
                Team.name.ilike(f"%{search}%"),
                Team.slug.ilike(f"%{search}%"),
            )
        )

    # Apply active filter
    if is_active is not None:
        query = query.where(Team.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Team.created_at.desc())
    result = await db.execute(query)
    teams = result.scalars().all()

    return TeamList(
        items=[TeamResponse.model_validate(team) for team in teams],
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.post("/", response_model=TeamWithDetails, status_code=status.HTTP_201_CREATED)
async def create_team(
    team_in: TeamCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> TeamWithDetails:
    """
    Create a new team.

    The creating user automatically becomes the team owner.
    """
    # Check if slug already exists
    result = await db.execute(select(Team).where(Team.slug == team_in.slug))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Team with slug '{team_in.slug}' already exists",
        )

    # Create team
    team = Team(
        **team_in.model_dump(),
        created_by_id=current_user.id,
    )
    db.add(team)
    await db.flush()

    # Add creator as owner
    owner_member = TeamMember(
        team_id=team.id,
        user_id=current_user.id,
        role=TeamRole.OWNER,
    )
    db.add(owner_member)

    await db.commit()
    await db.refresh(team)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="team",
        entity_id=str(team.id),
        description=f"Created team '{team.name}' ({team.slug})",
        new_values=serialize_model(team),
        request=request,
    )

    # Build response with details
    return TeamWithDetails(
        **TeamResponse.model_validate(team).model_dump(),
        members=[TeamMemberInfo(
            id=owner_member.id,
            user_id=current_user.id,
            email=current_user.email,
            full_name=current_user.full_name,
            role=TeamRole.OWNER,
        )],
        workspaces=[],
        member_count=1,
        workspace_count=0,
    )


@router.get("/{team_id}", response_model=TeamWithDetails)
async def get_team(
    team_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> TeamWithDetails:
    """
    Get team details by ID.

    - Super admins can view any team
    - Other users can only view teams they belong to
    """
    # Build query with eager loading
    query = (
        select(Team)
        .where(Team.id == team_id)
        .options(
            selectinload(Team.members).selectinload(TeamMember.user),
            selectinload(Team.workspaces),
        )
    )

    result = await db.execute(query)
    team = result.scalar_one_or_none()

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    # Check access for non-superusers
    if not current_user.is_superuser:
        is_member = any(m.user_id == current_user.id for m in team.members)
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this team",
            )

    # Build member info
    members = [
        TeamMemberInfo(
            id=m.id,
            user_id=m.user_id,
            email=m.user.email,
            full_name=m.user.full_name,
            role=m.role,
        )
        for m in team.members
    ]

    # Build workspace summaries
    workspaces = [
        WorkspaceSummary(
            id=w.id,
            name=w.name,
            slug=w.slug,
            is_active=w.is_active,
            agency_count=len(w.agencies),
        )
        for w in team.workspaces
    ]

    return TeamWithDetails(
        **TeamResponse.model_validate(team).model_dump(),
        members=members,
        workspaces=workspaces,
        member_count=len(members),
        workspace_count=len(workspaces),
    )


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: int,
    team_in: TeamUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Team:
    """
    Update team details.

    - Super admins can update any team
    - Only team owners can update their teams
    """
    # Get team
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    # Check permissions - only owners can update teams
    has_permission = await check_team_permission(
        db, current_user, team_id, [TeamRole.OWNER]
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can update the team",
        )

    # Check slug uniqueness if updating slug
    update_data = team_in.model_dump(exclude_unset=True)
    if "slug" in update_data and update_data["slug"] != team.slug:
        result = await db.execute(
            select(Team).where(
                Team.slug == update_data["slug"],
                Team.id != team_id,
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Team with slug '{update_data['slug']}' already exists",
            )

    # Capture old values for audit
    old_values = serialize_model(team)

    # Update team
    for field, value in update_data.items():
        setattr(team, field, value)

    await db.commit()
    await db.refresh(team)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="team",
        entity_id=str(team.id),
        description=f"Updated team '{team.name}' ({team.slug})",
        old_values=old_values,
        new_values=serialize_model(team),
        request=request,
    )

    return team


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Delete a team.

    - Super admins can delete any team
    - Only team owners can delete their teams

    This will cascade delete all workspaces, members, and invitations.
    """
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    # Check permissions (only owner can delete)
    has_permission = await check_team_permission(
        db, current_user, team_id, [TeamRole.OWNER]
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can delete the team",
        )

    # Capture info for audit
    team_name = team.name
    old_values = serialize_model(team)

    # Delete team (cascade will handle members, workspaces, invitations)
    await db.delete(team)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="team",
        entity_id=str(team_id),
        description=f"Deleted team '{team_name}'",
        old_values=old_values,
        request=request,
    )


# ==================== Team Member Endpoints ====================


@router.get("/{team_id}/members", response_model=TeamMemberList)
async def list_team_members(
    team_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> TeamMemberList:
    """
    List all members of a team.
    """
    # Check team exists and user has access
    query = (
        select(Team)
        .where(Team.id == team_id)
        .options(selectinload(Team.members).selectinload(TeamMember.user))
    )
    result = await db.execute(query)
    team = result.scalar_one_or_none()

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    # Check access
    if not current_user.is_superuser:
        is_member = any(m.user_id == current_user.id for m in team.members)
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this team",
            )

    # Build response
    members = [
        TeamMemberResponse(
            id=m.id,
            team_id=m.team_id,
            user_id=m.user_id,
            role=m.role,
            email=m.user.email,
            full_name=m.user.full_name,
            created_at=m.created_at,
        )
        for m in team.members
    ]

    return TeamMemberList(
        items=members,
        total=len(members),
    )


@router.post("/{team_id}/members", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: int,
    member_in: TeamMemberCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> TeamMemberResponse:
    """
    Add a user to a team directly (without invitation).

    - Super admins can add members to any team
    - Only team owners can add members to their teams
    """
    # Check permissions - only owners can add members
    has_permission = await check_team_permission(
        db, current_user, team_id, [TeamRole.OWNER]
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can add members",
        )

    # Check team exists
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    # Check user exists
    result = await db.execute(select(User).where(User.id == member_in.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check not already a member
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == member_in.user_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this team",
        )

    # Validate role assignment (can't add another owner unless superuser)
    if member_in.role == TeamRole.OWNER and not current_user.is_superuser:
        # Check if current user is owner
        result = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == current_user.id,
                TeamMember.role == TeamRole.OWNER,
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only team owners can add another owner",
            )

    # Add member
    member = TeamMember(
        team_id=team_id,
        user_id=member_in.user_id,
        role=member_in.role,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="team_member",
        entity_id=f"{team_id}:{member_in.user_id}",
        description=f"Added user {user.email} to team '{team.name}' as {member_in.role.value}",
        new_values={"team_id": team_id, "user_id": member_in.user_id, "role": member_in.role.value},
        request=request,
    )

    return TeamMemberResponse(
        id=member.id,
        team_id=member.team_id,
        user_id=member.user_id,
        role=member.role,
        email=user.email,
        full_name=user.full_name,
        created_at=member.created_at,
    )


@router.patch("/{team_id}/members/{user_id}", response_model=TeamMemberResponse)
async def update_team_member(
    team_id: int,
    user_id: int,
    member_in: TeamMemberUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> TeamMemberResponse:
    """
    Update a member's role in the team.

    - Super admins can update any member
    - Only team owners can change roles
    """
    # Get member
    query = (
        select(TeamMember)
        .where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        .options(selectinload(TeamMember.user))
    )
    result = await db.execute(query)
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    # Check permissions - only owners can change roles
    if not current_user.is_superuser:
        # Get current user's role
        result = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == current_user.id,
            )
        )
        current_membership = result.scalar_one_or_none()

        if not current_membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this team",
            )

        # Only owners can change roles
        if current_membership.role != TeamRole.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only team owners can change member roles",
            )

    # Prevent removing the last owner
    if member.role == TeamRole.OWNER and member_in.role != TeamRole.OWNER:
        result = await db.execute(
            select(func.count()).where(
                TeamMember.team_id == team_id,
                TeamMember.role == TeamRole.OWNER,
            )
        )
        owner_count = result.scalar()
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last owner. Transfer ownership first.",
            )

    # Capture old values
    old_role = member.role

    # Update role
    member.role = member_in.role
    await db.commit()
    await db.refresh(member)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="team_member",
        entity_id=f"{team_id}:{user_id}",
        description=f"Updated user {member.user.email} role in team from {old_role.value} to {member_in.role.value}",
        old_values={"role": old_role.value},
        new_values={"role": member_in.role.value},
        request=request,
    )

    return TeamMemberResponse(
        id=member.id,
        team_id=member.team_id,
        user_id=member.user_id,
        role=member.role,
        email=member.user.email,
        full_name=member.user.full_name,
        created_at=member.created_at,
    )


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    team_id: int,
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Remove a member from the team.

    - Super admins can remove any member
    - Team owners can remove anyone except themselves if they're the last owner
    - Members can remove themselves (leave team)
    """
    # Get member
    query = (
        select(TeamMember)
        .where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        .options(selectinload(TeamMember.user))
    )
    result = await db.execute(query)
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    # Check permissions
    is_self_removal = user_id == current_user.id

    if not current_user.is_superuser and not is_self_removal:
        has_permission = await check_team_permission(
            db, current_user, team_id, [TeamRole.OWNER]
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only team owners can remove members",
            )

    # Prevent removing the last owner
    if member.role == TeamRole.OWNER:
        result = await db.execute(
            select(func.count()).where(
                TeamMember.team_id == team_id,
                TeamMember.role == TeamRole.OWNER,
            )
        )
        owner_count = result.scalar()
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner. Transfer ownership or delete the team.",
            )

    # Capture info for audit
    member_email = member.user.email
    member_role = member.role

    # Remove member
    await db.delete(member)
    await db.commit()

    # Create audit log
    action_desc = "left team" if is_self_removal else f"removed user {member_email} from team"
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="team_member",
        entity_id=f"{team_id}:{user_id}",
        description=f"User {action_desc}",
        old_values={"user_id": user_id, "email": member_email, "role": member_role.value},
        request=request,
    )


# ==================== Team Invitation Endpoints ====================


@router.get("/{team_id}/invitations", response_model=TeamInvitationList)
async def list_team_invitations(
    team_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    status_filter: Optional[InvitationStatus] = None,
) -> TeamInvitationList:
    """
    List all invitations for a team.
    """
    # Check permissions - only owners can view invitations
    has_permission = await check_team_permission(
        db, current_user, team_id, [TeamRole.OWNER]
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can view invitations",
        )

    # Build query
    query = (
        select(TeamInvitation)
        .where(TeamInvitation.team_id == team_id)
        .options(selectinload(TeamInvitation.invited_by))
    )

    if status_filter:
        query = query.where(TeamInvitation.status == status_filter)

    result = await db.execute(query)
    invitations = result.scalars().all()

    # Build response
    items = [
        TeamInvitationResponse(
            id=inv.id,
            team_id=inv.team_id,
            email=inv.email,
            role=inv.role,
            status=inv.status,
            invited_by_id=inv.invited_by_id,
            invited_by_name=inv.invited_by.full_name if inv.invited_by else None,
            expires_at=inv.expires_at,
            created_at=inv.created_at,
        )
        for inv in invitations
    ]

    return TeamInvitationList(
        items=items,
        total=len(items),
    )


@router.post("/{team_id}/invitations", response_model=TeamInvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_team_invitation(
    team_id: int,
    invitation_in: TeamInvitationCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> TeamInvitationResponse:
    """
    Create an invitation to join a team.

    - Only team owners can create invitations
    - Owners can invite with any role (OWNER, EDITOR, VIEWER)
    - Sends an invitation email if email service is configured
    """
    # Check team exists
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    # Check permissions - only owners can invite
    has_permission = await check_team_permission(
        db, current_user, team_id, [TeamRole.OWNER]
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can invite members",
        )

    # Check if user already member
    result = await db.execute(
        select(User).where(User.email == invitation_in.email)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        result = await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
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
            TeamInvitation.team_id == team_id,
            TeamInvitation.email == invitation_in.email,
            TeamInvitation.status == InvitationStatus.PENDING,
        )
    )
    existing_invitation = result.scalar_one_or_none()

    if existing_invitation:
        # Update existing invitation instead of creating new
        existing_invitation.role = invitation_in.role
        existing_invitation.invited_by_id = current_user.id
        existing_invitation.token = generate_invitation_token()
        existing_invitation.expires_at = datetime.now(timezone.utc) + timedelta(days=INVITATION_VALIDITY_DAYS)

        await db.commit()
        await db.refresh(existing_invitation)

        # Send invitation email (re-send)
        if email_service.is_enabled():
            background_tasks.add_task(
                send_invitation_email_task,
                email=existing_invitation.email,
                team_name=team.name,
                inviter_name=current_user.full_name,
                role=existing_invitation.role.value,
                token=existing_invitation.token,
                expires_at=existing_invitation.expires_at,
            )

        return TeamInvitationResponse(
            id=existing_invitation.id,
            team_id=existing_invitation.team_id,
            email=existing_invitation.email,
            role=existing_invitation.role,
            status=existing_invitation.status,
            invited_by_id=existing_invitation.invited_by_id,
            invited_by_name=current_user.full_name,
            expires_at=existing_invitation.expires_at,
            created_at=existing_invitation.created_at,
        )

    # Create new invitation
    invitation = TeamInvitation(
        team_id=team_id,
        email=invitation_in.email,
        role=invitation_in.role,
        status=InvitationStatus.PENDING,
        token=generate_invitation_token(),
        invited_by_id=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITATION_VALIDITY_DAYS),
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="team_invitation",
        entity_id=str(invitation.id),
        description=f"Invited {invitation_in.email} to team '{team.name}' as {invitation_in.role.value}",
        new_values={"email": invitation_in.email, "role": invitation_in.role.value, "team_id": team_id},
        request=request,
    )

    # Send invitation email
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

    return TeamInvitationResponse(
        id=invitation.id,
        team_id=invitation.team_id,
        email=invitation.email,
        role=invitation.role,
        status=invitation.status,
        invited_by_id=invitation.invited_by_id,
        invited_by_name=current_user.full_name,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


@router.delete("/{team_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_team_invitation(
    team_id: int,
    invitation_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Revoke/delete a team invitation.

    - Only team owners can revoke invitations
    """
    # Check permissions - only owners can revoke invitations
    has_permission = await check_team_permission(
        db, current_user, team_id, [TeamRole.OWNER]
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can revoke invitations",
        )

    # Get invitation
    result = await db.execute(
        select(TeamInvitation).where(
            TeamInvitation.id == invitation_id,
            TeamInvitation.team_id == team_id,
        )
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    # Capture for audit
    email = invitation.email

    # Delete invitation
    await db.delete(invitation)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="team_invitation",
        entity_id=str(invitation_id),
        description=f"Revoked invitation for {email}",
        old_values={"email": email, "team_id": team_id},
        request=request,
    )


# ==================== Public Invitation Endpoints ====================


@router.get("/invitations/by-token/{token}", response_model=TeamInvitationPublic)
async def get_invitation_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> TeamInvitationPublic:
    """
    Get invitation details by token (public endpoint for accepting invitations).
    """
    query = (
        select(TeamInvitation)
        .where(TeamInvitation.token == token)
        .options(
            selectinload(TeamInvitation.team),
            selectinload(TeamInvitation.invited_by),
        )
    )
    result = await db.execute(query)
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or invalid token",
        )

    # Check if expired
    is_expired = datetime.now(timezone.utc) > invitation.expires_at

    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invitation has already been {invitation.status.value}",
        )

    return TeamInvitationPublic(
        team_name=invitation.team.name,
        team_slug=invitation.team.slug,
        role=invitation.role,
        invited_by_name=invitation.invited_by.full_name if invitation.invited_by else None,
        expires_at=invitation.expires_at,
        is_expired=is_expired,
    )


@router.post("/invitations/accept", response_model=TeamMemberResponse)
async def accept_team_invitation(
    accept_in: TeamInvitationAccept,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> TeamMemberResponse:
    """
    Accept a team invitation.

    The current user must be logged in and their email must match the invitation.
    """
    # Get invitation
    query = (
        select(TeamInvitation)
        .where(TeamInvitation.token == accept_in.token)
        .options(selectinload(TeamInvitation.team))
    )
    result = await db.execute(query)
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or invalid token",
        )

    # Check status
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invitation has already been {invitation.status.value}",
        )

    # Check expiration
    if datetime.now(timezone.utc) > invitation.expires_at:
        invitation.status = InvitationStatus.EXPIRED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )

    # Check email matches
    if current_user.email.lower() != invitation.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation was sent to a different email address",
        )

    # Check not already a member
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == invitation.team_id,
            TeamMember.user_id == current_user.id,
        )
    )
    if result.scalar_one_or_none():
        invitation.status = InvitationStatus.ACCEPTED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already a member of this team",
        )

    # Create membership
    member = TeamMember(
        team_id=invitation.team_id,
        user_id=current_user.id,
        role=invitation.role,
    )
    db.add(member)

    # Update invitation
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_by_id = current_user.id

    await db.commit()
    await db.refresh(member)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="team_member",
        entity_id=f"{invitation.team_id}:{current_user.id}",
        description=f"Accepted invitation to join team '{invitation.team.name}' as {invitation.role.value}",
        new_values={"team_id": invitation.team_id, "role": invitation.role.value},
        request=request,
    )

    return TeamMemberResponse(
        id=member.id,
        team_id=member.team_id,
        user_id=member.user_id,
        role=member.role,
        email=current_user.email,
        full_name=current_user.full_name,
        created_at=member.created_at,
    )
