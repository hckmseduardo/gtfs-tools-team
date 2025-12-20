"""GTFS (General Transit Feed Specification) models"""

from typing import List
from decimal import Decimal
from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Text,
    Date,
    Time,
    Numeric,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from app.db.base_class import Base, TimestampMixin


class GTFSFeed(Base, TimestampMixin):
    """GTFS Feed - represents a complete GTFS dataset imported for an agency"""

    __tablename__ = "gtfs_feeds"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    agency_id: Mapped[int] = mapped_column(
        ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Feed metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Descriptive name for this feed")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="Optional version identifier")
    imported_at: Mapped[str] = mapped_column(String(30), nullable=False, comment="ISO timestamp of import")
    imported_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Whether this feed is currently active"
    )

    # Original filename for reference
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Statistics
    total_routes: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    total_stops: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    total_trips: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)

    # Relationships
    agency: Mapped["Agency"] = relationship("Agency", back_populates="gtfs_feeds")
    imported_by_user: Mapped["User | None"] = relationship("User")

    # GTFS data relationships
    routes: Mapped[List["Route"]] = relationship(
        "Route", back_populates="feed", cascade="all, delete-orphan"
    )
    stops: Mapped[List["Stop"]] = relationship(
        "Stop", back_populates="feed", cascade="all, delete-orphan"
    )
    trips: Mapped[List["Trip"]] = relationship(
        "Trip", back_populates="feed", cascade="all, delete-orphan"
    )
    calendars: Mapped[List["Calendar"]] = relationship(
        "Calendar", back_populates="feed", cascade="all, delete-orphan"
    )
    shapes: Mapped[List["Shape"]] = relationship(
        "Shape", back_populates="feed", cascade="all, delete-orphan"
    )
    fare_attributes: Mapped[List["FareAttribute"]] = relationship(
        "FareAttribute", back_populates="feed", cascade="all, delete-orphan"
    )
    fare_rules: Mapped[List["FareRule"]] = relationship(
        "FareRule", back_populates="feed", cascade="all, delete-orphan"
    )
    feed_info: Mapped["FeedInfo | None"] = relationship(
        "FeedInfo", back_populates="feed", cascade="all, delete-orphan", uselist=False
    )

    def __repr__(self) -> str:
        return f"<GTFSFeed {self.name}>"


class Stop(Base, TimestampMixin):
    """GTFS stops.txt - Transit stops/stations"""

    __tablename__ = "gtfs_stops"
    __table_args__ = (
        {"comment": "GTFS stops - uses composite PK (feed_id, stop_id)"}
    )

    # Composite primary key: (feed_id, stop_id)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("gtfs_feeds.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    stop_id: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)

    # GTFS fields
    stop_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stop_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    stop_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    stop_lat: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    stop_lon: Mapped[Decimal] = mapped_column(Numeric(11, 8), nullable=False)
    zone_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stop_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location_type: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=0, comment="0=stop, 1=station, 2=entrance, 3=node"
    )
    parent_station: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stop_timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    wheelchair_boarding: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="0=no info, 1=accessible, 2=not accessible"
    )
    tts_stop_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Text-to-speech readable stop name"
    )
    level_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Level ID within station"
    )
    platform_code: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Platform identifier (e.g., G, 3)"
    )

    # PostGIS geometry column for spatial queries
    geom: Mapped[str | None] = mapped_column(
        Geometry("POINT", srid=4326), nullable=True, comment="PostGIS geometry point"
    )

    # Custom/extension fields from GTFS
    custom_fields: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Custom/extension fields from GTFS"
    )

    # Relationships
    feed: Mapped["GTFSFeed"] = relationship("GTFSFeed", back_populates="stops")
    stop_times: Mapped[List["StopTime"]] = relationship(
        "StopTime", back_populates="stop", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Stop {self.stop_name}>"


class Route(Base, TimestampMixin):
    """GTFS routes.txt - Transit routes"""

    __tablename__ = "gtfs_routes"
    __table_args__ = (
        {"comment": "GTFS routes - uses composite PK (feed_id, route_id), also links to agency"}
    )

    # Composite primary key: (feed_id, route_id)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("gtfs_feeds.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    route_id: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)

    # Link to agency (denormalized for easier querying)
    agency_id: Mapped[int] = mapped_column(
        ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # GTFS fields
    route_short_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    route_long_name: Mapped[str] = mapped_column(String(255), nullable=False)
    route_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    route_type: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="0=Tram, 1=Subway, 2=Rail, 3=Bus, 4=Ferry, 5=Cable car, 6=Gondola, 7=Funicular",
    )
    route_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    route_color: Mapped[str | None] = mapped_column(String(6), nullable=True)
    route_text_color: Mapped[str | None] = mapped_column(String(6), nullable=True)
    route_sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # GTFS additional optional fields
    continuous_pickup: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="0=continuous, 1=none, 2=phone agency, 3=coordinate with driver"
    )
    continuous_drop_off: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="0=continuous, 1=none, 2=phone agency, 3=coordinate with driver"
    )
    network_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Identifies a group of routes for fare purposes"
    )

    # Custom/extension fields from GTFS
    custom_fields: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Custom/extension fields from GTFS"
    )

    # Relationships
    feed: Mapped["GTFSFeed"] = relationship("GTFSFeed", back_populates="routes")
    agency: Mapped["Agency"] = relationship("Agency", foreign_keys=[agency_id])
    trips: Mapped[List["Trip"]] = relationship(
        "Trip",
        back_populates="route",
        cascade="all, delete-orphan",
        overlaps="trips"
    )

    def __repr__(self) -> str:
        return f"<Route {self.route_short_name} - {self.route_long_name}>"


