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


def _logged_in_client(username: str) -> TestClient:
    client = TestClient(app)
    with patch("app.services.email.send_email"):
        from app.database import SessionLocal
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


def test_dashboard_and_logs_pages_render_unauthenticated_gate():
    anon = TestClient(app)
    assert anon.get("/dashboard").status_code == 200  # page itself renders; its JS gates on /api/me
    assert anon.get("/logs").status_code == 200
    assert "priyanshu-n8n" not in anon.get("/dashboard").text
    assert "priyanshu-n8n" not in anon.get("/logs").text


def test_dashboard_data_pipeline_normalizes_api_shape():
    """The dashboard's JS maps snake_case API fields to its internal camelCase
    shape client-side — this confirms the API itself returns data the mapping
    can actually consume (workout_date, weight_kg, metrics dict, etc.)."""
    client = _logged_in_client("dashuser")

    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Main",
        "exercise": "Barbell Back Squat", "performed_as": "Hack Squat", "muscle_group": "Quads",
        "set_number": 1, "weight_kg": 80, "reps": 6,
    })
    client.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Saturday", "section": "Warmup",
        "exercise": "Treadmill", "metrics": {"Inclination": "5", "Speed": "6", "Minutes": "10"},
    })

    r = client.get("/api/workout-logs")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    main_row = next(x for x in rows if x["section"] == "Main")
    assert main_row["performed_as"] == "Hack Squat"
    assert main_row["weight_kg"] == 80.0
    warmup_row = next(x for x in rows if x["section"] == "Warmup")
    assert warmup_row["metrics"] == {"Inclination": "5", "Speed": "6", "Minutes": "10"}


def test_dashboard_and_logs_isolated_between_users():
    alice = _logged_in_client("dashalice")
    bob = _logged_in_client("dashbob")

    alice.post("/api/workout-logs", json={
        "workout_date": "2026-08-29", "day_name": "Sat", "section": "Main",
        "exercise": "Deadlift", "set_number": 1, "weight_kg": 100, "reps": 5,
    })

    assert len(alice.get("/api/workout-logs").json()) == 1
    assert len(bob.get("/api/workout-logs").json()) == 0
