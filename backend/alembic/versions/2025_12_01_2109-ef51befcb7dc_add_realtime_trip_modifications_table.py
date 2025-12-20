"""add_realtime_trip_modifications_table

Revision ID: ef51befcb7dc
Revises: e2ad235760ae
Create Date: 2025-12-01 21:09:22.036972

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef51befcb7dc'
down_revision: Union[str, None] = 'e2ad235760ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the new enum value for GTFS-RT Trip Modifications feed source type
    op.execute("ALTER TYPE feedsourcetype ADD VALUE IF NOT EXISTS 'gtfs_rt_trip_modifications'")

    # Create the realtime_trip_modifications table
    op.create_table('realtime_trip_modifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('feed_source_id', sa.Integer(), nullable=False),
    sa.Column('modification_id', sa.String(length=255), nullable=False, comment='Unique modification ID'),
    sa.Column('trip_id', sa.String(length=255), nullable=True, comment='GTFS trip_id (if single trip)'),
    sa.Column('route_id', sa.String(length=255), nullable=True, comment='GTFS route_id'),
    sa.Column('direction_id', sa.Integer(), nullable=True, comment='Direction of travel'),
    sa.Column('start_time', sa.String(length=20), nullable=True, comment='Start time of affected trips'),
    sa.Column('start_date', sa.String(length=10), nullable=True, comment='Start date (YYYYMMDD)'),
    sa.Column('service_dates', sa.JSON(), nullable=True, comment='List of dates when this modification applies (YYYYMMDD format)'),
    sa.Column('affected_stop_ids', sa.JSON(), nullable=True, comment='List of stop_ids that are affected (skipped, modified, etc.)'),
    sa.Column('replacement_stops', sa.JSON(), nullable=True, comment='List of replacement stops with properties'),
    sa.Column('modifications', sa.JSON(), nullable=True, comment='Detailed modification objects from GTFS-RT'),
    sa.Column('propagated_modification_delay', sa.Integer(), nullable=True, comment='Delay in seconds caused by this modification'),
    sa.Column('timestamp', sa.Integer(), nullable=True, comment='POSIX timestamp of this update'),
    sa.Column('raw_data', sa.JSON(), nullable=True, comment='Raw GTFS-RT TripModifications data'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['feed_source_id'], ['external_feed_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_realtime_trip_modifications_feed_source_id'), 'realtime_trip_modifications', ['feed_source_id'], unique=False)
    op.create_index(op.f('ix_realtime_trip_modifications_id'), 'realtime_trip_modifications', ['id'], unique=False)
    op.create_index(op.f('ix_realtime_trip_modifications_modification_id'), 'realtime_trip_modifications', ['modification_id'], unique=False)
    op.create_index(op.f('ix_realtime_trip_modifications_route_id'), 'realtime_trip_modifications', ['route_id'], unique=False)
    op.create_index(op.f('ix_realtime_trip_modifications_trip_id'), 'realtime_trip_modifications', ['trip_id'], unique=False)
    op.create_index('ix_trip_mods_feed_mod', 'realtime_trip_modifications', ['feed_source_id', 'modification_id'], unique=True)
    op.create_index('ix_trip_mods_route', 'realtime_trip_modifications', ['route_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_trip_mods_route', table_name='realtime_trip_modifications')
    op.drop_index('ix_trip_mods_feed_mod', table_name='realtime_trip_modifications')
    op.drop_index(op.f('ix_realtime_trip_modifications_trip_id'), table_name='realtime_trip_modifications')
    op.drop_index(op.f('ix_realtime_trip_modifications_route_id'), table_name='realtime_trip_modifications')
    op.drop_index(op.f('ix_realtime_trip_modifications_modification_id'), table_name='realtime_trip_modifications')
    op.drop_index(op.f('ix_realtime_trip_modifications_id'), table_name='realtime_trip_modifications')
    op.drop_index(op.f('ix_realtime_trip_modifications_feed_source_id'), table_name='realtime_trip_modifications')
    op.drop_table('realtime_trip_modifications')
    # Note: PostgreSQL doesn't support removing enum values easily, so we leave the enum value
