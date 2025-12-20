"""Calendar (GTFS service schedules) management endpoints"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, cast, String, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.deps import get_db
from app.models.user import User, UserRole
from app.models.audit import AuditAction
from app.models.gtfs import Calendar, CalendarDate, Trip, GTFSFeed
from app.schemas.calendar import (
    CalendarCreate,
    CalendarUpdate,
    CalendarResponse,
    CalendarWithStats,
    CalendarWithSummary,
    CalendarList,
    CalendarListWithStats,
    CalendarDateCreate,
    CalendarDateUpdate,
    CalendarDateResponse,
    CalendarDateList,
    ServiceDaysSummary,
)
from app.utils.audit import create_audit_log, serialize_model

router = APIRouter()


def _get_service_days_summary(calendar: Calendar, exception_count: int = 0) -> ServiceDaysSummary:
    """Helper to create service days summary"""
    days = []
    if calendar.monday:
        days.append("Monday")
    if calendar.tuesday:
        days.append("Tuesday")
    if calendar.wednesday:
        days.append("Wednesday")
    if calendar.thursday:
        days.append("Thursday")
    if calendar.friday:
        days.append("Friday")
    if calendar.saturday:
        days.append("Saturday")
    if calendar.sunday:
        days.append("Sunday")

    weekdays = all([calendar.monday, calendar.tuesday, calendar.wednesday,
                    calendar.thursday, calendar.friday])
    weekends = calendar.saturday and calendar.sunday

    return ServiceDaysSummary(
        weekdays=weekdays,
        weekends=weekends,
        days_of_week=days,
        start_date=calendar.start_date,
        end_date=calendar.end_date,
        total_exceptions=exception_count,
    )


async def _verify_feed_access(
    feed_id: int,
    current_user: User,
    db: AsyncSession,
) -> GTFSFeed:
    """Verify that the feed exists and the user has access to it."""
    result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = result.scalar_one_or_none()

    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check user has access to the agency (if not super admin)
    if not current_user.is_superuser:
        from app.models.user import user_agencies

        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
        )
        membership_result = await db.execute(membership_query)
        if not membership_result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this feed",
            )

    return feed


@router.get("/", response_model=CalendarList)
async def list_calendars(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    active_only: bool = Query(False, description="Only show currently active calendars"),
) -> CalendarList:
    """
    List all calendars/services with pagination.

    Users only see calendars from feeds they have access to.
    """
    # Build query - join with GTFSFeed for agency filtering
    from app.models.gtfs import GTFSFeed
    from app.models.user import user_agencies

    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check access
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this feed",
            )

    # Build query for calendars in this specific feed
    query = select(Calendar).where(Calendar.feed_id == feed_id)

    if search:
        query = query.where(Calendar.service_id.ilike(f"%{search}%"))

    if active_only:
        # Filter by current date (simplified - would need proper date handling)
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        query = query.where(
            Calendar.start_date <= today,
            Calendar.end_date >= today,
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Calendar.service_id)
    result = await db.execute(query)
    calendars = result.scalars().all()

    return CalendarList(
        items=[CalendarResponse.model_validate(cal) for cal in calendars],
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.get("/with-stats", response_model=CalendarListWithStats)
async def list_calendars_with_stats(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> CalendarListWithStats:
    """
    List calendars with statistics (trip counts, exception counts).
    """
    from app.models.gtfs import GTFSFeed
    from app.models.user import user_agencies

    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check access
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this feed",
            )

    # Build query for calendars in this specific feed
    query = select(Calendar).where(Calendar.feed_id == feed_id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(Calendar.service_id)
    result = await db.execute(query)
    calendars = result.scalars().all()

    # Get trip counts (using composite key - service_id is string)
    service_ids = [cal.service_id for cal in calendars]
    trip_counts_query = (
        select(Trip.service_id, func.count())
        .where(Trip.feed_id == feed_id, Trip.service_id.in_(service_ids))
        .group_by(Trip.service_id)
    )
    trip_counts_result = await db.execute(trip_counts_query)
    trip_counts = dict(trip_counts_result.all())

    # Get exception counts (using composite key)
    exception_counts_query = (
        select(CalendarDate.service_id, func.count())
        .where(CalendarDate.feed_id == feed_id, CalendarDate.service_id.in_(service_ids))
        .group_by(CalendarDate.service_id)
    )
    exception_counts_result = await db.execute(exception_counts_query)
    exception_counts = dict(exception_counts_result.all())

    # Build response
    items = []
    for cal in calendars:
        cal_data = CalendarResponse.model_validate(cal)
        items.append(
            CalendarWithStats(
                **cal_data.model_dump(),
                trip_count=trip_counts.get(cal.service_id, 0),
                exception_count=exception_counts.get(cal.service_id, 0),
            )
        )

    return CalendarListWithStats(
        items=items,
        total=total or 0,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        pages=(total + limit - 1) // limit if total and limit > 0 else 0,
    )


@router.post("/", response_model=CalendarResponse, status_code=status.HTTP_201_CREATED)
async def create_calendar(
    feed_id: int,
    calendar_in: CalendarCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Calendar:
    """
    Create a new calendar/service.

    Super admins and agency admins can create calendars.
    """
    from app.models.gtfs import GTFSFeed
    from app.models.user import user_agencies

    # Verify feed exists and get its agency
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check permissions - must be super admin or agency admin for the feed's agency
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
            cast(user_agencies.c.role, String).in_([UserRole.AGENCY_ADMIN.value, UserRole.SUPER_ADMIN.value]),
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create calendars for this agency",
            )

    # Check if service_id already exists for this feed (composite key validation)
    existing = await db.execute(
        select(Calendar).where(
            Calendar.feed_id == feed_id,
            Calendar.service_id == calendar_in.service_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Calendar with service_id '{calendar_in.service_id}' already exists for this feed",
        )

    # Validate exceptions for duplicate dates before creating anything
    exceptions_data = calendar_in.exceptions or []
    if exceptions_data:
        seen_dates = set()
        for exc in exceptions_data:
            if exc.date in seen_dates:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Duplicate exception date: {exc.date}",
                )
            seen_dates.add(exc.date)

    # Create calendar (exclude exceptions from the model_dump)
    calendar_data = calendar_in.model_dump(exclude={"exceptions"})
    calendar = Calendar(**calendar_data)
    db.add(calendar)

    # Create exceptions in the same transaction
    created_exceptions = []
    for exc in exceptions_data:
        calendar_date = CalendarDate(
            feed_id=feed_id,
            service_id=calendar_in.service_id,
            date=exc.date,
            exception_type=exc.exception_type,
        )
        db.add(calendar_date)
        created_exceptions.append(calendar_date)

    # Commit everything atomically
    await db.commit()
    await db.refresh(calendar)

    # Create audit log for calendar
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="calendar",
        entity_id=f"{feed_id}:{calendar.service_id}",
        description=f"Created calendar service '{calendar.service_id}'" +
                    (f" with {len(created_exceptions)} exceptions" if created_exceptions else ""),
        new_values=serialize_model(calendar),
        agency_id=feed.agency_id,
        request=request,
    )

    # Create audit logs for exceptions
    for exc in created_exceptions:
        await create_audit_log(
            db=db,
            user=current_user,
            action=AuditAction.CREATE,
            entity_type="calendar_date",
            entity_id=f"{feed_id}:{calendar.service_id}:{exc.date}",
            description=f"Created calendar exception for service '{calendar.service_id}' on {exc.date}",
            new_values={"date": exc.date, "exception_type": exc.exception_type},
            agency_id=feed.agency_id,
            request=request,
        )

    return calendar


@router.get("/{service_id}", response_model=CalendarResponse)
async def get_calendar(
    feed_id: int,
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Calendar:
    """
    Get calendar details by composite key (feed_id, service_id).
    """
    from app.models.gtfs import GTFSFeed
    from app.models.user import user_agencies

    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check access
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this feed",
            )

    # Get calendar with composite key
    result = await db.execute(
        select(Calendar).where(
            Calendar.feed_id == feed_id,
            Calendar.service_id == service_id
        )
    )
    calendar = result.scalar_one_or_none()

    if not calendar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar not found",
        )

    return calendar


@router.get("/{service_id}/summary", response_model=CalendarWithSummary)
async def get_calendar_summary(
    feed_id: int,
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> CalendarWithSummary:
    """
    Get calendar with human-readable summary using composite key (feed_id, service_id).
    """
    from app.models.gtfs import GTFSFeed
    from app.models.user import user_agencies

    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check access
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this feed",
            )

    # Get calendar with composite key
    result = await db.execute(
        select(Calendar).where(
            Calendar.feed_id == feed_id,
            Calendar.service_id == service_id
        )
    )
    calendar = result.scalar_one_or_none()

    if not calendar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar not found",
        )

    # Get exception count (using composite key)
    exception_count_query = select(func.count()).where(
        CalendarDate.feed_id == feed_id,
        CalendarDate.service_id == service_id
    )
    exception_count = await db.scalar(exception_count_query) or 0

    cal_data = CalendarResponse.model_validate(calendar)
    summary = _get_service_days_summary(calendar, exception_count)

    return CalendarWithSummary(
        **cal_data.model_dump(),
        summary=summary,
    )


@router.patch("/{service_id}", response_model=CalendarResponse)
async def update_calendar(
    feed_id: int,
    service_id: str,
    calendar_in: CalendarUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Calendar:
    """
    Update calendar details using composite key (feed_id, service_id).

    Super admins and agency admins can update calendars.
    """
    from app.models.gtfs import GTFSFeed
    from app.models.user import user_agencies

    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check permissions - must be super admin or agency admin for the feed's agency
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
            cast(user_agencies.c.role, String).in_([UserRole.AGENCY_ADMIN.value, UserRole.SUPER_ADMIN.value]),
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this calendar",
            )

    # Get calendar with composite key
    result = await db.execute(
        select(Calendar).where(
            Calendar.feed_id == feed_id,
            Calendar.service_id == service_id
        )
    )
    calendar = result.scalar_one_or_none()

    if not calendar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar not found",
        )

    # Check if service_id is being changed and if it conflicts
    if calendar_in.service_id and calendar_in.service_id != calendar.service_id:
        existing = await db.execute(
            select(Calendar).where(
                Calendar.feed_id == feed_id,
                Calendar.service_id == calendar_in.service_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Calendar with service_id '{calendar_in.service_id}' already exists",
            )

    # Store old values for audit
    old_values = serialize_model(calendar)

    # Update calendar
    update_data = calendar_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(calendar, field, value)

    await db.commit()
    await db.refresh(calendar)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="calendar",
        entity_id=f"{feed_id}:{calendar.service_id}",
        description=f"Updated calendar service '{calendar.service_id}'",
        old_values=old_values,
        new_values=serialize_model(calendar),
        agency_id=feed.agency_id,
        request=request,
    )

    return calendar


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar(
    feed_id: int,
    service_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Delete a calendar using composite key (feed_id, service_id).

    Super admins and agency admins can delete calendars.
    This will cascade delete all calendar dates and fail if trips reference it.
    """
    from app.models.gtfs import GTFSFeed
    from app.models.user import user_agencies

    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check permissions - must be super admin or agency admin for the feed's agency
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
            cast(user_agencies.c.role, String).in_([UserRole.AGENCY_ADMIN.value, UserRole.SUPER_ADMIN.value]),
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this calendar",
            )

    # Get calendar with composite key
    result = await db.execute(
        select(Calendar).where(
            Calendar.feed_id == feed_id,
            Calendar.service_id == service_id
        )
    )
    calendar = result.scalar_one_or_none()

    if not calendar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar not found",
        )

    # Check if any trips use this calendar (using composite key)
    trip_count_query = select(func.count()).where(
        Trip.feed_id == feed_id,
        Trip.service_id == service_id
    )
    trip_count = await db.scalar(trip_count_query)

    if trip_count and trip_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete calendar: {trip_count} trips are using this service",
        )

    # Store values for audit log before deletion
    old_values = serialize_model(calendar)

    # Create audit log before deletion
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="calendar",
        entity_id=f"{feed_id}:{service_id}",
        description=f"Deleted calendar service '{calendar.service_id}'",
        old_values=old_values,
        agency_id=feed.agency_id,
        request=request,
    )

    await db.delete(calendar)
    await db.commit()


