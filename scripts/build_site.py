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

import duckdb  # noqa: E402
import yaml  # noqa: E402

from checker import llm  # noqa: E402
from checker.core import FLAGGED, recheck  # noqa: E402
from checker.dataset import Dataset, default_dataset  # noqa: E402
from checker.guardrails import Catalog, _literals, _numbers  # noqa: E402
from checker.highlight import _nest, _Span, locate  # noqa: E402
from checker.memo import review_memo  # noqa: E402
from checker.prompts import prompt_version  # noqa: E402
from evaluate import score  # noqa: E402

RESULTS = ROOT / "results"
BENCH = ROOT / "benchmark"
OUT = ROOT / "docs" / "data" / "site.js"
FROZEN_TAG = "v1.1-frozen"
# Every frozen configuration so far, so the run history can label its rows. Same prompts; different judges.
VERSIONS: list[dict] = [
    {"label": "v1.0", "prompt_version": "38701a08", "model": "gemini-3.5-flash-lite",
     "judge_model": "gemini-3.6-flash", "judge_votes": 1,
     "note": "A stronger judge model (gemini-3.6-flash). Its free tier allows about 20 calls a day, so the "
             "benchmark never finished."},
    {"label": "v1.1", "prompt_version": "38701a08", "model": "gemini-3.5-flash-lite",
     "judge_model": "gemini-3.5-flash-lite", "judge_votes": None,  # filled from the chosen setup
     "note": "One fast model for every step, which the free tier can finish. Same prompts as v1.0."},
]
LINKS = {
    "github": "https://github.com/eytanberko/report-checker",
    "demo": "https://report-checkerwitz.streamlit.app/",
    "linkedin": "https://www.linkedin.com/in/eytan-berkowitz",
    "data_source": "https://github.com/owid/energy-data",
}
DATA_SOURCE = "Our World in Data, energy dataset"
MAX_ROWS = 30  # rows shown under "Show the data" for one claim


def _clean(text: str) -> str:
    """Join the YAML's hard line wraps into one paragraph of running text."""
    return " ".join(text.split())


def segments(text: str, claims: list[dict]) -> tuple[list[dict], list[str]]:
    """Report text as nested segments: {"t": text} or {"c": claim id, "k": [children]}; plus unlocated ids."""
    spans: list[_Span] = []
    missing: list[str] = []
    for c in claims:
        loc = locate(text, c.get("quote", ""))
        if loc:
            spans.append(_Span(loc[0], loc[1], c))
        else:
            missing.append(c["id"])

    def walk(start: int, end: int, nodes: list[_Span]) -> list[dict]:
        out: list[dict] = []
        pos = start
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


def frozen_config() -> dict:
    """The frozen settings: what a result must have been made with to count as the frozen run."""
    return {"prompt_version": prompt_version(), "model": llm.MODEL, "judge_model": llm.JUDGE_MODEL,
            "judge_votes": llm.JUDGE_VOTES}


def is_frozen(meta: dict, config: dict) -> bool:
    """True when a saved result was made with exactly the frozen settings (prompts, both models, judge votes).
    Results from before judge votes existed used a single judge call."""
    return all(meta.get(k, 1 if k == "judge_votes" else None) == v for k, v in config.items())


def claim_rows(con: duckdb.DuckDBPyConnection, catalog: Catalog, ds: Dataset, sql: str | None) -> dict | None:
    """The dataset rows a claim's query read: its countries and years, with the columns it used.

    Read from the SQL text (no LLM): the entity and year filters and every data column it names.
    None when the claim has no query, names no data column, or filters on nothing narrower than the whole table."""
    if not sql or not ds.entity_col or not ds.time_col:
        return None
    cols = [c for c in catalog.columns
            if c not in (ds.entity_col, ds.time_col) and re.search(r"\b" + re.escape(c) + r"\b", sql)]
    entities = sorted(set(_literals(sql, ds.entity_col)))
    years = sorted({int(v) for v in _numbers(sql, ds.time_col)})
    if not cols or not (entities or years):
        return None
    where: list[str] = []
    params: list[object] = []
    if entities:
        where.append(f'"{ds.entity_col}" IN ({", ".join("?" * len(entities))})')
        params += entities
    if years:
        where.append(f'"{ds.time_col}" IN ({", ".join("?" * len(years))})')
        params += years
    columns = [ds.entity_col, ds.time_col, *cols]
    select = ", ".join(f'"{c}"' for c in columns)
    rows = con.execute(f'SELECT {select} FROM "{ds.table}" WHERE {" AND ".join(where)} '
                       f"ORDER BY 1, 2 LIMIT {MAX_ROWS}", params).fetchall()
    fmt = lambda v: round(v, 2) if isinstance(v, float) else v  # noqa: E731
    return {"columns": columns, "rows": [[fmt(v) for v in row] for row in rows],
            "filters": {"entities": entities, "years": years}}


