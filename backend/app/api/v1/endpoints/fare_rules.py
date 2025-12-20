"""FareRules API endpoints"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.api import deps
from app.api.deps import get_db
from app.models.user import User
from app.models.gtfs import FareRule, FareAttribute, GTFSFeed
from app.models.audit import AuditAction
from app.schemas.fare_rule import (
    FareRuleCreate,
    FareRuleUpdate,
    FareRuleResponse,
    FareRuleList,
    FareRuleIdentifier,
    FareRuleUpdateRequest,
)
from app.utils.audit import create_audit_log

router = APIRouter()


@router.get("/", response_model=FareRuleList)
async def list_fare_rules(
    feed_id: int,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    fare_id: Optional[str] = Query(None, description="Filter by fare_id"),
    route_id: Optional[str] = Query(None, description="Filter by route_id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FareRuleList:
    """
    List all fare rules for a feed.
    """
    # Verify feed exists and user has access
    feed = await _verify_feed_access(feed_id, current_user, db)

    # Build query with optional filters
    query = select(FareRule).where(FareRule.feed_id == feed_id)
    count_query = select(func.count()).where(FareRule.feed_id == feed_id)

    if fare_id:
        query = query.where(FareRule.fare_id == fare_id)
        count_query = count_query.where(FareRule.fare_id == fare_id)

    if route_id:
        query = query.where(FareRule.route_id == route_id)
        count_query = count_query.where(FareRule.route_id == route_id)

    # Get total count
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Get fare rules
    result = await db.execute(
        query
        .order_by(FareRule.fare_id, FareRule.route_id)
        .offset(skip)
        .limit(limit)
    )
    fare_rules = result.scalars().all()

    return FareRuleList(
        items=[FareRuleResponse.model_validate(fr) for fr in fare_rules],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/by-fare/{fare_id}", response_model=FareRuleList)
async def get_fare_rules_by_fare_id(
    feed_id: int,
    fare_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FareRuleList:
    """
    Get all fare rules for a specific fare_id.
    """
    # Verify user has access to the feed
    feed = await _verify_feed_access(feed_id, current_user, db)

    # Get fare rules
    result = await db.execute(
        select(FareRule).where(
            FareRule.feed_id == feed_id,
            FareRule.fare_id == fare_id
        ).order_by(FareRule.route_id)
    )
    fare_rules = result.scalars().all()

    return FareRuleList(
        items=[FareRuleResponse.model_validate(fr) for fr in fare_rules],
        total=len(fare_rules),
        skip=0,
        limit=len(fare_rules),
    )


@router.post("/get", response_model=FareRuleResponse)
async def get_fare_rule(
    feed_id: int,
    identifier: FareRuleIdentifier,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FareRuleResponse:
    """
    Get a specific fare rule by its composite key.
    Uses POST to handle the complex composite key in the request body.
    """
    # Verify user has access to the feed
    feed = await _verify_feed_access(feed_id, current_user, db)

    # Get fare rule with composite key
    result = await db.execute(
        select(FareRule).where(
            FareRule.feed_id == feed_id,
            FareRule.fare_id == identifier.fare_id,
            FareRule.route_id == identifier.route_id,
            FareRule.origin_id == identifier.origin_id,
            FareRule.destination_id == identifier.destination_id,
            FareRule.contains_id == identifier.contains_id,
        )
    )
    fare_rule = result.scalar_one_or_none()

    if not fare_rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fare rule not found",
        )

    return FareRuleResponse.model_validate(fare_rule)


@router.post("/", response_model=FareRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_fare_rule(
    feed_id: int,
    fare_rule_in: FareRuleCreate,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FareRuleResponse:
    """
    Create a new fare rule.
    """
    # Verify feed exists and user has access
    feed = await _verify_feed_access(feed_id, current_user, db)

    # Verify the fare_id exists in fare_attributes
    existing_fare = await db.execute(
        select(FareAttribute).where(
            FareAttribute.feed_id == feed_id,
            FareAttribute.fare_id == fare_rule_in.fare_id,
        )
    )
    if not existing_fare.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fare attribute with fare_id '{fare_rule_in.fare_id}' does not exist in this feed",
        )

    # Check for duplicate fare rule (all composite key fields)
    existing = await db.execute(
        select(FareRule).where(
            FareRule.feed_id == feed_id,
            FareRule.fare_id == fare_rule_in.fare_id,
            FareRule.route_id == fare_rule_in.route_id,
            FareRule.origin_id == fare_rule_in.origin_id,
            FareRule.destination_id == fare_rule_in.destination_id,
            FareRule.contains_id == fare_rule_in.contains_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fare rule with these fields already exists in this feed",
        )

    # Create fare rule
    fare_rule = FareRule(
        feed_id=feed_id,
        fare_id=fare_rule_in.fare_id,
        route_id=fare_rule_in.route_id,
        origin_id=fare_rule_in.origin_id,
        destination_id=fare_rule_in.destination_id,
        contains_id=fare_rule_in.contains_id,
        custom_fields=fare_rule_in.custom_fields,
    )

    db.add(fare_rule)
    await db.commit()
    await db.refresh(fare_rule)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.CREATE,
        entity_type="fare_rule",
        entity_id=f"{feed_id}:{fare_rule.fare_id}:{fare_rule.route_id}:{fare_rule.origin_id}:{fare_rule.destination_id}:{fare_rule.contains_id}",
        description=f"Created fare rule for fare '{fare_rule.fare_id}'",
        new_values=fare_rule_in.model_dump(),
        agency_id=feed.agency_id,
        request=request,
    )

    return FareRuleResponse.model_validate(fare_rule)


@router.patch("/", response_model=FareRuleResponse)
async def update_fare_rule(
    feed_id: int,
    update_request: FareRuleUpdateRequest,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> FareRuleResponse:
    """
    Update a fare rule using composite key.
    Request body contains identifier (old values) and update (new values).
    Supports updating fare_id by deleting old record and creating new one.
    """
    identifier = update_request.identifier
    fare_rule_in = update_request.update

    # Verify user has access to the feed
    feed = await _verify_feed_access(feed_id, current_user, db)

    # Get fare rule with composite key
    result = await db.execute(
        select(FareRule).where(
            FareRule.feed_id == feed_id,
            FareRule.fare_id == identifier.fare_id,
            FareRule.route_id == identifier.route_id,
            FareRule.origin_id == identifier.origin_id,
            FareRule.destination_id == identifier.destination_id,
            FareRule.contains_id == identifier.contains_id,
        )
    )
    fare_rule = result.scalar_one_or_none()

    if not fare_rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fare rule not found",
        )

    # Store old values for audit
    old_values = {
        "fare_id": fare_rule.fare_id,
        "route_id": fare_rule.route_id,
        "origin_id": fare_rule.origin_id,
        "destination_id": fare_rule.destination_id,
        "contains_id": fare_rule.contains_id,
        "custom_fields": fare_rule.custom_fields,
    }

    update_data = fare_rule_in.model_dump(exclude_unset=True)

    # Determine new values for all key fields (use new value if provided, else keep old)
    new_fare_id = update_data.get("fare_id", identifier.fare_id)
    new_route_id = update_data.get("route_id", identifier.route_id)
    new_origin_id = update_data.get("origin_id", identifier.origin_id)
    new_destination_id = update_data.get("destination_id", identifier.destination_id)
    new_contains_id = update_data.get("contains_id", identifier.contains_id)

    # Check if any key field is being changed (requires delete + create since they're all part of PK)
    key_changed = (
        new_fare_id != identifier.fare_id or
        new_route_id != identifier.route_id or
        new_origin_id != identifier.origin_id or
        new_destination_id != identifier.destination_id or
        new_contains_id != identifier.contains_id
    )

    if key_changed:
        # If fare_id is being changed, verify it exists in fare_attributes
        if new_fare_id != identifier.fare_id:
            existing_fare = await db.execute(
                select(FareAttribute).where(
                    FareAttribute.feed_id == feed_id,
                    FareAttribute.fare_id == new_fare_id,
                )
            )
            if not existing_fare.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Fare attribute with fare_id '{new_fare_id}' does not exist in this feed",
                )

        # Check if target fare rule already exists
        existing_rule = await db.execute(
            select(FareRule).where(
                FareRule.feed_id == feed_id,
                FareRule.fare_id == new_fare_id,
                FareRule.route_id == new_route_id,
                FareRule.origin_id == new_origin_id,
                FareRule.destination_id == new_destination_id,
                FareRule.contains_id == new_contains_id,
            )
        )
        if existing_rule.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A fare rule with this combination already exists",
            )

        # Delete old fare rule
        await db.delete(fare_rule)

        # Create new fare rule with updated key fields
        new_fare_rule = FareRule(
            feed_id=feed_id,
            fare_id=new_fare_id,
            route_id=new_route_id,
            origin_id=new_origin_id,
            destination_id=new_destination_id,
            contains_id=new_contains_id,
            custom_fields=update_data.get("custom_fields", fare_rule.custom_fields),
        )
        db.add(new_fare_rule)
        await db.commit()
        await db.refresh(new_fare_rule)
        fare_rule = new_fare_rule
    else:
        # Only update non-key fields (custom_fields)
        if "custom_fields" in update_data:
            fare_rule.custom_fields = update_data["custom_fields"]

        await db.commit()
        await db.refresh(fare_rule)

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.UPDATE,
        entity_type="fare_rule",
        entity_id=f"{feed_id}:{fare_rule.fare_id}:{fare_rule.route_id}:{fare_rule.origin_id}:{fare_rule.destination_id}:{fare_rule.contains_id}",
        description=f"Updated fare rule from fare '{old_values['fare_id']}' to '{fare_rule.fare_id}'",
        old_values=old_values,
        new_values=update_data,
        agency_id=feed.agency_id,
        request=request,
    )

    return FareRuleResponse.model_validate(fare_rule)


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fare_rule(
    feed_id: int,
    identifier: FareRuleIdentifier,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Delete a fare rule using composite key.
    Uses DELETE with body for identifier due to complex composite key.
    """
    # Verify user has access to the feed
    feed = await _verify_feed_access(feed_id, current_user, db)

    # Get fare rule with composite key
    result = await db.execute(
        select(FareRule).where(
            FareRule.feed_id == feed_id,
            FareRule.fare_id == identifier.fare_id,
            FareRule.route_id == identifier.route_id,
            FareRule.origin_id == identifier.origin_id,
            FareRule.destination_id == identifier.destination_id,
            FareRule.contains_id == identifier.contains_id,
        )
    )
    fare_rule = result.scalar_one_or_none()

    if not fare_rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fare rule not found",
        )

    # Store values for audit log before deletion
    old_values = {
        "fare_id": fare_rule.fare_id,
        "route_id": fare_rule.route_id,
        "origin_id": fare_rule.origin_id,
        "destination_id": fare_rule.destination_id,
        "contains_id": fare_rule.contains_id,
    }

    await db.delete(fare_rule)
    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="fare_rule",
        entity_id=f"{feed_id}:{identifier.fare_id}:{identifier.route_id}:{identifier.origin_id}:{identifier.destination_id}:{identifier.contains_id}",
        description=f"Deleted fare rule for fare '{identifier.fare_id}'",
        old_values=old_values,
        agency_id=feed.agency_id,
        request=request,
    )


@router.delete("/by-fare/{fare_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fare_rules_by_fare_id(
    feed_id: int,
    fare_id: str,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Delete all fare rules for a specific fare_id.
    """
    # Verify user has access to the feed
    feed = await _verify_feed_access(feed_id, current_user, db)

    # Get all fare rules for this fare_id
    result = await db.execute(
        select(FareRule).where(
            FareRule.feed_id == feed_id,
            FareRule.fare_id == fare_id,
        )
    )
    fare_rules = result.scalars().all()

    if not fare_rules:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No fare rules found for fare_id '{fare_id}'",
        )

    deleted_count = len(fare_rules)

    for fare_rule in fare_rules:
        await db.delete(fare_rule)

    await db.commit()

    # Create audit log
    await create_audit_log(
        db=db,
        user=current_user,
        action=AuditAction.DELETE,
        entity_type="fare_rule",
        entity_id=f"{feed_id}:{fare_id}:*",
        description=f"Deleted {deleted_count} fare rules for fare '{fare_id}'",
        old_values={"fare_id": fare_id, "count": deleted_count},
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
