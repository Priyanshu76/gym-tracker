from fastapi.testclient import TestClient

from app.main import app


def test_theme_js_is_served():
    client = TestClient(app)
    r = client.get("/static/js/theme.js")
    assert r.status_code == 200
    assert "function applyTheme(" in r.text
    assert "ACCENT_COLORS" in r.text
    assert len([1 for _ in r.text.split("id:") if True]) - 1 >= 8  # sanity: 8 accent color entries


def test_all_pages_include_theme_system():
    client = TestClient(app)
    for path in ["/", "/signup", "/reset-password", "/dashboard", "/logs", "/onboarding", "/profile", "/plans", "/admin"]:
        r = client.get(path)
        assert r.status_code == 200
        assert "/static/js/theme.js" in r.text, f"{path} does not include the theme system"


def test_all_pages_have_light_theme_and_accent_css_overrides():
    client = TestClient(app)
    for path in ["/", "/signup", "/reset-password", "/dashboard", "/logs", "/onboarding", "/profile", "/plans", "/admin", "/this-404-page-does-not-exist"]:
        r = client.get(path)
        assert '[data-theme="light"]' in r.text, f"{path} missing light theme override"
        assert '[data-accent="blue"]' in r.text, f"{path} missing accent color overrides"


def test_profile_page_includes_appearance_settings():
    client = TestClient(app)
    r = client.get("/profile")
    assert 'id="appearance-section"' in r.text
    assert 'id="accent-swatches"' in r.text
    assert "initAppearanceControls" in r.text


def test_dashboard_charts_use_resolved_theme_colors_not_raw_css_vars():
    """Regression guard for a real bug: Chart.js/Canvas rendering cannot
    resolve CSS custom properties — passing 'var(--accent)' directly as a
    chart color silently fails or draws an unexpected default, since canvas
    fillStyle/strokeStyle strings are not part of the CSS cascade. Every
    chart color must come from getResolvedThemeColors() instead."""
    client = TestClient(app)
    r = client.get("/dashboard")
    # the app script must call the resolver; it must NOT still assign a
    # bare var(--...) string directly to a Chart.js color property
    assert "getResolvedThemeColors()" in r.text
    assert "borderColor: 'var(--accent)'" not in r.text
    assert "borderColor: 'var(--steel)'" not in r.text
    assert "pointBackgroundColor: pointColors" not in r.text or "'var(--green)'" not in r.text
