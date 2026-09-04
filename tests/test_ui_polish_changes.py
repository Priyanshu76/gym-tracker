from fastapi.testclient import TestClient

from app.main import app


def test_tips_section_removed_from_log_page():
    client = TestClient(app)
    r = client.get("/")
    assert "tips-fab" not in r.text
    assert "renderTips" not in r.text
    assert "Guidelines" not in r.text
    assert "const TIPS" not in r.text


def test_weight_logging_moved_to_log_page():
    client = TestClient(app)
    r = client.get("/")
    assert 'id="bw-quick-input"' in r.text
    assert 'id="bw-quick-btn"' in r.text
    assert "/api/body-metrics" in r.text


def test_weight_logging_form_removed_from_dashboard():
    """The dashboard should keep the chart but no longer have the
    logging input/button — that moved to the Log screen."""
    client = TestClient(app)
    r = client.get("/dashboard")
    assert 'id="bw-input"' not in r.text
    assert 'id="bw-log-btn"' not in r.text
    assert 'id="bwChart"' in r.text  # the chart itself must still be there


def test_log_button_has_popping_style():
    client = TestClient(app)
    r = client.get("/")
    assert "box-shadow:0 4px 0 0" in r.text
    assert ".log-btn:active" in r.text
