from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine, SessionLocal
from app.main import app
from migrations_data.seed_exercises import seed


@pytest.fixture(autouse=True)
def clean_and_seed_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed()
    yield


def _logged_in_client_with_profile(username: str, **profile_overrides) -> TestClient:
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

    profile = {
        "goal": "hypertrophy", "experience_level": "intermediate", "equipment_access": "full_gym",
        "height_cm": 178.0, "weight_kg": 75.0, "age": 28, "days_per_week": 4, "injuries_limitations": None,
    }
    profile.update(profile_overrides)
    client.put("/api/profile", json=profile)
    return client


# ==================================================================
# Generator unit tests — no HTTP, direct against the service function
# ==================================================================
def test_generator_produces_three_distinct_options():
    from app.models.user_profile import EquipmentAccess, ExperienceLevel, Goal, UserProfile
    from app.services.plan_generator import generate_plan_options
    import uuid

    db = SessionLocal()
    profile = UserProfile(
        user_id=uuid.uuid4(), goal=Goal.hypertrophy, experience_level=ExperienceLevel.intermediate,
        equipment_access=EquipmentAccess.full_gym, height_cm=178, weight_kg=75, age=28, days_per_week=4,
    )
    options = generate_plan_options(profile, db, num_options=3)
    db.close()

    assert len(options) == 3
    exercise_sets = [
        frozenset(ex.exercise.name for day in opt.days for ex in day.exercises)
        for opt in options
    ]
    assert len(set(exercise_sets)) > 1, "the 3 options should not all be identical"


def test_generator_is_deterministic_for_same_profile():
    from app.models.user_profile import EquipmentAccess, ExperienceLevel, Goal, UserProfile
    from app.services.plan_generator import generate_plan_options
    import uuid

    user_id = uuid.uuid4()
    db = SessionLocal()
    profile = UserProfile(
        user_id=user_id, goal=Goal.strength, experience_level=ExperienceLevel.beginner,
        equipment_access=EquipmentAccess.home_basic, height_cm=170, weight_kg=70, age=25, days_per_week=3,
    )
    options_a = generate_plan_options(profile, db, num_options=3)
    options_b = generate_plan_options(profile, db, num_options=3)
    db.close()

    names_a = [[ex.exercise.name for day in opt.days for ex in day.exercises] for opt in options_a]
    names_b = [[ex.exercise.name for day in opt.days for ex in day.exercises] for opt in options_b]
    assert names_a == names_b, "same profile must produce the same plan every time — not random"


def test_generator_never_exceeds_equipment_access():
    from app.models.exercise import EQUIPMENT_RANK
    from app.models.user_profile import EquipmentAccess, ExperienceLevel, Goal, UserProfile
    from app.services.plan_generator import generate_plan_options
    import uuid

    db = SessionLocal()
    profile = UserProfile(
        user_id=uuid.uuid4(), goal=Goal.general_fitness, experience_level=ExperienceLevel.beginner,
        equipment_access=EquipmentAccess.bodyweight_only, height_cm=175, weight_kg=70, age=30, days_per_week=3,
    )
    options = generate_plan_options(profile, db, num_options=2)
    db.close()

    user_rank = EQUIPMENT_RANK[EquipmentAccess.bodyweight_only]
    for opt in options:
        for day in opt.days:
            for ge in day.exercises:
                assert EQUIPMENT_RANK[ge.exercise.equipment_needed] <= user_rank, (
                    f"{ge.exercise.name} needs more equipment than bodyweight_only allows"
                )


def test_generator_never_exceeds_experience_level():
    from app.models.exercise import EXPERIENCE_RANK
    from app.models.user_profile import EquipmentAccess, ExperienceLevel, Goal, UserProfile
    from app.services.plan_generator import generate_plan_options
    import uuid

    db = SessionLocal()
    profile = UserProfile(
        user_id=uuid.uuid4(), goal=Goal.strength, experience_level=ExperienceLevel.beginner,
        equipment_access=EquipmentAccess.full_gym, height_cm=175, weight_kg=70, age=30, days_per_week=5,
    )
    options = generate_plan_options(profile, db, num_options=2)
    db.close()

    user_rank = EXPERIENCE_RANK[ExperienceLevel.beginner]
    for opt in options:
        for day in opt.days:
            for ge in day.exercises:
                assert EXPERIENCE_RANK[ge.exercise.min_experience_level] <= user_rank, (
                    f"{ge.exercise.name} is above beginner's experience level"
                )


