"""Calendar (GTFS service schedules) schemas for API requests and responses"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date


class CalendarBase(BaseModel):
    """Base calendar schema"""

    service_id: str = Field(..., min_length=1, max_length=255, description="GTFS service_id")
    monday: bool = Field(default=False, description="Service runs on Mondays")
    tuesday: bool = Field(default=False, description="Service runs on Tuesdays")
    wednesday: bool = Field(default=False, description="Service runs on Wednesdays")
    thursday: bool = Field(default=False, description="Service runs on Thursdays")
    friday: bool = Field(default=False, description="Service runs on Fridays")
    saturday: bool = Field(default=False, description="Service runs on Saturdays")
    sunday: bool = Field(default=False, description="Service runs on Sundays")
    start_date: str = Field(..., pattern=r"^\d{8}$", description="Start date (YYYYMMDD)")
    end_date: str = Field(..., pattern=r"^\d{8}$", description="End date (YYYYMMDD)")
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields from GTFS")

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_gtfs_date(cls, v: str) -> str:
        """Validate GTFS date format (YYYYMMDD)"""
        if len(v) != 8:
            raise ValueError("Date must be in YYYYMMDD format (8 digits)")
        try:
            # Validate it's a real date
            year = int(v[:4])
            month = int(v[4:6])
            day = int(v[6:8])
            date(year, month, day)
        except ValueError as e:
            raise ValueError(f"Invalid date: {e}")
        return v

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: str, info) -> str:
        """Ensure end_date >= start_date"""
        if "start_date" in info.data and v < info.data["start_date"]:
            raise ValueError("end_date must be greater than or equal to start_date")
        return v


class CalendarExceptionInput(BaseModel):
    """Schema for exception input when creating calendar with exceptions"""

    date: str = Field(..., pattern=r"^\d{8}$", description="Exception date (YYYYMMDD)")
    exception_type: int = Field(..., ge=1, le=2, description="1=service added, 2=service removed")

    @field_validator("date")
    @classmethod
    def validate_gtfs_date(cls, v: str) -> str:
        """Validate GTFS date format"""
        if len(v) != 8:
            raise ValueError("Date must be in YYYYMMDD format (8 digits)")
        try:
            year = int(v[:4])
            month = int(v[4:6])
            day = int(v[6:8])
            date(year, month, day)
        except ValueError as e:
            raise ValueError(f"Invalid date: {e}")
        return v


class CalendarCreate(CalendarBase):
    """Schema for creating a new calendar/service"""

    feed_id: int = Field(..., description="Feed ID this calendar belongs to")
    exceptions: Optional[List[CalendarExceptionInput]] = Field(
        None,
        description="Optional list of calendar exceptions to create atomically"
    )


class CalendarUpdate(BaseModel):
    """Schema for updating a calendar"""

    service_id: Optional[str] = Field(None, min_length=1, max_length=255)
    monday: Optional[bool] = None
    tuesday: Optional[bool] = None
    wednesday: Optional[bool] = None
    thursday: Optional[bool] = None
    friday: Optional[bool] = None
    saturday: Optional[bool] = None
    sunday: Optional[bool] = None
    start_date: Optional[str] = Field(None, pattern=r"^\d{8}$")
    end_date: Optional[str] = Field(None, pattern=r"^\d{8}$")
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields from GTFS")


class CalendarResponse(CalendarBase):
    """Schema for calendar response"""

    feed_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CalendarWithStats(CalendarResponse):
    """Calendar response with statistics"""

    trip_count: int = Field(default=0, description="Number of trips using this service")
    exception_count: int = Field(default=0, description="Number of calendar date exceptions")


# Calendar Date (exceptions)


class CalendarDateBase(BaseModel):
    """Base calendar date schema"""

    date: str = Field(..., pattern=r"^\d{8}$", description="Exception date (YYYYMMDD)")
    exception_type: int = Field(..., ge=1, le=2, description="1=service added, 2=service removed")

    @field_validator("date")
    @classmethod
    def validate_gtfs_date(cls, v: str) -> str:
        """Validate GTFS date format"""
        if len(v) != 8:
            raise ValueError("Date must be in YYYYMMDD format (8 digits)")
        try:
            year = int(v[:4])
            month = int(v[4:6])
            day = int(v[6:8])
            date(year, month, day)
        except ValueError as e:
            raise ValueError(f"Invalid date: {e}")
        return v


class CalendarDateCreate(CalendarDateBase):
    """Schema for creating a calendar date exception via API endpoint.

    Note: service_id and feed_id are taken from the URL path parameters,
    so they are not required in the request body.
    """
    pass


class CalendarDateUpdate(BaseModel):
    """Schema for updating a calendar date"""

    date: Optional[str] = Field(None, pattern=r"^\d{8}$")
    exception_type: Optional[int] = Field(None, ge=1, le=2)


class CalendarDateResponse(CalendarDateBase):
    """Schema for calendar date response"""

    feed_id: int
    service_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# List and pagination schemas


class CalendarList(BaseModel):
    """Paginated list of calendars"""

    items: List[CalendarResponse] = Field(..., description="List of calendars/services")
    total: int = Field(..., description="Total number of calendars")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


class CalendarListWithStats(BaseModel):
    """Paginated list of calendars with statistics"""

    items: List[CalendarWithStats] = Field(..., description="List of calendars with stats")
    total: int = Field(..., description="Total number of calendars")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")


class CalendarDateList(BaseModel):
    """List of calendar date exceptions"""

    items: List[CalendarDateResponse] = Field(..., description="List of calendar dates")
    total: int = Field(..., description="Total number of exceptions")


# Helper schemas


class ServiceDaysSummary(BaseModel):
    """Summary of service days"""

    weekdays: bool = Field(..., description="Service runs Monday-Friday")
    weekends: bool = Field(..., description="Service runs Saturday-Sunday")
    days_of_week: List[str] = Field(..., description="List of days service runs")
    start_date: str
    end_date: str
    total_exceptions: int = Field(default=0, description="Number of date exceptions")


class CalendarWithSummary(CalendarResponse):
    """Calendar with human-readable summary"""

    summary: ServiceDaysSummary


# Bulk operations


class CalendarImport(BaseModel):
    """Schema for importing calendars from GTFS"""

    calendars: List[CalendarCreate] = Field(..., description="List of calendars to import")
    replace_existing: bool = Field(default=False, description="Replace existing calendars with same service_id")


class CalendarImportResult(BaseModel):
    """Result of calendar import operation"""

    created: int = Field(..., description="Number of calendars created")
    updated: int = Field(..., description="Number of calendars updated")
    skipped: int = Field(..., description="Number of calendars skipped")
    errors: List[str] = Field(default_factory=list, description="List of errors encountered")
