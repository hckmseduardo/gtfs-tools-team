"""User and authentication models"""

from typing import List
from sqlalchemy import String, Boolean, Integer, Table, Column, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.base_class import Base, TimestampMixin


class UserRole(str, enum.Enum):
    """User roles"""

    SUPER_ADMIN = "super_admin"  # Platform administrator
    AGENCY_ADMIN = "agency_admin"  # Agency administrator
    EDITOR = "editor"  # Can edit GTFS data
    VIEWER = "viewer"  # Read-only access


# Association table for many-to-many relationship between users and agencies
user_agencies = Table(
    "user_agencies",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "agency_id", Integer, ForeignKey("agencies.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "role",
        SQLEnum(UserRole, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=UserRole.VIEWER,
        comment="User role for this agency",
    ),
)


class User(Base, TimestampMixin):
    """User model"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Microsoft Entra ID fields
    azure_ad_object_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    azure_ad_tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    agencies: Mapped[List["Agency"]] = relationship(
        "Agency", secondary=user_agencies, back_populates="users"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