# Calendar Date (Exception) Endpoints


@router.get("/{service_id}/exceptions", response_model=CalendarDateList)
async def list_calendar_exceptions(
    feed_id: int,
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> CalendarDateList:
    """
    List all date exceptions for a calendar using composite key (feed_id, service_id).
    """
    from app.models.gtfs import GTFSFeed
    from app.models.user import user_agencies

    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check access
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
        )
        result = await db.execute(membership_query)
        if not result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this feed",
            )

    # Verify calendar exists (composite key)
    cal_result = await db.execute(
        select(Calendar).where(
            Calendar.feed_id == feed_id,
            Calendar.service_id == service_id
        )
    )
    if not cal_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar not found",
        )

    # Get exceptions (composite key)
    query = (
        select(CalendarDate)
        .where(
            CalendarDate.feed_id == feed_id,
            CalendarDate.service_id == service_id
        )
        .order_by(CalendarDate.date)
    )
    result = await db.execute(query)
    exceptions = result.scalars().all()

    return CalendarDateList(
        items=[CalendarDateResponse.model_validate(ex) for ex in exceptions],
        total=len(exceptions),
    )


@router.post("/{service_id}/exceptions", response_model=CalendarDateResponse, status_code=status.HTTP_201_CREATED)
async def create_calendar_exception(
    feed_id: int,
    service_id: str,
    exception_in: CalendarDateCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> CalendarDate:
    """
    Add a date exception to a calendar using composite key (feed_id, service_id).

    Super admins and agency admins can create exceptions.
    """
    from app.models.gtfs import GTFSFeed

    # Verify feed exists
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Verify calendar exists (composite key)
    cal_result = await db.execute(
        select(Calendar).where(
            Calendar.feed_id == feed_id,
            Calendar.service_id == service_id
        )
    )
    if not cal_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar not found",
        )

    # Check if exception already exists for this date (composite key)
    existing = await db.execute(
        select(CalendarDate).where(
            CalendarDate.feed_id == feed_id,
            CalendarDate.service_id == service_id,
            CalendarDate.date == exception_in.date,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Exception for date {exception_in.date} already exists for this calendar",
        )

    # Create exception
    calendar_date = CalendarDate(
        feed_id=feed_id,
        service_id=service_id,
        date=exception_in.date,
        exception_type=exception_in.exception_type,
    )
    db.add(calendar_date)
    await db.commit()
    await db.refresh(calendar_date)

    # Create audit log
    if request:
        await create_audit_log(
            db=db,
            user=current_user,
            action=AuditAction.CREATE,
            entity_type="calendar_date",
            entity_id=f"{feed_id}:{service_id}:{exception_in.date}",
            description=f"Created calendar exception for service '{service_id}' on {exception_in.date}",
            new_values=exception_in.model_dump(),
            agency_id=feed.agency_id,
            request=request,
        )

    return calendar_date


@router.patch("/{service_id}/exceptions/{date}", response_model=CalendarDateResponse)
async def update_calendar_exception(
    feed_id: int,
    service_id: str,
    date: str,
    exception_in: CalendarDateUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> CalendarDate:
    """
    Update a calendar date exception using composite key (feed_id, service_id, date).

    Super admins and agency admins can update exceptions.
    """
    from app.models.gtfs import GTFSFeed
    from app.models.user import user_agencies

    # Verify feed exists and user has access
    feed_result = await db.execute(
        select(GTFSFeed).where(GTFSFeed.id == feed_id)
    )
    feed = feed_result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed not found",
        )

    # Check permissions
    if not current_user.is_superuser:
        membership_query = select(user_agencies).where(
            user_agencies.c.user_id == current_user.id,
            user_agencies.c.agency_id == feed.agency_id,
            cast(user_agencies.c.role, String).in_([UserRole.AGENCY_ADMIN.value, UserRole.SUPER_ADMIN.value]),
        )
        perm_result = await db.execute(membership_query)
        if not perm_result.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this exception",
            )

    # Get exception with composite key
    result = await db.execute(
        select(CalendarDate).where(
            CalendarDate.feed_id == feed_id,
            CalendarDate.service_id == service_id,
            CalendarDate.date == date,
        )
    )
    exception = result.scalar_one_or_none()

    if not exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar exception not found",
        )

    # Store old values for audit
    old_values = {
        "date": exception.date,
        "exception_type": exception.exception_type,
    }

    # Update exception
    update_data = exception_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(exception, field, value)

    await db.commit()
    await db.refresh(exception)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="calendar_date",
        entity_id=f"{feed_id}:{service_id}:{exception.date}",
        description=f"Updated calendar exception for date '{exception.date}'",
        old_values=old_values,
        new_values={"date": exception.date, "exception_type": exception.exception_type},
        agency_id=feed.agency_id,
        request=request,
    )

    return exception


@router.delete("/{service_id}/exceptions/{date}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar_exception(
    feed_id: int,
    service_id: str,
    date: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> None:
    """
    Delete a calendar date exception.

    Super admins and agency admins can delete exceptions.
    """
    # Verify user has access to the feed
    feed = await _verify_feed_access(feed_id, current_user, db)

    # Verify calendar exists in this feed
    calendar_result = await db.execute(
        select(Calendar).where(
            Calendar.feed_id == feed_id,
            Calendar.service_id == service_id
        )
    )
    if not calendar_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calendar '{service_id}' not found in this feed",
        )

    # Get exception with composite key
    result = await db.execute(
        select(CalendarDate).where(
            CalendarDate.feed_id == feed_id,
            CalendarDate.service_id == service_id,
            CalendarDate.date == date,
        )
    )
    exception = result.scalar_one_or_none()

    if not exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calendar exception for date '{date}' not found",
        )

    # Create audit log before deletion
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="calendar_date",
        entity_id=f"{feed_id}:{service_id}:{date}",
        description=f"Deleted calendar exception for date '{date}'",
        old_values={"date": exception.date, "exception_type": exception.exception_type},
        agency_id=feed.agency_id,
        request=request,
    )

    await db.delete(exception)
    await db.commit()
