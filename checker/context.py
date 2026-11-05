"""Deterministic data context for the judge: the rows of the data behind the report, built in Python.

Without it the judge only sees the report's own numbers, so it can't reject a cause the report
doesn't contradict ("the coal phase-out was driven by solar" when gas rose more).
For every entity and year in the extracted claims (their SQL and their quotes; a period contributes
its first and last year), it lists the context columns, plus the change from the first to the last year.
"""
import duckdb

from .dataset import Dataset
from .guardrails import _YEAR, _literals, _mentions, _numbers

MAX_ENTITIES, MAX_YEARS = 12, 8


def context_columns(con: duckdb.DuckDBPyConnection, ds: Dataset) -> list[str]:
    """The dataset's chosen context columns, else every numeric column except the time column."""
    if ds.context_columns:
        return ds.context_columns
    cat = ds.catalog(con)
    return [c for c in cat.ranges if c != ds.time_col]


def scope(con: duckdb.DuckDBPyConnection, ds: Dataset, claims: list[dict]) -> tuple[list[str], list[int]]:
    """Entities and years the claims refer to, read from their SQL and quotes."""
    cat = ds.catalog(con)
    known = cat.categories.get(ds.entity_col, set()) if ds.entity_col else set()
    lo, hi = cat.ranges.get(ds.time_col, (float("-inf"), float("inf"))) if ds.time_col else (0, 0)
    entities, years = set(), set()
    for c in claims:
        sql, quote = c.get("sql") or "", c.get("quote") or ""
        if ds.entity_col:
            entities |= {e for e in _literals(sql, ds.entity_col) if e in known} | _mentions(quote, known)
        if ds.time_col:
            claim_years = {int(y) for y in _numbers(sql, ds.time_col)} | {int(y) for y in _YEAR.findall(quote)}
            years |= {y for y in claim_years if lo <= y <= hi}
    return sorted(entities)[:MAX_ENTITIES], sorted(years)[-MAX_YEARS:]


def _fmt(x: float | None) -> str:
    return "" if x is None else f"{x:,.1f}"


def data_context(con: duckdb.DuckDBPyConnection, ds: Dataset, claims: list[dict]) -> str:
    """Markdown table of the data for the claims' entities and years (plus first->last changes)."""
    if not (ds.entity_col and ds.time_col):
        return "(none)"
    entities, years = scope(con, ds, claims)
    if not entities or not years:
        return "(none)"
    cols = context_columns(con, ds)
    q = ", ".join(f'"{c}"' for c in cols)
    rows = con.execute(
        f'SELECT "{ds.entity_col}", "{ds.time_col}", {q} FROM "{ds.table}" '
        f'WHERE "{ds.entity_col}" IN ({", ".join("?" * len(entities))}) '
        f'AND "{ds.time_col}" IN ({", ".join("?" * len(years))}) ORDER BY 1, 2',
        [*entities, *years]).fetchall()
    lines = [f"| {ds.entity_col} | {ds.time_col} | " + " | ".join(cols) + " |",
             "|" + "---|" * (len(cols) + 2)]
    by_entity: dict[str, list[tuple]] = {}
    for row in rows:
        lines.append(f"| {row[0]} | {row[1]} | " + " | ".join(_fmt(v) for v in row[2:]) + " |")
        by_entity.setdefault(row[0], []).append(row)
    for entity, rs in by_entity.items():
        if len(rs) >= 2:
            first, last = rs[0], rs[-1]
            diffs = [_fmt(b - a) if a is not None and b is not None else ""
                     for a, b in zip(first[2:], last[2:], strict=True)]
            lines.append(f"| {entity} | change {first[1]}->{last[1]} (absolute) | " + " | ".join(diffs) + " |")
    missing = [e for e in entities if e not in by_entity]
    if missing:
        lines.append(f"\nNo rows for: {', '.join(missing)} in those years.")
    return "\n".join(lines)
