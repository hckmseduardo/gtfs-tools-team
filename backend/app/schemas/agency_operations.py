"""Schemas for agency merge and split operations"""

from typing import Optional, List
from pydantic import BaseModel, Field


# ============================================================================
# Merge Agencies Schemas
# ============================================================================

class AgencyMergeRequest(BaseModel):
    """Request schema for merging multiple feeds from agencies"""

    source_feed_ids: List[int] = Field(
        ...,
        min_length=2,
        description="List of source feed IDs to merge (minimum 2)"
    )
    target_agency_id: Optional[int] = Field(
        None,
        description="Target agency ID where merged data will be created (required if create_new_agency is False)"
    )
    create_new_agency: bool = Field(
        default=False,
        description="Whether to create a new agency for the merged data"
    )
    new_agency_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Name for the new agency (required if create_new_agency is True)"
    )
    new_agency_description: Optional[str] = Field(
        None,
        description="Optional description for the new agency"
    )
    merge_strategy: str = Field(
        default="fail_on_conflict",
        description="Strategy for handling ID conflicts: 'fail_on_conflict' or 'auto_prefix'"
    )
    feed_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name for the new merged feed"
    )
    feed_description: Optional[str] = Field(
        None,
        description="Optional description for the merged feed"
    )
    activate_on_success: bool = Field(
        default=True,
        description="Whether to activate the merged feed immediately on success"
    )


class FeedEntityCounts(BaseModel):
    """Entity counts for a single feed"""

    feed_id: int = Field(..., description="Feed ID")
    feed_name: str = Field(..., description="Feed name")
    agency_id: int = Field(..., description="Agency ID this feed belongs to")
    agency_name: str = Field(..., description="Agency name")
    routes: int = Field(default=0, description="Number of routes")
    trips: int = Field(default=0, description="Number of trips")
    stops: int = Field(default=0, description="Number of stops")
    stop_times: int = Field(default=0, description="Number of stop times")
    shapes: int = Field(default=0, description="Number of unique shapes")
    calendars: int = Field(default=0, description="Number of calendar entries")
    calendar_dates: int = Field(default=0, description="Number of calendar date exceptions")
    fare_attributes: int = Field(default=0, description="Number of fare attributes")
    fare_rules: int = Field(default=0, description="Number of fare rules")


class IDConflict(BaseModel):
    """Schema for representing an ID conflict"""

    entity_type: str = Field(..., description="Type of entity (route, trip, shape, stop)")
    conflicting_id: str = Field(..., description="The ID that conflicts")
    source_agencies: List[int] = Field(..., description="Agency IDs where this ID exists")
    count: int = Field(..., description="Number of occurrences")


class AgencyMergeValidationResult(BaseModel):
    """Result of merge validation before execution"""

    valid: bool = Field(..., description="Whether the merge can proceed")
    conflicts: List[IDConflict] = Field(default_factory=list, description="List of ID conflicts found")

    # Per-feed entity counts
    feed_counts: List[FeedEntityCounts] = Field(default_factory=list, description="Entity counts per feed")

    # Expected totals after merge
    total_routes: int = Field(default=0, description="Expected total routes after merge")
    total_trips: int = Field(default=0, description="Expected total trips after merge")
    total_stops: int = Field(default=0, description="Expected total stops after merge")
    total_stop_times: int = Field(default=0, description="Expected total stop times after merge")
    total_shapes: int = Field(default=0, description="Expected total unique shapes after merge")
    total_calendars: int = Field(default=0, description="Expected total calendar entries after merge")
    total_calendar_dates: int = Field(default=0, description="Expected total calendar dates after merge")
    total_fare_attributes: int = Field(default=0, description="Expected total fare attributes after merge")
    total_fare_rules: int = Field(default=0, description="Expected total fare rules after merge")

    warnings: List[str] = Field(default_factory=list, description="Warning messages")
    errors: List[str] = Field(default_factory=list, description="Error messages")


class AgencyMergeResponse(BaseModel):
    """Response after initiating a merge operation"""

    task_id: str = Field(..., description="Celery task ID for tracking progress")
    new_agency_id: Optional[int] = Field(None, description="ID of the newly created agency (if create_new_agency was True)")
    new_feed_id: Optional[int] = Field(None, description="ID of the newly created feed (if created synchronously)")
    status: str = Field(..., description="Status: 'queued', 'validating', or 'failed'")
    message: str = Field(..., description="Status message")
    validation_result: Optional[AgencyMergeValidationResult] = Field(None, description="Validation results if validation failed")


