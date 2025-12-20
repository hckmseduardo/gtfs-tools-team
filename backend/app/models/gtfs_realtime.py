"""GTFS-Realtime data models for storing real-time transit information"""

from typing import Any, Optional
import enum
from sqlalchemy import String, Integer, Float, ForeignKey, Text, JSON, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin


class VehicleStopStatus(str, enum.Enum):
    """Vehicle stop status from GTFS-RT"""
    INCOMING_AT = "incoming_at"
    STOPPED_AT = "stopped_at"
    IN_TRANSIT_TO = "in_transit_to"


class CongestionLevel(str, enum.Enum):
    """Congestion level from GTFS-RT"""
    UNKNOWN = "unknown"
    RUNNING_SMOOTHLY = "running_smoothly"
    STOP_AND_GO = "stop_and_go"
    CONGESTION = "congestion"
    SEVERE_CONGESTION = "severe_congestion"


class OccupancyStatus(str, enum.Enum):
    """Occupancy status from GTFS-RT"""
    EMPTY = "empty"
    MANY_SEATS_AVAILABLE = "many_seats_available"
    FEW_SEATS_AVAILABLE = "few_seats_available"
    STANDING_ROOM_ONLY = "standing_room_only"
    CRUSHED_STANDING_ROOM_ONLY = "crushed_standing_room_only"
    FULL = "full"
    NOT_ACCEPTING_PASSENGERS = "not_accepting_passengers"


class AlertCause(str, enum.Enum):
    """Alert cause from GTFS-RT"""
    UNKNOWN_CAUSE = "unknown_cause"
    OTHER_CAUSE = "other_cause"
    TECHNICAL_PROBLEM = "technical_problem"
    STRIKE = "strike"
    DEMONSTRATION = "demonstration"
    ACCIDENT = "accident"
    HOLIDAY = "holiday"
    WEATHER = "weather"
    MAINTENANCE = "maintenance"
    CONSTRUCTION = "construction"
    POLICE_ACTIVITY = "police_activity"
    MEDICAL_EMERGENCY = "medical_emergency"


class AlertEffect(str, enum.Enum):
    """Alert effect from GTFS-RT"""
    NO_SERVICE = "no_service"
    REDUCED_SERVICE = "reduced_service"
    SIGNIFICANT_DELAYS = "significant_delays"
    DETOUR = "detour"
    ADDITIONAL_SERVICE = "additional_service"
    MODIFIED_SERVICE = "modified_service"
    OTHER_EFFECT = "other_effect"
    UNKNOWN_EFFECT = "unknown_effect"
    STOP_MOVED = "stop_moved"
    NO_EFFECT = "no_effect"
    ACCESSIBILITY_ISSUE = "accessibility_issue"


class RealtimeVehiclePosition(Base, TimestampMixin):
    """
    Real-time vehicle position from GTFS-RT VehiclePositions feed.

    This table stores the latest position for each vehicle, updated
    periodically from the GTFS-RT feed.
    """

    __tablename__ = "realtime_vehicle_positions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Feed source reference
    feed_source_id: Mapped[int] = mapped_column(
        ForeignKey("external_feed_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Vehicle identification
    vehicle_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        comment="Vehicle ID from the feed"
    )
    vehicle_label: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="User-visible label (e.g., vehicle number)"
    )
    license_plate: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="License plate of the vehicle"
    )

    # Position
    latitude: Mapped[float] = mapped_column(
        Float, nullable=False,
        comment="Current latitude"
    )
    longitude: Mapped[float] = mapped_column(
        Float, nullable=False,
        comment="Current longitude"
    )
    bearing: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Bearing in degrees (0=North, 90=East)"
    )
    speed: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Speed in meters/second"
    )
    odometer: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Odometer value in meters"
    )

    # Trip information
    trip_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
        comment="GTFS trip_id this vehicle is serving"
    )
    route_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
        comment="GTFS route_id this vehicle is serving"
    )
    direction_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Direction of travel (0 or 1)"
    )
    start_time: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="Scheduled start time of the trip"
    )
    start_date: Mapped[str | None] = mapped_column(
        String(10), nullable=True,
        comment="Start date of the trip (YYYYMMDD)"
    )
    schedule_relationship: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="SCHEDULED, ADDED, UNSCHEDULED, CANCELED"
    )

    # Current stop
    current_stop_sequence: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Current stop sequence"
    )
    stop_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Current or next stop ID"
    )
    current_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="INCOMING_AT, STOPPED_AT, IN_TRANSIT_TO"
    )

    # Additional info
    congestion_level: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Congestion level"
    )
    occupancy_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Occupancy status"
    )
    occupancy_percentage: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Occupancy percentage (0-100)"
    )

    # Timestamp from the feed
    timestamp: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="POSIX timestamp from the vehicle position"
    )

    # Raw data for debugging
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True,
        comment="Raw data from GTFS-RT for debugging"
    )

    __table_args__ = (
        Index('ix_vehicle_positions_feed_vehicle', 'feed_source_id', 'vehicle_id', unique=True),
    )

    def __repr__(self) -> str:
        return f"<VehiclePosition {self.vehicle_id} at ({self.latitude}, {self.longitude})>"


