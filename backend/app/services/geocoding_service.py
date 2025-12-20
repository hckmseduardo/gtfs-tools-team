"""
Geocoding Service for forward and reverse geocoding.
Uses OpenStreetMap Nominatim API for address lookup and Valhalla for intersection detection.
"""

import httpx
import logging
import os
from typing import Optional, List, Tuple
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Nominatim API URL - can be overridden for self-hosted instance
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org")

# Valhalla URL for intersection detection
VALHALLA_URL = os.getenv("VALHALLA_URL", "http://valhalla:8002")

# User-Agent is required by Nominatim usage policy
USER_AGENT = os.getenv("NOMINATIM_USER_AGENT", "GTFS-Editor/1.0 (https://gtfs-tools.com)")


class GeocodingResult(BaseModel):
    """Result from reverse geocoding"""
    display_name: str
    name: Optional[str] = None
    road: Optional[str] = None
    house_number: Optional[str] = None
    neighbourhood: Optional[str] = None
    suburb: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postcode: Optional[str] = None
    suggested_stop_name: str  # Computed best name for a transit stop
    intersection: Optional[str] = None  # Intersection name if detected


class SearchResult(BaseModel):
    """Result from forward geocoding (address search)"""
    place_id: int
    display_name: str
    lat: float
    lon: float
    type: Optional[str] = None  # e.g., "house", "street", "city"
    importance: Optional[float] = None
    # Bounding box for zoom fitting [south, north, west, east]
    boundingbox: Optional[List[float]] = None


