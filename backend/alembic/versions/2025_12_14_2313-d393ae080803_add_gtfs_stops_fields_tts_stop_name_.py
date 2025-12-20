"""Add GTFS stops fields: tts_stop_name, level_id, platform_code

Revision ID: d393ae080803
Revises: route_fields_001
Create Date: 2025-12-14 23:13:02.526667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd393ae080803'
down_revision: Union[str, None] = 'route_fields_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new GTFS fields to stops table
    op.add_column('gtfs_stops', sa.Column('tts_stop_name', sa.String(length=255), nullable=True, comment='Text-to-speech readable stop name'))
    op.add_column('gtfs_stops', sa.Column('level_id', sa.String(length=255), nullable=True, comment='Level ID within station'))
    op.add_column('gtfs_stops', sa.Column('platform_code', sa.String(length=50), nullable=True, comment='Platform identifier (e.g., G, 3)'))


def downgrade() -> None:
    op.drop_column('gtfs_stops', 'platform_code')
    op.drop_column('gtfs_stops', 'level_id')
    op.drop_column('gtfs_stops', 'tts_stop_name')
