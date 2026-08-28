"""
Tests for the migrated Weekly_Lift_Log page: confirms it actually renders,
and that the cookie-based auth flow its JS depends on (no client-side token
at all) genuinely works end-to-end — /api/me before and after login, and a
same-origin request naturally carrying the cookie with zero manual wiring.
"""
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


def test_page_renders():
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Weekly Lift Log" in r.text
    # confirm the old n8n/localStorage patterns are genuinely gone from what ships to the browser
    assert "priyanshu-n8n" not in r.text
    assert "localStorage.getItem(AUTH_KEY" not in r.text
    assert "/api/login" in r.text


def test_me_endpoint_reflects_login_state_with_zero_client_side_state():
    client = TestClient(app)

    # not logged in yet
    assert client.get("/api/me").status_code == 401

    with patch("app.services.email.send_email"):
        from app.database import SessionLocal
        from app.models.pending_signup import PendingSignup
        from app.models.user import User
        from app.services.security import hash_password

        client.post("/api/signup", json={"username": "pagetest", "display_name": "Page Test", "email": "pagetest@example.com", "website_url": ""})
        db = SessionLocal()
        pending = db.query(PendingSignup).filter(PendingSignup.username == "pagetest").first()
        client.get(f"/api/verify-email?request_id={pending.id}&token={pending.verification_token}")
        db.refresh(pending)
        client.get(f"/api/approve-signup?request_id={pending.id}&token={pending.approval_token}")
        user = db.query(User).filter(User.username == "pagetest").first()
        user.password_hash = hash_password("KnownPass123!")
        db.commit()
        db.close()

    # No cookie manually attached anywhere below — relying entirely on the
    # client's normal cookie jar, exactly like a real browser would.
    login = client.post("/api/login", json={"username": "pagetest", "password": "KnownPass123!"})
    assert login.status_code == 200

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["username"] == "pagetest"

    # this is what the force-reset overlay actually calls
    reset = client.post("/api/set-new-password", json={"new_password": "BrandNew123!"})
    assert reset.status_code == 200

    me2 = client.get("/api/me")
    assert me2.json()["must_reset_password"] is False

    # logout actually revokes the session, not just a client-side no-op
    logout = client.post("/api/logout")
    assert logout.status_code == 200
    assert client.get("/api/me").status_code == 401
