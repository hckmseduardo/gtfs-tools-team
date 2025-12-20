"""add_realtime_shapes_and_stops_tables

Revision ID: 46b3c6dec493
Revises: 1016627eb9b8
Create Date: 2025-12-02 22:17:28.496377

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46b3c6dec493'
down_revision: Union[str, None] = '1016627eb9b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new feed source type enum values for shapes and stops
    op.execute("ALTER TYPE feedsourcetype ADD VALUE IF NOT EXISTS 'gtfs_rt_shapes'")
    op.execute("ALTER TYPE feedsourcetype ADD VALUE IF NOT EXISTS 'gtfs_rt_stops'")

    # Create realtime_shapes table
    op.create_table('realtime_shapes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('feed_source_id', sa.Integer(), nullable=False),
    sa.Column('shape_id', sa.String(length=255), nullable=False, comment='Unique shape ID from the feed'),
    sa.Column('encoded_polyline', sa.Text(), nullable=True, comment='Encoded polyline string for the shape'),
    sa.Column('shape_points', sa.JSON(), nullable=True, comment='Array of {lat, lon, sequence, dist_traveled} points'),
    sa.Column('modification_id', sa.String(length=255), nullable=True, comment='Associated trip modification ID'),
    sa.Column('trip_id', sa.String(length=255), nullable=True, comment='Associated trip ID'),
    sa.Column('route_id', sa.String(length=255), nullable=True, comment='Associated route ID'),
    sa.Column('timestamp', sa.Integer(), nullable=True, comment='POSIX timestamp of this update'),
    sa.Column('raw_data', sa.JSON(), nullable=True, comment='Raw GTFS-RT shape data'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['feed_source_id'], ['external_feed_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_realtime_shapes_feed_source_id'), 'realtime_shapes', ['feed_source_id'], unique=False)
    op.create_index(op.f('ix_realtime_shapes_id'), 'realtime_shapes', ['id'], unique=False)
    op.create_index(op.f('ix_realtime_shapes_modification_id'), 'realtime_shapes', ['modification_id'], unique=False)
    op.create_index(op.f('ix_realtime_shapes_route_id'), 'realtime_shapes', ['route_id'], unique=False)
    op.create_index(op.f('ix_realtime_shapes_shape_id'), 'realtime_shapes', ['shape_id'], unique=False)
    op.create_index(op.f('ix_realtime_shapes_trip_id'), 'realtime_shapes', ['trip_id'], unique=False)
    op.create_index('ix_rt_shapes_feed_shape', 'realtime_shapes', ['feed_source_id', 'shape_id'], unique=True)

    # Create realtime_stops table
    op.create_table('realtime_stops',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('feed_source_id', sa.Integer(), nullable=False),
    sa.Column('stop_id', sa.String(length=255), nullable=False, comment='Unique stop ID from the feed'),
    sa.Column('stop_name', sa.String(length=500), nullable=True, comment='Name of the stop'),
    sa.Column('stop_lat', sa.Float(), nullable=True, comment='Latitude of the stop'),
    sa.Column('stop_lon', sa.Float(), nullable=True, comment='Longitude of the stop'),
    sa.Column('stop_code', sa.String(length=100), nullable=True, comment='Short code for the stop'),
    sa.Column('stop_desc', sa.Text(), nullable=True, comment='Description of the stop'),
    sa.Column('zone_id', sa.String(length=100), nullable=True, comment='Fare zone ID'),
    sa.Column('stop_url', sa.String(length=2000), nullable=True, comment='URL for stop information'),
    sa.Column('location_type', sa.Integer(), nullable=True, comment='0=stop, 1=station, 2=entrance/exit'),
    sa.Column('parent_station', sa.String(length=255), nullable=True, comment='Parent station stop_id'),
    sa.Column('wheelchair_boarding', sa.Integer(), nullable=True, comment='Wheelchair boarding: 0=unknown, 1=accessible, 2=not accessible'),
    sa.Column('platform_code', sa.String(length=100), nullable=True, comment='Platform identifier'),
    sa.Column('modification_id', sa.String(length=255), nullable=True, comment='Associated trip modification ID'),
    sa.Column('route_id', sa.String(length=255), nullable=True, comment='Associated route ID'),
    sa.Column('is_replacement', sa.Boolean(), nullable=False, comment='Whether this is a temporary replacement stop'),
    sa.Column('timestamp', sa.Integer(), nullable=True, comment='POSIX timestamp of this update'),
    sa.Column('raw_data', sa.JSON(), nullable=True, comment='Raw GTFS-RT stop data'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['feed_source_id'], ['external_feed_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_realtime_stops_feed_source_id'), 'realtime_stops', ['feed_source_id'], unique=False)
    op.create_index(op.f('ix_realtime_stops_id'), 'realtime_stops', ['id'], unique=False)
    op.create_index(op.f('ix_realtime_stops_modification_id'), 'realtime_stops', ['modification_id'], unique=False)
    op.create_index(op.f('ix_realtime_stops_route_id'), 'realtime_stops', ['route_id'], unique=False)
    op.create_index(op.f('ix_realtime_stops_stop_id'), 'realtime_stops', ['stop_id'], unique=False)
    op.create_index('ix_rt_stops_feed_stop', 'realtime_stops', ['feed_source_id', 'stop_id'], unique=True)


def downgrade() -> None:
    # Drop realtime_stops table and indexes
    op.drop_index('ix_rt_stops_feed_stop', table_name='realtime_stops')
    op.drop_index(op.f('ix_realtime_stops_stop_id'), table_name='realtime_stops')
    op.drop_index(op.f('ix_realtime_stops_route_id'), table_name='realtime_stops')
    op.drop_index(op.f('ix_realtime_stops_modification_id'), table_name='realtime_stops')
    op.drop_index(op.f('ix_realtime_stops_id'), table_name='realtime_stops')
    op.drop_index(op.f('ix_realtime_stops_feed_source_id'), table_name='realtime_stops')
    op.drop_table('realtime_stops')

    # Drop realtime_shapes table and indexes
    op.drop_index('ix_rt_shapes_feed_shape', table_name='realtime_shapes')
    op.drop_index(op.f('ix_realtime_shapes_trip_id'), table_name='realtime_shapes')
    op.drop_index(op.f('ix_realtime_shapes_shape_id'), table_name='realtime_shapes')
    op.drop_index(op.f('ix_realtime_shapes_route_id'), table_name='realtime_shapes')
    op.drop_index(op.f('ix_realtime_shapes_modification_id'), table_name='realtime_shapes')
    op.drop_index(op.f('ix_realtime_shapes_id'), table_name='realtime_shapes')
    op.drop_index(op.f('ix_realtime_shapes_feed_source_id'), table_name='realtime_shapes')
    op.drop_table('realtime_shapes')

    # Note: PostgreSQL doesn't support removing enum values easily
    # The gtfs_rt_shapes and gtfs_rt_stops enum values will remain in the database
