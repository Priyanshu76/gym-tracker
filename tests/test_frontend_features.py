from fastapi.testclient import TestClient

from app.main import app


def test_log_page_includes_rpe_input():
    client = TestClient(app)
    r = client.get("/")
    assert "rpe-input" in r.text
    assert "rpe:" in r.text  # payload field


def test_log_page_includes_last_time_reference():
    client = TestClient(app)
    r = client.get("/")
    assert "loadLastTime" in r.text
    assert "/api/workout-logs/last" in r.text
    assert "Use these numbers" in r.text


def test_log_page_includes_rest_timer():
    client = TestClient(app)
    r = client.get("/")
    assert "startRestTimer" in r.text
    assert "rest-timer" in r.text


def test_log_page_has_enter_key_ergonomics():
    client = TestClient(app)
    r = client.get("/")
    assert "keydown" in r.text
    assert "nextRow" in r.text


def test_workout_logs_page_has_export_button():
    client = TestClient(app)
    r = client.get("/logs")
    assert 'id="export-btn"' in r.text
    assert "/api/workout-logs/export" in r.text


def test_log_page_ties_guidelines_to_users_goal():
    """Regression guard: renderTipsForGoal existed but was never called by
    renderTips() in an earlier version of this feature — confirms the wiring
    is actually complete, not just that the helper function exists."""
    client = TestClient(app)
    r = client.get("/")
    assert "renderTipsForGoal(USER_GOAL)" in r.text
    assert "TIPS.map(t=>" not in r.text  # the old unfiltered direct usage must be gone


def test_dashboard_normalizes_muscle_group_taxonomy():
    client = TestClient(app)
    r = client.get("/dashboard")
    assert "normalizeMuscleGroup" in r.text
