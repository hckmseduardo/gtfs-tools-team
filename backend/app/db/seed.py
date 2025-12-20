"""Seed database with sample data for development"""

import asyncio
from sqlalchemy import select, text
from app.db.session import AsyncSessionLocal
from app.models.user import User, UserRole
from app.models.agency import Agency

# Import all models to ensure relationships can be resolved
from app.db import base  # noqa: F401


async def seed_data() -> None:
    """Seed development database with sample data"""

    print("Starting database seeding...")

    async with AsyncSessionLocal() as db:
        # Check if data already exists
        result = await db.execute(select(User))
        if result.scalars().first():
            print("Database already seeded. Skipping...")
            return

        # Create super admin user
        super_admin = User(
            email="admin@gtfs-tools.local",
            full_name="System Administrator",
            is_active=True,
            is_superuser=True,
        )
        db.add(super_admin)

        # Create sample agencies
        agency1 = Agency(
            name="Metro Transit Authority",
            slug="metro-transit",
            is_active=True,
            contact_email="contact@metro-transit.local",
            contact_phone="+1-555-0100",
            website="https://metro-transit.local",
        )
        db.add(agency1)

        agency2 = Agency(
            name="City Bus Services",
            slug="city-bus",
            is_active=True,
            contact_email="info@citybus.local",
            contact_phone="+1-555-0200",
            website="https://citybus.local",
        )
        db.add(agency2)

        # Create sample users
        editor_user = User(
            email="editor@gtfs-tools.local",
            full_name="John Editor",
            is_active=True,
            is_superuser=False,
        )
        db.add(editor_user)

        viewer_user = User(
            email="viewer@gtfs-tools.local",
            full_name="Jane Viewer",
            is_active=True,
            is_superuser=False,
        )
        db.add(viewer_user)

        # Commit to get IDs
        await db.commit()
        await db.refresh(agency1)
        await db.refresh(agency2)
        await db.refresh(editor_user)
        await db.refresh(viewer_user)

        # Assign users to agencies (using raw SQL for now)
        await db.execute(
            text("""
                INSERT INTO user_agencies (user_id, agency_id, role)
                VALUES
                    (:admin_id, :agency1_id, 'super_admin'),
                    (:admin_id, :agency2_id, 'super_admin'),
                    (:editor_id, :agency1_id, 'editor'),
                    (:viewer_id, :agency1_id, 'viewer'),
                    (:viewer_id, :agency2_id, 'viewer')
            """),
            {
                "admin_id": super_admin.id,
                "agency1_id": agency1.id,
                "agency2_id": agency2.id,
                "editor_id": editor_user.id,
                "viewer_id": viewer_user.id,
            },
        )

        await db.commit()

    print("✅ Database seeded successfully!")
    print("\nSample users created:")
    print("  - admin@gtfs-tools.local (Super Admin)")
    print("  - editor@gtfs-tools.local (Editor for Metro Transit)")
    print("  - viewer@gtfs-tools.local (Viewer for both agencies)")
    print("\nSample agencies created:")
    print("  - Metro Transit Authority (slug: metro-transit)")
    print("  - City Bus Services (slug: city-bus)")


if __name__ == "__main__":
    asyncio.run(seed_data())
