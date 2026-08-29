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


# ==================================================================
# Bug #3: edit/delete workout log entries
# ==================================================================
def test_edit_workout_log_entry():
    client = _logged_in_client("edituser")
    log_id = client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 60, "reps": 8,
    }).json()
    logs = client.get("/api/workout-logs").json()
    entry_id = logs[0]["id"]

    r = client.patch(f"/api/workout-logs/{entry_id}", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 65, "reps": 6,
    })
    assert r.status_code == 200
    assert r.json()["weight_kg"] == 65.0
    assert r.json()["reps"] == 6

    updated = client.get("/api/workout-logs").json()
    assert updated[0]["weight_kg"] == 65.0


def test_delete_workout_log_entry():
    client = _logged_in_client("deleteuser")
    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 60, "reps": 8,
    })
    logs = client.get("/api/workout-logs").json()
    entry_id = logs[0]["id"]

    r = client.delete(f"/api/workout-logs/{entry_id}")
    assert r.status_code == 200
    assert client.get("/api/workout-logs").json() == []


def test_cannot_edit_or_delete_another_users_log_entry():
    alice = _logged_in_client("editalice")
    bob = _logged_in_client("editbob")
    alice.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 60, "reps": 8,
    })
    alice_entry_id = alice.get("/api/workout-logs").json()[0]["id"]

    r1 = bob.patch(f"/api/workout-logs/{alice_entry_id}", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 100, "reps": 1,
    })
    assert r1.status_code == 404

    r2 = bob.delete(f"/api/workout-logs/{alice_entry_id}")
    assert r2.status_code == 404

    # confirm alice's entry is untouched
    assert alice.get("/api/workout-logs").json()[0]["weight_kg"] == 60.0


def test_edit_delete_require_authentication():
    anon = TestClient(app)
    fake_id = "00000000-0000-0000-0000-000000000000"
    assert anon.patch(f"/api/workout-logs/{fake_id}", json={}).status_code == 401
    assert anon.delete(f"/api/workout-logs/{fake_id}").status_code == 401


# ==================================================================
# Bug #4: beginner + full_gym should reach foundational barbell lifts
# ==================================================================
def test_beginner_with_full_gym_gets_foundational_barbell_lifts():
    from app.models.exercise import Exercise
    from app.models.user_profile import EquipmentAccess, ExperienceLevel, Goal, UserProfile
    from app.services.plan_generator import generate_plan_options
    import uuid

    db = SessionLocal()
    profile = UserProfile(
        user_id=uuid.uuid4(), goal=Goal.strength, experience_level=ExperienceLevel.beginner,
        equipment_access=EquipmentAccess.full_gym, height_cm=175, weight_kg=75, age=25, days_per_week=4,
    )
    options = generate_plan_options(profile, db, num_options=1, extra_seed="fixed-for-test")
    db.close()

    all_names = {ge.exercise.name for day in options[0].days for ge in day.exercises}
    foundational_lifts = {"Barbell Back Squat", "Barbell Bench Press", "Barbell Row", "Barbell Overhead Press"}
    assert all_names & foundational_lifts, (
        f"A beginner with full gym access should see at least one foundational barbell lift, got: {all_names}"
    )


def test_regenerating_produces_different_results():
    """The actual product-level bug: hitting 'Generate new options' twice
    used to return the identical plan both times."""
    from app.models.user_profile import EquipmentAccess, ExperienceLevel, Goal, UserProfile
    from app.services.plan_generator import generate_plan_options
    import uuid

    db = SessionLocal()
    profile = UserProfile(
        user_id=uuid.uuid4(), goal=Goal.hypertrophy, experience_level=ExperienceLevel.intermediate,
        equipment_access=EquipmentAccess.full_gym, height_cm=178, weight_kg=75, age=28, days_per_week=4,
    )
    first_call = generate_plan_options(profile, db, num_options=1, extra_seed="call-one")
    second_call = generate_plan_options(profile, db, num_options=1, extra_seed="call-two")
    db.close()

    first_names = [ge.exercise.name for day in first_call[0].days for ge in day.exercises]
    second_names = [ge.exercise.name for day in second_call[0].days for ge in day.exercises]
    assert first_names != second_names, "different extra_seed values should produce different plans"


def test_same_extra_seed_still_deterministic():
    """Confirms the fix didn't break reproducibility when the caller wants it."""
    from app.models.user_profile import EquipmentAccess, ExperienceLevel, Goal, UserProfile
    from app.services.plan_generator import generate_plan_options
    import uuid

    user_id = uuid.uuid4()
    db = SessionLocal()
    profile = UserProfile(
        user_id=user_id, goal=Goal.hypertrophy, experience_level=ExperienceLevel.intermediate,
        equipment_access=EquipmentAccess.full_gym, height_cm=178, weight_kg=75, age=28, days_per_week=4,
    )
    a = generate_plan_options(profile, db, num_options=1, extra_seed="same-seed")
    b = generate_plan_options(profile, db, num_options=1, extra_seed="same-seed")
    db.close()

    names_a = [ge.exercise.name for day in a[0].days for ge in day.exercises]
    names_b = [ge.exercise.name for day in b[0].days for ge in day.exercises]
    assert names_a == names_b
