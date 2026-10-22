"""Messaging provider interface.

Two messaging channels run behind the ``MessagingProvider`` protocol:

- SMS OTP (Phase 2): ``LogOtpProvider`` (dev/test) and ``Msg91OtpProvider``.
- WhatsApp: every business-initiated message MUST use a pre-approved template
  (see ``WHATSAPP_TEMPLATES`` and ``docs/whatsapp-templates.md``).
  Implementations include mock/log development providers and Meta/MSG91
  production providers.

Switching is one environment variable: ``WHATSAPP_PROVIDER``, plus
``MESSAGING_PROVIDER`` for the OTP SMS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

import httpx

from app.core.config import get_settings
from app.core.security import mask_mobile
from app.schemas.validators import is_valid_mobile, normalise_mobile

logger = logging.getLogger(__name__)


class MessagingError(RuntimeError):
    """Raised when a provider fails to deliver a message."""


@runtime_checkable
class MessagingProvider(Protocol):
    def send_otp(self, mobile: str, code: str) -> None: ...

    def send_template(
        self,
        mobile: str,
        template_name: str,
        params: dict[str, Any],
        language: str = "en",
    ) -> str | None: ...


# ------------------------------------------------------------------ templates


@dataclass(frozen=True)
class WhatsAppTemplate:
    """One pre-approved WhatsApp template.

    ``variables`` is the ordered parameter list the provider expects; the
    sample text is exactly what is submitted for approval (mirrored in
    ``docs/whatsapp-templates.md``).
    """

    name: str
    display_name: str
    category: Literal["utility", "marketing"]
    variables: list[str]
    sample_text: str
    # The proactive category toggled in Settings; user-initiated messages
    # (scheme_summary) have none.
    pref_category: str | None = None
    eligible_for_quiet_hours: bool = True


WHATSAPP_TEMPLATES: dict[str, WhatsAppTemplate] = {
    item.name: item
    for item in [
        WhatsAppTemplate(
            name="scheme_summary",
            display_name="Scheme summary",
            category="utility",
            variables=[
                "scheme_name",
                "benefit",
                "eligibility_line",
                "documents",
                "deadline",
                "facility_name",
                "closing_line",
            ],
            sample_text=(
                "Scheme: {{scheme_name}}\n"
                "Benefit: {{benefit}}\n"
                "Eligibility: {{eligibility_line}}\n"
                "Documents Needed: {{documents}}\n"
                "Apply Before: {{deadline}}\n"
                "Nearest Center: {{facility_name}}\n"
                "{{closing_line}}"
            ),
        ),
        WhatsAppTemplate(
            name="new_scheme_eligible",
            display_name="New scheme eligible",
            category="utility",
            variables=["person_name", "scheme_name", "benefit", "deadline_line"],
            sample_text=(
                "Good news{{person_name_line}}: you are eligible for "
                "{{scheme_name}}.\nBenefit: {{benefit}}\n{{deadline_line}}\n"
                "Open SchemePing for details and documents."
            ),
            pref_category="new_schemes",
        ),
        WhatsAppTemplate(
            name="family_milestone",
            display_name="Family milestone",
            category="utility",
            variables=["person_name", "milestone_line", "scheme_name", "benefit"],
            sample_text=(
                "{{person_name}} has become eligible for {{scheme_name}} because "
                "{{milestone_line}}.\nBenefit: {{benefit}}\n"
                "Open SchemePing for details and documents."
            ),
            pref_category="family_milestones",
        ),
        WhatsAppTemplate(
            name="deadline_reminder",
            display_name="Deadline reminder",
            category="utility",
            variables=["scheme_name", "job_name", "days_left", "deadline_line"],
            sample_text=(
                "Reminder: {{job_name}} is eligible for {{scheme_name}}.\n"
                "{{days_left}}\n{{deadline_line}}\n"
                "Open SchemePing to apply."
            ),
            pref_category="deadlines",
        ),
        WhatsAppTemplate(
            name="festival_benefit",
            display_name="Festival benefit",
            category="marketing",
            variables=["greeting", "scheme_name", "benefit", "deadline_line"],
            sample_text=(
                "{{greeting}}\nYou are eligible for {{scheme_name}} this season.\n"
                "Benefit: {{benefit}}\n{{deadline_line}}"
            ),
            pref_category="festival",
        ),
    ]
}


def get_template(template_name: str) -> WhatsAppTemplate:
    """A template must be registered (pre-approved) before it can ever send."""
    template = WHATSAPP_TEMPLATES.get(template_name)
    if template is None:
        raise MessagingError(f"Unknown WhatsApp template: {template_name}")
    return template


# The scheme_summary closing line is fixed product copy, written in each of
# the six supported languages. It is part of the approved template text.
CLOSING_LINES: dict[str, str] = {
    "en": "For full details visit SchemePing.",
    "ta": "முழு விவரங்களுக்கு SchemePing பார்க்கவும்.",
    "hi": "पूरी जानकारी के लिए SchemePing देखें।",
    "te": "పూర్తి వివరాలకు SchemePing చూడండి.",
    "kn": "ಪೂರ್ತಿ ವಿವರಗಳಿಗೆ SchemePing ನೋಡಿ.",
    "ml": "മുഴുവൻ വിവരങ്ങൾക്ക് SchemePing കാണുക.",
}


def closing_line(language: str) -> str:
    return CLOSING_LINES.get(language, CLOSING_LINES["en"])


def ordered_template_params(template_name: str, params: dict[str, Any]) -> list[str]:
    """Providers that take a positional variable list (MSG91)."""
    template = get_template(template_name)
    return [str(params.get(variable, "")) for variable in template.variables]


def unknown_template_params(template_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Reject keys that are not part of the approved template.

    A variable outside the approved list must never reach a provider: it
    would mean the message no longer matches the approved sample.
    """
    template = get_template(template_name)
    unknown = set(params) - set(template.variables)
    if unknown:
        raise MessagingError(
            f"Template {template_name} does not accept variables: {sorted(unknown)}"
        )
    return params


