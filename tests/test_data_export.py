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


def _logged_in_client_with_profile(username: str) -> TestClient:
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
        "goal": "hypertrophy", "experience_level": "intermediate", "equipment_access": "full_gym",
        "height_cm": 178.0, "weight_kg": 75.0, "age": 28, "days_per_week": 4, "injuries_limitations": None,
    })
    return client


# ==================================================================
# Full account export
# ==================================================================
def test_full_export_includes_everything():
    client = _logged_in_client_with_profile("exportfulluser")
    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 100, "reps": 5,
    })
    client.post("/api/body-metrics", json={"weight_kg": 80})
    client.post("/api/custom-exercises", json={"main_exercise": "Barbell Back Squat", "custom_alt_name": "Front Squat"})
    client.post("/api/plans/generate")

    r = client.get("/api/export/full")
    assert r.status_code == 200
    data = r.json()
    assert data["profile"]["goal"] == "hypertrophy"
    assert len(data["workout_logs"]) == 1
    assert len(data["body_metrics"]) == 1
    assert len(data["custom_exercises"]) == 1
    assert len(data["plans"]) == 3  # generate produces 3 options


def test_full_export_never_includes_password_hash():
    client = _logged_in_client_with_profile("exportsecureuser")
    r = client.get("/api/export/full")
    body_text = r.text
    assert "password_hash" not in body_text
    assert "argon2" not in body_text  # would appear inside any leaked hash string


def test_full_export_scoped_to_current_user():
    alice = _logged_in_client_with_profile("exportalice")
    bob = _logged_in_client_with_profile("exportbob")
    alice.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "set_number": 1, "weight_kg": 100, "reps": 5,
    })

    bob_export = bob.get("/api/export/full").json()
    assert bob_export["workout_logs"] == []


def test_full_export_requires_authentication():
    anon = TestClient(app)
    assert anon.get("/api/export/full").status_code == 401


# ==================================================================
# Plan import
# ==================================================================
def _sample_plan_payload():
    return {
        "name": "Shared Push Pull Legs",
        "default_progression_rule": "linear",
        "days": [
            {
                "day_index": 0, "day_name": "Monday", "split_label": "Push", "is_rest": False,
                "exercises": [
                    {"exercise_name": "Barbell Bench Press", "order_index": 0, "sets": 4, "reps_low": 4, "reps_high": 8},
                    {"exercise_name": "This Exercise Does Not Exist", "order_index": 1, "sets": 3, "reps_low": 8, "reps_high": 12},
                ],
            },
            {"day_index": 6, "day_name": "Sunday", "split_label": "Rest", "is_rest": True, "exercises": []},
        ],
    }


def test_import_plan_creates_inactive_plan():
    client = _logged_in_client_with_profile("importuser")
    r = client.post("/api/export/plans/import", json=_sample_plan_payload())
    assert r.status_code == 200, r.text
    plan_id = r.json()["plan_id"]

    plans = client.get("/api/plans").json()
    imported = next(p for p in plans if p["id"] == plan_id)
    assert imported["is_active"] is False
    assert imported["name"] == "Shared Push Pull Legs"


def test_import_plan_matches_exercises_by_name_and_skips_unmatched():
    client = _logged_in_client_with_profile("importskipuser")
    r = client.post("/api/export/plans/import", json=_sample_plan_payload())
    assert r.json()["skipped_exercises"] == ["This Exercise Does Not Exist"]

    client.patch(f"/api/plans/{r.json()['plan_id']}/activate")
    active = client.get("/api/plans/active").json()
    monday = next(d for d in active["days"] if d["day_name"] == "Monday")
    assert len(monday["exercises"]) == 1  # only the matched one was created
    assert monday["exercises"][0]["name"] == "Barbell Bench Press"


def test_import_plan_never_overwrites_existing_plans():
    """The core 'merges, never overwritten' guarantee — importing must not
    touch any plan the user already has."""
    client = _logged_in_client_with_profile("importmergeuser")
    existing = client.post("/api/plans/generate").json()
    existing_ids = {p["id"] for p in existing}

    client.post("/api/export/plans/import", json=_sample_plan_payload())

    all_plans = client.get("/api/plans").json()
    all_ids = {p["id"] for p in all_plans}
    assert existing_ids.issubset(all_ids), "importing must not remove or replace existing plans"
    assert len(all_plans) == 4  # 3 original + 1 imported


def test_import_plan_requires_authentication():
    anon = TestClient(app)
    assert anon.post("/api/export/plans/import", json=_sample_plan_payload()).status_code == 401


def test_export_then_import_round_trip():
    """Export a real generated plan, feed its structure back through
    import, confirm it recreates an equivalent plan."""
    client = _logged_in_client_with_profile("roundtripuser")
    client.post("/api/plans/generate")
    full_export = client.get("/api/export/full").json()
    original_plan = full_export["plans"][0]

    import_payload = {
        "name": original_plan["name"] + " (copy)",
        "default_progression_rule": original_plan["default_progression_rule"],
        "days": original_plan["days"],
    }
    r = client.post("/api/export/plans/import", json=import_payload)
    assert r.status_code == 200
    assert r.json()["skipped_exercises"] == []  # every exercise in a real generated plan exists in the library
