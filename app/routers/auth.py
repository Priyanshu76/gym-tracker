import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import COOKIE_NAME, get_current_user
from app.models.pending_signup import PendingSignup, SignupStatus
from app.models.session import Session as SessionModel
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    ResetPasswordRequest,
    SetNewPasswordRequest,
    SignupRequest,
)
from app.services import email as email_service
from app.services.html_pages import confirmation_page
from app.services.security import (
    create_access_token,
    generate_secure_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api", tags=["auth"])
settings = get_settings()

VERIFICATION_TTL = timedelta(hours=24)
APPROVAL_TTL = timedelta(days=7)
RESET_TTL = timedelta(hours=1)
SESSION_TTL_DAYS = 30


def _now():
    return datetime.now(timezone.utc)


@router.get("/me")
def get_me(user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    """
    Lets the frontend check "am I logged in, and as whom" purely by asking
    the server — no token to store or manage client-side at all, since the
    httpOnly cookie is sent automatically by the browser. A 401 here just
    means "show the login screen." has_profile drives the forced onboarding
    gate the same way must_reset_password drives the forced password reset.
    """
    from app.models.user_profile import UserProfile

    has_profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first() is not None
    return {
        "username": user.username,
        "display_name": user.display_name,
        "must_reset_password": user.must_reset_password,
        "has_profile": has_profile,
    }


# ============================================================
# Signup
# ============================================================
@router.post("/signup", response_model=MessageResponse)
def signup(payload: SignupRequest, db: DBSession = Depends(get_db)):
    generic_success = MessageResponse(
        success=True,
        message="Check your email to verify your address before your request can be reviewed.",
    )

    # Honeypot: real users never see or fill this field. Respond exactly like
    # a real success so bots can't distinguish detection from acceptance.
    if payload.website_url:
        return generic_success

    existing_user = db.query(User).filter(User.username == payload.username).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="That username is already taken.")

    existing_email_user = db.query(User).filter(User.email == payload.email).first()
    if existing_email_user:
        raise HTTPException(status_code=409, detail="That email is already registered.")

    # A signup that's already verified-and-awaiting-approval (or still awaiting
    # verification) for the same username/email shouldn't be allowed to start
    # a second, competing request — otherwise two people could race to grab
    # the same username before either one is actually approved.
    in_flight_statuses = (SignupStatus.pending_verification, SignupStatus.pending_approval)
    existing_pending_username = (
        db.query(PendingSignup)
        .filter(PendingSignup.username == payload.username, PendingSignup.status.in_(in_flight_statuses))
        .first()
    )
    if existing_pending_username:
        raise HTTPException(status_code=409, detail="That username already has a pending signup request.")

    existing_pending_email = (
        db.query(PendingSignup)
        .filter(PendingSignup.email == payload.email, PendingSignup.status.in_(in_flight_statuses))
        .first()
    )
    if existing_pending_email:
        raise HTTPException(status_code=409, detail="That email already has a pending signup request.")

    pending = PendingSignup(
        username=payload.username,
        display_name=payload.display_name,
        email=payload.email,
        status=SignupStatus.pending_verification,
        verification_token=generate_secure_token(),
        verification_expires=_now() + VERIFICATION_TTL,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)

    email_service.send_verification_email(
        to=pending.email,
        display_name=pending.display_name,
        request_id=str(pending.id),
        token=pending.verification_token,
    )

    return generic_success


@router.get("/verify-email")
def verify_email(request_id: str, token: str, db: DBSession = Depends(get_db)):
    try:
        pending = db.query(PendingSignup).filter(PendingSignup.id == uuid.UUID(request_id)).first()
    except ValueError:
        pending = None

    if not pending or pending.status != SignupStatus.pending_verification:
        return confirmation_page(
            "Link invalid or expired",
            "This verification link is no longer valid. Please sign up again.",
            status_code=400,
        )
    if pending.verification_token != token:
        return confirmation_page("Link invalid or expired", "This link is no longer valid.", status_code=400)
    if pending.verification_expires.replace(tzinfo=timezone.utc) < _now():
        return confirmation_page(
            "Link invalid or expired",
            "This verification link is no longer valid. Please sign up again.",
            status_code=400,
        )

    pending.status = SignupStatus.pending_approval
    pending.approval_token = generate_secure_token()
    pending.approval_expires = _now() + APPROVAL_TTL
    db.commit()

    email_service.send_admin_notification(
        username=pending.username,
        display_name=pending.display_name,
        email=pending.email,
        request_id=str(pending.id),
        approval_token=pending.approval_token,
    )

    return confirmation_page(
        "Email verified",
        "Your request has been sent to the site owner for approval. You'll get an email once it's reviewed.",
    )


# ============================================================
# Login / logout
# ============================================================
@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, db: DBSession = Depends(get_db)):
    invalid = HTTPException(status_code=401, detail="Invalid username or password")

    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise invalid

    jti = str(uuid.uuid4())
    expires_at = _now() + timedelta(days=SESSION_TTL_DAYS)
    session = SessionModel(user_id=user.id, token_jti=jti, expires_at=expires_at)
    db.add(session)
    db.commit()

    token = create_access_token(user.id, jti)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.is_production,  # HTTPS-only in prod; plain HTTP local dev needs this off or the cookie never comes back
        samesite="lax",
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        path="/",
    )

    return LoginResponse(success=True, display_name=user.display_name, must_reset_password=user.must_reset_password)


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    db.query(SessionModel).filter(SessionModel.user_id == user.id, SessionModel.revoked.is_(False)).update(
        {"revoked": True}
    )
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return MessageResponse(success=True, message="Logged out.")


# ============================================================
# Forgot / reset password
# ============================================================
@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordRequest, db: DBSession = Depends(get_db)):
    generic = MessageResponse(
        success=True,
        message="If that account exists, a reset link has been sent to its registered email.",
    )

    user = db.query(User).filter(User.username == payload.username).first()
    if not user:
        # Same response either way — don't reveal whether a username exists.
        return generic

    user.reset_token = generate_secure_token()
    user.reset_token_expires = _now() + RESET_TTL
    db.commit()

    email_service.send_reset_email(
        to=user.email, display_name=user.display_name, username=user.username, token=user.reset_token
    )
    return generic


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: DBSession = Depends(get_db)):
    invalid = HTTPException(
        status_code=400,
        detail="This reset link is invalid, expired, or the password is too short (min 8 characters).",
    )

    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not user.reset_token or user.reset_token != payload.token:
        raise invalid
    if not user.reset_token_expires or user.reset_token_expires.replace(tzinfo=timezone.utc) < _now():
        raise invalid

    user.password_hash = hash_password(payload.new_password)
    user.must_reset_password = False
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()

    # Now that we have a real DB, we can actually do the thing the n8n version
    # couldn't: invalidate every existing session the moment the password changes.
    db.query(SessionModel).filter(SessionModel.user_id == user.id, SessionModel.revoked.is_(False)).update(
        {"revoked": True}
    )
    db.commit()

    return MessageResponse(success=True, message="Password updated — you can log in now.")


@router.post("/set-new-password", response_model=MessageResponse)
def set_new_password(
    payload: SetNewPasswordRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    user.password_hash = hash_password(payload.new_password)
    user.must_reset_password = False
    db.commit()

    return MessageResponse(success=True, message="Password set — you can continue.")
