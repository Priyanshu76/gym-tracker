import re

from fastapi.testclient import TestClient

from app.main import app


def _find_ordering_bugs(html: str) -> list[str]:
    """
    Returns element IDs referenced by a TOP-LEVEL (unindented) statement like
    `const x = document.getElementById('foo');` where the ID only exists in
    the static HTML after the <script> tag opens. Top-level statements run
    immediately as the script is parsed — before the browser has read any
    HTML that appears later in the source — so this is the actual bug
    pattern from the real production incident.

    Deliberately does NOT flag getElementById calls inside function bodies
    (indented lines): those run later, typically after some earlier code in
    the same script has already rendered dynamic content via .innerHTML —
    a normal, safe pattern used throughout this app (e.g. renderTable()
    building the log table, then binding buttons within it).
    """
    script_start = html.index("<script>")
    html_before_script = html[:script_start]
    script_body = html[script_start:]

    top_level_ids = re.findall(
        r"^const \w+ = document\.getElementById\('([\w-]+)'\)",
        script_body, re.MULTILINE,
    )
    return [eid for eid in set(top_level_ids) if f'id="{eid}"' not in html_before_script]


def test_workout_logs_modal_elements_exist_before_script_runs():
    """
    Regression test for a real production bug: the confirm/edit modal <div>s
    were placed AFTER the <script> tag in the HTML source. Since the script
    has no defer/DOMContentLoaded wrapper, it ran document.getElementById()
    on those IDs immediately — before the browser had parsed them into the
    DOM yet — throwing 'Cannot read properties of null' on page load.

    This can't be caught by TestClient alone (no real browser/DOM here), but
    a plain source-order check catches this exact bug class cheaply.
    """
    client = TestClient(app)
    html = client.get("/logs").text
    bugs = _find_ordering_bugs(html)
    assert not bugs, (
        f"These element IDs are queried by the script but only exist in the "
        f"HTML after the <script> tag — getElementById will return null for "
        f"them on page load: {bugs}"
    )


def test_log_page_modal_elements_exist_before_script_runs():
    """Same check on the main log page, which already had this correctly
    ordered — confirms it stays that way."""
    client = TestClient(app)
    html = client.get("/").text
    bugs = _find_ordering_bugs(html)
    assert not bugs, f"IDs queried before they exist in the DOM: {bugs}"
