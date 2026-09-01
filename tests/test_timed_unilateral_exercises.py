from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine, SessionLocal
from app.main import app
from migrations_data.seed_exercises import seed


@pytest.fixture(autouse=True)
def clean_and_seed():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed()
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


def test_exercise_library_flags_plank_as_timed():
    from app.database import SessionLocal
    from app.models.exercise import Exercise
    db = SessionLocal()
    plank = db.query(Exercise).filter(Exercise.name == "Plank").first()
    assert plank.is_timed is True
    walking_lunge = db.query(Exercise).filter(Exercise.name == "Walking Lunge").first()
    assert walking_lunge.is_unilateral is True
    squat = db.query(Exercise).filter(Exercise.name == "Barbell Back Squat").first()
    assert squat.is_timed is False
    assert squat.is_unilateral is False
    db.close()


def test_log_set_with_duration_seconds():
    client = _logged_in_client("durationuser")
    r = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Plank", "set_number": 1, "duration_seconds": 45,
    })
    assert r.status_code == 200

    logs = client.get("/api/workout-logs").json()
    assert logs[0]["duration_seconds"] == 45
    assert logs[0]["reps"] is None


def test_duration_seconds_validation_bounds():
    client = _logged_in_client("durationboundsuser")
    r = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Plank", "set_number": 1, "duration_seconds": 9999,
    })
    assert r.status_code == 422


def test_timed_exercise_can_also_carry_weight():
    """A weighted plank — duration AND weight both present, matching
    openGym's 'they can carry weight too' behavior for timed exercises."""
    client = _logged_in_client("weightedplankuser")
    r = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Plank", "set_number": 1, "duration_seconds": 60, "weight_kg": 10,
    })
    assert r.status_code == 200
    logs = client.get("/api/workout-logs").json()
    assert logs[0]["duration_seconds"] == 60
    assert logs[0]["weight_kg"] == 10.0


def test_edit_workout_log_updates_duration():
    client = _logged_in_client("editdurationuser")
    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Plank", "set_number": 1, "duration_seconds": 30,
    })
    entry_id = client.get("/api/workout-logs").json()[0]["id"]

    r = client.patch(f"/api/workout-logs/{entry_id}", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Plank", "set_number": 1, "duration_seconds": 50,
    })
    assert r.status_code == 200
    assert r.json()["duration_seconds"] == 50


def test_generated_plan_exposes_timed_and_unilateral_flags():
    client = _logged_in_client("planflagsuser")
    client.put("/api/profile", json={
        "goal": "general_fitness", "experience_level": "beginner", "equipment_access": "bodyweight_only",
        "height_cm": 175, "weight_kg": 75, "age": 25, "days_per_week": 3, "injuries_limitations": None,
    })
    plans = client.post("/api/plans/generate").json()
    found_flag_field = False
    for day in plans[0]["days"]:
        for ex in day["exercises"]:
            assert "is_timed" in ex
            assert "is_unilateral" in ex
            found_flag_field = True
    assert found_flag_field
