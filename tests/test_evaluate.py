"""Benchmark tooling: resume after a quota stop, offline re-scoring, stale results, history log."""
import csv
import json

import pytest

import evaluate
from checker import llm


class FakeLLM:
    """Answers like the LLM (no claims, all requirements covered); can run out of quota after N calls."""

    def __init__(self, quota=None):
        self.calls, self.quota = 0, quota

    def __call__(self, prompt):
        if self.quota is not None and self.calls >= self.quota:
            raise llm.QuotaExhausted("Daily free-tier quota is used up.")
        self.calls += 1
        if "Split the REPORT" in prompt:
            return {"claims": []}
        return {"judgments": [], "requirements": [{"id": f"R{i}", "status": "covered"} for i in range(1, 6)]}


@pytest.fixture
def out(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate, "OUT", tmp_path)
    monkeypatch.setattr(llm, "OFFLINE", False)
    return tmp_path


def history(out):
    with (out / "history.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_quota_stop_then_resume(out, monkeypatch):
    first = FakeLLM(quota=5)                       # enough for 2 reports (2 calls each) + 1 extract
    monkeypatch.setattr(llm, "ask_json", first)
    monkeypatch.setattr(llm, "ask_judge", first)
    assert evaluate.main([]) == 3
    assert sorted(p.stem for p in out.glob("report_*.json")) == ["report_01", "report_02"]
    meta = json.loads((out / "report_01.json").read_text(encoding="utf-8"))["meta"]
    assert meta["model"] == llm.MODEL and meta["prompt_version"] == evaluate.prompt_version()
    assert history(out)[0]["status"].startswith("stopped: Daily free-tier quota")
    assert "**Partial:** 2 of 10 reports scored" in (out / "metrics.md").read_text(encoding="utf-8")

    second = FakeLLM()
    monkeypatch.setattr(llm, "ask_json", second)
    monkeypatch.setattr(llm, "ask_judge", second)
    assert evaluate.main([]) == 0
    assert second.calls == 16                      # only the 8 unfinished reports
    rows = history(out)
    assert [r["status"] for r in rows] == [rows[0]["status"], "complete"] and rows[1]["reports_scored"] == "10"
    m = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert m["run"]["prompt_version"] == evaluate.prompt_version() and m["planted"] == 16


def test_offline_scores_saved_results_without_calls(out, monkeypatch):
    def no_calls(prompt):
        raise AssertionError("offline must not call the LLM")
    monkeypatch.setattr(llm, "ask_json", no_calls)
    monkeypatch.setattr(llm, "ask_judge", no_calls)
    stale = {"claims": [], "requirements": [{"id": "R3", "status": "missing"}]}  # legacy: no meta
    (out / "report_03.json").write_text(json.dumps(stale), encoding="utf-8")
    assert evaluate.main(["--offline"]) == 3
    m = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert (m["reports_scored"], m["caught"], m["prompt_versions"]) == (1, 1, ["legacy"])
    assert history(out)[0]["mode"] == "offline"


def test_stale_results_are_rerun_live(out, monkeypatch):
    (out / "report_01.json").write_text(json.dumps({"claims": [], "requirements": [],
                                                    "meta": {"model": llm.MODEL, "prompt_version": "old"}}))
    fake = FakeLLM()
    monkeypatch.setattr(llm, "ask_json", fake)
    monkeypatch.setattr(llm, "ask_judge", fake)
    assert evaluate.main([]) == 0 and fake.calls == 20
