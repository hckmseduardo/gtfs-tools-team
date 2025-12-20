"""Import all models for Alembic autogenerate"""

from app.db.base_class import Base

# Import all models so Alembic can detect them
from app.models.user import User, user_agencies
from app.models.agency import Agency
from app.models.gtfs import (
    GTFSFeed,
    Stop,
    Route,
    Trip,
    StopTime,
    Calendar,
    CalendarDate,
    Shape,
    FareAttribute,
    FeedInfo,
)
from app.models.audit import AuditLog
from app.models.task import AsyncTask
from app.models.validation import AgencyValidationPreferences
from app.models.feed_source import ExternalFeedSource, FeedSourceCheckLog
from app.models.gtfs_realtime import (
    RealtimeVehiclePosition,
    RealtimeTripUpdate,
    RealtimeAlert,
    RealtimeTripModification,
)
from app.models.team import (
    Team,
    TeamMember,
    Workspace,
    TeamInvitation,
    workspace_agencies,
)

__all__ = [
    "Base",
    "User",
    "user_agencies",
    "Agency",
    "GTFSFeed",
    "Stop",
    "Route",
    "Trip",
    "StopTime",
    "Calendar",
    "CalendarDate",
    "Shape",
    "FareAttribute",
    "FeedInfo",
    "AuditLog",
    "AsyncTask",
    "AgencyValidationPreferences",
    "ExternalFeedSource",
    "FeedSourceCheckLog",
    "RealtimeVehiclePosition",
    "RealtimeTripUpdate",
    "RealtimeAlert",
    "RealtimeTripModification",
    "Team",
    "TeamMember",
    "Workspace",
    "TeamInvitation",
    "workspace_agencies",
]