class GeocodingError(Exception):
    """Custom exception for geocoding failures"""
    def __init__(self, message: str, code: str = "GEOCODING_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class GeocodingService:
    """Service for geocoding operations via Nominatim and Valhalla"""

    def __init__(self):
        self.base_url = NOMINATIM_URL
        self.valhalla_url = VALHALLA_URL
        self.timeout = 10.0
        self.headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en,fr,pt-BR",  # Multi-language support
        }

    async def _get_intersection_from_valhalla(
        self,
        lat: float,
        lon: float
    ) -> Optional[Tuple[str, str]]:
        """
        Use Valhalla's locate endpoint to find nearby road segments and detect intersections.
        Queries multiple nearby points to find cross streets.

        Returns tuple of (road1, road2) if intersection found, None otherwise.
        """
        try:
            # Query multiple points around the target to find nearby roads
            # Offset by ~20 meters in each direction
            offset = 0.0002  # Approximately 20 meters
            points = [
                {"lat": lat, "lon": lon},
                {"lat": lat + offset, "lon": lon},
                {"lat": lat - offset, "lon": lon},
                {"lat": lat, "lon": lon + offset},
                {"lat": lat, "lon": lon - offset},
            ]

            request_body = {
                "locations": points,
                "costing": "auto",
                "verbose": True
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.valhalla_url}/locate",
                    json=request_body,
                    timeout=5.0
                )

                if response.status_code != 200:
                    logger.debug(f"Valhalla locate failed: {response.status_code}")
                    return None

                data = response.json()

                if not data or not isinstance(data, list):
                    return None

                # Collect unique road names from all queried locations
                road_names = set()
                for location in data:
                    if not location:
                        continue
                    edges = location.get("edges", [])
                    for edge in edges:
                        edge_info = edge.get("edge_info", {})
                        names = edge_info.get("names", [])
                        for name in names:
                            if name and len(name) > 1:  # Filter out empty or single-char names
                                road_names.add(name)

                # If we have 2+ different road names, it's likely an intersection
                road_list = list(road_names)
                if len(road_list) >= 2:
                    # Sort alphabetically for consistent ordering
                    road_list.sort()
                    return (road_list[0], road_list[1])

                return None

        except Exception as e:
            logger.debug(f"Valhalla intersection detection failed: {e}")
            return None

    async def reverse_geocode(
        self,
        lat: float,
        lon: float,
        lang: str = "en"
    ) -> GeocodingResult:
        """
        Reverse geocode a lat/lon coordinate to an address.
        Uses Valhalla to detect intersections for better stop naming.

        Args:
            lat: Latitude
            lon: Longitude
            lang: Preferred language for results (en, fr, pt)

        Returns:
            GeocodingResult with address components and suggested stop name
        """
        # Try to get intersection from Valhalla first (faster, more accurate for roads)
        intersection = await self._get_intersection_from_valhalla(lat, lon)

        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "addressdetails": 1,
            "zoom": 18,  # High detail level for street addresses
        }

        headers = self.headers.copy()
        headers["Accept-Language"] = lang

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/reverse",
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )

                if response.status_code != 200:
                    logger.error(f"Nominatim reverse geocode failed: {response.status_code}")
                    raise GeocodingError(
                        f"Geocoding service returned {response.status_code}",
                        "SERVICE_ERROR"
                    )

                data = response.json()

                if "error" in data:
                    # No results found - return coordinates as name
                    return GeocodingResult(
                        display_name=f"{lat:.6f}, {lon:.6f}",
                        suggested_stop_name=f"Stop at {lat:.5f}, {lon:.5f}"
                    )

                return self._parse_result(data, intersection)

        except httpx.RequestError as e:
            logger.error(f"Nominatim request failed: {e}")
            raise GeocodingError(f"Geocoding service unavailable: {e}", "SERVICE_UNAVAILABLE")

    def _parse_result(
        self,
        data: dict,
        intersection: Optional[Tuple[str, str]] = None
    ) -> GeocodingResult:
        """Parse Nominatim reverse geocode response"""
        address = data.get("address", {})

        # Extract address components
        name = data.get("name")
        road = address.get("road") or address.get("pedestrian") or address.get("path")
        house_number = address.get("house_number")
        neighbourhood = address.get("neighbourhood") or address.get("quarter")
        suburb = address.get("suburb") or address.get("borough")
        city = (
            address.get("city") or
            address.get("town") or
            address.get("village") or
            address.get("municipality")
        )
        state = address.get("state") or address.get("province")
        country = address.get("country")
        postcode = address.get("postcode")

        # Format intersection string if detected
        intersection_str = None
        if intersection:
            intersection_str = f"{intersection[0]} / {intersection[1]}"

        # Compute suggested stop name (prefer intersection if available)
        suggested_stop_name = self._compute_stop_name(
            name=name,
            road=road,
            house_number=house_number,
            neighbourhood=neighbourhood,
            suburb=suburb,
            city=city,
            address=address,
            intersection=intersection
        )

        return GeocodingResult(
            display_name=data.get("display_name", ""),
            name=name,
            road=road,
            house_number=house_number,
            neighbourhood=neighbourhood,
            suburb=suburb,
            city=city,
            state=state,
            country=country,
            postcode=postcode,
            suggested_stop_name=suggested_stop_name,
            intersection=intersection_str
        )

    def _compute_stop_name(
        self,
        name: Optional[str],
        road: Optional[str],
        house_number: Optional[str],
        neighbourhood: Optional[str],
        suburb: Optional[str],
        city: Optional[str],
        address: dict,
        intersection: Optional[Tuple[str, str]] = None
    ) -> str:
        """
        Compute a suitable stop name from address components.

        Priority:
        1. POI name if available (e.g., "Central Station", "City Hall")
        2. Intersection name (e.g., "Main St / Oak Ave")
        3. Road + neighbourhood/suburb
        4. Road name alone
        5. Neighbourhood + city
        6. Suburb + city
        """
        # Check for POI types that make good stop names
        poi_keys = [
            "amenity", "shop", "building", "tourism", "leisure",
            "railway", "bus_stop", "tram_stop", "station"
        ]

        # If there's a specific name and it's a POI, use it
        if name:
            for key in poi_keys:
                if key in address:
                    return name

        # Intersection-based naming (preferred for transit stops)
        if intersection:
            return f"{intersection[0]} / {intersection[1]}"

        # Road-based naming
        if road:
            # Check for cross street from Nominatim (rarely provided)
            cross_street = address.get("cross_street")
            if cross_street:
                return f"{road} / {cross_street}"

            # Road + neighbourhood
            if neighbourhood:
                return f"{road} ({neighbourhood})"

            # Road + suburb
            if suburb:
                return f"{road} ({suburb})"

            return road

        # Fallback to area names
        if neighbourhood and city:
            return f"{neighbourhood}, {city}"

        if suburb and city:
            return f"{suburb}, {city}"

        if neighbourhood:
            return neighbourhood

        if suburb:
            return suburb

        if city:
            return city

        # Last resort - use the full display name truncated
        if name:
            return name[:50]

        return "Unnamed Stop"


    async def search(
        self,
        query: str,
        limit: int = 5,
        lang: str = "en",
        viewbox: Optional[Tuple[float, float, float, float]] = None,
        bounded: bool = False
    ) -> List[SearchResult]:
        """
        Forward geocode: search for addresses/places matching a query.

        Args:
            query: Search query (address, place name, etc.)
            limit: Maximum number of results (default 5, max 10)
            lang: Preferred language for results
            viewbox: Optional bounding box to bias results (minLon, minLat, maxLon, maxLat)
            bounded: If True with viewbox, only return results within the box

        Returns:
            List of SearchResult with coordinates and display names
        """
        if not query or len(query.strip()) < 2:
            return []

        params = {
            "q": query.strip(),
            "format": "json",
            "limit": min(limit, 10),  # Cap at 10
            "addressdetails": 1,
        }

        if viewbox:
            # Nominatim format: minLon,maxLat,maxLon,minLat (west,north,east,south)
            params["viewbox"] = f"{viewbox[0]},{viewbox[3]},{viewbox[2]},{viewbox[1]}"
            if bounded:
                params["bounded"] = 1

        headers = self.headers.copy()
        headers["Accept-Language"] = lang

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/search",
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )

                if response.status_code != 200:
                    logger.error(f"Nominatim search failed: {response.status_code}")
                    raise GeocodingError(
                        f"Geocoding service returned {response.status_code}",
                        "SERVICE_ERROR"
                    )

                data = response.json()

                results = []
                for item in data:
                    try:
                        # Parse bounding box if available
                        bbox = None
                        if "boundingbox" in item and len(item["boundingbox"]) == 4:
                            bbox = [float(x) for x in item["boundingbox"]]

                        results.append(SearchResult(
                            place_id=int(item.get("place_id", 0)),
                            display_name=item.get("display_name", ""),
                            lat=float(item.get("lat", 0)),
                            lon=float(item.get("lon", 0)),
                            type=item.get("type"),
                            importance=float(item.get("importance", 0)) if item.get("importance") else None,
                            boundingbox=bbox
                        ))
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to parse search result: {e}")
                        continue

                return results

        except httpx.RequestError as e:
            logger.error(f"Nominatim search request failed: {e}")
            raise GeocodingError(f"Geocoding service unavailable: {e}", "SERVICE_UNAVAILABLE")


# Singleton instance
geocoding_service = GeocodingService()
