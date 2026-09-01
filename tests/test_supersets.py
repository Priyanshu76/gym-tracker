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


def _first_two_exercises_same_day(plan_detail):
    for day in plan_detail["days"]:
        if len(day["exercises"]) >= 2:
            return day["exercises"][0], day["exercises"][1]
    raise AssertionError("no day with 2+ exercises found")


def test_pair_superset_success():
    client = _logged_in_client_with_profile("superuser")
    plans = client.post("/api/plans/generate").json()
    ex_a, ex_b = _first_two_exercises_same_day(plans[0])

    r = client.patch("/api/plans/plan-exercises/pair-superset", params={
        "plan_exercise_id_a": ex_a["id"], "plan_exercise_id_b": ex_b["id"],
    })
    assert r.status_code == 200, r.text
    group_id = r.json()["superset_group_id"]

    active_plan = client.get(f"/api/plans/active").json()
    # not yet activated -- fetch via the plan detail directly by re-listing
    client.patch(f"/api/plans/{plans[0]['id']}/activate")
    active = client.get("/api/plans/active").json()
    day, _ = None, None
    for d in active["days"]:
        for ex in d["exercises"]:
            if ex["id"] == ex_a["id"] or ex["id"] == ex_b["id"]:
                assert ex["superset_group_id"] == group_id


def test_pair_superset_rejects_different_days():
    client = _logged_in_client_with_profile("superdiffdayuser")
    plans = client.post("/api/plans/generate").json()
    days_with_exercises = [d for d in plans[0]["days"] if d["exercises"]]
    if len(days_with_exercises) < 2:
        return  # not enough days generated to test this — profile/generator dependent
    ex_a = days_with_exercises[0]["exercises"][0]
    ex_b = days_with_exercises[1]["exercises"][0]

    r = client.patch("/api/plans/plan-exercises/pair-superset", params={
        "plan_exercise_id_a": ex_a["id"], "plan_exercise_id_b": ex_b["id"],
    })
    assert r.status_code == 400


def test_pair_superset_rejects_self_pairing():
    client = _logged_in_client_with_profile("superselfuser")
    plans = client.post("/api/plans/generate").json()
    ex_a, _ = _first_two_exercises_same_day(plans[0])

    r = client.patch("/api/plans/plan-exercises/pair-superset", params={
        "plan_exercise_id_a": ex_a["id"], "plan_exercise_id_b": ex_a["id"],
    })
    assert r.status_code == 400


def test_unpair_superset_dissolves_both_sides():
    client = _logged_in_client_with_profile("superunpairuser")
    plans = client.post("/api/plans/generate").json()
    ex_a, ex_b = _first_two_exercises_same_day(plans[0])
    client.patch("/api/plans/plan-exercises/pair-superset", params={
        "plan_exercise_id_a": ex_a["id"], "plan_exercise_id_b": ex_b["id"],
    })

    r = client.patch(f"/api/plans/plan-exercises/{ex_a['id']}/unpair-superset")
    assert r.status_code == 200

    client.patch(f"/api/plans/{plans[0]['id']}/activate")
    active = client.get("/api/plans/active").json()
    for d in active["days"]:
        for ex in d["exercises"]:
            if ex["id"] in (ex_a["id"], ex_b["id"]):
                assert ex["superset_group_id"] is None, "unpairing one side must dissolve the whole group"


def test_pair_superset_scoped_to_owner():
    alice = _logged_in_client_with_profile("superowneralice")
    bob = _logged_in_client_with_profile("superownerbob")
    plans = alice.post("/api/plans/generate").json()
    ex_a, ex_b = _first_two_exercises_same_day(plans[0])

    r = bob.patch("/api/plans/plan-exercises/pair-superset", params={
        "plan_exercise_id_a": ex_a["id"], "plan_exercise_id_b": ex_b["id"],
    })
    assert r.status_code == 404


def test_pair_superset_requires_authentication():
    anon = TestClient(app)
    fake_id = "00000000-0000-0000-0000-000000000000"
    r = anon.patch("/api/plans/plan-exercises/pair-superset", params={
        "plan_exercise_id_a": fake_id, "plan_exercise_id_b": fake_id,
    })
    assert r.status_code == 401
