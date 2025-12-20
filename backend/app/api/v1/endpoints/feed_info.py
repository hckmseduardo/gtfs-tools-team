"""FeedInfo API endpoints"""

from fastapi import APIRouter, Depends, HTTPException, Request, status, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api import deps
from app.api.deps import get_db
from app.models.user import User, UserRole, user_agencies
from app.models.gtfs import FeedInfo, GTFSFeed
from app.models.audit import AuditAction
from app.schemas.feed_info import (
    FeedInfoCreate,
    FeedInfoUpdate,
    FeedInfoResponse,
)
from app.utils.audit import create_audit_log

router = APIRouter()


@router.get("", response_model=FeedInfoResponse)
async def get_feed_info(
    feed_id: int = Path(..., description="Feed ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FeedInfoResponse:
    """
    Get feed info for a specific feed.
    Each feed can have only one feed_info record.
    """
    # Verify feed exists and user has access
    await deps.verify_feed_access(feed_id, db, current_user)

    result = await db.execute(
        select(FeedInfo).where(FeedInfo.feed_id == feed_id)
    )
    feed_info = result.scalar_one_or_none()

    if not feed_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed info not found for this feed",
        )

    return FeedInfoResponse.model_validate(feed_info)


@router.post("", response_model=FeedInfoResponse, status_code=status.HTTP_201_CREATED)
async def create_feed_info(
    feed_info_in: FeedInfoCreate,
    feed_id: int = Path(..., description="Feed ID"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FeedInfoResponse:
    """
    Create feed info for a feed.
    Each feed can have only one feed_info record.
    """
    # Verify feed exists and user has access
    agency_id = await deps.verify_feed_access(
        feed_id, db, current_user, required_role=UserRole.EDITOR
    )

    # Check if feed_info already exists for this feed
    existing = await db.execute(
        select(FeedInfo).where(FeedInfo.feed_id == feed_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feed info already exists for this feed. Use PATCH to update.",
        )

    # Create feed info
    feed_info = FeedInfo(
        feed_id=feed_id,
        feed_publisher_name=feed_info_in.feed_publisher_name,
        feed_publisher_url=feed_info_in.feed_publisher_url,
        feed_lang=feed_info_in.feed_lang,
        default_lang=feed_info_in.default_lang,
        feed_start_date=feed_info_in.feed_start_date,
        feed_end_date=feed_info_in.feed_end_date,
        feed_version=feed_info_in.feed_version,
        feed_contact_email=feed_info_in.feed_contact_email,
        feed_contact_url=feed_info_in.feed_contact_url,
        custom_fields=feed_info_in.custom_fields,
    )

    db.add(feed_info)
    await db.commit()
    await db.refresh(feed_info)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="feed_info",
        entity_id=str(feed_id),
        description=f"Created feed info for feed {feed_id}",
        new_values=feed_info_in.model_dump(),
        agency_id=agency_id,
        request=request,
    )

    return FeedInfoResponse.model_validate(feed_info)


@router.patch("", response_model=FeedInfoResponse)
async def update_feed_info(
    feed_info_in: FeedInfoUpdate,
    feed_id: int = Path(..., description="Feed ID"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FeedInfoResponse:
    """
    Update feed info for a feed.
    """
    # Verify feed exists and user has access
    agency_id = await deps.verify_feed_access(
        feed_id, db, current_user, required_role=UserRole.EDITOR
    )

    result = await db.execute(
        select(FeedInfo).where(FeedInfo.feed_id == feed_id)
    )
    feed_info = result.scalar_one_or_none()

    if not feed_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed info not found for this feed",
        )

    # Store old values for audit
    old_values = {
        "feed_publisher_name": feed_info.feed_publisher_name,
        "feed_publisher_url": feed_info.feed_publisher_url,
        "feed_lang": feed_info.feed_lang,
        "default_lang": feed_info.default_lang,
        "feed_start_date": feed_info.feed_start_date,
        "feed_end_date": feed_info.feed_end_date,
        "feed_version": feed_info.feed_version,
        "feed_contact_email": feed_info.feed_contact_email,
        "feed_contact_url": feed_info.feed_contact_url,
    }

    # Update fields
    update_data = feed_info_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(feed_info, field, value)

    await db.commit()
    await db.refresh(feed_info)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="feed_info",
        entity_id=str(feed_id),
        description=f"Updated feed info for feed {feed_id}",
        old_values=old_values,
        new_values=update_data,
        agency_id=agency_id,
        request=request,
    )

    return FeedInfoResponse.model_validate(feed_info)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feed_info(
    feed_id: int = Path(..., description="Feed ID"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Delete feed info for a feed.
    """
    # Verify feed exists and user has access
    agency_id = await deps.verify_feed_access(
        feed_id, db, current_user, required_role=UserRole.AGENCY_ADMIN
    )

    result = await db.execute(
        select(FeedInfo).where(FeedInfo.feed_id == feed_id)
    )
    feed_info = result.scalar_one_or_none()

    if not feed_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feed info not found for this feed",
        )

    await db.delete(feed_info)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="feed_info",
        entity_id=str(feed_id),
        description=f"Deleted feed info for feed {feed_id}",
        old_values={"feed_id": feed_id},
        agency_id=agency_id,
        request=request,
    )
