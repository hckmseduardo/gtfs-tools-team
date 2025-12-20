"""unify agencies and gtfs_agencies tables

Revision ID: unify_agencies_001
Revises: add_trips_cars_allowed
Create Date: 2025-12-14 25:00:00.000000

This migration removes the gtfs_agencies table and uses the agencies table
as the single source of truth for GTFS agency data.

Steps:
1. For each unique (gtfs_agency_id, agency_name) in gtfs_agencies, create Agency if not exists
2. Update routes to reference the correct Agency based on their gtfs_agency_id
3. Drop gtfs_agency_id column from gtfs_routes
4. Drop gtfs_agencies table
"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'unify_agencies_001'
down_revision: Union[str, None] = 'add_trips_cars_allowed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Step 1: Get all unique GTFSAgency records that need Agency records
    # We group by gtfs_agency_id to avoid duplicates across feeds
    gtfs_agencies = conn.execute(sa.text("""
        SELECT DISTINCT ON (gtfs_agency_id)
            gtfs_agency_id,
            agency_name,
            agency_url,
            agency_timezone,
            agency_lang,
            agency_phone,
            agency_fare_url,
            agency_email
        FROM gtfs_agencies
        WHERE gtfs_agency_id IS NOT NULL AND gtfs_agency_id != ''
        ORDER BY gtfs_agency_id, created_at
    """)).fetchall()

    # Create Agency records for each unique gtfs_agency_id that doesn't have one
    for ga in gtfs_agencies:
        gtfs_agency_id = ga[0]
        agency_name = ga[1]

        # Check if Agency with this agency_id already exists
        existing = conn.execute(sa.text("""
            SELECT id FROM agencies WHERE agency_id = :agency_id
        """), {"agency_id": gtfs_agency_id}).fetchone()

        if not existing:
            # Generate unique slug
            base_slug = agency_name.lower().replace(' ', '_').replace('-', '_')[:80]
            slug = base_slug
            counter = 1
            while True:
                slug_exists = conn.execute(sa.text("""
                    SELECT 1 FROM agencies WHERE slug = :slug
                """), {"slug": slug}).fetchone()
                if not slug_exists:
                    break
                slug = f"{base_slug}_{counter}"
                counter += 1

            # Create new Agency
            conn.execute(sa.text("""
                INSERT INTO agencies (
                    name, slug, agency_id, agency_url, agency_timezone,
                    agency_lang, agency_phone, agency_fare_url, agency_email,
                    is_active, created_at, updated_at
                ) VALUES (
                    :name, :slug, :agency_id, :agency_url, :agency_timezone,
                    :agency_lang, :agency_phone, :agency_fare_url, :agency_email,
                    true, :created_at, :updated_at
                )
            """), {
                "name": agency_name,
                "slug": slug,
                "agency_id": gtfs_agency_id,
                "agency_url": ga[2],
                "agency_timezone": ga[3],
                "agency_lang": ga[4],
                "agency_phone": ga[5],
                "agency_fare_url": ga[6],
                "agency_email": ga[7],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            })

    # Step 2: Update routes to reference the correct Agency
    # For routes with a gtfs_agency_id, find the matching Agency and update agency_id
    conn.execute(sa.text("""
        UPDATE gtfs_routes r
        SET agency_id = a.id
        FROM agencies a
        WHERE r.gtfs_agency_id = a.agency_id
        AND r.gtfs_agency_id IS NOT NULL
        AND r.gtfs_agency_id != ''
    """))

    # For routes with empty/null gtfs_agency_id, keep the existing agency_id (from feed's owner)
    # No action needed - they already reference the correct agency

    # Step 3: Drop gtfs_agency_id column from gtfs_routes
    op.drop_column('gtfs_routes', 'gtfs_agency_id')

    # Step 4: Drop gtfs_agencies table
    op.drop_table('gtfs_agencies')


def downgrade() -> None:
    # Re-create gtfs_agencies table
    op.create_table(
        'gtfs_agencies',
        sa.Column('feed_id', sa.Integer(), nullable=False),
        sa.Column('gtfs_agency_id', sa.String(255), nullable=False),
        sa.Column('agency_name', sa.String(255), nullable=False),
        sa.Column('agency_url', sa.String(500), nullable=False),
        sa.Column('agency_timezone', sa.String(100), nullable=False),
        sa.Column('agency_lang', sa.String(10), nullable=True),
        sa.Column('agency_phone', sa.String(50), nullable=True),
        sa.Column('agency_fare_url', sa.String(500), nullable=True),
        sa.Column('agency_email', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['feed_id'], ['gtfs_feeds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('feed_id', 'gtfs_agency_id'),
        comment='GTFS agencies - uses composite PK (feed_id, gtfs_agency_id)'
    )

    # Re-add gtfs_agency_id column to gtfs_routes
    op.add_column('gtfs_routes', sa.Column('gtfs_agency_id', sa.String(255), nullable=True))

    # Note: Data cannot be fully restored - GTFSAgency records would need to be re-imported
