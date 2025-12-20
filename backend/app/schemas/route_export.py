"""Route Export (Route Creator) schemas for API requests and responses"""

from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator
import re


class RouteExportRoute(BaseModel):
    """Route data for export"""

    route_id: str = Field(..., min_length=1, max_length=255, description="GTFS route_id")
    route_short_name: str = Field("", max_length=50, description="Short route name")
    route_long_name: Optional[str] = Field(None, max_length=255, description="Full route name")
    route_type: int = Field(3, ge=0, le=2000, description="Type of transportation (default: Bus)")
    route_color: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{6}$", description="Route color (hex, no #)")
    route_text_color: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{6}$", description="Text color (hex, no #)")
    route_desc: Optional[str] = Field(None, description="Route description")
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields")

    @field_validator("route_color", "route_text_color", mode='before')
    @classmethod
    def validate_hex_color(cls, v: Optional[str]) -> Optional[str]:
        """Validate hex color format and remove # if present"""
        if v is None or v == "":
            return None
        if v.startswith("#"):
            v = v[1:]
        if len(v) != 6:
            raise ValueError("Color must be 6 hex characters")
        return v.upper()


class RouteExportStop(BaseModel):
    """Stop data for export (new stops only)"""

    stop_id: str = Field(..., min_length=1, max_length=255, description="GTFS stop_id")
    stop_name: str = Field(..., min_length=1, max_length=255, description="Stop name")
    stop_lat: Decimal = Field(..., ge=-90, le=90, description="Latitude")
    stop_lon: Decimal = Field(..., ge=-180, le=180, description="Longitude")
    stop_code: Optional[str] = Field(None, max_length=50, description="Stop code")
    stop_desc: Optional[str] = Field(None, description="Stop description")
    wheelchair_boarding: Optional[int] = Field(0, ge=0, le=2, description="Wheelchair boarding")
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields")

    @field_validator("stop_lat", "stop_lon", mode="before")
    @classmethod
    def validate_coordinates(cls, v) -> Decimal:
        """Validate and convert coordinates to Decimal"""
        if v is None:
            return v
        if not isinstance(v, Decimal):
            v = Decimal(str(v))
        return v


class RouteExportShapePoint(BaseModel):
    """Shape point data for export"""

    lat: Decimal = Field(..., ge=-90, le=90, description="Latitude")
    lon: Decimal = Field(..., ge=-180, le=180, description="Longitude")
    sequence: int = Field(..., ge=0, description="Point sequence in shape")
    dist_traveled: Optional[Decimal] = Field(None, ge=0, description="Distance traveled")

    @field_validator("lat", "lon", "dist_traveled", mode="before")
    @classmethod
    def validate_decimal(cls, v) -> Optional[Decimal]:
        """Convert to Decimal if needed"""
        if v is None:
            return v
        if not isinstance(v, Decimal):
            v = Decimal(str(v))
        return v


class RouteExportTrip(BaseModel):
    """Trip data for export"""

    trip_id: str = Field(..., min_length=1, max_length=255, description="GTFS trip_id")
    trip_headsign: Optional[str] = Field(None, max_length=255, description="Trip headsign")
    direction_id: Optional[int] = Field(0, ge=0, le=1, description="0=outbound, 1=inbound")
    wheelchair_accessible: Optional[int] = Field(0, ge=0, le=2, description="Wheelchair accessible")
    bikes_allowed: Optional[int] = Field(0, ge=0, le=2, description="Bikes allowed")
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields")


class RouteExportStopTime(BaseModel):
    """Stop time data for export"""

    trip_id: str = Field(..., description="Reference to trip_id in trips list")
    stop_id: str = Field(..., description="GTFS stop_id (existing or new)")
    stop_sequence: int = Field(..., ge=0, description="Sequence in trip")
    arrival_time: str = Field(..., pattern=r"^\d{1,2}:\d{2}:\d{2}$", description="Arrival time HH:MM:SS")
    departure_time: str = Field(..., pattern=r"^\d{1,2}:\d{2}:\d{2}$", description="Departure time HH:MM:SS")
    stop_headsign: Optional[str] = Field(None, max_length=255, description="Stop-specific headsign")
    pickup_type: Optional[int] = Field(0, ge=0, le=3, description="Pickup type")
    drop_off_type: Optional[int] = Field(0, ge=0, le=3, description="Drop-off type")
    shape_dist_traveled: Optional[Decimal] = Field(None, ge=0, description="Distance along shape")
    timepoint: Optional[int] = Field(None, ge=0, le=1, description="Timepoint")

    @field_validator("arrival_time", "departure_time")
    @classmethod
    def validate_gtfs_time(cls, v: str) -> str:
        """Validate GTFS time format"""
        if not re.match(r"^\d{1,2}:\d{2}:\d{2}$", v):
            raise ValueError("Time must be in HH:MM:SS format")

        parts = v.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])

        if hours < 0 or hours > 48:
            raise ValueError("Hours must be between 0 and 48")
        if minutes < 0 or minutes > 59:
            raise ValueError("Minutes must be between 0 and 59")
        if seconds < 0 or seconds > 59:
            raise ValueError("Seconds must be between 0 and 59")

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class RouteExportPayload(BaseModel):
    """Complete route export payload from Route Creator"""

    # Target feed
    feed_id: int = Field(..., description="Target GTFS feed ID")

    # Service calendars for trips (GTFS service_id strings from calendar.txt)
    service_ids: List[str] = Field(..., min_length=1, description="Calendar service_id values for creating trips")

    # Route data
    route: RouteExportRoute = Field(..., description="Route to create")

    # Stops (only new stops - existing stops are referenced by stop_id in stop_times)
    new_stops: List[RouteExportStop] = Field(default_factory=list, description="New stops to create")

    # Shape (generated shape_id will be assigned)
    shape_id: str = Field(..., min_length=1, max_length=255, description="GTFS shape_id")
    shape_points: List[RouteExportShapePoint] = Field(..., min_length=2, description="Shape points")

    # Trips (one trip definition, will be duplicated for each service_id)
    trips: List[RouteExportTrip] = Field(..., min_length=1, description="Trip definitions")

    # Stop times (referenced by trip_id and stop_id strings)
    stop_times: List[RouteExportStopTime] = Field(..., min_length=1, description="Stop times for each trip")


class RouteExportRequest(BaseModel):
    """Request to start route export task"""

    payload: RouteExportPayload = Field(..., description="Route export data")


class RouteExportTaskResponse(BaseModel):
    """Response when starting route export task"""

    task_id: int = Field(..., description="Database task ID for tracking")
    celery_task_id: str = Field(..., description="Celery task ID")
    message: str = Field(..., description="Status message")


class RouteExportResult(BaseModel):
    """Result of route export operation"""

    route_id: str = Field(..., description="GTFS route_id")
    feed_id: int = Field(..., description="Feed ID")
    stops_created: int = Field(0, description="Number of new stops created")
    stops_linked: int = Field(0, description="Number of existing stops linked")
    shape_points_created: int = Field(0, description="Number of shape points created")
    trips_created: int = Field(0, description="Number of trips created")
    stop_times_created: int = Field(0, description="Number of stop times created")
    warnings: List[str] = Field(default_factory=list, description="Non-blocking warnings")


class RouteExportValidation(BaseModel):
    """Pre-export validation result"""

    valid: bool = Field(..., description="Whether payload is valid for export")
    errors: List[str] = Field(default_factory=list, description="Blocking errors")
    warnings: List[str] = Field(default_factory=list, description="Non-blocking warnings")
    summary: Dict[str, Any] = Field(default_factory=dict, description="Data summary for confirmation")
