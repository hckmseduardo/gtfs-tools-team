"""Agency management models"""

from typing import List
from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin
from app.models.user import user_agencies


class Agency(Base, TimestampMixin):
    """Agency model - represents a transit agency"""

    __tablename__ = "agencies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False, comment="URL-friendly identifier"
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # GTFS agency.txt fields
    agency_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="GTFS agency_id - unique identifier for GTFS export"
    )
    agency_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="GTFS agency_url - agency website URL"
    )
    agency_timezone: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="GTFS agency_timezone - IANA timezone (e.g., America/New_York)"
    )
    agency_lang: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="GTFS agency_lang - ISO 639-1 language code"
    )
    agency_phone: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="GTFS agency_phone - voice telephone number"
    )
    agency_fare_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="GTFS agency_fare_url - URL for fare information"
    )
    agency_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="GTFS agency_email - customer service email"
    )

    # Legacy fields (kept for backwards compatibility, will migrate to GTFS fields)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User", secondary=user_agencies, back_populates="agencies"
    )
    gtfs_feeds: Mapped[List["GTFSFeed"]] = relationship(
        "GTFSFeed", back_populates="agency", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog", back_populates="agency", cascade="all, delete-orphan"
    )
    validation_preferences: Mapped["AgencyValidationPreferences | None"] = relationship(
        "AgencyValidationPreferences", back_populates="agency", cascade="all, delete-orphan", uselist=False
    )
    feed_sources: Mapped[List["ExternalFeedSource"]] = relationship(
        "ExternalFeedSource", back_populates="agency", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Agency {self.name}>"
