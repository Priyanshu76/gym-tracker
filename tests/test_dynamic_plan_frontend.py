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


def test_deactivate_reverts_to_classic():
    client = _logged_in_client_with_profile("deactivateuser")
    plans = client.post("/api/plans/generate").json()
    client.patch(f"/api/plans/{plans[0]['id']}/activate")
    assert client.get("/api/plans/active").json() is not None

    r = client.patch("/api/plans/deactivate")
    assert r.status_code == 200
    assert client.get("/api/plans/active").json() is None


def test_deactivate_with_no_active_plan_is_a_safe_noop():
    client = _logged_in_client_with_profile("noplanuser")
    r = client.patch("/api/plans/deactivate")
    assert r.status_code == 200


def test_plans_page_renders():
    client = _logged_in_client_with_profile("planspageuser")
    r = client.get("/plans")
    assert r.status_code == 200
    assert "My Plan" in r.text


def test_log_page_references_dynamic_plan_fetch():
    """Confirms the actual shipped page includes the plan-fetch/transform
    logic — not just that the standalone function is syntactically valid."""
    client = _logged_in_client_with_profile("logpageuser")
    r = client.get("/")
    assert "/api/plans/active" in r.text
    assert "transformGeneratedPlan" in r.text
