"""Add FareRule model for GTFS fare_rules.txt

Revision ID: farerule001
Revises: 9c95d4dfe653
Create Date: 2025-12-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'farerule001'
down_revision: Union[str, None] = '9c95d4dfe653'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create gtfs_fare_rules table
    op.create_table('gtfs_fare_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('feed_id', sa.Integer(), nullable=False),
    sa.Column('fare_id', sa.String(length=255), nullable=False),
    sa.Column('route_id', sa.String(length=255), nullable=True),
    sa.Column('origin_id', sa.String(length=255), nullable=True, comment='Origin zone ID'),
    sa.Column('destination_id', sa.String(length=255), nullable=True, comment='Destination zone ID'),
    sa.Column('contains_id', sa.String(length=255), nullable=True, comment='Zone ID that must be contained in itinerary'),
    sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Custom/extension fields from GTFS'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['feed_id'], ['gtfs_feeds.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gtfs_fare_rules_fare_id'), 'gtfs_fare_rules', ['fare_id'], unique=False)
    op.create_index(op.f('ix_gtfs_fare_rules_feed_id'), 'gtfs_fare_rules', ['feed_id'], unique=False)
    op.create_index(op.f('ix_gtfs_fare_rules_id'), 'gtfs_fare_rules', ['id'], unique=False)
    op.create_index(op.f('ix_gtfs_fare_rules_route_id'), 'gtfs_fare_rules', ['route_id'], unique=False)


def downgrade() -> None:
    # Drop gtfs_fare_rules table
    op.drop_index(op.f('ix_gtfs_fare_rules_route_id'), table_name='gtfs_fare_rules')
    op.drop_index(op.f('ix_gtfs_fare_rules_id'), table_name='gtfs_fare_rules')
    op.drop_index(op.f('ix_gtfs_fare_rules_feed_id'), table_name='gtfs_fare_rules')
    op.drop_index(op.f('ix_gtfs_fare_rules_fare_id'), table_name='gtfs_fare_rules')
    op.drop_table('gtfs_fare_rules')
