"""Pydantic schemas for routing operations"""

from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class TransitMode(str, Enum):
    """Transport modes for routing"""
    BUS = "bus"
    RAIL = "rail"
    TRAM = "tram"
    FERRY = "ferry"


class RoutingPointInput(BaseModel):
    """Input point for routing"""
    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lon: float = Field(..., ge=-180, le=180, description="Longitude")


class SnapToRoadRequest(BaseModel):
    """Request to snap shape points to road network"""
    feed_id: int = Field(..., description="Feed ID for permission check")
    shape_id: str = Field(..., description="Shape ID to snap")
    mode: TransitMode = Field(default=TransitMode.BUS, description="Transport mode for routing")


class AutoRouteRequest(BaseModel):
    """Request to generate route from waypoints"""
    feed_id: int = Field(..., description="Feed ID for permission check")
    shape_id: str = Field(..., description="Shape ID to update or create")
    waypoints: List[RoutingPointInput] = Field(
        ...,
        min_length=2,
        description="Waypoints to route through (minimum 2)"
    )
    mode: TransitMode = Field(default=TransitMode.BUS, description="Transport mode for routing")


class RoutingPointOutput(BaseModel):
    """Output point from routing operation"""
    lat: float
    lon: float
    sequence: int

    model_config = ConfigDict(from_attributes=True)


class RoutingResult(BaseModel):
    """Result from a routing operation"""
    success: bool
    shape_id: str
    points: List[RoutingPointOutput]
    point_count: int
    distance_meters: float
    message: Optional[str] = None
    confidence: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class RoutingHealthResponse(BaseModel):
    """Health check response for routing service"""
    available: bool
    message: str

    model_config = ConfigDict(from_attributes=True)
