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


def test_rpe_and_set_type_persist():
    client = _logged_in_client("rpeuser")
    r = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 100, "reps": 5,
        "rpe": 8.5, "set_type": "amrap",
    })
    assert r.status_code == 200
    logs = client.get("/api/workout-logs").json()
    assert logs[0]["rpe"] == 8.5
    assert logs[0]["set_type"] == "amrap"


def test_set_type_defaults_to_working_when_omitted():
    client = _logged_in_client("defaultuser")
    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 100, "reps": 5,
    })
    logs = client.get("/api/workout-logs").json()
    assert logs[0]["set_type"] == "working"
    assert logs[0]["rpe"] is None


def test_rpe_validation_bounds():
    client = _logged_in_client("rpeboundsuser")
    r = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 100, "reps": 5, "rpe": 15,
    })
    assert r.status_code == 422


def test_last_session_returns_empty_for_never_logged_exercise():
    client = _logged_in_client("neverloggeduser")
    r = client.get("/api/workout-logs/last", params={"exercise": "Barbell Back Squat"})
    assert r.status_code == 200
    assert r.json() == []


def test_last_session_returns_most_recent_dates_sets_only():
    client = _logged_in_client("lastsessionuser")
    # older session: 2 sets
    for i in range(1, 3):
        client.post("/api/workout-logs", json={
            "workout_date": "2026-08-20", "day_name": "Thursday", "section": "Main",
            "exercise": "Barbell Back Squat", "set_number": i, "weight_kg": 80, "reps": 8,
        })
    # more recent session: 3 sets
    for i in range(1, 4):
        client.post("/api/workout-logs", json={
            "workout_date": "2026-08-27", "day_name": "Thursday", "section": "Main",
            "exercise": "Barbell Back Squat", "set_number": i, "weight_kg": 85, "reps": 6,
        })

    r = client.get("/api/workout-logs/last", params={"exercise": "Barbell Back Squat"})
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 3, "should only return the most recent session's sets, not all history"
    assert all(row["workout_date"] == "2026-08-27" for row in results)
    assert all(row["weight_kg"] == 85.0 for row in results)


def test_last_session_scoped_by_exercise_name_and_user():
    alice = _logged_in_client("lastalice")
    bob = _logged_in_client("lastbob")
    alice.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 100, "reps": 5,
    })
    alice.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Bench Press", "set_number": 1, "weight_kg": 60, "reps": 8,
    })

    squat_last = alice.get("/api/workout-logs/last", params={"exercise": "Barbell Back Squat"}).json()
    assert len(squat_last) == 1
    assert squat_last[0]["exercise"] == "Barbell Back Squat"

    bob_squat_last = bob.get("/api/workout-logs/last", params={"exercise": "Barbell Back Squat"}).json()
    assert bob_squat_last == [], "one user's last-session data must not leak to another"


def test_last_session_requires_authentication():
    anon = TestClient(app)
    assert anon.get("/api/workout-logs/last", params={"exercise": "Barbell Back Squat"}).status_code == 401
