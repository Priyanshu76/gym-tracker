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


def test_first_ever_set_is_not_a_pr():
    """Nothing to beat yet — the very first logged set shouldn't be flagged."""
    client = _logged_in_client("firstsetuser")
    r = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 100, "reps": 5,
    })
    assert r.status_code == 200
    assert r.json()["is_pr"] is False


def test_heavier_weight_is_a_weight_pr():
    client = _logged_in_client("weightpruser")
    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 100, "reps": 5,
    })
    r = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-30", "day_name": "Sunday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 105, "reps": 5,
    })
    assert r.json()["is_pr"] is True
    assert r.json()["pr_type"] == "weight"


def test_same_weight_more_reps_is_an_estimated_1rm_pr():
    """Not heavier, but more reps at the same weight beats the estimated 1RM."""
    client = _logged_in_client("e1rmpruser")
    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Bench Press", "set_number": 1, "weight_kg": 80, "reps": 5,
    })
    r = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-30", "day_name": "Sunday", "section": "Main",
        "exercise": "Barbell Bench Press", "set_number": 1, "weight_kg": 80, "reps": 8,
    })
    assert r.json()["is_pr"] is True
    assert r.json()["pr_type"] == "estimated_1rm"


def test_lighter_weight_fewer_reps_is_not_a_pr():
    client = _logged_in_client("nopruser")
    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Bench Press", "set_number": 1, "weight_kg": 80, "reps": 8,
    })
    r = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-30", "day_name": "Sunday", "section": "Main",
        "exercise": "Barbell Bench Press", "set_number": 1, "weight_kg": 70, "reps": 5,
    })
    assert r.json()["is_pr"] is False


def test_pr_check_scoped_to_exercise_name():
    """A PR on one exercise shouldn't be influenced by history on a
    different exercise."""
    client = _logged_in_client("prscopeuser")
    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 150, "reps": 5,
    })
    r = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Bench Press", "set_number": 1, "weight_kg": 60, "reps": 5,
    })
    assert r.json()["is_pr"] is False  # first-ever bench, not compared against squat history


def test_pr_check_scoped_to_user():
    """One user's heavy lifting history must not affect another user's PR
    detection."""
    alice = _logged_in_client("prisoalice")
    bob = _logged_in_client("prisobob")
    alice.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 200, "reps": 5,
    })
    r = bob.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 60, "reps": 5,
    })
    assert r.json()["is_pr"] is False  # bob's first squat, not compared against alice's


def test_warmup_sets_never_trigger_or_count_toward_pr():
    client = _logged_in_client("warmupprnotuser")
    # a very heavy "warmup" set-type shouldn't itself be flagged as a PR...
    r1 = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 200, "reps": 5, "set_type": "warmup",
    })
    assert r1.json()["is_pr"] is False
    # ...and a genuinely lighter *working* set afterward should still count as
    # this exercise's first real PR-eligible set, unaffected by the heavy warmup
    r2 = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 2, "weight_kg": 100, "reps": 5, "set_type": "working",
    })
    assert r2.json()["is_pr"] is False  # first working set ever — nothing to beat, not compared against the warmup


def test_bodyweight_exercise_without_weight_never_flagged_as_pr():
    client = _logged_in_client("bwexuser")
    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Push-Up", "set_number": 1, "reps": 20,
    })
    r = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-30", "day_name": "Sunday", "section": "Main",
        "exercise": "Push-Up", "set_number": 1, "reps": 30,
    })
    assert r.json()["is_pr"] is False
