"""Agency management endpoints"""

import re
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func, or_, cast, String, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.deps import get_db
from app.models.user import User, UserRole
from app.models.agency import Agency
from app.models.gtfs import GTFSFeed
from app.models.user import user_agencies
from app.models.team import TeamMember, Workspace, workspace_agencies
from app.models.audit import AuditAction
from app.models.validation import AgencyValidationPreferences
from app.schemas.agency import (
    AgencyCreate,
    AgencyUpdate,
    AgencyResponse,
    AgencyList,
    AgencyMember,
    AgencyMemberCreate,
    AgencyMemberUpdate,
    AgencyMemberList,
)
from app.schemas.validation import (
    AgencyValidationPreferencesCreate,
    AgencyValidationPreferencesUpdate,
    AgencyValidationPreferencesResponse,
    EnabledValidationsResponse,
    ValidationRuleSummary,
)
from app.schemas.agency_operations import (
    AgencyMergeRequest,
    AgencyMergeResponse,
    AgencyMergeValidationResult,
    AgencySplitRequest,
    AgencySplitResponse,
)
from app.services.agency_merge_service import AgencyMergeService
from app.services.agency_split_service import AgencySplitService
from app.utils.audit import create_audit_log, serialize_model

router = APIRouter()


@router.get("/", response_model=AgencyList)
async def list_agencies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> AgencyList:
    """
    List all agencies with pagination and filtering.

    Users only see agencies they belong to (directly or through teams).
    """
    # Build base query
    query = select(Agency)

    # Get agencies where user is a direct member
    direct_agency_ids = select(user_agencies.c.agency_id).where(
        user_agencies.c.user_id == current_user.id
    )

    # Get agencies where user has access through team membership
    # User -> TeamMember -> Team -> Workspace -> workspace_agencies -> Agency
    team_agency_ids = (
        select(workspace_agencies.c.agency_id)
        .select_from(TeamMember)
        .join(Workspace, TeamMember.team_id == Workspace.team_id)
        .join(workspace_agencies, Workspace.id == workspace_agencies.c.workspace_id)
        .where(TeamMember.user_id == current_user.id)
    )

    # Combine both: agencies where user is direct member OR has team access
    query = query.where(
        or_(
            Agency.id.in_(direct_agency_ids),
            Agency.id.in_(team_agency_ids)
        )
    )

    # Apply filters
    if search:
        query = query.where(
            or_(
                Agency.name.ilike(f"%{search}%"),
                Agency.slug.ilike(f"%{search}%"),
            )
        )

    if is_active is not None:
        query = query.where(Agency.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Agency.created_at.desc())
    result = await db.execute(query)
    agencies = result.scalars().all()

    return AgencyList(
        items=[AgencyResponse.model_validate(agency) for agency in agencies],
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.post("/", response_model=AgencyResponse, status_code=status.HTTP_201_CREATED)
async def create_agency(
    agency_in: AgencyCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Agency:
    """
    Create a new agency.

    Any authenticated user can create agencies.
    The creating user automatically becomes the agency admin.
    """
    # Check if slug already exists
    result = await db.execute(select(Agency).where(Agency.slug == agency_in.slug))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agency with slug '{agency_in.slug}' already exists",
        )

    # Create agency
    agency = Agency(**agency_in.model_dump())
    db.add(agency)
    await db.flush()  # Get the agency ID before adding membership

    # Add creating user as agency admin
    stmt = user_agencies.insert().values(
        user_id=current_user.id,
        agency_id=agency.id,
        role=UserRole.AGENCY_ADMIN.value,
    )
    await db.execute(stmt)

    await db.commit()
    await db.refresh(agency)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="agency",
        entity_id=str(agency.id),
        description=f"Created agency '{agency.name}' ({agency.slug})",
        new_values=serialize_model(agency),
        agency_id=agency.id,
        request=request,
    )

    return agency


