"""Smoke test of the Streamlit demo, headless and offline (saved results only, no API calls)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")  # newer Streamlit resolves relative paths from here

DEMO_NOTE = "Live checks are disabled in the public demo; saved runs are shown."


def run_app(choice: str, monkeypatch, key: str | None = None) -> AppTest:
    if key:
        monkeypatch.setenv("GEMINI_API_KEY", key)    # live mode; nothing here clicks a button, so no API call
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.selectbox[0].select(choice).run()
    assert not at.exception
    return at


def test_saved_run_is_shown_highlighted_with_live_button_when_key_set(monkeypatch):
    at = run_app("report_02 · Analyst B", monkeypatch, key="test-key")
    assert any("Saved run" in i.value for i in at.info)
    assert any("claims flagged" in e.value for e in at.error)
    assert any('class="rc-claim rc-red"' in m.value for m in at.markdown)
    assert [b.label for b in at.button] == ["Run live check"]


def test_paste_my_own_requires_live_run(monkeypatch):
    at = run_app("Paste my own", monkeypatch, key="test-key")
    assert [b.label for b in at.button] == ["Run check"]
    assert not any("Saved run" in i.value for i in at.info)


@pytest.mark.parametrize("choice", ["report_02 · Analyst B", "Paste my own"])
def test_public_demo_without_key_hides_live_checks(monkeypatch, choice):
    at = run_app(choice, monkeypatch)
    assert at.button == [] or all(b.label not in ("Run live check", "Run check") for b in at.button)
    assert any(i.value == DEMO_NOTE for i in at.info)
    if choice.startswith("report_02"):
        assert any("Saved run" in i.value for i in at.info)               # saved runs still shown


def test_benchmark_tab_shows_metrics_chart_and_history(monkeypatch):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert {"Recall", "Precision", "False alarms", "Cascade errors caught"} <= set(labels)
    assert any(s.value == "History across runs" for s in at.subheader)
