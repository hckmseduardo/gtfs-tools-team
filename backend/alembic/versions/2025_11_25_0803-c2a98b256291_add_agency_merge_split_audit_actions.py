"""add_agency_merge_split_audit_actions

Revision ID: c2a98b256291
Revises: 66d152b34e85
Create Date: 2025-11-25 08:03:12.864500

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2a98b256291'
down_revision: Union[str, None] = '66d152b34e85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new enum values to auditaction enum type
    # PostgreSQL requires using raw SQL to add enum values
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'agency_merge'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'agency_split'")


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values directly
    # This would require recreating the enum type, which is complex
    # For production, consider keeping old values or using a different approach
    pass
