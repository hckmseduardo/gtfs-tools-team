"""simplify_team_roles_and_add_workspace_members

Simplifies TeamRole from 4 roles (owner, admin, contributor, read_only) to 3:
- owner: Full control, invite users, create workspaces
- editor: Can edit data (replaces contributor)
- viewer: Read-only access (replaces read_only)

Also adds workspace_members table for workspace-level access control.

Revision ID: a1b2c3d4e5f6
Revises: 46b3c6dec493
Create Date: 2025-12-04 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '46b3c6dec493'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create workspace_members table for workspace-level access control
    op.execute("""
        CREATE TABLE IF NOT EXISTS workspace_members (
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            PRIMARY KEY (workspace_id, user_id)
        );
    """)

    # Add new enum values for 'owner' (lowercase), 'editor' and 'viewer'
    # The original enum had OWNER (uppercase), we need lowercase versions
    op.execute("ALTER TYPE teamrole ADD VALUE IF NOT EXISTS 'owner'")
    op.execute("ALTER TYPE teamrole ADD VALUE IF NOT EXISTS 'editor'")
    op.execute("ALTER TYPE teamrole ADD VALUE IF NOT EXISTS 'viewer'")

    # PostgreSQL requires a commit before using newly added enum values
    op.execute("COMMIT")
    op.execute("BEGIN")

    # Grant all existing non-owner team members access to all workspaces in their teams
    # This ensures backward compatibility - existing users don't lose access
    # Note: At this point only uppercase 'OWNER' exists in the enum, so we exclude it
    op.execute("""
        INSERT INTO workspace_members (workspace_id, user_id)
        SELECT DISTINCT w.id, tm.user_id
        FROM workspaces w
        JOIN team_members tm ON w.team_id = tm.team_id
        WHERE tm.role::text != 'OWNER'
        ON CONFLICT (workspace_id, user_id) DO NOTHING;
    """)

    # Migrate all roles to lowercase versions:
    # - OWNER/ADMIN -> owner (promote admins to owners since we're simplifying)
    # - MEMBER/contributor -> editor
    # - read_only -> viewer
    # Note: Use text casting for comparison and cast to new lowercase enum values
    op.execute("""
        UPDATE team_members SET role = 'owner'::teamrole WHERE role::text IN ('OWNER', 'ADMIN', 'admin');
    """)
    op.execute("""
        UPDATE team_members SET role = 'editor'::teamrole WHERE role::text IN ('MEMBER', 'member', 'contributor', 'CONTRIBUTOR');
    """)
    op.execute("""
        UPDATE team_members SET role = 'viewer'::teamrole WHERE role::text IN ('read_only', 'READ_ONLY');
    """)

    # Also update invitations
    op.execute("""
        UPDATE team_invitations SET role = 'owner'::teamrole WHERE role::text IN ('OWNER', 'ADMIN', 'admin');
    """)
    op.execute("""
        UPDATE team_invitations SET role = 'editor'::teamrole WHERE role::text IN ('MEMBER', 'member', 'contributor', 'CONTRIBUTOR');
    """)
    op.execute("""
        UPDATE team_invitations SET role = 'viewer'::teamrole WHERE role::text IN ('read_only', 'READ_ONLY');
    """)


def downgrade() -> None:
    # Migrate roles back:
    # - owner (that was admin) - keep as owner (can't distinguish)
    # - editor -> contributor
    # - viewer -> read_only
    op.execute("""
        UPDATE team_members SET role = 'contributor' WHERE role = 'editor';
    """)
    op.execute("""
        UPDATE team_members SET role = 'read_only' WHERE role = 'viewer';
    """)

    op.execute("""
        UPDATE team_invitations SET role = 'contributor' WHERE role = 'editor';
    """)
    op.execute("""
        UPDATE team_invitations SET role = 'read_only' WHERE role = 'viewer';
    """)

    # Drop workspace_members table
    op.drop_table('workspace_members')

    # Note: Cannot remove enum values in PostgreSQL, so 'editor' and 'viewer' will remain
