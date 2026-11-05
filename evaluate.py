"""Runs the checker on every benchmark report and scores it against the planted errors.

  python evaluate.py            run what's needed: reports already finished with the current model and
                                prompt version are reused (free); the rest call the LLM, throttled.
                                Stops cleanly on a daily-quota error; re-run later to resume.
  python evaluate.py --offline  never call the API: score the saved results that exist

Writes results/<report>.json, results/metrics.md + metrics.json, and appends a row to results/history.csv.
Exit code: 0 = all reports scored, 3 = stopped early (quota / LLM error) or partial.
"""
import argparse
import csv
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from checker import llm
from checker.core import FLAGGED, check_report, recheck
from checker.highlight import locate
from checker.prompts import prompt_version

BENCH = Path(__file__).resolve().parent / "benchmark"
OUT = Path(__file__).resolve().parent / "results"
DEFAULT_OUT = OUT
HISTORY_FIELDS = ["timestamp", "mode", "model", "judge_model", "judge_votes", "prompt_version", "reports_scored",
                  "reports_total",
                  "recall", "precision", "false_alarms", "cascade", "query_mismatches",
                  "api_calls", "cache_hits", "seconds", "status"]


def _requirement_cascades(report: dict, result: dict, flagged: list[dict], candidates: set[str]) -> set[str]:
    """General rule: a requirement marked partial/missing is a cascade of a planted claim error when its
    evidence quote contains that error's match, or overlaps (in the report text) a claim the checker flagged."""
    matches = [e["match"].lower() for e in report["planted"] if e.get("match")]
    flagged_spans = [s for s in (locate(report["text"], c["quote"]) for c in flagged) if s]
    out = set()
    for r in result["requirements"]:
        evidence = r.get("evidence")
        if r["id"] not in candidates or not isinstance(evidence, str) or not evidence.strip():
            continue
        span = locate(report["text"], evidence)
        if any(m in evidence.lower() for m in matches) or \
                (span and any(s[0] < span[1] and span[0] < s[1] for s in flagged_spans)):
            out.add(r["id"])
    return out


MIN_INSIDE = 12  # a flagged quote this long or longer that sits inside a sentence-long match counts for it


def _squash(text: str) -> str:
    return " ".join(text.lower().split()).strip(" .;:,")


def _flags_for(match: str, flagged: list[dict]) -> list[dict]:
    """Flagged claims that are this planted error: the quote contains the match, or (for a sentence-long match)
    the quote is a substantial part of it."""
    m = _squash(match)
    return [c for c in flagged if m in _squash(c["quote"])
            or (len(_squash(c["quote"])) >= MIN_INSIDE and _squash(c["quote"]) in m)]


def _requirements_at(report: dict, result: dict, match: str, not_covered: set[str]) -> list[str]:
    """Requirements marked partial/missing whose evidence quote overlaps the given sentence of the report."""
    target = locate(report["text"], match)
    out = []
    for r in result["requirements"]:
        evidence = r.get("evidence")
        if r["id"] not in not_covered or not isinstance(evidence, str) or not evidence.strip():
            continue
        span = locate(report["text"], evidence)
        if (target and span and span[0] < target[1] and target[0] < span[1]) or _squash(match) in _squash(evidence):
            out.append(r["id"])
    return out


