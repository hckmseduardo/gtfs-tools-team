"""Workspace management endpoints"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.deps import get_db
from app.models.user import User
from app.models.agency import Agency
from app.models.team import Team, TeamMember, Workspace, TeamRole, workspace_agencies, workspace_members
from app.models.audit import AuditAction
from app.schemas.team import (
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceResponse,
    WorkspaceWithDetails,
    WorkspaceList,
    WorkspaceAgencyAdd,
    AgencySummary,
)
from app.utils.audit import create_audit_log, serialize_model

router = APIRouter()


async def check_team_permission(
    db: AsyncSession,
    user: User,
    team_id: int,
    required_roles: list[TeamRole],
) -> bool:
    """Check if user has required role in team"""
    if user.is_superuser:
        return True

    query = select(TeamMember).where(
        TeamMember.team_id == team_id,
        TeamMember.user_id == user.id,
        TeamMember.role.in_(required_roles),
    )
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None


async def check_workspace_access(
    db: AsyncSession,
    user: User,
    workspace_id: int,
) -> Workspace | None:
    """Check if user has access to workspace and return it"""
    query = (
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(selectinload(Workspace.team).selectinload(Team.members))
    )
    result = await db.execute(query)
    workspace = result.scalar_one_or_none()

    if not workspace:
        return None

    if user.is_superuser:
        return workspace

    # Check if user is a member of the team
    is_member = any(m.user_id == user.id for m in workspace.team.members)
    return workspace if is_member else None


# ==================== Workspace Endpoints ====================


@router.get("/", response_model=WorkspaceList)
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    team_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> WorkspaceList:
    """
    List workspaces the current user has access to.

    - Super admins see all workspaces
    - Other users see workspaces of teams they belong to
    """
    query = select(Workspace).options(selectinload(Workspace.team))

    # Filter by team membership for non-superusers
    if not current_user.is_superuser:
        query = query.join(Team).join(TeamMember).where(TeamMember.user_id == current_user.id)

    # Filter by specific team
    if team_id:
        query = query.where(Workspace.team_id == team_id)

    # Apply search filter
    if search:
        query = query.where(
            or_(
                Workspace.name.ilike(f"%{search}%"),
                Workspace.slug.ilike(f"%{search}%"),
            )
        )

    # Apply active filter
    if is_active is not None:
        query = query.where(Workspace.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Workspace.created_at.desc())
    result = await db.execute(query)
    workspaces = result.scalars().all()

    return WorkspaceList(
        items=[WorkspaceResponse.model_validate(ws) for ws in workspaces],
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.post("/", response_model=WorkspaceWithDetails, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    workspace_in: WorkspaceCreate,
    team_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> WorkspaceWithDetails:
    """
    Create a new workspace in a team.

    - Only team owners can create workspaces
    """
    # Check team exists
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    # Check permissions - only owners can create workspaces
    has_permission = await check_team_permission(
        db, current_user, team_id, [TeamRole.OWNER]
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can create workspaces",
        )

    # Check slug uniqueness within team
    result = await db.execute(
        select(Workspace).where(
            Workspace.team_id == team_id,
            Workspace.slug == workspace_in.slug,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Workspace with slug '{workspace_in.slug}' already exists in this team",
        )

    # Create workspace
    workspace = Workspace(
        **workspace_in.model_dump(),
        team_id=team_id,
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="workspace",
        entity_id=str(workspace.id),
        description=f"Created workspace '{workspace.name}' in team '{team.name}'",
        new_values=serialize_model(workspace),
        request=request,
    )

    return WorkspaceWithDetails(
        **WorkspaceResponse.model_validate(workspace).model_dump(),
        agencies=[],
        agency_count=0,
    )


@router.get("/{workspace_id}", response_model=WorkspaceWithDetails)
async def get_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> WorkspaceWithDetails:
    """
    Get workspace details by ID.
    """
    # Get workspace with agencies
    query = (
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(
            selectinload(Workspace.team).selectinload(Team.members),
            selectinload(Workspace.agencies),
        )
    )
    result = await db.execute(query)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # Check access
    if not current_user.is_superuser:
        is_member = any(m.user_id == current_user.id for m in workspace.team.members)
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this workspace",
            )

    # Build agency summaries
    agencies = [
        AgencySummary(
            id=a.id,
            name=a.name,
            slug=a.slug,
            is_active=a.is_active,
        )
        for a in workspace.agencies
    ]

    return WorkspaceWithDetails(
        **WorkspaceResponse.model_validate(workspace).model_dump(),
        agencies=agencies,
        agency_count=len(agencies),
    )


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: int,
    workspace_in: WorkspaceUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Workspace:
    """
    Update workspace details.

    - Only team owners can update workspaces
    """
    # Get workspace
    query = (
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(selectinload(Workspace.team))
    )
    result = await db.execute(query)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # Check permissions - only owners can update workspaces
    has_permission = await check_team_permission(
        db, current_user, workspace.team_id, [TeamRole.OWNER]
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can update workspaces",
        )

    # Check slug uniqueness if updating
    update_data = workspace_in.model_dump(exclude_unset=True)
    if "slug" in update_data and update_data["slug"] != workspace.slug:
        result = await db.execute(
            select(Workspace).where(
                Workspace.team_id == workspace.team_id,
                Workspace.slug == update_data["slug"],
                Workspace.id != workspace_id,
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Workspace with slug '{update_data['slug']}' already exists in this team",
            )

    # Capture old values
    old_values = serialize_model(workspace)

    # Update workspace
    for field, value in update_data.items():
        setattr(workspace, field, value)

    await db.commit()
    await db.refresh(workspace)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="workspace",
        entity_id=str(workspace.id),
        description=f"Updated workspace '{workspace.name}'",
        old_values=old_values,
        new_values=serialize_model(workspace),
        request=request,
    )

    return workspace


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Delete a workspace.

    - Only team owners can delete workspaces
    """
    # Get workspace
    query = (
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(selectinload(Workspace.team))
    )
    result = await db.execute(query)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # Check permissions - only owners can delete workspaces
    has_permission = await check_team_permission(
        db, current_user, workspace.team_id, [TeamRole.OWNER]
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can delete workspaces",
        )

    # Capture for audit
    workspace_name = workspace.name
    old_values = serialize_model(workspace)

    # Delete workspace
    await db.delete(workspace)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="workspace",
        entity_id=str(workspace_id),
        description=f"Deleted workspace '{workspace_name}'",
        old_values=old_values,
        request=request,
    )


