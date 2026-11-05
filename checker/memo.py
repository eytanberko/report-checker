"""Review memo: the feedback a team lead would send the analyst, as Markdown.

Deterministic: built only from the check result, no LLM call.
"""
import re

# Claim statuses that mean a number in the report is wrong (highest severity).
NUMBER_STATUSES = ("contradicted", "inconsistent")


def _fmt(x: float) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def _number_item(c: dict) -> str:
    if c["status"] == "inconsistent":
        says = f'The report\'s own numbers don\'t agree: {c.get("note") or "see details"}.'
        fix = "Recompute from the source values and make the figures in the text agree with each other."
    elif c.get("actual") is None:
        says, fix = c.get("note") or "", "Correct the figure against the data."
    else:
        actual = _fmt(c["actual"])
        says = f"The data says **{actual}**."
        if len(set(re.findall(r"\b(?:19|20)\d\d\b", c.get("sql") or ""))) >= 2:  # a change between two years
            fix = (f"Correct it to {actual}, or reword it if a different measure was meant "
                   "(percentage points vs %, simple vs compound growth).")
        else:
            fix = f"Correct it to {actual} (check the year and country the figure was taken from)."
    return f'- “{c["quote"]}”  \n  {says}  \n  *Fix:* {fix}'


def _requirement_item(r: dict) -> str:
    gap = "not answered" if r["status"] == "missing" else "only partly answered"
    reason = r.get("reason") or ""
    return (f'- **{r["id"]}** is {gap}. {reason}  \n'
            f"  *Fix:* answer exactly what the client asked (same period, comparison group and metric).")


def _unsupported_item(c: dict) -> str:
    return (f'- “{c["quote"]}”  \n  {c.get("note") or "Not supported by the data."}  \n'
            "  *Fix:* support it with a figure from the data, soften it to what the data shows, or remove it.")


def _unverifiable_item(c: dict) -> str:
    return (f'- “{c["quote"]}”  \n  Could not be checked ({c.get("note") or "no query"}).  \n'
            "  *Fix:* make sure it is stated precisely (metric, country, year) or cite its source.")


def review_memo(result: dict, title: str = "the report") -> str:
    """Markdown feedback for the analyst, issues grouped by severity, each with quote, evidence and a fix."""
    claims = result.get("claims", [])
    groups = [
        ("Wrong numbers", [_number_item(c) for c in claims if c.get("status") in NUMBER_STATUSES]),
        ("Requirements not met", [_requirement_item(r) for r in result.get("requirements", [])
                                  if r.get("status") != "covered"]),
        ("Unsupported conclusions", [_unsupported_item(c) for c in claims if c.get("status") == "unsupported"]),
        ("Could not verify", [_unverifiable_item(c) for c in claims if c.get("status") == "unverifiable"]),
    ]
    n_issues = sum(len(items) for _, items in groups)
    ok = sum(c.get("status") in ("verified", "supported") for c in claims)

    lines = [f"# Review: {title}", ""]
    if n_issues == 0:
        lines += [f"All {len(claims)} claims check out against the data and every client requirement is covered. "
                  "Good to send.", ""]
    else:
        lines += [f"Thanks for the draft. {ok} of {len(claims)} claims check out against the data; "
                  f"{n_issues} issue{'s' if n_issues != 1 else ''} to fix before it goes to the client, "
                  "most important first.", ""]
        for i, (name, items) in enumerate([g for g in groups if g[1]], 1):
            lines += [f"## {i}. {name} ({len(items)})", "", *items, ""]

    mismatches = [c for c in claims if c.get("status") == "query_mismatch"]
    if mismatches or result.get("errors"):
        lines += ["## Checker notes (not errors in the report)", "",
                  *[f'- “{c["quote"]}”: not checked, {c.get("note", "")}' for c in mismatches],
                  *[f"- {e}" for e in result.get("errors", [])], ""]
    if n_issues:
        lines += ["Please send the revised version when these are fixed."]
    return "\n".join(lines).rstrip() + "\n"
