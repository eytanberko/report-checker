"""Command line:  python -m checker check --report r.md --requirements req.md --data data.csv

Prints the verdict, writes the review memo. Uses a saved benchmark run when the report is one of
the benchmark reports, otherwise the LLM cache (so re-runs are free); --offline never calls the API.
Exit code: 0 = nothing flagged, 1 = issues found, 2 = could not run.
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

from . import llm
from .core import FLAGGED, check_report, recheck
from .dataset import load_dataset
from .highlight import verdict
from .memo import review_memo
from .schema import DATA_PATH

BENCH = Path("benchmark")
RESULTS = Path("results")


def _norm(text: str) -> str:
    return " ".join(text.split())


def saved_run(report: str, requirements: str, data: str) -> tuple[str, dict] | None:
    """(report id, saved result) if this exact benchmark report + requirements + data has a saved run."""
    bench_reqs = BENCH / "requirements.md"
    if Path(data).resolve() != Path(DATA_PATH).resolve() or not bench_reqs.exists() \
            or _norm(requirements) != _norm(bench_reqs.read_text(encoding="utf-8")):
        return None
    for rep in yaml.safe_load((BENCH / "reports.yaml").read_text(encoding="utf-8"))["reports"]:
        path = RESULTS / f"{rep['id']}.json"
        if _norm(rep["text"]) == _norm(report) and path.exists():
            return rep["id"], json.loads(path.read_text(encoding="utf-8"))
    return None


def cmd_check(args: argparse.Namespace) -> int:
    """`check` command: verdict on stdout, review memo to a file; returns the exit code."""
    report = Path(args.report).read_text(encoding="utf-8")
    requirements = Path(args.requirements).read_text(encoding="utf-8")
    dataset = load_dataset(args.data)
    llm.OFFLINE = llm.OFFLINE or args.offline

    saved = saved_run(report, requirements, args.data)
    if saved:
        print(f"Using saved run results/{saved[0]}.json (deterministic checks re-run, no API call)")
        result = recheck(saved[1], report, dataset)
    else:
        try:
            result = check_report(report, requirements, ask=llm.ask_json, dataset=dataset,
                                  judge_ask=llm.ask_judge)
        except llm.CacheMiss:
            print("No saved or cached result for this report. Run without --offline "
                  "(needs an API key, see README).", file=sys.stderr)
            return 2

    level, text = verdict(result, FLAGGED)
    print(f"\nVERDICT: {text}\n")
    for err in result.get("errors", []):
        print(f"CHECKER PROBLEM: {err}")
    for c in result["claims"]:
        mark = "!!" if c["status"] in FLAGGED else "  "
        print(f'{mark} {c["id"]:<4} {c["status"]:<15} "{c["quote"]}"' + (f'  -- {c["note"]}' if c.get("note") else ""))
    for r in result["requirements"]:
        print(f'   {r["id"]:<4} {r["status"]:<15} {r.get("reason", "")}')

    out = Path(args.out) if args.out else Path(args.report).with_suffix(".review.md")
    out.write_text(review_memo(result, Path(args.report).name), encoding="utf-8")
    print(f"\nReview memo written to {out}")
    return 0 if level == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    """Entry point for `python -m checker`."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m checker", description="Check an analyst report.")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="check one report and write a review memo")
    check.add_argument("--report", required=True, help="report text file (.md / .txt)")
    check.add_argument("--requirements", required=True, help="client requirements file")
    check.add_argument("--data", default=DATA_PATH, help=f"CSV the report is based on (default {DATA_PATH})")
    check.add_argument("--out", help="where to write the memo (default: <report>.review.md)")
    check.add_argument("--offline", action="store_true", help="never call the LLM API; saved/cached only")
    args = parser.parse_args(argv)
    return cmd_check(args)
