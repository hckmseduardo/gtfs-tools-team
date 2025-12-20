"""Add continuous_pickup, continuous_drop_off, and network_id to routes

Revision ID: add_route_fields_gtfs
Revises: 2025_12_12_2000-convert_to_composite_pks
Create Date: 2025-12-14 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'route_fields_001'
down_revision: Union[str, None] = 'composite_pks_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add GTFS route fields per specification
    op.add_column('gtfs_routes', sa.Column(
        'continuous_pickup',
        sa.Integer(),
        nullable=True,
        comment='0=continuous, 1=none, 2=phone agency, 3=coordinate with driver'
    ))
    op.add_column('gtfs_routes', sa.Column(
        'continuous_drop_off',
        sa.Integer(),
        nullable=True,
        comment='0=continuous, 1=none, 2=phone agency, 3=coordinate with driver'
    ))
    op.add_column('gtfs_routes', sa.Column(
        'network_id',
        sa.String(255),
        nullable=True,
        comment='Identifies a group of routes for fare purposes'
    ))


def downgrade() -> None:
    op.drop_column('gtfs_routes', 'network_id')
    op.drop_column('gtfs_routes', 'continuous_drop_off')
    op.drop_column('gtfs_routes', 'continuous_pickup')