def test_generator_respects_days_per_week_and_rest_days():
    from app.models.user_profile import EquipmentAccess, ExperienceLevel, Goal, UserProfile
    from app.services.plan_generator import generate_plan_options
    import uuid

    db = SessionLocal()
    profile = UserProfile(
        user_id=uuid.uuid4(), goal=Goal.hypertrophy, experience_level=ExperienceLevel.advanced,
        equipment_access=EquipmentAccess.full_gym, height_cm=180, weight_kg=85, age=25, days_per_week=5,
    )
    options = generate_plan_options(profile, db, num_options=1)
    db.close()

    plan = options[0]
    assert len(plan.days) == 7
    training_days = [d for d in plan.days if not d.is_rest]
    rest_days = [d for d in plan.days if d.is_rest]
    assert len(training_days) == 5
    assert len(rest_days) == 2
    for day in training_days:
        assert len(day.exercises) > 0


def test_strength_goal_uses_low_rep_high_set_scheme():
    from app.models.user_profile import EquipmentAccess, ExperienceLevel, Goal, UserProfile
    from app.services.plan_generator import generate_plan_options
    import uuid

    db = SessionLocal()
    profile = UserProfile(
        user_id=uuid.uuid4(), goal=Goal.strength, experience_level=ExperienceLevel.advanced,
        equipment_access=EquipmentAccess.full_gym, height_cm=180, weight_kg=85, age=25, days_per_week=4,
    )
    options = generate_plan_options(profile, db, num_options=1)
    db.close()

    for day in options[0].days:
        for ge in day.exercises:
            assert ge.reps_high <= 8, f"strength goal should use low reps, got {ge.reps_low}-{ge.reps_high}"


# ==================================================================
# API-level tests
# ==================================================================
def test_generate_requires_profile_first():
    client = TestClient(app)
    with patch("app.services.email.send_email"):
        from app.models.pending_signup import PendingSignup
        from app.models.user import User
        from app.services.security import hash_password
        client.post("/api/signup", json={"username": "noprofileuser", "display_name": "N", "email": "n@example.com", "website_url": ""})
        db = SessionLocal()
        pending = db.query(PendingSignup).filter(PendingSignup.username == "noprofileuser").first()
        client.get(f"/api/verify-email?request_id={pending.id}&token={pending.verification_token}")
        db.refresh(pending)
        client.get(f"/api/approve-signup?request_id={pending.id}&token={pending.approval_token}")
        user = db.query(User).filter(User.username == "noprofileuser").first()
        user.password_hash = hash_password("KnownPass123!")
        db.commit()
        db.close()
    client.post("/api/login", json={"username": "noprofileuser", "password": "KnownPass123!"})

    r = client.post("/api/plans/generate")
    assert r.status_code == 400


def test_generate_persists_three_plans_and_none_active_yet():
    client = _logged_in_client_with_profile("planuser")
    r = client.post("/api/plans/generate")
    assert r.status_code == 200, r.text
    plans = r.json()
    assert len(plans) == 3
    assert all(not p["is_active"] for p in plans)

    listed = client.get("/api/plans").json()
    assert len(listed) == 3


def test_activate_plan_deactivates_others():
    client = _logged_in_client_with_profile("activateuser")
    plans = client.post("/api/plans/generate").json()

    r1 = client.patch(f"/api/plans/{plans[0]['id']}/activate")
    assert r1.status_code == 200
    assert r1.json()["is_active"] is True

    listed = client.get("/api/plans").json()
    active_ids = [p["id"] for p in listed if p["is_active"]]
    assert active_ids == [plans[0]["id"]]

    r2 = client.patch(f"/api/plans/{plans[1]['id']}/activate")
    listed2 = client.get("/api/plans").json()
    active_ids2 = [p["id"] for p in listed2 if p["is_active"]]
    assert active_ids2 == [plans[1]["id"]], "activating a new plan must deactivate the previous one"


def test_get_active_plan_returns_full_structure():
    client = _logged_in_client_with_profile("activeplanuser", days_per_week=3)
    plans = client.post("/api/plans/generate").json()
    client.patch(f"/api/plans/{plans[0]['id']}/activate")

    active = client.get("/api/plans/active").json()
    assert active["is_active"] is True
    assert len(active["days"]) == 7
    training_days = [d for d in active["days"] if not d["is_rest"]]
    assert len(training_days) == 3
    for day in training_days:
        assert len(day["exercises"]) > 0
        for ex in day["exercises"]:
            assert ex["name"]
            assert ex["sets"] > 0


def test_no_active_plan_returns_null_not_error():
    client = _logged_in_client_with_profile("noactiveuser")
    r = client.get("/api/plans/active")
    assert r.status_code == 200
    assert r.json() is None


def test_plans_isolated_between_users():
    alice = _logged_in_client_with_profile("planalice")
    bob = _logged_in_client_with_profile("planbob")
    alice.post("/api/plans/generate")

    assert len(alice.get("/api/plans").json()) == 3
    assert len(bob.get("/api/plans").json()) == 0


def test_cannot_activate_another_users_plan():
    alice = _logged_in_client_with_profile("planalice2")
    bob = _logged_in_client_with_profile("planbob2")
    alice_plans = alice.post("/api/plans/generate").json()

    r = bob.patch(f"/api/plans/{alice_plans[0]['id']}/activate")
    assert r.status_code == 404
