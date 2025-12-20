"""Geocoding endpoints for address lookup"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status

from app.schemas.geocoding import (
    ReverseGeocodeRequest,
    ReverseGeocodeResponse,
    GeocodingHealthResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from app.services.geocoding_service import (
    geocoding_service,
    GeocodingError,
)

router = APIRouter()


@router.get("/health", response_model=GeocodingHealthResponse)
async def check_geocoding_health():
    """
    Check if the geocoding service (Nominatim) is available.

    This endpoint is public and doesn't require authentication.
    """
    try:
        # Test with a known location (Montreal)
        result = await geocoding_service.reverse_geocode(45.5017, -73.5673)
        return GeocodingHealthResponse(
            available=True,
            message="Geocoding service is available"
        )
    except GeocodingError:
        return GeocodingHealthResponse(
            available=False,
            message="Geocoding service is unavailable"
        )


@router.post("/reverse", response_model=ReverseGeocodeResponse)
async def reverse_geocode(request: ReverseGeocodeRequest):
    """
    Reverse geocode a latitude/longitude to an address.

    Returns address components and a suggested stop name based on the location.
    This endpoint is public to allow address lookup during stop creation.
    """
    try:
        result = await geocoding_service.reverse_geocode(
            lat=request.lat,
            lon=request.lon,
            lang=request.lang or "en"
        )

        return ReverseGeocodeResponse(
            success=True,
            display_name=result.display_name,
            suggested_stop_name=result.suggested_stop_name,
            intersection=result.intersection,
            name=result.name,
            road=result.road,
            house_number=result.house_number,
            neighbourhood=result.neighbourhood,
            suburb=result.suburb,
            city=result.city,
            state=result.state,
            country=result.country,
            postcode=result.postcode,
        )

    except GeocodingError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Geocoding failed: {e.message}"
        )


@router.post("/search", response_model=SearchResponse)
async def search_address(request: SearchRequest):
    """
    Search for addresses/places matching a query (forward geocoding).

    Returns a list of matching locations with coordinates.
    This endpoint is public to allow address search on the map.
    """
    try:
        # Convert viewbox list to tuple if provided
        viewbox = None
        if request.viewbox and len(request.viewbox) == 4:
            viewbox = tuple(request.viewbox)

        results = await geocoding_service.search(
            query=request.query,
            limit=request.limit,
            lang=request.lang or "en",
            viewbox=viewbox,
            bounded=request.bounded
        )

        return SearchResponse(
            success=True,
            results=[
                SearchResultItem(
                    place_id=r.place_id,
                    display_name=r.display_name,
                    lat=r.lat,
                    lon=r.lon,
                    type=r.type,
                    importance=r.importance,
                    boundingbox=r.boundingbox
                )
                for r in results
            ]
        )

    except GeocodingError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Search failed: {e.message}"
        )
