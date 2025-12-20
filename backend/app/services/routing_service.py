"""
Valhalla Routing Service for OSM-based shape routing and map-matching.
Wraps the self-hosted Valhalla API for GTFS shape operations.
"""

import httpx
import logging
import os
import math
from typing import List, Optional, Tuple
from enum import Enum
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Valhalla service URL - internal docker network
VALHALLA_URL = os.getenv("VALHALLA_URL", "http://valhalla:8002")


class TransitMode(str, Enum):
    """Transport modes supported by Valhalla routing"""
    BUS = "auto"           # Uses road network
    RAIL = "pedestrian"    # Rail/metro - uses pedestrian for tracing paths
    TRAM = "bicycle"       # Tram uses mixed routing (roads + some paths)
    FERRY = "auto"         # Ferry uses road network for land portions
    PEDESTRIAN = "pedestrian"


class RoutingPoint(BaseModel):
    """A single point for routing operations"""
    lat: float
    lon: float


class RoutedShape(BaseModel):
    """Result from a routing operation"""
    points: List[RoutingPoint]
    distance_meters: float
    duration_seconds: Optional[float] = None
    matched: bool = True
    confidence: Optional[float] = None


class RoutingError(Exception):
    """Custom exception for routing failures"""
    def __init__(self, message: str, code: str = "ROUTING_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class RoutingService:
    """Service for OSM-based routing operations via Valhalla"""

    def __init__(self):
        self.base_url = VALHALLA_URL
        self.timeout = 60.0  # Generous timeout for large shapes

    async def check_health(self) -> bool:
        """Check if Valhalla is available and healthy"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/status",
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Valhalla health check failed: {e}")
            return False

    async def snap_to_road(
        self,
        points: List[RoutingPoint],
        mode: TransitMode = TransitMode.BUS,
    ) -> RoutedShape:
        """
        Snap existing shape points to the nearest road/rail network.
        Uses Valhalla's trace_route (map-matching) endpoint.

        Args:
            points: List of shape points to snap
            mode: Transport mode for routing costing

        Returns:
            RoutedShape with snapped points following the road network
        """
        if len(points) < 2:
            raise RoutingError("At least 2 points required", "INSUFFICIENT_POINTS")

        # Build Valhalla trace_route request
        shape = [{"lat": p.lat, "lon": p.lon} for p in points]

        request_body = {
            "shape": shape,
            "costing": mode.value,
            "shape_match": "map_snap",  # Snap to nearest road
            "filters": {
                "attributes": ["shape", "matched.point", "matched.type"],
                "action": "include"
            },
            "trace_options": {
                "search_radius": 100,  # meters - expand search for transit
                "gps_accuracy": 10,
                "turn_penalty_factor": 0  # Don't penalize turns for transit
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/trace_route",
                    json=request_body,
                    timeout=self.timeout
                )

                if response.status_code != 200:
                    error_data = response.json() if response.text else {}
                    error_msg = error_data.get("error", "Unknown routing error")
                    logger.error(f"Valhalla trace_route failed: {error_msg}")
                    raise RoutingError(error_msg, "VALHALLA_ERROR")

                result = response.json()
                return self._parse_trace_result(result)

        except httpx.RequestError as e:
            logger.error(f"Valhalla request failed: {e}")
            raise RoutingError(f"Routing service unavailable: {e}", "SERVICE_UNAVAILABLE")

    async def auto_route(
        self,
        waypoints: List[RoutingPoint],
        mode: TransitMode = TransitMode.BUS,
    ) -> RoutedShape:
        """
        Generate a route through waypoints following the road network.
        Uses Valhalla's route endpoint.

        Args:
            waypoints: List of waypoints to route through (minimum 2)
            mode: Transport mode for routing costing

        Returns:
            RoutedShape with detailed route following roads
        """
        if len(waypoints) < 2:
            raise RoutingError("At least 2 waypoints required", "INSUFFICIENT_WAYPOINTS")

        # Build Valhalla route request
        locations = [{"lat": p.lat, "lon": p.lon, "type": "break"} for p in waypoints]

        request_body = {
            "locations": locations,
            "costing": mode.value,
            "directions_options": {
                "units": "kilometers"
            },
            "costing_options": {
                mode.value: {
                    "use_highways": 1.0 if mode == TransitMode.BUS else 0.5,
                    "use_ferry": 0.5
                }
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/route",
                    json=request_body,
                    timeout=self.timeout
                )

                if response.status_code != 200:
                    error_data = response.json() if response.text else {}
                    error_msg = error_data.get("error", "Unknown routing error")
                    logger.error(f"Valhalla route failed: {error_msg}")
                    raise RoutingError(error_msg, "VALHALLA_ERROR")

                result = response.json()
                return self._parse_route_result(result)

        except httpx.RequestError as e:
            logger.error(f"Valhalla request failed: {e}")
            raise RoutingError(f"Routing service unavailable: {e}", "SERVICE_UNAVAILABLE")

    def _parse_trace_result(self, result: dict) -> RoutedShape:
        """Parse Valhalla trace_route response into RoutedShape"""
        trip = result.get("trip", {})
        legs = trip.get("legs", [])

        if not legs:
            raise RoutingError("No route found for given points", "NO_ROUTE")

        # Decode the polyline shape. Valhalla may return trip-level shape or per-leg shapes.
        encoded_shape = trip.get("shape", "")
        points: List[Tuple[float, float]] = []

        if encoded_shape:
            points = self._decode_polyline(encoded_shape)
        else:
            # Fallback: stitch leg shapes together
            for i, leg in enumerate(legs):
                leg_shape = leg.get("shape", "")
                if not leg_shape:
                    continue
                leg_points = self._decode_polyline(leg_shape)
                if not leg_points:
                    continue
                if points:
                    # drop first point to avoid duplicates at leg boundaries
                    leg_points = leg_points[1:]
                points.extend(leg_points)

        points = self._simplify_points(points)

        # Calculate total distance (legs return length in km)
        total_distance = sum(leg.get("summary", {}).get("length", 0) for leg in legs) * 1000

        # Get confidence from matched points
        matched_points = result.get("matched_points", [])
        if matched_points:
            matched_count = sum(1 for p in matched_points if p.get("type") == "matched")
            avg_confidence = matched_count / len(matched_points) if matched_points else 1.0
        else:
            avg_confidence = 1.0

        return RoutedShape(
            points=[RoutingPoint(lat=p[0], lon=p[1]) for p in points],
            distance_meters=total_distance,
            matched=True,
            confidence=avg_confidence
        )

    def _parse_route_result(self, result: dict) -> RoutedShape:
        """Parse Valhalla route response into RoutedShape"""
        trip = result.get("trip", {})
        legs = trip.get("legs", [])

        if not legs:
            raise RoutingError("No route found between waypoints", "NO_ROUTE")

        # Decode the polyline shape (trip-level or per-leg)
        encoded_shape = trip.get("shape", "")
        points: List[Tuple[float, float]] = []

        if encoded_shape:
            points = self._decode_polyline(encoded_shape)
        else:
            for leg in legs:
                leg_shape = leg.get("shape", "")
                if not leg_shape:
                    continue
                leg_points = self._decode_polyline(leg_shape)
                if not leg_points:
                    continue
                if points:
                    leg_points = leg_points[1:]
                points.extend(leg_points)

        points = self._simplify_points(points)

        # Get summary info
        summary = trip.get("summary", {})
        total_distance = summary.get("length", 0) * 1000  # km to meters
        total_time = summary.get("time", 0)

        return RoutedShape(
            points=[RoutingPoint(lat=p[0], lon=p[1]) for p in points],
            distance_meters=total_distance,
            duration_seconds=total_time,
            matched=True
        )

    def _simplify_points(
        self,
        points: List[Tuple[float, float]],
        tolerance_meters: float = 15.0,
        max_points: Optional[int] = None
    ) -> List[Tuple[float, float]]:
        """
        Thin the point list with a lightweight Douglas-Peucker in meter space.
        Keeps endpoints; skips if already short or below tolerance.
        """
        if len(points) <= 2:
            return points

        if max_points is not None and len(points) <= max_points:
            # Respect optional guard when provided
            return points

        # Pre-compute meter conversion using equirectangular projection
        lat0 = math.radians(points[0][0])
        meter_per_deg_lat = 111_320.0
        meter_per_deg_lon = meter_per_deg_lat * math.cos(lat0)

        def to_xy(p: Tuple[float, float]) -> Tuple[float, float]:
            lat, lon = p
            return (
                (lon - points[0][1]) * meter_per_deg_lon,
                (lat - points[0][0]) * meter_per_deg_lat,
            )

        xy_points = [to_xy(p) for p in points]

        def perpendicular_distance(a, b, p) -> float:
            # Distance from p to line ab in meters
            ax, ay = a
            bx, by = b
            px, py = p
            dx = bx - ax
            dy = by - ay
            if dx == 0 and dy == 0:
                return math.hypot(px - ax, py - ay)
            return abs(dy * px - dx * py + bx * ay - by * ax) / math.hypot(dx, dy)

        # Iterative Douglas-Peucker
        keep = [False] * len(points)
        keep[0] = keep[-1] = True
        stack: List[Tuple[int, int]] = [(0, len(points) - 1)]

        while stack:
            start, end = stack.pop()
            max_dist = 0.0
            index = None
            for i in range(start + 1, end):
                dist = perpendicular_distance(xy_points[start], xy_points[end], xy_points[i])
                if dist > max_dist:
                    max_dist = dist
                    index = i
            if index is not None and max_dist > tolerance_meters:
                keep[index] = True
                stack.append((start, index))
                stack.append((index, end))

        simplified = [pt for pt, k in zip(points, keep) if k]
        if len(simplified) < len(points):
            logger.info(
                f"Simplified routed shape from {len(points)} to {len(simplified)} points "
                f"with tolerance {tolerance_meters}m"
            )
        return simplified

    def _decode_polyline(self, encoded: str, precision: int = 6) -> List[Tuple[float, float]]:
        """
        Decode a Valhalla encoded polyline.
        Valhalla uses precision 6 by default.

        Returns list of (lat, lon) tuples.
        """
        if not encoded:
            return []

        def _decode_with_precision(enc: str, prec: int) -> List[Tuple[float, float]]:
            inv = 1.0 / (10 ** prec)
            decoded: List[Tuple[float, float]] = []
            lat = 0
            lon = 0
            i = 0

            while i < len(enc):
                # Decode latitude
                shift = 0
                result = 0
                while True:
                    b = ord(enc[i]) - 63
                    i += 1
                    result |= (b & 0x1f) << shift
                    shift += 5
                    if b < 0x20:
                        break
                dlat = ~(result >> 1) if result & 1 else (result >> 1)
                lat += dlat

                # Decode longitude
                shift = 0
                result = 0
                while True:
                    b = ord(enc[i]) - 63
                    i += 1
                    result |= (b & 0x1f) << shift
                    shift += 5
                    if b < 0x20:
                        break
                dlon = ~(result >> 1) if result & 1 else (result >> 1)
                lon += dlon

                decoded.append((lat * inv, lon * inv))

            return decoded

        # Try default precision 6 first; if empty, attempt precision 5 as a fallback
        decoded = _decode_with_precision(encoded, precision)
        if not decoded:
            logger.warning("Polyline decode returned 0 points with precision 6; retrying with precision 5")
            decoded = _decode_with_precision(encoded, 5)

        return decoded


# Singleton instance
routing_service = RoutingService()
