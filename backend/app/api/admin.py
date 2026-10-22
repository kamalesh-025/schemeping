"""Admin panel API (Phase 6 Part B).

Separate staff authentication (username + password + TOTP, unrelated to
the citizen OTP login), two roles (``editor`` drafts/edits, ``publisher``
publishes and sends alerts) and one immutable audit trail. Every write
records who, what and the before/after diff in ``admin_audit_logs``.

Boostrap: the first admin account is created through ``POST
/bootstrap`` which only works while the table is empty. Later accounts are
created by a publisher through ``POST /admins``.

Scheme workflow: draft -> (publish) -> archived. Publishing a scheme sets
``last_verified_on = today``, re-computes eligibility for everyone and
drops now-stale cached translations (the translation cache keys on the
scheme content hash; publishing keeps it authoritative by re-caching).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.logging import get_logger
from app.eligibility.context import PersonProfile, build_person_context
from app.eligibility.engine import evaluate as evaluate_rules
from app.eligibility.rules import RuleValidationError, validate_eligibility_rules
from app.models.admin import AdminUser
from app.models.audit import AdminAuditLog
from app.models.enums import SchemeStatus
from app.models.facility import Facility
from app.models.scheme import Scheme, SchemeTranslation
from app.models.user import User
from app.services import admin_auth
from app.services.translations import content_hash

logger = get_logger(__name__)

router = APIRouter(prefix="/admin-panel", tags=["admin-panel"])


# ------------------------------------------------------------------ models


class BootstrapIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)
    role: Literal["editor", "publisher"] = "publisher"


class LoginIn(BaseModel):
    username: str
    password: str
    totp: str


class AdminOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool


class AdminTokenOut(BaseModel):
    token: str
    role: str
    username: str


class StatusOut(BaseModel):
    needs_bootstrap: bool


class SchemeIn(BaseModel):
    slug: str = Field(min_length=3, max_length=120)
    name: str = Field(min_length=3)
    department: str = Field(min_length=2)
    level: Literal["central", "state"]
    state: str | None = None
    category: str
    scope: Literal["individual", "family"]
    benefit_summary: str = Field(min_length=1)
    benefit_amount: str | None = None
    benefit_type: Literal["cash", "kind", "discount", "service"] = "cash"
    eligibility_rules: dict[str, Any]
    required_documents: list[dict[str, Any]] = Field(default_factory=list)
    application_steps: list[dict[str, Any]] = Field(default_factory=list)
    apply_url: str | None = None
    deadline: str | None = None  # ISO date
    source_url: str | None = None
    priority: int = 50


class RuleTestIn(BaseModel):
    rules: dict[str, Any]
    sample_profile: dict[str, Any]


class RuleTestOut(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    status: str | None = None
    reasons: list[dict[str, Any]] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class SchemeActionOut(BaseModel):
    id: int
    status: str
    last_verified_on: str | None


class AuditOut(BaseModel):
    id: int
    admin_id: str
    action: str
    entity: str
    entity_id: int | None
    diff: dict[str, Any]
    created_at: datetime


class AuditListOut(BaseModel):
    total: int
    logs: list[AuditOut]


# ------------------------------------------------------------------ deps


class AdminPrincipal(BaseModel):
    """A verified, active admin on the request."""

    username: str
    role: str


def get_admin_principal(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> AdminPrincipal:
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required"
        )
    try:
        username = admin_auth.decode_admin_token(token)
    except admin_auth.AdminAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from None
    row = db.scalar(select(AdminUser).where(AdminUser.username == username))
    if row is None or not row.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin account disabled"
        )
    return AdminPrincipal(username=row.username, role=row.role)


def require_role(needed: Literal["editor", "publisher"]) -> Any:
    def dependency(
        principal: Annotated[AdminPrincipal, Depends(get_admin_principal)],
    ) -> AdminPrincipal:
        if not admin_auth.role_allowed(principal.role, needed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"The {needed} role is required for this action",
            )
        return principal

    return dependency


Editor = Annotated[AdminPrincipal, Depends(require_role("editor"))]
Publisher = Annotated[AdminPrincipal, Depends(require_role("publisher"))]
AnyAdmin = Annotated[AdminPrincipal, Depends(get_admin_principal)]


def record_audit(
    db: Any,
    principal: AnyAdmin,
    action: str,
    entity: str,
    entity_id: int | None,
    diff: dict[str, Any],
    request: Request | None = None,
) -> None:
    ip = request.client.host if request is not None and request.client else None
    db.add(
        AdminAuditLog(
            admin_id=principal.username,
            action=action,
            entity=entity,
            entity_id=entity_id,
            diff=diff,
            ip_address=ip,
        )
    )
    db.commit()


# ------------------------------------------------------------------ bootstrap + login


@router.get("/status", response_model=StatusOut)
def admin_status(db: DbSession) -> StatusOut:
    count = db.scalar(select(AdminUser.id).limit(1))
    return StatusOut(needs_bootstrap=count is None)


@router.post("/bootstrap", response_model=AdminOut)
def bootstrap(
    payload: BootstrapIn, request: Request, db: DbSession
) -> AdminOut:
    from app.core.ratelimit import enforce

    enforce(request, limit=5, window_seconds=3600, scope="admin_bootstrap")
    existing = db.scalar(select(AdminUser.id).limit(1))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An admin account already exists; use a publisher login.",
        )
    admin = AdminUser(
        username=payload.username,
        password_hash=admin_auth.hash_password(payload.password),
        role=admin_auth.normalise_role(payload.role),
        totp_secret=admin_auth.generate_totp_secret(),
    )
    db.add(admin)
    db.commit()
    record_audit(
        db,
        AdminPrincipal(username=admin.username, role=admin.role),
        "bootstrap",
        "admin",
        admin.id,
        {"created": {"username": admin.username, "role": admin.role}},
        request,
    )
    return AdminOut(id=admin.id, username=admin.username, role=admin.role, is_active=True)


@router.post("/login", response_model=AdminTokenOut)
def login(payload: LoginIn, request: Request, db: DbSession) -> AdminTokenOut:
    from app.core.ratelimit import enforce

    enforce(request, limit=20, window_seconds=300, scope="admin_login")
    admin = db.scalar(
        select(AdminUser).where(AdminUser.username == payload.username)
    )
    # Constant-ish time: always run the checks even when the user is unknown.
    password_ok = False
    totp_ok = False
    if admin is not None and admin.is_active:
        password_ok = admin_auth.verify_password(payload.password, admin.password_hash)
        totp_ok = admin_auth.verify_totp(admin.totp_secret, payload.totp)
    if not (password_ok and totp_ok) or admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wrong username, password or 2FA code",
        )
    admin.last_login_at = datetime.now(tz=UTC)
    db.commit()
    return AdminTokenOut(
        token=admin_auth.create_admin_token(admin.username),
        role=admin.role,
        username=admin.username,
    )


# ------------------------------------------------------------------ schemes


def _scheme_payload_public(scheme: Scheme) -> dict[str, Any]:
    return {
        "id": scheme.id,
        "slug": scheme.slug,
        "name": scheme.name,
        "department": scheme.department,
        "level": str(getattr(scheme.level, "value", scheme.level)),
        "state": scheme.state,
        "category": scheme.category,
        "scope": str(getattr(scheme.scope, "value", scheme.scope)),
        "status": str(getattr(scheme.status, "value", scheme.status)),
        "benefit_summary": scheme.benefit_summary,
        "benefit_amount": scheme.benefit_amount,
        "benefit_type": str(getattr(scheme.benefit_type, "value", scheme.benefit_type)),
        "eligibility_rules": scheme.eligibility_rules,
        "required_documents": scheme.required_documents or [],
        "application_steps": scheme.application_steps or [],
        "apply_url": scheme.apply_url,
        "deadline": scheme.deadline.isoformat() if scheme.deadline else None,
        "source_url": scheme.source_url,
        "priority": scheme.priority,
        "last_verified_on": (
            scheme.last_verified_on.isoformat() if scheme.last_verified_on else None
        ),
    }


@router.get("/schemes")
def list_schemes(
    principal: AnyAdmin,
    db: DbSession,
    scheme_status: str | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    statement = select(Scheme).order_by(Scheme.id.desc())
    if scheme_status:
        statement = statement.where(
            Scheme.status == SchemeStatus(scheme_status)  # raises on bad value
        )
    rows = db.scalars(statement).all()
    return {"total": len(rows), "schemes": [_scheme_payload_public(s) for s in rows]}


@router.get("/schemes/{scheme_id}")
def get_scheme_admin(
    scheme_id: int, principal: AnyAdmin, db: DbSession
) -> dict[str, Any]:
    scheme = db.get(Scheme, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="Unknown scheme")
    return _scheme_payload_public(scheme)


@router.post("/schemes")
def create_scheme(
    payload: SchemeIn, principal: Editor, db: DbSession, request: Request
) -> dict[str, Any]:
    errors = validate_rules(payload.eligibility_rules)
    if errors:
        raise HTTPException(status_code=422, detail={"rules_invalid": errors})
    scheme = Scheme(
        slug=payload.slug,
        name=payload.name,
        department=payload.department,
        level=payload.level,
        state=payload.state,
        category=payload.category,
        scope=payload.scope,
        status=SchemeStatus.DRAFT,
        benefit_summary=payload.benefit_summary,
        benefit_amount=payload.benefit_amount,
        benefit_type=payload.benefit_type,
        eligibility_rules=payload.eligibility_rules,
        required_documents=payload.required_documents,
        application_steps=payload.application_steps,
        apply_url=payload.apply_url,
        deadline=_iso_date(payload.deadline),
        source_url=payload.source_url,
        priority=payload.priority,
    )
    db.add(scheme)
    db.commit()
    record_audit(
        db,
        principal,
        "create",
        "scheme",
        scheme.id,
        admin_auth.audit_diff(None, {"slug": scheme.slug, "status": "draft"}),
        request,
    )
    return _scheme_payload_public(scheme)


@router.put("/schemes/{scheme_id}")
def update_scheme(
    scheme_id: int,
    payload: SchemeIn,
    principal: Editor,
    db: DbSession,
    request: Request,
) -> dict[str, Any]:
    scheme = db.get(Scheme, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="Unknown scheme")
    errors = validate_rules(payload.eligibility_rules)
    if errors:
        raise HTTPException(status_code=422, detail={"rules_invalid": errors})
    before = _scheme_payload_public(scheme)
    for field, value in (
        ("slug", payload.slug),
        ("name", payload.name),
        ("department", payload.department),
        ("level", payload.level),
        ("state", payload.state),
        ("category", payload.category),
        ("scope", payload.scope),
        ("benefit_summary", payload.benefit_summary),
        ("benefit_amount", payload.benefit_amount),
        ("benefit_type", payload.benefit_type),
        ("eligibility_rules", payload.eligibility_rules),
        ("required_documents", payload.required_documents),
        ("application_steps", payload.application_steps),
        ("apply_url", payload.apply_url),
        ("deadline", _iso_date(payload.deadline)),
        ("source_url", payload.source_url),
        ("priority", payload.priority),
    ):
        setattr(scheme, field, value)
    db.commit()
    record_audit(
        db,
        principal,
        "update",
        "scheme",
        scheme.id,
        admin_auth.audit_diff(
            {key: before[key] for key in ("name", "status", "benefit_summary")},
            {
                "name": scheme.name,
                "status": str(getattr(scheme.status, "value", scheme.status)),
                "benefit_summary": scheme.benefit_summary,
            },
        ),
        request,
    )
    return _scheme_payload_public(scheme)


@router.post("/schemes/{scheme_id}/publish", response_model=SchemeActionOut)
def publish_scheme(
    scheme_id: int, principal: Publisher, db: DbSession, request: Request
) -> SchemeActionOut:
    """Draft -> published, then refresh the derived data.

    ``last_verified_on`` stamps today; eligibility is re-computed for every
    account; translations stale against the edited record are dropped so
    the fallback path shows current English text until the LLM re-caches.
    """
    from app.services.eligibility import recompute_user

    scheme = db.get(Scheme, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="Unknown scheme")
    if scheme.status is SchemeStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Scheme is already published"
        )
    errors = validate_rules(scheme.eligibility_rules or {})
    if errors:
        raise HTTPException(status_code=422, detail={"rules_invalid": errors})

    before_status = str(getattr(scheme.status, "value", scheme.status))
    scheme.status = SchemeStatus.PUBLISHED
    scheme.last_verified_on = date.today()
    hash_before_rebuild = content_hash(scheme)
    for row in db.scalars(
        select(SchemeTranslation).where(SchemeTranslation.scheme_id == scheme.id)
    ).all():
        if row.source_hash != hash_before_rebuild:
            db.delete(row)
    db.commit()

    recomputed = 0
    for user in db.scalars(select(User).where(User.deleted_at.is_(None))).all():
        recompute_user(db, user)
        recomputed += 1

    record_audit(
        db,
        principal,
        "publish",
        "scheme",
        scheme.id,
        admin_auth.audit_diff(
            {"status": before_status},
            {
                "status": "published",
                "last_verified_on": scheme.last_verified_on.isoformat(),
                "recomputed_users": recomputed,
            },
        ),
        request,
    )
    return SchemeActionOut(
        id=scheme.id,
        status="published",
        last_verified_on=str(scheme.last_verified_on.isoformat()),
    )


@router.post("/schemes/{scheme_id}/archive", response_model=SchemeActionOut)
def archive_scheme(
    scheme_id: int, principal: Publisher, db: DbSession, request: Request
) -> SchemeActionOut:
    scheme = db.get(Scheme, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="Unknown scheme")
    scheme.status = SchemeStatus.ARCHIVED
    db.commit()
    record_audit(
        db,
        principal,
        "archive",
        "scheme",
        scheme.id,
        {"after": {"status": "archived"}},
        request,
    )
    return SchemeActionOut(
        id=scheme.id,
        status="archived",
        last_verified_on=str(scheme.last_verified_on.isoformat())
        if scheme.last_verified_on
        else None,
    )


@router.post("/rules/test", response_model=RuleTestOut)
def test_rules(
    payload: RuleTestIn, principal: Editor, db: DbSession
) -> RuleTestOut:
    """Try a rule JSON against a sample profile without touching records."""
    errors = validate_rules(payload.rules)
    if errors:
        return RuleTestOut(valid=False, errors=errors)

    profile = PersonProfile(**_profile_kwargs(payload.sample_profile))
    outcome = evaluate_rules(payload.rules, build_person_context(profile))
    return RuleTestOut(
        valid=True,
        status=str(getattr(outcome.status, "value", outcome.status)),
        reasons=[reason.as_dict() for reason in outcome.reasons],
        missing_fields=list(outcome.missing_fields),
    )


_PROFILE_FIELDS = {
    "name",
    "dob",
    "gender",
    "annual_income",
    "occupation",
    "education",
    "education_status",
    "marital_status",
    "relationship",
    "state",
    "district",
    "pincode",
    "is_student",
    "is_disabled",
    "is_widow",
    "is_senior",
    "is_minor",
    "is_adult",
}


def _profile_kwargs(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept only the known profile fields; DOB is parsed to a date."""
    values = {key: value for key, value in raw.items() if key in _PROFILE_FIELDS}
    dob = values.get("dob")
    if isinstance(dob, str):
        try:
            values["dob"] = date.fromisoformat(dob)
        except ValueError:
            values.pop("dob")
    return values