class RealtimeTripUpdate(Base, TimestampMixin):
    """
    Real-time trip updates from GTFS-RT TripUpdates feed.

    Stores delay information and schedule changes for trips.
    """

    __tablename__ = "realtime_trip_updates"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Feed source reference
    feed_source_id: Mapped[int] = mapped_column(
        ForeignKey("external_feed_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Trip identification
    trip_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        comment="GTFS trip_id"
    )
    route_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
        comment="GTFS route_id"
    )
    direction_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Direction of travel"
    )
    start_time: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="Scheduled start time"
    )
    start_date: Mapped[str | None] = mapped_column(
        String(10), nullable=True,
        comment="Start date (YYYYMMDD)"
    )
    schedule_relationship: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="SCHEDULED, ADDED, UNSCHEDULED, CANCELED, REPLACEMENT"
    )

    # Vehicle info
    vehicle_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Vehicle ID serving this trip"
    )
    vehicle_label: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Vehicle label"
    )

    # Overall delay
    delay: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Current delay in seconds (positive = late)"
    )

    # Timestamp
    timestamp: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="POSIX timestamp of this update"
    )

    # Raw data
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True,
        comment="Raw data including stop_time_updates"
    )

    __table_args__ = (
        Index('ix_trip_updates_feed_trip', 'feed_source_id', 'trip_id', unique=True),
    )

    def __repr__(self) -> str:
        return f"<TripUpdate {self.trip_id} delay={self.delay}s>"


class RealtimeAlert(Base, TimestampMixin):
    """
    Service alerts from GTFS-RT Alerts feed.

    Stores information about disruptions, delays, and other service notices.
    """

    __tablename__ = "realtime_alerts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Feed source reference
    feed_source_id: Mapped[int] = mapped_column(
        ForeignKey("external_feed_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Alert identification
    alert_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        comment="Unique alert ID from the feed"
    )

    # Active period
    active_period_start: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Start of active period (POSIX timestamp)"
    )
    active_period_end: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="End of active period (POSIX timestamp)"
    )

    # Affected entities (stored as JSON array)
    informed_entities: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True,
        comment="List of affected agencies, routes, stops, trips"
    )

    # Alert details
    cause: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Alert cause"
    )
    effect: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Alert effect"
    )
    severity_level: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="INFO, WARNING, SEVERE"
    )

    # Text content (stored as JSON for multi-language support)
    header_text: Mapped[dict[str, str] | None] = mapped_column(
        JSON, nullable=True,
        comment="Alert header in multiple languages"
    )
    description_text: Mapped[dict[str, str] | None] = mapped_column(
        JSON, nullable=True,
        comment="Alert description in multiple languages"
    )
    url: Mapped[str | None] = mapped_column(
        String(2000), nullable=True,
        comment="URL for more information"
    )

    # Raw data
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True,
        comment="Raw alert data"
    )

    __table_args__ = (
        Index('ix_alerts_feed_alert', 'feed_source_id', 'alert_id', unique=True),
    )

    def __repr__(self) -> str:
        return f"<Alert {self.alert_id} effect={self.effect}>"


