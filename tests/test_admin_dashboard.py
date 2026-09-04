from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine, SessionLocal
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _create_and_login(username: str, email: str) -> TestClient:
    client = TestClient(app)
    with patch("app.services.email.send_email"):
        from app.models.pending_signup import PendingSignup
        from app.models.user import User
        from app.services.security import hash_password
        client.post("/api/signup", json={"username": username, "display_name": username.title(), "email": email, "website_url": ""})
        db = SessionLocal()
        pending = db.query(PendingSignup).filter(PendingSignup.username == username).first()
        client.get(f"/api/verify-email?request_id={pending.id}&token={pending.verification_token}")
        db.refresh(pending)
        client.get(f"/api/approve-signup?request_id={pending.id}&token={pending.approval_token}")
        user = db.query(User).filter(User.username == username).first()
        user.password_hash = hash_password("KnownPass123!")
        db.commit()
        db.close()
    client.post("/api/login", json={"username": username, "password": "KnownPass123!"})
    return client


def _admin_client() -> TestClient:
    """Logging in with whatever email is actually configured as
    settings.admin_email should self-heal into is_admin=True on first
    admin action — read it dynamically rather than hardcoding a value,
    since ADMIN_EMAIL is set via environment variable and a mismatch here
    would silently test the wrong thing."""
    from app.config import get_settings
    admin_email = get_settings().admin_email
    return _create_and_login("theadmin", admin_email)


def _regular_client(username="regularuser") -> TestClient:
    return _create_and_login(username, f"{username}@example.com")


# ==================================================================
# Admin bootstrap and access control
# ==================================================================
def test_admin_email_self_heals_into_admin_on_first_use():
    client = _admin_client()
    r = client.get("/api/admin/users")
    assert r.status_code == 200

    from app.config import get_settings
    from app.database import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    admin_user = db.query(User).filter(User.email == get_settings().admin_email).first()
    assert admin_user.is_admin is True
    db.close()


def test_non_admin_user_gets_403():
    client = _regular_client()
    r = client.get("/api/admin/users")
    assert r.status_code == 403


def test_admin_endpoints_require_authentication():
    anon = TestClient(app)
    assert anon.get("/api/admin/users").status_code == 401
    assert anon.get("/api/admin/pending-signups").status_code == 401


# ==================================================================
# Pending signups
# ==================================================================
def test_admin_can_see_and_approve_pending_signup():
    admin = _admin_client()
    with patch("app.services.email.send_email"):
        from app.database import SessionLocal
        from app.models.pending_signup import PendingSignup
        anon = TestClient(app)
        anon.post("/api/signup", json={"username": "pendinguser", "display_name": "P", "email": "pending@example.com", "website_url": ""})
        db = SessionLocal()
        pending = db.query(PendingSignup).filter(PendingSignup.username == "pendinguser").first()
        anon.get(f"/api/verify-email?request_id={pending.id}&token={pending.verification_token}")
        db.close()

        listed = admin.get("/api/admin/pending-signups").json()
        assert any(p["username"] == "pendinguser" for p in listed)

        signup_id = next(p["id"] for p in listed if p["username"] == "pendinguser")
        r = admin.post(f"/api/admin/pending-signups/{signup_id}/approve")
        assert r.status_code == 200

    from app.database import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    assert db.query(User).filter(User.username == "pendinguser").count() == 1
    db.close()


def test_non_admin_cannot_approve_signups():
    regular = _regular_client()
    fake_id = "00000000-0000-0000-0000-000000000000"
    assert regular.post(f"/api/admin/pending-signups/{fake_id}/approve").status_code == 403


# ==================================================================
# User listing and disable/enable
# ==================================================================
def test_admin_can_list_users_with_last_active():
    admin = _admin_client()
    regular = _regular_client("listeduser")
    regular.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 100, "reps": 5,
    })

    users = admin.get("/api/admin/users").json()
    listed = next(u for u in users if u["username"] == "listeduser")
    assert listed["last_active"] is not None


def test_disable_user_blocks_login():
    admin = _admin_client()
    regular = _regular_client("disableduser")
    users = admin.get("/api/admin/users").json()
    target_id = next(u["id"] for u in users if u["username"] == "disableduser")

    r = admin.patch(f"/api/admin/users/{target_id}/disable")
    assert r.status_code == 200

    fresh = TestClient(app)
    login_r = fresh.post("/api/login", json={"username": "disableduser", "password": "KnownPass123!"})
    assert login_r.status_code == 403


def test_disable_user_kicks_out_existing_session():
    admin = _admin_client()
    regular = _regular_client("kickoutuser")
    assert regular.get("/api/me").status_code == 200

    users = admin.get("/api/admin/users").json()
    target_id = next(u["id"] for u in users if u["username"] == "kickoutuser")
    admin.patch(f"/api/admin/users/{target_id}/disable")

    assert regular.get("/api/me").status_code == 401


def test_enable_user_restores_login():
    admin = _admin_client()
    regular = _regular_client("reenableduser")
    users = admin.get("/api/admin/users").json()
    target_id = next(u["id"] for u in users if u["username"] == "reenableduser")
    admin.patch(f"/api/admin/users/{target_id}/disable")
    admin.patch(f"/api/admin/users/{target_id}/enable")

    fresh = TestClient(app)
    login_r = fresh.post("/api/login", json={"username": "reenableduser", "password": "KnownPass123!"})
    assert login_r.status_code == 200


def test_admin_cannot_disable_own_account():
    admin = _admin_client()
    users = admin.get("/api/admin/users").json()
    admin_id = next(u["id"] for u in users if u["username"] == "theadmin")

    r = admin.patch(f"/api/admin/users/{admin_id}/disable")
    assert r.status_code == 400


def test_non_admin_cannot_disable_users():
    regular = _regular_client()
    fake_id = "00000000-0000-0000-0000-000000000000"
    assert regular.patch(f"/api/admin/users/{fake_id}/disable").status_code == 403


# ==================================================================
# Per-user summary
# ==================================================================
def test_user_summary_shows_training_stats():
    admin = _admin_client()
    regular = _regular_client("summaryuser")
    regular.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 100, "reps": 5,
    })
    regular.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 2, "weight_kg": 100, "reps": 5,
    })

    users = admin.get("/api/admin/users").json()
    target_id = next(u["id"] for u in users if u["username"] == "summaryuser")
    summary = admin.get(f"/api/admin/users/{target_id}/summary").json()
    assert summary["total_main_sets_logged"] == 2
    assert summary["distinct_days_trained"] == 1


def test_me_reports_is_admin_true_for_admin_email_even_before_first_visit():
    """The nav-link-showing check in /api/me should recognize the admin
    email immediately, not only after the DB flag has been self-healed by
    an actual admin endpoint visit."""
    from app.config import get_settings
    admin_email = get_settings().admin_email
    client = _create_and_login("freshadmin", admin_email)
    me = client.get("/api/me").json()
    assert me["is_admin"] is True


def test_me_reports_is_admin_false_for_regular_user():
    client = _regular_client("notadminuser")
    me = client.get("/api/me").json()
    assert me["is_admin"] is False


def test_admin_page_renders():
    client = TestClient(app)
    r = client.get("/admin")
    assert r.status_code == 200
    assert "Admin" in r.text