@router.get("/{agency_id}", response_model=AgencyResponse)
async def get_agency(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Agency:
    """
    Get agency details by ID.

    - Super admins can view any agency
    - Other users can only view agencies they belong to (directly or through teams)
    """
    # First get the agency
    result = await db.execute(select(Agency).where(Agency.id == agency_id))
    agency = result.scalar_one_or_none()

    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agency not found",
        )

    # Check access for non-superusers
    if not current_user.is_superuser:
        # Check direct membership
        direct_access = await db.execute(
            select(user_agencies.c.agency_id).where(
                user_agencies.c.user_id == current_user.id,
                user_agencies.c.agency_id == agency_id,
            )
        )
        has_direct_access = direct_access.scalar_one_or_none() is not None

        # Check team-based access
        team_access = await db.execute(
            select(workspace_agencies.c.agency_id)
            .select_from(TeamMember)
            .join(Workspace, TeamMember.team_id == Workspace.team_id)
            .join(workspace_agencies, Workspace.id == workspace_agencies.c.workspace_id)
            .where(
                TeamMember.user_id == current_user.id,
                workspace_agencies.c.agency_id == agency_id
            )
        )
        has_team_access = team_access.scalar_one_or_none() is not None

        if not has_direct_access and not has_team_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this agency",
            )

    return agency


@router.patch("/{agency_id}", response_model=AgencyResponse)
async def update_agency(
    agency_id: int,
    agency_in: AgencyUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Agency:
    """
    Update agency details.

    - Super admins can update any agency
    - Agency admins can update only their agencies
    """
    # Get agency
    query = select(Agency).where(Agency.id == agency_id)
    result = await db.execute(query)
    agency = result.scalar_one_or_none()

    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agency not found",
        )

    # Check permissions
    if not current_user.is_superuser:
        # Check if user is agency admin
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == agency_id,
            cast(user_agencies.c.role, String) == UserRole.AGENCY_ADMIN.value,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admins or agency admins can update agencies",
            )

    # Check slug uniqueness if updating slug
    update_data = agency_in.model_dump(exclude_unset=True)
    if "slug" in update_data and update_data["slug"] != agency.slug:
        result = await db.execute(
            select(Agency).where(
                Agency.slug == update_data["slug"],
                Agency.id != agency_id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Agency with slug '{update_data['slug']}' already exists",
            )

    # Capture old values for audit log
    old_values = serialize_model(agency)

    # Update agency
    for field, value in update_data.items():
        setattr(agency, field, value)

    await db.commit()
    await db.refresh(agency)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="agency",
        entity_id=str(agency.id),
        description=f"Updated agency '{agency.name}' ({agency.slug})",
        old_values=old_values,
        new_values=serialize_model(agency),
        agency_id=agency.id,
        request=request,
    )

    return agency


@router.delete("/{agency_id}", status_code=status.HTTP_202_ACCEPTED)
async def delete_agency(
    agency_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict:
    """
    Delete an agency permanently (asynchronous).

    Super admins or agency admins can delete agencies.
    This permanently removes the agency and all associated data including:
    - GTFS feeds and all GTFS data
    - User memberships
    - Audit logs (agency-specific)
    - Validation preferences
    - Associated tasks

    Returns a task ID for tracking progress in the Task Manager.
    A global audit log (without agency_id) is created to preserve deletion history.
    """
    result = await db.execute(select(Agency).where(Agency.id == agency_id))
    agency = result.scalar_one_or_none()

    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agency not found",
        )

    # Check if user has permission to delete this agency
    if not current_user.is_superuser:
        # Check if user is agency_admin for this agency
        membership_result = await db.execute(
            select(user_agencies.c.role).where(
                user_agencies.c.user_id == current_user.id,
                user_agencies.c.agency_id == agency_id,
            )
        )
        membership = membership_result.scalar_one_or_none()

        if not membership or membership != UserRole.AGENCY_ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only agency admins can delete agencies",
            )

    # Capture agency info before deletion
    agency_name = agency.name

    # Import task models and Celery task
    from app.db.base import AsyncTask
    from app.models.task import TaskStatus, TaskType
    from app.tasks import delete_agency as delete_agency_task
    import uuid

    # Create AsyncTask record (without agency_id so it survives the deletion)
    task_record = AsyncTask(
        celery_task_id=str(uuid.uuid4()),  # Temporary UUID to avoid unique constraint violation
        task_name=f"Delete agency: {agency_name}",
        description=f"Permanently deleting agency '{agency_name}' (ID: {agency_id}) and all associated data",
        task_type=TaskType.DELETE_AGENCY.value,
        user_id=current_user.id,
        agency_id=None,  # Don't link to agency - it will be deleted
        status=TaskStatus.PENDING.value,
        progress=0.0,
        input_data={
            "agency_id": agency_id,
            "agency_name": agency_name,
        },
    )

    db.add(task_record)
    await db.commit()
    await db.refresh(task_record)

    # Queue the Celery task
    celery_result = delete_agency_task.apply_async(
        kwargs={
            "task_db_id": task_record.id,
            "agency_id": agency_id,
            "agency_name": agency_name,
            "user_id": current_user.id,
        }
    )

    # Update task record with Celery task ID
    task_record.celery_task_id = celery_result.id
    await db.commit()

    return {
        "task_id": task_record.id,
        "status": "queued",
        "message": f"Agency deletion task queued. Track progress in Task Manager.",
        "agency_id": agency_id,
        "agency_name": agency_name,
    }