class MockWhatsAppProvider:
    """Records every send in memory. Default for development and CI."""

    sentinel_id = 0

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.fail_next: int = 0

    def send_otp(self, mobile: str, code: str) -> None: ...  # pragma: no cover

    def send_template(
        self,
        mobile: str,
        template_name: str,
        params: dict[str, Any],
        language: str = "en",
    ) -> str | None:
        get_template(template_name)
        unknown_template_params(template_name, params)
        if self.fail_next > 0:
            self.fail_next -= 1
            raise MessagingError("Simulated provider outage (fail_next)")
        MockWhatsAppProvider.sentinel_id += 1
        message_id = f"mock-{MockWhatsAppProvider.sentinel_id}"
        self.sent.append(
            {"mobile": mobile, "template": template_name, "params": dict(params)}
        )
        logger.info(
            "whatsapp_mock_sent",
            extra={"mobile": mask_mobile(mobile), "template": template_name},
        )
        return message_id


class LogWhatsAppProvider:
    """Prints the template name to the console; never contacts the network."""

    def send_otp(self, mobile: str, code: str) -> None: ...  # pragma: no cover

    def send_template(
        self,
        mobile: str,
        template_name: str,
        params: dict[str, Any],
        language: str = "en",
    ) -> str | None:
        get_template(template_name)
        unknown_template_params(template_name, params)
        logger.info(
            "whatsapp_logged",
            extra={
                "mobile": mask_mobile(mobile),
                "template": template_name,
                "param_count": len(params),
            },
        )
        return None


