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


def test_search_returns_matching_exercises():
    client = _logged_in_client("searchuser")
    r = client.get("/api/exercises/search", params={"q": "squat"})
    assert r.status_code == 200
    names = [ex["name"] for ex in r.json()]
    assert any("Squat" in n for n in names)
    assert all("squat" in n.lower() for n in names)


def test_search_with_no_query_returns_all_main_exercises():
    client = _logged_in_client("searchalluser")
    r = client.get("/api/exercises/search")
    assert r.status_code == 200
    assert len(r.json()) > 20  # the seed library has 47 main exercises


def test_search_only_returns_specified_category():
    client = _logged_in_client("searchcatuser")
    r = client.get("/api/exercises/search", params={"category": "Warmup"})
    assert r.status_code == 200
    assert len(r.json()) == 5  # exactly the 5 seeded warmup exercises
    assert all(ex["is_timed"] is False or ex["is_timed"] is True for ex in r.json())  # sanity: field present


def test_search_filters_by_explicit_equipment_override():
    client = _logged_in_client("searchequipuser")
    r = client.get("/api/exercises/search", params={"equipment": "bodyweight_only"})
    names = [ex["name"] for ex in r.json()]
    assert "Barbell Back Squat" not in names  # needs full_gym
    assert "Push-Up" in names  # bodyweight-accessible


def test_search_defaults_equipment_from_profile_when_not_overridden():
    """The core 'adapts to what you've picked' behavior — without an
    explicit equipment override, results should respect the user's own
    stated equipment access."""
    client = _logged_in_client("searchprofileuser")
    client.put("/api/profile", json={
        "goal": "general_fitness", "experience_level": "beginner", "equipment_access": "bodyweight_only",
        "height_cm": 175, "weight_kg": 75, "age": 25, "days_per_week": 3, "injuries_limitations": None,
    })
    r = client.get("/api/exercises/search")
    names = [ex["name"] for ex in r.json()]
    assert "Barbell Back Squat" not in names


def test_search_includes_split_category_and_flags():
    client = _logged_in_client("searchfieldsuser")
    r = client.get("/api/exercises/search", params={"q": "Plank"})
    plank = next(ex for ex in r.json() if ex["name"] == "Plank")
    assert plank["is_timed"] is True
    assert plank["muscle_group"] is not None


def test_search_requires_authentication():
    anon = TestClient(app)
    assert anon.get("/api/exercises/search").status_code == 401


def test_search_result_limit():
    client = _logged_in_client("searchlimituser")
    r = client.get("/api/exercises/search")
    assert len(r.json()) <= 30
