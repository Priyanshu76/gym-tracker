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
