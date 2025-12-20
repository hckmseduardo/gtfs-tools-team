"""add_gtfs_agency_fields

Add GTFS-compliant fields to agencies table:
- agency_id: unique identifier for GTFS export
- agency_url: website URL (required for GTFS)
- agency_timezone: IANA timezone (required for GTFS)
- agency_lang: ISO 639-1 language code
- agency_phone: voice telephone number
- agency_fare_url: URL for fare information
- agency_email: customer service email

Revision ID: 9c95d4dfe653
Revises: a1b2c3d4e5f6
Create Date: 2025-12-12 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c95d4dfe653'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add GTFS agency.txt fields to agencies table
    op.add_column('agencies', sa.Column('agency_id', sa.String(100), nullable=True,
                  comment='GTFS agency_id - unique identifier for GTFS export'))
    op.add_column('agencies', sa.Column('agency_url', sa.String(500), nullable=True,
                  comment='GTFS agency_url - agency website URL'))
    op.add_column('agencies', sa.Column('agency_timezone', sa.String(100), nullable=True,
                  comment='GTFS agency_timezone - IANA timezone (e.g., America/New_York)'))
    op.add_column('agencies', sa.Column('agency_lang', sa.String(10), nullable=True,
                  comment='GTFS agency_lang - ISO 639-1 language code'))
    op.add_column('agencies', sa.Column('agency_phone', sa.String(50), nullable=True,
                  comment='GTFS agency_phone - voice telephone number'))
    op.add_column('agencies', sa.Column('agency_fare_url', sa.String(500), nullable=True,
                  comment='GTFS agency_fare_url - URL for fare information'))
    op.add_column('agencies', sa.Column('agency_email', sa.String(255), nullable=True,
                  comment='GTFS agency_email - customer service email'))

    # Migrate existing data from legacy fields to GTFS fields
    # Copy website -> agency_url
    op.execute("""
        UPDATE agencies
        SET agency_url = website
        WHERE website IS NOT NULL AND agency_url IS NULL
    """)

    # Copy contact_email -> agency_email
    op.execute("""
        UPDATE agencies
        SET agency_email = contact_email
        WHERE contact_email IS NOT NULL AND agency_email IS NULL
    """)

    # Copy contact_phone -> agency_phone
    op.execute("""
        UPDATE agencies
        SET agency_phone = contact_phone
        WHERE contact_phone IS NOT NULL AND agency_phone IS NULL
    """)


def downgrade() -> None:
    # Remove GTFS fields
    op.drop_column('agencies', 'agency_email')
    op.drop_column('agencies', 'agency_fare_url')
    op.drop_column('agencies', 'agency_phone')
    op.drop_column('agencies', 'agency_lang')
    op.drop_column('agencies', 'agency_timezone')
    op.drop_column('agencies', 'agency_url')
    op.drop_column('agencies', 'agency_id')
