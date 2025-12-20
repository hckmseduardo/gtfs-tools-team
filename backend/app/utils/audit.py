"""
Audit logging utilities
"""

from typing import Any, Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

from app.models.audit import AuditLog, AuditAction
from app.models.user import User


async def create_audit_log(
    db: AsyncSession,
    user: User,
    action: AuditAction,
    entity_type: str,
    entity_id: str,
    description: Optional[str] = None,
    old_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
    agency_id: Optional[int] = None,
    request: Optional[Request] = None,
) -> AuditLog:
    """
    Create an audit log entry.

    Args:
        db: Database session
        user: User performing the action
        action: Type of action (create, update, delete, etc.)
        entity_type: Type of entity being modified (e.g., 'route', 'stop', 'trip')
        entity_id: ID of the entity
        description: Optional description of the action
        old_values: Previous values (for updates/deletes)
        new_values: New values (for creates/updates)
        agency_id: Agency ID for multi-tenancy
        request: Optional FastAPI request object to extract IP and user agent

    Returns:
        Created AuditLog instance
    """
    # Extract request metadata if available
    ip_address = None
    user_agent = None
    if request:
        # Try to get real IP from X-Forwarded-For header (for proxy setups)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            ip_address = forwarded_for.split(",")[0].strip()
        else:
            ip_address = request.client.host if request.client else None

        user_agent = request.headers.get("User-Agent")

    audit_log = AuditLog(
        user_id=user.id,
        agency_id=agency_id,
        action=action.value if isinstance(action, AuditAction) else action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        description=description,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.add(audit_log)
    await db.commit()
    await db.refresh(audit_log)

    return audit_log


def serialize_model(model: Any, exclude_fields: Optional[list[str]] = None) -> Dict[str, Any]:
    """
    Serialize a SQLAlchemy model to a dictionary for audit logging.

    Args:
        model: SQLAlchemy model instance
        exclude_fields: List of field names to exclude from serialization

    Returns:
        Dictionary representation of the model
    """
    if exclude_fields is None:
        exclude_fields = []

    # Get all columns from the model
    result = {}
    for column in model.__table__.columns:
        if column.name not in exclude_fields:
            value = getattr(model, column.name)
            # Convert to JSON-serializable types
            if hasattr(value, 'isoformat'):
                # Handle datetime objects
                result[column.name] = value.isoformat()
            elif hasattr(value, '__json__'):
                # Handle objects with custom JSON serialization
                result[column.name] = value.__json__()
            elif isinstance(value, (str, int, float, bool, type(None))):
                result[column.name] = value
            else:
                # For other types, convert to string
                result[column.name] = str(value)

    return result
