"""Service for creating demo agency with sample GTFS data for new users"""

import logging
import re
import uuid
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.agency import Agency
from app.models.user import User, user_agencies
from app.models.gtfs import (
    GTFSFeed,
    Route,
    Stop,
    Trip,
    StopTime,
    Calendar,
    Shape,
)
from app.models.feed_source import ExternalFeedSource, FeedSourceType, FeedSourceStatus, CheckFrequency

logger = logging.getLogger(__name__)


def generate_slug(name: str) -> str:
    """Generate a URL-friendly slug from a name"""
    # Convert to lowercase and replace spaces with hyphens
    slug = name.lower().replace(" ", "-")
    # Remove special characters
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    # Add unique suffix to avoid conflicts
    slug = f"{slug}-{uuid.uuid4().hex[:8]}"
    return slug


class DemoAgencyService:
    """Service to create demo agency with sample GTFS data for new users"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_demo_agency_for_user(self, user: User) -> Agency:
        """
        Create a demo agency with sample GTFS data for a new user.

        Creates a Montreal, Quebec transit system demo with:
        - 1 Agency named "Demo Agency - {user_name}" (with GTFS fields populated)
        - 1 Feed with demo data
        - 4 Routes (3 metro lines + 1 airport express bus)
        - 1 Shape for each route
        - 17 Stops across all routes
        - 10 Trips (8 weekday + 2 weekend)
        - Stop times for each trip
        - 2 Calendars (weekday and weekend service)
        - 6 GTFS-RT feed sources for real-time simulation
        """
        user_name = user.full_name or user.email.split("@")[0]

        # Create the demo agency with GTFS fields populated
        agency_name = f"Demo Agency - {user_name}"
        agency = Agency(
            name=agency_name,
            slug=generate_slug(agency_name),
            # GTFS agency.txt fields
            agency_id="demo_agency",
            agency_url="https://example.com",
            agency_timezone="America/Montreal",
            agency_lang="fr",
        )
        self.db.add(agency)
        await self.db.flush()

        # Associate user with agency
        from app.models.user import UserRole
        await self.db.execute(
            user_agencies.insert().values(
                user_id=user.id,
                agency_id=agency.id,
                role=UserRole.AGENCY_ADMIN.value,
            )
        )

        # Create the demo feed
        feed = GTFSFeed(
            agency_id=agency.id,
            name="Montreal Demo Feed",
            description="Sample Montreal transit data for learning and exploration",
            version="1.0",
            imported_at=datetime.utcnow().isoformat() + "Z",
            imported_by=user.id,
            is_active=True,
            total_routes=4,
            total_stops=17,
            total_trips=10,
        )
        self.db.add(feed)
        await self.db.flush()

        # Create Calendar (weekday service)
        weekday_calendar = Calendar(
            feed_id=feed.id,
            service_id="weekday",
            monday=True,
            tuesday=True,
            wednesday=True,
            thursday=True,
            friday=True,
            saturday=False,
            sunday=False,
            start_date=(datetime.now()).strftime("%Y%m%d"),
            end_date=(datetime.now() + timedelta(days=365)).strftime("%Y%m%d"),
        )
        self.db.add(weekday_calendar)

        # Create Calendar (weekend service)
        weekend_calendar = Calendar(
            feed_id=feed.id,
            service_id="weekend",
            monday=False,
            tuesday=False,
            wednesday=False,
            thursday=False,
            friday=False,
            saturday=True,
            sunday=True,
            start_date=(datetime.now()).strftime("%Y%m%d"),
            end_date=(datetime.now() + timedelta(days=365)).strftime("%Y%m%d"),
        )
        self.db.add(weekend_calendar)
        await self.db.flush()

        # Create Stops for Montreal transit system
        # Montreal coordinates centered around downtown
        stops_data = [
            # Green Line (Ligne Verte) - East-West downtown
            {"stop_id": "green_1", "stop_name": "Berri-UQAM", "lat": 45.5154, "lon": -73.5640},
            {"stop_id": "green_2", "stop_name": "Place-des-Arts", "lat": 45.5082, "lon": -73.5684},
            {"stop_id": "green_3", "stop_name": "McGill", "lat": 45.5040, "lon": -73.5724},
            {"stop_id": "green_4", "stop_name": "Peel", "lat": 45.5010, "lon": -73.5760},
            {"stop_id": "green_5", "stop_name": "Guy-Concordia", "lat": 45.4966, "lon": -73.5796},
            # Orange Line (Ligne Orange) - North through Plateau
            {"stop_id": "orange_1", "stop_name": "Champ-de-Mars", "lat": 45.5102, "lon": -73.5567},
            {"stop_id": "orange_2", "stop_name": "Place-d'Armes", "lat": 45.5061, "lon": -73.5599},
            {"stop_id": "orange_3", "stop_name": "Square-Victoria", "lat": 45.5016, "lon": -73.5631},
            {"stop_id": "orange_4", "stop_name": "Bonaventure", "lat": 45.4975, "lon": -73.5668},
            {"stop_id": "orange_5", "stop_name": "Lucien-L'Allier", "lat": 45.4943, "lon": -73.5709},
            # Blue Line (Ligne Bleue) - East through Outremont
            {"stop_id": "blue_1", "stop_name": "Jean-Talon", "lat": 45.5394, "lon": -73.6135},
            {"stop_id": "blue_2", "stop_name": "De Castelnau", "lat": 45.5356, "lon": -73.6200},
            {"stop_id": "blue_3", "stop_name": "Parc", "lat": 45.5306, "lon": -73.6240},
            {"stop_id": "blue_4", "stop_name": "Outremont", "lat": 45.5239, "lon": -73.6157},
            # 747 Express Bus - Airport
            {"stop_id": "bus_1", "stop_name": "Gare d'autocars de Montréal", "lat": 45.5162, "lon": -73.5628},
            {"stop_id": "bus_2", "stop_name": "Lionel-Groulx", "lat": 45.4829, "lon": -73.5795},
            {"stop_id": "bus_3", "stop_name": "Aéroport Montréal-Trudeau", "lat": 45.4576, "lon": -73.7497},
        ]

        stops = {}
        for stop_data in stops_data:
            stop = Stop(
                feed_id=feed.id,
                stop_id=stop_data["stop_id"],
                stop_name=stop_data["stop_name"],
                stop_lat=stop_data["lat"],
                stop_lon=stop_data["lon"],
            )
            self.db.add(stop)
            stops[stop_data["stop_id"]] = stop
        await self.db.flush()

        # Create Routes - 4 Montreal lines with distinct colors
        # Green Line - Ligne Verte
        green_route = Route(
            feed_id=feed.id,
            route_id="green_line",
            agency_id=agency.id,
            route_short_name="1",
            route_long_name="Ligne Verte",
            route_type=1,  # Metro
            route_color="008E4F",  # STM Green
            route_text_color="FFFFFF",
        )
        self.db.add(green_route)

        # Orange Line - Ligne Orange
        orange_route = Route(
            feed_id=feed.id,
            route_id="orange_line",
            agency_id=agency.id,
            route_short_name="2",
            route_long_name="Ligne Orange",
            route_type=1,  # Metro
            route_color="ED8C21",  # STM Orange
            route_text_color="FFFFFF",
        )
        self.db.add(orange_route)

        # Blue Line - Ligne Bleue
        blue_route = Route(
            feed_id=feed.id,
            route_id="blue_line",
            agency_id=agency.id,
            route_short_name="5",
            route_long_name="Ligne Bleue",
            route_type=1,  # Metro
            route_color="0078C9",  # STM Blue
            route_text_color="FFFFFF",
        )
        self.db.add(blue_route)

        # 747 Express Bus
        bus_route = Route(
            feed_id=feed.id,
            route_id="bus_747",
            agency_id=agency.id,
            route_short_name="747",
            route_long_name="747 Express YUL Aéroport",
            route_type=3,  # Bus
            route_color="E02D2D",  # Red for express bus
            route_text_color="FFFFFF",
        )
        self.db.add(bus_route)
        await self.db.flush()

        # Create Shapes for Green Line
        green_shape_points = [
            (45.5154, -73.5640, 0),
            (45.5118, -73.5662, 1),
            (45.5082, -73.5684, 2),
            (45.5061, -73.5704, 3),
            (45.5040, -73.5724, 4),
            (45.5025, -73.5742, 5),
            (45.5010, -73.5760, 6),
            (45.4988, -73.5778, 7),
            (45.4966, -73.5796, 8),
        ]

        green_shape_first = None
        for lat, lon, seq in green_shape_points:
            shape = Shape(
                feed_id=feed.id,
                shape_id="green_shape",
                shape_pt_lat=lat,
                shape_pt_lon=lon,
                shape_pt_sequence=seq,
            )
            self.db.add(shape)
            if green_shape_first is None:
                green_shape_first = shape
        await self.db.flush()

        # Create Shapes for Orange Line
        orange_shape_points = [
            (45.5102, -73.5567, 0),
            (45.5082, -73.5583, 1),
            (45.5061, -73.5599, 2),
            (45.5039, -73.5615, 3),
            (45.5016, -73.5631, 4),
            (45.4996, -73.5650, 5),
            (45.4975, -73.5668, 6),
            (45.4959, -73.5689, 7),
            (45.4943, -73.5709, 8),
        ]

        orange_shape_first = None
        for lat, lon, seq in orange_shape_points:
            shape = Shape(
                feed_id=feed.id,
                shape_id="orange_shape",
                shape_pt_lat=lat,
                shape_pt_lon=lon,
                shape_pt_sequence=seq,
            )
            self.db.add(shape)
            if orange_shape_first is None:
                orange_shape_first = shape
        await self.db.flush()

        # Create Shapes for Blue Line
        blue_shape_points = [
            (45.5394, -73.6135, 0),
            (45.5375, -73.6168, 1),
            (45.5356, -73.6200, 2),
            (45.5331, -73.6220, 3),
            (45.5306, -73.6240, 4),
            (45.5273, -73.6199, 5),
            (45.5239, -73.6157, 6),
        ]

        blue_shape_first = None
        for lat, lon, seq in blue_shape_points:
            shape = Shape(
                feed_id=feed.id,
                shape_id="blue_shape",
                shape_pt_lat=lat,
                shape_pt_lon=lon,
                shape_pt_sequence=seq,
            )
            self.db.add(shape)
            if blue_shape_first is None:
                blue_shape_first = shape
        await self.db.flush()

        # Create Shapes for 747 Bus
        bus_shape_points = [
            (45.5162, -73.5628, 0),
            (45.5050, -73.5700, 1),
            (45.4940, -73.5750, 2),
            (45.4829, -73.5795, 3),
            (45.4750, -73.6200, 4),
            (45.4680, -73.6600, 5),
            (45.4620, -73.7000, 6),
            (45.4576, -73.7497, 7),
        ]

        bus_shape_first = None
        for lat, lon, seq in bus_shape_points:
            shape = Shape(
                feed_id=feed.id,
                shape_id="bus_747_shape",
                shape_pt_lat=lat,
                shape_pt_lon=lon,
                shape_pt_sequence=seq,
            )
            self.db.add(shape)
            if bus_shape_first is None:
                bus_shape_first = shape
        await self.db.flush()

        # Create Trips and StopTimes for all routes

        # Green Line trips
        green_trips_data = [
            {"trip_id": "green_trip_1", "headsign": "Angrignon", "direction": 0, "times": ["07:00:00", "07:03:00", "07:06:00", "07:09:00", "07:12:00"]},
            {"trip_id": "green_trip_2", "headsign": "Honoré-Beaugrand", "direction": 1, "times": ["07:30:00", "07:33:00", "07:36:00", "07:39:00", "07:42:00"]},
        ]
        green_stop_ids = ["green_1", "green_2", "green_3", "green_4", "green_5"]

        for trip_data in green_trips_data:
            trip = Trip(
                feed_id=feed.id,
                route_id=green_route.route_id,
                service_id=weekday_calendar.service_id,
                trip_id=trip_data["trip_id"],
                trip_headsign=trip_data["headsign"],
                direction_id=trip_data["direction"],
                shape_id=green_shape_first.shape_id,
            )
            self.db.add(trip)
            await self.db.flush()

            stop_order = green_stop_ids if trip_data["direction"] == 0 else list(reversed(green_stop_ids))
            for seq, (stop_id, time) in enumerate(zip(stop_order, trip_data["times"])):
                stop_time = StopTime(
                    feed_id=feed.id,
                    trip_id=trip.trip_id,
                    stop_id=stops[stop_id].stop_id,
                    arrival_time=time,
                    departure_time=time,
                    stop_sequence=seq + 1,
                )
                self.db.add(stop_time)

        # Orange Line trips
        orange_trips_data = [
            {"trip_id": "orange_trip_1", "headsign": "Côte-Vertu", "direction": 0, "times": ["06:45:00", "06:48:00", "06:51:00", "06:54:00", "06:57:00"]},
            {"trip_id": "orange_trip_2", "headsign": "Montmorency", "direction": 1, "times": ["07:15:00", "07:18:00", "07:21:00", "07:24:00", "07:27:00"]},
        ]
        orange_stop_ids = ["orange_1", "orange_2", "orange_3", "orange_4", "orange_5"]

        for trip_data in orange_trips_data:
            trip = Trip(
                feed_id=feed.id,
                route_id=orange_route.route_id,
                service_id=weekday_calendar.service_id,
                trip_id=trip_data["trip_id"],
                trip_headsign=trip_data["headsign"],
                direction_id=trip_data["direction"],
                shape_id=orange_shape_first.shape_id,
            )
            self.db.add(trip)
            await self.db.flush()

            stop_order = orange_stop_ids if trip_data["direction"] == 0 else list(reversed(orange_stop_ids))
            for seq, (stop_id, time) in enumerate(zip(stop_order, trip_data["times"])):
                stop_time = StopTime(
                    feed_id=feed.id,
                    trip_id=trip.trip_id,
                    stop_id=stops[stop_id].stop_id,
                    arrival_time=time,
                    departure_time=time,
                    stop_sequence=seq + 1,
                )
                self.db.add(stop_time)

        # Blue Line trips
        blue_trips_data = [
            {"trip_id": "blue_trip_1", "headsign": "Snowdon", "direction": 0, "times": ["07:10:00", "07:14:00", "07:18:00", "07:22:00"]},
            {"trip_id": "blue_trip_2", "headsign": "Saint-Michel", "direction": 1, "times": ["07:40:00", "07:44:00", "07:48:00", "07:52:00"]},
        ]
        blue_stop_ids = ["blue_1", "blue_2", "blue_3", "blue_4"]

        for trip_data in blue_trips_data:
            trip = Trip(
                feed_id=feed.id,
                route_id=blue_route.route_id,
                service_id=weekday_calendar.service_id,
                trip_id=trip_data["trip_id"],
                trip_headsign=trip_data["headsign"],
                direction_id=trip_data["direction"],
                shape_id=blue_shape_first.shape_id,
            )
            self.db.add(trip)
            await self.db.flush()

            stop_order = blue_stop_ids if trip_data["direction"] == 0 else list(reversed(blue_stop_ids))
            for seq, (stop_id, time) in enumerate(zip(stop_order, trip_data["times"])):
                stop_time = StopTime(
                    feed_id=feed.id,
                    trip_id=trip.trip_id,
                    stop_id=stops[stop_id].stop_id,
                    arrival_time=time,
                    departure_time=time,
                    stop_sequence=seq + 1,
                )
                self.db.add(stop_time)

        # 747 Bus trips
        bus_trips_data = [
            {"trip_id": "bus_trip_1", "headsign": "Aéroport", "direction": 0, "times": ["06:00:00", "06:25:00", "06:55:00"]},
            {"trip_id": "bus_trip_2", "headsign": "Centre-ville", "direction": 1, "times": ["07:00:00", "07:30:00", "08:00:00"]},
        ]
        bus_stop_ids = ["bus_1", "bus_2", "bus_3"]

        for trip_data in bus_trips_data:
            trip = Trip(
                feed_id=feed.id,
                route_id=bus_route.route_id,
                service_id=weekday_calendar.service_id,
                trip_id=trip_data["trip_id"],
                trip_headsign=trip_data["headsign"],
                direction_id=trip_data["direction"],
                shape_id=bus_shape_first.shape_id,
            )
            self.db.add(trip)
            await self.db.flush()

            stop_order = bus_stop_ids if trip_data["direction"] == 0 else list(reversed(bus_stop_ids))
            for seq, (stop_id, time) in enumerate(zip(stop_order, trip_data["times"])):
                stop_time = StopTime(
                    feed_id=feed.id,
                    trip_id=trip.trip_id,
                    stop_id=stops[stop_id].stop_id,
                    arrival_time=time,
                    departure_time=time,
                    stop_sequence=seq + 1,
                )
                self.db.add(stop_time)

        # Weekend trips (reduced service on Saturday and Sunday)
        # Green Line weekend trips
        green_weekend_trips_data = [
            {"trip_id": "green_trip_weekend_1", "headsign": "Angrignon", "direction": 0, "times": ["08:00:00", "08:04:00", "08:08:00", "08:12:00", "08:16:00"]},
        ]

        for trip_data in green_weekend_trips_data:
            trip = Trip(
                feed_id=feed.id,
                route_id=green_route.route_id,
                service_id=weekend_calendar.service_id,
                trip_id=trip_data["trip_id"],
                trip_headsign=trip_data["headsign"],
                direction_id=trip_data["direction"],
                shape_id=green_shape_first.shape_id,
            )
            self.db.add(trip)
            await self.db.flush()

            stop_order = green_stop_ids if trip_data["direction"] == 0 else list(reversed(green_stop_ids))
            for seq, (stop_id, time) in enumerate(zip(stop_order, trip_data["times"])):
                stop_time = StopTime(
                    feed_id=feed.id,
                    trip_id=trip.trip_id,
                    stop_id=stops[stop_id].stop_id,
                    arrival_time=time,
                    departure_time=time,
                    stop_sequence=seq + 1,
                )
                self.db.add(stop_time)

        # Orange Line weekend trips
        orange_weekend_trips_data = [
            {"trip_id": "orange_trip_weekend_1", "headsign": "Côte-Vertu", "direction": 0, "times": ["08:30:00", "08:34:00", "08:38:00", "08:42:00", "08:46:00"]},
        ]

        for trip_data in orange_weekend_trips_data:
            trip = Trip(
                feed_id=feed.id,
                route_id=orange_route.route_id,
                service_id=weekend_calendar.service_id,
                trip_id=trip_data["trip_id"],
                trip_headsign=trip_data["headsign"],
                direction_id=trip_data["direction"],
                shape_id=orange_shape_first.shape_id,
            )
            self.db.add(trip)
            await self.db.flush()

            stop_order = orange_stop_ids if trip_data["direction"] == 0 else list(reversed(orange_stop_ids))
            for seq, (stop_id, time) in enumerate(zip(stop_order, trip_data["times"])):
                stop_time = StopTime(
                    feed_id=feed.id,
                    trip_id=trip.trip_id,
                    stop_id=stops[stop_id].stop_id,
                    arrival_time=time,
                    departure_time=time,
                    stop_sequence=seq + 1,
                )
                self.db.add(stop_time)

        await self.db.commit()

        # Create GTFS-RT feed sources for all supported types
        # These point to our demo endpoints that simulate real-time data

        # 1. Vehicle Positions feed source
        vehicle_positions_feed = ExternalFeedSource(
            name="Demo Vehicle Positions",
            description="Simulated real-time vehicle positions for demo trips",
            source_type=FeedSourceType.GTFS_RT_VEHICLE_POSITIONS.value,
            url=f"/api/v1/demo/agency/{agency.id}/vehicle-positions",
            agency_id=agency.id,
            is_enabled=True,
            auto_import=False,
            status=FeedSourceStatus.ACTIVE.value,
            check_frequency=CheckFrequency.DAILY.value,
            error_count=0,
        )
        self.db.add(vehicle_positions_feed)

        # 2. Trip Updates feed source (delays)
        trip_updates_feed = ExternalFeedSource(
            name="Demo Trip Updates",
            description="Simulated real-time trip updates with delays for demo trips",
            source_type=FeedSourceType.GTFS_RT_TRIP_UPDATES.value,
            url=f"/api/v1/demo/agency/{agency.id}/trip-updates",
            agency_id=agency.id,
            is_enabled=True,
            auto_import=False,
            status=FeedSourceStatus.ACTIVE.value,
            check_frequency=CheckFrequency.DAILY.value,
            error_count=0,
        )
        self.db.add(trip_updates_feed)

        # 3. Service Alerts feed source
        alerts_feed = ExternalFeedSource(
            name="Demo Service Alerts",
            description="Simulated service alerts demonstrating weather, maintenance, and other advisories",
            source_type=FeedSourceType.GTFS_RT_ALERTS.value,
            url=f"/api/v1/demo/agency/{agency.id}/alerts",
            agency_id=agency.id,
            is_enabled=True,
            auto_import=False,
            status=FeedSourceStatus.ACTIVE.value,
            check_frequency=CheckFrequency.DAILY.value,
            error_count=0,
        )
        self.db.add(alerts_feed)

        # 4. Trip Modifications feed source (detours - experimental)
        trip_modifications_feed = ExternalFeedSource(
            name="Demo Trip Modifications",
            description="Simulated trip modifications demonstrating detours (experimental GTFS-RT extension)",
            source_type=FeedSourceType.GTFS_RT_TRIP_MODIFICATIONS.value,
            url=f"/api/v1/demo/agency/{agency.id}/trip-modifications",
            agency_id=agency.id,
            is_enabled=True,
            auto_import=False,
            status=FeedSourceStatus.ACTIVE.value,
            check_frequency=CheckFrequency.DAILY.value,
            error_count=0,
        )
        self.db.add(trip_modifications_feed)

        # 5. Shapes feed source (replacement shapes for detours - experimental)
        shapes_feed = ExternalFeedSource(
            name="Demo RT Shapes",
            description="Simulated real-time shapes demonstrating detour paths (experimental GTFS-RT extension)",
            source_type=FeedSourceType.GTFS_RT_SHAPES.value,
            url=f"/api/v1/demo/agency/{agency.id}/shapes",
            agency_id=agency.id,
            is_enabled=True,
            auto_import=False,
            status=FeedSourceStatus.ACTIVE.value,
            check_frequency=CheckFrequency.DAILY.value,
            error_count=0,
        )
        self.db.add(shapes_feed)

        # 6. Stops feed source (replacement stops for detours - experimental)
        stops_feed = ExternalFeedSource(
            name="Demo RT Stops",
            description="Simulated real-time stops demonstrating temporary detour stops (experimental GTFS-RT extension)",
            source_type=FeedSourceType.GTFS_RT_STOPS.value,
            url=f"/api/v1/demo/agency/{agency.id}/stops",
            agency_id=agency.id,
            is_enabled=True,
            auto_import=False,
            status=FeedSourceStatus.ACTIVE.value,
            check_frequency=CheckFrequency.DAILY.value,
            error_count=0,
        )
        self.db.add(stops_feed)

        await self.db.commit()

        logger.info(f"Created demo agency '{agency.name}' (ID: {agency.id}) for user {user.email}")

        return agency


async def create_demo_agency_for_user(db: AsyncSession, user: User) -> Agency:
    """Helper function to create demo agency for a user"""
    service = DemoAgencyService(db)
    return await service.create_demo_agency_for_user(user)
