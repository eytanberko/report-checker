"""Internal consistency: do the report's own numbers agree with each other? No data access needed.

Each numeric claim is keyed by what it measures, read from its SQL text (column, entity, year),
never by running it. Checks:
  - a stated change vs its stated endpoints, under the claim's own wording
    ("15 percentage points", "15%", "2.8% per year", "8.9 times")
  - shares of the same entity/year that add up to more than 100%, or parts larger than their whole
  - the same metric stated twice with different values
Every stated number is an interval that covers its rounding (16.9 -> [16.85, 16.95]),
widened for approximate wording ("about 28%"), so rounding alone never triggers a finding.
"""
import re
from dataclasses import dataclass, field

APPROX = re.compile(r"\b(about|around|roughly|approximately|almost|nearly|close to|some)\b|~|four out of five", re.I)
APPROX_SLACK = 0.03  # relative widening for approximate wording

# Which share columns are parts of which whole; the top-level wholes are disjoint and sum to <= 100.
ENERGY_SHARES = {
    "renewables_share_elec": ["solar_share_elec", "wind_share_elec"],
    "fossil_share_elec": ["gas_share_elec", "coal_share_elec", "oil_share_elec"],
}


@dataclass
class Issue:
    """One inconsistency. `suspects` are the claims that may be wrong; `others` are the rest involved."""
    kind: str
    note: str
    suspects: list[dict]
    others: list[dict] = field(default_factory=list)


def _interval(value: float, quote: str) -> tuple[float, float]:
    text = f"{value}"
    decimals = len(text.split(".")[1].rstrip("0")) if "." in text else 0
    half = 0.5 * 10 ** -decimals
    if APPROX.search(quote or ""):
        half = max(half, APPROX_SLACK * abs(value))
    return value - half, value + half


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def _wording(quote: str) -> str | None:
    """How the claim states a change: percentage points, relative %, compound % per year, or a ratio."""
    q = (quote or "").lower()
    if re.search(r"percentage[- ]points?|\bpp\b|\bpoints?\b", q):
        return "pp"
    if re.search(r"per year|a year|annual|annually|cagr|each year|/yr", q):
        return "cagr"
    if re.search(r"\d\s*(x|times|-fold|fold)\b", q):
        return "ratio"
    if "%" in q or "percent" in q:
        return "pct"
    return None


def parse_key(sql: str | None, columns: list[str], entity_col: str | None = "country",
              time_col: str | None = "year") -> tuple[str, str, tuple[int, ...]] | None:
    """(column, entity, years) measured by a simple claim query, or None for comparisons / unclear SQL."""
    if not sql or not time_col or re.search(r"\bcase\s+when\b", sql, re.I):
        return None
    cols = {c for c in columns
            if c not in (entity_col, time_col) and re.search(rf"\b{re.escape(c)}\b", sql)}
    entities = set(re.findall(rf"\b{entity_col}\s*=\s*'([^']+)'", sql, re.I)) if entity_col else {""}
    years = tuple(sorted({int(y) for y in re.findall(rf"\b{time_col}\s*=\s*(\d{{4}})\b", sql, re.I)}))
    if len(cols) != 1 or len(entities) != 1 or not 1 <= len(years) <= 2:
        return None
    return cols.pop(), entities.pop(), years


def _change_interval(kind: str, a: tuple[float, float], b: tuple[float, float],
                     years: int) -> tuple[float, float] | None:
    if kind == "pp":
        return b[0] - a[1], b[1] - a[0]
    if a[0] <= 0 or b[0] < 0:
        return None
    lo, hi = b[0] / a[1], b[1] / a[0]
    if kind == "ratio":
        return lo, hi
    if kind == "pct":
        return 100 * (lo - 1), 100 * (hi - 1)
    if kind == "cagr" and years > 0:
        return 100 * (lo ** (1 / years) - 1), 100 * (hi ** (1 / years) - 1)
    return None


def _describe_change(a: float, b: float, years: int) -> str:
    parts = [f"{b - a:+.1f} percentage points" if abs(b) <= 100 and abs(a) <= 100 else f"{b - a:+g}"]
    if a > 0:
        parts.append(f"{100 * (b / a - 1):+.1f}%")
        if years > 1:
            parts.append(f"{100 * ((b / a) ** (1 / years) - 1):+.2f}% per year compounded")
    return ", ".join(parts)


