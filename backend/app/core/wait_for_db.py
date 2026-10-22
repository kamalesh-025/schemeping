"""Wait for MySQL to accept connections before starting the API or migrations.

Docker healthchecks already gate the api service, but this makes local runs and
the entrypoint resilient to slow first-time initialisation of the MySQL volume.
"""

from __future__ import annotations

import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings

MAX_WAIT_SECONDS = 60


def main() -> int:
    settings = get_settings()
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    attempt = 0

    while time.monotonic() < deadline:
        attempt += 1
        try:
            engine = create_engine(settings.database_url, pool_pre_ping=True)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            engine.dispose()
            print(f"Database reachable after {attempt} attempt(s).")
            return 0
        except SQLAlchemyError as exc:
            print(f"Database not ready (attempt {attempt}): {type(exc).__name__}")
            time.sleep(2)

    print("Database did not become ready in time.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
