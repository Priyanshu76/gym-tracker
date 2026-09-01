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


def _logged_in_client_with_profile(username: str, goal: str = "strength", days_per_week: int = 4) -> TestClient:
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
    client.put("/api/profile", json={
        "goal": goal, "experience_level": "intermediate", "equipment_access": "full_gym",
        "height_cm": 178.0, "weight_kg": 75.0, "age": 28, "days_per_week": days_per_week, "injuries_limitations": None,
    })
    return client


def _get_first_main_exercise(plan_detail):
    for day in plan_detail["days"]:
        for ex in day["exercises"]:
            return day, ex
    raise AssertionError("no exercises found in plan")


def test_generated_plan_has_goal_appropriate_default_progression_rule():
    client = _logged_in_client_with_profile("proguser", goal="strength")
    plans = client.post("/api/plans/generate").json()
    _, ex = _get_first_main_exercise(plans[0])
    assert ex["progression_rule"] == "greyskull_lp"


def test_hypertrophy_goal_defaults_to_double_progression():
    client = _logged_in_client_with_profile("hyperproguser", goal="hypertrophy")
    plans = client.post("/api/plans/generate").json()
    _, ex = _get_first_main_exercise(plans[0])
    assert ex["progression_rule"] == "double_progression"


def test_evaluate_progression_establishes_baseline_on_first_session():
    client = _logged_in_client_with_profile("baselineuser", goal="general_fitness")
    plans = client.post("/api/plans/generate").json()
    client.patch(f"/api/plans/{plans[0]['id']}/activate")
    active = client.get("/api/plans/active").json()
    day, ex = _get_first_main_exercise(active)

    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": day["day_name"], "section": "Main",
        "exercise": ex["name"], "set_number": 1, "weight_kg": 50, "reps": ex["current_reps_target"] or 8,
    })

    plan_exercise_id = None
    from app.database import SessionLocal
    from app.models.workout_plan import PlanExercise, PlanDay, WorkoutPlan
    db = SessionLocal()
    pe_row = (
        db.query(PlanExercise)
        .join(PlanDay).join(WorkoutPlan)
        .filter(WorkoutPlan.id == plans[0]["id"])
        .first()
    )
    plan_exercise_id = str(pe_row.id)
    db.close()

    r = client.post(f"/api/plans/plan-exercises/{plan_exercise_id}/evaluate-progression")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["outcome"] in ("progressed", "repeated")
    assert data["note"]


def test_evaluate_progression_requires_logged_sets():
    client = _logged_in_client_with_profile("nologsuser")
    plans = client.post("/api/plans/generate").json()
    _, ex = _get_first_main_exercise(plans[0])

    from app.database import SessionLocal
    from app.models.workout_plan import PlanExercise, PlanDay, WorkoutPlan
    db = SessionLocal()
    pe_row = db.query(PlanExercise).join(PlanDay).join(WorkoutPlan).filter(WorkoutPlan.id == plans[0]["id"]).first()
    plan_exercise_id = str(pe_row.id)
    db.close()

    r = client.post(f"/api/plans/plan-exercises/{plan_exercise_id}/evaluate-progression")
    assert r.status_code == 400


def test_evaluate_progression_scoped_to_owner():
    alice = _logged_in_client_with_profile("progalice")
    bob = _logged_in_client_with_profile("progbob")
    plans = alice.post("/api/plans/generate").json()

    from app.database import SessionLocal
    from app.models.workout_plan import PlanExercise, PlanDay, WorkoutPlan
    db = SessionLocal()
    pe_row = db.query(PlanExercise).join(PlanDay).join(WorkoutPlan).filter(WorkoutPlan.id == plans[0]["id"]).first()
    plan_exercise_id = str(pe_row.id)
    db.close()

    r = bob.post(f"/api/plans/plan-exercises/{plan_exercise_id}/evaluate-progression")
    assert r.status_code == 404


def test_evaluate_progression_requires_authentication():
    anon = TestClient(app)
    fake_id = "00000000-0000-0000-0000-000000000000"
    assert anon.post(f"/api/plans/plan-exercises/{fake_id}/evaluate-progression").status_code == 401


def test_manual_progression_rule_returns_error_not_a_result():
    """Sanity check that 'none' (manual) doesn't silently compute nonsense —
    it should explicitly say there's nothing to evaluate."""
    client = _logged_in_client_with_profile("manualuser")
    plans = client.post("/api/plans/generate").json()
    day, ex = _get_first_main_exercise(plans[0])

    from app.database import SessionLocal
    from app.models.workout_plan import PlanExercise, PlanDay, WorkoutPlan, ProgressionRule
    db = SessionLocal()
    pe_row = db.query(PlanExercise).join(PlanDay).join(WorkoutPlan).filter(WorkoutPlan.id == plans[0]["id"]).first()
    pe_row.progression_rule = ProgressionRule.none
    plan_exercise_id = str(pe_row.id)
    db.commit()
    db.close()

    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": day["day_name"], "section": "Main",
        "exercise": ex["name"], "set_number": 1, "weight_kg": 50, "reps": 8,
    })
    r = client.post(f"/api/plans/plan-exercises/{plan_exercise_id}/evaluate-progression")
    assert r.status_code == 400
