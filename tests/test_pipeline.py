"""End-to-end pipeline + scoring with a FAKE LLM (so it runs offline, no API key)."""
from pathlib import Path

import yaml

from checker.core import check_report
from evaluate import score

REPORTS = {r["id"]: r for r in
           yaml.safe_load(Path("benchmark/reports.yaml").read_text(encoding="utf-8"))["reports"]}
Q = "SELECT {col} FROM energy WHERE country='{c}' AND year={y}"


def fake_llm(prompt: str) -> dict:
    if "Split the REPORT" in prompt:  # extraction step for report_04
        return {"claims": [
            {"id": "C1", "quote": "renewables share reached 16.9% in 2025", "kind": "numeric",
             "stated_value": 16.9, "sql": Q.format(col="renewables_share_elec", c="Israel", y=2025)},
            {"id": "C2", "quote": "Total generation grew to 92.1 TWh in 2025", "kind": "numeric",
             "stated_value": 92.1, "sql": Q.format(col="electricity_generation", c="Israel", y=2025)},
            {"id": "C3", "quote": "Cyprus reached 49.7% renewables in 2025", "kind": "numeric",
             "stated_value": 49.7, "sql": Q.format(col="renewables_share_elec", c="Cyprus", y=2025)},
            {"id": "C4", "quote": "The key risk is concentration", "kind": "judgment",
             "stated_value": None, "sql": None},
        ]}
    return {"judgments": [{"id": "C4", "verdict": "supported", "reason": "gas is 79.7%"}],
            "requirements": [{"id": f"R{i}", "status": "covered", "evidence": "...", "reason": ""}
                             for i in range(1, 6)]}


def test_pipeline_catches_planted_errors():
    rep = REPORTS["report_04"]
    result = check_report(rep["text"], "reqs", ask=fake_llm)
    status = {c["id"]: c["status"] for c in result["claims"]}
    assert status == {"C1": "verified", "C2": "contradicted", "C3": "contradicted", "C4": "supported"}

    s = score(rep, result)
    assert len(s["caught"]) == 2 and not s["missed"] and not s["false_alarms"]


def test_cascade_flags_are_not_false_alarms():
    rep = REPORTS["report_07"]
    def flagged(i, q):
        return {"id": i, "quote": q, "status": "contradicted"}
    result = {"claims": [flagged("C3", "Solar provided 13.1% of electricity in 2025"),
                         flagged("C8", "Egypt reached 24.0% renewables in 2025"),
                         flagged("C9", "ahead of Israel")],
              "requirements": []}
    s = score(rep, result)
    assert len(s["caught"]) == 2 and not s["false_alarms"]
    assert [c["id"] for c in s["cascade"]] == ["C9"]


def test_duplicate_flags_of_one_planted_error_count_once():
    rep = REPORTS["report_07"]
    flags = [{"id": "C3", "quote": "Solar provided 13.1% of electricity in 2025", "status": "contradicted"},
             {"id": "C4", "quote": "Solar provided 13.1% ... and is the main renewable source",
              "status": "unsupported"},
             {"id": "C8", "quote": "Egypt reached 24.0% renewables in 2025", "status": "contradicted"}]
    s = score(rep, {"claims": flags, "requirements": []})
    assert len(s["caught"]) == 2 and not s["false_alarms"] and not s["cascade"]


def requirement(rid, status, evidence):
    return {"id": rid, "status": status, "evidence": evidence, "reason": ""}


def test_requirement_cascade_general_rule():
    rep = REPORTS["report_04"]  # planted: "92.1 TWh", "Cyprus reached 49.7%"
    flags = [{"id": "C5", "quote": "Total generation grew to 92.1 TWh in 2025", "status": "contradicted"},
             {"id": "C7", "quote": "Cyprus reached 49.7% renewables in 2025", "status": "contradicted"}]
    reqs = [
        requirement("R4", "partial", "Total generation grew to 92.1 TWh in 2025 from 64.2 TWh in 2015."),  # match
        requirement("R3", "partial", "In the region, Cyprus reached 49.7% renewables"),  # match
        requirement("R2", "partial", "Coal is nearly gone at 3.4%"),           # unrelated evidence: false alarm
        requirement("R5", "missing", None),                                    # no evidence: false alarm
    ]
    s = score(rep, {"claims": flags, "requirements": reqs})
    assert sorted(c["id"] for c in s["cascade"]) == ["R3", "R4"]
    assert [a["id"] for a in s["false_alarms"]] == ["R2", "R5"]


