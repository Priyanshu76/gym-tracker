from fastapi.testclient import TestClient

from app.main import app


def test_icons_js_is_served():
    client = TestClient(app)
    r = client.get("/static/js/icons.js")
    assert r.status_code == 200
    assert "function icon(" in r.text
    assert "function applyStandardIcons(" in r.text


def test_all_pages_include_icon_library():
    client = TestClient(app)
    for path in ["/", "/signup", "/reset-password", "/dashboard", "/logs", "/onboarding", "/profile", "/plans"]:
        r = client.get(path)
        assert r.status_code == 200
        assert "/static/js/icons.js" in r.text, f"{path} does not include the icon library"


def test_no_page_still_references_the_old_yellow_accent():
    """Regression guard for the palette refresh — if a future edit
    accidentally reintroduces the old hardcoded hex or variable name, this
    catches it immediately instead of shipping an inconsistent page."""
    client = TestClient(app)
    for path in ["/", "/signup", "/reset-password", "/dashboard", "/logs", "/onboarding", "/profile", "/plans"]:
        r = client.get(path)
        assert "#e8b23c" not in r.text, f"{path} still has the old accent hex hardcoded"
        assert "--yellow" not in r.text, f"{path} still references the old --yellow variable"


def test_exercise_cards_render_with_an_icon():
    """Confirms the actual shipped page wires guessIconCategory into the
    exercise card markup, not just that the standalone helper exists."""
    client = TestClient(app)
    r = client.get("/")
    assert "guessIconCategory" in r.text
    assert "ex-icon" in r.text
