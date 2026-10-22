#!/bin/sh
set -eu

echo "Waiting for the database..."
python -m app.core.wait_for_db

echo "Applying database migrations..."
alembic upgrade head

if [ "${SEED_ON_START:-false}" = "true" ]; then
  echo "Loading sample seed data..."
  python -m seed.load_schemes
fi

exec "$@"
