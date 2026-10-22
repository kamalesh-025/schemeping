from __future__ import annotations

from typing import Any

import httpx
import pytest
from app.services.messaging import (
    WHATSAPP_TEMPLATES,
    MessagingError,
    MetaWhatsAppProvider,
    Msg91OtpProvider,
    Msg91WidgetVerifier,
)


def test_meta_provider_sends_approved_template_and_returns_message_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request: dict[str, Any] = {}

    def post(url: str, **kwargs: Any) -> httpx.Response:
        request.update(url=url, **kwargs)
        return httpx.Response(
            200,
            json={"messages": [{"id": "wamid.example"}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.services.messaging.httpx.post", post)
    provider = MetaWhatsAppProvider("phone-id", "access-token", "v22.0")
    template = WHATSAPP_TEMPLATES["scheme_summary"]
    params = {name: f"value-{name}" for name in template.variables}

    message_id = provider.send_template(
        "9876543210", "scheme_summary", params, language="ta"
    )

    assert message_id == "wamid.example"
    assert request["url"] == "https://graph.facebook.com/v22.0/phone-id/messages"
    assert request["headers"] == {"Authorization": "Bearer access-token"}
    assert request["json"]["to"] == "919876543210"
    assert request["json"]["template"]["language"] == {"code": "ta"}
    assert request["json"]["template"]["components"][0]["parameters"] == [
        {"type": "text", "text": params[name]} for name in template.variables
    ]


def test_meta_provider_rejects_unapproved_or_incomplete_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.messaging.httpx.post",
        lambda *args, **kwargs: pytest.fail("must not call Meta for invalid template data"),
    )
    provider = MetaWhatsAppProvider("phone-id", "access-token")

    with pytest.raises(MessagingError, match="Unknown WhatsApp template"):
        provider.send_template("9876543210", "not_approved", {})
    with pytest.raises(MessagingError, match="missing variables"):
        provider.send_template("9876543210", "scheme_summary", {})


def test_meta_provider_requires_credentials() -> None:
    with pytest.raises(MessagingError, match="META_WHATSAPP_PHONE_NUMBER_ID"):
        MetaWhatsAppProvider("", "")


def test_msg91_otp_sends_template_and_accepts_success_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request: dict[str, Any] = {}

    def post(url: str, **kwargs: Any) -> httpx.Response:
        request.update(url=url, **kwargs)
        return httpx.Response(
            200,
            json={"type": "success", "message": "OTP sent successfully", "request_id": "r1"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.services.messaging.httpx.post", post)
    Msg91OtpProvider("auth-key", "template-id", "SOCKET").send_otp("9876543210", "123456")

    assert request["url"] == "https://control.msg91.com/api/v5/otp"
    assert request["headers"]["authkey"] == "auth-key"
    assert request["json"]["mobile"] == "919876543210"
    assert request["json"]["otp"] == "123456"
    assert request["json"]["template_id"] == "template-id"
    assert request["json"]["sender"] == "SOCKET"


def test_msg91_otp_raises_on_error_envelope_with_http_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MSG91 answers 200 even when it rejects the send. A bare 200 is not delivery."""

    monkeypatch.setattr(
        "app.services.messaging.httpx.post",
        lambda url, **kwargs: httpx.Response(
            200,
            json={"type": "error", "message": "Template ID is invalid"},
            request=httpx.Request("POST", url),
        ),
    )

    with pytest.raises(MessagingError, match="Template ID is invalid"):
        Msg91OtpProvider("auth-key", "template-id").send_otp("9876543210", "123456")


def test_msg91_otp_raises_on_unparseable_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.messaging.httpx.post",
        lambda url, **kwargs: httpx.Response(
            200, text="<html>gateway</html>", request=httpx.Request("POST", url)
        ),
    )

    with pytest.raises(MessagingError, match="Could not send the OTP SMS"):
        Msg91OtpProvider("auth-key", "template-id").send_otp("9876543210", "123456")


def test_msg91_otp_requires_credentials() -> None:
    with pytest.raises(MessagingError, match="MSG91_AUTH_KEY"):
        Msg91OtpProvider("", "template-id")


def test_widget_verifier_returns_the_verified_mobile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request: dict[str, Any] = {}

    def post(url: str, **kwargs: Any) -> httpx.Response:
        request.update(url=url, **kwargs)
        return httpx.Response(
            200,
            json={"type": "success", "message": "919876543210"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.services.messaging.httpx.post", post)

    mobile = Msg91WidgetVerifier("auth-key").verify("widget-access-token")

    assert mobile == "9876543210"
    assert request["url"] == "https://control.msg91.com/api/v5/widget/verifyAccessToken"
    assert request["json"] == {"authkey": "auth-key", "access-token": "widget-access-token"}


def test_widget_verifier_rejects_an_error_envelope_with_http_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.messaging.httpx.post",
        lambda url, **kwargs: httpx.Response(
            200,
            json={"type": "error", "message": "AuthenticationFailure", "code": "201"},
            request=httpx.Request("POST", url),
        ),
    )

    with pytest.raises(MessagingError, match="could not verify"):
        Msg91WidgetVerifier("auth-key").verify("widget-access-token")


def test_widget_verifier_rejects_email_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.messaging.httpx.post",
        lambda url, **kwargs: httpx.Response(
            200,
            json={"type": "success", "message": "person@example.com"},
            request=httpx.Request("POST", url),
        ),
    )

    with pytest.raises(MessagingError, match="mobile number"):
        Msg91WidgetVerifier("auth-key").verify("widget-access-token")


def test_widget_verifier_requires_an_auth_key() -> None:
    with pytest.raises(MessagingError, match="MSG91_AUTH_KEY"):
        Msg91WidgetVerifier("")
