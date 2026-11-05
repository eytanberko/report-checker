"""Defensive parsing of LLM output: whatever comes back, the pipeline gets well-formed claims.

A claim that can't be used is kept with a "problem" (it becomes "unverifiable" with that reason), so the reviewer
sees it instead of the checker crashing or silently dropping it.
"""
import re

KINDS = ("numeric", "judgment")
VERDICTS = ("supported", "unsupported")
REQ_STATUSES = ("covered", "partial", "missing")
_NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?|[-+]?\.\d+")


def parse_number(value: object) -> float | None:
    """16.9, "16.9", "16.9%", "1,480", True -> float; anything else -> None."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "yes"):
            return 1.0
        if text in ("false", "no"):
            return 0.0
        found = _NUMBER.findall(text)
        if len(found) == 1:
            return float(found[0].replace(",", ""))
    return None


def _unusable(cid: str, quote: str, reason: str) -> dict:
    return {"id": cid, "quote": quote, "kind": "numeric", "stated_value": None, "sql": None, "problem": reason}


def normalize_claims(raw: object) -> tuple[list[dict], list[str]]:
    """Well-formed claims with ids C1..Cn from the extractor's output, plus problems found."""
    errors: list[str] = []
    items = raw.get("claims") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return [], ["extraction returned no claims list"]

    claims = []
    for n, item in enumerate(items, 1):
        cid = f"C{n}"
        if not isinstance(item, dict):
            claims.append(_unusable(cid, str(item)[:80], "malformed claim from the extractor"))
            continue
        quote = item.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            claims.append(_unusable(cid, "(no quote)", "the extractor gave no quote for this claim"))
            continue
        kind = item.get("kind")
        if kind not in KINDS:
            kind = "numeric" if item.get("sql") or item.get("stated_value") is not None else "judgment"
        claim = {"id": cid, "quote": quote.strip(), "kind": kind, "stated_value": None, "sql": None}
        if kind == "judgment":
            claims.append(claim)
            continue
        sql = item.get("sql")
        claim["sql"] = sql if isinstance(sql, str) and sql.strip() else None
        value = item.get("stated_value")
        claim["stated_value"] = parse_number(value)
        if value is not None and claim["stated_value"] is None:
            claims.append({**claim, "problem": f"stated value is not a number: {value!r}"})
            continue
        claims.append(claim)
    return claims, errors


def normalize_review(raw: object, judgment_ids: list[str]) -> tuple[dict[str, dict], list[dict], list[str]]:
    """(verdict per known judgment id, well-formed requirements, problems found) from the judge's output."""
    if not isinstance(raw, dict):
        return {}, [], ["judge returned no usable answer"]
    errors: list[str] = []
    verdicts: dict[str, dict] = {}
    judgments = raw.get("judgments")
    for v in judgments if isinstance(judgments, list) else []:
        if not isinstance(v, dict):
            continue
        if v.get("id") not in judgment_ids:
            errors.append(f"judge answered an unknown claim id {v.get('id')!r} (ignored)")
            continue
        verdicts[v["id"]] = v

    requirements = []
    reqs = raw.get("requirements")
    for r in reqs if isinstance(reqs, list) else []:
        if not isinstance(r, dict) or not isinstance(r.get("id"), str):
            errors.append("judge returned a requirement without an id (ignored)")
            continue
        status, reason = r.get("status"), r.get("reason") or ""
        if status not in REQ_STATUSES:
            reason = f"unrecognised status {status!r}, needs a human look. {reason}".strip()
            status = "partial"
        requirements.append({**r, "status": status, "reason": reason})
    if not isinstance(reqs, list):
        errors.append("judge returned no requirements list")
    return verdicts, requirements, errors


def apply_verdict(claim: dict, verdict: dict | None) -> dict:
    """Judgment claim with status from the judge; a missing or unknown verdict is unverifiable, not a finding."""
    if verdict is None:
        return {**claim, "status": "unverifiable", "actual": None, "note": "no verdict returned by the judge"}
    v = verdict.get("verdict")
    if v not in VERDICTS:
        return {**claim, "status": "unverifiable", "actual": None, "note": f"unrecognised verdict {v!r}"}
    return {**claim, "status": v, "actual": None, "note": verdict.get("reason") or ""}
