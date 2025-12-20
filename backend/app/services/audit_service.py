"""Audit logging service"""

from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

from app.models.audit import AuditLog, AuditAction
from app.models.user import User


class AuditService:
    """Service for creating audit log entries"""

    @staticmethod
    async def log(
        db: AsyncSession,
        user: User,
        action: AuditAction,
        entity_type: str,
        entity_id: str | int,
        agency_id: Optional[int] = None,
        description: Optional[str] = None,
        old_values: Optional[dict[str, Any]] = None,
        new_values: Optional[dict[str, Any]] = None,
        request: Optional[Request] = None,
    ) -> AuditLog:
        """
        Create an audit log entry.

        Args:
            db: Database session
            user: User performing the action
            action: Action type (create, update, delete, etc.)
            entity_type: Type of entity (e.g., 'route', 'stop', 'trip')
            entity_id: ID of the entity
            agency_id: Optional agency ID for multi-tenancy
            description: Optional human-readable description
            old_values: Previous values (for updates/deletes)
            new_values: New values (for creates/updates)
            request: FastAPI request object for extracting IP and user agent

        Returns:
            Created AuditLog instance
        """
        # Extract request metadata if available
        ip_address = None
        user_agent = None
        if request:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")

        # Create audit log entry
        audit_log = AuditLog(
            user_id=user.id,
            agency_id=agency_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            description=description,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        db.add(audit_log)
        await db.flush()  # Flush to get the ID without committing

        return audit_log

    @staticmethod
    def sanitize_values(values: dict[str, Any]) -> dict[str, Any]:
        """
        Sanitize sensitive values before logging.

        Removes or masks sensitive fields like passwords, tokens, etc.
        """
        sensitive_fields = {
            "password",
            "hashed_password",
            "token",
            "access_token",
            "refresh_token",
            "secret",
            "api_key",
        }

        sanitized = {}
        for key, value in values.items():
            if any(sensitive in key.lower() for sensitive in sensitive_fields):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value

        return sanitized
