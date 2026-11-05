/* Report Checker showcase. Renders everything from window.SITE (docs/data/site.js, built by scripts/build_site.py). */
(() => {
  "use strict";
  const SITE = window.SITE;
  const $ = (sel) => document.querySelector(sel);
  if (!SITE || !SITE.reports || !SITE.reports.length) {
    $("#report-text").textContent = "The benchmark data has not been generated. Run python scripts/build_site.py.";
    return;
  }

  const STATUS = {
    verified: { tick: "t-agreed", label: "Matches the data" },
    supported: { tick: "t-agreed", label: "Supported by the data" },
    contradicted: { tick: "t-exception", label: "Contradicted by the data" },
    inconsistent: { tick: "t-nofoot", label: "Numbers inside the report don't add up" },
    unsupported: { tick: "t-unsupported", label: "Conclusion not supported by the data" },
    unverifiable: { tick: "t-unverified", label: "Couldn't be checked" },
    query_mismatch: { tick: "t-query", label: "Not checked: the checker's own query was wrong" },
  };
  const REQ = {
    covered: { tick: "t-agreed", cls: "tk-agreed", label: "Answered" },
    partial: { tick: "t-partial", cls: "tk-partial", label: "Partly answered" },
    missing: { tick: "t-missing", cls: "tk-missing", label: "Not answered" },
  };
  const TYPES = [
    ["wrong_number", "Wrong number", "Coal at “13.4%” when the data says 3.4%"],
    ["wrong_period", "Wrong year", "Solar’s 2024 share reported as 2025"],
    ["wrong_entity", "Wrong country", "Greece’s figure attributed to Cyprus"],
    ["wrong_calculation", "Wrong calculation", "“Rose by 15%” when it rose 15 percentage points"],
    ["plausible_calculation", "Right-looking, wrong method", "“2.8% a year” as 28% ÷ 10; compounded it is 2.5%"],
    ["unsupported_conclusion", "Unsupported conclusion", "“Coal’s decline was driven by solar” (gas rose twice as much)"],
    ["missing_requirement", "Requirement not answered", "The client asked for a peer comparison; there is none"],
    ["misread_requirement", "Requirement misread", "Change since 2020 when the client asked since 2015"],
  ];
  const VERSION_NOTES = {
    legacy: "First run, one model (gemini-3.6-flash). Re-scored later without new calls.",
    "7a00fa6a": "One fast model for every step. Cascade scoring added; two new mistake types; judge prompt adjusted once.",
    "1f18b8c3": "Judge given a table of the underlying data; one planted error now counts once; requirement cascades scored by a general rule.",
    "38701a08": "Judge moved to a stronger model; a failed checker query is shown to it as “not checked”. Frozen as v1.0.",
  };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const tick = (id, cls = "") => `<svg class="tk ${cls}" aria-hidden="true"><use href="#${id}"/></svg>`;
  const fmt = (x) => (x == null ? "" : Number(x).toLocaleString("en-US", { maximumFractionDigits: 2 }));
  const pct = (x) => (x == null ? "n/a" : `${Math.round(x * 100)}%`);
  const num = (id) => id.replace("report_", "");
  const tickClass = (status) => ({ verified: "tk-agreed", supported: "tk-agreed", contradicted: "tk-exception", inconsistent: "tk-nofoot", unsupported: "tk-unsupported", unverifiable: "tk-unverified", query_mismatch: "tk-query" }[status] || "");

  let current = null;   // selected report
  let pinned = null;    // pinned claim id

  /* ---------- tabs ---------- */
  function renderTabs() {
    const list = $("#tabs");
    list.innerHTML = SITE.reports.map((r) => {
      const n = (s) => r.claims.filter((c) => c.status === s).length;
      const exc = n("contradicted") + n("inconsistent");
      const other = n("unsupported");
      const tally = [
        exc ? `<span title="${exc} contradicted or inconsistent number${exc > 1 ? "s" : ""}">${tick("t-exception", "tk-exception")}${exc}</span>` : "",
        other ? `<span title="${other} unsupported conclusion${other > 1 ? "s" : ""}">${tick("t-unsupported", "tk-unsupported")}${other}</span>` : "",
        !exc && !other ? `<span>${tick("t-agreed", "tk-agreed")}clean</span>` : "",
      ].join("");
      return `<button class="tab" role="tab" id="tab-${r.id}" aria-controls="panel" aria-selected="false" tabindex="-1" data-id="${r.id}">
        <span class="tab-num">${num(r.id)}</span><span>${esc(r.author)}</span>
        <span class="tab-tally">${tally}${r.run.frozen ? "" : '<span class="tab-earlier">earlier run</span>'}</span></button>`;
    }).join("");
    list.addEventListener("click", (e) => {
      const b = e.target.closest(".tab");
      if (b) select(b.dataset.id, null, true);
    });
    list.addEventListener("keydown", (e) => {
      const tabs = [...list.querySelectorAll(".tab")];
      const i = tabs.indexOf(document.activeElement);
      if (i < 0) return;
      const next = { ArrowDown: i + 1, ArrowRight: i + 1, ArrowUp: i - 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
      if (next == null) return;
      e.preventDefault();
      const t = tabs[(next + tabs.length) % tabs.length];
      t.focus();
      select(t.dataset.id, null, true);
    });
  }

  /* ---------- the marked-up report ---------- */
  const CIRCLE = '<svg class="circle" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true"><path pathLength="1" d="M52 3C25 2 4 8 3 20c-1 12 22 17 48 17 25 0 46-6 46-17C97 9 78 3 47 4"/></svg>';

  // An auditor circles the figure itself: find the stated value in the claim's own text.
  function circleFigure(text, fig) {
    if (!fig || fig.done) return esc(text);
    const re = /\d[\d,]*(?:\.\d+)?(?:\s?%|\s?TWh)?/g;
    let m;
    while ((m = re.exec(text))) {
      if (Math.abs(parseFloat(m[0].replace(/,/g, "")) - fig.value) < 1e-9) {
        fig.done = true;
        return `${esc(text.slice(0, m.index))}<span class="circled">${esc(m[0])}${CIRCLE}</span>${esc(text.slice(m.index + m[0].length))}`;
      }
    }
    return esc(text);
  }

  function renderSegments(segs, byId, fig = null) {
    return segs.map((s) => {
      if (s.t != null) return circleFigure(s.t, fig);
      const c = byId[s.c];
      const st = STATUS[c.status] || STATUS.unverifiable;
      const own = c.status === "contradicted" && c.stated_value != null ? { value: Number(c.stated_value), done: false } : fig;
      const tickSvg = `<svg class="tick" aria-hidden="true"><use href="#${st.tick}"/></svg>`;
      // Keep the tick on the same line as the claim's last word.
      const last = s.k[s.k.length - 1];
      const tail = last && last.t != null ? last.t.match(/\S+\s*$/) : null;
      let inner;
      if (tail) {
        const head = { t: last.t.slice(0, tail.index) };
        inner = renderSegments([...s.k.slice(0, -1), head], byId, own)
          + `<span class="nowrap">${circleFigure(tail[0], own)}${tickSvg}</span>`;
      } else {
        inner = renderSegments(s.k, byId, own) + tickSvg;
      }
      return `<span class="claim s-${c.status}" role="button" tabindex="0" data-id="${c.id}" aria-describedby="note">${inner}<span class="visually-hidden"> (${esc(st.label)})</span></span>`;
    }).join("");
  }

  function noteHtml(c) {
    if (!c) {
      return `<p class="note-empty">Point at any underlined claim in the report to see its evidence here. Red circles are figures the data contradicts.</p>`;
    }
    const st = STATUS[c.status] || STATUS.unverifiable;
    const isNumber = c.kind === "numeric";
    let data = "";
    if (c.actual != null && c.status !== "query_mismatch") {
      data = `<p class="note-data">The data says <strong>${fmt(c.actual)}</strong>${c.stated_value != null ? `; the report says <strong>${fmt(c.stated_value)}</strong>` : ""}.</p>`;
    }
    const why = c.note && !/^data says/.test(c.note) ? `<p class="note-why">${esc(c.note)}</p>` : "";
    const sql = c.sql
      ? `<div class="note-sql"><span class="sql-label">The query behind it</span><pre>${esc(c.sql)}</pre></div>`
      : isNumber ? "" : `<p class="note-why">A conclusion, judged by the judge model against the checked facts and the data.</p>`;
    return `<p class="note-status">${tick(st.tick, tickClass(c.status))}${esc(st.label)}</p>
      <p class="note-quote">${esc(c.quote)}</p>${data}${why}${sql}
      <p class="note-link"><a class="claim-link" href="${claimUrl(current.id, c.id)}">Copy link to this claim</a><span class="copied" role="status"></span></p>`;
  }

  function showNote(id) {
    const c = current.claims.find((x) => x.id === id);
    const note = $("#note");
    note.innerHTML = noteHtml(c);
    note.classList.toggle("is-contradicted", c?.status === "contradicted");
    document.querySelectorAll(".claim.is-active").forEach((el) => el.classList.remove("is-active"));
    if (id) document.querySelectorAll(`.claim[data-id="${id}"]`).forEach((el) => el.classList.add("is-active"));
  }

  function bindClaims() {
    const box = $("#report-text");
    const target = (e) => e.target.closest(".claim");
    box.addEventListener("mouseover", (e) => { const t = target(e); if (t) { e.stopPropagation(); showNote(innermost(e)); } });
    box.addEventListener("mouseleave", () => showNote(pinned));
    box.addEventListener("focusin", (e) => { const t = target(e); if (t) showNote(t.dataset.id); });
    box.addEventListener("click", (e) => { const t = target(e); if (t) pin(innermost(e)); });
    box.addEventListener("keydown", (e) => {
      const t = target(e);
      if (t && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); pin(t.dataset.id); }
    });
  }
  const innermost = (e) => e.target.closest(".claim").dataset.id;

  const narrow = window.matchMedia("(max-width: 900px)");
  function pin(id) {
    pinned = id;
    showNote(id);
    history.replaceState(null, "", `#${current.id}/${id}`);
    // Below 900px the note sits under the report: bring it into view so the evidence is never off-screen.
    if (narrow.matches) {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      $("#note").scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
    }
  }

  /* ---------- answer key, coverage, memo ---------- */
  function renderAnswerKey(r) {
    const k = r.answer_key;
    const labels = Object.fromEntries(TYPES.map(([t, l]) => [t, l]));
    const planted = k.planted.length
      ? `<ul class="key-list">${k.planted.map((p) => `<li>${p.caught ? tick("t-agreed", "key-hit") : tick("t-unverified", "key-miss")}
          <span><span class="key-type">${esc(labels[p.type] || p.type)}</span>: ${/^R\d/.test(p.target) ? `requirement ${esc(p.target)}` : `“${esc(p.target)}”`}. ${p.caught ? "Caught." : "<strong>Missed.</strong>"}</span></li>`).join("")}</ul>`
      : "<p>This report is clean: no errors were planted.</p>";
    const fa = k.false_alarms.length
      ? `<p><strong>${k.false_alarms.length} false alarm${k.false_alarms.length > 1 ? "s" : ""}</strong>: ${k.false_alarms.map((a) => esc(a.quote)).join("; ")}.</p>`
      : `<p>No false alarms on this report.</p>`;
    const cascade = k.cascade.length ? `<p>${k.cascade.length} more flag${k.cascade.length > 1 ? "s" : ""} followed from a planted error (counted as a consequence, not as a false alarm).</p>` : "";
    const run = r.run.frozen
      ? ""
      : `<p><em>Shown from an earlier run with older settings (prompt ${esc(r.run.prompt_version)}, ${esc(r.run.model)}). The v1.0 run of this report is pending and will replace it automatically.</em></p>`;
    $("#answer-key").innerHTML = `<h3>Answer key for this report</h3>${planted}${fa}${cascade}${run}`;
  }

  function renderCoverage(r) {
    const asked = Object.fromEntries(SITE.requirements.map((q) => [q.id, q.text]));
    $("#coverage-body").innerHTML = r.requirements.map((q) => {
      const m = REQ[q.status] || REQ.partial;
      const ev = q.evidence ? `<span class="evidence">Answered by: “${esc(q.evidence)}”</span>` : "";
      return `<tr><td class="ref">${esc(q.id)}</td><td>${esc(asked[q.id] || "")}</td>
        <td><span class="result">${tick(m.tick, m.cls)}${m.label}</span></td><td><div>${esc(q.reason || "")}${ev}</div></td></tr>`;
    }).join("");
    labelCells("#coverage-body");
    const gaps = r.requirements.filter((q) => q.status !== "covered").length;
    $("#c-sub").textContent = `The client's five requirements, checked against ${r.author}'s report: ${gaps ? `${gaps} not fully answered.` : "all answered."}`;
  }

  function md(text) {
    const inline = (s) => esc(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*Fix:\*/g, '<em class="fix">Fix:</em>')
      .replace(/\*(.+?)\*/g, "<em>$1</em>");
    const out = [];
    let item = null;
    const flush = () => { if (item) { out.push(`<li>${item.join("<br>")}</li>`); item = null; } };
    let inList = false;
    for (const raw of text.split("\n")) {
      const line = raw.replace(/\s+$/, "");
      if (/^- /.test(line)) { if (!inList) { out.push("<ul>"); inList = true; } flush(); item = [inline(line.slice(2))]; continue; }
      if (item && /^\s{2,}\S/.test(raw)) { item.push(inline(line.trim())); continue; }
      flush();
      if (inList && line !== "") { out.push("</ul>"); inList = false; }
      if (/^# /.test(line)) out.push(`<h3>${inline(line.slice(2))}</h3>`);
      else if (/^## /.test(line)) out.push(`<h4>${inline(line.slice(3))}</h4>`);
      else if (line) out.push(`<p>${inline(line)}</p>`);
    }
    flush();
    if (inList) out.push("</ul>");
    return out.join("");
  }

  /* ---------- selecting a report ---------- */
  function select(id, claimId, fromUser) {
    const r = SITE.reports.find((x) => x.id === id) || SITE.reports[0];
    current = r;
    const n = num(r.id);
    document.querySelectorAll(".tab").forEach((t) => {
      const on = t.dataset.id === r.id;
      t.setAttribute("aria-selected", on);
      t.tabIndex = on ? 0 : -1;
    });
    $("#panel").setAttribute("aria-labelledby", `tab-${r.id}`);
    ["#b-ref", "#c-ref", "#d-ref"].forEach((sel) => { $(sel).textContent = `Report ${n}`; });
    const run = r.run.frozen
      ? `v1.0 (frozen settings)`
      : `Earlier settings · v1.0 pending`;
    $("#b-meta").innerHTML = `
      <div><dt>Client</dt><dd>Energy Policy desk</dd></div>
      <div><dt>Prepared by</dt><dd>${esc(r.author)}</dd></div>
      <div><dt>Period</dt><dd>2015–2025</dd></div>
      <div><dt>Reviewed by</dt><dd>Report Checker</dd></div>
      <div class="${r.run.frozen ? "" : "run-older"}"><dt>Settings</dt><dd>${run}</dd></div>`;
    const byId = Object.fromEntries(r.claims.map((c) => [c.id, c]));
    $("#report-text").innerHTML = renderSegments(r.segments, byId);
    renderAnswerKey(r);
    renderCoverage(r);
    $("#memo-body").innerHTML = md(r.memo);

    const first = r.claims.find((c) => c.status === "contradicted") || r.claims.find((c) => c.status !== "verified" && c.status !== "supported");
    pinned = claimId && byId[claimId] ? claimId : first ? first.id : null;
    showNote(pinned);
    if (pinned && byId[pinned]?.status === "contradicted") {
      document.querySelectorAll(`.claim[data-id="${pinned}"] .circle`).forEach((c) => c.classList.add("draw"));
    }
    if (fromUser) history.replaceState(null, "", `#${r.id}`);
  }

  /* ---------- benchmark ---------- */
  function renderBenchmark() {
    const m = SITE.metrics;
    const cfg = SITE.config;
    $("#m-extract").textContent = cfg.model;
    $("#m-judge").textContent = cfg.judge_model;
    if (!m) { $("#plain").innerHTML = "<p>No benchmark run yet.</p>"; return; }
    const flags = m.caught + m.false_alarms;
    const partial = m.reports_scored < m.reports_total;
    $("#e-sub").textContent = `The frozen v1.0 configuration (${cfg.model} for extraction, ${cfg.judge_model} as judge, prompt ${cfg.prompt_version}), on ${m.reports_scored} of ${m.reports_total} benchmark reports so far.`;
    $("#plain").innerHTML = `
      <p><span class="term">Recall</span>: of the <span class="figure">${m.planted}</span> mistakes planted in the reports scored so far, it caught <span class="figure">${m.caught}</span>.</p>
      <p><span class="term">Precision</span>: of the <span class="figure">${flags}</span> things it flagged, <span class="figure">${m.caught}</span> were planted mistakes and <span class="figure">${m.false_alarms}</span> ${m.false_alarms === 1 ? "was a false alarm" : "were false alarms"}.</p>
      <p>A further ${m.cascade} flag${m.cascade === 1 ? " was a correct consequence" : "s were correct consequences"} of a planted mistake (a conclusion built on a wrong number), and ${m.query_mismatches} of its own queries ${m.query_mismatches === 1 ? "was" : "were"} caught by the guardrails before they could become false alarms.</p>`;
    const caveats = [
      partial ? `Only ${m.reports_scored} of ${m.reports_total} reports are scored with the frozen configuration; the rest wait for the judge model's free daily quota.` : "",
      "Ten reports, one client request, one dataset, all written by me. That is a demonstration, not a statistic.",
      "The prompts and scoring rules were tuned on these same reports, so these numbers are optimistic. The held-out test below is the honest measure.",
    ].filter(Boolean);
    $("#caveats").innerHTML = caveats.map((c) => `<li>${esc(c)}</li>`).join("");

    // One pencil mark per planted mistake (no bars: one of one must not look like two of two), totalled below.
    const byType = Object.fromEntries((m.by_type || []).map((t) => [t.type, t]));
    $("#types-body").innerHTML = TYPES.map(([type, label, example]) => {
      const t = byType[type];
      if (!t) {
        return `<tr class="untested"><td>${esc(label)}</td><td>${esc(example)}</td>
          <td><span class="untested-label">None in the reports scored so far</span></td><td class="num">–</td></tr>`;
      }
      const marks = tick("t-agreed", "tk-agreed").repeat(t.caught) + tick("t-unverified", "tk-unverified").repeat(t.planted - t.caught);
      return `<tr><td>${esc(label)}</td><td>${esc(example)}</td>
        <td><span class="marks" role="img" aria-label="${t.caught} of ${t.planted} caught">${marks}</span></td>
        <td class="num">${t.caught} of ${t.planted}</td></tr>`;
    }).join("");
    const footCaught = (m.by_type || []).reduce((a, t) => a + t.caught, 0);
    const footPlanted = (m.by_type || []).reduce((a, t) => a + t.planted, 0);
    const foots = footCaught === m.caught && footPlanted === m.planted;
    $("#types-foot").innerHTML = `<tr><th scope="row" colspan="3">Total${foots ? `<span class="foot-mark" title="Matches the recall figure above">${tick("t-agreed", "tk-agreed")}</span>` : ""}</th>
      <td class="num">${footCaught} of ${footPlanted}</td></tr>`;
    labelCells("#types-body");
    const h = SITE.heldout;
    $("#heldout").innerHTML = h
      ? `<span class="stamp">Held-out</span><div><h3>Held-out test</h3><p>Recall ${pct(h.recall)}, precision ${pct(h.precision)}, ${h.false_alarms} false alarm${h.false_alarms === 1 ? "" : "s"} on ${h.reports_scored} reports the checker had never seen.</p></div>`
      : `<span class="stamp">Not yet run</span><div><h3>Held-out test</h3><p>New reports the checker has never seen, scored with the configuration frozen before they were written (tag ${esc(cfg.tag)}, prompt ${esc(cfg.prompt_version)}). This is where the result that matters will appear.</p></div>`;

    const rows = SITE.history;
    const isFrozen = (row) => row.prompt_version === cfg.prompt_version && row.model === cfg.model && row.judge_model === cfg.judge_model;
    const outcomeOf = (row) => (row.status && row.status.startsWith("stopped")
      ? (/quota/i.test(row.status) ? "Stopped early: daily quota." : "Stopped early: server overloaded.")
      : row.status === "partial" ? "Partial." : "Complete.");

    function runRow(row, change, cls = "") {
      const frozen = isFrozen(row);
      const m1 = `<span class="nowrap">${esc(row.model)}</span>`;
      const models = row.judge_model && row.judge_model !== row.model
        ? `${m1}<br><span class="nowrap">${esc(row.judge_model)} (judge)</span>` : m1;
      const date = (row.timestamp || "").slice(5, 16).replace("-", "/");
      return `<tr class="figures ${frozen ? "frozen" : ""}"><td><div>${esc(date)}${frozen ? '<span class="tag">v1.0</span>' : ""}</div></td>
        <td class="models"><div>${models}</div></td><td class="num">${esc(row.reports_scored)}/${esc(row.reports_total)}</td>
        <td class="num">${row.recall === "" ? "–" : pct(+row.recall)}</td><td class="num">${row.precision === "" ? "–" : pct(+row.precision)}</td>
        <td class="num">${esc(row.false_alarms)}</td></tr>
        <tr class="change ${frozen ? "frozen" : ""} ${cls}"><td colspan="6" data-label="What changed"><div>${change}</div></td></tr>`;
    }
    function labelRuns(tbodySel) {
      const table = $(tbodySel).closest("table");
      const heads = [...table.querySelectorAll("thead th")].map((th) => th.textContent.trim());
      table.querySelectorAll("tbody tr.figures").forEach((tr) => [...tr.children].forEach((td, i) => { td.dataset.label = heads[i] || ""; }));
    }

    // The three runs that matter: the first, the best with one model for every step, and the frozen v1.0 settings.
    const f1 = (r) => (+r.recall && +r.precision ? (2 * r.recall * r.precision) / (+r.recall + +r.precision) : 0);
    const single = rows.filter((r) => r.status === "complete" && (!r.judge_model || r.judge_model === r.model));
    const bestSingle = single.reduce((best, r) => (!best || f1(r) > f1(best) ? r : best), null);
    const frozenRuns = rows.filter(isFrozen);
    const frozenRun = frozenRuns.filter((r) => r.status === "complete").pop() || frozenRuns.pop();
    const key = [];
    const add = (row, role) => { if (row && !key.some((k) => k.row === row)) key.push({ row, role }); };
    add(rows[0], "First run.");
    add(bestSingle, "Best run with one model for every step.");
    add(frozenRun, "The frozen v1.0 settings.");
    $("#history-key").innerHTML = key
      .sort((a, b) => rows.indexOf(a.row) - rows.indexOf(b.row))
      .map(({ row, role }) => runRow(row, `<strong>${esc(role)}</strong> ${esc(VERSION_NOTES[row.prompt_version] || "")} ${outcomeOf(row)}`))
      .join("");
    labelRuns("#history-key");

    // Full history: each change stated once; a run with the same settings as the one above is a re-run (ditto).
    let prevConfig = null;
    $("#history-body").innerHTML = rows.map((row) => {
      const config = `${row.prompt_version}|${row.model}|${row.judge_model}`;
      const rerun = config === prevConfig;
      prevConfig = config;
      const change = rerun
        ? `<span class="ditto" aria-hidden="true">〃</span> Same settings, run again. ${outcomeOf(row)}`
        : `${esc(VERSION_NOTES[row.prompt_version] || "")} ${outcomeOf(row)}`;
      return runRow(row, change, rerun ? "rerun" : "");
    }).join("");
    labelRuns("#history-body");
    $("#all-runs-title").textContent = `Show all ${rows.length} runs`;
  }

  // Phones show each schedule row as labelled lines: copy the column headers onto the cells.
  function labelCells(tbodySel) {
    const table = $(tbodySel).closest("table");
    const heads = [...table.querySelectorAll("thead th")].map((th) => th.textContent.trim());
    table.querySelectorAll("tbody tr").forEach((tr) => [...tr.children].forEach((td, i) => { td.dataset.label = heads[i] || ""; }));
  }

  /* ---------- links ---------- */
  function renderLinks() {
    if (SITE.links.linkedin) {
      const href = esc(SITE.links.linkedin);
      const li = document.createElement("li");
      li.innerHTML = `<a href="${href}">LinkedIn</a>`;
      $("#signoff-links").append(li);
      $("#cover-links").insertAdjacentHTML("beforeend", `<a href="${href}">LinkedIn</a>`);
      document.querySelector(".byline-compact").insertAdjacentHTML("beforeend", ` · <a href="${href}">LinkedIn</a>`);
    }
  }

  // A claim link is "<page>#report_07/C3": it opens that report with that claim selected and on screen.
  function claimUrl(reportId, claimId) {
    return `${location.href.split("#")[0]}#${reportId}/${claimId}`;
  }

  function scrollToClaim(claimId) {
    const el = document.querySelector(`.claim[data-id="${CSS.escape(claimId)}"]`);
    if (el) el.scrollIntoView({ block: "center", behavior: "instant" });
  }

  function fromHash() {
    const [id, claim] = decodeURIComponent(location.hash.slice(1)).split("/");
    if (id && SITE.reports.some((r) => r.id === id)) {
      select(id, claim, false);
      if (claim) {
        scrollToClaim(claim);
        // fonts can still move the text after the first paint; settle on the claim once they are in
        document.fonts?.ready.then(() => scrollToClaim(claim));
      }
      return true;
    }
    return false;
  }

  // "Copy link to this claim": copy the address instead of navigating to the page we are already on.
  document.addEventListener("click", async (e) => {
    const a = e.target.closest(".claim-link");
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;  // new tab/window: let the browser open it
    e.preventDefault();
    const status = a.parentElement.querySelector(".copied");
    try {
      await navigator.clipboard.writeText(a.href);
      status.textContent = "Link copied";
    } catch {
      history.replaceState(null, "", a.href);
      status.textContent = "Link is in the address bar";
    }
  });

  renderTabs();
  bindClaims();
  renderBenchmark();
  renderLinks();
  if (!fromHash()) select("report_02", null, false);
  window.addEventListener("hashchange", fromHash);
})();
