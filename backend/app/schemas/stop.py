"""Stop (GTFS) schemas for API requests and responses"""

from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class StopBase(BaseModel):
    """Base stop schema"""

    stop_id: str = Field(..., min_length=1, max_length=255, description="GTFS stop_id")
    stop_name: str = Field(..., min_length=1, max_length=255, description="Stop name")
    stop_code: Optional[str] = Field(None, max_length=50, description="Stop code (for passengers)")
    stop_desc: Optional[str] = Field(None, description="Stop description")
    stop_lat: Decimal = Field(..., ge=-90, le=90, description="Latitude (WGS84)")
    stop_lon: Decimal = Field(..., ge=-180, le=180, description="Longitude (WGS84)")
    zone_id: Optional[str] = Field(None, max_length=50, description="Fare zone ID")
    stop_url: Optional[str] = Field(None, max_length=500, description="Stop URL")
    location_type: Optional[int] = Field(
        0, ge=0, le=3, description="0=stop, 1=station, 2=entrance, 3=node"
    )
    parent_station: Optional[str] = Field(None, max_length=255, description="Parent station stop_id")
    stop_timezone: Optional[str] = Field(None, max_length=100, description="Stop timezone")
    wheelchair_boarding: Optional[int] = Field(
        0, ge=0, le=2, description="0=no info, 1=accessible, 2=not accessible"
    )
    tts_stop_name: Optional[str] = Field(None, max_length=255, description="Text-to-speech readable stop name")
    level_id: Optional[str] = Field(None, max_length=255, description="Level ID within station")
    platform_code: Optional[str] = Field(None, max_length=50, description="Platform identifier (e.g., G, 3)")
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields from GTFS")

    @field_validator("stop_lat", "stop_lon", mode="before")
    @classmethod
    def validate_coordinates(cls, v) -> Decimal:
        """Validate and convert coordinates to Decimal"""
        if v is None:
            return v
        # Convert to Decimal if needed
        if not isinstance(v, Decimal):
            v = Decimal(str(v))
        return v


class StopCreate(StopBase):
    """Schema for creating a new stop"""

    agency_id: Optional[int] = Field(None, description="Agency ID (optional, feed determines agency)")


class StopUpdate(BaseModel):
    """Schema for updating a stop"""

    stop_id: Optional[str] = Field(None, min_length=1, max_length=255)
    stop_name: Optional[str] = Field(None, min_length=1, max_length=255)
    stop_code: Optional[str] = Field(None, max_length=50)
    stop_desc: Optional[str] = None
    stop_lat: Optional[Decimal] = Field(None, ge=-90, le=90)
    stop_lon: Optional[Decimal] = Field(None, ge=-180, le=180)
    zone_id: Optional[str] = Field(None, max_length=50)
    stop_url: Optional[str] = Field(None, max_length=500)
    location_type: Optional[int] = Field(None, ge=0, le=3)
    parent_station: Optional[str] = Field(None, max_length=255)
    stop_timezone: Optional[str] = Field(None, max_length=100)
    wheelchair_boarding: Optional[int] = Field(None, ge=0, le=2)
    tts_stop_name: Optional[str] = Field(None, max_length=255)
    level_id: Optional[str] = Field(None, max_length=255)
    platform_code: Optional[str] = Field(None, max_length=50)
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields from GTFS")


class StopResponse(StopBase):
    """Schema for stop response"""

    feed_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StopWithDistance(StopResponse):
    """Stop response with distance from a reference point"""

    distance_meters: Optional[float] = Field(None, description="Distance in meters from reference point")


# Geospatial queries


class StopNearbyQuery(BaseModel):
    """Query for finding nearby stops"""

    latitude: Decimal = Field(..., ge=-90, le=90, description="Reference latitude")
    longitude: Decimal = Field(..., ge=-180, le=180, description="Reference longitude")
    radius_meters: int = Field(1000, ge=1, le=50000, description="Search radius in meters (max 50km)")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results")


class StopBoundsQuery(BaseModel):
    """Query for stops within bounding box"""

    min_lat: Decimal = Field(..., ge=-90, le=90, description="Minimum latitude")
    min_lon: Decimal = Field(..., ge=-180, le=180, description="Minimum longitude")
    max_lat: Decimal = Field(..., ge=-90, le=90, description="Maximum latitude")
    max_lon: Decimal = Field(..., ge=-180, le=180, description="Maximum longitude")

    @field_validator("max_lat")
    @classmethod
    def validate_lat_bounds(cls, v: Decimal, info) -> Decimal:
        """Ensure max_lat > min_lat"""
        if "min_lat" in info.data and v <= info.data["min_lat"]:
            raise ValueError("max_lat must be greater than min_lat")
        return v

    @field_validator("max_lon")
    @classmethod
    def validate_lon_bounds(cls, v: Decimal, info) -> Decimal:
        """Ensure max_lon > min_lon"""
        if "min_lon" in info.data and v <= info.data["min_lon"]:
            raise ValueError("max_lon must be greater than min_lon")
        return v


# List and pagination schemas


class StopList(BaseModel):
    """Paginated list of stops"""

    items: List[StopResponse] = Field(..., description="List of stops")
    total: int = Field(..., description="Total number of stops")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


class StopListWithDistance(BaseModel):
    """List of stops with distance information"""

    items: List[StopWithDistance] = Field(..., description="List of stops with distances")
    total: int = Field(..., description="Total number of stops")


# Bulk operations


class StopImport(BaseModel):
    """Schema for importing stops from GTFS"""

    stops: List[StopCreate] = Field(..., description="List of stops to import")
    replace_existing: bool = Field(default=False, description="Replace existing stops with same stop_id")


class StopImportResult(BaseModel):
    """Result of stop import operation"""

    created: int = Field(..., description="Number of stops created")
    updated: int = Field(..., description="Number of stops updated")
    skipped: int = Field(..., description="Number of stops skipped")
    errors: List[str] = Field(default_factory=list, description="List of errors encountered")