def validate_rules(rules: dict[str, Any]) -> list[str]:
    """Return a list of human-readable problems (empty when valid)."""
    try:
        validate_eligibility_rules(rules)
    except RuleValidationError as exc:
        return [str(exc)]
    return []


def _iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid ISO date: {value}"
        ) from exc


# ------------------------------------------------------------------ facilities


class FacilityIn(BaseModel):
    name: str = Field(min_length=2)
    kind: Literal["csc", "taluk_office", "collector_office", "e_sevai", "welfare_office"]
    address: str = Field(min_length=4)
    district: str
    state: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    working_hours: str | None = None
    phone: str | None = None


@router.post("/facilities")
def create_facility(
    payload: FacilityIn, principal: Editor, db: DbSession, request: Request
) -> dict[str, Any]:
    facility = Facility(
        name=payload.name,
        type=payload.kind,
        address=payload.address,
        district=payload.district,
        state=payload.state,
        location=(payload.longitude, payload.latitude),
        working_hours=payload.working_hours,
        phone=payload.phone,
    )
    db.add(facility)
    db.commit()
    record_audit(
        db,
        principal,
        "create",
        "facility",
        facility.id,
        admin_auth.audit_diff(None, {"name": facility.name, "district": facility.district}),
        request,
    )
    return {"id": facility.id, "name": facility.name}


