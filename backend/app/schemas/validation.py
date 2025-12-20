"""Validation preferences schemas"""

from pydantic import BaseModel, ConfigDict


class AgencyValidationPreferencesBase(BaseModel):
    """Base schema for validation preferences"""

    # Routes validations (3)
    validate_route_agency: bool = True
    validate_route_duplicates: bool = True
    validate_route_mandatory: bool = True

    # Shapes validations (4)
    validate_shape_dist_traveled: bool = True
    validate_shape_dist_accuracy: bool = True
    validate_shape_sequence: bool = True
    validate_shape_mandatory: bool = True

    # Calendar validations (1)
    validate_calendar_mandatory: bool = True

    # Calendar dates validations (1)
    validate_calendar_date_mandatory: bool = True

    # Fare attributes validations (1)
    validate_fare_attribute_mandatory: bool = True

    # Feed info validations (1)
    validate_feed_info_mandatory: bool = True

    # Stops validations (2)
    validate_stop_duplicates: bool = True
    validate_stop_mandatory: bool = True

    # Trips validations (4)
    validate_trip_service: bool = True
    validate_trip_duplicates: bool = True
    validate_trip_shape: bool = True
    validate_trip_mandatory: bool = True

    # Stop times validations (4)
    validate_stop_time_trip: bool = True
    validate_stop_time_stop: bool = True
    validate_stop_time_sequence: bool = True
    validate_stop_time_mandatory: bool = True

    # Additional settings
    custom_settings: dict | None = None


class AgencyValidationPreferencesCreate(AgencyValidationPreferencesBase):
    """Schema for creating validation preferences"""

    agency_id: int


class AgencyValidationPreferencesUpdate(AgencyValidationPreferencesBase):
    """Schema for updating validation preferences - all fields optional"""

    validate_route_agency: bool | None = None
    validate_route_duplicates: bool | None = None
    validate_route_mandatory: bool | None = None
    validate_shape_dist_traveled: bool | None = None
    validate_shape_dist_accuracy: bool | None = None
    validate_shape_sequence: bool | None = None
    validate_shape_mandatory: bool | None = None
    validate_calendar_mandatory: bool | None = None
    validate_calendar_date_mandatory: bool | None = None
    validate_fare_attribute_mandatory: bool | None = None
    validate_feed_info_mandatory: bool | None = None
    validate_stop_duplicates: bool | None = None
    validate_stop_mandatory: bool | None = None
    validate_trip_service: bool | None = None
    validate_trip_duplicates: bool | None = None
    validate_trip_shape: bool | None = None
    validate_trip_mandatory: bool | None = None
    validate_stop_time_trip: bool | None = None
    validate_stop_time_stop: bool | None = None
    validate_stop_time_sequence: bool | None = None
    validate_stop_time_mandatory: bool | None = None
    custom_settings: dict | None = None


class AgencyValidationPreferencesResponse(AgencyValidationPreferencesBase):
    """Schema for validation preferences response"""

    id: int
    agency_id: int

    model_config = ConfigDict(from_attributes=True)


class ValidationRuleSummary(BaseModel):
    """Summary of validation rules by entity"""

    routes: dict[str, bool]
    shapes: dict[str, bool]
    calendar: dict[str, bool]
    calendar_dates: dict[str, bool]
    fare_attributes: dict[str, bool]
    feed_info: dict[str, bool]
    stops: dict[str, bool]
    trips: dict[str, bool]
    stop_times: dict[str, bool]


class EnabledValidationsResponse(BaseModel):
    """Response showing which validations are enabled"""

    agency_id: int
    enabled_rules: ValidationRuleSummary
    total_enabled: int
    total_rules: int
