"""Demo UI.  Run:  streamlit run app.py"""
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))  # find `checker` however the app is launched
from checker import llm  # noqa: E402
from checker.core import FLAGGED, check_report, recheck  # noqa: E402
from checker.dataset import BadCSV, Dataset, default_dataset, load_upload  # noqa: E402
from checker.highlight import render_html, verdict  # noqa: E402
from checker.memo import review_memo  # noqa: E402

st.set_page_config(page_title="Report Checker", page_icon="🔎", layout="wide")
ICON = {"verified": "✅", "supported": "✅", "contradicted": "❌", "unsupported": "⚠️", "unverifiable": "❔",
        "inconsistent": "🟧", "query_mismatch": "🔧"}
LEGEND = ("🟩 verified / supported · 🟥 contradicted by the data · 🟨 unsupported / unverifiable · "
          "🟧 inconsistent with the report's own numbers · hover a highlight for details")
REQ_ICON = {"covered": "✅", "partial": "⚠️", "missing": "❌"}
PASTE = "Paste my own"
SERIES = ["#2a78d6", "#eb6834"]  # categorical slots 1-2 (blue, orange) of the validated reference palette
ROOT = Path(__file__).resolve().parent  # repo root: works from any working directory (e.g. Streamlit Cloud)
DEMO_NOTE = "Live checks are disabled in the public demo; saved runs are shown."
OWN_NOTE = ("Live checks are disabled in the public demo, so this tab cannot run here. "
            "Run the app locally with your own free API key (README, \"Check your own report\").")


@dataclass
class Example:
    """What one "Try your own" toggle fills in; csv None means the benchmark's energy data."""
    label: str
    report: Path
    requirements: Path
    csv: Path | None = None


EXAMPLES = {
    "cafes": Example("Fill in the café example (invented numbers, with mistakes)",
                     ROOT / "examples" / "cafes" / "report.md", ROOT / "examples" / "cafes" / "requirements.md",
                     ROOT / "examples" / "cafes" / "cafes.csv"),
    "energy": Example("Fill in the energy example (the benchmark's data, a correct report)",
                      ROOT / "examples" / "energy" / "report.md", ROOT / "benchmark" / "requirements.md"),
}
UPLOADS = Path(tempfile.gettempdir()) / "report-checker-uploads"
# Someone is waiting at the screen: on 500/503 retry twice after a short wait, then say so (the CLI waits minutes).
APP_OVERLOAD_WAITS = (10, 30)


def live_enabled() -> bool:
    """True when an API key for the configured provider is set, as an env var or a Streamlit secret."""
    key_env = llm.PROVIDERS[llm.PROVIDER]["key_env"]
    if os.getenv(key_env):
        return True
    try:
        secret = st.secrets.get(key_env)
    except Exception:  # no secrets file at all
        return False
    if secret:
        os.environ[key_env] = str(secret)  # the LLM client reads keys from the environment
    return bool(secret)


LIVE = live_enabled()

reports = yaml.safe_load((ROOT / "benchmark" / "reports.yaml").read_text(encoding="utf-8"))["reports"]
by_label = {r["id"] + " · " + r["author"]: r for r in reports}
default_reqs = (ROOT / "benchmark" / "requirements.md").read_text(encoding="utf-8")


def saved_result(rep: dict) -> dict | None:
    """The saved benchmark result for this report, re-checked with the current deterministic stages."""
    path = ROOT / "results" / f"{rep['id']}.json"
    # Deterministic stages are re-run on the saved LLM output, so saved runs get the latest checks.
    return recheck(json.loads(path.read_text(encoding="utf-8")), rep["text"]) if path.exists() else None


