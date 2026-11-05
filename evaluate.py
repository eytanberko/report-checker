"""Runs the checker on every benchmark report and scores it against the planted errors.

  python evaluate.py            -> prints metrics, writes results/metrics.md + results/<report>.json
"""
import json
from collections import Counter
from pathlib import Path

import yaml

from checker.core import FLAGGED, check_report

BENCH = Path("benchmark")
OUT = Path("results")


def score(report: dict, result: dict) -> dict:
    flagged = [c for c in result["claims"] if c["status"] in FLAGGED]
    not_covered = {r["id"] for r in result["requirements"] if r["status"] != "covered"}
    caught, missed, used = [], [], set()

    for err in report["planted"]:
        if err["type"] in ("missing_requirement", "misread_requirement"):
            hit = err["requirement"] in not_covered
            if hit:
                used.add(err["requirement"])
        else:
            match = next((c for c in flagged if err["match"].lower() in c["quote"].lower()), None)
            hit = match is not None
            if hit:
                used.add(match["id"])
        (caught if hit else missed).append(err)

    # Downstream "cascade" errors caused by a planted error: neither false alarms nor extra recall.
    also = [m.lower() for e in report["planted"] for m in e.get("also", [])]
    also_reqs = {r for e in report["planted"] for r in e.get("also_requirements", [])}
    cascade = [c for c in flagged if c["id"] not in used and any(m in c["quote"].lower() for m in also)]
    cascade += [{"id": r, "quote": f"requirement {r} marked not covered"}
                for r in sorted((not_covered - used) & also_reqs)]
    used |= {c["id"] for c in cascade}

    false_alarms = [c for c in flagged if c["id"] not in used] + \
                   [{"id": r, "quote": f"requirement {r} marked not covered"} for r in sorted(not_covered - used)]
    return {"caught": caught, "missed": missed, "cascade": cascade, "false_alarms": false_alarms}


def main():
    reports = yaml.safe_load((BENCH / "reports.yaml").read_text(encoding="utf-8"))["reports"]
    requirements = (BENCH / "requirements.md").read_text(encoding="utf-8")
    OUT.mkdir(exist_ok=True)

    by_type_total, by_type_caught = Counter(), Counter()
    total_alarms, total_cascade, rows = 0, 0, []
    for rep in reports:
        print(f"checking {rep['id']} ...")
        result = check_report(rep["text"], requirements)
        (OUT / f"{rep['id']}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        s = score(rep, result)
        for e in rep["planted"]:
            by_type_total[e["type"]] += 1
        for e in s["caught"]:
            by_type_caught[e["type"]] += 1
        total_alarms += len(s["false_alarms"])
        total_cascade += len(s["cascade"])
        rows.append((rep["id"], len(rep["planted"]), len(s["caught"]), len(s["cascade"]),
                     len(s["false_alarms"]), "; ".join(a["quote"][:60] for a in s["false_alarms"])))

    planted, caught = sum(by_type_total.values()), sum(by_type_caught.values())
    flagged_total = caught + total_alarms
    lines = [
        "# Benchmark results\n",
        f"- **Recall** (planted errors caught): {caught}/{planted} = {caught / planted:.0%}",
        f"- **Precision** (flags that were real errors): {caught}/{flagged_total} = "
        f"{(caught / flagged_total if flagged_total else 0):.0%}",
        f"- **False alarms**: {total_alarms} across {len(reports)} reports",
        f"- **Cascade errors caught** (downstream of a planted error; not in recall or precision): "
        f"{total_cascade}\n",
        "## By error type\n", "| type | caught | planted |", "|---|---|---|",
        *[f"| {t} | {by_type_caught[t]} | {n} |" for t, n in by_type_total.items()],
        "\n## By report\n",
        "| report | planted | caught | cascade | false alarms | false-alarm details |",
        "|---|---|---|---|---|---|",
        *[f"| {r} | {p} | {c} | {k} | {f} | {d} |" for r, p, c, k, f, d in rows],
    ]
    md = "\n".join(lines)
    (OUT / "metrics.md").write_text(md, encoding="utf-8")
    print("\n" + md)


if __name__ == "__main__":
    main()
