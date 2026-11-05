"""Smoke test of the Streamlit demo, headless and offline (saved results only, no API calls)."""
from streamlit.testing.v1 import AppTest


def run_app(choice: str) -> AppTest:
    at = AppTest.from_file("app.py", default_timeout=30).run()
    at.selectbox[0].select(choice).run()
    assert not at.exception
    return at


def test_saved_run_is_shown_highlighted():
    at = run_app("report_02 · Analyst B")
    assert any("Saved run" in i.value for i in at.info)
    assert any("claims flagged" in e.value for e in at.error)
    assert any('class="rc-claim rc-red"' in m.value for m in at.markdown)
    assert [b.label for b in at.button] == ["Run live check"]


def test_paste_my_own_requires_live_run():
    at = run_app("Paste my own")
    assert [b.label for b in at.button] == ["Run check"]
    assert not any("Saved run" in i.value for i in at.info)
