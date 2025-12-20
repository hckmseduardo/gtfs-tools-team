"""Add cars_allowed field to trips table

Revision ID: add_trips_cars_allowed
Revises: d393ae080803
Create Date: 2025-12-14 24:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_trips_cars_allowed'
down_revision: Union[str, None] = 'd393ae080803'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add cars_allowed column to gtfs_trips table
    op.add_column('gtfs_trips', sa.Column('cars_allowed', sa.Integer(), nullable=True, comment='0=no info, 1=allowed, 2=not allowed'))


def downgrade() -> None:
    # Remove cars_allowed column from gtfs_trips table
    op.drop_column('gtfs_trips', 'cars_allowed')