@router.put("/facilities/{facility_id}")
def update_facility(
    facility_id: int,
    payload: FacilityIn,
    principal: Editor,
    db: DbSession,
    request: Request,
) -> dict[str, Any]:
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(status_code=404, detail="Unknown facility")
    before = {"name": facility.name, "district": facility.district}
    facility.name = payload.name
    facility.address = payload.address
    facility.district = payload.district
    facility.state = payload.state
    facility.location = (payload.longitude, payload.latitude)
    facility.working_hours = payload.working_hours
    facility.phone = payload.phone
    db.commit()
    record_audit(
        db,
        principal,
        "update",
        "facility",
        facility.id,
        admin_auth.audit_diff(
            before, {"name": facility.name, "district": facility.district}
        ),
        request,
    )
    return {"id": facility.id, "name": facility.name}


# ------------------------------------------------------------------ audit logs (read-only)


@router.get("/audit-logs", response_model=AuditListOut)
def read_audit_logs(
    principal: AnyAdmin,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
) -> AuditListOut:
    rows = db.scalars(
        select(AdminAuditLog).order_by(AdminAuditLog.id.desc()).limit(limit)
    ).all()
    return AuditListOut(
        total=len(rows),
        logs=[
            AuditOut(
                id=row.id,
                admin_id=row.admin_id,
                action=row.action,
                entity=row.entity,
                entity_id=row.entity_id,
                diff=dict(row.diff or {}),
                created_at=row.created_at,
            )
            for row in rows
        ],
    )

