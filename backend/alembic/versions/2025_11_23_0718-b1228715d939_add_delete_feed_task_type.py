"""add_delete_feed_task_type

Revision ID: b1228715d939
Revises: dbca6c010ccf
Create Date: 2025-11-23 07:18:56.903988

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1228715d939'
down_revision: Union[str, None] = 'dbca6c010ccf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'delete_feed' value to tasktype enum
    op.execute("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'delete_feed'")


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values
    # This would require recreating the enum type
    pass
