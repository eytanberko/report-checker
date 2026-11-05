"""SQL guardrails, run before a claim's query executes.

They catch a bad *query* (the LLM's mistake) so it isn't reported as a bad *report*:
unknown columns, unknown category values (e.g. a misspelt country), years outside the data,
and a country or year in the SQL that the claim's sentence doesn't name or imply.
A failed guardrail gives status "query_mismatch", which is not counted as a report error.
"""
import re
from dataclasses import dataclass, field

import duckdb

from .highlight import locate

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}
_RELATIVE = re.compile(r"\b(\d+|" + "|".join(NUMBER_WORDS) + r"|a)\s+years?\s+(?:earlier|ago|before|later|on)\b"
                       r"|\b(?:a|the|over the|over a)\s+(decade)\b|\b(previous|prior|next) year\b", re.I)
_YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)|\n\s*\n")


@dataclass
class Catalog:
    """What the guardrails need to know about a table: columns, category values, numeric ranges."""
    table: str
    columns: dict[str, str]                                   # name -> DuckDB type
    categories: dict[str, set[str]] = field(default_factory=dict)
    ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    entity_col: str | None = "country"
    time_col: str | None = "year"

    @classmethod
    def from_connection(cls, con, table: str, entity_col: str | None = "country",
                        time_col: str | None = "year", max_categories: int = 500) -> "Catalog":
        columns = {name: typ for name, typ, *_ in con.execute(f"DESCRIBE {table}").fetchall()}
        cat = cls(table, columns, entity_col=entity_col, time_col=time_col)
        for name, typ in columns.items():
            q = f'"{name}"'
            if typ == "VARCHAR":
                values = con.execute(f"SELECT DISTINCT {q} FROM {table} WHERE {q} IS NOT NULL "
                                     f"LIMIT {max_categories + 1}").fetchall()
                if len(values) <= max_categories:
                    cat.categories[name] = {v[0] for v in values}
            elif any(t in typ for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL")):
                lo, hi = con.execute(f"SELECT MIN({q}), MAX({q}) FROM {table}").fetchone()
                if lo is not None:
                    cat.ranges[name] = (float(lo), float(hi))
        return cat


def _sentence(report: str, quote: str) -> str:
    """The sentence(s) of the report that contain the quote (the whole report if it can't be found)."""
    span = locate(report, quote)
    if span is None:
        return report
    ends = [m.end() for m in _SENTENCE_END.finditer(report)]
    start = max([e for e in ends if e <= span[0]], default=0)
    end = min([e for e in ends if e >= span[1]], default=len(report))
    return report[start:end]


def _years_implied(text: str) -> set[int]:
    """Explicit years plus years implied by relative wording ("ten years earlier", "over the decade")."""
    years = {int(y) for y in _YEAR.findall(text)}
    offsets = set()
    for m in _RELATIVE.finditer(text):
        n, decade, prev_next = m.groups()
        if decade:
            offsets.add(10)
        elif prev_next:
            offsets.add(1)
        else:
            offsets.add(1 if n.lower() == "a" else int(n) if n.isdigit() else NUMBER_WORDS[n.lower()])
    return years | {y + s * o for y in years for o in offsets for s in (-1, 1)}


def _mentions(text: str, values: set[str]) -> set[str]:
    return {v for v in values if re.search(r"\b" + re.escape(v), text, re.I)}


def _literals(sql: str, column: str) -> list[str]:
    """String literals compared to `column` with = or IN (...)."""
    out = re.findall(rf"\b{re.escape(column)}\s*=\s*'([^']*)'", sql, re.I)
    for group in re.findall(rf"\b{re.escape(column)}\s+IN\s*\(([^)]*)\)", sql, re.I):
        out += re.findall(r"'([^']*)'", group)
    return out


def _numbers(sql: str, column: str) -> list[float]:
    """Numeric literals compared to `column` with =, IN (...) or BETWEEN."""
    c = re.escape(column)
    out = [float(x) for x in re.findall(rf"\b{c}\s*=\s*(-?\d+(?:\.\d+)?)\b", sql, re.I)]
    for a, b in re.findall(rf"\b{c}\s+BETWEEN\s+(-?\d+(?:\.\d+)?)\s+AND\s+(-?\d+(?:\.\d+)?)", sql, re.I):
        out += [float(a), float(b)]
    for group in re.findall(rf"\b{c}\s+IN\s*\(([^)]*)\)", sql, re.I):
        out += [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", group)]
    return out


def check_query(con, catalog: Catalog, sql: str, quote: str, report: str) -> str | None:
    """Why this query can't be trusted to check this claim, or None if it passes every guardrail."""
    try:
        con.execute("EXPLAIN " + sql)
    except (duckdb.BinderException, duckdb.CatalogException) as e:
        return "query refers to something not in the data: " + str(e).splitlines()[0]
    except duckdb.Error:
        return None  # syntax and other errors are reported by the verifier itself

    for col, allowed in catalog.categories.items():
        unknown = sorted({v for v in _literals(sql, col) if v not in allowed})
        if unknown:
            return f"{col} value not in the data: {', '.join(repr(v) for v in unknown)}"
    for col, (lo, hi) in catalog.ranges.items():
        outside = sorted({v for v in _numbers(sql, col) if not lo <= v <= hi})
        if outside and col == catalog.time_col:
            return f"{col} {', '.join(f'{v:g}' for v in outside)} is outside the data ({lo:g}-{hi:g})"

    context = _sentence(report, quote)
    if catalog.entity_col in catalog.categories:
        entities = catalog.categories[catalog.entity_col]
        named = _mentions(context, entities) or _mentions(report, entities)
        used = set(_literals(sql, catalog.entity_col))
        if named and used - named:
            return (f"query uses {', '.join(sorted(used - named))}, but the claim's sentence names "
                    f"{', '.join(sorted(_mentions(context, entities) or named))}")
    if catalog.time_col:
        used_years = {int(v) for v in _numbers(sql, catalog.time_col)}
        allowed_years = _years_implied(context) or _years_implied(report)
        if allowed_years and used_years - allowed_years:
            return (f"query uses {catalog.time_col} {', '.join(map(str, sorted(used_years - allowed_years)))}, "
                    f"which the claim's sentence doesn't state or imply")
    return None