# ==================== Workspace Agency Endpoints ====================


@router.post("/{workspace_id}/agencies", status_code=status.HTTP_201_CREATED)
async def add_agency_to_workspace(
    workspace_id: int,
    agency_add: WorkspaceAgencyAdd,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict:
    """
    Add an agency to a workspace.

    - Only team owners can add agencies to workspaces
    - The agency must exist
    """
    # Get workspace
    query = (
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(selectinload(Workspace.agencies))
    )
    result = await db.execute(query)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # Check permissions - only owners can add agencies
    has_permission = await check_team_permission(
        db, current_user, workspace.team_id, [TeamRole.OWNER]
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can add agencies to workspaces",
        )

    # Check agency exists
    result = await db.execute(select(Agency).where(Agency.id == agency_add.agency_id))
    agency = result.scalar_one_or_none()
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agency not found",
        )

    # Check if already added
    if any(a.id == agency_add.agency_id for a in workspace.agencies):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agency is already in this workspace",
        )

    # Add agency to workspace
    stmt = workspace_agencies.insert().values(
        workspace_id=workspace_id,
        agency_id=agency_add.agency_id,
    )
    await db.execute(stmt)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="workspace_agency",
        entity_id=f"{workspace_id}:{agency_add.agency_id}",
        description=f"Added agency '{agency.name}' to workspace '{workspace.name}'",
        new_values={"workspace_id": workspace_id, "agency_id": agency_add.agency_id},
        request=request,
    )

    return {"message": f"Agency '{agency.name}' added to workspace '{workspace.name}'"}


