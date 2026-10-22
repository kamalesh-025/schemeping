"""SQLAdmin panel mounted inside FastAPI (Phase 6 Part B).

Authentication is the staff login from ``app.services.admin_auth``: username
+ password + TOTP 2FA. It is completely separate from the citizen OTP
login, and it shares the same ``admin_users`` table and the same audit
trail: every model change through this panel is written to
``admin_audit_logs`` by :class:`AuditedModelView`.

Model views are deliberately narrow: staff can browse and edit schemes,
facilities and translations. Publishing stays in the API
(``POST /api/v1/admin-panel/schemes/{id}/publish``) because it has side
effects - recompute, translation invalidation - that a raw table editor
must not trigger.
"""

from __future__ import annotations

from typing import Any, ClassVar

from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.admin import AdminUser
from app.models.audit import AdminAuditLog
from app.models.facility import Facility
from app.models.scheme import Scheme, SchemeTranslation
from app.models.user import User
from app.services import admin_auth

logger = get_logger(__name__)


class AdminAuthentication(AuthenticationBackend):
    """Session login with password + TOTP, driven by ``admin_users``."""

    async def login(self, request: Request) -> bool:
        from app.core.db import SessionLocal

        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        totp = str(form.get("totp", ""))
        if not username or not password or not totp:
            return False

        with SessionLocal() as session:
            admin = session.query(AdminUser).filter_by(username=username).first()
            if admin is None or not admin.is_active:
                return False
            if not admin_auth.verify_password(password, admin.password_hash):
                return False
            if not admin_auth.verify_totp(admin.totp_secret, totp):
                return False
            role = admin.role

        request.session.update({"admin_username": username, "admin_role": role})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> Response | bool:
        if request.session.get("admin_username"):
            return True
        return RedirectResponse(request.url_for("admin:login"), status_code=302)


class AuditedModelView(ModelView):
    """A model view that writes an audit row for every change."""

    audit_entity: str = "record"

    async def on_model_change(
        self, data: dict[str, Any], model: Any, is_created: bool, request: Request
    ) -> None:
        await super().on_model_change(data, model, is_created, request)
        admin_username = request.session.get("admin_username", "unknown")
        entity_id = getattr(model, "id", None)
        from app.core.db import SessionLocal

        with SessionLocal() as session:
            session.add(
                AdminAuditLog(
                    admin_id=str(admin_username),
                    action="create" if is_created else "update",
                    entity=self.audit_entity,
                    entity_id=entity_id if isinstance(entity_id, int) else None,
                    diff={
                        "changed": {
                            key: value
                            for key, value in data.items()
                            if key not in ("password_hash", "totp_secret")
                        }
                    },
                    ip_address=request.client.host if request.client else None,
                )
            )
            session.commit()
        logger.info(
            "admin_panel_change",
            extra={
                "admin_id": admin_username,
                "entity": self.audit_entity,
                "entity_id": entity_id,
                "created": is_created,
            },
        )


class SchemeAdminView(AuditedModelView, model=Scheme):
    name = "Scheme"
    name_plural = "Schemes"
    audit_entity = "scheme"
    column_list: ClassVar[list[Any]] = [
        Scheme.id,
        Scheme.name,
        Scheme.department,
        Scheme.state,
        Scheme.category,
        Scheme.status,
        Scheme.last_verified_on,
    ]
    form_excluded_columns: ClassVar[list[Any]] = [Scheme.status]


class FacilityAdminView(AuditedModelView, model=Facility):
    name = "Facility"
    name_plural = "Facilities"
    audit_entity = "facility"
    column_list: ClassVar[list[Any]] = [
        Facility.id,
        Facility.name,
        Facility.type,
        Facility.district,
        Facility.state,
    ]
    form_excluded_columns: ClassVar[list[Any]] = [Facility.location]


class TranslationAdminView(AuditedModelView, model=SchemeTranslation):
    name = "Translation"
    name_plural = "Translations"
    audit_entity = "scheme_translation"
    column_list: ClassVar[list[Any]] = [
        SchemeTranslation.id,
        SchemeTranslation.scheme_id,
        SchemeTranslation.language,
        SchemeTranslation.source_hash,
    ]


class UserAdminView(AuditedModelView, model=User):
    name = "User"
    name_plural = "Users"
    audit_entity = "user"
    # Personal data is never shown in the panel beyond what is needed.
    column_list: ClassVar[list[Any]] = [
        User.id,
        User.name,
        User.state,
        User.district,
        User.created_at,
    ]
    form_excluded_columns: ClassVar[list[Any]] = [
        User.dob,
        User.gender,
        User.annual_income,
        User.is_disabled,
        User.notification_prefs,
        # A hash must never be typed or copied in a form. Password resets go
        # through `python -m app.scripts.reset_password <mobile>`.
        User.password_hash,
    ]
    can_create = False
    can_delete = False


def mount_admin(app: Any) -> Admin | None:
    """Mount SQLAdmin on ``/admin``; returns None when the DB is unreachable."""
    settings = get_settings()
    try:
        from pathlib import Path

        from app.core.db import engine

        admin = Admin(
            app,
            engine=engine,
            base_url="/admin",
            title="SchemePing Admin",
            authentication_backend=AdminAuthentication(secret_key=settings.secret_key),
            # Custom login form with the 2FA field.
            templates_dir=str(Path(__file__).parent / "admin_templates"),
        )
        admin.add_view(SchemeAdminView)
        admin.add_view(FacilityAdminView)
        admin.add_view(TranslationAdminView)
        admin.add_view(UserAdminView)
        logger.info("admin_panel_mounted", extra={"base_url": "/admin"})
        return admin
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("admin_panel_mount_failed", extra={"error": repr(exc)})
        return None


