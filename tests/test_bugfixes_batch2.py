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


def test_unknown_page_route_returns_styled_html_not_raw_json():
    client = TestClient(app)
    r = client.get("/this-page-does-not-exist")
    assert r.status_code == 404
    assert "text/html" in r.headers["content-type"]
    assert "Page not found" in r.text
    assert '"detail"' not in r.text  # not the raw FastAPI JSON shape


def test_unknown_api_route_still_returns_json():
    """API clients need JSON, not a styled HTML page — this must not regress."""
    client = TestClient(app)
    r = client.get("/api/this-does-not-exist")
    assert r.status_code == 404
    assert "application/json" in r.headers["content-type"]
    assert r.json()["detail"]


def test_real_404_from_a_valid_route_pattern_still_works():
    """Confirms the custom handler doesn't swallow legitimate 404s from
    real endpoints (e.g. deleting an already-deleted log entry)."""
    client = TestClient(app)
    with patch("app.services.email.send_email"):
        from app.models.pending_signup import PendingSignup
        from app.models.user import User
        from app.services.security import hash_password
        client.post("/api/signup", json={"username": "notfounduser", "display_name": "N", "email": "n@example.com", "website_url": ""})
        db = SessionLocal()
        pending = db.query(PendingSignup).filter(PendingSignup.username == "notfounduser").first()
        client.get(f"/api/verify-email?request_id={pending.id}&token={pending.verification_token}")
        db.refresh(pending)
        client.get(f"/api/approve-signup?request_id={pending.id}&token={pending.approval_token}")
        user = db.query(User).filter(User.username == "notfounduser").first()
        user.password_hash = hash_password("KnownPass123!")
        db.commit()
        db.close()
    client.post("/api/login", json={"username": "notfounduser", "password": "KnownPass123!"})

    fake_id = "00000000-0000-0000-0000-000000000000"
    r = client.delete(f"/api/workout-logs/{fake_id}")
    assert r.status_code == 404
    assert "application/json" in r.headers["content-type"]


def test_profile_page_has_a_back_link_element():
    client = TestClient(app)
    r = client.get("/profile")
    assert r.status_code == 200
    assert 'id="back-link"' in r.text


def test_log_page_has_editable_date_picker():
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="log-date-picker"' in r.text
    assert "LOG_DATE" in r.text


def test_auth_links_say_request_access_not_sign_up():
    client = TestClient(app)
    for path in ["/", "/dashboard", "/logs"]:
        r = client.get(path)
        assert ">Sign up<" not in r.text, f"{path} still says 'Sign up'"
        assert "Request access" in r.text
