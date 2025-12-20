"""Route (GTFS) schemas for API requests and responses"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


# Enum for route types
class RouteType(int):
    """GTFS Route Type Enum

    0 - Tram, Streetcar, Light rail
    1 - Subway, Metro
    2 - Rail
    3 - Bus
    4 - Ferry
    5 - Cable car
    6 - Gondola, Suspended cable car
    7 - Funicular
    """
    TRAM = 0
    SUBWAY = 1
    RAIL = 2
    BUS = 3
    FERRY = 4
    CABLE_CAR = 5
    GONDOLA = 6
    FUNICULAR = 7


class RouteBase(BaseModel):
    """Base route schema"""

    route_id: str = Field(..., min_length=1, max_length=255, description="GTFS route_id")
    route_short_name: str = Field("", max_length=50, description="Short route name (e.g., '101')")
    route_long_name: Optional[str] = Field(None, max_length=255, description="Full route name")
    route_desc: Optional[str] = Field(None, description="Route description")
    route_type: int = Field(..., ge=0, le=2000, description="Type of transportation (0-7 standard, 100-1700 extended)")
    route_url: Optional[str] = Field(None, max_length=500, description="Route URL")
    route_color: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{6}$", description="Route color (hex, no #)")
    route_text_color: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{6}$", description="Text color (hex, no #)")
    route_sort_order: Optional[int] = Field(None, ge=0, description="Sort order for display")
    continuous_pickup: Optional[int] = Field(None, ge=0, le=3, description="Continuous pickup behavior")
    continuous_drop_off: Optional[int] = Field(None, ge=0, le=3, description="Continuous drop-off behavior")
    network_id: Optional[str] = Field(None, max_length=255, description="Network ID for fare calculations")
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields from GTFS")

    @field_validator("route_color", "route_text_color", mode='before')
    @classmethod
    def validate_hex_color(cls, v: Optional[str]) -> Optional[str]:
        """Validate hex color format"""
        if v is None or v == "":
            return None
        # Remove # if present
        if v.startswith("#"):
            v = v[1:]
        # Ensure 6 characters
        if len(v) != 6:
            raise ValueError("Color must be 6 hex characters")
        # Ensure uppercase
        return v.upper()

    @field_validator("route_desc", "route_url", "route_long_name", "network_id", mode='before')
    @classmethod
    def empty_str_to_none(cls, v: Optional[str]) -> Optional[str]:
        """Convert empty strings to None for optional fields"""
        if v == "":
            return None
        return v


class RouteCreate(RouteBase):
    """Schema for creating a new route"""

    agency_id: Optional[int] = Field(None, description="Agency ID (optional, derived from feed)")


class RouteUpdate(BaseModel):
    """Schema for updating a route"""

    route_id: Optional[str] = Field(None, min_length=1, max_length=255)
    route_short_name: Optional[str] = Field(None, max_length=50)
    route_long_name: Optional[str] = Field(None, max_length=255)
    route_desc: Optional[str] = None
    route_type: Optional[int] = Field(None, ge=0, le=2000)
    route_url: Optional[str] = Field(None, max_length=500)
    route_color: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{6}$")
    route_text_color: Optional[str] = Field(None, pattern=r"^[0-9A-Fa-f]{6}$")
    route_sort_order: Optional[int] = Field(None, ge=0)
    continuous_pickup: Optional[int] = Field(None, ge=0, le=3)
    continuous_drop_off: Optional[int] = Field(None, ge=0, le=3)
    network_id: Optional[str] = Field(None, max_length=255)
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields from GTFS")

    @field_validator("route_color", "route_text_color", mode='before')
    @classmethod
    def validate_hex_color(cls, v: Optional[str]) -> Optional[str]:
        """Validate hex color format, convert empty to None"""
        if v is None or v == "":
            return None
        if v.startswith("#"):
            v = v[1:]
        if len(v) != 6:
            raise ValueError("Color must be 6 hex characters")
        return v.upper()

    @field_validator("route_desc", "route_url", "route_long_name", "route_short_name", "network_id", mode='before')
    @classmethod
    def empty_str_to_none(cls, v: Optional[str]) -> Optional[str]:
        """Convert empty strings to None for optional fields"""
        if v == "":
            return None
        return v


class RouteResponse(RouteBase):
    """Schema for route response"""

    feed_id: int
    agency_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RouteWithStats(RouteResponse):
    """Route response with statistics"""

    trip_count: int = Field(default=0, description="Number of trips for this route")
    active_trips: int = Field(default=0, description="Number of currently active trips")


# List and pagination schemas


class RouteList(BaseModel):
    """Paginated list of routes"""

    items: List[RouteResponse] = Field(..., description="List of routes")
    total: int = Field(..., description="Total number of routes")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


class RouteListWithStats(BaseModel):
    """Paginated list of routes with statistics"""

    items: List[RouteWithStats] = Field(..., description="List of routes with stats")
    total: int = Field(..., description="Total number of routes")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


# Bulk operations


class RouteImport(BaseModel):
    """Schema for importing routes from GTFS"""

    routes: List[RouteCreate] = Field(..., description="List of routes to import")
    replace_existing: bool = Field(default=False, description="Replace existing routes with same route_id")


class RouteImportResult(BaseModel):
    """Result of route import operation"""

    created: int = Field(..., description="Number of routes created")
    updated: int = Field(..., description="Number of routes updated")
    skipped: int = Field(..., description="Number of routes skipped")
    errors: List[str] = Field(default_factory=list, description="List of errors encountered")
