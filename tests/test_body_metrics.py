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
# goal_weight_kg on profile
# ==================================================================
def test_profile_accepts_goal_weight():
    client = _logged_in_client("goalweightuser")
    r = client.put("/api/profile", json={
        "goal": "fat_loss", "experience_level": "beginner", "equipment_access": "home_basic",
        "height_cm": 170, "weight_kg": 85, "goal_weight_kg": 75, "age": 30, "days_per_week": 3,
    })
    assert r.status_code == 200
    assert r.json()["goal_weight_kg"] == 75.0


def test_profile_goal_weight_is_optional():
    client = _logged_in_client("nogoalweightuser")
    r = client.put("/api/profile", json={
        "goal": "fat_loss", "experience_level": "beginner", "equipment_access": "home_basic",
        "height_cm": 170, "weight_kg": 85, "age": 30, "days_per_week": 3,
    })
    assert r.status_code == 200
    assert r.json()["goal_weight_kg"] is None


def test_profile_goal_weight_validation_bounds():
    client = _logged_in_client("badgoalweightuser")
    r = client.put("/api/profile", json={
        "goal": "fat_loss", "experience_level": "beginner", "equipment_access": "home_basic",
        "height_cm": 170, "weight_kg": 85, "goal_weight_kg": 999, "age": 30, "days_per_week": 3,
    })
    assert r.status_code == 422


# ==================================================================
# Body metric logging
# ==================================================================
def test_log_and_list_body_weight():
    client = _logged_in_client("bwuser")
    r = client.post("/api/body-metrics", json={"weight_kg": 82.5})
    assert r.status_code == 200

    logs = client.get("/api/body-metrics").json()
    assert len(logs) == 1
    assert logs[0]["weight_kg"] == 82.5


def test_body_weight_logs_ordered_chronologically():
    client = _logged_in_client("bworderuser")
    client.post("/api/body-metrics", json={"weight_kg": 85})
    client.post("/api/body-metrics", json={"weight_kg": 84})
    client.post("/api/body-metrics", json={"weight_kg": 83})

    logs = client.get("/api/body-metrics").json()
    assert [l["weight_kg"] for l in logs] == [85.0, 84.0, 83.0]


def test_body_weight_validation_bounds():
    client = _logged_in_client("bwboundsuser")
    r = client.post("/api/body-metrics", json={"weight_kg": 5})
    assert r.status_code == 422


def test_delete_body_weight_entry():
    client = _logged_in_client("bwdeleteuser")
    client.post("/api/body-metrics", json={"weight_kg": 80})
    entry_id = client.get("/api/body-metrics").json()[0]["id"]

    r = client.delete(f"/api/body-metrics/{entry_id}")
    assert r.status_code == 200
    assert client.get("/api/body-metrics").json() == []


def test_body_weight_isolated_between_users():
    alice = _logged_in_client("bwalice")
    bob = _logged_in_client("bwbob")
    alice.post("/api/body-metrics", json={"weight_kg": 70})

    assert len(alice.get("/api/body-metrics").json()) == 1
    assert len(bob.get("/api/body-metrics").json()) == 0


def test_cannot_delete_another_users_body_weight_entry():
    alice = _logged_in_client("bwdelalice")
    bob = _logged_in_client("bwdelbob")
    alice.post("/api/body-metrics", json={"weight_kg": 70})
    entry_id = alice.get("/api/body-metrics").json()[0]["id"]

    r = bob.delete(f"/api/body-metrics/{entry_id}")
    assert r.status_code == 404


def test_body_metrics_requires_authentication():
    anon = TestClient(app)
    assert anon.get("/api/body-metrics").status_code == 401
    assert anon.post("/api/body-metrics", json={"weight_kg": 80}).status_code == 401