# ============================================================================
# Split Agency Schemas
# ============================================================================

class AgencySplitRequest(BaseModel):
    """Request schema for splitting routes from an agency"""

    feed_id: int = Field(..., description="Feed ID containing the routes to split")
    route_ids: List[str] = Field(
        ...,
        min_length=1,
        description="List of route IDs to split into new agency"
    )
    new_agency_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name for the new agency"
    )
    new_agency_description: Optional[str] = Field(
        None,
        description="Optional description for the new agency"
    )
    new_feed_name: str = Field(
        default="Initial Feed",
        description="Name for the feed in the new agency"
    )
    copy_users: bool = Field(
        default=False,
        description="Whether to copy users from source agency to new agency"
    )
    remove_from_source: bool = Field(
        default=False,
        description="Whether to remove routes from source agency after split"
    )


class AgencySplitDependencies(BaseModel):
    """Schema showing dependencies that will be copied during split"""

    routes: List[str] = Field(default_factory=list, description="Route IDs to be copied")
    trips: int = Field(default=0, description="Number of trips to be copied")
    stops: int = Field(default=0, description="Number of stops to be copied")
    stop_times: int = Field(default=0, description="Number of stop times to be copied")
    calendars: int = Field(default=0, description="Number of calendar entries to be copied")
    calendar_dates: int = Field(default=0, description="Number of calendar dates to be copied")
    shapes: int = Field(default=0, description="Number of shape points to be copied")
    shared_stops: int = Field(default=0, description="Number of stops shared with remaining routes")


class AgencySplitResponse(BaseModel):
    """Response after initiating a split operation"""

    task_id: str = Field(..., description="Celery task ID for tracking progress")
    new_agency_id: int = Field(..., description="ID of the newly created agency")
    new_feed_id: Optional[int] = Field(None, description="ID of the newly created feed")
    status: str = Field(..., description="Status: 'queued' or 'failed'")
    message: str = Field(..., description="Status message")
    dependencies: Optional[AgencySplitDependencies] = Field(None, description="Dependencies that will be copied")


# ============================================================================
# Common Schemas
# ============================================================================

class MergeReportStats(BaseModel):
    """Statistics from a completed merge operation"""

    # Actual counts after merge
    routes_merged: int = Field(default=0, description="Total routes in merged feed")
    trips_merged: int = Field(default=0, description="Total trips in merged feed")
    stops_merged: int = Field(default=0, description="Total stops in merged feed")
    stop_times_merged: int = Field(default=0, description="Total stop times in merged feed")
    shapes_merged: int = Field(default=0, description="Total unique shapes in merged feed")
    calendars_merged: int = Field(default=0, description="Total calendar entries in merged feed")
    calendar_dates_merged: int = Field(default=0, description="Total calendar dates in merged feed")
    fare_attributes_merged: int = Field(default=0, description="Total fare attributes in merged feed")
    fare_rules_merged: int = Field(default=0, description="Total fare rules in merged feed")

    # Actions performed
    stops_deduplicated: int = Field(default=0, description="Number of duplicate stops merged")
    ids_prefixed: int = Field(default=0, description="Number of IDs that were prefixed to avoid conflicts")
    conflicts_auto_resolved: int = Field(default=0, description="Number of conflicts auto-resolved")

    # Validation
    validation_errors: int = Field(default=0, description="Number of validation errors found")
    validation_warnings: int = Field(default=0, description="Number of validation warnings found")
    count_mismatches: List[str] = Field(default_factory=list, description="Entity types where counts didn't match expected")


class SplitReportStats(BaseModel):
    """Statistics from a completed split operation"""

    routes_copied: int = Field(default=0)
    trips_copied: int = Field(default=0)
    stops_copied: int = Field(default=0)
    stop_times_copied: int = Field(default=0)
    shapes_copied: int = Field(default=0)
    calendars_copied: int = Field(default=0)
    calendar_dates_copied: int = Field(default=0)
    routes_removed_from_source: int = Field(default=0)
