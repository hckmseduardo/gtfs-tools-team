"""GTFS Import/Export schemas"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class GTFSImportOptions(BaseModel):
    """Options for GTFS import"""

    agency_id: int = Field(..., description="Agency to import data into")
    replace_existing: bool = Field(
        default=False,
        description="Replace existing GTFS data for this agency"
    )
    validate_only: bool = Field(
        default=False,
        description="Only validate, don't import"
    )
    skip_shapes: bool = Field(
        default=False,
        description="Skip importing shapes (for faster imports)"
    )
    stop_on_error: bool = Field(
        default=False,
        description="Stop import on first error (otherwise continue with warnings)"
    )


class GTFSImportProgress(BaseModel):
    """Progress update for GTFS import"""

    status: str = Field(..., description="current, completed, failed")
    current_file: Optional[str] = Field(None, description="Currently processing file")
    total_files: int = Field(default=0, description="Total files to process")
    processed_files: int = Field(default=0, description="Files processed")
    current_row: int = Field(default=0, description="Current row in file")
    total_rows: int = Field(default=0, description="Total rows in current file")
    message: Optional[str] = Field(None, description="Status message")


class GTFSFileStats(BaseModel):
    """Statistics for a single GTFS file"""

    filename: str
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0


class GTFSImportResult(BaseModel):
    """Result of GTFS import operation"""

    success: bool = Field(..., description="Whether import succeeded")
    agency_id: int
    feed_id: Optional[int] = Field(None, description="ID of the imported feed")
    files_processed: List[GTFSFileStats] = Field(default_factory=list)
    total_imported: int = Field(default=0, description="Total records imported")
    total_updated: int = Field(default=0, description="Total records updated")
    total_skipped: int = Field(default=0, description="Total records skipped")
    total_errors: int = Field(default=0, description="Total errors encountered")
    validation_errors: List[str] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime
    duration_seconds: float


class GTFSExportOptions(BaseModel):
    """Options for GTFS export"""

    agency_id: int = Field(..., description="Agency to export data from")
    feed_id: Optional[int] = Field(None, description="Specific feed to export (uses active feed if not specified)")
    include_shapes: bool = Field(default=True, description="Include shapes.txt")
    include_calendar_dates: bool = Field(default=True, description="Include calendar_dates.txt")
    date_filter_start: Optional[str] = Field(
        None,
        pattern=r"^\d{8}$",
        description="Export only services active on/after this date (YYYYMMDD)"
    )
    date_filter_end: Optional[str] = Field(
        None,
        pattern=r"^\d{8}$",
        description="Export only services active on/before this date (YYYYMMDD)"
    )
    route_ids: Optional[List[str]] = Field(
        None,
        description="Export only specific routes (by GTFS route_id)"
    )


class GTFSExportResult(BaseModel):
    """Result of GTFS export operation"""

    success: bool
    agency_id: int
    filename: str = Field(..., description="Name of generated GTFS zip file")
    file_size_bytes: int
    files_included: List[str] = Field(..., description="List of files in the export")
    record_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Number of records in each file"
    )
    warnings: List[str] = Field(default_factory=list)
    created_at: datetime


class GTFSValidationIssue(BaseModel):
    """A single validation issue"""

    severity: str = Field(..., description="error, warning, info")
    file: str = Field(..., description="GTFS file where issue was found")
    line: Optional[int] = Field(None, description="Line number (if applicable)")
    field: Optional[str] = Field(None, description="Field name (if applicable)")
    message: str = Field(..., description="Description of the issue")
    record_id: Optional[str] = Field(None, description="ID of the problematic record")


class GTFSValidationResult(BaseModel):
    """Result of GTFS validation"""

    valid: bool = Field(..., description="Whether GTFS passes validation")
    error_count: int = Field(default=0)
    warning_count: int = Field(default=0)
    info_count: int = Field(default=0)
    issues: List[GTFSValidationIssue] = Field(default_factory=list)
    files_checked: List[str] = Field(default_factory=list)
    summary: str = Field(..., description="Human-readable summary")


# Task tracking for async operations


class GTFSTask(BaseModel):
    """GTFS import/export task information"""

    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(..., description="pending, processing, completed, failed")
    operation: str = Field(..., description="import, export, validate")
    agency_id: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: Optional[GTFSImportProgress] = None
    result: Optional[Any] = None
    error: Optional[str] = None


class GTFSTaskStatus(BaseModel):
    """Current status of a GTFS task"""

    task_id: str
    status: str
    progress: Optional[GTFSImportProgress] = None
    result: Optional[Any] = None
    error: Optional[str] = None


# GTFS Analysis schemas (for 4-step wizard import)


class GTFSAgencyInfo(BaseModel):
    """Agency information extracted from agency.txt"""

    agency_id: Optional[str] = Field(None, description="GTFS agency_id from agency.txt")
    agency_name: str = Field(..., description="GTFS agency_name from agency.txt")
    agency_url: Optional[str] = Field(None, description="GTFS agency_url from agency.txt")
    agency_timezone: Optional[str] = Field(None, description="GTFS agency_timezone from agency.txt")
    agency_lang: Optional[str] = Field(None, description="GTFS agency_lang from agency.txt")
    agency_phone: Optional[str] = Field(None, description="GTFS agency_phone from agency.txt")
    agency_fare_url: Optional[str] = Field(None, description="GTFS agency_fare_url from agency.txt")
    agency_email: Optional[str] = Field(None, description="GTFS agency_email from agency.txt")


class GTFSFileSummary(BaseModel):
    """Summary of a GTFS file"""

    filename: str
    row_count: int
    columns: List[str]


class AgencyMatch(BaseModel):
    """A potential matching existing agency"""

    id: int
    name: str
    slug: str
    agency_id: Optional[str] = None
    match_score: float = Field(..., description="Match confidence 0.0-1.0")
    match_reason: str = Field(..., description="Why this is considered a match")


class GTFSAnalysisResult(BaseModel):
    """Result of GTFS file analysis (Step 2 of import wizard)"""

    upload_id: str = Field(..., description="Temporary ID to reference this upload for import")
    filename: str
    file_size_bytes: int
    agencies_in_file: List[GTFSAgencyInfo] = Field(
        ..., description="Agencies found in agency.txt (can be multiple)"
    )
    matching_agencies: List[AgencyMatch] = Field(
        default_factory=list, description="Existing agencies that might match"
    )
    files_summary: List[GTFSFileSummary] = Field(
        default_factory=list, description="Summary of files in the GTFS zip"
    )
    has_required_files: bool = Field(..., description="Whether all required GTFS files are present")
    missing_files: List[str] = Field(default_factory=list, description="Required files that are missing")
    extra_files: List[str] = Field(default_factory=list, description="Non-standard files found")
