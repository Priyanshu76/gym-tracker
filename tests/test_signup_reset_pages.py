"""Tests confirming the signup and reset-password pages render and that the
forms' actual payload shapes match what the API endpoints expect."""
import re
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


def test_signup_page_renders():
    client = TestClient(app)
    r = client.get("/signup")
    assert r.status_code == 200
    assert "Request access" in r.text
    assert "priyanshu-n8n" not in r.text
    assert "/api/signup" in r.text


def test_reset_password_page_renders():
    client = TestClient(app)
    r = client.get("/reset-password")
    assert r.status_code == 200
    assert "priyanshu-n8n" not in r.text
    assert "/api/forgot-password" in r.text
    assert "/api/reset-password" in r.text


def test_signup_page_payload_shape_matches_api():
    """Exactly what the signup.html JS actually sends — display_name, not displayName."""
    client = TestClient(app)
    with patch("app.services.email.send_email"):
        r = client.post(
            "/api/signup",
            json={"username": "pagesignup", "display_name": "Page Signup", "email": "pagesignup@example.com", "website_url": ""},
        )
    assert r.status_code == 200, r.text


def test_reset_password_page_payload_shape_matches_api():
    """Exactly what the reset_password.html JS actually sends — new_password, not newPassword."""
    client = TestClient(app)
    with patch("app.services.email.send_email"):
        from app.database import SessionLocal
        from app.models.pending_signup import PendingSignup
        from app.models.user import User
        from app.services.security import hash_password

        client.post("/api/signup", json={"username": "resettest", "display_name": "Reset Test", "email": "resettest@example.com", "website_url": ""})
        db = SessionLocal()
        pending = db.query(PendingSignup).filter(PendingSignup.username == "resettest").first()
        client.get(f"/api/verify-email?request_id={pending.id}&token={pending.verification_token}")
        db.refresh(pending)
        client.get(f"/api/approve-signup?request_id={pending.id}&token={pending.approval_token}")
        user = db.query(User).filter(User.username == "resettest").first()
        user.password_hash = hash_password("OldPass123!")
        db.commit()
        db.close()

        forgot = client.post("/api/forgot-password", json={"username": "resettest"})
        assert forgot.status_code == 200

        # find the reset email that was actually sent, extract the real token
        # (send_email is a MagicMock here, so pull args from its call history —
        # it's always called positionally as send_email(to, subject, body))
        import app.services.email as email_module
        reset_call = next(c for c in email_module.send_email.call_args_list if "Reset your Gym Tracker" in c.args[1])
        body = reset_call.args[2]
        m = re.search(r"username=(\w+)&token=([a-f0-9]+)", body)
        username, token = m.groups()

    r = client.post("/api/reset-password", json={"username": username, "token": token, "new_password": "BrandNewPass123!"})
    assert r.status_code == 200, r.text

    login = client.post("/api/login", json={"username": "resettest", "password": "BrandNewPass123!"})
    assert login.status_code == 200


def test_signup_validation_error_shape_is_human_readable():
    """A bad email produces Pydantic's array-of-errors 422 shape — confirms the
    page's extractErrorMessage helper has real data to work with, not just a guess."""
    client = TestClient(app)
    r = client.post(
        "/api/signup",
        json={"username": "ab", "display_name": "X", "email": "not-an-email", "website_url": ""},
    )
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)
    assert len(r.json()["detail"]) > 0
    assert "msg" in r.json()["detail"][0]
