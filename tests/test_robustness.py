"""Malformed LLM output never crashes the pipeline; each unusable claim becomes unverifiable with a reason."""
import json

import pytest

from checker import llm
from checker.core import check_report
from checker.memo import review_memo
from checker.normalize import normalize_claims, normalize_review, parse_number

REPORT = "Israel's renewables were 16.9% of electricity in 2025. This trend will surely continue."
Q = "SELECT renewables_share_elec FROM energy WHERE country='Israel' AND year=2025"
COVERED = [{"id": "R1", "status": "covered"}]


def fake(extract, review=None):
    """LLM stub returning the given (possibly malformed) answers; an Exception instance is raised."""
    def ask(prompt):
        answer = extract if "Split the REPORT" in prompt else review
        if isinstance(answer, Exception):
            raise answer
        return answer
    return ask


def run(extract, review=None):
    return check_report(REPORT, "reqs", ask=fake(extract, review or {"judgments": [], "requirements": COVERED}))


def statuses(result):
    return {c["id"]: (c["status"], c["note"]) for c in result["claims"]}


@pytest.mark.parametrize("value,expected", [(16.9, 16.9), ("16.9", 16.9), ("16.9%", 16.9), ("1,480", 1480.0),
                                            (True, 1.0), ("true", 1.0), ("about sixteen", None),
                                            ("15 to 17", None), (None, None), ([16.9], None)])
def test_parse_number(value, expected):
    assert parse_number(value) == expected


def test_non_json_answer_raises_bad_output_and_is_not_cached(tmp_path, monkeypatch):
    class Resp:
        status_code, headers, text = 200, {}, ""

        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "Sure! Here are the claims: ..."}]}}]}
    monkeypatch.setattr(llm, "PROVIDER", "gemini")
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    monkeypatch.setattr(llm, "OFFLINE", False)
    monkeypatch.setattr(llm, "MIN_INTERVAL", 0)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: Resp())
    with pytest.raises(llm.BadOutput, match="did not return usable JSON"):
        llm.ask_json("p")
    assert list(tmp_path.iterdir()) == []


def test_extraction_bad_output_gives_empty_result_with_error():
    result = run(llm.BadOutput("gemini did not return usable JSON"))
    assert result == {"claims": [], "requirements": [],
                      "errors": ["extraction failed: gemini did not return usable JSON"]}
    assert "extraction failed" in review_memo(result)


@pytest.mark.parametrize("extract", [{"items": []}, {"claims": "C1: 16.9%"}, ["not", "a", "dict"]])
def test_extraction_without_claims_list(extract):
    assert run(extract)["errors"][0] == "extraction returned no claims list"


def test_missing_fields_and_malformed_claims():
    result = run({"claims": [
        {"quote": "renewables were 16.9%", "stated_value": 16.9, "sql": Q},             # no id, no kind
        {"id": "C1", "kind": "numeric", "stated_value": 16.9, "sql": Q},                 # duplicate id, no quote
        "16.9% renewables",                                                              # not a dict
        {"id": "C9", "quote": "This trend will surely continue", "kind": "opinion"},     # unknown kind
    ]}, {"judgments": [{"id": "C4", "verdict": "unsupported", "reason": "forecast"}], "requirements": COVERED})
    s = statuses(result)
    assert list(s) == ["C1", "C2", "C3", "C4"]                                  # renumbered, nothing dropped
    assert s["C1"] == ("verified", "")
    assert s["C2"] == ("unverifiable", "the extractor gave no quote for this claim")
    assert s["C3"] == ("unverifiable", "malformed claim from the extractor")
    assert s["C4"] == ("unsupported", "forecast")                               # kind inferred: judgment


def test_non_numeric_stated_values():
    result = run({"claims": [
        {"id": "C1", "quote": "16.9% of electricity", "kind": "numeric", "stated_value": "16.9%", "sql": Q},
        {"id": "C2", "quote": "renewables were", "kind": "numeric", "stated_value": "about sixteen", "sql": Q},
        {"id": "C3", "quote": "in 2025", "kind": "numeric", "stated_value": 16.9, "sql": ["not", "sql"]},
    ]})
    s = statuses(result)
    assert s["C1"] == ("verified", "")
    assert s["C2"] == ("unverifiable", "stated value is not a number: 'about sixteen'")
    assert s["C3"] == ("unverifiable", "no query could be written")


def test_judge_unknown_ids_missing_and_unknown_verdicts():
    extract = {"claims": [{"id": "C1", "quote": "This trend will surely continue", "kind": "judgment"},
                          {"id": "C2", "quote": "renewables were 16.9%", "kind": "judgment"}]}
    review = {"judgments": [{"id": "C7", "verdict": "supported"}, {"id": "C2", "verdict": "partly"}],
              "requirements": COVERED}
    result = run(extract, review)
    s = statuses(result)
    assert s["C1"] == ("unverifiable", "no verdict returned by the judge")
    assert s["C2"] == ("unverifiable", "unrecognised verdict 'partly'")
    assert result["errors"] == ["judge answered an unknown claim id 'C7' (ignored)"]


def test_judge_bad_output_and_malformed_requirements():
    extract = {"claims": [{"id": "C1", "quote": "This trend will surely continue", "kind": "judgment"}]}
    result = run(extract, llm.BadOutput("not JSON"))
    assert statuses(result)["C1"][0] == "unverifiable" and result["requirements"] == []
    assert result["errors"] == ["judge failed: not JSON", "judge returned no usable answer"]

    _, reqs, errors = normalize_review({"judgments": "x", "requirements": [
        {"id": "R1", "status": "done"}, {"status": "covered"}, "R3"]}, [])
    assert reqs == [{"id": "R1", "status": "partial", "reason": "unrecognised status 'done', needs a human look."}]
    assert errors == ["judge returned a requirement without an id (ignored)"] * 2


def test_normalized_claims_round_trip_through_json():
    claims, errors = normalize_claims({"claims": [{"quote": "x", "stated_value": "5%", "sql": Q}]})
    assert json.loads(json.dumps(claims)) == claims and not errors
