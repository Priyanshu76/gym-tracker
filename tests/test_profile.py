from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _logged_in_client(username: str) -> TestClient:
    client = TestClient(app)
    with patch("app.services.email.send_email"):
        from app.database import SessionLocal
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


VALID_PROFILE = {
    "goal": "hypertrophy",
    "experience_level": "intermediate",
    "equipment_access": "full_gym",
    "height_cm": 178.0,
    "weight_kg": 75.5,
    "age": 28,
    "days_per_week": 5,
    "injuries_limitations": None,
}


def test_new_user_has_no_profile_and_me_reflects_it():
    client = _logged_in_client("newprofileuser")
    me = client.get("/api/me").json()
    assert me["has_profile"] is False
    assert client.get("/api/profile").json() is None


def test_create_and_fetch_profile():
    client = _logged_in_client("profileuser")
    r = client.put("/api/profile", json=VALID_PROFILE)
    assert r.status_code == 200, r.text
    assert r.json()["goal"] == "hypertrophy"

    me = client.get("/api/me").json()
    assert me["has_profile"] is True

    fetched = client.get("/api/profile").json()
    assert fetched["days_per_week"] == 5


def test_update_existing_profile_overwrites_not_duplicates():
    client = _logged_in_client("updateuser")
    client.put("/api/profile", json=VALID_PROFILE)

    updated = dict(VALID_PROFILE)
    updated["goal"] = "fat_loss"
    updated["days_per_week"] = 3
    r = client.put("/api/profile", json=updated)
    assert r.status_code == 200
    assert r.json()["goal"] == "fat_loss"

    from app.database import SessionLocal
    from app.models.user_profile import UserProfile
    db = SessionLocal()
    count = db.query(UserProfile).count()
    db.close()
    assert count == 1, "updating a profile must not create a duplicate row"


def test_profile_validation_rejects_out_of_range_values():
    client = _logged_in_client("badprofileuser")
    bad = dict(VALID_PROFILE)
    bad["height_cm"] = 999
    r = client.put("/api/profile", json=bad)
    assert r.status_code == 422


def test_profile_requires_authentication():
    anon = TestClient(app)
    assert anon.get("/api/profile").status_code == 401
    assert anon.put("/api/profile", json=VALID_PROFILE).status_code == 401


def test_profiles_isolated_between_users():
    alice = _logged_in_client("profilealice")
    bob = _logged_in_client("profilebob")
    alice.put("/api/profile", json=VALID_PROFILE)

    assert alice.get("/api/profile").json() is not None
    assert bob.get("/api/profile").json() is None


def test_onboarding_and_profile_pages_render():
    client = _logged_in_client("pageuser")
    assert client.get("/onboarding").status_code == 200
    assert client.get("/profile").status_code == 200