@router.get("/{agency_id}/members", response_model=AgencyMemberList)
async def list_agency_members(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> AgencyMemberList:
    """
    List all members of an agency.

    - Super admins can view members of any agency
    - Other users can only view members of agencies they belong to
    """
    # Check if user has access to this agency
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == agency_id,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this agency",
            )

    # Get all members
    query = (
        select(User, user_agencies.c.role)
        .join(user_agencies)
        .where(user_agencies.c.agency_id == agency_id)
        .order_by(User.full_name)
    )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    members = [
        AgencyMember(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=role,
            is_active=True,  # Default to True - column may not exist yet
        )
        for user, role in rows
    ]

    return AgencyMemberList(
        items=members,
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.post("/{agency_id}/members", response_model=AgencyMember, status_code=status.HTTP_201_CREATED)
async def add_agency_member(
    agency_id: int,
    member_in: AgencyMemberCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> AgencyMember:
    """
    Add a user to an agency with a specific role.

    - Super admins can add members to any agency
    - Agency admins can add members to their agencies
    """
    # Check if user has permission
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == agency_id,
            cast(user_agencies.c.role, String) == UserRole.AGENCY_ADMIN.value,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admins or agency admins can add members",
            )

    # Check if agency exists
    agency_result = await db.execute(select(Agency).where(Agency.id == agency_id))
    if not agency_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agency not found",
        )

    # Check if user exists
    user_result = await db.execute(select(User).where(User.id == member_in.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if user is already a member
    existing_query = select(user_agencies).where(
        user_agencies.c.user_id == member_in.user_id,
        user_agencies.c.agency_id == agency_id,
    )
    result = await db.execute(existing_query)
    if result.first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this agency",
        )

    # Add user to agency
    stmt = user_agencies.insert().values(
        user_id=member_in.user_id,
        agency_id=agency_id,
        role=member_in.role,
        is_active=True,
    )
    await db.execute(stmt)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="agency_member",
        entity_id=f"{agency_id}:{member_in.user_id}",
        description=f"Added user {user.email} to agency with role {member_in.role}",
        new_values={"user_id": member_in.user_id, "agency_id": agency_id, "role": member_in.role, "is_active": True},
        agency_id=agency_id,
        request=request,
    )

    return AgencyMember(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member_in.role,
        is_active=True,
    )