def find_issues(claims: list[dict], columns: list[str], entity_col: str | None = "country",
                time_col: str | None = "year",
                shares: dict[str, list[str]] | None = None, share_total: float = 100.0) -> list[Issue]:
    """All internal inconsistencies among numeric claims. Pure function of the stated values."""
    points: dict[tuple, list[dict]] = {}
    changes: list[tuple[dict, tuple]] = []
    for c in claims:
        if c.get("kind") != "numeric" or not isinstance(c.get("stated_value"), (int, float)):
            continue
        key = parse_key(c.get("sql"), columns, entity_col, time_col)
        if key is None:
            continue
        col, entity, years = key
        if len(years) == 1:
            points.setdefault((col, entity, years[0]), []).append(c)
        else:
            changes.append((c, key))

    issues: list[Issue] = []
    known: dict[tuple, tuple[float, float]] = {}
    for (col, entity, year), cs in points.items():
        ivs = [_interval(float(c["stated_value"]), c["quote"]) for c in cs]
        lo, hi = max(i[0] for i in ivs), min(i[1] for i in ivs)
        if lo > hi:
            values = " vs ".join(f'{c["stated_value"]:g} (“{c["quote"]}”)' for c in cs)
            issues.append(Issue("duplicate", f"{col} for {entity} {year} is stated twice with different values: "
                                             f"{values}", suspects=list(cs)))
        else:
            known[(col, entity, year)] = (lo, hi)

    for c, (col, entity, (y1, y2)) in changes:
        kind = _wording(c["quote"])
        a, b = known.get((col, entity, y1)), known.get((col, entity, y2))
        if kind is None or a is None or b is None:
            continue
        computed = _change_interval(kind, a, b, y2 - y1)
        if computed is None:
            continue
        stated = _interval(float(c["stated_value"]), c["quote"])
        if stated[0] >= 0 and computed[1] < 0:  # "fell by 42 points" stated as a positive number
            computed = (-computed[1], -computed[0])
        if not _overlap(stated, computed):
            a_mid, b_mid = (a[0] + a[1]) / 2, (b[0] + b[1]) / 2
            ends = points[(col, entity, y1)] + points[(col, entity, y2)]
            word = {"pp": "percentage points", "pct": "%", "cagr": "% per year", "ratio": "x"}[kind]
            issues.append(Issue("change", f"the report's own figures {a_mid:g} ({y1}) -> {b_mid:g} ({y2}) give "
                                          f"{_describe_change(a_mid, b_mid, y2 - y1)}, but it states "
                                          f"{c['stated_value']:g} {word}".replace(" %", "%"),
                                suspects=[c], others=ends))

    for (entity, year) in {(e, y) for (_, e, y) in known}:
        issues += _share_issues(points, known, entity, year, shares or {}, share_total)
    return issues


def _share_issues(points: dict[tuple, list[dict]], known: dict[tuple, tuple[float, float]], entity: str,
                  year: int, shares: dict[str, list[str]], share_total: float) -> list[Issue]:
    def val(col: str) -> tuple[float, float] | None:
        return known.get((col, entity, year))

    issues: list[Issue] = []
    total_lo, used = 0.0, []
    for whole, parts in shares.items():
        part_vals = {p: v for p in parts if (v := val(p))}
        part_cols = list(part_vals)
        parts_lo = sum(v[0] for v in part_vals.values())
        whole_val = val(whole)
        if whole_val:
            if part_cols and parts_lo > whole_val[1]:
                involved = [c for p in part_cols for c in points[(p, entity, year)]]
                issues.append(Issue("parts", f"for {entity} {year}, {' + '.join(part_cols)} add up to more than "
                                             f"{whole} ({whole_val[0]:g}-{whole_val[1]:g})",
                                    suspects=involved + points[(whole, entity, year)]))
            total_lo += whole_val[0]
            used.append(whole)
        elif part_cols:
            total_lo += parts_lo
            used += part_cols
    if len(used) > 1 and total_lo > share_total + 1e-9:
        stated = " + ".join(f"{points[(col, entity, year)][0]['stated_value']:g} ({col})" for col in used)
        issues.append(Issue("shares", f"shares for {entity} {year} add up to more than {share_total:g}%: {stated}",
                            suspects=[c for col in used for c in points[(col, entity, year)]]))
    return issues


def apply_issues(claims: list[dict], issues: list[Issue]) -> list[dict]:
    """Mark suspects "inconsistent". Data wins: a contradicted claim stays contradicted (note added),
    and a data-verified claim is left alone when another claim in the same issue is contradicted."""
    for issue in issues:
        involved = issue.suspects + issue.others
        explained = any(c.get("status") == "contradicted" for c in involved)
        for c in issue.suspects:
            status = c.get("status")
            if status == "contradicted":
                c["note"] = (c.get("note") or "") + f"; also inconsistent: {issue.note}"
            elif status == "verified" and explained:
                continue
            else:
                c["status"], c["note"] = "inconsistent", issue.note
                c["actual"] = c.get("actual") if status == "verified" else None
    return claims

