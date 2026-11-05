"""The full check: extract claims (LLM) -> verify numbers (SQL) -> judge conclusions + coverage (LLM)."""
import json

from . import llm
from .prompts import extract_prompt, judge_prompt
from .verify import connect, verify_claim


def check_report(report: str, requirements: str, ask=llm.ask_json) -> dict:
    con = connect()

    claims = ask(extract_prompt(report))["claims"]
    numeric = [verify_claim(con, c) for c in claims if c["kind"] == "numeric"]
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


# Which statuses count as a finding the reviewer must look at.
FLAGGED = {"contradicted", "unsupported", "unverifiable"}


def summary(result: dict) -> dict:
    claims = result["claims"]
    return {
        "claims": len(claims),
        "verified": sum(c["status"] in ("verified", "supported") for c in claims),
        "flagged": sum(c["status"] in FLAGGED for c in claims),
        "requirements_missing": sum(r["status"] != "covered" for r in result["requirements"]),
    }
