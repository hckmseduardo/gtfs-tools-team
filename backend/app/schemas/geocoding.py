"""Schemas for geocoding API endpoints"""

from typing import Optional, List
from pydantic import BaseModel, Field


class ReverseGeocodeRequest(BaseModel):
    """Request for reverse geocoding"""
    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lon: float = Field(..., ge=-180, le=180, description="Longitude")
    lang: Optional[str] = Field("en", description="Preferred language (en, fr, pt)")


class SearchRequest(BaseModel):
    """Request for forward geocoding (address search)"""
    query: str = Field(..., min_length=2, max_length=200, description="Search query")
    limit: int = Field(5, ge=1, le=10, description="Maximum number of results")
    lang: Optional[str] = Field("en", description="Preferred language (en, fr, pt)")
    # Optional viewbox to bias results (minLon, minLat, maxLon, maxLat)
    viewbox: Optional[List[float]] = Field(None, description="Bounding box [minLon, minLat, maxLon, maxLat]")
    bounded: bool = Field(False, description="If true, only return results within viewbox")


class SearchResultItem(BaseModel):
    """Single search result"""
    place_id: int
    display_name: str
    lat: float
    lon: float
    type: Optional[str] = None
    importance: Optional[float] = None
    boundingbox: Optional[List[float]] = Field(None, description="[south, north, west, east]")


class SearchResponse(BaseModel):
    """Response from address search"""
    success: bool = True
    results: List[SearchResultItem] = Field(default_factory=list)


class ReverseGeocodeResponse(BaseModel):
    """Response from reverse geocoding"""
    success: bool = True
    display_name: str = Field(..., description="Full formatted address")
    suggested_stop_name: str = Field(..., description="Suggested name for a transit stop")
    intersection: Optional[str] = Field(None, description="Intersection name if detected (e.g., 'Main St / Oak Ave')")

    # Address components
    name: Optional[str] = Field(None, description="POI or place name")
    road: Optional[str] = Field(None, description="Street name")
    house_number: Optional[str] = Field(None, description="House/building number")
    neighbourhood: Optional[str] = Field(None, description="Neighbourhood name")
    suburb: Optional[str] = Field(None, description="Suburb or district")
    city: Optional[str] = Field(None, description="City, town, or village")
    state: Optional[str] = Field(None, description="State or province")
    country: Optional[str] = Field(None, description="Country")
    postcode: Optional[str] = Field(None, description="Postal code")


class GeocodingHealthResponse(BaseModel):
    """Health check response for geocoding service"""
    available: bool
    message: str