class Trip(Base, TimestampMixin):
    """GTFS trips.txt - Individual trips"""

    __tablename__ = "gtfs_trips"
    __table_args__ = (
        ForeignKeyConstraint(
            ['feed_id', 'route_id'],
            ['gtfs_routes.feed_id', 'gtfs_routes.route_id'],
            ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ['feed_id', 'service_id'],
            ['gtfs_calendar.feed_id', 'gtfs_calendar.service_id'],
            ondelete="CASCADE"
        ),
        {"comment": "GTFS trips - uses composite PK (feed_id, trip_id) and composite FKs"}
    )

    # Composite primary key: (feed_id, trip_id)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("gtfs_feeds.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    trip_id: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)
    # Note: id alias handled by __getattr__ method below for compatibility

    # Composite foreign key to Route (feed_id, route_id)
    route_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Composite foreign key to Calendar (feed_id, service_id)
    service_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Optional reference to Shape (feed_id, shape_id)
    # Note: We don't enforce FK constraint to shapes because shape has shape_pt_sequence in PK
    shape_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # GTFS fields
    trip_headsign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trip_short_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    direction_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="0=outbound, 1=inbound"
    )
    block_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wheelchair_accessible: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="0=no info, 1=accessible, 2=not accessible"
    )
    bikes_allowed: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="0=no info, 1=allowed, 2=not allowed"
    )
    cars_allowed: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="0=no info, 1=allowed, 2=not allowed"
    )

    # Custom/extension fields from GTFS
    custom_fields: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Custom/extension fields from GTFS"
    )

    # Relationships
    feed: Mapped["GTFSFeed"] = relationship(
        "GTFSFeed",
        back_populates="trips",
        overlaps="trips"
    )
    route: Mapped["Route"] = relationship(
        "Route",
        foreign_keys=[feed_id, route_id],
        back_populates="trips",
        overlaps="feed,trips"
    )
    service: Mapped["Calendar"] = relationship(
        "Calendar",
        foreign_keys=[feed_id, service_id],
        back_populates="trips",
        overlaps="feed,route,trips,trips"
    )
    stop_times: Mapped[List["StopTime"]] = relationship(
        "StopTime",
        back_populates="trip",
        cascade="all, delete-orphan",
        overlaps="stop_times"
    )

    def __repr__(self) -> str:
        return f"<Trip {self.trip_id}>"

    def __getattr__(self, name: str):
        """
        Compatibility shim: some legacy code still expects a surrogate numeric `id`.
        The GTFS model uses composite keys, so expose `trip_id` via `id` when requested.
        """
        if name == "id":
            return self.trip_id
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