def score(report: dict, result: dict) -> dict:
    """Match a result's flags to the report's planted errors: caught, missed, cascade, false alarms."""
    flagged = [c for c in result["claims"] if c["status"] in FLAGGED]
    not_covered = {r["id"] for r in result["requirements"] if r["status"] != "covered"}
    caught, missed, used = [], [], set()

    for err in report["planted"]:
        if err["type"] in ("missing_requirement", "misread_requirement") and err.get("requirement"):
            hit = err["requirement"] in not_covered
            if hit:
                used.add(err["requirement"])
        elif err["type"] in ("missing_requirement", "misread_requirement"):
            # Given as the offending sentence: caught when a requirement marked partial/missing is answered by
            # that sentence (its evidence overlaps it), or when a flagged claim sits inside it.
            reqs = _requirements_at(report, result, err["match"], not_covered)
            matches = _flags_for(err["match"], flagged)
            hit = bool(reqs or matches)
            used |= set(reqs) | {c["id"] for c in matches}
        else:
            # Every flag that contains the match (or sits inside a sentence-long match) is this one error:
            # counted once, never a false alarm.
            matches = _flags_for(err["match"], flagged)
            hit = bool(matches)
            used |= {c["id"] for c in matches}
        (caught if hit else missed).append(err)

    # Downstream "cascade" errors caused by a planted error: neither false alarms nor extra recall.
    also = [m.lower() for e in report["planted"] for m in e.get("also", [])]
    also_reqs = {r for e in report["planted"] for r in e.get("also_requirements", [])}
    also_reqs |= _requirement_cascades(report, result, flagged, not_covered - used)
    cascade = [c for c in flagged if c["id"] not in used and any(m in c["quote"].lower() for m in also)]
    cascade += [{"id": r, "quote": f"requirement {r} marked not covered"}
                for r in sorted((not_covered - used) & also_reqs)]
    used |= {c["id"] for c in cascade}

    false_alarms = [c for c in flagged if c["id"] not in used] + \
                   [{"id": r, "quote": f"requirement {r} marked not covered"} for r in sorted(not_covered - used)]
    return {"caught": caught, "missed": missed, "cascade": cascade, "false_alarms": false_alarms}


META_DEFAULTS = {"judge_votes": 1, "cache_salt": ""}  # what results saved before these settings existed used


def run_meta() -> dict:
    """What a result must have been made with to be reused: models, judge votes, prompt version, cache namespace."""
    return {"model": llm.MODEL, "judge_model": llm.JUDGE_MODEL, "judge_votes": llm.JUDGE_VOTES,
            "prompt_version": prompt_version(), "cache_salt": llm.SALT}


