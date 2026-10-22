"""Shared pytest fixtures.

Integration tests need a real MySQL 8 server because the schema uses
``POINT SRID 4326`` and spatial indexes, which no in-memory database can
emulate. The fixture creates and migrates a dedicated ``schemeping_test``
database, so the development database is never touched.

Connection details come from ``TEST_DATABASE_BASE_URL`` (default: the compose
MySQL on port 3307). If the server is unreachable, every test that needs the
database is skipped rather than failed.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_NAME = "schemeping_test"
_BASE_URL = os.environ.get(
    "TEST_DATABASE_BASE_URL",
    "mysql+pymysql://schemeping:schemeping@127.0.0.1:3307",
)

# These must be set before any application module is imported: settings are
# cached and the engine is created at import time.
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"{_BASE_URL}/{TEST_DATABASE_NAME}?charset=utf8mb4"
os.environ["SECRET_KEY"] = "test-only-secret-key-not-used-outside-tests-000000"
os.environ["ENCRYPTION_KEY"] = "1nS5NFwSoYVbHVFNZAdX-2L1B63shyOWmjn8b78mwG4="
# No network in tests: the mock LLM provider builds output from the record.
os.environ["LLM_PROVIDER"] = "mock"
os.environ["GEMINI_API_KEY"] = ""

# Child rows first so TRUNCATE works without disabling foreign keys.
_TRUNCATE_ORDER = (
    "chat_messages",
    "analytics_events",
    "eligibility_results",
    "notifications",
    "scheme_translations",
    "admin_audit_logs",
    "admin_users",
    "otp_requests",
    "refresh_tokens",
    "family_members",
    "users",
    "schemes",
    "facilities",
)


def _server_engine() -> Engine:
    return create_engine(make_url(_BASE_URL).set(database=None), pool_pre_ping=True)


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[None]:
    """Create a clean test database and run every migration once."""
    from alembic import command
    from alembic.config import Config

    try:
        server = _server_engine()
        with server.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{TEST_DATABASE_NAME}`"))
            connection.execute(
                text(
                    f"CREATE DATABASE `{TEST_DATABASE_NAME}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            connection.commit()
        server.dispose()
    except Exception as exc:
        pytest.skip(f"MySQL test server unavailable at {_BASE_URL}: {exc}")

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")

    yield

    from app.core.db import engine

    engine.dispose()


@pytest.fixture(autouse=True)
def reset_rate_limits() -> Iterator[None]:
    """The in-process limiter is shared by every test in the session."""
    from app.core.ratelimit import _limiter

    _limiter.reset()
    yield
    _limiter.reset()


@pytest.fixture
def db(migrated_database: None) -> Iterator[Session]:
    """A session against an empty database; all rows removed before each test."""
    from app.core.db import SessionLocal, engine

    with engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in _TRUNCATE_ORDER:
            connection.execute(text(f"TRUNCATE TABLE `{table}`"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


class RecordingOtpProvider:
    """Test provider: records the plaintext OTP instead of sending an SMS."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_otp(self, mobile: str, code: str) -> None:
        self.sent.append((mobile, code))

    def send_template(
        self, mobile: str, template_name: str, params: dict, language: str = "en"
    ) -> str | None:
        return None

    @property
    def last_code(self) -> str:
        return self.sent[-1][1]

    def code_for(self, mobile: str) -> str:
        for sent_mobile, code in reversed(self.sent):
            if sent_mobile == mobile:
                return code
        raise AssertionError(f"No OTP recorded for {mobile}")


@pytest.fixture
def otp_provider(monkeypatch) -> RecordingOtpProvider:
    provider = RecordingOtpProvider()
    monkeypatch.setattr(
        "app.services.otp.get_messaging_provider", lambda: provider
    )
    return provider


@pytest.fixture
def client(migrated_database: None, otp_provider: RecordingOtpProvider, db):
    """An HTTP client on top of an empty database.

    Depends on ``db`` purely so every test starts from a truncated database;
    the app uses its own sessions.
    """
    from app.main import create_app
    from fastapi.testclient import TestClient

    with TestClient(create_app()) as test_client:
        yield test_client


# Password used by the session fixtures. Registration signs the user in, so a
# fixture that needs a session does not need a second request.
TEST_PASSWORD = "schemeping-test-password"


@pytest.fixture
def logged_in_client(client):
    """A client with an active session for a freshly registered account."""

    response = client.post(
        "/api/v1/auth/register",
        json={"mobile": "9876543210", "password": TEST_PASSWORD},
    )
    assert response.status_code == 201, response.text
    return client


@pytest.fixture
def make_logged_in_client(migrated_database: None, db):
    """Factory for additional independent sessions (used for isolation tests)."""

    from app.main import create_app
    from fastapi.testclient import TestClient

    created: list = []

    def _factory(mobile: str):
        test_client = TestClient(create_app())
        test_client.__enter__()
        created.append(test_client)
        register = test_client.post(
            "/api/v1/auth/register",
            json={"mobile": mobile, "password": TEST_PASSWORD},
        )
        assert register.status_code == 201, register.text
        return test_client

    yield _factory

    for test_client in created:
        test_client.__exit__(None, None, None)


# ------------------------------------------------------------------ phase 4


def make_completed_profile(db: Session, **overrides):
    """Create a user whose profile satisfies the engine's address fields.

    Fields mirror ``PUT /me``; overrides replace individual fields. Returns
    the ``User`` row (probably not yet recomputed).
    """
    from app.models.user import User

    values: dict = {
        "name": "Lakshmi",
        "dob": "1985-06-15",
        "gender": "female",
        "occupation": "farmer",
        "annual_income": 180000,
        "education": "secondary",
        "marital_status": "married",
        "state": "Tamil Nadu",
        "district": "Erode",
        "locality": "Perundurai",
        "pincode": "638052",
        "is_disabled": False,
        "language": "en",
        "consent_data_processing": True,
        "consent_whatsapp": False,
        "consent_version": "2026-07-01",
    }
    values.update(overrides)

    # The engine derives age from a date object; strings only work when a
    # Pydantic schema parses them first (API flows). Grow a real date here.
    if values.get("dob") is not None and not hasattr(values["dob"], "year"):
        values["dob"] = date.fromisoformat(str(values["dob"]))
    # Same for family-member helpers that may pass dob strings.

    mobile = values.pop("mobile", "9876543210")
    user = User(mobile=mobile, **values)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def seed_sample_facilities_and_schemes(db: Session) -> None:
    """Load the seed files (drafts + samples) and publish sample schemes."""
    from seed.load_schemes import publish_sample_schemes, seed_all

    seed_all(db)
    publish_sample_schemes(db)