def requirement_flag(text: str, requirement: dict, claims: list[dict]) -> str | None:
    """For an answered requirement whose evidence quote contains a flagged claim: "contradicted" (a wrong figure)
    or "unsupported" (an unsupported conclusion). Display only; the result itself is not changed."""
    evidence = requirement.get("evidence")
    if requirement.get("status") != "covered" or not isinstance(evidence, str) or not evidence.strip():
        return None
    span = locate(text, evidence)
    hits = set()
    for c in claims:
        if c["status"] not in ("contradicted", "inconsistent", "unsupported"):
            continue
        cs = locate(text, c["quote"])
        if (span and cs and cs[0] < span[1] and span[0] < cs[1]) or c["quote"].lower() in evidence.lower():
            hits.add("contradicted" if c["status"] != "unsupported" else "unsupported")
    return "contradicted" if "contradicted" in hits else "unsupported" if hits else None


def report_entry(rep: dict, config: dict, con: duckdb.DuckDBPyConnection | None = None,
                 catalog: Catalog | None = None, ds: Dataset | None = None,
                 results_dir: Path | None = None) -> dict | None:
    path = (results_dir or RESULTS) / f"{rep['id']}.json"
    if not path.exists():
        return None
    text = _clean(rep["text"])
    result = recheck(json.loads(path.read_text(encoding="utf-8")), text)
    s = score(rep, result)
    meta = result.get("meta", {})
    segs, missing = segments(text, result["claims"])
    flagged_ids = {c["id"] for c in result["claims"] if c["status"] in FLAGGED}
    if ds is None or con is None or catalog is None:
        ds = default_dataset()
        con = ds.connect()
        catalog = ds.catalog(con)
    number = rep["id"].split("_")[-1]
    claims = []
    for c in result["claims"]:
        entry = {k: c.get(k) for k in ("id", "kind", "quote", "status", "note", "actual", "stated_value", "sql")}
        entry["data"] = claim_rows(con, catalog, ds, c.get("sql"))
        claims.append(entry)
    return {
        "id": rep["id"],
        "number": number,
        "text": text,
        "segments": segs,
        "unlocated": missing,
        "claims": claims,
        "requirements": [{**{k: r.get(k) for k in ("id", "status", "reason", "evidence")},
                          "flag": requirement_flag(text, r, result["claims"])}
                         for r in result.get("requirements", [])],
        "memo": review_memo(result, f"Report {number}"),
        "run": {"prompt_version": meta.get("prompt_version", "legacy"), "model": meta.get("model"),
                "judge_model": meta.get("judge_model", meta.get("model")), "judge_votes": meta.get("judge_votes", 1),
                "frozen": is_frozen(meta, config)},
        "answer_key": {
            "planted": [{"type": e["type"], "target": e.get("match") or e.get("requirement"),
                         "why": e.get("why"), "caught": e in s["caught"]} for e in rep["planted"]],
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


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def heldout_block(config: dict, con: duckdb.DuckDBPyConnection, catalog: Catalog, ds: Dataset) -> dict | None:
    """The held-out test: its metrics and, per report, what was planted and whether it was caught."""
    metrics = _load(RESULTS / "heldout" / "metrics.json")
    if metrics is None:
        return None
    reps = yaml.safe_load((BENCH / "holdout.yaml").read_text(encoding="utf-8"))["reports"]
    entries = [report_entry(r, config, con, catalog, ds, RESULTS / "heldout") for r in reps]
    return {"metrics": metrics,
            "reports": [{"id": e["id"], "answer_key": e["answer_key"], "run": e["run"]} for e in entries if e]}


def repeats_block() -> list[dict]:
    """Repeat runs of the frozen settings that bypass the cache: how much the results vary between runs."""
    out = []
    for path in sorted((RESULTS / "repeats").glob("r*/metrics.json")):
        m = _load(path)
        if m is None:
            continue
        out.append({"run": path.parent.name, "complete": m["reports_scored"] == m["reports_total"],
                    **{k: m.get(k) for k in ("recall", "precision", "caught", "planted", "false_alarms",
                                             "reports_scored", "reports_total")}})
    return out


def build() -> dict:
    """Everything the site renders, as one JSON-serialisable dict."""
    reports_yaml = yaml.safe_load((BENCH / "reports.yaml").read_text(encoding="utf-8"))["reports"]
    config = frozen_config()
    ds = default_dataset()
    con = ds.connect()
    catalog = ds.catalog(con)
    return {
        "links": LINKS,
        "data_source": DATA_SOURCE,
        "config": {"tag": FROZEN_TAG, "label": FROZEN_TAG.split("-")[0], **config},
        "versions": [{**v, "judge_votes": v["judge_votes"] or config["judge_votes"]} for v in VERSIONS],
        "requirements": requirements_list((BENCH / "requirements.md").read_text(encoding="utf-8")),
        "reports": [e for e in (report_entry(r, config, con, catalog, ds) for r in reports_yaml) if e],
        "metrics": _load(RESULTS / "metrics.json"),
        "history": history_rows(),
        "heldout": heldout_block(config, con, catalog, ds),
        "repeats": repeats_block(),
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
