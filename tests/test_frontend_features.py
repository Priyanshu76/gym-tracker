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


def test_guidelines_tips_feature_intentionally_removed():
    """The Guidelines/Tips drawer was explicitly removed from the Log
    screen per user request — confirms it stays gone, not that it exists."""
    client = TestClient(app)
    r = client.get("/")
    assert "renderTipsForGoal" not in r.text
    assert "tips-fab" not in r.text


def test_log_page_includes_progression_wiring():
    client = TestClient(app)
    r = client.get("/")
    assert "formatProgressionReps" in r.text
    assert "evaluate-progression" in r.text
    assert "planExerciseId" in r.text
    assert "progression-note" in r.text


def test_log_page_includes_pr_celebration():
    client = TestClient(app)
    r = client.get("/")
    assert "prHit" in r.text
    assert "is_pr" in r.text
    assert "New weight PR" in r.text


def test_log_page_includes_superset_wiring():
    client = TestClient(app)
    r = client.get("/")
    assert "supersetGroupId" in r.text
    assert "pair-superset" in r.text
    assert "unpair-superset" in r.text
    assert "DAY_SUPERSET_PROGRESS" in r.text


def test_log_page_includes_timed_and_unilateral_wiring():
    client = TestClient(app)
    r = client.get("/")
    assert "isTimed" in r.text
    assert "isUnilateral" in r.text
    assert "work-timer-btn" in r.text
    assert "duration_seconds" in r.text
    assert "per-side-hint" in r.text


def test_log_page_includes_wake_lock():
    client = TestClient(app)
    r = client.get("/")
    assert "wakeLock" in r.text


def test_log_page_includes_exercise_library_search():
    client = TestClient(app)
    r = client.get("/")
    assert "/api/exercises/search" in r.text
    assert "exercise-datalist" in r.text


def test_profile_page_includes_export_button():
    client = TestClient(app)
    r = client.get("/profile")
    assert 'id="export-data-btn"' in r.text
    assert "/api/export/full" in r.text


def test_plans_page_includes_import_ui():
    client = TestClient(app)
    r = client.get("/plans")
    assert 'id="import-file-input"' in r.text
    assert "/api/export/plans/import" in r.text


def test_dashboard_normalizes_muscle_group_taxonomy():
    client = TestClient(app)
    r = client.get("/dashboard")
    assert "normalizeMuscleGroup" in r.text


def test_dashboard_includes_body_weight_chart_but_not_logging_form():
    """Weight LOGGING moved to the Log screen per user request — the
    dashboard keeps only the trend chart, not the input/button."""
    client = TestClient(app)
    r = client.get("/dashboard")
    assert "bwChart" in r.text
    assert "GOAL_WEIGHT_KG" in r.text
    assert "bw-log-btn" not in r.text


def test_dashboard_includes_muscle_map():
    client = TestClient(app)
    r = client.get("/dashboard")
    assert "renderMuscleMapSVG" in r.text
    assert "toMuscleMapRegions" in r.text
    assert "muscle-map-figure" in r.text
