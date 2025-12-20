"""API v1 router"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, auth_entra, agencies, users, routes, stops, trips, calendars, stop_times, shapes, feeds, gtfs_io, tasks, audit, feed_sources, realtime, fare_attributes, fare_rules, feed_info, teams, workspaces, demo, routing, route_creator, team_context, geocoding

api_router = APIRouter()

# Include authentication endpoints
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
# Include Entra ID authentication endpoints (new, simplified approach)
api_router.include_router(auth_entra.router, tags=["entra-authentication"])

# Include agency management endpoints
api_router.include_router(agencies.router, prefix="/agencies", tags=["agencies"])

# Include user management endpoints
api_router.include_router(users.router, prefix="/users", tags=["users"])

# Include GTFS feed management endpoints
api_router.include_router(feeds.router, prefix="/feeds", tags=["gtfs-feeds"])

# Include nested GTFS entity endpoints (under /feeds/{feed_id})
# These use composite primary keys (feed_id, entity_string_id)
api_router.include_router(stops.router, prefix="/feeds/{feed_id}/stops", tags=["gtfs-stops"])
api_router.include_router(routes.router, prefix="/feeds/{feed_id}/routes", tags=["gtfs-routes"])
api_router.include_router(trips.router, prefix="/feeds/{feed_id}/trips", tags=["gtfs-trips"])
api_router.include_router(calendars.router, prefix="/feeds/{feed_id}/calendars", tags=["gtfs-calendars"])
api_router.include_router(stop_times.router, prefix="/feeds/{feed_id}/stop-times", tags=["gtfs-stop-times"])
api_router.include_router(shapes.router, prefix="/feeds/{feed_id}/shapes", tags=["gtfs-shapes"])
api_router.include_router(fare_attributes.router, prefix="/feeds/{feed_id}/fare-attributes", tags=["gtfs-fare-attributes"])
api_router.include_router(fare_rules.router, prefix="/feeds/{feed_id}/fare-rules", tags=["gtfs-fare-rules"])
api_router.include_router(feed_info.router, prefix="/feeds/{feed_id}/feed-info", tags=["gtfs-feed-info"])

# Include GTFS Import/Export endpoints
api_router.include_router(gtfs_io.router, prefix="/gtfs", tags=["gtfs-import-export"])

# Include task management endpoints
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])

# Include audit log endpoints
api_router.include_router(audit.router, prefix="/audit", tags=["audit-logs"])

# Include feed source monitoring endpoints
api_router.include_router(feed_sources.router, prefix="/feed-sources", tags=["feed-sources"])

# Include GTFS-Realtime endpoints
api_router.include_router(realtime.router, prefix="/realtime", tags=["gtfs-realtime"])

# Include team and workspace management endpoints
api_router.include_router(teams.router, prefix="/teams", tags=["teams"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])

# Include team context endpoints (for multi-tenant subdomain-based access)
api_router.include_router(team_context.router, prefix="/team", tags=["team-context"])

# Include demo endpoints for simulated GTFS-RT data
api_router.include_router(demo.router, prefix="/demo", tags=["demo"])

# Include routing endpoints for OSM-based shape improvements
api_router.include_router(routing.router, prefix="/routing", tags=["routing"])

# Include Route Creator endpoints for creating routes from in-memory data
api_router.include_router(route_creator.router, prefix="/route-creator", tags=["route-creator"])

# Include geocoding endpoints for address lookup
api_router.include_router(geocoding.router, prefix="/geocoding", tags=["geocoding"])