@router.delete("/{workspace_id}/agencies/{agency_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_agency_from_workspace(
    workspace_id: int,
    agency_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Remove an agency from a workspace.

    - Only team owners can remove agencies from workspaces
    """
    # Get workspace
    query = (
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(selectinload(Workspace.agencies))
    )
    result = await db.execute(query)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # Check permissions - only owners can remove agencies
    has_permission = await check_team_permission(
        db, current_user, workspace.team_id, [TeamRole.OWNER]
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can remove agencies from workspaces",
        )

    # Check if agency is in workspace
    agency = next((a for a in workspace.agencies if a.id == agency_id), None)
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agency not found in this workspace",
        )

    # Remove agency from workspace
    stmt = workspace_agencies.delete().where(
        workspace_agencies.c.workspace_id == workspace_id,
        workspace_agencies.c.agency_id == agency_id,
    )
    await db.execute(stmt)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="workspace_agency",
        entity_id=f"{workspace_id}:{agency_id}",
        description=f"Removed agency '{agency.name}' from workspace '{workspace.name}'",
        old_values={"workspace_id": workspace_id, "agency_id": agency_id},
        request=request,
    )


@router.get("/{workspace_id}/agencies", response_model=list[AgencySummary])
async def list_workspace_agencies(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> list[AgencySummary]:
    """
    List all agencies in a workspace.
    """
    # Get workspace with agencies
    workspace = await check_workspace_access(db, current_user, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or you don't have access",
        )

    # Reload with agencies
    query = (
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(selectinload(Workspace.agencies))
    )
    result = await db.execute(query)
    workspace = result.scalar_one_or_none()

    return [
        AgencySummary(
            id=a.id,
            name=a.name,
            slug=a.slug,
            is_active=a.is_active,
        )
        for a in workspace.agencies
    ]


# ==================== Workspace Member Endpoints ====================


@router.get("/{workspace_id}/members")
async def list_workspace_members(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> list[dict]:
    """
    List all members who have explicit access to this workspace.

    Note: Team owners automatically have access to all workspaces and are not listed here.
    This endpoint returns only non-owner members who have been granted explicit access.
    """
    # Get workspace with members
    query = (
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(
            selectinload(Workspace.team).selectinload(Team.members),
            selectinload(Workspace.members),
        )
    )
    result = await db.execute(query)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # Check access - user must be team member
    if not current_user.is_superuser:
        is_member = any(m.user_id == current_user.id for m in workspace.team.members)
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this workspace",
            )

    return [
        {
            "id": member.id,
            "email": member.email,
            "full_name": member.full_name,
        }
        for member in workspace.members
    ]


@router.post("/{workspace_id}/members", status_code=status.HTTP_201_CREATED)
async def add_workspace_member(
    workspace_id: int,
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict:
    """
    Grant a team member access to this workspace.

    - Only team owners can grant workspace access
    - The user must already be a team member (not an owner)
    - Owners automatically have access to all workspaces
    """
    # Get workspace
    query = (
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(
            selectinload(Workspace.team).selectinload(Team.members),
            selectinload(Workspace.members),
        )
    )
    result = await db.execute(query)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # Check permissions - only owners can grant access
    has_permission = await check_team_permission(
        db, current_user, workspace.team_id, [TeamRole.OWNER]
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can grant workspace access",
        )

    # Check that user is a team member
    team_member = next(
        (m for m in workspace.team.members if m.user_id == user_id),
        None
    )
    if not team_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a member of this team",
        )

    # Owners don't need explicit access
    if team_member.role == TeamRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Team owners automatically have access to all workspaces",
        )

    # Check if already has access
    if any(m.id == user_id for m in workspace.members):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has access to this workspace",
        )

    # Get user details for audit
    from app.db.base import User as UserModel
    result = await db.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()

    # Add workspace member
    stmt = workspace_members.insert().values(
        workspace_id=workspace_id,
        user_id=user_id,
    )
    await db.execute(stmt)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="workspace_member",
        entity_id=f"{workspace_id}:{user_id}",
        description=f"Granted user '{user.email}' access to workspace '{workspace.name}'",
        new_values={"workspace_id": workspace_id, "user_id": user_id},
        request=request,
    )

    return {"message": f"User '{user.email}' now has access to workspace '{workspace.name}'"}


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_workspace_member(
    workspace_id: int,
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Revoke a user's access to this workspace.

    - Only team owners can revoke workspace access
    """
    # Get workspace
    query = (
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(selectinload(Workspace.members))
    )
    result = await db.execute(query)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # Check permissions - only owners can revoke access
    has_permission = await check_team_permission(
        db, current_user, workspace.team_id, [TeamRole.OWNER]
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owners can revoke workspace access",
        )

    # Check if user has explicit access
    member = next((m for m in workspace.members if m.id == user_id), None)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User does not have explicit access to this workspace",
        )

    # Remove workspace member
    stmt = workspace_members.delete().where(
        workspace_members.c.workspace_id == workspace_id,
        workspace_members.c.user_id == user_id,
    )
    await db.execute(stmt)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="workspace_member",
        entity_id=f"{workspace_id}:{user_id}",
        description=f"Revoked user '{member.email}' access from workspace '{workspace.name}'",
        old_values={"workspace_id": workspace_id, "user_id": user_id},
        request=request,
    )
