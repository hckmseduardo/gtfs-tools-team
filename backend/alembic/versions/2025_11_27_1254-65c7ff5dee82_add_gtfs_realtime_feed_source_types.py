"""add_gtfs_realtime_feed_source_types

Revision ID: 65c7ff5dee82
Revises: fa0f147f32eb
Create Date: 2025-11-27 12:54:48.610902

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65c7ff5dee82'
down_revision: Union[str, None] = 'fa0f147f32eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new GTFS-RT feed source types to the feedsourcetype enum
    # PostgreSQL doesn't support removing enum values in downgrade, so this is a one-way migration
    op.execute("ALTER TYPE feedsourcetype ADD VALUE IF NOT EXISTS 'gtfs_realtime'")
    op.execute("ALTER TYPE feedsourcetype ADD VALUE IF NOT EXISTS 'gtfs_rt_vehicle_positions'")
    op.execute("ALTER TYPE feedsourcetype ADD VALUE IF NOT EXISTS 'gtfs_rt_trip_updates'")
    op.execute("ALTER TYPE feedsourcetype ADD VALUE IF NOT EXISTS 'gtfs_rt_alerts'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from enums
    # To truly downgrade, you would need to create a new enum without these values
    # and migrate all data, which is complex and potentially destructive
    pass
