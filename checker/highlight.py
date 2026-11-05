"""Locate each claim's quote in the report and render the report with claims highlighted in place.

Pure Python (no Streamlit) so it can be unit-tested and reused for saved results.
"""
import html
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# status -> highlight colour name (CSS class suffix)
STATUS_COLOR = {
    "verified": "green", "supported": "green",
    "contradicted": "red",
    "unsupported": "yellow", "unverifiable": "yellow",
    "inconsistent": "orange",
    "query_mismatch": "grey",
}
FUZZY_MIN = 0.75  # minimum similarity for a fuzzy quote match

CSS = """<style>
.rc-report {line-height: 2.0; font-size: 1.02rem;}
.rc-claim {border-radius: 4px; padding: 1px 2px; cursor: help;}
.rc-claim sup {font-size: .62em; opacity: .75; margin-left: 2px;}
.rc-green  {background: rgba(34,197,94,.20);  border-bottom: 2px solid rgba(34,197,94,.9);}
.rc-red    {background: rgba(239,68,68,.24);  border-bottom: 2px solid rgba(239,68,68,.95);}
.rc-yellow {background: rgba(234,179,8,.26);  border-bottom: 2px solid rgba(234,179,8,.95);}
.rc-orange {background: rgba(249,115,22,.28); border-bottom: 2px solid rgba(249,115,22,.95);}
.rc-grey   {background: rgba(148,163,184,.22); border-bottom: 2px dashed rgba(148,163,184,.95);}
</style>"""


def locate(text: str, quote: str) -> tuple[int, int] | None:
    """Return the (start, end) span of `quote` in `text`: exact, then whitespace/case-insensitive, then fuzzy."""
    if not quote or not quote.strip():
        return None
    i = text.find(quote)
    if i >= 0:
        return i, i + len(quote)
    pattern = r"\s+".join(re.escape(w) for w in quote.split())
    m = re.search(pattern, text, re.I)
    if m:
        return m.span()
    return _fuzzy_locate(text, quote)


def _fuzzy_locate(text: str, quote: str) -> tuple[int, int] | None:
    """Best-matching window of words, if similar enough (handles paraphrased or retyped quotes)."""
    tokens = [m.span() for m in re.finditer(r"\S+", text)]
    target = " ".join(quote.lower().split())
    n = len(quote.split())
    best_ratio, best_span = 0.0, None
    for size in range(max(1, n - 2), n + 3):
        for i in range(len(tokens) - size + 1):
            s, e = tokens[i][0], tokens[i + size - 1][1]
            ratio = SequenceMatcher(None, target, " ".join(text[s:e].lower().split())).ratio()
            if ratio > best_ratio:
                best_ratio, best_span = ratio, (s, e)
    if best_ratio < FUZZY_MIN or best_span is None:
        return None
    s, e = best_span
    while e > s and text[e - 1] in ".,;:":  # don't swallow trailing punctuation
        e -= 1
    return s, e


@dataclass
class _Span:
    start: int
    end: int
    claim: dict
    children: list["_Span"] = field(default_factory=list)


def _nest(spans: list[_Span]) -> list[_Span]:
    """Arrange spans into a tree. Partial overlaps are clipped so the HTML stays well-nested."""
    roots: list[_Span] = []
    stack: list[_Span] = []
    for sp in sorted(spans, key=lambda s: (s.start, -s.end)):
        while True:
            while stack and stack[-1].end <= sp.start:
                stack.pop()
            if stack and sp.end > stack[-1].end:  # partial overlap: start after the enclosing span
                sp.start = stack[-1].end
                continue
            break
        if sp.start >= sp.end:
            continue
        (stack[-1].children if stack else roots).append(sp)
        stack.append(sp)
    return roots


def _esc(s: str) -> str:
    return html.escape(s).replace("\n\n", "<br><br>").replace("\n", " ")


def _tooltip(c: dict) -> str:
    parts = [f'{c.get("id", "?")} · {c.get("status", "?").upper()}']
    if c.get("actual") is not None:
        parts.append(f'data: {c["actual"]:g}')
    if c.get("note"):
        parts.append(c["note"])
    return html.escape(" — ".join(parts), quote=True)


def _render(text: str, start: int, end: int, nodes: list[_Span]) -> str:
    out, pos = [], start
    for n in nodes:
        color = STATUS_COLOR.get(n.claim.get("status"), "grey")
        out.append(_esc(text[pos:n.start]))
        out.append(f'<span class="rc-claim rc-{color}" title="{_tooltip(n.claim)}">')
        out.append(_render(text, n.start, n.end, n.children))
        out.append(f'<sup>{html.escape(str(n.claim.get("id", "")))}</sup></span>')
        pos = n.end
    out.append(_esc(text[pos:end]))
    return "".join(out)


def render_html(text: str, claims: list[dict]) -> tuple[str, list[dict]]:
    """Report text as HTML with every locatable claim highlighted by status.

    Returns (html, claims that could not be located in the text).
    """
    spans, missing = [], []
    for c in claims:
        loc = locate(text, c.get("quote", ""))
        if loc:
            spans.append(_Span(loc[0], loc[1], c))
        else:
            missing.append(c)
    body = _render(text, 0, len(text), _nest(spans))
    return f'{CSS}<div class="rc-report">{body}</div>', missing


def verdict(result: dict, flagged: set[str]) -> tuple[str, str]:
    """One-line verdict, e.g. "3 of 9 claims flagged, 1 requirement not covered", with a level ok|warn|error."""
    claims = result.get("claims", [])
    n_flag = sum(c.get("status") in flagged for c in claims)
    n_req = sum(r.get("status") != "covered" for r in result.get("requirements", []))
    n_mismatch = sum(c.get("status") == "query_mismatch" for c in claims)
    text = (f"{n_flag} of {len(claims)} claims flagged, "
            f"{n_req} requirement{'' if n_req == 1 else 's'} not covered")
    if n_mismatch:
        text += f" ({n_mismatch} check{'' if n_mismatch == 1 else 's'} skipped: query didn't match the claim)"
    level = "ok" if not (n_flag or n_req) else "error" if any(
        c.get("status") in ("contradicted", "inconsistent") for c in claims) else "warn"
    return level, text
