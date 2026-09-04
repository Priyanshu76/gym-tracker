from fastapi.testclient import TestClient

from app.main import app


def test_log_page_has_app_shell_top_bar():
    client = TestClient(app)
    r = client.get("/")
    assert 'class="app-topbar"' in r.text
    assert "Gym Tracker" in r.text
    assert 'id="profile-icon-btn"' in r.text


def test_log_page_has_bottom_tab_bar():
    client = TestClient(app)
    r = client.get("/")
    assert 'class="app-tabbar"' in r.text
    for href in ['href="/"', 'href="/dashboard"', 'href="/plans"', 'href="/logs"']:
        assert href in r.text


def test_log_page_no_longer_has_dangling_logout_button():
    """Regression guard: logout moved to the profile page — the main page
    must not reference a logout-btn element that no longer exists in its
    own markup (which would throw on getElementById(...).style access)."""
    client = TestClient(app)
    r = client.get("/")
    assert 'id="logout-btn"' not in r.text


def test_log_page_admin_icon_hidden_by_default():
    client = TestClient(app)
    r = client.get("/")
    assert 'id="admin-nav-link"' in r.text
    assert 'style="display:none;"' in r.text


def test_dashboard_has_app_shell():
    client = TestClient(app)
    r = client.get("/dashboard")
    assert 'class="app-topbar"' in r.text
    assert 'class="app-tabbar"' in r.text
    assert 'href="/dashboard" class="app-tab active"' in r.text
    assert 'id="logout-btn"' not in r.text


def test_logs_page_has_app_shell():
    client = TestClient(app)
    r = client.get("/logs")
    assert 'class="app-topbar"' in r.text
    assert 'class="app-tabbar"' in r.text
    assert 'href="/logs" class="app-tab active"' in r.text
    assert 'id="logout-btn"' not in r.text


def test_plans_page_has_app_shell():
    client = TestClient(app)
    r = client.get("/plans")
    assert 'class="app-topbar"' in r.text
    assert 'class="app-tabbar"' in r.text
    assert 'href="/plans" class="app-tab active"' in r.text


def test_profile_page_has_logout_button():
    """Logout was removed from every other page on the assumption it'd
    live on the profile page instead — confirms it actually does."""
    client = TestClient(app)
    r = client.get("/profile")
    assert 'id="logout-btn"' in r.text
    assert "/api/logout" in r.text


def test_only_one_page_has_the_logout_button():
    """The whole point of moving logout to one place — every other page
    must not have re-introduced it."""
    client = TestClient(app)
    for path in ["/", "/dashboard", "/logs", "/plans"]:
        r = client.get(path)
        assert 'id="logout-btn"' not in r.text, f"{path} should not have its own logout button"