class StopTime(Base, TimestampMixin):
    """GTFS stop_times.txt - Stop times for trips"""

    __tablename__ = "gtfs_stop_times"
    __table_args__ = (
        ForeignKeyConstraint(
            ['feed_id', 'trip_id'],
            ['gtfs_trips.feed_id', 'gtfs_trips.trip_id'],
            ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ['feed_id', 'stop_id'],
            ['gtfs_stops.feed_id', 'gtfs_stops.stop_id'],
            ondelete="CASCADE"
        ),
        {"comment": "GTFS stop_times - uses composite PK (feed_id, trip_id, stop_sequence)"}
    )

    # Composite primary key: (feed_id, trip_id, stop_sequence)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("gtfs_feeds.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    trip_id: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)
    stop_sequence: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)

    # Composite foreign key to Stop (feed_id, stop_id)
    stop_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # GTFS fields
    arrival_time: Mapped[str] = mapped_column(
        String(8), nullable=False, comment="Format: HH:MM:SS"
    )
    departure_time: Mapped[str] = mapped_column(
        String(8), nullable=False, comment="Format: HH:MM:SS"
    )
    stop_headsign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pickup_type: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=0, comment="0=regular, 1=none, 2=phone, 3=driver"
    )
    drop_off_type: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=0, comment="0=regular, 1=none, 2=phone, 3=driver"
    )
    shape_dist_traveled: Mapped[Decimal | None] = mapped_column(
        Numeric(16, 10), nullable=True, comment="Distance traveled along shape in meters (full precision)"
    )
    timepoint: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="0=approximate, 1=exact"
    )

    # Relationships
    trip: Mapped["Trip"] = relationship(
        "Trip",
        foreign_keys=[feed_id, trip_id],
        back_populates="stop_times",
        overlaps="stop_times"
    )
    stop: Mapped["Stop"] = relationship(
        "Stop",
        foreign_keys=[feed_id, stop_id],
        back_populates="stop_times",
        overlaps="stop_times,trip"
    )

    def __repr__(self) -> str:
        return f"<StopTime trip={self.trip_id} stop={self.stop_id} seq={self.stop_sequence}>"


class Calendar(Base, TimestampMixin):
    """GTFS calendar.txt - Service calendar"""

    __tablename__ = "gtfs_calendar"
    __table_args__ = (
        {"comment": "GTFS calendar - uses composite PK (feed_id, service_id)"}
    )

    # Composite primary key: (feed_id, service_id)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("gtfs_feeds.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    service_id: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)

    # GTFS fields
    monday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tuesday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    wednesday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    thursday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    friday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    saturday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sunday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    start_date: Mapped[str] = mapped_column(String(8), nullable=False, comment="YYYYMMDD")
    end_date: Mapped[str] = mapped_column(String(8), nullable=False, comment="YYYYMMDD")

    # Custom/extension fields from GTFS
    custom_fields: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Custom/extension fields from GTFS"
    )

    # Relationships
    feed: Mapped["GTFSFeed"] = relationship("GTFSFeed", back_populates="calendars")
    trips: Mapped[List["Trip"]] = relationship(
        "Trip",
        back_populates="service",
        cascade="all, delete-orphan",
        overlaps="feed,route,trips,trips"
    )
    calendar_dates: Mapped[List["CalendarDate"]] = relationship(
        "CalendarDate", back_populates="service", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Calendar {self.service_id}>"


class CalendarDate(Base, TimestampMixin):
    """GTFS calendar_dates.txt - Service exceptions"""

    __tablename__ = "gtfs_calendar_dates"
    __table_args__ = (
        ForeignKeyConstraint(
            ['feed_id', 'service_id'],
            ['gtfs_calendar.feed_id', 'gtfs_calendar.service_id'],
            ondelete="CASCADE"
        ),
        {"comment": "GTFS calendar_dates - uses composite PK (feed_id, service_id, date)"}
    )

    # Composite primary key: (feed_id, service_id, date)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("gtfs_feeds.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    service_id: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)
    date: Mapped[str] = mapped_column(String(8), primary_key=True, nullable=False, comment="YYYYMMDD")

    # GTFS fields
    exception_type: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="1=service added, 2=service removed"
    )

    # Relationships
    service: Mapped["Calendar"] = relationship(
        "Calendar",
        foreign_keys=[feed_id, service_id],
        back_populates="calendar_dates"
    )

    def __repr__(self) -> str:
        return f"<CalendarDate {self.date}>"


