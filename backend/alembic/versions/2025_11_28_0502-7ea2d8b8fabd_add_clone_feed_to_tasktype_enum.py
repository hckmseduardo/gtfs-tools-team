"""Add clone_feed to TaskType enum

Revision ID: 7ea2d8b8fabd
Revises: 65c7ff5dee82
Create Date: 2025-11-28 05:02:46.322241

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ea2d8b8fabd'
down_revision: Union[str, None] = '65c7ff5dee82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add clone_feed to TaskType enum
    op.execute("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'clone_feed'")

    # Create realtime tables
    op.create_table('realtime_alerts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('feed_source_id', sa.Integer(), nullable=False),
    sa.Column('alert_id', sa.String(length=255), nullable=False, comment='Unique alert ID from the feed'),
    sa.Column('active_period_start', sa.Integer(), nullable=True, comment='Start of active period (POSIX timestamp)'),
    sa.Column('active_period_end', sa.Integer(), nullable=True, comment='End of active period (POSIX timestamp)'),
    sa.Column('informed_entities', sa.JSON(), nullable=True, comment='List of affected agencies, routes, stops, trips'),
    sa.Column('cause', sa.String(length=50), nullable=True, comment='Alert cause'),
    sa.Column('effect', sa.String(length=50), nullable=True, comment='Alert effect'),
    sa.Column('severity_level', sa.String(length=50), nullable=True, comment='INFO, WARNING, SEVERE'),
    sa.Column('header_text', sa.JSON(), nullable=True, comment='Alert header in multiple languages'),
    sa.Column('description_text', sa.JSON(), nullable=True, comment='Alert description in multiple languages'),
    sa.Column('url', sa.String(length=2000), nullable=True, comment='URL for more information'),
    sa.Column('raw_data', sa.JSON(), nullable=True, comment='Raw alert data'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['feed_source_id'], ['external_feed_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alerts_feed_alert', 'realtime_alerts', ['feed_source_id', 'alert_id'], unique=True)
    op.create_index(op.f('ix_realtime_alerts_alert_id'), 'realtime_alerts', ['alert_id'], unique=False)
    op.create_index(op.f('ix_realtime_alerts_feed_source_id'), 'realtime_alerts', ['feed_source_id'], unique=False)
    op.create_index(op.f('ix_realtime_alerts_id'), 'realtime_alerts', ['id'], unique=False)
    op.create_table('realtime_trip_updates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('feed_source_id', sa.Integer(), nullable=False),
    sa.Column('trip_id', sa.String(length=255), nullable=False, comment='GTFS trip_id'),
    sa.Column('route_id', sa.String(length=255), nullable=True, comment='GTFS route_id'),
    sa.Column('direction_id', sa.Integer(), nullable=True, comment='Direction of travel'),
    sa.Column('start_time', sa.String(length=20), nullable=True, comment='Scheduled start time'),
    sa.Column('start_date', sa.String(length=10), nullable=True, comment='Start date (YYYYMMDD)'),
    sa.Column('schedule_relationship', sa.String(length=50), nullable=True, comment='SCHEDULED, ADDED, UNSCHEDULED, CANCELED, REPLACEMENT'),
    sa.Column('vehicle_id', sa.String(length=255), nullable=True, comment='Vehicle ID serving this trip'),
    sa.Column('vehicle_label', sa.String(length=255), nullable=True, comment='Vehicle label'),
    sa.Column('delay', sa.Integer(), nullable=True, comment='Current delay in seconds (positive = late)'),
    sa.Column('timestamp', sa.Integer(), nullable=True, comment='POSIX timestamp of this update'),
    sa.Column('raw_data', sa.JSON(), nullable=True, comment='Raw data including stop_time_updates'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['feed_source_id'], ['external_feed_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_realtime_trip_updates_feed_source_id'), 'realtime_trip_updates', ['feed_source_id'], unique=False)
    op.create_index(op.f('ix_realtime_trip_updates_id'), 'realtime_trip_updates', ['id'], unique=False)
    op.create_index(op.f('ix_realtime_trip_updates_route_id'), 'realtime_trip_updates', ['route_id'], unique=False)
    op.create_index(op.f('ix_realtime_trip_updates_trip_id'), 'realtime_trip_updates', ['trip_id'], unique=False)
    op.create_index('ix_trip_updates_feed_trip', 'realtime_trip_updates', ['feed_source_id', 'trip_id'], unique=True)
    op.create_table('realtime_vehicle_positions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('feed_source_id', sa.Integer(), nullable=False),
    sa.Column('vehicle_id', sa.String(length=255), nullable=False, comment='Vehicle ID from the feed'),
    sa.Column('vehicle_label', sa.String(length=255), nullable=True, comment='User-visible label (e.g., vehicle number)'),
    sa.Column('license_plate', sa.String(length=100), nullable=True, comment='License plate of the vehicle'),
    sa.Column('latitude', sa.Float(), nullable=False, comment='Current latitude'),
    sa.Column('longitude', sa.Float(), nullable=False, comment='Current longitude'),
    sa.Column('bearing', sa.Float(), nullable=True, comment='Bearing in degrees (0=North, 90=East)'),
    sa.Column('speed', sa.Float(), nullable=True, comment='Speed in meters/second'),
    sa.Column('odometer', sa.Float(), nullable=True, comment='Odometer value in meters'),
    sa.Column('trip_id', sa.String(length=255), nullable=True, comment='GTFS trip_id this vehicle is serving'),
    sa.Column('route_id', sa.String(length=255), nullable=True, comment='GTFS route_id this vehicle is serving'),
    sa.Column('direction_id', sa.Integer(), nullable=True, comment='Direction of travel (0 or 1)'),
    sa.Column('start_time', sa.String(length=20), nullable=True, comment='Scheduled start time of the trip'),
    sa.Column('start_date', sa.String(length=10), nullable=True, comment='Start date of the trip (YYYYMMDD)'),
    sa.Column('schedule_relationship', sa.String(length=50), nullable=True, comment='SCHEDULED, ADDED, UNSCHEDULED, CANCELED'),
    sa.Column('current_stop_sequence', sa.Integer(), nullable=True, comment='Current stop sequence'),
    sa.Column('stop_id', sa.String(length=255), nullable=True, comment='Current or next stop ID'),
    sa.Column('current_status', sa.String(length=50), nullable=True, comment='INCOMING_AT, STOPPED_AT, IN_TRANSIT_TO'),
    sa.Column('congestion_level', sa.String(length=50), nullable=True, comment='Congestion level'),
    sa.Column('occupancy_status', sa.String(length=50), nullable=True, comment='Occupancy status'),
    sa.Column('occupancy_percentage', sa.Integer(), nullable=True, comment='Occupancy percentage (0-100)'),
    sa.Column('timestamp', sa.Integer(), nullable=True, comment='POSIX timestamp from the vehicle position'),
    sa.Column('raw_data', sa.JSON(), nullable=True, comment='Raw data from GTFS-RT for debugging'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['feed_source_id'], ['external_feed_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_realtime_vehicle_positions_feed_source_id'), 'realtime_vehicle_positions', ['feed_source_id'], unique=False)
    op.create_index(op.f('ix_realtime_vehicle_positions_id'), 'realtime_vehicle_positions', ['id'], unique=False)
    op.create_index(op.f('ix_realtime_vehicle_positions_route_id'), 'realtime_vehicle_positions', ['route_id'], unique=False)
    op.create_index(op.f('ix_realtime_vehicle_positions_trip_id'), 'realtime_vehicle_positions', ['trip_id'], unique=False)
    op.create_index(op.f('ix_realtime_vehicle_positions_vehicle_id'), 'realtime_vehicle_positions', ['vehicle_id'], unique=False)
    op.create_index('ix_vehicle_positions_feed_vehicle', 'realtime_vehicle_positions', ['feed_source_id', 'vehicle_id'], unique=True)


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values, so we skip that
    op.drop_index('ix_vehicle_positions_feed_vehicle', table_name='realtime_vehicle_positions')
    op.drop_index(op.f('ix_realtime_vehicle_positions_vehicle_id'), table_name='realtime_vehicle_positions')
    op.drop_index(op.f('ix_realtime_vehicle_positions_trip_id'), table_name='realtime_vehicle_positions')
    op.drop_index(op.f('ix_realtime_vehicle_positions_route_id'), table_name='realtime_vehicle_positions')
    op.drop_index(op.f('ix_realtime_vehicle_positions_id'), table_name='realtime_vehicle_positions')
    op.drop_index(op.f('ix_realtime_vehicle_positions_feed_source_id'), table_name='realtime_vehicle_positions')
    op.drop_table('realtime_vehicle_positions')
    op.drop_index('ix_trip_updates_feed_trip', table_name='realtime_trip_updates')
    op.drop_index(op.f('ix_realtime_trip_updates_trip_id'), table_name='realtime_trip_updates')
    op.drop_index(op.f('ix_realtime_trip_updates_route_id'), table_name='realtime_trip_updates')
    op.drop_index(op.f('ix_realtime_trip_updates_id'), table_name='realtime_trip_updates')
    op.drop_index(op.f('ix_realtime_trip_updates_feed_source_id'), table_name='realtime_trip_updates')
    op.drop_table('realtime_trip_updates')
    op.drop_index(op.f('ix_realtime_alerts_id'), table_name='realtime_alerts')
    op.drop_index(op.f('ix_realtime_alerts_feed_source_id'), table_name='realtime_alerts')
    op.drop_index(op.f('ix_realtime_alerts_alert_id'), table_name='realtime_alerts')
    op.drop_index('ix_alerts_feed_alert', table_name='realtime_alerts')
    op.drop_table('realtime_alerts')
