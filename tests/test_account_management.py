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


def _logged_in_client(username: str) -> TestClient:
    client = TestClient(app)
    with patch("app.services.email.send_email"):
        from app.models.pending_signup import PendingSignup
        from app.models.user import User
        from app.services.security import hash_password
        client.post("/api/signup", json={"username": username, "display_name": username.title(), "email": f"{username}@example.com", "website_url": ""})
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


# ==================================================================
# Change password
# ==================================================================
def test_change_password_success():
    client = _logged_in_client("changepwuser")
    r = client.post("/api/change-password", json={"current_password": "KnownPass123!", "new_password": "BrandNewPass456!"})
    assert r.status_code == 200

    fresh = TestClient(app)
    assert fresh.post("/api/login", json={"username": "changepwuser", "password": "BrandNewPass456!"}).status_code == 200
    assert fresh.post("/api/login", json={"username": "changepwuser", "password": "KnownPass123!"}).status_code == 401


def test_change_password_wrong_current_password_rejected():
    client = _logged_in_client("wrongpwuser")
    r = client.post("/api/change-password", json={"current_password": "TotallyWrong!", "new_password": "BrandNewPass456!"})
    assert r.status_code == 400

    # original password must still work
    fresh = TestClient(app)
    assert fresh.post("/api/login", json={"username": "wrongpwuser", "password": "KnownPass123!"}).status_code == 200


def test_change_password_revokes_other_sessions():
    client = _logged_in_client("revokepwuser")
    old_session_token = client.cookies.get("access_token")

    client.post("/api/change-password", json={"current_password": "KnownPass123!", "new_password": "BrandNewPass456!"})

    stale_client = TestClient(app)
    stale_client.cookies.set("access_token", old_session_token)
    assert stale_client.get("/api/me").status_code == 401


def test_change_password_requires_authentication():
    anon = TestClient(app)
    r = anon.post("/api/change-password", json={"current_password": "x", "new_password": "BrandNewPass456!"})
    assert r.status_code == 401


def test_change_password_validates_new_password_length():
    client = _logged_in_client("shortpwuser")
    r = client.post("/api/change-password", json={"current_password": "KnownPass123!", "new_password": "short"})
    assert r.status_code == 422


# ==================================================================
# Account deletion
# ==================================================================
def test_delete_account_success_and_cascades():
    client = _logged_in_client("deleteaccountuser")
    client.put("/api/profile", json={
        "goal": "hypertrophy", "experience_level": "intermediate", "equipment_access": "full_gym",
        "height_cm": 178.0, "weight_kg": 75.0, "age": 28, "days_per_week": 4, "injuries_limitations": None,
    })
    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 100, "reps": 5,
    })

    from app.models.user import User
    db = SessionLocal()
    assert db.query(User).filter(User.username == "deleteaccountuser").count() == 1
    db.close()

    r = client.post("/api/account/delete", json={"current_password": "KnownPass123!"})
    assert r.status_code == 200

    db = SessionLocal()
    assert db.query(User).filter(User.username == "deleteaccountuser").count() == 0
    from app.models.workout_log import WorkoutLog
    from app.models.user_profile import UserProfile
    assert db.query(WorkoutLog).count() == 0, "workout logs must cascade-delete with the account"
    assert db.query(UserProfile).count() == 0, "profile must cascade-delete with the account"
    db.close()


def test_delete_account_wrong_password_rejected():
    client = _logged_in_client("keepaccountuser")
    r = client.post("/api/account/delete", json={"current_password": "WrongPassword!"})
    assert r.status_code == 400

    from app.models.user import User
    db = SessionLocal()
    assert db.query(User).filter(User.username == "keepaccountuser").count() == 1
    db.close()


def test_delete_account_requires_authentication():
    anon = TestClient(app)
    r = anon.post("/api/account/delete", json={"current_password": "x"})
    assert r.status_code == 401


def test_deleted_account_username_can_be_reused_for_signup():
    """Confirms the delete genuinely removed the row, not just deactivated it."""
    client = _logged_in_client("reuseuser")
    client.post("/api/account/delete", json={"current_password": "KnownPass123!"})

    fresh = TestClient(app)
    with patch("app.services.email.send_email"):
        r = fresh.post("/api/signup", json={"username": "reuseuser", "display_name": "New", "email": "different@example.com", "website_url": ""})
    assert r.status_code == 200


def test_profile_page_includes_account_management_ui():
    client = TestClient(app)
    r = client.get("/profile")
    assert 'id="change-password-form"' in r.text
    assert 'id="delete-account-btn"' in r.text
    assert "/api/change-password" in r.text
    assert "/api/account/delete" in r.text