class RealtimeTripModification(Base, TimestampMixin):
    """
    Trip modifications from GTFS-RT TripModifications feed (experimental).

    Stores information about detours, modified stops, and service changes.
    This is an experimental GTFS-RT extension for communicating about
    trip modifications such as detours.
    """

    __tablename__ = "realtime_trip_modifications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Feed source reference
    feed_source_id: Mapped[int] = mapped_column(
        ForeignKey("external_feed_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Modification identification
    modification_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        comment="Unique modification ID"
    )

    # Trip identification (which trip(s) are affected)
    trip_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
        comment="GTFS trip_id (if single trip)"
    )
    route_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
        comment="GTFS route_id"
    )
    direction_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Direction of travel"
    )
    start_time: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="Start time of affected trips"
    )
    start_date: Mapped[str | None] = mapped_column(
        String(10), nullable=True,
        comment="Start date (YYYYMMDD)"
    )

    # Service dates when this modification applies
    service_dates: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True,
        comment="List of dates when this modification applies (YYYYMMDD format)"
    )

    # Affected stops (stop_ids that are skipped/modified)
    affected_stop_ids: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True,
        comment="List of stop_ids that are affected (skipped, modified, etc.)"
    )

    # Replacement stops (new stops added as part of detour)
    replacement_stops: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True,
        comment="List of replacement stops with properties"
    )

    # Modifications detail (array of modification objects)
    modifications: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True,
        comment="Detailed modification objects from GTFS-RT"
    )

    # Propagated delay caused by the modification
    propagated_modification_delay: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Delay in seconds caused by this modification"
    )

    # Timestamp
    timestamp: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="POSIX timestamp of this update"
    )

    # Raw data for debugging
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True,
        comment="Raw GTFS-RT TripModifications data"
    )

    __table_args__ = (
        Index('ix_trip_mods_feed_mod', 'feed_source_id', 'modification_id', unique=True),
        Index('ix_trip_mods_route', 'route_id'),
    )

    def __repr__(self) -> str:
        return f"<TripModification {self.modification_id} route={self.route_id}>"


class RealtimeShape(Base, TimestampMixin):
    """
    Real-time shapes from GTFS-RT Shapes feed (experimental).

    Stores modified/replacement shapes for trip modifications such as detours.
    These shapes are temporary route paths that override the static GTFS shapes.
    """

    __tablename__ = "realtime_shapes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Feed source reference
    feed_source_id: Mapped[int] = mapped_column(
        ForeignKey("external_feed_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Shape identification
    shape_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        comment="Unique shape ID from the feed"
    )

    # Encoded polyline (for efficient storage of shape points)
    encoded_polyline: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Encoded polyline string for the shape"
    )

    # Shape points as JSON array (alternative to encoded polyline)
    shape_points: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True,
        comment="Array of {lat, lon, sequence, dist_traveled} points"
    )

    # Associated modification/trip info
    modification_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
        comment="Associated trip modification ID"
    )
    trip_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
        comment="Associated trip ID"
    )
    route_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
        comment="Associated route ID"
    )

    # Timestamp
    timestamp: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="POSIX timestamp of this update"
    )

    # Raw data for debugging
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True,
        comment="Raw GTFS-RT shape data"
    )

    __table_args__ = (
        Index('ix_rt_shapes_feed_shape', 'feed_source_id', 'shape_id', unique=True),
    )

    def __repr__(self) -> str:
        return f"<RealtimeShape {self.shape_id}>"


class RealtimeStop(Base, TimestampMixin):
    """
    Real-time stops from GTFS-RT Stops feed (experimental).

    Stores modified/replacement stops for trip modifications.
    These stops are temporary stop locations used during detours or service changes.
    """

    __tablename__ = "realtime_stops"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Feed source reference
    feed_source_id: Mapped[int] = mapped_column(
        ForeignKey("external_feed_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Stop identification
    stop_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        comment="Unique stop ID from the feed"
    )

    # Stop location
    stop_name: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Name of the stop"
    )
    stop_lat: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Latitude of the stop"
    )
    stop_lon: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Longitude of the stop"
    )

    # Stop details
    stop_code: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Short code for the stop"
    )
    stop_desc: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Description of the stop"
    )
    zone_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Fare zone ID"
    )
    stop_url: Mapped[str | None] = mapped_column(
        String(2000), nullable=True,
        comment="URL for stop information"
    )
    location_type: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="0=stop, 1=station, 2=entrance/exit"
    )
    parent_station: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Parent station stop_id"
    )
    wheelchair_boarding: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Wheelchair boarding: 0=unknown, 1=accessible, 2=not accessible"
    )
    platform_code: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Platform identifier"
    )

    # Associated modification info
    modification_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
        comment="Associated trip modification ID"
    )
    route_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
        comment="Associated route ID"
    )

    # Is this a temporary/replacement stop?
    is_replacement: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Whether this is a temporary replacement stop"
    )

    # Timestamp
    timestamp: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="POSIX timestamp of this update"
    )

    # Raw data for debugging
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True,
        comment="Raw GTFS-RT stop data"
    )

    __table_args__ = (
        Index('ix_rt_stops_feed_stop', 'feed_source_id', 'stop_id', unique=True),
    )

    def __repr__(self) -> str:
        return f"<RealtimeStop {self.stop_id} '{self.stop_name}'>"
