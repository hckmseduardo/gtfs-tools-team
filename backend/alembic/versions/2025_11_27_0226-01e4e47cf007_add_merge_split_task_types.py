"""add_merge_split_task_types

Revision ID: 01e4e47cf007
Revises: c2a98b256291
Create Date: 2025-11-27 02:26:56.994370

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01e4e47cf007'
down_revision: Union[str, None] = 'c2a98b256291'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new values to tasktype enum
    op.execute("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'merge_agencies'")
    op.execute("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'split_agency'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily
    # This would require recreating the enum type
    pass
