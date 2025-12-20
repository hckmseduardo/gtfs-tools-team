"""Increase shape_dist_traveled precision to preserve all decimals

Revision ID: increase_dist_precision
Revises: unify_agencies_001
Create Date: 2025-12-14 26:00:00.000000

GTFS files can have many decimal places for shape_dist_traveled values.
This migration increases precision from Numeric(10, 2) to Numeric(16, 10)
to preserve all original decimal places when importing/exporting GTFS data.

Affected tables:
- gtfs_stop_times: shape_dist_traveled column
- gtfs_shapes: shape_dist_traveled column
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'increase_dist_precision'
down_revision: Union[str, None] = 'unify_agencies_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Increase precision for shape_dist_traveled in stop_times
    # From Numeric(10, 2) to Numeric(16, 10)
    op.alter_column(
        'gtfs_stop_times',
        'shape_dist_traveled',
        type_=sa.Numeric(16, 10),
        existing_type=sa.Numeric(10, 2),
        existing_nullable=True,
        comment='Distance traveled along shape in meters (full precision)'
    )

    # Increase precision for shape_dist_traveled in shapes
    # From Numeric(10, 2) to Numeric(16, 10)
    op.alter_column(
        'gtfs_shapes',
        'shape_dist_traveled',
        type_=sa.Numeric(16, 10),
        existing_type=sa.Numeric(10, 2),
        existing_nullable=True,
        comment='Distance traveled along shape in meters (full precision)'
    )


def downgrade() -> None:
    # Revert shape_dist_traveled precision in stop_times
    # WARNING: This will truncate decimal places
    op.alter_column(
        'gtfs_stop_times',
        'shape_dist_traveled',
        type_=sa.Numeric(10, 2),
        existing_type=sa.Numeric(16, 10),
        existing_nullable=True
    )

    # Revert shape_dist_traveled precision in shapes
    # WARNING: This will truncate decimal places
    op.alter_column(
        'gtfs_shapes',
        'shape_dist_traveled',
        type_=sa.Numeric(10, 2),
        existing_type=sa.Numeric(16, 10),
        existing_nullable=True
    )
