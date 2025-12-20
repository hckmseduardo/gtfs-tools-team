"""convert to composite primary keys

Revision ID: composite_pks_001
Revises: 2025_12_12_1800
Create Date: 2025-12-12 20:00:00.000000

This migration completely rebuilds the GTFS schema with composite primary keys.
All GTFS entities now use (feed_id, entity_id) as their primary key, ensuring
proper data isolation per feed.

WARNING: This migration drops all existing GTFS data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = 'composite_pks_001'
down_revision: Union[str, None] = 'farerule001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop all GTFS tables (in reverse dependency order)
    op.execute("DROP TABLE IF EXISTS gtfs_stop_times CASCADE")
    op.execute("DROP TABLE IF EXISTS gtfs_calendar_dates CASCADE")
    op.execute("DROP TABLE IF EXISTS gtfs_trips CASCADE")
    op.execute("DROP TABLE IF EXISTS gtfs_fare_rules CASCADE")
    op.execute("DROP TABLE IF EXISTS gtfs_fare_attributes CASCADE")
    op.execute("DROP TABLE IF EXISTS gtfs_feed_info CASCADE")
    op.execute("DROP TABLE IF EXISTS gtfs_shapes CASCADE")
    op.execute("DROP TABLE IF EXISTS gtfs_calendar CASCADE")
    op.execute("DROP TABLE IF EXISTS gtfs_routes CASCADE")
    op.execute("DROP TABLE IF EXISTS gtfs_stops CASCADE")
    op.execute("DROP TABLE IF EXISTS gtfs_agencies CASCADE")

    # Create gtfs_agencies with composite PK
    op.create_table(
        'gtfs_agencies',
        sa.Column('feed_id', sa.Integer(), nullable=False),
        sa.Column('gtfs_agency_id', sa.String(255), nullable=False),
        sa.Column('agency_name', sa.String(255), nullable=False),
        sa.Column('agency_url', sa.String(500), nullable=False),
        sa.Column('agency_timezone', sa.String(100), nullable=False),
        sa.Column('agency_lang', sa.String(10), nullable=True),
        sa.Column('agency_phone', sa.String(50), nullable=True),
        sa.Column('agency_fare_url', sa.String(500), nullable=True),
        sa.Column('agency_email', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['feed_id'], ['gtfs_feeds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('feed_id', 'gtfs_agency_id'),
        comment='GTFS agencies - uses composite PK (feed_id, gtfs_agency_id)'
    )

    # Create gtfs_stops with composite PK
    op.create_table(
        'gtfs_stops',
        sa.Column('feed_id', sa.Integer(), nullable=False),
        sa.Column('stop_id', sa.String(255), nullable=False),
        sa.Column('stop_code', sa.String(50), nullable=True),
        sa.Column('stop_name', sa.String(255), nullable=False),
        sa.Column('stop_desc', sa.Text(), nullable=True),
        sa.Column('stop_lat', sa.Numeric(10, 8), nullable=False),
        sa.Column('stop_lon', sa.Numeric(11, 8), nullable=False),
        sa.Column('zone_id', sa.String(50), nullable=True),
        sa.Column('stop_url', sa.String(500), nullable=True),
        sa.Column('location_type', sa.Integer(), nullable=True),
        sa.Column('parent_station', sa.String(255), nullable=True),
        sa.Column('stop_timezone', sa.String(100), nullable=True),
        sa.Column('wheelchair_boarding', sa.Integer(), nullable=True),
        sa.Column('geom', Geometry('POINT', srid=4326), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['feed_id'], ['gtfs_feeds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('feed_id', 'stop_id'),
        comment='GTFS stops - uses composite PK (feed_id, stop_id)'
    )
    op.create_index('ix_gtfs_stops_stop_name', 'gtfs_stops', ['stop_name'])

    # Create gtfs_routes with composite PK and agency_id
    op.create_table(
        'gtfs_routes',
        sa.Column('feed_id', sa.Integer(), nullable=False),
        sa.Column('route_id', sa.String(255), nullable=False),
        sa.Column('agency_id', sa.Integer(), nullable=False),  # Link to agencies table
        sa.Column('gtfs_agency_id', sa.String(255), nullable=True),
        sa.Column('route_short_name', sa.String(50), nullable=False),
        sa.Column('route_long_name', sa.String(255), nullable=False),
        sa.Column('route_desc', sa.Text(), nullable=True),
        sa.Column('route_type', sa.Integer(), nullable=False),
        sa.Column('route_url', sa.String(500), nullable=True),
        sa.Column('route_color', sa.String(6), nullable=True),
        sa.Column('route_text_color', sa.String(6), nullable=True),
        sa.Column('route_sort_order', sa.Integer(), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['feed_id'], ['gtfs_feeds.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('feed_id', 'route_id'),
        comment='GTFS routes - uses composite PK (feed_id, route_id), also links to agency'
    )
    op.create_index('ix_gtfs_routes_route_short_name', 'gtfs_routes', ['route_short_name'])
    op.create_index('ix_gtfs_routes_agency_id', 'gtfs_routes', ['agency_id'])

    # Create gtfs_calendar with composite PK
    op.create_table(
        'gtfs_calendar',
        sa.Column('feed_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.String(255), nullable=False),
        sa.Column('monday', sa.Boolean(), nullable=False, default=False),
        sa.Column('tuesday', sa.Boolean(), nullable=False, default=False),
        sa.Column('wednesday', sa.Boolean(), nullable=False, default=False),
        sa.Column('thursday', sa.Boolean(), nullable=False, default=False),
        sa.Column('friday', sa.Boolean(), nullable=False, default=False),
        sa.Column('saturday', sa.Boolean(), nullable=False, default=False),
        sa.Column('sunday', sa.Boolean(), nullable=False, default=False),
        sa.Column('start_date', sa.String(8), nullable=False),
        sa.Column('end_date', sa.String(8), nullable=False),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['feed_id'], ['gtfs_feeds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('feed_id', 'service_id'),
        comment='GTFS calendar - uses composite PK (feed_id, service_id)'
    )

    # Create gtfs_shapes with composite PK
    op.create_table(
        'gtfs_shapes',
        sa.Column('feed_id', sa.Integer(), nullable=False),
        sa.Column('shape_id', sa.String(255), nullable=False),
        sa.Column('shape_pt_sequence', sa.Integer(), nullable=False),
        sa.Column('shape_pt_lat', sa.Numeric(10, 8), nullable=False),
        sa.Column('shape_pt_lon', sa.Numeric(11, 8), nullable=False),
        sa.Column('shape_dist_traveled', sa.Numeric(10, 2), nullable=True),
        sa.Column('geom', Geometry('POINT', srid=4326), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['feed_id'], ['gtfs_feeds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('feed_id', 'shape_id', 'shape_pt_sequence'),
        comment='GTFS shapes - uses composite PK (feed_id, shape_id, shape_pt_sequence)'
    )

    # Create gtfs_trips with composite PK and composite FKs
    op.create_table(
        'gtfs_trips',
        sa.Column('feed_id', sa.Integer(), nullable=False),
        sa.Column('trip_id', sa.String(255), nullable=False),
        sa.Column('route_id', sa.String(255), nullable=False),
        sa.Column('service_id', sa.String(255), nullable=False),
        sa.Column('shape_id', sa.String(255), nullable=True),
        sa.Column('trip_headsign', sa.String(255), nullable=True),
        sa.Column('trip_short_name', sa.String(50), nullable=True),
        sa.Column('direction_id', sa.Integer(), nullable=True),
        sa.Column('block_id', sa.String(50), nullable=True),
        sa.Column('wheelchair_accessible', sa.Integer(), nullable=True),
        sa.Column('bikes_allowed', sa.Integer(), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['feed_id'], ['gtfs_feeds.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['feed_id', 'route_id'], ['gtfs_routes.feed_id', 'gtfs_routes.route_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['feed_id', 'service_id'], ['gtfs_calendar.feed_id', 'gtfs_calendar.service_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('feed_id', 'trip_id'),
        comment='GTFS trips - uses composite PK (feed_id, trip_id) and composite FKs'
    )
    op.create_index('ix_gtfs_trips_route_id', 'gtfs_trips', ['route_id'])
    op.create_index('ix_gtfs_trips_service_id', 'gtfs_trips', ['service_id'])

    # Create gtfs_stop_times with composite PK and composite FKs
    op.create_table(
        'gtfs_stop_times',
        sa.Column('feed_id', sa.Integer(), nullable=False),
        sa.Column('trip_id', sa.String(255), nullable=False),
        sa.Column('stop_sequence', sa.Integer(), nullable=False),
        sa.Column('stop_id', sa.String(255), nullable=False),
        sa.Column('arrival_time', sa.String(8), nullable=False),
        sa.Column('departure_time', sa.String(8), nullable=False),
        sa.Column('stop_headsign', sa.String(255), nullable=True),
        sa.Column('pickup_type', sa.Integer(), nullable=True, default=0),
        sa.Column('drop_off_type', sa.Integer(), nullable=True, default=0),
        sa.Column('shape_dist_traveled', sa.Numeric(10, 2), nullable=True),
        sa.Column('timepoint', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['feed_id'], ['gtfs_feeds.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['feed_id', 'trip_id'], ['gtfs_trips.feed_id', 'gtfs_trips.trip_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['feed_id', 'stop_id'], ['gtfs_stops.feed_id', 'gtfs_stops.stop_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('feed_id', 'trip_id', 'stop_sequence'),
        comment='GTFS stop_times - uses composite PK (feed_id, trip_id, stop_sequence)'
    )
    op.create_index('ix_gtfs_stop_times_stop_id', 'gtfs_stop_times', ['stop_id'])

    # Create gtfs_calendar_dates with composite PK and composite FK
    op.create_table(
        'gtfs_calendar_dates',
        sa.Column('feed_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.String(255), nullable=False),
        sa.Column('date', sa.String(8), nullable=False),
        sa.Column('exception_type', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['feed_id'], ['gtfs_feeds.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['feed_id', 'service_id'], ['gtfs_calendar.feed_id', 'gtfs_calendar.service_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('feed_id', 'service_id', 'date'),
        comment='GTFS calendar_dates - uses composite PK (feed_id, service_id, date)'
    )

    # Create gtfs_fare_attributes with composite PK
    op.create_table(
        'gtfs_fare_attributes',
        sa.Column('feed_id', sa.Integer(), nullable=False),
        sa.Column('fare_id', sa.String(255), nullable=False),
        sa.Column('price', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency_type', sa.String(3), nullable=False),
        sa.Column('payment_method', sa.Integer(), nullable=False),
        sa.Column('transfers', sa.Integer(), nullable=True),
        sa.Column('agency_id', sa.String(255), nullable=True),
        sa.Column('transfer_duration', sa.Integer(), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['feed_id'], ['gtfs_feeds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('feed_id', 'fare_id'),
        comment='GTFS fare_attributes - uses composite PK (feed_id, fare_id)'
    )

    # Create gtfs_fare_rules with composite PK
    op.create_table(
        'gtfs_fare_rules',
        sa.Column('feed_id', sa.Integer(), nullable=False),
        sa.Column('fare_id', sa.String(255), nullable=False),
        sa.Column('route_id', sa.String(255), nullable=False, server_default=''),
        sa.Column('origin_id', sa.String(255), nullable=False, server_default=''),
        sa.Column('destination_id', sa.String(255), nullable=False, server_default=''),
        sa.Column('contains_id', sa.String(255), nullable=False, server_default=''),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['feed_id'], ['gtfs_feeds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('feed_id', 'fare_id', 'route_id', 'origin_id', 'destination_id', 'contains_id'),
        comment='GTFS fare_rules - uses composite PK with all identifying fields'
    )

    # Create gtfs_feed_info with feed_id as PK
    op.create_table(
        'gtfs_feed_info',
        sa.Column('feed_id', sa.Integer(), nullable=False),
        sa.Column('feed_publisher_name', sa.String(255), nullable=False),
        sa.Column('feed_publisher_url', sa.String(500), nullable=False),
        sa.Column('feed_lang', sa.String(10), nullable=False),
        sa.Column('default_lang', sa.String(10), nullable=True),
        sa.Column('feed_start_date', sa.String(8), nullable=True),
        sa.Column('feed_end_date', sa.String(8), nullable=True),
        sa.Column('feed_version', sa.String(50), nullable=True),
        sa.Column('feed_contact_email', sa.String(255), nullable=True),
        sa.Column('feed_contact_url', sa.String(500), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['feed_id'], ['gtfs_feeds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('feed_id'),
        comment='GTFS feed_info - uses feed_id as PK (1-to-1 with feed)'
    )


def downgrade() -> None:
    # This migration cannot be easily downgraded
    # You would need to restore from backup
    raise NotImplementedError("Downgrade not supported - restore from backup if needed")
