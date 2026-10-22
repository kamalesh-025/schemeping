"""Runtime capability flags: only offer WhatsApp delivery when it can work."""

from __future__ import annotations

from app.core.config import get_settings
from app.services.messaging import whatsapp_delivery_configured
from fastapi.testclient import TestClient


def test_features_default_to_the_free_share_link(client: TestClient) -> None:
    response = client.get("/api/v1/features")

    assert response.status_code == 200
    body = response.json()
    # The default WHATSAPP_PROVIDER is mock: it accepts messages but cannot
    # deliver them, so the frontend must use the wa.me link instead.
    assert body["whatsapp_delivery"] is False
    assert body["whatsapp_click_to_chat"] is True


def test_meta_without_credentials_is_not_delivery(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_provider", "meta")
    monkeypatch.setattr(settings, "meta_whatsapp_phone_number_id", "")
    monkeypatch.setattr(settings, "meta_whatsapp_access_token", "")

    assert whatsapp_delivery_configured() is False


def test_meta_with_credentials_is_delivery(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_provider", "meta")
    monkeypatch.setattr(settings, "meta_whatsapp_phone_number_id", "1234567890")
    monkeypatch.setattr(settings, "meta_whatsapp_access_token", "token")

    assert whatsapp_delivery_configured() is True


def test_msg91_needs_a_template_mapping(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_provider", "msg91")
    monkeypatch.setattr(settings, "msg91_auth_key", "key")
    monkeypatch.setattr(settings, "msg91_whatsapp_number", "919876543210")
    monkeypatch.setattr(settings, "msg91_whatsapp_template_ids", "")

    assert whatsapp_delivery_configured() is False

    monkeypatch.setattr(
        settings, "msg91_whatsapp_template_ids", "scheme_summary:template-id"
    )
    assert whatsapp_delivery_configured() is True


def test_log_provider_is_not_delivery(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_provider", "log")

    assert whatsapp_delivery_configured() is False
