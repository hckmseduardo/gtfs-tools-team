"""External GTFS feed source models for automatic monitoring"""

from typing import Any, List
import enum
from sqlalchemy import String, Integer, ForeignKey, Text, JSON, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin


class FeedSourceStatus(str, enum.Enum):
    """Feed source monitoring status"""
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    PENDING = "pending"


class FeedSourceType(str, enum.Enum):
    """Type of feed source"""
    GTFS_STATIC = "gtfs_static"
    GTFS_REALTIME = "gtfs_realtime"
    GTFS_RT_VEHICLE_POSITIONS = "gtfs_rt_vehicle_positions"
    GTFS_RT_TRIP_UPDATES = "gtfs_rt_trip_updates"
    GTFS_RT_ALERTS = "gtfs_rt_alerts"
    GTFS_RT_TRIP_MODIFICATIONS = "gtfs_rt_trip_modifications"
    GTFS_RT_SHAPES = "gtfs_rt_shapes"  # Modified shapes for trip modifications
    GTFS_RT_STOPS = "gtfs_rt_stops"  # Modified/replacement stops for trip modifications


class CheckFrequency(str, enum.Enum):
    """How often to check for updates"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MANUAL = "manual"


class ExternalFeedSource(Base, TimestampMixin):
    """
    External GTFS feed source configuration.

    Allows agencies to configure external GTFS feeds to be automatically
    monitored and imported when changes are detected.
    """

    __tablename__ = "external_feed_sources"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Basic info
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Display name for this feed source"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Optional description"
    )

    # Source configuration
    source_type: Mapped[str] = mapped_column(
        Enum(FeedSourceType, native_enum=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=FeedSourceType.GTFS_STATIC.value,
        comment="Type of GTFS feed"
    )
    url: Mapped[str] = mapped_column(
        String(2000), nullable=False, comment="URL to the GTFS feed (zip or realtime)"
    )

    # Authentication (optional)
    auth_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Authentication type: none, api_key, basic, bearer"
    )
    auth_header: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Header name for API key auth"
    )
    auth_value: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="Auth value (encrypted in production)"
    )

    # Monitoring settings
    check_frequency: Mapped[str] = mapped_column(
        Enum(CheckFrequency, native_enum=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=CheckFrequency.DAILY.value,
        comment="How often to check for updates"
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="Whether monitoring is enabled"
    )
    auto_import: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Automatically import when changes detected"
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        Enum(FeedSourceStatus, native_enum=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=FeedSourceStatus.PENDING.value,
        comment="Current status"
    )
    last_checked_at: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="When the source was last checked"
    )
    last_successful_check: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="When the source was last successfully checked"
    )
    last_import_at: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="When data was last imported"
    )
    last_etag: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="ETag from last check for change detection"
    )
    last_modified: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Last-Modified header from last check"
    )
    last_content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="SHA256 hash of last downloaded content"
    )

    # Error tracking
    error_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Consecutive error count"
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Last error message"
    )

    # Import settings
    import_options: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Import options (skip_shapes, validate_only, etc.)"
    )

    # Relationships
    agency_id: Mapped[int] = mapped_column(
        ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agency: Mapped["Agency"] = relationship("Agency", back_populates="feed_sources")

    # Track which feed was created from this source
    created_feed_id: Mapped[int | None] = mapped_column(
        ForeignKey("gtfs_feeds.id", ondelete="SET NULL"), nullable=True
    )

    # History of checks
    check_history: Mapped[List["FeedSourceCheckLog"]] = relationship(
        "FeedSourceCheckLog", back_populates="feed_source", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ExternalFeedSource {self.name} ({self.status})>"


class FeedSourceCheckLog(Base, TimestampMixin):
    """Log of feed source check attempts"""

    __tablename__ = "feed_source_check_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    feed_source_id: Mapped[int] = mapped_column(
        ForeignKey("external_feed_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    feed_source: Mapped["ExternalFeedSource"] = relationship(
        "ExternalFeedSource", back_populates="check_history"
    )

    # Check details
    checked_at: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="When the check occurred"
    )
    success: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="Whether the check was successful"
    )

    # Response info
    http_status: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="HTTP status code"
    )
    content_changed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Whether content changed"
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="SHA256 hash of content"
    )
    content_size: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Size of downloaded content in bytes"
    )

    # Import info
    import_triggered: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Whether import was triggered"
    )
    import_task_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Celery task ID if import was triggered"
    )

    # Error info
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Error message if check failed"
    )

    def __repr__(self) -> str:
        return f"<FeedSourceCheckLog {self.feed_source_id} at {self.checked_at}>"
