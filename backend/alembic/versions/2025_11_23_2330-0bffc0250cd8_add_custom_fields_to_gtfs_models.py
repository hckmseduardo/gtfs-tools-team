"""add_custom_fields_to_gtfs_models

Revision ID: 0bffc0250cd8
Revises: b1228715d939
Create Date: 2025-11-23 23:30:56.370313

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0bffc0250cd8'
down_revision: Union[str, None] = 'b1228715d939'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add custom_fields JSONB column to gtfs_routes
    op.add_column('gtfs_routes',
        sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment='Custom/extension fields from GTFS'))

    # Add custom_fields JSONB column to gtfs_stops
    op.add_column('gtfs_stops',
        sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment='Custom/extension fields from GTFS'))

    # Add custom_fields JSONB column to gtfs_trips
    op.add_column('gtfs_trips',
        sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment='Custom/extension fields from GTFS'))

    # Add custom_fields JSONB column to gtfs_calendar
    op.add_column('gtfs_calendar',
        sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment='Custom/extension fields from GTFS'))


def downgrade() -> None:
    # Remove custom_fields columns
    op.drop_column('gtfs_calendar', 'custom_fields')
    op.drop_column('gtfs_trips', 'custom_fields')
    op.drop_column('gtfs_stops', 'custom_fields')
    op.drop_column('gtfs_routes', 'custom_fields')
