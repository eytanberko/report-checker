"""The full check: extract claims (LLM) -> verify numbers (SQL) + internal consistency -> judge (LLM)."""
import json
from collections import Counter
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


def majority_review(reviews: list, judgment_ids: list[str]) -> tuple[dict, list[str]]:
    """Combine several judge answers: each conclusion takes the verdict most votes give, each requirement the
    most common status (a three-way tie is "partial"). Returns (a single judge-shaped answer, problems)."""
    parsed = [normalize_review(r, judgment_ids) for r in reviews if r is not None]
    errors = [e for _, _, errs in parsed for e in errs]
    judgments = []
    for jid in judgment_ids:
        votes = [v[jid] for v, _, _ in parsed if jid in v and v[jid].get("verdict") in ("supported", "unsupported")]
        if votes:
            top = Counter(v["verdict"] for v in votes).most_common()
            verdict = top[0][0] if len(top) == 1 or top[0][1] > top[1][1] else votes[0]["verdict"]
            judgments.append(next(v for v in votes if v["verdict"] == verdict))
    requirements = []
    req_ids = list(dict.fromkeys(r["id"] for _, reqs, _ in parsed for r in reqs))
    for rid in req_ids:
        votes = [r for _, reqs, _ in parsed for r in reqs if r["id"] == rid]
        top = Counter(r["status"] for r in votes).most_common()
        status = top[0][0] if len(top) == 1 or top[0][1] > top[1][1] else "partial"
        requirements.append(next((r for r in votes if r["status"] == status), {**votes[0], "status": status}))
    return {"judgments": judgments, "requirements": requirements}, errors


def check_report(report: str, requirements: str, ask: Callable[[str], dict] | None = None,
                 dataset: Dataset | None = None, judge_ask: Callable[..., dict] | None = None,
                 judge_votes: int | None = None) -> dict:
    """Run the whole pipeline on one report.

    `ask` is the extraction LLM call and `judge_ask` the judge call (default: the extraction and judge
    models from llm.py). A test that injects only `ask` gets it for both stages. With `judge_votes` > 1
    (default llm.JUDGE_VOTES when the real LLM is used, else 1) the judge answers that many times, majority wins."""
    if ask is None:
        ask, judge_ask = llm.ask_json, judge_ask or llm.ask_judge
        judge_votes = judge_votes or llm.JUDGE_VOTES
    judge: Callable[..., dict] = judge_ask or ask
    judge_votes = judge_votes or 1
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
    prompt = judge_prompt(report, requirements, facts, j_list, data_context(con, ds, claims))
    ids = [c["id"] for c in judgments]
    if judge_votes == 1:
        try:
            review = judge(prompt)
        except llm.BadOutput as e:
            review, errors = None, errors + [f"judge failed: {e}"]
    else:
        reviews = []
        for vote in range(1, judge_votes + 1):
            try:
                reviews.append(judge(prompt, vote=vote))
            except llm.BadOutput as e:
                errors = errors + [f"judge vote {vote} failed: {e}"]
        review, vote_errors = majority_review(reviews, ids) if reviews else (None, [])
        errors = errors + vote_errors
    verdicts, reqs, review_errors = normalize_review(review, ids)
    judged = [apply_verdict(c, verdicts.get(c["id"])) for c in judgments]

    all_claims = sorted(numeric + judged, key=lambda c: int(c["id"].lstrip("C")))
    result: dict = {"claims": all_claims, "requirements": reqs}
    if errors + review_errors:
        result["errors"] = errors + review_errors
    return result


def recheck(result: dict, report: str, dataset: Dataset | None = None) -> dict:
    """Re-run the deterministic stages on a saved result (no LLM): judge verdicts and requirements are kept."""
    ds = dataset or default_dataset()
    numeric = {c["id"]: c for c in check_numeric(ds.connect(), result["claims"], report, ds)}
    claims = [numeric.get(c["id"], c) for c in result["claims"]]
    return {**result, "claims": claims}