def show_answer_key(rep: dict) -> None:
    """The planted errors (and their cascade errors) for a benchmark report."""
    st.markdown("**Answer key — planted errors**")
    if not rep["planted"]:
        st.markdown("_None: this is a clean report._")
    for e in rep["planted"]:
        target = f'requirement {e["requirement"]}' if "requirement" in e else f'“{e["match"]}”'
        line = f'- `{e["type"]}` — {target}'
        cascade = [f'“{m}”' for m in e.get("also", [])] + e.get("also_requirements", [])
        if cascade:
            line += f'  \n  cascade: {", ".join(cascade)}'
        st.markdown(line)


def run_live(where: str, key: tuple, report: str, requirements: str, dataset: Dataset | None = None) -> dict | None:
    """One live check. On failure the reason is kept for offer_saved() and None is returned."""
    waits, llm.OVERLOAD_WAITS = llm.OVERLOAD_WAITS, APP_OVERLOAD_WAITS
    st.session_state.pop("failed", None)
    with st.spinner("Extracting claims, running SQL, reviewing conclusions..."):
        try:
            return check_report(report, requirements, dataset=dataset)
        except llm.QuotaExhausted as e:
            message = (f"**The API quota for today is used up.** {e} "
                       "Try again after the daily reset, or use another key.")
        except llm.Overloaded:
            message = ("**The AI service is busy right now (503)** and stayed busy through two retries. "
                       "This is on the provider's side, not in the checker; try again in a few minutes.")
        except llm.LLMError as e:
            message = f"**The live check could not finish:** {e}"
        except Exception as e:  # network errors and the like: say what happened rather than show a traceback
            message = f"**The live check could not finish:** {type(e).__name__}: {e}"
        finally:
            llm.OVERLOAD_WAITS = waits
    st.session_state["failed"] = {"where": where, "key": key, "message": message, "show": False}
    return None


def offer_saved(where: str, key: tuple, example: str) -> None:
    """After a failed live run here: the reason, and a button that shows a saved example run instead."""
    failed = st.session_state.get("failed")
    if not failed or failed["where"] != where or failed["key"] != key:
        return
    st.error(failed["message"])
    if st.button("Show a saved example instead", key=f"saved_{where}"):
        failed["show"] = True
    if failed["show"]:
        show_saved_example(example)


def show_saved_example(name: str) -> None:
    """A run of one of the examples saved by scripts/save_examples.py: no API call."""
    saved = json.loads((ROOT / "examples" / name / "saved_result.json").read_text(encoding="utf-8"))
    meta = saved["meta"]
    st.info(f"Saved example: the {name} example as checked live on {meta['date']} with `{meta['model']}` "
            "(no API call). This is not the check that just failed.")
    show_result(saved["result"], EXAMPLES[name].report.read_text(encoding="utf-8"), f"{name}-example")


def show_result(result: dict, report: str, name: str) -> None:
    """Verdict banner, memo download, highlighted report, claim details and requirement coverage."""
    level, text = verdict(result, FLAGGED)
    {"ok": st.success, "warn": st.warning, "error": st.error}[level](f"**{text}**")
    for err in result.get("errors", []):
        st.warning(f"Checker problem: {err}")
    memo = review_memo(result, name)
    st.download_button("Download review memo (.md)", memo, file_name=f"review_{name.split(' ')[0]}.md",
                       mime="text/markdown")
    with st.expander("Review memo for the analyst"):
        st.markdown(memo)

    st.subheader("Report")
    st.caption(LEGEND)
    body, missing = render_html(report, result["claims"])
    st.markdown(body, unsafe_allow_html=True)
    if missing:
        st.caption("Not located in the text: " + "; ".join(f'{c["id"]} “{c["quote"]}”' for c in missing))

    with st.expander("Claim details and SQL"):
        for c in result["claims"]:
            line = f'{ICON.get(c["status"], "❔")} **{c["id"]} {c["status"].upper()}** — “{c["quote"]}”'
            if c.get("note"):
                line += f'  \n  ↳ {c["note"]}'
            st.markdown(line)
            if c.get("sql"):
                st.code(c["sql"], language="sql")

    st.subheader("Client requirements")
    for r in result["requirements"]:
        st.markdown(f'{REQ_ICON.get(r["status"], "❔")} **{r["id"]}** — {r["status"]}: {r.get("reason", "")}')


