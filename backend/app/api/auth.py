"""Authentication routes: password sign-up/sign-in, OTP sign-in, refresh, logout."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, clear_session_cookies, set_session_cookies
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.ratelimit import allow_key, enforce
from app.core.security import mask_mobile
from app.core.time import utcnow
from app.models.enums import Language
from app.models.user import User
from app.schemas.auth import (
    AuthConfigOut,
    LoginIn,
    OtpRequestIn,
    OtpRequestOut,
    OtpVerifyIn,
    OtpWidgetVerifyIn,
    PasswordChangeIn,
    RegisterIn,
    UserSessionOut,
)
from app.services import auth as auth_service
from app.services import otp as otp_service
from app.services.auth import (
    AccountExists,
    InvalidCredentials,
    SessionError,
    revoke_token,
    rotate_session,
    start_session,
)
from app.services.messaging import MessagingError, Msg91WidgetVerifier
from app.services.profile import is_profile_complete

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45] or None
    return request.client.host if request.client else None


def _session_payload(user: User) -> UserSessionOut:
    return UserSessionOut(
        id=user.id,
        name=user.name,
        mobile=user.mobile,
        language=user.language or Language.ENGLISH,
        profile_complete=is_profile_complete(user),
        has_consent=bool(user.consent_data_processing),
    )


def _require_password_mode() -> None:
    if get_settings().auth_mode != "password":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Password sign-in is not enabled on this deployment.",
        )


def _require_otp_mode() -> None:
    if get_settings().auth_mode != "otp":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="OTP sign-in is not enabled on this deployment.",
        )


def _require_server_otp() -> None:
    """Reject the backend-generated OTP flow when the widget owns verification."""
    _require_otp_mode()
    if get_settings().messaging_provider == "msg91_widget":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This deployment verifies OTPs in the app with MSG91. "
                "Reload the app to sign in."
            ),
        )


def _issue_session(
    db: Session, user: User, request: Request, response: Response
) -> UserSessionOut:
    """Start a session for a user whose identity has already been proven."""
    issued = start_session(
        db,
        user,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookies(
        response,
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
    )
    logger.info("user_logged_in", extra={"user_id": user.id})
    return _session_payload(user)


def _login_verified_mobile(
    db: Session, mobile: str, request: Request, response: Response
) -> UserSessionOut:
    """Find or create the account for an OTP-proven mobile number."""
    user = db.scalar(select(User).where(User.mobile == mobile))
    if user is None:
        # Registration and login are the same step in OTP mode: the account
        # exists as soon as the mobile number is proven.
        user = User(
            mobile=mobile,
            language=Language.ENGLISH,
            consent_data_processing=False,
            consent_whatsapp=False,
        )
        db.add(user)
        db.flush()

    user.mobile_verified_at = utcnow()
    return _issue_session(db, user, request, response)


@router.get(
    "/config",
    response_model=AuthConfigOut,
    summary="Which sign-in flow the client should render",
)
def auth_config() -> AuthConfigOut:
    settings = get_settings()
    if settings.auth_mode == "password":
        return AuthConfigOut(
            mode="password", password_min_length=settings.password_min_length
        )
    if settings.messaging_provider == "msg91_widget":
        return AuthConfigOut(
            mode="widget",
            password_min_length=settings.password_min_length,
            widget_id=settings.msg91_widget_id or None,
            widget_token=settings.msg91_widget_token or None,
        )
    return AuthConfigOut(mode="server", password_min_length=settings.password_min_length)


@router.post(
    "/register",
    response_model=UserSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account with a mobile number and a password",
)
def register(
    payload: RegisterIn, request: Request, response: Response, db: DbSession
) -> UserSessionOut:
    _require_password_mode()
    enforce(request, scope="auth_register", limit=20, window_seconds=3600)
    try:
        user = auth_service.register_user(
            db, mobile=payload.mobile, password=payload.password, name=payload.name
        )
    except AccountExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    logger.info("account_registered", extra={"mobile": mask_mobile(payload.mobile)})
    return _issue_session(db, user, request, response)


@router.post(
    "/login",
    response_model=UserSessionOut,
    summary="Sign in with a mobile number and password",
)
def login(
    payload: LoginIn, request: Request, response: Response, db: DbSession
) -> UserSessionOut:
    _require_password_mode()
    # Two budgets: one per caller (broad attacks) and one per number (targeted
    # guessing at a single account).
    enforce(request, scope="auth_login_ip", limit=30, window_seconds=900)
    if not allow_key(f"auth_login_mobile:{payload.mobile}", limit=10, window_seconds=900):
        logger.warning(
            "login_rate_limited", extra={"mobile": mask_mobile(payload.mobile)}
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts. Please try again in 15 minutes.",
        )

    try:
        user = auth_service.authenticate(
            db, mobile=payload.mobile, password=payload.password
        )
    except InvalidCredentials as exc:
        logger.warning("login_failed", extra={"mobile": mask_mobile(payload.mobile)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    return _issue_session(db, user, request, response)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change the password of the signed-in account",
)
def change_password(
    payload: PasswordChangeIn,
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    _require_password_mode()
    try:
        auth_service.change_password(
            db, user, payload.current_password, payload.new_password
        )
    except InvalidCredentials as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    # A password change signs out every other device but keeps this one.
    settings = get_settings()
    auth_service.revoke_other_sessions(
        db, user.id, request.cookies.get(settings.refresh_cookie_name)
    )
    db.commit()
    logger.info("password_changed", extra={"user_id": user.id})
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/otp/request",
    response_model=OtpRequestOut,
    summary="Send a login OTP by SMS",
)
def request_otp(payload: OtpRequestIn, request: Request, db: DbSession) -> OtpRequestOut:
    _require_server_otp()
    try:
        result = otp_service.request_otp(db, payload.mobile, ip_address=_client_ip(request))
    except otp_service.OtpRateLimited as exc:
        # 429 with Retry-After so the client can show a real countdown.
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except MessagingError as exc:
        # The provider refused the send (bad template, DLT sender not approved,
        # empty wallet). Surface it instead of returning a false "sent".
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    logger.info(
        "otp_requested",
        extra={"mobile": mask_mobile(payload.mobile), "ip": _client_ip(request)},
    )
    return OtpRequestOut(
        message=otp_service.SMS_SENT_MESSAGE,
        expires_in_seconds=result.expires_in_seconds,
        resend_after_seconds=result.resend_after_seconds,
    )


@router.post(
    "/otp/verify",
    response_model=UserSessionOut,
    summary="Verify an OTP and start a session",
)
def verify_otp(
    payload: OtpVerifyIn, request: Request, response: Response, db: DbSession
) -> UserSessionOut:
    _require_server_otp()
    try:
        otp_service.verify_otp(db, payload.mobile, payload.otp)
    except otp_service.OtpLocked as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    except otp_service.OtpExpired as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    except otp_service.OtpInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return _login_verified_mobile(db, payload.mobile, request, response)


@router.post(
    "/otp/widget/verify",
    response_model=UserSessionOut,
    summary="Trade an MSG91 widget access token for a session",
)
def verify_widget_otp(
    payload: OtpWidgetVerifyIn, request: Request, response: Response, db: DbSession
) -> UserSessionOut:
    """Complete a widget sign-in.

    The browser never tells us who the user is: MSG91's ``access-token`` is
    exchanged server-side for the identifier it actually verified. That keeps
    the "OTP proves the number" rule intact even though MSG91 sent the code.
    """
    settings = get_settings()
    _require_otp_mode()
    if settings.messaging_provider != "msg91_widget":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="OTP widget sign-in is not enabled on this deployment.",
        )
    if not (
        settings.msg91_auth_key
        and settings.msg91_widget_id
        and settings.msg91_widget_token
    ):
        # Never fall back to the log provider here: that would print OTPs to the
        # server console in a deployment that asked for real SMS.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The OTP widget is not configured on this server.",
        )

    try:
        mobile = Msg91WidgetVerifier(settings.msg91_auth_key).verify(payload.access_token)
    except MessagingError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    return _login_verified_mobile(db, mobile, request, response)


@router.post(
    "/refresh",
    response_model=UserSessionOut,
    summary="Rotate the refresh token and issue a new access token",
)
def refresh(request: Request, response: Response, db: DbSession) -> UserSessionOut:
    settings = get_settings()
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in to continue."
        )

    try:
        rotated = rotate_session(
            db,
            token,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except SessionError as exc:
        clear_session_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    set_session_cookies(
        response,
        access_token=rotated.session.access_token,
        refresh_token=rotated.session.refresh_token,
    )
    return _session_payload(rotated.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="End the session")
def logout(request: Request, response: Response, db: DbSession) -> Response:
    settings = get_settings()
    revoke_token(db, request.cookies.get(settings.refresh_cookie_name))
    clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/session", response_model=UserSessionOut, summary="Who am I")
def current_session(user: CurrentUser) -> UserSessionOut:
    return _session_payload(user)
