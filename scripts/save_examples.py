"""Save a checked run of each example, shown in the app when a live run fails.

Cache-first like everything else: with the answers in .llm_cache/ this makes no API calls.
Run:  python scripts/save_examples.py [--offline]
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checker import llm  # noqa: E402
from checker.core import check_report  # noqa: E402
from checker.dataset import default_dataset, load_dataset  # noqa: E402
from checker.prompts import prompt_version  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = {  # name -> (report, requirements, data; None = the benchmark's energy data)
    "cafes": ("examples/cafes/report.md", "examples/cafes/requirements.md", "examples/cafes/cafes.csv"),
    "energy": ("examples/energy/report.md", "benchmark/requirements.md", None),
}


def save(name: str) -> dict:
    report, reqs, data = EXAMPLES[name]
    ds = default_dataset() if data is None else load_dataset(str(ROOT / data))
    result = check_report((ROOT / report).read_text(encoding="utf-8"), (ROOT / reqs).read_text(encoding="utf-8"),
                          dataset=ds)
    saved = {"meta": {"model": llm.MODEL, "judge_model": llm.JUDGE_MODEL, "prompt_version": prompt_version(),
                      "date": datetime.now(timezone.utc).strftime("%d %b %Y")},
             "result": result}
    out = ROOT / "examples" / name / "saved_result.json"
    out.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return saved


def main() -> int:
    if "--offline" in sys.argv:
        llm.OFFLINE = True
    for name in EXAMPLES:
        r = save(name)["result"]
        print(name, [(c["id"], c["status"]) for c in r["claims"]], [(q["id"], q["status"]) for q in r["requirements"]])
    print(llm.stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
