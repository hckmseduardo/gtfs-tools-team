"""Trip (GTFS) schemas for API requests and responses"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class TripBase(BaseModel):
    """Base trip schema"""

    trip_id: str = Field(..., min_length=1, max_length=255, description="GTFS trip_id")
    trip_headsign: Optional[str] = Field(None, max_length=255, description="Text that appears on signage")
    trip_short_name: Optional[str] = Field(None, max_length=50, description="Short name for trip")
    direction_id: Optional[int] = Field(None, ge=0, le=1, description="0=outbound, 1=inbound")
    block_id: Optional[str] = Field(None, max_length=50, description="Block ID for vehicle operations")
    wheelchair_accessible: Optional[int] = Field(
        0, ge=0, le=2, description="0=no info, 1=accessible, 2=not accessible"
    )
    bikes_allowed: Optional[int] = Field(
        0, ge=0, le=2, description="0=no info, 1=allowed, 2=not allowed"
    )
    cars_allowed: Optional[int] = Field(
        0, ge=0, le=2, description="0=no info, 1=allowed, 2=not allowed"
    )
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields from GTFS")


class TripCreate(TripBase):
    """Schema for creating a new trip"""

    feed_id: int = Field(..., description="Feed ID this trip belongs to")
    route_id: str = Field(..., description="GTFS route_id for this trip")
    service_id: str = Field(..., description="GTFS service_id (Calendar)")
    shape_id: Optional[str] = Field(None, description="GTFS shape_id (optional)")


class TripUpdate(BaseModel):
    """Schema for updating a trip"""

    trip_id: Optional[str] = Field(None, min_length=1, max_length=255)
    route_id: Optional[str] = None
    service_id: Optional[str] = None
    trip_headsign: Optional[str] = Field(None, max_length=255)
    trip_short_name: Optional[str] = Field(None, max_length=50)
    direction_id: Optional[int] = Field(None, ge=0, le=1)
    block_id: Optional[str] = Field(None, max_length=50)
    shape_id: Optional[str] = None
    wheelchair_accessible: Optional[int] = Field(None, ge=0, le=2)
    bikes_allowed: Optional[int] = Field(None, ge=0, le=2)
    cars_allowed: Optional[int] = Field(None, ge=0, le=2)
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields from GTFS")


class TripResponse(TripBase):
    """Schema for trip response"""

    feed_id: int
    route_id: str
    service_id: str
    shape_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TripWithRoute(TripResponse):
    """Trip response with route information"""

    gtfs_route_id: str = Field(..., description="GTFS route_id identifier")
    gtfs_shape_id: Optional[str] = Field(None, description="GTFS shape_id identifier")
    route_short_name: str = Field(..., description="Route short name")
    route_long_name: str = Field(..., description="Route long name")
    route_type: int = Field(..., description="Route type")
    route_color: Optional[str] = None


class TripWithDetails(TripWithRoute):
    """Trip response with full details including stop count"""

    stop_count: int = Field(default=0, description="Number of stops in this trip")
    first_departure: Optional[str] = Field(None, description="First departure time (HH:MM:SS)")
    last_arrival: Optional[str] = Field(None, description="Last arrival time (HH:MM:SS)")


# Stop Time reference (minimal, for trip details)


class TripStopTimeReference(BaseModel):
    """Minimal stop time reference for trip listings"""

    stop_id: str
    stop_name: str
    stop_sequence: int
    arrival_time: str
    departure_time: str


class TripWithStopTimes(TripWithRoute):
    """Trip with all stop times"""

    stop_times: List[TripStopTimeReference] = Field(
        default_factory=list, description="All stop times for this trip"
    )


# List and pagination schemas


class TripList(BaseModel):
    """Paginated list of trips"""

    items: List[TripResponse] = Field(..., description="List of trips")
    total: int = Field(..., description="Total number of trips")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


class TripListWithRoute(BaseModel):
    """Paginated list of trips with route info"""

    items: List[TripWithRoute] = Field(..., description="List of trips with route info")
    total: int = Field(..., description="Total number of trips")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


class TripListWithDetails(BaseModel):
    """Paginated list of trips with full details"""

    items: List[TripWithDetails] = Field(..., description="List of trips with details")
    total: int = Field(..., description="Total number of trips")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


# Bulk operations


class TripImport(BaseModel):
    """Schema for importing trips from GTFS"""

    trips: List[TripCreate] = Field(..., description="List of trips to import")
    replace_existing: bool = Field(default=False, description="Replace existing trips with same trip_id")


class TripImportResult(BaseModel):
    """Result of trip import operation"""

    created: int = Field(..., description="Number of trips created")
    updated: int = Field(..., description="Number of trips updated")
    skipped: int = Field(..., description="Number of trips skipped")
    errors: List[str] = Field(default_factory=list, description="List of errors encountered")


# Trip copying


class TripCopy(BaseModel):
    """Schema for copying a trip"""

    new_trip_id: str = Field(..., min_length=1, max_length=255, description="New trip ID")
    copy_stop_times: bool = Field(default=True, description="Also copy all stop times")