@router.patch("/{agency_id}/members/{user_id}", response_model=AgencyMember)
async def update_agency_member(
    agency_id: int,
    user_id: int,
    member_in: AgencyMemberUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> AgencyMember:
    """
    Update a user's role or status in an agency.

    - Super admins can update any member
    - Agency admins can update members in their agencies
    """
    # Check if user has permission
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == agency_id,
            cast(user_agencies.c.role, String) == UserRole.AGENCY_ADMIN.value,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admins or agency admins can update members",
            )

    # Check if membership exists and get old values
    membership_query = select(user_agencies, User).join(User).where(
        user_agencies.c.user_id == user_id,
        user_agencies.c.agency_id == agency_id,
    )
    result = await db.execute(membership_query)
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this agency",
        )

    # Capture old values for audit log
    old_role = row[0]  # role from user_agencies
    old_is_active = row[1]  # is_active from user_agencies
    member_user = row[2]  # User object
    old_values = {"role": old_role, "is_active": old_is_active}

    # Update membership
    update_data = member_in.model_dump(exclude_unset=True)
    if update_data:
        stmt = (
            user_agencies.update()
            .where(
                user_agencies.c.user_id == user_id,
                user_agencies.c.agency_id == agency_id,
            )
            .values(**update_data)
        )
        await db.execute(stmt)
        await db.commit()

    # Get updated membership
    query = (
        select(User, user_agencies.c.role)
        .join(user_agencies)
        .where(
            user_agencies.c.user_id == user_id,
            user_agencies.c.agency_id == agency_id,
        )
    )
    result = await db.execute(query)
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    user, role = row

    # Create audit log
    new_values = {"role": role, "is_active": True}
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="agency_member",
        entity_id=f"{agency_id}:{user_id}",
        description=f"Updated user {user.email} in agency",
        old_values=old_values,
        new_values=new_values,
        agency_id=agency_id,
        request=request,
    )

    return AgencyMember(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=role,
        is_active=True,  # Default to True - column may not exist yet
    )


@router.delete("/{agency_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_agency_member(
    agency_id: int,
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Remove a user from an agency.

    - Super admins can remove any member
    - Agency admins can remove members from their agencies
    - Users cannot remove themselves
    """
    # Check if user has permission
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == agency_id,
            cast(user_agencies.c.role, String) == UserRole.AGENCY_ADMIN.value,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admins or agency admins can remove members",
            )

    # Prevent self-removal
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove yourself from an agency",
        )

    # Check if membership exists and get user info for audit log
    membership_query = select(user_agencies, User).join(User).where(
        user_agencies.c.user_id == user_id,
        user_agencies.c.agency_id == agency_id,
    )
    result = await db.execute(membership_query)
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this agency",
        )

    # Capture old values for audit log
    old_role = row[0]  # role from user_agencies
    old_is_active = row[1]  # is_active from user_agencies
    member_user = row[2]  # User object
    old_values = {"role": old_role, "is_active": old_is_active, "user_email": member_user.email}

    # Remove membership
    stmt = user_agencies.delete().where(
        user_agencies.c.user_id == user_id,
        user_agencies.c.agency_id == agency_id,
    )
    await db.execute(stmt)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="agency_member",
        entity_id=f"{agency_id}:{user_id}",
        description=f"Removed user {member_user.email} from agency",
        old_values=old_values,
        agency_id=agency_id,
        request=request,
    )




# Validation Preferences Endpoints

@router.get("/{agency_id}/validation-preferences", response_model=AgencyValidationPreferencesResponse)
async def get_validation_preferences(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Get validation preferences for an agency.

    Per claude.md line 49: "we must be able to select the gtfs validations
    we want to execute and it is as parameter auto saved by agency"

    Returns default preferences (all enabled) if none exist yet.
    """
    # Check agency exists
    agency_query = select(Agency).where(Agency.id == agency_id)
    result = await db.execute(agency_query)
    agency = result.scalar_one_or_none()
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agency with id {agency_id} not found"
        )

    # Check user has access to this agency
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == agency_id,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this agency"
            )

    # Get preferences or return defaults
    prefs_query = select(AgencyValidationPreferences).where(
        AgencyValidationPreferences.agency_id == agency_id
    )
    result = await db.execute(prefs_query)
    preferences = result.scalar_one_or_none()

    if not preferences:
        # Return default preferences (all enabled)
        return AgencyValidationPreferencesResponse(
            id=0,  # Indicates not yet saved
            agency_id=agency_id,
            **{field: True for field in AgencyValidationPreferencesResponse.model_fields
               if field.startswith('validate_')}
        )

    return preferences


