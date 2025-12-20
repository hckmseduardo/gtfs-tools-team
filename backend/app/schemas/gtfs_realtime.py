"""Pydantic schemas for GTFS-Realtime data"""

from typing import Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class VehiclePositionBase(BaseModel):
    """Base schema for vehicle position"""
    vehicle_id: str
    vehicle_label: Optional[str] = None
    license_plate: Optional[str] = None
    latitude: float
    longitude: float
    bearing: Optional[float] = None
    speed: Optional[float] = None
    odometer: Optional[float] = None
    trip_id: Optional[str] = None
    route_id: Optional[str] = None
    direction_id: Optional[int] = None
    start_time: Optional[str] = None
    start_date: Optional[str] = None
    schedule_relationship: Optional[str] = None
    current_stop_sequence: Optional[int] = None
    stop_id: Optional[str] = None
    current_status: Optional[str] = None
    congestion_level: Optional[str] = None
    occupancy_status: Optional[str] = None
    occupancy_percentage: Optional[int] = None
    timestamp: Optional[int] = None


class VehiclePositionResponse(VehiclePositionBase):
    """Response schema for vehicle position"""
    id: int
    feed_source_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VehiclePositionMapResponse(BaseModel):
    """Simplified response for map display"""
    id: int
    vehicle_id: str
    vehicle_label: Optional[str] = None
    latitude: float
    longitude: float
    bearing: Optional[float] = None
    speed: Optional[float] = None
    route_id: Optional[str] = None
    trip_id: Optional[str] = None
    current_status: Optional[str] = None
    occupancy_status: Optional[str] = None
    timestamp: Optional[int] = None
    # Additional fields for display
    route_short_name: Optional[str] = None
    route_color: Optional[str] = None
    headsign: Optional[str] = None

    class Config:
        from_attributes = True


class VehiclePositionListResponse(BaseModel):
    """List response for vehicle positions"""
    items: list[VehiclePositionResponse]
    total: int


class TripUpdateBase(BaseModel):
    """Base schema for trip update"""
    trip_id: str
    route_id: Optional[str] = None
    direction_id: Optional[int] = None
    start_time: Optional[str] = None
    start_date: Optional[str] = None
    schedule_relationship: Optional[str] = None
    vehicle_id: Optional[str] = None
    vehicle_label: Optional[str] = None
    delay: Optional[int] = None
    timestamp: Optional[int] = None


class TripUpdateResponse(TripUpdateBase):
    """Response schema for trip update"""
    id: int
    feed_source_id: int
    raw_data: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TripUpdateListResponse(BaseModel):
    """List response for trip updates"""
    items: list[TripUpdateResponse]
    total: int


class StopTimeUpdate(BaseModel):
    """Stop time update within a trip update"""
    stop_sequence: Optional[int] = None
    stop_id: Optional[str] = None
    arrival_delay: Optional[int] = None
    arrival_time: Optional[int] = None
    departure_delay: Optional[int] = None
    departure_time: Optional[int] = None
    schedule_relationship: Optional[str] = None


class AlertBase(BaseModel):
    """Base schema for alert"""
    alert_id: str
    active_period_start: Optional[int] = None
    active_period_end: Optional[int] = None
    informed_entities: Optional[list[dict[str, Any]]] = None
    cause: Optional[str] = None
    effect: Optional[str] = None
    severity_level: Optional[str] = None
    header_text: Optional[dict[str, str]] = None
    description_text: Optional[dict[str, str]] = None
    url: Optional[str] = None


class AlertResponse(AlertBase):
    """Response schema for alert"""
    id: int
    feed_source_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AlertListResponse(BaseModel):
    """List response for alerts"""
    items: list[AlertResponse]
    total: int


class RealtimeFeedStatus(BaseModel):
    """Status of a GTFS-RT feed"""
    feed_source_id: int
    feed_source_name: str
    feed_type: str
    last_updated: Optional[datetime] = None
    vehicle_count: int = 0
    trip_update_count: int = 0
    alert_count: int = 0
    is_active: bool = True
    error_message: Optional[str] = None


class RealtimeOverview(BaseModel):
    """Overview of all real-time data for an agency"""
    agency_id: int
    total_vehicles: int = 0
    total_trip_updates: int = 0
    total_alerts: int = 0
    total_trip_modifications: int = 0
    total_shapes: int = 0
    total_stops: int = 0
    feeds: list[RealtimeFeedStatus] = []


# Trip Modifications schemas (for detours, service changes, etc.)
class ModifiedStop(BaseModel):
    """A stop that has been modified (added, removed, or changed)"""
    stop_id: Optional[str] = None
    stop_sequence: Optional[int] = None
    travel_time_to_stop: Optional[int] = None  # seconds from previous stop
    stop_time_properties: Optional[dict[str, Any]] = None


class ReplacementStop(BaseModel):
    """A replacement stop in a trip modification"""
    stop_id: Optional[str] = None
    travel_time_to_stop: Optional[int] = None
    stop_time_properties: Optional[dict[str, Any]] = None


class StopSelector(BaseModel):
    """Selector for identifying which stops are affected"""
    stop_sequence: Optional[int] = None
    stop_id: Optional[str] = None