def fmt_time(stamp: str) -> str:
    """'2026-11-05 09:17 UTC' -> '5 Nov 2026, 09:17 UTC' (the stored format stays sortable)."""
    try:
        t = datetime.strptime(stamp.replace(" UTC", ""), "%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return stamp
    return f"{t.day} {t:%b %Y, %H:%M}" + (" UTC" if "UTC" in stamp else "")


def load_result(rep: dict) -> tuple[dict | None, bool]:
    """(saved result with deterministic stages re-run, whether it was made with the current model+prompts)."""
    path = OUT / f"{rep['id']}.json"
    if not path.exists():
        return None, False
    saved = json.loads(path.read_text(encoding="utf-8"))
    meta = saved.get("meta", {})
    current = all(meta.get(k, META_DEFAULTS.get(k)) == v for k, v in run_meta().items())
    return recheck(saved, rep["text"]), current


def metrics(reports: list[dict], scored: dict[str, tuple[dict, dict]]) -> dict:
    """Aggregate scores over the reports that have a result."""
    by_type_total, by_type_caught, rows = Counter(), Counter(), []
    alarms = cascade = mismatches = 0
    for rep in reports:
        if rep["id"] not in scored:
            rows.append({"report": rep["id"], "planted": len(rep["planted"]), "scored": False})
            continue
        result, s = scored[rep["id"]]
        for e in rep["planted"]:
            by_type_total[e["type"]] += 1
        for e in s["caught"]:
            by_type_caught[e["type"]] += 1
        n_mismatch = sum(c["status"] == "query_mismatch" for c in result["claims"])
        alarms += len(s["false_alarms"])
        cascade += len(s["cascade"])
        mismatches += n_mismatch
        rows.append({"report": rep["id"], "planted": len(rep["planted"]), "scored": True,
                     "caught": len(s["caught"]), "cascade": len(s["cascade"]),
                     "false_alarms": len(s["false_alarms"]), "query_mismatches": n_mismatch,
                     "prompt_version": result.get("meta", {}).get("prompt_version", "legacy"),
                     "missed": [e.get("match") or e.get("requirement") for e in s["missed"]],
                     "false_alarm_details": [a["quote"][:60] for a in s["false_alarms"]]})
    planted, caught = sum(by_type_total.values()), sum(by_type_caught.values())
    return {
        "reports_scored": len(scored), "reports_total": len(reports),
        "planted": planted, "caught": caught,
        "recall": caught / planted if planted else None,
        "precision": caught / (caught + alarms) if caught + alarms else None,
        "false_alarms": alarms, "cascade": cascade, "query_mismatches": mismatches,
        "by_type": [{"type": t, "caught": by_type_caught[t], "planted": n} for t, n in by_type_total.items()],
        "by_report": rows,
        "prompt_versions": sorted({r["prompt_version"] for r in rows if r.get("scored")}),
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def to_markdown(m: dict, run: dict) -> str:
    """metrics.md: headline metrics, per-type and per-report tables."""
    versions = ", ".join(f"`{v}`" for v in m["prompt_versions"]) or "none"
    lines = ["# Benchmark results\n",
             f"Models: extraction `{run['model']}`, judge `{run['judge_model']}`; prompt version(s) {versions}; "
             f"run {fmt_time(run['timestamp'])} ({run['mode']}).",
             ""]
    if m["reports_scored"] < m["reports_total"]:
        lines += [f"> **Partial:** {m['reports_scored']} of {m['reports_total']} reports scored.", ""]
    lines += [f"- **Recall** (planted errors caught): {m['caught']}/{m['planted']} = {_pct(m['recall'])}",
              f"- **Precision** (flags that were real errors): {_pct(m['precision'])}",
              f"- **False alarms**: {m['false_alarms']} across {m['reports_scored']} reports",
              f"- **Cascade errors caught** (downstream of a planted error; not in recall or precision): "
              f"{m['cascade']}",
              f"- **Query mismatches** (checker-side, the claim was not checked; not counted): "
              f"{m['query_mismatches']}\n",
              "## By error type\n", "| type | caught | planted |", "|---|---|---|",
              *[f"| {t['type']} | {t['caught']} | {t['planted']} |" for t in m["by_type"]],
              "\n## By report\n",
              "| report | planted | caught | cascade | false alarms | false-alarm details |",
              "|---|---|---|---|---|---|"]
    for r in m["by_report"]:
        if r["scored"]:
            lines.append(f"| {r['report']} | {r['planted']} | {r['caught']} | {r['cascade']} | "
                         f"{r['false_alarms']} | {'; '.join(r['false_alarm_details'])} |")
        else:
            lines.append(f"| {r['report']} | {r['planted']} | not run | | | |")
    return "\n".join(lines) + "\n"


def append_history(m: dict, run: dict) -> None:
    """One row per run in results/history.csv, to compare metrics across prompt versions."""
    path = OUT / "history.csv"
    if path.exists():  # older files lack newer columns: rewrite them once (judge_model was the same model)
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            old_fields, rows = reader.fieldnames, list(reader)
        if old_fields != HISTORY_FIELDS:
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
                w.writeheader()
                w.writerows({k: r.get(k) or {"judge_model": r.get("model", ""), "judge_votes": "1"}.get(k, "")
                             for k in HISTORY_FIELDS} for r in rows)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        if new:
            w.writeheader()
        w.writerow({**{k: run.get(k, 1 if k == "judge_votes" else "") for k in (
                        "timestamp", "mode", "model", "judge_model", "judge_votes", "api_calls", "cache_hits",
                        "seconds", "status")},
                    "prompt_version": "+".join(m["prompt_versions"]),
                    **{k: m[k] for k in ("reports_scored", "reports_total", "false_alarms", "cascade",
                                         "query_mismatches")},
                    "recall": "" if m["recall"] is None else round(m["recall"], 3),
                    "precision": "" if m["precision"] is None else round(m["precision"], 3)})


def refresh_site() -> None:
    """Rebuild the showcase's data (docs/data/site.js) from the results just written, so the site follows each run
    with no manual step: e.g. the "earlier run" labels disappear once a report is re-scored with the frozen settings."""
    # the benchmark, held-out and repeat folders under results/ feed the site; tests and ad-hoc folders do not
    if OUT.resolve() != DEFAULT_OUT.resolve() and DEFAULT_OUT.resolve() not in OUT.resolve().parents:
        return
    from scripts import build_site
    build_site.main()


def main(argv: list[str] | None = None) -> int:
    """Run (or resume) the benchmark; see the module docstring."""
    global OUT
    parser = argparse.ArgumentParser(description="Run the Report Checker benchmark.")
    parser.add_argument("--offline", action="store_true", help="never call the API; score saved results")
    parser.add_argument("--reports", default=str(BENCH / "reports.yaml"), help="reports + answer key (YAML)")
    parser.add_argument("--out", help="folder for results, metrics and history (default: results/)")
    parser.add_argument("--judge-model", help="judge model (default: llm.JUDGE_MODEL)")
    parser.add_argument("--votes", type=int, help="judge votes per report; majority wins (default: llm.JUDGE_VOTES)")
    parser.add_argument("--salt", help="separate cache namespace: a repeat run that bypasses the main cache")
    args = parser.parse_args(argv)
    if args.out:
        OUT = Path(args.out)
    if args.judge_model:
        llm.JUDGE_MODEL = args.judge_model
    if args.votes:
        llm.JUDGE_VOTES = args.votes
    if args.salt:
        llm.SALT = args.salt
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    reports = yaml.safe_load(Path(args.reports).read_text(encoding="utf-8"))["reports"]
    requirements = (BENCH / "requirements.md").read_text(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    llm.OFFLINE = llm.OFFLINE or args.offline
    calls0, hits0, t0 = llm.stats["calls"], llm.stats["cache_hits"], time.monotonic()
    run = {**run_meta(), "mode": "offline" if llm.OFFLINE else "live",
           "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    salt = f", cache salt {llm.SALT}" if llm.SALT else ""
    print(f"extraction {run['model']}, judge {run['judge_model']} x{run['judge_votes']}, "
          f"prompt version {run['prompt_version']}, mode {run['mode']}{salt}")

    scored, stopped = {}, None
    for rep in reports:
        result, current = load_result(rep)
        if result is not None and (current or llm.OFFLINE):
            print(f"{rep['id']}: saved result" + ("" if current else " (older prompt version)"))
        elif llm.OFFLINE or stopped is not None:
            print(f"{rep['id']}: not run")
            continue
        else:
            print(f"{rep['id']}: checking ...")
            try:
                llm.start_report()
                result = check_report(rep["text"], requirements, ask=llm.ask_json, judge_ask=llm.ask_judge,
                                      judge_votes=llm.JUDGE_VOTES)
            except llm.LLMError as e:
                stopped = " ".join(str(e).split())[:200]  # one line, so history.csv stays readable
                print(f"\nSTOPPED: {e}\nFinished reports are saved; run `python evaluate.py` again to resume.\n")
                continue
            result["meta"] = {**run_meta(), "finished": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            (OUT / f"{rep['id']}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                                   encoding="utf-8")
        scored[rep["id"]] = (result, score(rep, result))

    llm._report_overloads = None  # the per-report retry budget ends with the benchmark loop
    m = metrics(reports, scored)
    complete = len(scored) == len(reports) and stopped is None
    run.update(api_calls=llm.stats["calls"] - calls0, cache_hits=llm.stats["cache_hits"] - hits0,
               seconds=round(time.monotonic() - t0, 1),
               status="complete" if complete else f"stopped: {stopped}" if stopped else "partial")
    md = to_markdown(m, run)
    (OUT / "metrics.md").write_text(md, encoding="utf-8")
    (OUT / "metrics.json").write_text(json.dumps({"run": run, **m}, indent=2), encoding="utf-8")
    append_history(m, run)
    print("\n" + md)
    print(f"{run['api_calls']} API calls, {run['cache_hits']} cache hits, {run['seconds']}s, {run['status']}")
    refresh_site()
    return 0 if complete else 3


if __name__ == "__main__":
    sys.exit(main())
