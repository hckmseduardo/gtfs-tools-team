"""User management endpoints"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.deps import get_db
from app.models.user import User, UserRole, user_agencies
from app.models.agency import Agency
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserPasswordUpdate,
    UserResponse,
    UserWithAgencies,
    UserList,
    UserListWithAgencies,
    UserAgencyMembership,
)
from app.core.security import get_password_hash, verify_password

router = APIRouter()


@router.get("/", response_model=UserList)
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_role(UserRole.SUPER_ADMIN)),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> UserList:
    """
    List all users with pagination and filtering.

    Only super admins can list all users.
    """
    # Build query
    query = select(User)

    # Apply filters
    if search:
        query = query.where(
            or_(
                User.email.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
            )
        )

    if is_active is not None:
        query = query.where(User.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(User.created_at.desc())
    result = await db.execute(query)
    users = result.scalars().all()

    return UserList(
        items=[UserResponse.model_validate(user) for user in users],
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.get("/me", response_model=UserWithAgencies)
async def get_current_user_info(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> UserWithAgencies:
    """
    Get current user's information including agency memberships.
    """
    # Get user's agency memberships
    query = (
        select(Agency, user_agencies.c.role)
        .join(user_agencies)
        .where(user_agencies.c.user_id == current_user.id)
        .order_by(Agency.name)
    )
    result = await db.execute(query)
    rows = result.all()

    agencies = [
        UserAgencyMembership(
            agency_id=agency.id,
            agency_name=agency.name,
            agency_slug=agency.slug,
            role=role,
            is_active=True,  # Membership is active if it exists
        )
        for agency, role in rows
    ]

    user_data = UserResponse.model_validate(current_user)
    return UserWithAgencies(
        **user_data.model_dump(),
        agencies=agencies,
    )


@router.get("/{user_id}", response_model=UserWithAgencies)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> UserWithAgencies:
    """
    Get user details by ID.

    - Users can view their own info
    - Super admins can view any user
    - Agency admins can view users in their agencies
    """
    # Users can always view their own info
    if user_id == current_user.id:
        return await get_current_user_info(db, current_user)

    # Get target user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Super admins can view anyone
    if current_user.is_superuser:
        # Get user's agency memberships
        query = (
            select(Agency, user_agencies.c.role)
            .join(user_agencies)
            .where(user_agencies.c.user_id == user_id)
            .order_by(Agency.name)
        )
        result = await db.execute(query)
        rows = result.all()

        agencies = [
            UserAgencyMembership(
                agency_id=agency.id,
                agency_name=agency.name,
                agency_slug=agency.slug,
                role=role,
                is_active=True,  # Membership is active if it exists
            )
            for agency, role in rows
        ]

        user_data = UserResponse.model_validate(user)
        return UserWithAgencies(
            **user_data.model_dump(),
            agencies=agencies,
        )

    # Agency admins can view users in their agencies
    # Check if current user is admin of any shared agency
    shared_agency_query = (
        select(func.count())
        .select_from(user_agencies.alias("ua1"))
        .join(
            user_agencies.alias("ua2"),
            user_agencies.c.agency_id == user_agencies.c.agency_id,
        )
        .where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.role == UserRole.AGENCY_ADMIN.value,
            user_agencies.c.user_id == user_id,
        )
    )
    shared_count = await db.scalar(shared_agency_query)

    if shared_count and shared_count > 0:
        # Get user's agency memberships (only shared agencies)
        query = (
            select(Agency, user_agencies.c.role)
            .join(user_agencies)
            .where(
                user_agencies.c.user_id == user_id,
                user_agencies.c.agency_id.in_(
                    select(user_agencies.c.agency_id).where(
                        user_agencies.c.user_id == current_user.id,
                        user_agencies.c.role == UserRole.AGENCY_ADMIN.value,
                    )
                ),
            )
            .order_by(Agency.name)
        )
        result = await db.execute(query)
        rows = result.all()

        agencies = [
            UserAgencyMembership(
                agency_id=agency.id,
                agency_name=agency.name,
                agency_slug=agency.slug,
                role=role,
                is_active=True,  # Membership is active if it exists
            )
            for agency, role in rows
        ]

        user_data = UserResponse.model_validate(user)
        return UserWithAgencies(
            **user_data.model_dump(),
            agencies=agencies,
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have permission to view this user",
    )


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> User:
    """
    Update current user's information.
    """
    # Check if email is being changed and if it's already taken
    if user_in.email and user_in.email != current_user.email:
        result = await db.execute(select(User).where(User.email == user_in.email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # Update user
    update_data = user_in.model_dump(exclude_unset=True, exclude={"is_active"})  # Users can't change their own active status
    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    return current_user


@router.patch("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def update_current_user_password(
    password_update: UserPasswordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Update current user's password.
    """
    # Verify current password
    if not current_user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is using external authentication and cannot change password",
        )

    if not verify_password(password_update.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password",
        )

    # Update password
    current_user.hashed_password = get_password_hash(password_update.new_password)
    await db.commit()


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_role(UserRole.SUPER_ADMIN)),
) -> User:
    """
    Update user information.

    Only super admins can update other users.
    """
    # Get user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if email is being changed and if it's already taken
    if user_in.email and user_in.email != user.email:
        result = await db.execute(select(User).where(User.email == user_in.email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # Update user
    update_data = user_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)

    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.require_role(UserRole.SUPER_ADMIN)),
) -> None:
    """
    Deactivate a user (soft delete).

    Only super admins can delete users.
    Users cannot delete themselves.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete yourself",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Soft delete
    user.is_active = False
    await db.commit()


@router.post("/me/create-demo-data")
async def create_demo_data_for_current_user(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> dict:
    """
    Create a demo agency with sample GTFS data for the current user.

    This creates:
    - 1 Demo Agency
    - 1 Feed with sample data
    - 2 Routes (bus and train)
    - 6 Stops
    - 4 Trips with stop times
    - 1 Calendar (weekday service)
    - 2 Shapes (one per route)
    """
    from app.services.demo_agency_service import create_demo_agency_for_user

    try:
        agency = await create_demo_agency_for_user(db, current_user)
        return {
            "success": True,
            "message": f"Demo agency '{agency.name}' created successfully!",
            "agency_id": agency.id,
            "agency_name": agency.name,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create demo data: {str(e)}",
        )
