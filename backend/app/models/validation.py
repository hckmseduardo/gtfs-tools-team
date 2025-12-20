"""Validation preferences and settings models"""

from sqlalchemy import String, Integer, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin


class AgencyValidationPreferences(Base, TimestampMixin):
    """
    Stores validation preferences per agency

    Per claude.md line 49: "we must be able to select the gtfs validations
    we want to execute and it is as parameter auto saved by agency"
    """

    __tablename__ = "agency_validation_preferences"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    agency_id: Mapped[int] = mapped_column(
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
        comment="One preferences record per agency"
    )

    # Individual validation rule toggles
    # Routes validations
    validate_route_agency: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate route without valid agency"
    )
    validate_route_duplicates: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate duplicated route_id"
    )
    validate_route_mandatory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate route mandatory fields"
    )

    # Shapes validations
    validate_shape_dist_traveled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate shape_dist_traveled are filled"
    )
    validate_shape_dist_accuracy: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate shape_dist_traveled makes sense considering lat/long"
    )
    validate_shape_sequence: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate shape_pt_sequence is filled and makes sense"
    )
    validate_shape_mandatory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate shape mandatory fields"
    )

    # Calendar validations
    validate_calendar_mandatory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate calendar mandatory fields"
    )

    # Calendar dates validations
    validate_calendar_date_mandatory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate calendar_dates mandatory fields"
    )

    # Fare attributes validations
    validate_fare_attribute_mandatory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate fare_attributes mandatory fields"
    )

    # Feed info validations
    validate_feed_info_mandatory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate feed_info mandatory fields"
    )

    # Stops validations
    validate_stop_duplicates: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate stop_id is not duplicated"
    )
    validate_stop_mandatory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate stop mandatory fields"
    )

    # Trips validations
    validate_trip_service: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate service_id is declared on calendar or calendar_dates"
    )
    validate_trip_duplicates: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate trip_id is unique"
    )
    validate_trip_shape: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate shape_id is a valid shape"
    )
    validate_trip_mandatory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate trip mandatory fields"
    )

    # Stop times validations
    validate_stop_time_trip: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate trip_id is valid and in trips list"
    )
    validate_stop_time_stop: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate stop_id is valid"
    )
    validate_stop_time_sequence: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate stop_sequence makes sense"
    )
    validate_stop_time_mandatory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Validate stop_time mandatory fields"
    )

    # Additional settings
    custom_settings: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional custom validation settings"
    )

    # Relationships
    agency: Mapped["Agency"] = relationship("Agency", back_populates="validation_preferences")

    def __repr__(self) -> str:
        return f"<AgencyValidationPreferences agency_id={self.agency_id}>"

    def get_enabled_validations(self) -> dict:
        """Return a dictionary of enabled validation rules"""
        return {
            'routes': {
                'agency': self.validate_route_agency,
                'duplicates': self.validate_route_duplicates,
                'mandatory': self.validate_route_mandatory,
            },
            'shapes': {
                'dist_traveled': self.validate_shape_dist_traveled,
                'dist_accuracy': self.validate_shape_dist_accuracy,
                'sequence': self.validate_shape_sequence,
                'mandatory': self.validate_shape_mandatory,
            },
            'calendar': {
                'mandatory': self.validate_calendar_mandatory,
            },
            'calendar_dates': {
                'mandatory': self.validate_calendar_date_mandatory,
            },
            'fare_attributes': {
                'mandatory': self.validate_fare_attribute_mandatory,
            },
            'feed_info': {
                'mandatory': self.validate_feed_info_mandatory,
            },
            'stops': {
                'duplicates': self.validate_stop_duplicates,
                'mandatory': self.validate_stop_mandatory,
            },
            'trips': {
                'service': self.validate_trip_service,
                'duplicates': self.validate_trip_duplicates,
                'shape': self.validate_trip_shape,
                'mandatory': self.validate_trip_mandatory,
            },
            'stop_times': {
                'trip': self.validate_stop_time_trip,
                'stop': self.validate_stop_time_stop,
                'sequence': self.validate_stop_time_sequence,
                'mandatory': self.validate_stop_time_mandatory,
            },
        }
