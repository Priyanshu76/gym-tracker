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


def _logged_in_client_with_goal(username: str, goal: str) -> TestClient:
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
        "height_cm": 178.0, "weight_kg": 75.0, "age": 28, "days_per_week": 4, "injuries_limitations": None,
    })
    return client


def test_dashboard_page_includes_goal_adaptation_logic():
    """The shipped page must reference USER_GOAL and fetch the profile —
    confirms the wiring exists, not just that it's syntactically valid."""
    client = _logged_in_client_with_goal("dashgoaluser", "strength")
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "USER_GOAL" in r.text
    assert "GOAL_COPY" in r.text
    assert "/api/profile" in r.text


def test_goal_copy_covers_every_possible_goal_value():
    """If a new Goal enum value is ever added without updating GOAL_COPY,
    the dashboard would silently show a blank banner — catch that here."""
    import re
    content = open("app/templates/progress_dashboard.html").read()
    m = re.search(r"const GOAL_COPY = \{(.*?)\};", content, re.S)
    goal_copy_block = m.group(1)

    from app.models.user_profile import Goal
    for goal in Goal:
        assert goal.value in goal_copy_block, f"GOAL_COPY is missing an entry for {goal.value}"
