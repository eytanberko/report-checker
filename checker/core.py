"""The full check: extract claims (LLM) -> verify numbers (SQL) + internal consistency -> judge (LLM)."""
import json
from collections.abc import Callable

import duckdb

from . import llm
from .consistency import apply_issues, find_issues
from .context import data_context
from .dataset import Dataset, default_dataset
from .guardrails import check_query
from .normalize import apply_verdict, normalize_claims, normalize_review
from .prompts import extract_prompt, format_facts, judge_prompt
from .verify import is_safe_select, verify_claim

# Which statuses count as a finding the reviewer must look at.
FLAGGED = {"contradicted", "inconsistent", "unsupported", "unverifiable"}
_RESULT_FIELDS = ("status", "actual", "note")


def check_numeric(con: duckdb.DuckDBPyConnection, claims: list[dict], report: str,
                  dataset: Dataset | None = None) -> list[dict]:
    """Deterministic stage: guardrails on each query, verify on the data, then the numbers against each other."""
    ds = dataset or default_dataset()
    catalog = ds.catalog(con)
    numeric = []
    for c in claims:
        if c["kind"] != "numeric":
            continue
        c = {k: v for k, v in c.items() if k not in _RESULT_FIELDS}
        if c.get("problem"):  # unusable LLM output, found by normalize_claims
            numeric.append({**c, "status": "unverifiable", "actual": None, "note": c["problem"]})
            continue
        sql = c.get("sql")
        mismatch = sql and is_safe_select(sql) and check_query(con, catalog, sql, c.get("quote", ""), report)
        if mismatch:
            numeric.append({**c, "status": "query_mismatch", "actual": None, "note": mismatch})
        else:
            numeric.append(verify_claim(con, c))
    # A mismatched query doesn't measure what its claim says, so it can't key the consistency checks.
    keyed = [c for c in numeric if c["status"] != "query_mismatch"]
    issues = find_issues(keyed, list(catalog.columns), ds.entity_col, ds.time_col, shares=ds.shares)
    return apply_issues(numeric, issues)


def check_report(report: str, requirements: str, ask: Callable[[str], dict] | None = None,
                 dataset: Dataset | None = None, judge_ask: Callable[[str], dict] | None = None) -> dict:
    """Run the whole pipeline on one report.

    `ask` is the extraction LLM call and `judge_ask` the judge call (default: the extraction and judge
    models from llm.py). A test that injects only `ask` gets it for both stages."""
    if ask is None:
        ask, judge_ask = llm.ask_json, judge_ask or llm.ask_judge
    judge_ask = judge_ask or ask
    ds = dataset or default_dataset()
    con = ds.connect()

    try:
        raw = ask(extract_prompt(report, ds.description, ds.table, ds.entity_col, ds.time_col))
    except llm.BadOutput as e:
        return {"claims": [], "requirements": [], "errors": [f"extraction failed: {e}"]}
    claims, errors = normalize_claims(raw)
    numeric = check_numeric(con, claims, report, ds)
    judgments = [c for c in claims if c["kind"] == "judgment"]

    facts = format_facts(numeric)
    j_list = json.dumps([{"id": c["id"], "quote": c["quote"]} for c in judgments], ensure_ascii=False)
    try:
        review = judge_ask(judge_prompt(report, requirements, facts, j_list, data_context(con, ds, claims)))
    except llm.BadOutput as e:
        review, errors = None, errors + [f"judge failed: {e}"]
    verdicts, reqs, review_errors = normalize_review(review, [c["id"] for c in judgments])
    judged = [apply_verdict(c, verdicts.get(c["id"])) for c in judgments]

    all_claims = sorted(numeric + judged, key=lambda c: int(c["id"].lstrip("C")))
    result = {"claims": all_claims, "requirements": reqs}
    if errors + review_errors:
        result["errors"] = errors + review_errors
    return result


def recheck(result: dict, report: str, dataset: Dataset | None = None) -> dict:
    """Re-run the deterministic stages on a saved result (no LLM): judge verdicts and requirements are kept."""
    ds = dataset or default_dataset()
    numeric = {c["id"]: c for c in check_numeric(ds.connect(), result["claims"], report, ds)}
    claims = [numeric.get(c["id"], c) for c in result["claims"]]
    return {**result, "claims": claims}