def test_requirement_cascade_by_overlap_with_a_flagged_claim():
    rep = REPORTS["report_04"]
    flags = [{"id": "C5", "quote": "Total generation grew to 92.1 TWh in 2025", "status": "contradicted"},
             {"id": "C9", "quote": "Egypt 13.0%", "status": "unverifiable"}]   # flagged, but not a planted error
    reqs = [requirement("R3", "partial", "and Egypt 13.0%.")]                  # no planted match; overlaps C9
    s = score(rep, {"claims": flags, "requirements": reqs})
    assert [c["id"] for c in s["cascade"]] == ["R3"] and [a["id"] for a in s["false_alarms"]] == ["C9"]


def test_majority_review_takes_the_majority_and_breaks_ties_to_partial():
    from checker.core import majority_review
    v = lambda verdict, req: {"judgments": [{"id": "C1", "verdict": verdict, "reason": verdict}],  # noqa: E731
                              "requirements": [{"id": "R1", "status": req, "reason": req}]}
    merged, errors = majority_review([v("supported", "covered"), v("unsupported", "covered"),
                                      v("unsupported", "missing")], ["C1"])
    assert merged["judgments"][0]["verdict"] == "unsupported" and merged["requirements"][0]["status"] == "covered"
    merged, _ = majority_review([v("supported", "covered"), v("supported", "partial"),
                                 v("unsupported", "missing")], ["C1"])
    assert merged["judgments"][0]["verdict"] == "supported" and merged["requirements"][0]["status"] == "partial"


def test_check_report_votes_three_times(monkeypatch):
    rep = REPORTS["report_04"]
    seen = []

    def judge(prompt, vote=0):
        seen.append(vote)
        return {"judgments": [{"id": "C4", "verdict": "supported" if vote != 2 else "unsupported"}],
                "requirements": [{"id": f"R{i}", "status": "covered"} for i in range(1, 6)]}
    result = check_report(rep["text"], "reqs", ask=fake_llm, judge_ask=judge, judge_votes=3)
    assert seen == [1, 2, 3]
    assert {c["id"]: c["status"] for c in result["claims"]}["C4"] == "supported"


def test_sentence_long_planted_errors_are_scored():
    tariffs = "The decline in carbon intensity proves that electricity tariffs fell."
    growth = "On the requested growth measure, per-capita generation rose by 8.2%."
    report = {"text": f"Coal fell to 3.4%. {tariffs} {growth}",
              "planted": [{"type": "unsupported_conclusion", "match": tariffs},
                          {"type": "misread_requirement", "match": growth}]}
    claims = [{"id": "C2", "quote": tariffs.rstrip("."), "status": "unsupported"}]
    reqs = [{"id": "R4", "status": "partial", "evidence": "per-capita generation rose by 8.2%"}]
    s = score(report, {"claims": claims, "requirements": reqs})
    assert len(s["caught"]) == 2 and not s["false_alarms"]
    s = score(report, {"claims": claims, "requirements": [{"id": "R4", "status": "covered", "evidence": None}]})
    assert [e["type"] for e in s["missed"]] == ["misread_requirement"]


def test_a_failed_judge_is_recorded_and_the_rest_of_the_result_kept():
    from checker import llm

    def broken(prompt, vote=0):
        raise llm.BadOutput("garbled")
    rep = REPORTS["report_04"]
    single = check_report(rep["text"], "reqs", ask=fake_llm, judge_ask=broken)
    assert any(e.startswith("judge failed") for e in single["errors"])
    assert {c["id"] for c in single["claims"]} == {"C1", "C2", "C3", "C4"}

    def flaky(prompt, vote=0):
        if vote == 2:
            raise llm.BadOutput("garbled")
        return fake_llm(prompt)
    voted = check_report(rep["text"], "reqs", ask=fake_llm, judge_ask=flaky, judge_votes=3)
    assert voted["errors"] == ["judge vote 2 failed: garbled"]
    assert {c["id"]: c["status"] for c in voted["claims"]}["C4"] == "supported"   # the two good votes agree
