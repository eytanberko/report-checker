"""Demo UI.  Run:  streamlit run app.py"""
import json
from pathlib import Path

import streamlit as st
import yaml

from checker.core import check_report, summary

st.set_page_config(page_title="Report Checker", page_icon="🔎", layout="wide")
ICON = {"verified": "✅", "supported": "✅", "contradicted": "❌", "unsupported": "⚠️", "unverifiable": "❔"}
REQ_ICON = {"covered": "✅", "partial": "⚠️", "missing": "❌"}
PASTE = "Paste my own"

reports = yaml.safe_load(Path("benchmark/reports.yaml").read_text(encoding="utf-8"))["reports"]
by_label = {r["id"] + " · " + r["author"]: r for r in reports}
default_reqs = Path("benchmark/requirements.md").read_text(encoding="utf-8")


def saved_result(report_id: str):
    path = Path("results") / f"{report_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


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


def show_result(result: dict):
    s = summary(result)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Claims", s["claims"])
    c2.metric("Verified", s["verified"])
    c3.metric("Flagged", s["flagged"])
    c4.metric("Requirements not covered", s["requirements_missing"])

    st.subheader("Claims")
    for c in result["claims"]:
        line = f'{ICON[c["status"]]} **{c["status"].upper()}** — “{c["quote"]}”'
        if c.get("note"):
            line += f'  \n  ↳ {c["note"]}'
        st.markdown(line)
        if c.get("sql"):
            with st.expander("SQL used to check this claim"):
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
    saved = saved_result(rep["id"]) if unedited else None
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
        show_result(run["result"])
    elif saved:
        st.info("Saved run — loaded from `results/" + rep["id"] + ".json` (no API call)")
        show_result(saved)
    elif rep and not unedited:
        st.caption("Text edited — the saved run no longer applies. Run a live check.")
    elif rep:
        st.caption("No saved run for this report yet. Run a live check.")

with tab_bench:
    metrics = Path("results/metrics.md")
    if metrics.exists():
        st.markdown(metrics.read_text(encoding="utf-8"))
    else:
        st.info("Run `python evaluate.py` first.")
