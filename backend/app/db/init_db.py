"""Database initialization script"""

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings


async def init_db() -> None:
    """Initialize database with PostGIS extension and run migrations"""

    print("Initializing database...")

    # Create engine for database operations
    engine = create_async_engine(settings.DATABASE_URL, echo=True)

    async with engine.begin() as conn:
        # Enable PostGIS extension
        print("Enabling PostGIS extension...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis_topology;"))

        print("PostGIS extension enabled successfully!")

    await engine.dispose()

    print("Database initialization complete!")
    print("Run 'alembic upgrade head' to apply migrations.")


if __name__ == "__main__":
    asyncio.run(init_db())
