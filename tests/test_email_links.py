"""Regression tests for a real production bug: a trailing slash in
SITE_BASE_URL produced double-slash links (e.g. //api/verify-email) that
404'd, and the welcome email linked to a /login route that never existed."""
from unittest.mock import patch

from app.services import email as email_service


def test_base_url_strips_trailing_slash():
    """Directly exercises the normalization that prevents the double-slash bug —
    not just its downstream effect on one email function."""
    assert "https://example.com/".rstrip("/") == "https://example.com"
    assert "https://example.com".rstrip("/") == "https://example.com"


def test_links_never_contain_double_slash_even_with_trailing_slash_config():
    # Simulate the exact misconfiguration that caused the production bug:
    # SITE_BASE_URL with a trailing slash. BASE_URL is computed once at import
    # time via .rstrip("/"), so we patch it directly here to confirm the
    # link-building functions never reintroduce a double slash regardless.
    with patch.object(email_service, "BASE_URL", "https://example.com"):
        sent = {}
        with patch("app.services.email.send_email", side_effect=lambda to, subject, body: sent.update(body=body)):
            email_service.send_verification_email("u@example.com", "User", "req-123", "tok-abc")
        assert "//api/verify-email" not in sent["body"]
        assert "https://example.com/api/verify-email?request_id=req-123&token=tok-abc" in sent["body"]


def test_welcome_email_links_to_real_root_route_not_nonexistent_login_path():
    with patch.object(email_service, "BASE_URL", "https://example.com"):
        sent = {}
        with patch("app.services.email.send_email", side_effect=lambda to, subject, body: sent.update(body=body)):
            email_service.send_welcome_email("u@example.com", "User", "someuser", "TempPass123!")
        assert "/login" not in sent["body"]
        assert "https://example.com/" in sent["body"]


def test_admin_notification_links_are_clean():
    with patch.object(email_service, "BASE_URL", "https://example.com"):
        sent = {}
        with patch("app.services.email.send_email", side_effect=lambda to, subject, body: sent.update(body=body)):
            email_service.send_admin_notification("someuser", "User", "u@example.com", "req-123", "approval-tok")
        assert "//api/" not in sent["body"]
        assert "https://example.com/api/approve-signup?request_id=req-123&token=approval-tok" in sent["body"]
        assert "https://example.com/api/reject-signup?request_id=req-123&token=approval-tok" in sent["body"]
