"""Audit log endpoints"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, cast, String

from app.api import deps
from app.api.deps import get_db
from app.models.user import User, UserRole
from app.models.audit import AuditLog, AuditAction
from app.schemas.audit import AuditLogResponse, AuditLogList, AuditLogStats

router = APIRouter()


@router.get("/", response_model=AuditLogList)
async def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    agency_id: Optional[int] = Query(None, description="Filter by agency ID"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    action: Optional[AuditAction] = Query(None, description="Filter by action type"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> AuditLogList:
    """
    List audit logs with filtering and pagination.

    Agency admins can see logs for their agencies.
    Super admins can see all logs.
    """
    # Build query
    query = select(AuditLog).order_by(desc(AuditLog.created_at))

    # Filter by agency if specified
    if agency_id is not None:
        # Check user has access to this agency
        if not current_user.is_superuser:
            from app.models.agency import user_agencies
            membership_query = select(user_agencies).where(
                user_agencies.c.user_id == current_user.id,
                user_agencies.c.agency_id == agency_id,
            )
            membership_result = await db.execute(membership_query)
            if not membership_result.first():
                # User doesn't have access - return empty list
                return AuditLogList(items=[], total=0, skip=skip, limit=limit)

        query = query.where(AuditLog.agency_id == agency_id)
    elif not current_user.is_superuser:
        # Non-super admins can only see logs for their agencies
        from app.models.agency import user_agencies
        subquery = select(user_agencies.c.agency_id).where(
            user_agencies.c.user_id == current_user.id
        )
        query = query.where(AuditLog.agency_id.in_(subquery))

    # Apply other filters
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    if action is not None:
        query = query.where(cast(AuditLog.action, String) == action.value)
    if entity_type is not None:
        query = query.where(AuditLog.entity_type == entity_type)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get paginated results
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return AuditLogList(
        items=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/stats", response_model=AuditLogStats)
async def get_audit_stats(
    agency_id: Optional[int] = Query(None, description="Filter by agency ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> AuditLogStats:
    """
    Get audit log statistics (action counts).
    """
    # Build base query
    query = select(
        cast(AuditLog.action, String).label("action"),
        func.count(AuditLog.id).label("count")
    )

    # Filter by agency if specified
    if agency_id is not None:
        # Check user has access to this agency
        if not current_user.is_superuser:
            from app.models.agency import user_agencies
            membership_query = select(user_agencies).where(
                user_agencies.c.user_id == current_user.id,
                user_agencies.c.agency_id == agency_id,
            )
            membership_result = await db.execute(membership_query)
            if not membership_result.first():
                # User doesn't have access - return empty stats
                return AuditLogStats(
                    total_logs=0,
                    action_counts={},
                    entity_type_counts={},
                )

        query = query.where(AuditLog.agency_id == agency_id)
    elif not current_user.is_superuser:
        # Non-super admins can only see logs for their agencies
        from app.models.agency import user_agencies
        subquery = select(user_agencies.c.agency_id).where(
            user_agencies.c.user_id == current_user.id
        )
        query = query.where(AuditLog.agency_id.in_(subquery))

    # Get action counts
    action_query = query.group_by(cast(AuditLog.action, String))
    action_result = await db.execute(action_query)
    action_counts = {row.action: row.count for row in action_result}

    # Get entity type counts
    entity_query = select(
        AuditLog.entity_type,
        func.count(AuditLog.id).label("count")
    )

    if agency_id is not None:
        entity_query = entity_query.where(AuditLog.agency_id == agency_id)
    elif not current_user.is_superuser:
        from app.models.agency import user_agencies
        subquery = select(user_agencies.c.agency_id).where(
            user_agencies.c.user_id == current_user.id
        )
        entity_query = entity_query.where(AuditLog.agency_id.in_(subquery))

    entity_query = entity_query.group_by(AuditLog.entity_type)
    entity_result = await db.execute(entity_query)
    entity_type_counts = {row.entity_type: row.count for row in entity_result}

    # Get total count
    total_logs = sum(action_counts.values())

    return AuditLogStats(
        total_logs=total_logs,
        action_counts=action_counts,
        entity_type_counts=entity_type_counts,
    )


@router.get("/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> AuditLogResponse:
    """
    Get a specific audit log by ID.
    """
    result = await db.execute(select(AuditLog).where(AuditLog.id == log_id))
    log = result.scalar_one_or_none()

    if not log:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log not found",
        )

    # Check user has access to this log's agency
    if not current_user.is_superuser and log.agency_id:
        from app.models.agency import user_agencies
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == log.agency_id,
        )
        membership_result = await db.execute(membership_query)
        if not membership_result.first():
            from fastapi import HTTPException
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this audit log",
            )

    return AuditLogResponse.model_validate(log)