@router.put("/{agency_id}/validation-preferences", response_model=AgencyValidationPreferencesResponse)
async def update_validation_preferences(
    agency_id: int,
    preferences_update: AgencyValidationPreferencesUpdate,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Update validation preferences for an agency.

    Creates new preferences if they don't exist (auto-save on first change).
    Only updates fields that are provided (partial updates supported).

    - Super admins can update any agency's preferences
    - Agency admins can update their agency's preferences
    - Editors and viewers cannot update preferences
    """
    # Check agency exists
    agency_query = select(Agency).where(Agency.id == agency_id)
    result = await db.execute(agency_query)
    agency = result.scalar_one_or_none()
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agency with id {agency_id} not found"
        )

    # Check user has permission (super admin or agency admin)
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == agency_id,
            cast(user_agencies.c.role, String) == UserRole.AGENCY_ADMIN.value,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admins or agency admins can update validation preferences"
            )

    # Get or create preferences
    prefs_query = select(AgencyValidationPreferences).where(
        AgencyValidationPreferences.agency_id == agency_id
    )
    result = await db.execute(prefs_query)
    preferences = result.scalar_one_or_none()

    if not preferences:
        # Create new preferences with defaults, then update
        preferences = AgencyValidationPreferences(agency_id=agency_id)
        db.add(preferences)
        await db.flush()  # Get the ID

    # Capture old values for audit
    old_values = serialize_model(preferences)

    # Update only provided fields
    update_data = preferences_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(preferences, field, value)

    await db.commit()
    await db.refresh(preferences)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="validation_preferences",
        entity_id=str(preferences.id),
        description=f"Updated validation preferences for agency {agency_id}",
        old_values=old_values,
        new_values=serialize_model(preferences),
        agency_id=agency_id,
        request=request,
    )

    return preferences


@router.get("/{agency_id}/validation-preferences/enabled", response_model=EnabledValidationsResponse)
async def get_enabled_validations(
    agency_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Get a summary of which validation rules are enabled for an agency.

    Returns rules grouped by entity type with counts.
    Useful for displaying validation status in UI.
    """
    # Check agency exists
    agency_query = select(Agency).where(Agency.id == agency_id)
    result = await db.execute(agency_query)
    agency = result.scalar_one_or_none()
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agency with id {agency_id} not found"
        )

    # Check user has access to this agency
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == agency_id,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this agency"
            )

    # Get preferences or use defaults
    prefs_query = select(AgencyValidationPreferences).where(
        AgencyValidationPreferences.agency_id == agency_id
    )
    result = await db.execute(prefs_query)
    preferences = result.scalar_one_or_none()

    # Build default preferences if none exist
    if not preferences:
        preferences = AgencyValidationPreferences(agency_id=agency_id)

    # Group validations by entity
    enabled_rules = ValidationRuleSummary(
        routes={
            "agency": preferences.validate_route_agency,
            "duplicates": preferences.validate_route_duplicates,
            "mandatory": preferences.validate_route_mandatory,
        },
        shapes={
            "dist_traveled": preferences.validate_shape_dist_traveled,
            "dist_accuracy": preferences.validate_shape_dist_accuracy,
            "sequence": preferences.validate_shape_sequence,
            "mandatory": preferences.validate_shape_mandatory,
        },
        calendar={
            "mandatory": preferences.validate_calendar_mandatory,
        },
        calendar_dates={
            "mandatory": preferences.validate_calendar_date_mandatory,
        },
        fare_attributes={
            "mandatory": preferences.validate_fare_attribute_mandatory,
        },
        feed_info={
            "mandatory": preferences.validate_feed_info_mandatory,
        },
        stops={
            "duplicates": preferences.validate_stop_duplicates,
            "mandatory": preferences.validate_stop_mandatory,
        },
        trips={
            "service": preferences.validate_trip_service,
            "duplicates": preferences.validate_trip_duplicates,
            "shape": preferences.validate_trip_shape,
            "mandatory": preferences.validate_trip_mandatory,
        },
        stop_times={
            "trip": preferences.validate_stop_time_trip,
            "stop": preferences.validate_stop_time_stop,
            "sequence": preferences.validate_stop_time_sequence,
            "mandatory": preferences.validate_stop_time_mandatory,
        },
    )

    # Count enabled rules
    total_rules = 21
    total_enabled = sum([
        sum(1 for v in entity_rules.values() if v)
        for entity_rules in [
            enabled_rules.routes,
            enabled_rules.shapes,
            enabled_rules.calendar,
            enabled_rules.calendar_dates,
            enabled_rules.fare_attributes,
            enabled_rules.feed_info,
            enabled_rules.stops,
            enabled_rules.trips,
            enabled_rules.stop_times,
        ]
    ])

    return EnabledValidationsResponse(
        agency_id=agency_id,
        enabled_rules=enabled_rules,
        total_enabled=total_enabled,
        total_rules=total_rules,
    )


