-- GTFS-Editor PostgreSQL Initialization Script
-- This runs when a new team's PostgreSQL container starts

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- The application will run Alembic migrations on first startup
-- to create all tables and schema

-- Log that initialization is complete
DO $$
BEGIN
    RAISE NOTICE 'GTFS-Editor database initialized with PostGIS extensions';
END $$;
