"""add_feed_permissions_and_update_team_roles

Revision ID: 1016627eb9b8
Revises: ef51befcb7dc
Create Date: 2025-12-02 21:58:23.326784

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1016627eb9b8'
down_revision: Union[str, None] = 'ef51befcb7dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create FeedRole enum type if it doesn't exist
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE feedrole AS ENUM ('owner', 'admin', 'contributor', 'read_only');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Create feed_teams table if it doesn't exist
    op.execute("""
        CREATE TABLE IF NOT EXISTS feed_teams (
            feed_id INTEGER NOT NULL REFERENCES gtfs_feeds(id) ON DELETE CASCADE,
            team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            role feedrole NOT NULL,
            PRIMARY KEY (feed_id, team_id)
        );
        COMMENT ON COLUMN feed_teams.role IS 'Team role for this feed';
    """)

    # Create feed_users table if it doesn't exist
    op.execute("""
        CREATE TABLE IF NOT EXISTS feed_users (
            feed_id INTEGER NOT NULL REFERENCES gtfs_feeds(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role feedrole NOT NULL,
            PRIMARY KEY (feed_id, user_id)
        );
        COMMENT ON COLUMN feed_users.role IS 'User role for this feed';
    """)

    # Update TeamRole enum: add 'contributor' and 'read_only'
    # Note: PostgreSQL enums can only have values added, not removed
    op.execute("ALTER TYPE teamrole ADD VALUE IF NOT EXISTS 'contributor'")
    op.execute("ALTER TYPE teamrole ADD VALUE IF NOT EXISTS 'read_only'")

    # Migrate existing 'member' roles to 'contributor' if 'member' exists
    # Use a safer approach that doesn't fail if 'member' doesn't exist in enum
    op.execute("""
        DO $$
        BEGIN
            -- Check if 'member' exists in the enum and migrate to 'contributor'
            IF EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'member'
                       AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'teamrole')) THEN
                UPDATE team_members SET role = 'contributor' WHERE role = 'member';
                UPDATE team_invitations SET role = 'contributor' WHERE role = 'member';
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Migrate 'contributor' back to 'member' before removing enum values
    # Note: PostgreSQL doesn't support removing enum values, so this is a best-effort migration
    op.execute("""
        UPDATE team_members SET role = 'member' WHERE role = 'contributor'
    """)
    op.execute("""
        UPDATE team_invitations SET role = 'member' WHERE role = 'contributor'
    """)

    # Drop feed permission tables
    op.drop_table('feed_users')
    op.drop_table('feed_teams')

    # Drop FeedRole enum
    op.execute("DROP TYPE IF EXISTS feedrole")
