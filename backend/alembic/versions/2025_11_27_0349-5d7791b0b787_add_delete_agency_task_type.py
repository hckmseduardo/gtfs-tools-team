"""add_delete_agency_task_type

Revision ID: 5d7791b0b787
Revises: 01e4e47cf007
Create Date: 2025-11-27 03:49:59.370377

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d7791b0b787'
down_revision: Union[str, None] = '01e4e47cf007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new value to tasktype enum for agency deletion
    op.execute("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'delete_agency'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily
    # This would require recreating the enum type
    pass
