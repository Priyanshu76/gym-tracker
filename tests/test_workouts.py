"""
Tests for workout-logs and custom-exercises endpoints, including the thing
that actually matters most here: one user's data must never be visible to,
or removable by, another user.
"""
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


def _make_logged_in_client(username: str) -> TestClient:
    """Signs up, verifies, approves, and logs in a fresh user — returns a
    TestClient whose cookie jar is already authenticated as that user."""
    client = TestClient(app)
    with patch("app.services.email.send_email"):
        from app.database import SessionLocal
        from app.models.pending_signup import PendingSignup
        from app.models.user import User
        from app.services.security import hash_password

        client.post(
            "/api/signup",
            json={"username": username, "display_name": username.title(), "email": f"{username}@example.com", "website_url": ""},
        )
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


def test_log_main_set_and_read_it_back():
    client = _make_logged_in_client("alice")

    r = client.post(
        "/api/workout-logs",
        json={
            "workout_date": "2026-08-29",
            "day_name": "Saturday",
            "section": "Main",
            "exercise": "Barbell Back Squat",
            "muscle_group": "Quads",
            "set_number": 1,
            "weight_kg": 60.5,
            "reps": 8,
        },
    )
    assert r.status_code == 200, r.text

    r2 = client.get("/api/workout-logs")
    assert r2.status_code == 200
    logs = r2.json()
    assert len(logs) == 1
    assert logs[0]["exercise"] == "Barbell Back Squat"
    assert logs[0]["weight_kg"] == 60.5


def test_out_of_range_weight_rejected():
    client = _make_logged_in_client("bob")
    r = client.post(
        "/api/workout-logs",
        json={
            "workout_date": "2026-08-29",
            "day_name": "Saturday",
            "section": "Main",
            "exercise": "Deadlift",
            "set_number": 1,
            "weight_kg": 9999,
            "reps": 8,
        },
    )
    assert r.status_code == 422


def test_warmup_metrics_roundtrip():
    client = _make_logged_in_client("carol")
    r = client.post(
        "/api/workout-logs",
        json={
            "workout_date": "2026-08-29",
            "day_name": "Saturday",
            "section": "Warmup",
            "exercise": "Treadmill",
            "metrics": {"Inclination": "5", "Speed": "6", "Minutes": "10"},
        },
    )
    assert r.status_code == 200
    logs = client.get("/api/workout-logs").json()
    assert logs[0]["metrics"] == {"Inclination": "5", "Speed": "6", "Minutes": "10"}


def test_unauthenticated_access_denied():
    anon = TestClient(app)
    assert anon.get("/api/workout-logs").status_code == 401
    assert anon.post("/api/workout-logs", json={}).status_code == 401


def test_workout_logs_are_isolated_between_users():
    alice = _make_logged_in_client("dave")
    bob = _make_logged_in_client("erin")

    alice.post(
        "/api/workout-logs",
        json={"workout_date": "2026-08-29", "day_name": "Sat", "section": "Main", "exercise": "Bench Press", "set_number": 1, "weight_kg": 40, "reps": 10},
    )

    assert len(alice.get("/api/workout-logs").json()) == 1
    assert len(bob.get("/api/workout-logs").json()) == 0, "one user's logs must never be visible to another"


def test_custom_exercise_add_list_remove():
    client = _make_logged_in_client("frank")

    r = client.post("/api/custom-exercises", json={"main_exercise": "Barbell Back Squat", "custom_alt_name": "Hack Squat"})
    assert r.status_code == 200
    exercise_id = r.json()["id"]

    r2 = client.get("/api/custom-exercises")
    assert len(r2.json()) == 1
    assert r2.json()[0]["custom_alt_name"] == "Hack Squat"

    r3 = client.delete(f"/api/custom-exercises/{exercise_id}")
    assert r3.status_code == 200

    r4 = client.get("/api/custom-exercises")
    assert len(r4.json()) == 0, "removed exercise should no longer be listed"


def test_cannot_remove_another_users_custom_exercise():
    grace = _make_logged_in_client("grace")
    heidi = _make_logged_in_client("heidi")

    r = grace.post("/api/custom-exercises", json={"main_exercise": "Squat", "custom_alt_name": "Leg Press"})
    exercise_id = r.json()["id"]

    # heidi tries to delete grace's exercise by guessing/knowing its ID
    r2 = heidi.delete(f"/api/custom-exercises/{exercise_id}")
    assert r2.status_code == 404, "a user must not be able to remove another user's custom exercise"

    # confirm it's untouched from grace's perspective
    assert len(grace.get("/api/custom-exercises").json()) == 1
