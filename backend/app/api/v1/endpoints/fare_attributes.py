"""FareAttributes API endpoints"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.api import deps
from app.api.deps import get_db
from app.models.user import User
from app.models.gtfs import FareAttribute, FareRule, GTFSFeed
from app.models.audit import AuditAction
from app.schemas.fare_attribute import (
    FareAttributeCreate,
    FareAttributeUpdate,
    FareAttributeResponse,
    FareAttributeList,
)
from app.utils.audit import create_audit_log

router = APIRouter()


@router.get("/", response_model=FareAttributeList)
async def list_fare_attributes(
    feed_id: int,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FareAttributeList:
    """
    List all fare attributes for a feed.
    """
    # Verify feed exists and user has access
    feed = await _verify_feed_access(feed_id, current_user, db)

    # Get total count
    count_result = await db.execute(
        select(func.count()).where(FareAttribute.feed_id == feed_id)
    )
    total = count_result.scalar() or 0

    # Get fare attributes
    result = await db.execute(
        select(FareAttribute)
        .where(FareAttribute.feed_id == feed_id)
        .order_by(FareAttribute.fare_id)
        .offset(skip)
        .limit(limit)
    )
    fare_attributes = result.scalars().all()

    return FareAttributeList(
        items=[FareAttributeResponse.model_validate(fa) for fa in fare_attributes],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{fare_id}", response_model=FareAttributeResponse)
async def get_fare_attribute(
    feed_id: int,
    fare_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FareAttributeResponse:
    """
    Get a specific fare attribute by composite key (feed_id, fare_id).
    """
    # Verify user has access to the feed
    feed = await _verify_feed_access(feed_id, current_user, db)

    # Get fare attribute with composite key
    result = await db.execute(
        select(FareAttribute).where(
            FareAttribute.feed_id == feed_id,
            FareAttribute.fare_id == fare_id
        )
    )
    fare_attribute = result.scalar_one_or_none()

    if not fare_attribute:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fare attribute not found",
        )

    return FareAttributeResponse.model_validate(fare_attribute)


@router.post("/", response_model=FareAttributeResponse, status_code=status.HTTP_201_CREATED)
async def create_fare_attribute(
    feed_id: int,
    fare_attribute_in: FareAttributeCreate,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FareAttributeResponse:
    """
    Create a new fare attribute.
    """
    # Verify feed exists and user has access
    feed = await _verify_feed_access(feed_id, current_user, db)

    # Check for duplicate fare_id in this feed (composite key validation)
    existing = await db.execute(
        select(FareAttribute).where(
            FareAttribute.feed_id == feed_id,
            FareAttribute.fare_id == fare_attribute_in.fare_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fare attribute with fare_id '{fare_attribute_in.fare_id}' already exists in this feed",
        )

    # Create fare attribute
    fare_attribute = FareAttribute(
        feed_id=feed_id,
        fare_id=fare_attribute_in.fare_id,
        price=fare_attribute_in.price,
        currency_type=fare_attribute_in.currency_type,
        payment_method=fare_attribute_in.payment_method,
        transfers=fare_attribute_in.transfers,
        agency_id=fare_attribute_in.agency_id,
        transfer_duration=fare_attribute_in.transfer_duration,
        custom_fields=fare_attribute_in.custom_fields,
    )

    db.add(fare_attribute)
    await db.commit()
    await db.refresh(fare_attribute)

    # Create audit log - convert Decimal to string for JSON serialization
    create_data_for_audit = {
        k: str(v) if hasattr(v, 'as_tuple') else v  # Decimal has as_tuple method
        for k, v in fare_attribute_in.model_dump().items()
    }
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="fare_attribute",
        entity_id=f"{feed_id}:{fare_attribute.fare_id}",
        description=f"Created fare attribute '{fare_attribute.fare_id}'",
        new_values=create_data_for_audit,
        agency_id=feed.agency_id,
        request=request,
    )

    return FareAttributeResponse.model_validate(fare_attribute)


@router.patch("/{fare_id}", response_model=FareAttributeResponse)
async def update_fare_attribute(
    feed_id: int,
    fare_id: str,
    fare_attribute_in: FareAttributeUpdate,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FareAttributeResponse:
    """
    Update a fare attribute using composite key (feed_id, fare_id).
    If fare_id is changed, cascades the update to all related fare_rules.
    """
    # Verify user has access to the feed
    feed = await _verify_feed_access(feed_id, current_user, db)

    # Get fare attribute with composite key
    result = await db.execute(
        select(FareAttribute).where(
            FareAttribute.feed_id == feed_id,
            FareAttribute.fare_id == fare_id
        )
    )
    fare_attribute = result.scalar_one_or_none()

    if not fare_attribute:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fare attribute not found",
        )

    # Store old values for audit
    old_values = {
        "fare_id": fare_attribute.fare_id,
        "price": str(fare_attribute.price),
        "currency_type": fare_attribute.currency_type,
        "payment_method": fare_attribute.payment_method,
        "transfers": fare_attribute.transfers,
        "agency_id": fare_attribute.agency_id,
        "transfer_duration": fare_attribute.transfer_duration,
    }

    update_data = fare_attribute_in.model_dump(exclude_unset=True)
    # Convert Decimal to string for JSON serialization in audit log
    update_data_for_audit = {
        k: str(v) if hasattr(v, 'as_tuple') else v  # Decimal has as_tuple method
        for k, v in update_data.items()
    }
    new_fare_id = update_data.get("fare_id")

    # Check if fare_id is being changed
    if new_fare_id and new_fare_id != fare_id:
        # Check if new fare_id already exists
        existing = await db.execute(
            select(FareAttribute).where(
                FareAttribute.feed_id == feed_id,
                FareAttribute.fare_id == new_fare_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Fare attribute with fare_id '{new_fare_id}' already exists in this feed",
            )

        # Cascade update to fare_rules - update all rules with old fare_id
        await db.execute(
            update(FareRule)
            .where(
                FareRule.feed_id == feed_id,
                FareRule.fare_id == fare_id
            )
            .values(fare_id=new_fare_id)
        )

        # Count affected fare rules for audit
        count_result = await db.execute(
            select(func.count()).where(
                FareRule.feed_id == feed_id,
                FareRule.fare_id == new_fare_id  # Already updated
            )
        )
        affected_rules = count_result.scalar() or 0

    # Update fields
    for field, value in update_data.items():
        setattr(fare_attribute, field, value)

    await db.commit()
    await db.refresh(fare_attribute)

    # Create audit log
    description = f"Updated fare attribute '{old_values['fare_id']}'"
    if new_fare_id and new_fare_id != fare_id:
        description = f"Renamed fare attribute '{fare_id}' to '{new_fare_id}' (cascaded to {affected_rules} fare rules)"

    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="fare_attribute",
        entity_id=f"{feed_id}:{fare_attribute.fare_id}",
        description=description,
        old_values=old_values,
        new_values=update_data_for_audit,
        agency_id=feed.agency_id,
        request=request,
    )

    return FareAttributeResponse.model_validate(fare_attribute)


@router.delete("/{fare_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fare_attribute(
    feed_id: int,
    fare_id: str,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Delete a fare attribute using composite key (feed_id, fare_id).
    """
    # Verify user has access to the feed
    feed = await _verify_feed_access(feed_id, current_user, db)

    # Get fare attribute with composite key
    result = await db.execute(
        select(FareAttribute).where(
            FareAttribute.feed_id == feed_id,
            FareAttribute.fare_id == fare_id
        )
    )
    fare_attribute = result.scalar_one_or_none()

    if not fare_attribute:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fare attribute not found",
        )

    # Store values for audit log before deletion
    old_values = {"fare_id": fare_attribute.fare_id}

    await db.delete(fare_attribute)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="fare_attribute",
        entity_id=f"{feed_id}:{fare_id}",
        description=f"Deleted fare attribute '{fare_id}'",
        old_values=old_values,
        agency_id=feed.agency_id,
        request=request,
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
        from app.models.agency import user_agencies
        from sqlalchemy import cast, String

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
