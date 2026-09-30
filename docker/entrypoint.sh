#!/usr/bin/env bash
set -e

# ==============================================================================
# Container Entrypoint Script
# Waits for dependencies (Postgres, Redis) and runs migrations if specified
# ==============================================================================

PG_HOST="${POSTGRES_HOST:-postgres}"
PG_PORT="${POSTGRES_PORT:-5432}"
REDIS_H="${REDIS_HOST:-redis}"
REDIS_P="${REDIS_PORT:-6379}"

echo "[entrypoint] Checking connectivity to PostgreSQL ($PG_HOST:$PG_PORT)..."
timeout=60
counter=0
until nc -z "$PG_HOST" "$PG_PORT"; do
  sleep 1
  counter=$((counter + 1))
  if [ "$counter" -ge "$timeout" ]; then
    echo "[entrypoint] ERROR: Timed out waiting for PostgreSQL to become available."
    exit 1
  fi
done
echo "[entrypoint] PostgreSQL is accessible."

echo "[entrypoint] Checking connectivity to Redis ($REDIS_H:$REDIS_P)..."
counter=0
until nc -z "$REDIS_H" "$REDIS_P"; do
  sleep 1
  counter=$((counter + 1))
  if [ "$counter" -ge "$timeout" ]; then
    echo "[entrypoint] ERROR: Timed out waiting for Redis to become available."
    exit 1
  fi
done
echo "[entrypoint] Redis is accessible."

# Run database migrations if RUN_MIGRATIONS is true or when executing API web service in dev
if [ "${RUN_MIGRATIONS:-false}" = "true" ] || [ "${1}" = "uvicorn" ]; then
  echo "[entrypoint] Running Alembic database migrations..."
  alembic upgrade head || echo "[entrypoint] Migration failed or skipped (ensure DB is initialized)"
fi

echo "[entrypoint] Starting command: $@"
exec "$@"
