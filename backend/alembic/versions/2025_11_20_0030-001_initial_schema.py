"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-11-20 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ENUM types if they don't exist
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE userrole AS ENUM ('super_admin', 'agency_admin', 'editor', 'viewer');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE auditaction AS ENUM ('create', 'update', 'delete', 'import', 'export', 'login', 'logout');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE taskstatus AS ENUM ('pending', 'running', 'completed', 'failed', 'cancelled');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE tasktype AS ENUM ('import_gtfs', 'export_gtfs', 'validate_gtfs', 'bulk_update', 'bulk_delete');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('azure_ad_object_id', sa.String(length=255), nullable=True),
        sa.Column('azure_ad_tenant_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_id', 'users', ['id'])
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_azure_ad_object_id', 'users', ['azure_ad_object_id'], unique=True)

    # Agencies table
    op.create_table(
        'agencies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('contact_email', sa.String(length=255), nullable=True),
        sa.Column('contact_phone', sa.String(length=50), nullable=True),
        sa.Column('website', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_agencies_id', 'agencies', ['id'])
    op.create_index('ix_agencies_name', 'agencies', ['name'])
    op.create_index('ix_agencies_slug', 'agencies', ['slug'], unique=True)

    # User-Agency association table
    op.create_table(
        'user_agencies',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('agency_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'agency_id')
    )
    # Cast the column to use the ENUM type and set default
    op.execute("ALTER TABLE user_agencies ALTER COLUMN role TYPE userrole USING role::userrole")
    op.execute("ALTER TABLE user_agencies ALTER COLUMN role SET DEFAULT 'viewer'::userrole")

    # GTFS Agencies table
    op.create_table(
        'gtfs_agencies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agency_id', sa.Integer(), nullable=False),
        sa.Column('gtfs_agency_id', sa.String(length=255), nullable=False),
        sa.Column('agency_name', sa.String(length=255), nullable=False),
        sa.Column('agency_url', sa.String(length=500), nullable=False),
        sa.Column('agency_timezone', sa.String(length=100), nullable=False),
        sa.Column('agency_lang', sa.String(length=10), nullable=True),
        sa.Column('agency_phone', sa.String(length=50), nullable=True),
        sa.Column('agency_fare_url', sa.String(length=500), nullable=True),
        sa.Column('agency_email', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_gtfs_agencies_id', 'gtfs_agencies', ['id'])
    op.create_index('ix_gtfs_agencies_agency_id', 'gtfs_agencies', ['agency_id'])

    # GTFS Stops table
    op.create_table(
        'gtfs_stops',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agency_id', sa.Integer(), nullable=False),
        sa.Column('stop_id', sa.String(length=255), nullable=False),
        sa.Column('stop_code', sa.String(length=50), nullable=True),
        sa.Column('stop_name', sa.String(length=255), nullable=False),
        sa.Column('stop_desc', sa.Text(), nullable=True),
        sa.Column('stop_lat', sa.Numeric(precision=10, scale=8), nullable=False),
        sa.Column('stop_lon', sa.Numeric(precision=11, scale=8), nullable=False),
        sa.Column('zone_id', sa.String(length=50), nullable=True),
        sa.Column('stop_url', sa.String(length=500), nullable=True),
        sa.Column('location_type', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('parent_station', sa.String(length=255), nullable=True),
        sa.Column('stop_timezone', sa.String(length=100), nullable=True),
        sa.Column('wheelchair_boarding', sa.Integer(), nullable=True),
        sa.Column('geom', Geometry('POINT', srid=4326), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_gtfs_stops_id', 'gtfs_stops', ['id'])
    op.create_index('ix_gtfs_stops_agency_id', 'gtfs_stops', ['agency_id'])
    op.create_index('ix_gtfs_stops_stop_id', 'gtfs_stops', ['stop_id'])
    op.create_index('ix_gtfs_stops_stop_name', 'gtfs_stops', ['stop_name'])
    # GeoAlchemy2 may auto-create GIST index - create manually if needed
    op.execute('CREATE INDEX IF NOT EXISTS idx_gtfs_stops_geom ON gtfs_stops USING GIST (geom)')

    # GTFS Routes table
    op.create_table(
        'gtfs_routes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agency_id', sa.Integer(), nullable=False),
        sa.Column('route_id', sa.String(length=255), nullable=False),
        sa.Column('gtfs_agency_id', sa.String(length=255), nullable=True),
        sa.Column('route_short_name', sa.String(length=50), nullable=False),
        sa.Column('route_long_name', sa.String(length=255), nullable=False),
        sa.Column('route_desc', sa.Text(), nullable=True),
        sa.Column('route_type', sa.Integer(), nullable=False),
        sa.Column('route_url', sa.String(length=500), nullable=True),
        sa.Column('route_color', sa.String(length=6), nullable=True),
        sa.Column('route_text_color', sa.String(length=6), nullable=True),
        sa.Column('route_sort_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_gtfs_routes_id', 'gtfs_routes', ['id'])
    op.create_index('ix_gtfs_routes_agency_id', 'gtfs_routes', ['agency_id'])
    op.create_index('ix_gtfs_routes_route_id', 'gtfs_routes', ['route_id'])
    op.create_index('ix_gtfs_routes_route_short_name', 'gtfs_routes', ['route_short_name'])

    # GTFS Calendar table
    op.create_table(
        'gtfs_calendar',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.String(length=255), nullable=False),
        sa.Column('monday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('tuesday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('wednesday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('thursday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('friday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('saturday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sunday', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('start_date', sa.String(length=8), nullable=False),
        sa.Column('end_date', sa.String(length=8), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_gtfs_calendar_id', 'gtfs_calendar', ['id'])
    op.create_index('ix_gtfs_calendar_service_id', 'gtfs_calendar', ['service_id'])

    # GTFS Shapes table
    op.create_table(
        'gtfs_shapes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shape_id', sa.String(length=255), nullable=False),
        sa.Column('shape_pt_lat', sa.Numeric(precision=10, scale=8), nullable=False),
        sa.Column('shape_pt_lon', sa.Numeric(precision=11, scale=8), nullable=False),
        sa.Column('shape_pt_sequence', sa.Integer(), nullable=False),
        sa.Column('shape_dist_traveled', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('geom', Geometry('LINESTRING', srid=4326), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_gtfs_shapes_id', 'gtfs_shapes', ['id'])
    op.create_index('ix_gtfs_shapes_shape_id', 'gtfs_shapes', ['shape_id'])
    # GeoAlchemy2 may auto-create GIST index - create manually if needed
    op.execute('CREATE INDEX IF NOT EXISTS idx_gtfs_shapes_geom ON gtfs_shapes USING GIST (geom)')

    # GTFS Trips table
    op.create_table(
        'gtfs_trips',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agency_id', sa.Integer(), nullable=False),
        sa.Column('route_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('trip_id', sa.String(length=255), nullable=False),
        sa.Column('trip_headsign', sa.String(length=255), nullable=True),
        sa.Column('trip_short_name', sa.String(length=50), nullable=True),
        sa.Column('direction_id', sa.Integer(), nullable=True),
        sa.Column('block_id', sa.String(length=50), nullable=True),
        sa.Column('shape_id', sa.Integer(), nullable=True),
        sa.Column('wheelchair_accessible', sa.Integer(), nullable=True),
        sa.Column('bikes_allowed', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['route_id'], ['gtfs_routes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['service_id'], ['gtfs_calendar.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shape_id'], ['gtfs_shapes.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_gtfs_trips_id', 'gtfs_trips', ['id'])
    op.create_index('ix_gtfs_trips_agency_id', 'gtfs_trips', ['agency_id'])
    op.create_index('ix_gtfs_trips_route_id', 'gtfs_trips', ['route_id'])
    op.create_index('ix_gtfs_trips_service_id', 'gtfs_trips', ['service_id'])
    op.create_index('ix_gtfs_trips_trip_id', 'gtfs_trips', ['trip_id'])

    # GTFS Stop Times table
    op.create_table(
        'gtfs_stop_times',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('arrival_time', sa.String(length=8), nullable=False),
        sa.Column('departure_time', sa.String(length=8), nullable=False),
        sa.Column('stop_id', sa.Integer(), nullable=False),
        sa.Column('stop_sequence', sa.Integer(), nullable=False),
        sa.Column('stop_headsign', sa.String(length=255), nullable=True),
        sa.Column('pickup_type', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('drop_off_type', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('shape_dist_traveled', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('timepoint', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['stop_id'], ['gtfs_stops.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trip_id'], ['gtfs_trips.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_gtfs_stop_times_id', 'gtfs_stop_times', ['id'])
    op.create_index('ix_gtfs_stop_times_trip_id', 'gtfs_stop_times', ['trip_id'])
    op.create_index('ix_gtfs_stop_times_stop_id', 'gtfs_stop_times', ['stop_id'])

    # GTFS Calendar Dates table
    op.create_table(
        'gtfs_calendar_dates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.String(length=8), nullable=False),
        sa.Column('exception_type', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['service_id'], ['gtfs_calendar.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_gtfs_calendar_dates_id', 'gtfs_calendar_dates', ['id'])
    op.create_index('ix_gtfs_calendar_dates_service_id', 'gtfs_calendar_dates', ['service_id'])

    # Audit Logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('agency_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('entity_type', sa.String(length=100), nullable=False),
        sa.Column('entity_id', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('old_values', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('new_values', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.execute("ALTER TABLE audit_logs ALTER COLUMN action TYPE auditaction USING action::auditaction")
    op.create_index('ix_audit_logs_id', 'audit_logs', ['id'])
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])
    op.create_index('ix_audit_logs_agency_id', 'audit_logs', ['agency_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_entity_type', 'audit_logs', ['entity_type'])
    op.create_index('ix_audit_logs_entity_id', 'audit_logs', ['entity_id'])

    # Async Tasks table
    op.create_table(
        'async_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('celery_task_id', sa.String(length=255), nullable=False),
        sa.Column('task_type', sa.String(50), nullable=False),
        sa.Column('task_name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('agency_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('progress', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('started_at', sa.String(length=100), nullable=True),
        sa.Column('completed_at', sa.String(length=100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_traceback', sa.Text(), nullable=True),
        sa.Column('input_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('result_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.execute("ALTER TABLE async_tasks ALTER COLUMN task_type TYPE tasktype USING task_type::tasktype")
    op.execute("ALTER TABLE async_tasks ALTER COLUMN status TYPE taskstatus USING status::taskstatus")
    op.execute("ALTER TABLE async_tasks ALTER COLUMN status SET DEFAULT 'pending'::taskstatus")
    op.create_index('ix_async_tasks_id', 'async_tasks', ['id'])
    op.create_index('ix_async_tasks_celery_task_id', 'async_tasks', ['celery_task_id'], unique=True)
    op.create_index('ix_async_tasks_task_type', 'async_tasks', ['task_type'])
    op.create_index('ix_async_tasks_user_id', 'async_tasks', ['user_id'])
    op.create_index('ix_async_tasks_agency_id', 'async_tasks', ['agency_id'])
    op.create_index('ix_async_tasks_status', 'async_tasks', ['status'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('async_tasks')
    op.drop_table('audit_logs')
    op.drop_table('gtfs_calendar_dates')
    op.drop_table('gtfs_stop_times')
    op.drop_table('gtfs_trips')
    op.drop_table('gtfs_shapes')
    op.drop_table('gtfs_calendar')
    op.drop_table('gtfs_routes')
    op.drop_table('gtfs_stops')
    op.drop_table('gtfs_agencies')
    op.drop_table('user_agencies')
    op.drop_table('agencies')
    op.drop_table('users')

    # Drop ENUM types
    op.execute('DROP TYPE tasktype')
    op.execute('DROP TYPE taskstatus')
    op.execute('DROP TYPE auditaction')
    op.execute('DROP TYPE userrole')
