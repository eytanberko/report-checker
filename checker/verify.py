"""Deterministic part: run each claim's SQL on the real data and compare to the stated value.
No LLM here -> this is the part we can fully trust and test."""
import re

import duckdb

_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|create|alter|attach|copy|pragma|install|load)\b", re.I)


def is_safe_select(sql: str) -> bool:
    """True for a single read-only SELECT / WITH statement."""
    s = sql.strip().rstrip(";")
    return ";" not in s and bool(re.match(r"^\s*(select|with)\b", s, re.I)) and not _FORBIDDEN.search(s)


def run_sql(con: duckdb.DuckDBPyConnection, sql: str) -> tuple[float | None, str | None]:
    """Returns (value, error). Only single read-only SELECT statements are allowed."""
    if not is_safe_select(sql):
        return None, "rejected: only a single SELECT is allowed"
    s = sql.strip().rstrip(";")
    try:
        row = con.execute(s).fetchone()
    except duckdb.Error as e:
        return None, f"sql error: {str(e).splitlines()[0]}"
    if not row or row[0] is None:
        return None, "no data for this claim"
    try:
        return float(row[0]), None
    except (TypeError, ValueError):
        return None, f"non-numeric result: {row[0]!r}"


def tolerance(stated: float, actual: float) -> float:
    """Allow for the rounding the analyst used (16.9 vs 16.93) plus 1% relative slack."""
    text = f"{stated}"
    decimals = len(text.split(".")[1].rstrip("0")) if "." in text else 0
    return max(0.5 * 10 ** -decimals, 0.01 * abs(actual))


def verify_claim(con: duckdb.DuckDBPyConnection, claim: dict) -> dict:
    """Adds status/actual/note to a numeric claim."""
    out = dict(claim)
    if claim.get("sql") is None or claim.get("stated_value") is None:
        out.update(status="unverifiable", actual=None, note="no query could be written")
        return out
    actual, err = run_sql(con, claim["sql"])
    if err or actual is None:
        out.update(status="unverifiable", actual=None, note=err)
        return out
    stated = float(claim["stated_value"])
    ok = abs(actual - stated) <= tolerance(stated, actual)
    out.update(status="verified" if ok else "contradicted", actual=round(actual, 2),
               note="" if ok else f"data says {actual:.2f}, report says {stated:g}")
    return out
