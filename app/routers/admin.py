import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_current_admin_user
from app.models.pending_signup import PendingSignup, SignupStatus
from app.models.session import Session as SessionModel
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.services import email as email_service
from app.services.html_pages import confirmation_page
from app.services.security import generate_temp_password, hash_password

router = APIRouter(prefix="/api", tags=["admin"])


def _now():
    return datetime.now(timezone.utc)


def _approve_pending_signup(pending: PendingSignup, db: DBSession) -> str:
    """Shared by the email-link flow and the admin-dashboard flow — one
    place that actually creates the account, so the two paths can't drift
    into different behavior over time."""
    temp_password = generate_temp_password()
    user = User(
        username=pending.username, display_name=pending.display_name, email=pending.email,
        email_verified=True, password_hash=hash_password(temp_password), must_reset_password=True,
    )
    db.add(user)
    pending.status = SignupStatus.approved
    db.commit()
    email_service.send_welcome_email(
        to=pending.email, display_name=pending.display_name, username=pending.username, temp_password=temp_password
    )
    return pending.email


def _reject_pending_signup(pending: PendingSignup, db: DBSession):
    pending.status = SignupStatus.rejected
    db.commit()
    email_service.send_rejection_email(to=pending.email, display_name=pending.display_name)


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

    email = _approve_pending_signup(pending, db)
    return confirmation_page("Signup approved", f"A welcome email with login details has been sent to {email}.")


@router.get("/reject-signup")
def reject_signup(request_id: str, token: str, db: DBSession = Depends(get_db)):
    pending = _load_pending_approval(request_id, token, db)
    if not pending:
        return confirmation_page("Link invalid or expired", "This link is no longer valid.", status_code=400)

    _reject_pending_signup(pending, db)
    return confirmation_page("Request rejected", "The requester has been notified.")


# ==================================================================
# Admin dashboard — authenticated endpoints, no email token needed
# ==================================================================
@router.get("/admin/pending-signups")
def list_pending_signups(admin: User = Depends(get_current_admin_user), db: DBSession = Depends(get_db)):
    pending = db.query(PendingSignup).filter(PendingSignup.status == SignupStatus.pending_approval).order_by(PendingSignup.created_at.desc()).all()
    return [
        {"id": str(p.id), "username": p.username, "display_name": p.display_name, "email": p.email, "created_at": p.created_at.isoformat()}
        for p in pending
    ]


@router.post("/admin/pending-signups/{signup_id}/approve")
def admin_approve_signup(signup_id: uuid.UUID, admin: User = Depends(get_current_admin_user), db: DBSession = Depends(get_db)):
    pending = db.query(PendingSignup).filter(PendingSignup.id == signup_id, PendingSignup.status == SignupStatus.pending_approval).first()
    if not pending:
        raise HTTPException(status_code=404, detail="Pending signup not found")
    email = _approve_pending_signup(pending, db)
    return {"success": True, "message": f"Approved — welcome email sent to {email}."}


@router.post("/admin/pending-signups/{signup_id}/reject")
def admin_reject_signup(signup_id: uuid.UUID, admin: User = Depends(get_current_admin_user), db: DBSession = Depends(get_db)):
    pending = db.query(PendingSignup).filter(PendingSignup.id == signup_id, PendingSignup.status == SignupStatus.pending_approval).first()
    if not pending:
        raise HTTPException(status_code=404, detail="Pending signup not found")
    _reject_pending_signup(pending, db)
    return {"success": True}


@router.get("/admin/users")
def list_users(admin: User = Depends(get_current_admin_user), db: DBSession = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    result = []
    for u in users:
        last_log = (
            db.query(WorkoutLog.logged_at)
            .filter(WorkoutLog.user_id == u.id)
            .order_by(WorkoutLog.logged_at.desc())
            .first()
        )
        result.append({
            "id": str(u.id), "username": u.username, "display_name": u.display_name, "email": u.email,
            "created_at": u.created_at.isoformat(), "is_admin": u.is_admin, "is_disabled": u.is_disabled,
            "last_active": last_log[0].isoformat() if last_log else None,
        })
    return result


@router.get("/admin/users/{user_id}/summary")
def user_summary(user_id: uuid.UUID, admin: User = Depends(get_current_admin_user), db: DBSession = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    total_sets = db.query(WorkoutLog).filter(WorkoutLog.user_id == user_id, WorkoutLog.section == "Main").count()
    distinct_days = (
        db.query(WorkoutLog.workout_date)
        .filter(WorkoutLog.user_id == user_id)
        .distinct()
        .count()
    )
    last_log = (
        db.query(WorkoutLog.logged_at)
        .filter(WorkoutLog.user_id == user_id)
        .order_by(WorkoutLog.logged_at.desc())
        .first()
    )
    return {
        "username": target.username, "display_name": target.display_name,
        "total_main_sets_logged": total_sets, "distinct_days_trained": distinct_days,
        "last_active": last_log[0].isoformat() if last_log else None,
    }


@router.patch("/admin/users/{user_id}/disable")
def disable_user(user_id: uuid.UUID, admin: User = Depends(get_current_admin_user), db: DBSession = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="Can't disable your own account.")

    target.is_disabled = True
    # Kick out any session they're already using — disabling should take
    # effect immediately, not just block their next login attempt.
    db.query(SessionModel).filter(SessionModel.user_id == target.id, SessionModel.revoked.is_(False)).update({"revoked": True})
    db.commit()
    return {"success": True}


@router.patch("/admin/users/{user_id}/enable")
def enable_user(user_id: uuid.UUID, admin: User = Depends(get_current_admin_user), db: DBSession = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.is_disabled = False
    db.commit()
    return {"success": True}
