"""Audit logging models"""

from typing import Any
from sqlalchemy import String, Integer, ForeignKey, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.base_class import Base, TimestampMixin


class AuditAction(str, enum.Enum):
    """Audit log action types"""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    IMPORT = "import"
    EXPORT = "export"
    LOGIN = "login"
    LOGOUT = "logout"
    AGENCY_MERGE = "agency_merge"
    AGENCY_SPLIT = "agency_split"


class AuditLog(Base, TimestampMixin):
    """Audit log for tracking all changes"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Who made the change
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Which agency (for multi-tenancy)
    agency_id: Mapped[int | None] = mapped_column(
        ForeignKey("agencies.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # What was changed
    action: Mapped[AuditAction] = mapped_column(
        SQLEnum(
            AuditAction,
            name="auditaction",
            create_constraint=True,
            native_enum=True,
            values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
        index=True
    )
    entity_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="e.g., 'route', 'stop', 'trip'"
    )
    entity_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="ID of the entity that was changed"
    )

    # Change details
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_values: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Previous values (for updates/deletes)"
    )
    new_values: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="New values (for creates/updates)"
    )

    # Request metadata
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="audit_logs")
    agency: Mapped["Agency | None"] = relationship("Agency", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.entity_type}:{self.entity_id}>"