# ============================================================================
# Merge Agencies Endpoints
# ============================================================================

@router.post("/merge", response_model=AgencyMergeResponse)
async def merge_agencies(
    request: AgencyMergeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> AgencyMergeResponse:
    """
    Merge multiple source agencies into a target agency.

    Requirements:
    - User must be SUPER_ADMIN or AGENCY_ADMIN of target agency (or super admin to create new agency)
    - Validates unique shape_ids, route_ids, trip_ids as per requirements
    - Creates new feed in target agency with merged data
    - Optionally creates a new agency for the merged data

    Returns task_id for tracking async merge progress.
    """

    target_agency = None
    new_agency_id = None

    if request.create_new_agency:
        # Superusers can always create new agencies
        # Agency admins must be admin of at least one source feed's agency
        if not current_user.is_superuser:
            # Get agency IDs from source feeds
            feed_agencies_result = await db.execute(
                select(GTFSFeed.agency_id).where(GTFSFeed.id.in_(request.source_feed_ids))
            )
            source_agency_ids = [row[0] for row in feed_agencies_result.all()]

            # Check if user is admin of at least one source agency
            admin_check = await db.execute(
                text("""
                    SELECT COUNT(*) FROM user_agencies
                    WHERE user_id = :user_id
                    AND agency_id = ANY(:agency_ids)
                    AND role = 'agency_admin'
                """),
                {"user_id": current_user.id, "agency_ids": source_agency_ids}
            )
            admin_count = admin_check.scalar()
            if admin_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You must be an agency admin of at least one source feed's agency to create a new merged agency"
                )

        # Validate new agency name is provided
        if not request.new_agency_name or not request.new_agency_name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New agency name is required when creating a new agency"
            )

        # Note: Agency names don't need to be unique, only slugs do

        # Create the new agency
        slug = re.sub(r'[^a-z0-9]+', '-', request.new_agency_name.lower()).strip('-')

        # Make sure slug is unique
        slug_result = await db.execute(
            select(Agency).where(Agency.slug == slug)
        )
        if slug_result.scalar_one_or_none():
            slug = f"{slug}-{int(datetime.now().timestamp())}"

        target_agency = Agency(
            name=request.new_agency_name.strip(),
            slug=slug,
        )
        db.add(target_agency)
        await db.flush()
        new_agency_id = target_agency.id

        # Add current user as agency admin
        await db.execute(
            text("INSERT INTO user_agencies (user_id, agency_id, role) VALUES (:user_id, :agency_id, :role)"),
            {"user_id": current_user.id, "agency_id": target_agency.id, "role": "agency_admin"}
        )
        await db.flush()
    else:
        # Using existing agency
        if not request.target_agency_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target agency ID is required when not creating a new agency"
            )

        target_agency = await db.get(Agency, request.target_agency_id)
        if not target_agency:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target agency {request.target_agency_id} not found"
            )

        # Check if user is super admin or agency admin of target
        is_super_admin = current_user.is_superuser
        result = await db.execute(
            select(user_agencies).where(
                user_agencies.c.user_id == current_user.id,
                user_agencies.c.agency_id == target_agency.id,
                cast(user_agencies.c.role, String) == UserRole.AGENCY_ADMIN.value
            )
        )
        is_agency_admin = result.first() is not None

        if not (is_super_admin or is_agency_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admins or agency admins of target agency can merge agencies"
            )

    # Validate merge request
    merge_service = AgencyMergeService(db)
    validation_result = await merge_service.validate_merge(request, current_user.id)

    if not validation_result.valid:
        # If we created a new agency but validation failed, we need to rollback
        if new_agency_id:
            await db.rollback()
        return AgencyMergeResponse(
            task_id="",
            status="failed",
            message="Merge validation failed",
            validation_result=validation_result,
        )

    # Import task models and Celery task
    from app.db.base import AsyncTask
    from app.models.task import TaskStatus, TaskType
    from app.tasks import merge_agencies as merge_agencies_task

    # Determine task description
    if request.create_new_agency:
        task_name = f"Merge feeds into new agency '{request.new_agency_name}'"
        task_description = f"Merging {len(request.source_feed_ids)} feeds into new agency '{request.new_agency_name}' as feed '{request.feed_name}'"
    else:
        task_name = f"Merge feeds into {target_agency.name}"
        task_description = f"Merging {len(request.source_feed_ids)} feeds into '{target_agency.name}' as feed '{request.feed_name}'"

    # Create AsyncTask record with temporary UUID for celery_task_id
    import uuid
    temp_celery_id = f"temp-{uuid.uuid4()}"

    task_record = AsyncTask(
        celery_task_id=temp_celery_id,  # Temporary ID, will be updated after queuing
        task_name=task_name,
        description=task_description,
        task_type=TaskType.MERGE_AGENCIES.value,
        user_id=current_user.id,
        agency_id=target_agency.id,
        status=TaskStatus.PENDING.value,
        progress=0.0,
        input_data={
            "source_feed_ids": request.source_feed_ids,
            "target_agency_id": target_agency.id,
            "create_new_agency": request.create_new_agency,
            "new_agency_name": request.new_agency_name,
            "merge_strategy": request.merge_strategy,
            "feed_name": request.feed_name,
            "feed_description": request.feed_description,
            "activate_on_success": request.activate_on_success,
        },
    )

    db.add(task_record)
    await db.commit()
    await db.refresh(task_record)

    # Queue the Celery task
    celery_result = merge_agencies_task.apply_async(
        kwargs={
            "task_db_id": task_record.id,
            "source_feed_ids": request.source_feed_ids,
            "target_agency_id": target_agency.id,
            "merge_strategy": request.merge_strategy,
            "feed_name": request.feed_name,
            "feed_description": request.feed_description,
            "activate_on_success": request.activate_on_success,
        }
    )

    # Update task record with Celery task ID
    task_record.celery_task_id = celery_result.id
    await db.commit()
    await db.refresh(task_record)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.AGENCY_MERGE,
        entity_type="agency",
        entity_id=str(target_agency.id),
        agency_id=target_agency.id,
        new_values={
            "source_feed_ids": request.source_feed_ids,
            "target_agency_id": target_agency.id,
            "create_new_agency": request.create_new_agency,
            "new_agency_name": request.new_agency_name if request.create_new_agency else None,
            "feed_name": request.feed_name,
            "merge_strategy": request.merge_strategy,
            "task_id": task_record.id,
        }
    )

    return AgencyMergeResponse(
        task_id=str(task_record.id),
        new_agency_id=new_agency_id,
        status="queued",
        message="Merge task queued. Track progress in Task Manager.",
        validation_result=validation_result if validation_result.warnings else None,
    )


