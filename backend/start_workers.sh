#!/bin/bash
# Start multiple Celery workers for parallel task processing
# Since we use asyncio tasks with solo pool, we spawn N worker processes

CONCURRENCY=${CELERY_WORKER_CONCURRENCY:-4}

echo "Starting $CONCURRENCY Celery worker(s) with solo pool..."

# Start workers in background, keeping the last one in foreground
# Each worker needs its own state file to avoid locking conflicts
for i in $(seq 1 $((CONCURRENCY - 1))); do
    echo "Starting worker $i..."
    celery -A app.celery_app worker \
        --loglevel=info \
        --pool=solo \
        --hostname="worker-${i}@%h" \
        --statedb="/tmp/celery_worker_state_${i}" \
        --concurrency=1 &
done

# Start the last worker in foreground to keep container running
echo "Starting worker $CONCURRENCY (foreground)..."
exec celery -A app.celery_app worker \
    --loglevel=info \
    --pool=solo \
    --hostname="worker-${CONCURRENCY}@%h" \
    --statedb="/tmp/celery_worker_state_${CONCURRENCY}" \
    --concurrency=1
