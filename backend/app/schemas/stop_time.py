"""StopTime (GTFS) schemas for API requests and responses"""

from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
import re


class StopTimeBase(BaseModel):
    """Base stop time schema"""

    arrival_time: str = Field(..., pattern=r"^\d{1,2}:\d{2}:\d{2}$", description="Arrival time (HH:MM:SS, can exceed 24)")
    departure_time: str = Field(..., pattern=r"^\d{1,2}:\d{2}:\d{2}$", description="Departure time (HH:MM:SS, can exceed 24)")
    stop_sequence: int = Field(..., ge=0, description="Order of stop in trip (0-based)")
    stop_headsign: Optional[str] = Field(None, max_length=255, description="Headsign for this stop")
    pickup_type: Optional[int] = Field(
        0, ge=0, le=3, description="0=regular, 1=none, 2=phone, 3=driver"
    )
    drop_off_type: Optional[int] = Field(
        0, ge=0, le=3, description="0=regular, 1=none, 2=phone, 3=driver"
    )
    shape_dist_traveled: Optional[Decimal] = Field(None, ge=0, description="Distance from first stop")
    timepoint: Optional[int] = Field(None, ge=0, le=1, description="0=approximate, 1=exact")

    @field_validator("arrival_time", "departure_time")
    @classmethod
    def validate_gtfs_time(cls, v: str) -> str:
        """Validate GTFS time format (HH:MM:SS, can exceed 24 hours)"""
        if not re.match(r"^\d{1,2}:\d{2}:\d{2}$", v):
            raise ValueError("Time must be in HH:MM:SS format")

        parts = v.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])

        # GTFS allows hours > 24 for trips that continue past midnight
        if hours < 0 or hours > 48:
            raise ValueError("Hours must be between 0 and 48")
        if minutes < 0 or minutes > 59:
            raise ValueError("Minutes must be between 0 and 59")
        if seconds < 0 or seconds > 59:
            raise ValueError("Seconds must be between 0 and 59")

        # Ensure two-digit formatting for consistency
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @field_validator("departure_time")
    @classmethod
    def validate_time_order(cls, v: str, info) -> str:
        """Ensure departure_time >= arrival_time"""
        if "arrival_time" in info.data:
            arrival = info.data["arrival_time"]
            # Simple string comparison works for HH:MM:SS format
            if v < arrival:
                raise ValueError("departure_time must be >= arrival_time")
        return v


class StopTimeCreate(StopTimeBase):
    """Schema for creating a new stop time"""

    feed_id: int = Field(..., description="Feed ID")
    trip_id: str = Field(..., description="GTFS trip_id")
    stop_id: str = Field(..., description="GTFS stop_id")


class StopTimeUpdate(BaseModel):
    """Schema for updating a stop time"""

    arrival_time: Optional[str] = Field(None, pattern=r"^\d{1,2}:\d{2}:\d{2}$")
    departure_time: Optional[str] = Field(None, pattern=r"^\d{1,2}:\d{2}:\d{2}$")
    stop_sequence: Optional[int] = Field(None, ge=0)
    stop_id: Optional[str] = None
    stop_headsign: Optional[str] = Field(None, max_length=255)
    pickup_type: Optional[int] = Field(None, ge=0, le=3)
    drop_off_type: Optional[int] = Field(None, ge=0, le=3)
    shape_dist_traveled: Optional[Decimal] = Field(None, ge=0)
    timepoint: Optional[int] = Field(None, ge=0, le=1)


class StopTimeResponse(StopTimeBase):
    """Schema for stop time response"""

    feed_id: int
    trip_id: str
    stop_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StopTimeWithStop(StopTimeResponse):
    """Stop time with stop information"""

    stop_name: str = Field(..., description="Stop name")
    stop_code: Optional[str] = None
    stop_lat: Decimal
    stop_lon: Decimal


class StopTimeWithDetails(StopTimeWithStop):
    """Stop time with full details including trip info"""

    trip_headsign: Optional[str] = None
    route_short_name: Optional[str] = None
    route_long_name: Optional[str] = None
    route_color: Optional[str] = None
    gtfs_trip_id: Optional[str] = None
    gtfs_route_id: Optional[str] = None


# Bulk operations


class StopTimesBulkCreate(BaseModel):
    """Schema for creating multiple stop times for a trip"""

    feed_id: int = Field(..., description="Feed ID")
    trip_id: str = Field(..., description="GTFS trip_id")

    class StopTimeWithStopId(StopTimeBase):
        stop_id: str = Field(..., description="GTFS stop_id")

    stop_times: List[StopTimeWithStopId] = Field(..., description="Stop times in sequence")


class StopTimesBulkUpdate(BaseModel):
    """Schema for updating multiple stop times"""

    stop_times: List[StopTimeUpdate] = Field(..., description="Stop times to update (by ID)")


class StopTimeBulkResult(BaseModel):
    """Result of bulk stop time operation"""

    created: int = Field(default=0, description="Number of stop times created")
    updated: int = Field(default=0, description="Number of stop times updated")
    deleted: int = Field(default=0, description="Number of stop times deleted")
    errors: List[str] = Field(default_factory=list, description="List of errors")


# List schemas


class StopTimeList(BaseModel):
    """List of stop times"""

    items: List[StopTimeResponse] = Field(..., description="List of stop times")
    total: int = Field(..., description="Total number of stop times")


class StopTimeListWithStop(BaseModel):
    """List of stop times with stop information"""

    items: List[StopTimeWithStop] = Field(..., description="Stop times with stop info")
    total: int = Field(..., description="Total number of stop times")


class StopTimeListWithDetails(BaseModel):
    """List of stop times with full details"""

    items: List[StopTimeWithDetails] = Field(..., description="Stop times with full details")
    total: int = Field(..., description="Total number of stop times")


# Time adjustment


class StopTimeAdjustment(BaseModel):
    """Schema for adjusting all times in a trip"""

    minutes_offset: int = Field(..., description="Minutes to add/subtract from all times")


# Validation helpers


class StopTimeValidation(BaseModel):
    """Validation result for stop times"""

    valid: bool = Field(..., description="Whether stop times are valid")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")


# Import/Export


class StopTimeImport(BaseModel):
    """Schema for importing stop times"""

    stop_times: List[StopTimeCreate] = Field(..., description="Stop times to import")
    replace_existing: bool = Field(default=False, description="Replace existing stop times for trips")


class StopTimeImportResult(BaseModel):
    """Result of stop time import"""

    created: int = Field(..., description="Number created")
    updated: int = Field(..., description="Number updated")
    skipped: int = Field(..., description="Number skipped")
    errors: List[str] = Field(default_factory=list, description="Errors encountered")