class Shape(Base, TimestampMixin):
    """GTFS shapes.txt - Route shapes/paths"""

    __tablename__ = "gtfs_shapes"
    __table_args__ = (
        {"comment": "GTFS shapes - uses composite PK (feed_id, shape_id, shape_pt_sequence)"}
    )

    # Composite primary key: (feed_id, shape_id, shape_pt_sequence)
    # Each shape has multiple points, so we need sequence in PK
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("gtfs_feeds.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    shape_id: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)
    shape_pt_sequence: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)

    # GTFS fields
    shape_pt_lat: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    shape_pt_lon: Mapped[Decimal] = mapped_column(Numeric(11, 8), nullable=False)
    shape_dist_traveled: Mapped[Decimal | None] = mapped_column(
        Numeric(16, 10), nullable=True, comment="Distance traveled along shape in meters (full precision)"
    )

    # PostGIS geometry column
    geom: Mapped[str | None] = mapped_column(
        Geometry("POINT", srid=4326), nullable=True, comment="PostGIS geometry point (changed from LINESTRING)"
    )

    # Relationships
    feed: Mapped["GTFSFeed"] = relationship("GTFSFeed", back_populates="shapes")

    def __repr__(self) -> str:
        return f"<Shape {self.shape_id} pt={self.shape_pt_sequence}>"


class FareAttribute(Base, TimestampMixin):
    """GTFS fare_attributes.txt - Fare information"""

    __tablename__ = "gtfs_fare_attributes"
    __table_args__ = (
        {"comment": "GTFS fare_attributes - uses composite PK (feed_id, fare_id)"}
    )

    # Composite primary key: (feed_id, fare_id)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("gtfs_feeds.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    fare_id: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)

    # GTFS fields
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency_type: Mapped[str] = mapped_column(
        String(3), nullable=False, comment="ISO 4217 currency code"
    )
    payment_method: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="0=on board, 1=before boarding"
    )
    transfers: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="0=no, 1=once, 2=twice, empty=unlimited"
    )
    agency_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transfer_duration: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Length of time in seconds before a transfer expires"
    )

    # Custom/extension fields from GTFS
    custom_fields: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Custom/extension fields from GTFS"
    )

    # Relationships
    feed: Mapped["GTFSFeed"] = relationship("GTFSFeed", back_populates="fare_attributes")

    def __repr__(self) -> str:
        return f"<FareAttribute {self.fare_id}>"


class FareRule(Base, TimestampMixin):
    """GTFS fare_rules.txt - Rules for applying fare information"""

    __tablename__ = "gtfs_fare_rules"
    __table_args__ = (
        {"comment": "GTFS fare_rules - uses composite PK with all identifying fields"}
    )

    # Composite primary key: (feed_id, fare_id, route_id, origin_id, destination_id, contains_id)
    # All fields are part of PK because fare_rules doesn't have a single unique identifier
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("gtfs_feeds.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    fare_id: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)
    route_id: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False, default="")
    origin_id: Mapped[str] = mapped_column(
        String(255), primary_key=True, nullable=False, default="", comment="Origin zone ID"
    )
    destination_id: Mapped[str] = mapped_column(
        String(255), primary_key=True, nullable=False, default="", comment="Destination zone ID"
    )
    contains_id: Mapped[str] = mapped_column(
        String(255), primary_key=True, nullable=False, default="", comment="Zone ID that must be contained in itinerary"
    )

    # Custom/extension fields from GTFS
    custom_fields: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Custom/extension fields from GTFS"
    )

    # Relationships
    feed: Mapped["GTFSFeed"] = relationship("GTFSFeed", back_populates="fare_rules")

    def __repr__(self) -> str:
        return f"<FareRule {self.fare_id}>"


class FeedInfo(Base, TimestampMixin):
    """GTFS feed_info.txt - Feed metadata"""

    __tablename__ = "gtfs_feed_info"
    __table_args__ = (
        {"comment": "GTFS feed_info - uses feed_id as PK (1-to-1 with feed)"}
    )

    # Primary key: feed_id (1-to-1 relationship with GTFSFeed)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("gtfs_feeds.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )

    # GTFS fields
    feed_publisher_name: Mapped[str] = mapped_column(String(255), nullable=False)
    feed_publisher_url: Mapped[str] = mapped_column(String(500), nullable=False)
    feed_lang: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="ISO 639-1 language code"
    )
    default_lang: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="ISO 639-1 language code"
    )
    feed_start_date: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="YYYYMMDD"
    )
    feed_end_date: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="YYYYMMDD"
    )
    feed_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    feed_contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    feed_contact_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Custom/extension fields from GTFS
    custom_fields: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Custom/extension fields from GTFS"
    )

    # Relationships
    feed: Mapped["GTFSFeed"] = relationship("GTFSFeed", back_populates="feed_info")

    def __repr__(self) -> str:
        return f"<FeedInfo {self.feed_publisher_name}>"