st.title("🔎 Report Checker")
st.caption("Checks an analyst's report against the data and the client's requirements, before it ships.")

tab_check, tab_own, tab_bench = st.tabs(["Check a report", "Try your own", "Benchmark results"])

with tab_check:
    left, right = st.columns(2)
    with left:
        choice = st.selectbox("Report", list(by_label) + [PASTE])
        rep = by_label.get(choice)
        report = st.text_area("Report text", rep["text"] if rep else "", height=230, key=f"text_{choice}")
    with right:
        requirements = st.text_area("Client requirements", default_reqs, height=300)
        if rep:
            show_answer_key(rep)

    # A saved run is only valid for the unedited benchmark report and requirements.
    unedited = rep is not None and report == rep["text"] and requirements == default_reqs
    saved = saved_result(rep) if rep is not None and unedited else None
    live = st.session_state.get("live", {})

    label = "Run live check" if saved else "Run check"
    if not LIVE:
        st.info(DEMO_NOTE)
    elif st.button(label, type="primary", disabled=not report.strip()):
        result = run_live("check", (choice, report, requirements), report, requirements)
        if result is not None:
            live[choice] = {"report": report, "requirements": requirements, "result": result}
            st.session_state["live"] = live
    offer_saved("check", (choice, report, requirements), "energy")

    run = live.get(choice)
    if run and run["report"] == report and run["requirements"] == requirements:
        st.success("Live run")
        show_result(run["result"], report, choice)
    elif saved:
        st.info(f"Saved run — loaded from `results/{rep['id'] if rep else ''}.json` (no API call)")
        show_result(saved, report, choice)
    elif rep and not unedited:
        st.caption("Text edited — the saved run no longer applies." + (" Run a live check." if LIVE else ""))
    elif rep:
        st.caption("No saved run for this report yet." + (" Run a live check." if LIVE else ""))


def pick_example(name: str) -> None:
    """One example at a time: turning one on turns the other off."""
    for other in EXAMPLES:
        if other != name:
            st.session_state[f"own_{other}"] = False


def reset_example(name: str) -> None:
    """Put the example's report and requirements back as they were, and forget its run."""
    for k in (f"own_report_{name}", f"own_reqs_{name}", "own", "failed"):
        st.session_state.pop(k, None)


def try_your_own() -> None:
    """Your own CSV, report and requirements (or an example): the schema is built from the file, then one live check."""
    st.caption("Upload a CSV, paste a report written from it and the client's requirements. The description of the "
               "data that the model sees (columns, types, ranges, categories) is built from the file.")
    for key_name, option in EXAMPLES.items():
        st.toggle(option.label, key=f"own_{key_name}", on_change=pick_example, args=(key_name,))
    example = next((n for n in EXAMPLES if st.session_state.get(f"own_{n}")), "")
    ex = EXAMPLES.get(example)
    left, right = st.columns(2)
    with left:
        if ex and ex.csv is None:
            name, data = "energy", b""
            st.caption("Data: `data/energy.csv` (Our World in Data), the benchmark's data")
        elif ex and ex.csv:
            name, data = ex.csv.name, ex.csv.read_bytes()
            st.caption(f"Data: `{ex.csv.relative_to(ROOT).as_posix()}`")
        else:
            upload = st.file_uploader("Data (CSV)", type="csv", key="own_csv")
            name, data = (upload.name, upload.getvalue()) if upload else ("", b"")
        report = st.text_area("Report text", ex.report.read_text(encoding="utf-8") if ex else "",
                              height=200, key=f"own_report_{example}")
    with right:
        requirements = st.text_area("Client requirements",
                                    ex.requirements.read_text(encoding="utf-8") if ex else "",
                                    height=200, key=f"own_reqs_{example}")
    if ex:
        st.button("Reset example", key="own_reset", on_click=reset_example, args=(example,),
                  help="Put the example's report and requirements back as they were")

    ds = None
    if ex and ex.csv is None:
        ds = default_dataset()
        with st.expander("Schema of the energy data (hand-written; what the model is told about the data)"):
            st.code(ds.description, language="markdown")
    elif name:
        try:
            ds = load_upload(name, data, UPLOADS)
        except BadCSV as e:
            st.error(f"**This CSV cannot be used.** {e}")
        else:
            with st.expander(f"Schema built from {name} (what the model is told about the data)"):
                st.code(ds.description, language="markdown")

    if not LIVE:
        st.info(OWN_NOTE)
        return
    missing = [what for what, ok in (("a CSV", ds), ("the report", report.strip()),
                                     ("the requirements", requirements.strip())) if not ok]
    if missing:
        st.caption("Still needed: " + ", ".join(missing) + ".")
    key = (name, hashlib.sha256(data).hexdigest(), report, requirements)
    if st.button("Run check", type="primary", disabled=bool(missing), key="own_run") and ds is not None:
        result = run_live("own", key, report, requirements, ds)
        if result is not None:
            st.session_state["own"] = {"key": key, "result": result}
    offer_saved("own", key, example or "cafes")
    run = st.session_state.get("own")
    if run and run["key"] == key:
        st.success("Live run")
        show_result(run["result"], report, Path(name).stem)


