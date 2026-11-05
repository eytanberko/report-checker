"""Review memo: severity order, evidence, suggested fixes."""
import json
from pathlib import Path

from checker.memo import review_memo


def c(cid, quote, status, actual=None, note="", sql=None):
    return {"id": cid, "quote": quote, "status": status, "actual": actual, "note": note, "sql": sql}


CHANGE_SQL = ("SELECT (SELECT x FROM energy WHERE year=2025) - (SELECT x FROM energy WHERE year=2015)")
RESULT = {
    "claims": [
        c("C1", "the phase-out is far from complete", "unsupported", note="coal is 3.4%"),
        c("C2", "coal still provided 14.3%", "contradicted", 3.41, sql="SELECT coal FROM energy WHERE year=2025"),
        c("C3", "rose by 15%", "contradicted", 791.57, sql=CHANGE_SQL),
        c("C4", "an increase of 20 points", "inconsistent", note="1.9 -> 16.9 is 15.0 points, not 20"),
        c("C5", "gas reached 79.7%", "verified", 79.66),
        c("C6", "per capita use is high", "unverifiable", note="no query could be written"),
        c("C7", "Spain (55.9%)", "query_mismatch", note="SQL uses Italy; the quote names Spain"),
    ],
    "requirements": [{"id": "R1", "status": "covered"},
                     {"id": "R3", "status": "partial", "reason": "Asked: Mediterranean peers; answered: Germany."}],
}


def test_sections_in_severity_order():
    memo = review_memo(RESULT, "report_x")
    order = ["## 1. Wrong numbers (3)", "## 2. Requirements not met (1)", "## 3. Unsupported conclusions (1)",
             "## 4. Could not verify (1)", "## Checker notes (not errors in the report)"]
    assert [memo.index(h) for h in order] == sorted(memo.index(h) for h in order)
    assert memo.startswith("# Review: report_x") and "6 issues to fix" in memo and "1 of 7 claims" in memo


def test_items_carry_quote_evidence_and_fix():
    memo = review_memo(RESULT)
    assert "“coal still provided 14.3%”  \n  The data says **3.41**." in memo
    assert "Correct it to 3.41 (check the year and country" in memo
    assert "Correct it to 791.57, or reword it" in memo                      # change claim: method hint
    assert "don't agree: 1.9 -> 16.9 is 15.0 points, not 20" in memo
    assert "**R3** is only partly answered. Asked: Mediterranean peers" in memo
    assert "Spain (55.9%)”: not checked" in memo                              # mismatch is not an issue


def test_clean_report_memo():
    result = json.loads(Path("results/report_01.json").read_text(encoding="utf-8"))
    memo = review_memo(result, "report_01")
    assert "Good to send." in memo and "##" not in memo


def test_suggested_correction_uses_the_reports_precision():
    claims = [c("C1", "coal at 14.3%", "contradicted", 3.41, sql="SELECT coal FROM energy WHERE year=2025"),
              c("C2", "rose by 15%", "contradicted", 791.57, sql=CHANGE_SQL)]
    claims[0]["stated_value"], claims[1]["stated_value"] = 14.3, 15
    memo = review_memo({"claims": claims, "requirements": []})
    assert "The data says **3.41**." in memo and "Correct it to 3.4 (check" in memo       # 14.3 has one decimal
    assert "Correct it to 792, or reword it" in memo                                       # 15 has none
