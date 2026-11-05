"""Demo UI.  Run:  streamlit run app.py"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from checker.core import FLAGGED, check_report, recheck
from checker.highlight import render_html, verdict
from checker.memo import review_memo

st.set_page_config(page_title="Report Checker", page_icon="🔎", layout="wide")
ICON = {"verified": "✅", "supported": "✅", "contradicted": "❌", "unsupported": "⚠️", "unverifiable": "❔",
        "inconsistent": "🟧", "query_mismatch": "🔧"}
LEGEND = ("🟩 verified / supported · 🟥 contradicted by the data · 🟨 unsupported / unverifiable · "
          "🟧 inconsistent with the report's own numbers · hover a highlight for details")
REQ_ICON = {"covered": "✅", "partial": "⚠️", "missing": "❌"}
PASTE = "Paste my own"
SERIES = ["#2a78d6", "#eb6834"]  # categorical slots 1-2 (blue, orange) of the validated reference palette

reports = yaml.safe_load(Path("benchmark/reports.yaml").read_text(encoding="utf-8"))["reports"]
by_label = {r["id"] + " · " + r["author"]: r for r in reports}
default_reqs = Path("benchmark/requirements.md").read_text(encoding="utf-8")


def saved_result(rep: dict):
    path = Path("results") / f"{rep['id']}.json"
    # Deterministic stages are re-run on the saved LLM output, so saved runs get the latest checks.
    return recheck(json.loads(path.read_text(encoding="utf-8")), rep["text"]) if path.exists() else None


def show_answer_key(rep: dict):
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


def show_result(result: dict, report: str, name: str):
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

tab_check, tab_bench = st.tabs(["Check a report", "Benchmark results"])

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
    saved = saved_result(rep) if unedited else None
    live = st.session_state.get("live", {})

    label = "Run live check" if saved else "Run check"
    if st.button(label, type="primary", disabled=not report.strip()):
        with st.spinner("Extracting claims, running SQL, reviewing conclusions..."):
            try:
                live[choice] = {"report": report, "requirements": requirements,
                                "result": check_report(report, requirements)}
                st.session_state["live"] = live
            except Exception as e:
                st.error(f"Live check failed: {e}")

    run = live.get(choice)
    if run and run["report"] == report and run["requirements"] == requirements:
        st.success("Live run")
        show_result(run["result"], report, choice)
    elif saved:
        st.info("Saved run — loaded from `results/" + rep["id"] + ".json` (no API call)")
        show_result(saved, report, choice)
    elif rep and not unedited:
        st.caption("Text edited — the saved run no longer applies. Run a live check.")
    elif rep:
        st.caption("No saved run for this report yet. Run a live check.")

def pct(x) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def show_benchmark():
    path = Path("results/metrics.json")
    if not path.exists():
        st.info("Run `python evaluate.py` first.")
        return
    m = json.loads(path.read_text(encoding="utf-8"))
    run = m["run"]
    st.caption(f"Model `{run['model']}` · prompt version(s) {', '.join(m['prompt_versions'])} · "
               f"{run['timestamp']} ({run['mode']}) · {run['api_calls']} API calls, {run['cache_hits']} cached")
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

    hist_path = Path("results/history.csv")
    if hist_path.exists():
        st.subheader("History across runs")
        hist = pd.read_csv(hist_path)
        if len(hist) >= 2:
            trend = hist.set_index("timestamp")[["recall", "precision"]] * 100
            st.line_chart(trend, color=SERIES[:2], height=240, y_label="%")
        st.dataframe(hist, use_container_width=True, hide_index=True)


with tab_bench:
    show_benchmark()