with tab_own:
    try_your_own()


def pct(x: float | None) -> str:
    """0.917 -> '92%'; None -> 'n/a'."""
    return "n/a" if x is None else f"{x:.0%}"


def show_benchmark() -> None:
    """Benchmark tab: headline metrics, caught-% by error type, per-report table, run history."""
    path = ROOT / "results" / "metrics.json"
    if not path.exists():
        st.info("Run `python evaluate.py` first.")
        return
    m = json.loads(path.read_text(encoding="utf-8"))
    run = m["run"]
    st.caption(f"Extraction `{run['model']}` · judge `{run.get('judge_model', run['model'])}` · "
               f"prompt version(s) {', '.join(m['prompt_versions'])} · {run['timestamp']} ({run['mode']}) · "
               f"{run['api_calls']} API calls, {run['cache_hits']} cached")
    if m["reports_scored"] < m["reports_total"]:
        st.warning(f"Partial: {m['reports_scored']} of {m['reports_total']} reports scored.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Recall", pct(m["recall"]), f"{m['caught']} of {m['planted']} planted errors", delta_color="off")
    c2.metric("Precision", pct(m["precision"]))
    c3.metric("False alarms", m["false_alarms"])
    c4.metric("Cascade errors caught", m["cascade"], "not in recall/precision", delta_color="off")

    st.subheader("Planted errors caught, by type (%)")
    by_type = pd.DataFrame(m["by_type"]).set_index("type")
    by_type["caught %"] = (100 * by_type["caught"] / by_type["planted"]).round()
    left, right = st.columns([3, 2])
    left.bar_chart(by_type["caught %"], horizontal=True, color=SERIES[0], height=260)
    right.dataframe(by_type, use_container_width=True)

    st.subheader("By report")
    rows = [{k: r.get(k) for k in ("report", "planted", "caught", "cascade", "false_alarms",
                                   "query_mismatches", "prompt_version")} for r in m["by_report"]]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    hist_path = ROOT / "results" / "history.csv"
    if hist_path.exists():
        st.subheader("History across runs")
        hist = pd.read_csv(hist_path)
        if len(hist) >= 2:
            trend = hist.set_index("timestamp")[["recall", "precision"]] * 100
            st.line_chart(trend, color=SERIES[:2], height=240, y_label="%")  # type: ignore[arg-type]  # stub too narrow
        st.dataframe(hist, use_container_width=True, hide_index=True)


with tab_bench:
    show_benchmark()
