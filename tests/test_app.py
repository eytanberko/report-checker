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
    assert [b.label for b in at.button if b.key != "own_run"] == ["Run live check"]


def test_paste_my_own_requires_live_run(monkeypatch):
    at = run_app("Paste my own", monkeypatch, key="test-key")
    assert [b.label for b in at.button if b.key != "own_run"] == ["Run check"]
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


def own_tab(monkeypatch, key: str | None = None, example: str = "cafes") -> AppTest:
    """'Try your own' with an example filled in (AppTest cannot upload files; uploads: test_dataset.py)."""
    if key:
        monkeypatch.setenv("GEMINI_API_KEY", key)
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.toggle(key=f"own_{example}").set_value(True).run()
    assert not at.exception
    return at


def test_try_your_own_shows_the_schema_built_from_the_csv_and_is_off_in_the_public_demo(monkeypatch):
    at = own_tab(monkeypatch)
    assert any("Table `cafes` (8 rows" in c.value for c in at.code)
    assert any("Run the app locally" in i.value for i in at.info)
    assert all(b.key != "own_run" for b in at.button)


def test_try_your_own_runs_the_cafe_example(monkeypatch):
    """Replays the live run of examples/cafes from the committed cache: same highlighted result and memo."""
    from checker import llm
    monkeypatch.setattr(llm, "OFFLINE", True)
    at = own_tab(monkeypatch, key="test-key")
    at.button(key="own_run").click().run()
    assert not at.exception and not [e.value for e in at.error if "failed" in e.value]
    assert any(s.value == "Live run" for s in at.success)
    assert any("claims flagged" in e.value for e in at.error)
    report = next(m.value for m in at.markdown if "rc-claim" in m.value and "Haifa sold" in m.value)
    assert report.count('class="rc-claim rc-red"') == 2         # the 25% growth and the 1,480 revenue
    assert any(d.label == "Download review memo (.md)" for d in at.get("download_button"))


@pytest.mark.parametrize("error,shown", [
    ("QuotaExhausted", "The API quota for today is used up."),
    ("Overloaded", "The AI service is busy right now (503)"),
])
def test_try_your_own_explains_quota_and_overload(monkeypatch, error, shown):
    from checker import core, llm

    def fail(*args, **kwargs):
        raise getattr(llm, error)("from the test")
    monkeypatch.setattr(core, "check_report", fail)
    at = own_tab(monkeypatch, key="test-key")
    at.button(key="own_run").click().run()
    assert not at.exception
    assert any(shown in e.value for e in at.error)
    assert not any(s.value == "Live run" for s in at.success)
    at.button(key="saved_own").click().run()                    # the fallback: a saved run of the same example
    assert not at.exception
    assert any(i.value.startswith("Saved example: the cafes example") for i in at.info)
    assert any('class="rc-claim rc-red"' in m.value and "Haifa sold" in m.value for m in at.markdown)


def test_energy_example_is_a_correct_report_and_runs_clean(monkeypatch):
    """Replays the one live run of examples/energy from the cache: every claim checks out, every requirement met."""
    from checker import llm
    monkeypatch.setattr(llm, "OFFLINE", True)
    at = own_tab(monkeypatch, key="test-key", example="energy")
    assert any("Table `energy`" in c.value for c in at.code)            # the hand-written energy schema
    at.button(key="own_run").click().run()
    assert not at.exception
    assert any(s.value == "**0 of 12 claims flagged, 0 requirements not covered**" for s in at.success)


def test_one_example_at_a_time_and_reset_puts_the_text_back(monkeypatch):
    at = own_tab(monkeypatch, key="test-key", example="cafes")
    at.toggle(key="own_energy").set_value(True).run()
    assert at.toggle(key="own_energy").value and not at.toggle(key="own_cafes").value
    original = at.text_area(key="own_report_energy").value
    at.text_area(key="own_report_energy").set_value(original.replace("16.9%", "19.6%")).run()
    assert "19.6%" in at.text_area(key="own_report_energy").value
    at.button(key="own_reset").click().run()
    assert not at.exception and at.text_area(key="own_report_energy").value == original


def test_failed_live_check_in_the_first_tab_offers_a_saved_example(monkeypatch):
    from checker import core, llm

    def fail(*args, **kwargs):
        raise llm.QuotaExhausted("from the test")
    monkeypatch.setattr(core, "check_report", fail)
    at = run_app("Paste my own", monkeypatch, key="test-key")
    at.text_area(key="text_Paste my own").set_value("Israel's renewables share was 16.9% in 2025.").run()
    at.button[0].click().run()
    assert any("The API quota for today is used up." in e.value for e in at.error)
    at.button(key="saved_check").click().run()
    assert any(i.value.startswith("Saved example: the energy example") for i in at.info)


@pytest.mark.parametrize("example,stem", [("cafes", "cafes"), ("energy", "energy")])
def test_examples_offer_their_data_report_and_requirements_as_downloads(monkeypatch, example, stem):
    at = own_tab(monkeypatch, example=example)
    labels = [d.label for d in at.get("download_button")][-4:]            # after the first tab's memo button
    assert labels == ["Download data (Excel)", "CSV", "Report (.txt)", "Requirements (.txt)"]
    assert not any(stem + ".csv`" in c.value for c in at.caption)          # the plain path is gone
