"""The full check: extract claims (LLM) -> verify numbers (SQL) + internal consistency -> judge (LLM)."""
import json

from . import llm
from .consistency import ENERGY_SHARES, apply_issues, find_issues
from .guardrails import Catalog, check_query
from .prompts import extract_prompt, judge_prompt
from .schema import TABLE
from .verify import connect, is_safe_select, verify_claim

# Which statuses count as a finding the reviewer must look at.
FLAGGED = {"contradicted", "inconsistent", "unsupported", "unverifiable"}
_RESULT_FIELDS = ("status", "actual", "note")


def check_numeric(con, claims: list[dict], report: str) -> list[dict]:
    """Deterministic stage: guardrails on each query, verify on the data, then the numbers against each other."""
    catalog = Catalog.from_connection(con, TABLE)
    numeric = []
    for c in claims:
        if c["kind"] != "numeric":
            continue
        c = {k: v for k, v in c.items() if k not in _RESULT_FIELDS}
        sql = c.get("sql")
        mismatch = sql and is_safe_select(sql) and check_query(con, catalog, sql, c.get("quote", ""), report)
        if mismatch:
            numeric.append({**c, "status": "query_mismatch", "actual": None, "note": mismatch})
        else:
            numeric.append(verify_claim(con, c))
    return apply_issues(numeric, find_issues(numeric, list(catalog.columns), shares=ENERGY_SHARES))


def check_report(report: str, requirements: str, ask=llm.ask_json) -> dict:
    """Run the whole pipeline on one report. `ask` is the LLM call (injectable for tests)."""
    con = connect()

    claims = ask(extract_prompt(report))["claims"]
    numeric = check_numeric(con, claims, report)
    judgments = [c for c in claims if c["kind"] == "judgment"]

    facts = "\n".join(f'- "{c["quote"]}" -> {c["status"]}'
                      + (f' (actual: {c["actual"]})' if c["actual"] is not None else "")
                      for c in numeric) or "(none)"
    j_list = json.dumps([{"id": c["id"], "quote": c["quote"]} for c in judgments], ensure_ascii=False)
    review = ask(judge_prompt(report, requirements, facts, j_list))

    verdicts = {v["id"]: v for v in review.get("judgments", [])}
    for c in judgments:
        v = verdicts.get(c["id"], {})
        c.update(status="supported" if v.get("verdict") == "supported" else "unsupported",
                 actual=None, note=v.get("reason", "no verdict returned"))

    all_claims = sorted(numeric + judgments, key=lambda c: int(c["id"].lstrip("C")))
    return {"claims": all_claims, "requirements": review.get("requirements", [])}


def recheck(result: dict, report: str) -> dict:
    """Re-run the deterministic stages on a saved result (no LLM): judge verdicts and requirements are kept."""
    numeric = {c["id"]: c for c in check_numeric(connect(), result["claims"], report)}
    claims = [numeric.get(c["id"], c) for c in result["claims"]]
    return {**result, "claims": claims}


def summary(result: dict) -> dict:
    claims = result["claims"]
    return {
        "claims": len(claims),
        "verified": sum(c["status"] in ("verified", "supported") for c in claims),
        "flagged": sum(c["status"] in FLAGGED for c in claims),
        "requirements_missing": sum(r["status"] != "covered" for r in result["requirements"]),
    }
