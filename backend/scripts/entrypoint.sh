#!/bin/bash
set -e

echo "Starting GTFS Editor Backend..."

# Extract hostnames from DATABASE_URL and REDIS_URL if set
# DATABASE_URL format: postgresql+asyncpg://user:pass@host:port/db
# REDIS_URL format: redis://host:port/db

if [ -n "$DATABASE_URL" ]; then
    # Extract host:port from DATABASE_URL
    DB_HOST_PORT=$(echo "$DATABASE_URL" | sed -E 's|.*@([^/]+)/.*|\1|')
    DB_HOST=$(echo "$DB_HOST_PORT" | cut -d: -f1)
    DB_PORT=$(echo "$DB_HOST_PORT" | cut -d: -f2)
else
    DB_HOST="postgres"
    DB_PORT="5432"
fi

if [ -n "$REDIS_URL" ]; then
    # Extract host:port from REDIS_URL
    REDIS_HOST_PORT=$(echo "$REDIS_URL" | sed -E 's|redis://([^/]+)/.*|\1|')
    REDIS_HOST=$(echo "$REDIS_HOST_PORT" | cut -d: -f1)
    REDIS_PORT=$(echo "$REDIS_HOST_PORT" | cut -d: -f2)
    [ -z "$REDIS_PORT" ] && REDIS_PORT="6379"
else
    REDIS_HOST="redis"
    REDIS_PORT="6379"
fi

echo "Database host: $DB_HOST:$DB_PORT"
echo "Redis host: $REDIS_HOST:$REDIS_PORT"

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
while ! nc -z "$DB_HOST" "$DB_PORT"; do
  sleep 0.1
done
echo "PostgreSQL started"

# Wait for Redis to be ready
echo "Waiting for Redis..."
while ! nc -z "$REDIS_HOST" "$REDIS_PORT"; do
  sleep 0.1
done
echo "Redis started"

# Initialize database (PostGIS extension)
echo "Initializing database..."
python -m app.db.init_db

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

echo "Database setup complete!"

# Execute the main command
exec "$@"