class TripModificationBase(BaseModel):
    """Base schema for trip modification (detours, service changes)"""
    modification_id: str
    trip_id: Optional[str] = None
    route_id: Optional[str] = None
    direction_id: Optional[int] = None
    start_time: Optional[str] = None
    start_date: Optional[str] = None
    service_dates: Optional[list[str]] = None  # Dates when this modification applies

    # Modification details
    modifications: Optional[list[dict[str, Any]]] = None  # Raw modification objects

    # Affected stops (stops that are skipped or modified)
    affected_stop_ids: Optional[list[str]] = None

    # Replacement stops (new stops added as detour)
    replacement_stops: Optional[list[dict[str, Any]]] = None

    # Propagated delays
    propagated_modification_delay: Optional[int] = None  # seconds

    timestamp: Optional[int] = None


class TripModificationResponse(TripModificationBase):
    """Response schema for trip modification"""
    id: int
    feed_source_id: int
    raw_data: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TripModificationListResponse(BaseModel):
    """List response for trip modifications"""
    items: list[TripModificationResponse]
    total: int


class TripModificationMapData(BaseModel):
    """Trip modification data formatted for map display"""
    modification_id: str
    trip_id: Optional[str] = None
    route_id: Optional[str] = None
    route_short_name: Optional[str] = None
    route_color: Optional[str] = None

    # Affected stops with coordinates for map display
    affected_stops: list[dict[str, Any]] = []  # [{stop_id, stop_name, lat, lon, action: 'skipped'|'modified'}]

    # Replacement path for detour visualization
    replacement_path: list[dict[str, float]] = []  # [{lat, lon}, ...]

    # Time info
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    service_dates: Optional[list[str]] = None

    # Description
    description: Optional[str] = None

    feed_source_name: Optional[str] = None


# Real-time Shapes schemas (for modified/detour shapes)
class ShapePoint(BaseModel):
    """A single point in a shape"""
    lat: float
    lon: float
    sequence: Optional[int] = None
    dist_traveled: Optional[float] = None


class RealtimeShapeBase(BaseModel):
    """Base schema for real-time shape"""
    shape_id: str
    encoded_polyline: Optional[str] = None
    shape_points: Optional[list[dict[str, Any]]] = None
    modification_id: Optional[str] = None
    trip_id: Optional[str] = None
    route_id: Optional[str] = None
    timestamp: Optional[int] = None


class RealtimeShapeResponse(RealtimeShapeBase):
    """Response schema for real-time shape"""
    id: int
    feed_source_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RealtimeShapeListResponse(BaseModel):
    """List response for real-time shapes"""
    items: list[RealtimeShapeResponse]
    total: int


class RealtimeShapeMapResponse(BaseModel):
    """Real-time shape formatted for map display"""
    shape_id: str
    points: list[ShapePoint] = []  # Decoded points for map rendering
    modification_id: Optional[str] = None
    route_id: Optional[str] = None
    route_short_name: Optional[str] = None
    route_color: Optional[str] = None
    feed_source_name: Optional[str] = None


# Real-time Stops schemas (for replacement/modified stops)
class RealtimeStopBase(BaseModel):
    """Base schema for real-time stop"""
    stop_id: str
    stop_name: Optional[str] = None
    stop_lat: Optional[float] = None
    stop_lon: Optional[float] = None
    stop_code: Optional[str] = None
    stop_desc: Optional[str] = None
    zone_id: Optional[str] = None
    stop_url: Optional[str] = None
    location_type: Optional[int] = None
    parent_station: Optional[str] = None
    wheelchair_boarding: Optional[int] = None
    platform_code: Optional[str] = None
    modification_id: Optional[str] = None
    route_id: Optional[str] = None
    is_replacement: bool = True
    timestamp: Optional[int] = None


class RealtimeStopResponse(RealtimeStopBase):
    """Response schema for real-time stop"""
    id: int
    feed_source_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RealtimeStopListResponse(BaseModel):
    """List response for real-time stops"""
    items: list[RealtimeStopResponse]
    total: int


class RealtimeStopMapResponse(BaseModel):
    """Real-time stop formatted for map display"""
    stop_id: str
    stop_name: Optional[str] = None
    stop_lat: Optional[float] = None
    stop_lon: Optional[float] = None
    stop_code: Optional[str] = None
    modification_id: Optional[str] = None
    route_id: Optional[str] = None
    route_short_name: Optional[str] = None
    route_color: Optional[str] = None
    is_replacement: bool = True
    wheelchair_boarding: Optional[int] = None
    feed_source_name: Optional[str] = None


# Updated AllRealtimeResponse to include shapes and stops
class AllRealtimeResponseExtended(BaseModel):
    """Extended response combining all real-time data types including shapes and stops"""
    agency_id: int
    timestamp: str

    # Standard GTFS-RT feeds
    vehicles: list[dict[str, Any]] = []
    vehicle_count: int = 0
    trip_updates: list[dict[str, Any]] = []
    trip_update_count: int = 0
    alerts: list[dict[str, Any]] = []
    alert_count: int = 0
    trip_modifications: list[dict[str, Any]] = []
    trip_modification_count: int = 0

    # New experimental feeds for trip modifications
    shapes: list[dict[str, Any]] = []
    shape_count: int = 0
    stops: list[dict[str, Any]] = []
    stop_count: int = 0

    errors: Optional[list[dict[str, str]]] = None
    message: Optional[str] = None
