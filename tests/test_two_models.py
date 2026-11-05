"""Two-model pipeline: extraction and judge on separate models; query mismatches shown as 'not checked'."""
import csv

import evaluate
from checker import llm
from checker.core import check_report
from checker.prompts import NOT_CHECKED, format_facts

Q = "SELECT renewables_share_elec FROM energy WHERE country='Israel' AND year={y}"
REPORT = "Israel's renewables were 16.9% of electricity in 2025. Spain reached 55.9%."
EXTRACT = {"claims": [
    {"id": "C1", "quote": "Israel's renewables were 16.9% of electricity in 2025", "kind": "numeric",
     "stated_value": 16.9, "sql": Q.format(y=2025)},
    {"id": "C2", "quote": "Spain reached 55.9%", "kind": "numeric", "stated_value": 55.9,
     "sql": Q.format(y=2025)},   # wrong country in SQL -> query_mismatch
]}
REVIEW = {"judgments": [], "requirements": [{"id": "R1", "status": "covered"}]}


def test_format_facts_never_presents_a_mismatch_as_a_report_problem():
    facts = format_facts([
        {"quote": "a", "status": "verified", "actual": 16.93},
        {"quote": "b", "status": "query_mismatch", "actual": None, "note": "query uses Israel"},
    ])
    assert facts == f'- "a" -> verified (actual: 16.93)\n- "b" -> {NOT_CHECKED}'
    assert "query_mismatch" not in facts and "Israel" not in facts


def test_extraction_and_judge_use_their_own_calls():
    seen = {"extract": [], "judge": []}

    def extract(prompt):
        seen["extract"].append(prompt)
        return EXTRACT

    def judge(prompt):
        seen["judge"].append(prompt)
        return REVIEW
    result = check_report(REPORT, "reqs", ask=extract, judge_ask=judge)
    assert len(seen["extract"]) == 1 and "Split the REPORT" in seen["extract"][0]
    assert len(seen["judge"]) == 1 and "senior analyst" in seen["judge"][0]
    assert f'"Spain reached 55.9%" -> {NOT_CHECKED}' in seen["judge"][0]
    assert [c["status"] for c in result["claims"]] == ["verified", "query_mismatch"]


def test_default_wiring_uses_extraction_and_judge_models(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "ask_json", lambda p, **kw: calls.append(("extract", kw)) or EXTRACT)
    monkeypatch.setattr(llm, "ask_judge", lambda p: calls.append(("judge", {})) or REVIEW)
    check_report(REPORT, "reqs")
    assert [c[0] for c in calls] == ["extract", "judge"]


def test_ask_judge_calls_the_judge_model_with_its_own_cache(tmp_path, monkeypatch):
    class Resp:
        status_code, headers, text = 200, {}, ""

        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"ok": 1}'}]}}]}
    urls = []
    monkeypatch.setattr(llm, "PROVIDER", "gemini")
    monkeypatch.setattr(llm, "MODEL", "extract-model")
    monkeypatch.setattr(llm, "JUDGE_MODEL", "judge-model")
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    monkeypatch.setattr(llm, "OFFLINE", False)
    monkeypatch.setattr(llm, "MIN_INTERVAL", 0)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(llm.requests, "post", lambda url, **kw: urls.append(url) or Resp())
    assert llm.ask_judge("p") == {"ok": 1} and llm.ask_json("p") == {"ok": 1}
    assert ["models/judge-model:" in urls[0], "models/extract-model:" in urls[1]] == [True, True]
    assert llm.cache_path("p", "judge-model") != llm.cache_path("p") and len(list(tmp_path.iterdir())) == 2


def test_history_gains_judge_model_column(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate, "OUT", tmp_path)
    old = ["timestamp", "mode", "model", "prompt_version", "reports_scored", "reports_total", "recall",
           "precision", "false_alarms", "cascade", "query_mismatches", "api_calls", "cache_hits", "seconds", "status"]
    with (tmp_path / "history.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=old)
        w.writeheader()
        w.writerow({k: "x" for k in old} | {"model": "old-model"})
    m = {"prompt_versions": ["v"], "reports_scored": 10, "reports_total": 10, "false_alarms": 0, "cascade": 0,
         "query_mismatches": 0, "recall": 1.0, "precision": 1.0}
    run = {"timestamp": "t", "mode": "live", "model": "e", "judge_model": "j", "api_calls": 1, "cache_hits": 0,
           "seconds": 1, "status": "complete"}
    evaluate.append_history(m, run)
    rows = list(csv.DictReader((tmp_path / "history.csv").open(encoding="utf-8")))
    assert [(r["model"], r["judge_model"]) for r in rows] == [("old-model", "old-model"), ("e", "j")]


def test_results_from_another_judge_model_are_stale():
    assert evaluate.run_meta()["judge_model"] == llm.JUDGE_MODEL
