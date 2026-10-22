"""Application settings.

All configuration comes from environment variables (or a local ``.env`` file)
and is validated once at import time. Local runs can use a root-level or
backend-level ``.env`` file; Docker Compose passes root-level values directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            Path(__file__).resolve().parents[3] / ".env",
            Path(__file__).resolve().parents[2] / ".env",
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "SchemePing API"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    secret_key: str = Field(min_length=16)

    encryption_key: str = Field(
        min_length=32,
        description="Fernet key(s), comma separated. The first key encrypts new data.",
    )

    database_url: str = Field(
        default="mysql+pymysql://schemeping:schemeping@127.0.0.1:3306/schemeping?charset=utf8mb4"
    )
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_recycle: int = 1800

    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str = "redis://127.0.0.1:6379/1"
    celery_result_backend: str = "redis://127.0.0.1:6379/2"

    # ---- Authentication ----
    # password: mobile number + password (default; no SMS vendor needed).
    # otp: one-time code by SMS. Needs MESSAGING_PROVIDER and, in India, DLT
    # registration unless the MSG91 OTP widget is used.
    auth_mode: Literal["password", "otp"] = "password"
    password_min_length: int = Field(default=8, ge=6, le=64)
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=120)
    admin_token_ttl_minutes: int = Field(default=30, ge=1, le=240)
    # The SQLAdmin panel (staff UI) at /admin.
    admin_panel_enabled: bool = True
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=365)
    access_cookie_name: str = "sp_access"
    refresh_cookie_name: str = "sp_refresh"
    cookie_secure: bool | None = Field(
        default=None,
        description="Defaults to true in production, false everywhere else.",
    )
    cookie_domain: str | None = None

    # ---- OTP ----
    otp_ttl_minutes: int = Field(default=5, ge=1, le=15)
    otp_length: int = Field(default=6, ge=4, le=8)
    otp_max_requests_per_mobile: int = Field(default=3, ge=1, le=20)
    otp_max_requests_per_ip: int = Field(default=10, ge=1, le=200)
    otp_request_window_minutes: int = Field(default=15, ge=1, le=60)
    otp_max_attempts: int = Field(default=5, ge=1, le=10)

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0
    sentry_environment: str = "development"

    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    # The alias tracks Google's current free-tier Flash model. Pinning a dated
    # model (for example gemini-2.5-flash) breaks without warning the day
    # Google retires it for new keys, which surfaces as HTTP 404 to every user.
    gemini_model: str = "gemini-flash-latest"
    # Chat assistant provider (Phase 6). "claude" uses ANTHROPIC_API_KEY;
    # anything else follows llm_provider.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"
    # Assistant quotas: per-user chat turns per hour and context size.
    chat_rate_limit_per_hour: int = 20
    chat_record_limit: int = 6
    chat_history_retention_days: int = 14

    messaging_provider: str = "log"
    meta_whatsapp_phone_number_id: str = ""
    meta_whatsapp_access_token: str = ""
    meta_whatsapp_verify_token: str = ""
    meta_whatsapp_app_secret: str = ""
    meta_whatsapp_api_version: str = "v22.0"
    msg91_auth_key: str = ""
    msg91_sender_id: str = ""
    msg91_otp_template_id: str = ""
    # OTP Widget mode (MESSAGING_PROVIDER=msg91_widget). MSG91 sends and verifies
    # the code in the browser using its own DLT-registered sender and default
    # template, so no DLT registration is needed. The widget id and its public
    # token are served to the SPA; the auth key never leaves the server.
    msg91_widget_id: str = ""
    msg91_widget_token: str = ""

    # ---- WhatsApp (Phase 5) ----
    # mock: records messages in memory (default, dev/CI). log: console only.
    # msg91: production provider, requires the credentials below plus DLT.
    whatsapp_provider: str = "mock"
    msg91_whatsapp_number: str = ""
    # Comma-separated "template_name:msg91_template_id" mapping for the six
    # pre-approved WhatsApp templates (see docs/whatsapp-templates.md).
    msg91_whatsapp_template_ids: str = ""
    # Shared secret for the delivery-status webhook (MSG91 configuration).
    whatsapp_webhook_secret: str = "change-me-whatsapp-webhook-secret"
    # Notifications are drained with retries; -1 means infinite, capped by
    # the task-runtime limits.
    send_notification_retries: int = 3

    # ---- Background jobs ----
    # Hourly cap for user-initiated "Send to WhatsApp" messages.
    send_whatsapp_hourly_limit: int = Field(default=10, ge=1, le=100)
    # Whether the scheduled jobs are enabled (beat schedule is inside celery_app).
    notifications_schedule_enabled: bool = True

    # ---- Admin API (shared key for the machine-to-machine endpoints) ----
    admin_api_key: str = "dev-admin-key-change-me"

    seed_on_start: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        level = value.upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        if level not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return level

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
