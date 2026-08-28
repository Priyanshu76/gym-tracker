import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models.pending_signup import PendingSignup, SignupStatus
from app.models.user import User
from app.services import email as email_service
from app.services.html_pages import confirmation_page
from app.services.security import generate_temp_password, hash_password

router = APIRouter(prefix="/api", tags=["admin"])


def _now():
    return datetime.now(timezone.utc)


def _load_pending_approval(request_id: str, token: str, db: DBSession) -> PendingSignup | None:
    try:
        pending = db.query(PendingSignup).filter(PendingSignup.id == uuid.UUID(request_id)).first()
    except ValueError:
        return None
    if not pending or pending.status != SignupStatus.pending_approval:
        return None
    if pending.approval_token != token:
        return None
    if not pending.approval_expires or pending.approval_expires.replace(tzinfo=timezone.utc) < _now():
        return None
    return pending


@router.get("/approve-signup")
def approve_signup(request_id: str, token: str, db: DBSession = Depends(get_db)):
    pending = _load_pending_approval(request_id, token, db)
    if not pending:
        return confirmation_page("Link invalid or expired", "This approval link is no longer valid.", status_code=400)

    temp_password = generate_temp_password()
    user = User(
        username=pending.username,
        display_name=pending.display_name,
        email=pending.email,
        email_verified=True,
        password_hash=hash_password(temp_password),
        must_reset_password=True,
    )
    db.add(user)

    pending.status = SignupStatus.approved
    db.commit()

    email_service.send_welcome_email(
        to=pending.email, display_name=pending.display_name, username=pending.username, temp_password=temp_password
    )

    return confirmation_page("Signup approved", f"A welcome email with login details has been sent to {pending.email}.")


@router.get("/reject-signup")
def reject_signup(request_id: str, token: str, db: DBSession = Depends(get_db)):
    pending = _load_pending_approval(request_id, token, db)
    if not pending:
        return confirmation_page("Link invalid or expired", "This link is no longer valid.", status_code=400)

    pending.status = SignupStatus.rejected
    db.commit()

    email_service.send_rejection_email(to=pending.email, display_name=pending.display_name)

    return confirmation_page("Request rejected", "The requester has been notified.")