@router.post("/merge/validate", response_model=AgencyMergeValidationResult)
async def validate_merge(
    request: AgencyMergeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> AgencyMergeValidationResult:
    """
    Validate a merge request without executing it (dry run).

    Returns:
    - Validation status
    - List of ID conflicts
    - Totals of entities to be merged
    - Warnings and errors
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"=== MERGE VALIDATION REQUEST ===")
    logger.info(f"source_feed_ids: {request.source_feed_ids}")
    logger.info(f"create_new_agency: {request.create_new_agency}")
    logger.info(f"new_agency_name: {request.new_agency_name}")
    logger.info(f"merge_strategy: {request.merge_strategy}")
    logger.info(f"target_agency_id: {request.target_agency_id}")

    # For existing target agency, verify it exists
    if not request.create_new_agency:
        if not request.target_agency_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target agency ID is required when not creating a new agency"
            )
        target_agency = await db.get(Agency, request.target_agency_id)
        if not target_agency:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target agency {request.target_agency_id} not found"
            )

    # Validate merge (the service handles both new and existing agency cases)
    merge_service = AgencyMergeService(db)
    validation_result = await merge_service.validate_merge(request, current_user.id)

    logger.info(f"=== MERGE VALIDATION RESULT ===")
    logger.info(f"valid: {validation_result.valid}")
    logger.info(f"errors: {validation_result.errors}")
    logger.info(f"warnings: {validation_result.warnings}")
    logger.info(f"conflicts count: {len(validation_result.conflicts)}")
    logger.info(f"total_routes: {validation_result.total_routes}")
    logger.info(f"total_trips: {validation_result.total_trips}")
    logger.info(f"total_stops: {validation_result.total_stops}")
    logger.info(f"total_shapes: {validation_result.total_shapes}")

    return validation_result


# ============================================================================
# Split Agency Endpoints
# ============================================================================

@router.post("/{agency_id}/split", response_model=AgencySplitResponse)
async def split_agency(
    agency_id: int,
    request: AgencySplitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> AgencySplitResponse:
    """
    Split selected routes from an agency into a new agency.

    Requirements:
    - User must be SUPER_ADMIN or AGENCY_ADMIN of source agency
    - Creates new agency and feed
    - Copies selected routes and all dependencies
    - Optionally removes from source

    Returns task_id for tracking async split progress.
    """

    # Check source agency exists
    source_agency = await db.get(Agency, agency_id)
    if not source_agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source agency {agency_id} not found"
        )

    # Check user permissions
    is_super_admin = current_user.is_superuser
    result = await db.execute(
        select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == source_agency.id,
            cast(user_agencies.c.role, String) == UserRole.AGENCY_ADMIN.value
        )
    )
    is_agency_admin = result.first() is not None

    if not (is_super_admin or is_agency_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins or agency admins of source agency can split agencies"
        )

    # Validate split request
    split_service = AgencySplitService(db)
    valid, errors = await split_service.validate_split(request, current_user.id)

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Split validation failed: {'; '.join(errors)}"
        )

    # Analyze dependencies for response
    dependencies = await split_service.analyze_dependencies(request)

    # Import task models and Celery task
    from app.db.base import AsyncTask
    from app.models.task import TaskStatus, TaskType
    from app.tasks import split_agency as split_agency_task

    # Create AsyncTask record
    task_record = AsyncTask(
        celery_task_id="",  # Will be updated after queuing
        task_name=f"Split agency: {request.new_agency_name}",
        description=f"Splitting {len(request.route_ids)} routes from '{source_agency.name}' into new agency '{request.new_agency_name}'",
        task_type=TaskType.SPLIT_AGENCY.value,
        user_id=current_user.id,
        agency_id=source_agency.id,
        status=TaskStatus.PENDING.value,
        progress=0.0,
        input_data={
            "source_agency_id": agency_id,
            "feed_id": request.feed_id,
            "route_ids": request.route_ids,
            "new_agency_name": request.new_agency_name,
            "new_agency_description": request.new_agency_description,
            "new_feed_name": request.new_feed_name,
            "copy_users": request.copy_users,
            "remove_from_source": request.remove_from_source,
        },
    )

    db.add(task_record)
    await db.commit()
    await db.refresh(task_record)

    # Queue the Celery task
    celery_result = split_agency_task.apply_async(
        kwargs={
            "task_db_id": task_record.id,
            "source_agency_id": agency_id,
            "feed_id": request.feed_id,
            "route_ids": request.route_ids,
            "new_agency_name": request.new_agency_name,
            "new_agency_description": request.new_agency_description,
            "new_feed_name": request.new_feed_name,
            "copy_users": request.copy_users,
            "remove_from_source": request.remove_from_source,
            "user_id": current_user.id,
        }
    )

    # Update task record with Celery task ID
    task_record.celery_task_id = celery_result.id
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.AGENCY_SPLIT,
        entity_type="agency",
        entity_id=str(source_agency.id),
        agency_id=source_agency.id,
        new_values={
            "new_agency_name": request.new_agency_name,
            "feed_id": request.feed_id,
            "route_ids": request.route_ids,
            "task_id": task_record.id,
        }
    )

    return AgencySplitResponse(
        task_id=str(task_record.id),
        new_agency_id=0,  # Will be created by the task
        new_feed_id=0,  # Will be created by the task
        status="queued",
        message=f"Split task queued. Track progress in Task Manager.",
        dependencies=dependencies,
    )
