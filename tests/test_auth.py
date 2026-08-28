"""
Full auth lifecycle test: signup -> honeypot/duplicate rejection -> email
verification -> admin approval -> forced password reset -> forgot/reset
password -> session revocation on password change.

Runs against a real Postgres database (see DATABASE_URL in .env / CI env) —
this is intentional. Sqlite-in-memory would hide real constraint/type issues
that only show up against Postgres, which is exactly the class of bug we're
trying to catch before it reaches production.
"""
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    """Wipe and recreate all tables before every test for isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def sent_emails():
    captured = []

    def capture(to, subject, body):
        captured.append({"to": to, "subject": subject, "body": body})

    with patch("app.services.email.send_email", side_effect=capture):
        yield captured


def find_email(sent_emails, subject_contains: str) -> dict:
    return next(e for e in sent_emails if subject_contains in e["subject"])


def test_full_auth_lifecycle(sent_emails):
    client = TestClient(app)

    # --- signup ---
    r = client.post(
        "/api/signup",
        json={"username": "priyanshu", "display_name": "Priyanshu", "email": "priyanshu@example.com", "website_url": ""},
    )
    assert r.status_code == 200

    # --- honeypot: identical response, no email sent ---
    r2 = client.post(
        "/api/signup",
        json={"username": "bot", "display_name": "Bot", "email": "bot@example.com", "website_url": "http://spam.com"},
    )
    assert r2.json() == r.json()

    # --- duplicate in-flight username is blocked ---
    r3 = client.post(
        "/api/signup",
        json={"username": "priyanshu", "display_name": "X", "email": "x@example.com", "website_url": ""},
    )
    assert r3.status_code == 409
    assert len(sent_emails) == 1, "honeypot and duplicate signups must never trigger an email"

    # --- email verification ---
    m = re.search(r"request_id=([a-f0-9-]+)&token=([a-f0-9]+)", find_email(sent_emails, "Verify your email")["body"])
    request_id, verify_token = m.groups()
    assert client.get(f"/api/verify-email?request_id={request_id}&token={verify_token}").status_code == 200
    assert client.get(f"/api/verify-email?request_id={request_id}&token={verify_token}").status_code == 400

    # --- admin approval ---
    m2 = re.search(
        r"approve-signup\?request_id=([a-f0-9-]+)&token=([a-f0-9]+)", find_email(sent_emails, "New signup request")["body"]
    )
    approve_id, approve_token = m2.groups()
    assert client.get(f"/api/approve-signup?request_id={approve_id}&token={approve_token}").status_code == 200
    assert client.get(f"/api/approve-signup?request_id={approve_id}&token={approve_token}").status_code == 400

    temp_password = re.search(r"Temporary password: (\S+)", find_email(sent_emails, "account is ready")["body"]).group(1)

    # --- login with temp password forces a reset ---
    r7 = client.post("/api/login", json={"username": "priyanshu", "password": temp_password})
    assert r7.status_code == 200
    assert r7.json()["must_reset_password"] is True

    assert client.post("/api/login", json={"username": "priyanshu", "password": "wrong"}).status_code == 401
    assert client.post("/api/login", json={"username": "nosuchuser", "password": "x"}).status_code == 401

    # --- protected endpoint genuinely requires a session ---
    anon_client = TestClient(app)
    assert anon_client.post("/api/set-new-password", json={"new_password": "X12345678!"}).status_code == 401

    # --- forced password reset via the temp-login session ---
    r10 = client.post("/api/set-new-password", json={"new_password": "MyRealPassword123!"})
    assert r10.status_code == 200

    r11 = client.post("/api/login", json={"username": "priyanshu", "password": "MyRealPassword123!"})
    assert r11.status_code == 200
    assert r11.json()["must_reset_password"] is False
    old_session_token = r11.cookies.get("access_token")

    # --- forgot password never reveals whether a username exists ---
    r12 = client.post("/api/forgot-password", json={"username": "priyanshu"})
    r13 = client.post("/api/forgot-password", json={"username": "nosuchuser"})
    assert r12.json()["message"] == r13.json()["message"]

    m4 = re.search(r"username=(\w+)&token=([a-f0-9]+)", find_email(sent_emails, "Reset your Gym Tracker password")["body"])
    reset_username, reset_token = m4.groups()
    r14 = client.post(
        "/api/reset-password",
        json={"username": reset_username, "token": reset_token, "new_password": "AnotherNewPass456!"},
    )
    assert r14.status_code == 200

    # --- password reset revokes prior sessions ---
    stale_client = TestClient(app)
    stale_client.cookies.set("access_token", old_session_token)
    assert stale_client.post("/api/set-new-password", json={"new_password": "ShouldFail123!"}).status_code == 401

    assert client.post("/api/login", json={"username": "priyanshu", "password": "AnotherNewPass456!"}).status_code == 200
    assert client.post(
        "/api/reset-password", json={"username": "priyanshu", "token": "wrong", "new_password": "X12345678!"}
    ).status_code == 400