class Msg91WhatsAppProvider:
    """Production WhatsApp via MSG91's WhatsApp API.

    Requires: a WhatsApp-integrated number on MSG91, DLT/WhatsApp template
    approval for every entry in ``WHATSAPP_TEMPLATES`` (the
    ``MSG91_WHATSAPP_TEMPLATE_IDS`` env maps registry name -> MSG91
    template id), and the auth key. See docs/whatsapp-templates.md.
    """

    _ENDPOINT = "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message"

    def __init__(self, auth_key: str, integrated_number: str, template_ids: dict[str, str]) -> None:
        missing = [arg for arg in (auth_key, integrated_number) if not arg]
        if missing or not template_ids:
            raise MessagingError(
                "MSG91_WHATSAPP requires MSG91_WHATSAPP_NUMBER, MSG91_AUTH_KEY and "
                "MSG91_WHATSAPP_TEMPLATE_IDS (template_name:msg91_id comma separated)"
            )
        unapproved = [
            name for name in template_ids if name not in WHATSAPP_TEMPLATES
        ]
        if unapproved:
            raise MessagingError(
                f"Unapproved template names in configuration: {unapproved}"
            )
        self._auth_key = auth_key
        self._integrated_number = integrated_number
        self._template_ids = template_ids

    def send_otp(self, mobile: str, code: str) -> None:  # pragma: no cover
        raise MessagingError("OTP SMS uses MESSAGING_PROVIDER, not the WhatsApp provider")

    def send_template(
        self,
        mobile: str,
        template_name: str,
        params: dict[str, Any],
        language: str = "en",
    ) -> str | None:
        template_id = self._template_ids.get(template_name)
        if not template_id:
            raise MessagingError(f"No MSG91 template id configured for {template_name}")
        payload = {
            "integrated_number": self._integrated_number,
            "content_id": template_id,
            "payload_type": "node",
            "mobiles": f"91{mobile}" if not mobile.startswith("91") else mobile,
            "variables": ordered_template_params(template_name, params),
        }
        try:
            response = httpx.post(
                self._ENDPOINT,
                json=payload,
                headers={"authkey": self._auth_key, "Content-Type": "application/json"},
                timeout=15.0,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error(
                "whatsapp_delivery_failed",
                extra={"mobile": mask_mobile(mobile), "template": template_name, "error": str(exc)},
            )
            raise MessagingError("The WhatsApp provider rejected the message.") from exc
        # MSG91 returns {status: "success", request_id: "..."}.
        request_id = body.get("request_id") if isinstance(body, dict) else None
        if request_id:
            return str(request_id)
        raise MessagingError(f"Unexpected WhatsApp provider response: {body!r}")


class MetaWhatsAppProvider:
    """Template delivery via the Meta WhatsApp Cloud API."""

    _LANGUAGE_CODES: ClassVar[dict[str, str]] = {
        "en": "en_US",
        "ta": "ta",
        "hi": "hi",
        "te": "te",
        "kn": "kn",
        "ml": "ml",
    }

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        api_version: str = "v22.0",
    ) -> None:
        if not phone_number_id or not access_token:
            raise MessagingError(
                "META_WHATSAPP_PHONE_NUMBER_ID and META_WHATSAPP_ACCESS_TOKEN "
                "are required when WHATSAPP_PROVIDER=meta"
            )
        self._endpoint = (
            f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        )
        self._access_token = access_token

    def send_otp(self, mobile: str, code: str) -> None:  # pragma: no cover
        raise MessagingError("OTP SMS uses MESSAGING_PROVIDER, not the WhatsApp provider")

    def send_template(
        self,
        mobile: str,
        template_name: str,
        params: dict[str, Any],
        language: str = "en",
    ) -> str | None:
        template = get_template(template_name)
        unknown_template_params(template_name, params)
        missing = set(template.variables) - set(params)
        if missing:
            raise MessagingError(
                f"Template {template_name} is missing variables: {sorted(missing)}"
            )
        phone = "".join(character for character in mobile if character.isdigit())
        if len(phone) == 10:
            phone = f"91{phone}"
        if len(phone) != 12 or not phone.startswith("91"):
            raise MessagingError("WhatsApp mobile number must be a valid Indian number")

        language_code = self._LANGUAGE_CODES.get(language, self._LANGUAGE_CODES["en"])
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": str(params[name])}
                            for name in template.variables
                        ],
                    }
                ],
            },
        }
        try:
            response = httpx.post(
                self._endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=15.0,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error(
                "whatsapp_delivery_failed",
                extra={
                    "mobile": mask_mobile(mobile),
                    "template": template_name,
                    "provider": "meta",
                    "error_type": type(exc).__name__,
                },
            )
            raise MessagingError("The WhatsApp provider rejected the message.") from exc

        messages = body.get("messages") if isinstance(body, dict) else None
        if isinstance(messages, list) and messages and isinstance(messages[0], dict):
            message_id = messages[0].get("id")
            if message_id:
                return str(message_id)
        raise MessagingError("Meta returned an unexpected WhatsApp response.")


class LogOtpProvider:
    """Development provider. Prints the OTP to the server console only."""

    def send_otp(self, mobile: str, code: str) -> None:
        # Deliberate dev-only print. This is the single place an OTP is ever
        # written in plaintext, and it is unreachable when APP_ENV=production.
        settings = get_settings()
        if settings.is_production:
            raise MessagingError(
                "The log messaging provider is disabled in production. "
                "Set MESSAGING_PROVIDER=msg91."
            )
        print(f"[DEV OTP] {mask_mobile(mobile)} -> {code}", flush=True)
        logger.info("otp_logged", extra={"mobile": mask_mobile(mobile)})

    def send_template(
        self,
        mobile: str,
        template_name: str,
        params: dict[str, Any],
        language: str = "en",
    ) -> str | None:
        logger.info(
            "message_logged",
            extra={
                "mobile": mask_mobile(mobile),
                "template": template_name,
                "param_count": len(params),
            },
        )
        return None


class Msg91OtpProvider:
    """MSG91 transactional SMS.

    Requires DLT registration (sender id + template) before it can deliver in
    India. See the README deployment prerequisites.
    """

    _ENDPOINT = "https://control.msg91.com/api/v5/otp"

    def __init__(self, auth_key: str, template_id: str, sender_id: str | None = None) -> None:
        if not auth_key or not template_id:
            raise MessagingError(
                "MSG91_AUTH_KEY and MSG91_OTP_TEMPLATE_ID are required "
                "when MESSAGING_PROVIDER=msg91"
            )
        self._auth_key = auth_key
        self._template_id = template_id
        self._sender_id = sender_id

    def send_otp(self, mobile: str, code: str) -> None:
        payload: dict[str, Any] = {
            "template_id": self._template_id,
            "mobile": f"91{mobile}" if not mobile.startswith("91") else mobile,
            "otp": code,
            "otp_expiry": get_settings().otp_ttl_minutes,
        }
        if self._sender_id:
            payload["sender"] = self._sender_id

        try:
            response = httpx.post(
                self._ENDPOINT,
                json=payload,
                headers={"authkey": self._auth_key, "Content-Type": "application/json"},
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(
                "otp_delivery_failed",
                extra={"mobile": mask_mobile(mobile), "error": str(exc)},
            )
            raise MessagingError("Could not send the OTP SMS. Please try again.") from exc

        # MSG91 answers 200 OK even when it rejects the request: a bad template,
        # an unapproved DLT sender or an empty wallet all come back as
        # {"type": "error", "message": "..."}. Never treat the status code alone
        # as delivery, or the failure is silent for the user and invisible in
        # the logs.
        try:
            body: Any = response.json()
        except ValueError:
            body = None

        if not isinstance(body, dict):
            logger.error(
                "otp_delivery_failed",
                extra={
                    "mobile": mask_mobile(mobile),
                    "provider_message": response.text[:300],
                    "reason": "unparseable_response",
                },
            )
            raise MessagingError("Could not send the OTP SMS. Please try again.")

        provider_message = str(body.get("message", ""))
        if str(body.get("type", "")).lower() == "error":
            logger.error(
                "otp_delivery_failed",
                extra={"mobile": mask_mobile(mobile), "provider_message": provider_message},
            )
            raise MessagingError(
                f"The SMS provider rejected the request: {provider_message or 'unknown error'}"
            )

        # Delivered to the operator (not the handset). ``request_id`` is what the
        # MSG91 dashboard uses to show the delivery report and the DLT reason.
        logger.info(
            "otp_sent",
            extra={
                "mobile": mask_mobile(mobile),
                "provider_message": provider_message,
                "request_id": body.get("request_id"),
            },
        )

    def send_template(
        self,
        mobile: str,
        template_name: str,
        params: dict[str, Any],
        language: str = "en",
    ) -> str | None:
        # OTP SMS provider; WhatsApp messages use the dedicated WhatsApp provider.
        raise NotImplementedError("Template messages use the WhatsApp provider")


class Msg91WidgetVerifier:
    """Verify a token minted by the MSG91 OTP Widget (DLT-free OTP path).

    In widget mode MSG91 generates, sends and verifies the code in the browser
    using its own DLT-registered sender and default template, which is why no
    DLT registration is required. The only server-side step is exchanging the
    widget's ``access-token`` for the identifier that was actually verified.

    Never trust a mobile number posted by the client: this call is the proof.
    """

    _ENDPOINT = "https://control.msg91.com/api/v5/widget/verifyAccessToken"

    def __init__(self, auth_key: str) -> None:
        if not auth_key:
            raise MessagingError(
                "MSG91_AUTH_KEY is required when MESSAGING_PROVIDER=msg91_widget"
            )
        self._auth_key = auth_key

    def verify(self, access_token: str) -> str:
        """Return the verified 10-digit Indian mobile number or raise."""
        try:
            response = httpx.post(
                self._ENDPOINT,
                json={"authkey": self._auth_key, "access-token": access_token},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(
                "otp_widget_verification_failed",
                extra={"error": str(exc), "reason": "transport"},
            )
            raise MessagingError(
                "We could not verify that code. Please request a new OTP."
            ) from exc

        try:
            body: Any = response.json()
        except ValueError:
            body = None

        # MSG91 answers 200 with {"type": "error"} for an expired, reused or
        # forged token. The status code is never enough.
        if not isinstance(body, dict) or str(body.get("type", "")).lower() != "success":
            message = body.get("message") if isinstance(body, dict) else None
            logger.error(
                "otp_widget_verification_failed",
                extra={"provider_message": message, "reason": "rejected"},
            )
            raise MessagingError(
                "We could not verify that code. Please request a new OTP."
            )

        identifier = str(body.get("message", "")).strip()
        if "@" in identifier:
            # The widget also supports email; SchemePing accounts are mobile-only.
            raise MessagingError("This account must be verified with a mobile number.")

        mobile = normalise_mobile(identifier)
        if not is_valid_mobile(mobile):
            logger.error(
                "otp_widget_verification_failed",
                extra={"reason": "unexpected_identifier"},
            )
            raise MessagingError(
                "We could not verify that code. Please request a new OTP."
            )

        logger.info("otp_widget_verified", extra={"mobile": mask_mobile(mobile)})
        return mobile


def _whatsapp_template_ids(raw: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for chunk in raw.split(","):
        if ":" in chunk:
            name, provider_id = chunk.split(":", 1)
            if name.strip() and provider_id.strip():
                mapping[name.strip()] = provider_id.strip()
    return mapping


def whatsapp_delivery_configured() -> bool:
    """True only when a real WhatsApp provider has every credential it needs.

    The mock and log providers accept messages without delivering them, so the
    app must not offer server-side queueing as if a message would arrive. The
    frontend uses this to fall back to the free ``wa.me`` click-to-chat link.
    """
    settings = get_settings()
    if settings.whatsapp_provider == "meta":
        return bool(
            settings.meta_whatsapp_phone_number_id
            and settings.meta_whatsapp_access_token
        )
    if settings.whatsapp_provider == "msg91":
        return bool(
            settings.msg91_auth_key
            and settings.msg91_whatsapp_number
            and _whatsapp_template_ids(settings.msg91_whatsapp_template_ids)
        )
    return False


def get_whatsapp_provider() -> MessagingProvider:
    """Factory for the WhatsApp channel (Phase 5).

    ``mock`` (default) records sends without a network; ``log`` prints to the
    console; ``meta`` uses the WhatsApp Cloud API and approved templates.
    """
    settings = get_settings()
    provider = settings.whatsapp_provider
    if provider == "msg91":
        return Msg91WhatsAppProvider(
            auth_key=settings.msg91_auth_key,
            integrated_number=settings.msg91_whatsapp_number,
            template_ids=_whatsapp_template_ids(settings.msg91_whatsapp_template_ids),
        )
    if provider == "meta":
        return MetaWhatsAppProvider(
            phone_number_id=settings.meta_whatsapp_phone_number_id,
            access_token=settings.meta_whatsapp_access_token,
            api_version=settings.meta_whatsapp_api_version,
        )
    if provider == "log":
        return LogWhatsAppProvider()
    if provider == "mock":
        return MockWhatsAppProvider()
    raise MessagingError(f"Unknown WHATSAPP_PROVIDER: {provider}")


def get_messaging_provider() -> MessagingProvider:
    settings = get_settings()
    if settings.messaging_provider == "msg91":
        return Msg91OtpProvider(
            auth_key=settings.msg91_auth_key,
            template_id=settings.msg91_otp_template_id,
            sender_id=settings.msg91_sender_id or None,
        )
    return LogOtpProvider()
