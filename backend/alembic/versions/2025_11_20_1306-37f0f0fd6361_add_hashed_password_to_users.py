"""Add hashed_password to users

Revision ID: 37f0f0fd6361
Revises: 001
Create Date: 2025-11-20 13:06:06.905895

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '37f0f0fd6361'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add hashed_password column for password-based authentication
    op.add_column('users', sa.Column('hashed_password', sa.String(length=255), nullable=True))


def downgrade() -> None:
    # Remove hashed_password column
    op.drop_column('users', 'hashed_password')
