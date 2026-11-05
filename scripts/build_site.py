"""Builds the showcase site's data, docs/data/site.js, from results/, benchmark/ and the checker itself.

    python scripts/build_site.py        # run after every benchmark run, then commit docs/

Saved results are re-checked with the current deterministic stages (no LLM, no API key), exactly as the
app and the CLI do. A held-out result appears once results/heldout/metrics.json exists; until then the site
shows a placeholder.

Fonts in docs/fonts are self-hosted from Google Fonts (SIL Open Font License), latin subset.
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from checker import llm  # noqa: E402
from checker.core import FLAGGED, recheck  # noqa: E402
from checker.highlight import _nest, _Span, locate  # noqa: E402
from checker.memo import review_memo  # noqa: E402
from checker.prompts import prompt_version  # noqa: E402
from evaluate import score  # noqa: E402

RESULTS = ROOT / "results"
BENCH = ROOT / "benchmark"
OUT = ROOT / "docs" / "data" / "site.js"
FROZEN_TAG = "v1.0-frozen"
LINKS = {
    "github": "https://github.com/eytanberko/report-checker",
    "demo": "https://report-checkerwitz.streamlit.app/",
    "linkedin": "https://www.linkedin.com/in/eytan-berkowitz",
}


def _clean(text: str) -> str:
    """Join the YAML's hard line wraps into one paragraph of running text."""
    return " ".join(text.split())


def segments(text: str, claims: list[dict]) -> tuple[list[dict], list[str]]:
    """Report text as nested segments: {"t": text} or {"c": claim id, "k": [children]}; plus unlocated ids."""
    spans, missing = [], []
    for c in claims:
        loc = locate(text, c.get("quote", ""))
        if loc:
            spans.append(_Span(loc[0], loc[1], c))
        else:
            missing.append(c["id"])

    def walk(start: int, end: int, nodes: list[_Span]) -> list[dict]:
        out, pos = [], start
        for n in nodes:
            if n.start > pos:
                out.append({"t": text[pos:n.start]})
            out.append({"c": n.claim["id"], "k": walk(n.start, n.end, n.children)})
            pos = n.end
        if end > pos:
            out.append({"t": text[pos:end]})
        return out

    return walk(0, len(text), _nest(spans)), missing


def requirements_list(md: str) -> list[dict]:
    """The client's requirements, from lines like '- **R1**: ...'."""
    return [{"id": rid, "text": text.strip()} for rid, text in re.findall(r"\*\*(R\d+)\*\*:\s*(.+)", md)]


def report_entry(rep: dict, frozen_version: str) -> dict | None:
    path = RESULTS / f"{rep['id']}.json"
    if not path.exists():
        return None
    text = _clean(rep["text"])
    result = recheck(json.loads(path.read_text(encoding="utf-8")), text)
    s = score(rep, result)
    meta = result.get("meta", {})
    segs, missing = segments(text, result["claims"])
    flagged_ids = {c["id"] for c in result["claims"] if c["status"] in FLAGGED}
    return {
        "id": rep["id"],
        "author": rep["author"],
        "text": text,
        "segments": segs,
        "unlocated": missing,
        "claims": [{k: c.get(k) for k in ("id", "kind", "quote", "status", "note", "actual", "stated_value", "sql")}
                   for c in result["claims"]],
        "requirements": [{k: r.get(k) for k in ("id", "status", "reason", "evidence")}
                         for r in result.get("requirements", [])],
        "memo": review_memo(result, f"{rep['id']} ({rep['author']})"),
        "run": {"prompt_version": meta.get("prompt_version", "legacy"), "model": meta.get("model"),
                "judge_model": meta.get("judge_model", meta.get("model")),
                "frozen": meta.get("prompt_version") == frozen_version},
        "answer_key": {
            "planted": [{"type": e["type"], "target": e.get("match") or e.get("requirement"),
                         "caught": e in s["caught"]} for e in rep["planted"]],
            "cascade": [c["id"] for c in s["cascade"]],
            "false_alarms": [{"id": a["id"], "quote": a["quote"]} for a in s["false_alarms"]],
            "flagged": sorted(flagged_ids, key=lambda i: int(i.lstrip("CR") or 0)),
        },
    }


def history_rows() -> list[dict]:
    path = RESULTS / "history.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def build() -> dict:
    """Everything the site renders, as one JSON-serialisable dict."""
    reports_yaml = yaml.safe_load((BENCH / "reports.yaml").read_text(encoding="utf-8"))["reports"]
    frozen_version = prompt_version()
    heldout_path = RESULTS / "heldout" / "metrics.json"
    metrics_path = RESULTS / "metrics.json"
    return {
        "links": LINKS,
        "config": {"tag": FROZEN_TAG, "prompt_version": frozen_version,
                   "model": llm.MODEL, "judge_model": llm.JUDGE_MODEL},
        "requirements": requirements_list((BENCH / "requirements.md").read_text(encoding="utf-8")),
        "reports": [e for e in (report_entry(r, frozen_version) for r in reports_yaml) if e],
        "metrics": json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None,
        "history": history_rows(),
        "heldout": json.loads(heldout_path.read_text(encoding="utf-8")) if heldout_path.exists() else None,
    }


def main() -> int:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("// Generated by scripts/build_site.py; do not edit by hand.\nwindow.SITE = "
                   + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    n_unlocated = sum(len(r["unlocated"]) for r in data["reports"])
    print(f"wrote {OUT.relative_to(ROOT)}: {len(data['reports'])} reports, "
          f"{sum(len(r['claims']) for r in data['reports'])} claims ({n_unlocated} unlocated), "
          f"held-out: {'yes' if data['heldout'] else 'pending'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
