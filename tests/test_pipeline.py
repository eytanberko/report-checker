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
