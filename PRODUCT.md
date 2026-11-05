# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
Two surfaces, both confirmed by the user:
- **Showcase site:** plain static HTML/CSS/JS in `/docs`, no framework and no build step, served by GitHub Pages.
  Its data is generated from the repository's results by a Python script, so a new benchmark run updates the site.
- **Streamlit app** (`app.py`): kept for local live checks; a public no-key demo runs on Streamlit Community Cloud.

## Users
- **Primary (the showcase):** a hiring manager at an AI / intelligence startup who opens the link cold and gives it
  about two minutes. They judge whether the author can build trustworthy AI systems around real analytical work.
- **Product user (the tool itself):** a team lead of data analysts who reviews every product before it ships to a
  client: are the numbers right, do conclusions follow from the data, does it answer what the client asked.

## Product Purpose
Report Checker checks an analyst's report against the data and against the client's requirements before it ships.
It splits the report into claims, verifies every number with SQL on the real data, checks the report's numbers
against each other, judges conclusions against the verified facts, and checks requirement coverage. It produces a
verdict, an inline-highlighted report and a review memo for the analyst. Success: the reviewer trusts the flags,
because every verdict shows its evidence.

## Positioning
The LLM never decides whether a number is correct: it only translates text into SQL, and the database decides.
Deterministic guardrails catch the LLM's own bad queries so they are not reported as the analyst's errors. Every
verdict shows the SQL behind it. Built by someone who does this review by hand today.

## Operating Context
- The author, Eytan Berkowitz, leads a team of data analysts and reviews every product before it ships.
- Benchmark: 10 reports the author wrote in the style of his team's work, all answering one client request
  (Israel's electricity transition 2015-2025), 3 clean and 7 with 16 planted errors drawn from real analyst mistakes
  (8 error types). Data: Our World in Data energy dataset, electricity mix by country 2010-2025, 17 countries.
- Two-model pipeline: extraction on `gemini-3.5-flash-lite`, judge on `gemini-3.6-flash`.
- Configuration frozen as `v1.0-frozen` (prompt version `38701a08`) before a held-out test.

## Capabilities and Constraints
- Statuses: verified, contradicted, inconsistent (report's own numbers disagree), unsupported, unverifiable,
  query_mismatch (checker-side, not a report error). Requirements: covered, partial, missing.
- The public showcase is static: it shows saved runs only and never calls an API.
- The frozen benchmark run is partial (reports 01-06 scored; 07-10 pending a quota reset). The held-out result
  does not exist yet and must appear only as a clearly marked placeholder.
- The prompts and scoring rules were tuned on this benchmark; the site must say so, not hide it.
- LinkedIn link: user wants one; URL not yet provided (undecided; hide until supplied).

## Brand Commitments
- Name: "Report Checker". Author credit: Eytan Berkowitz, with GitHub (github.com/eytanberko/report-checker) and
  LinkedIn links.
- Voice: plain, precise, calm; numbers explained in plain words; honest about limits.

## Evidence on Hand
- `results/report_*.json`: per-report claims, statuses, SQL, notes, requirement coverage.
- `results/metrics.json`, `results/metrics.md`, `results/history.csv`: metrics per run with models and prompt version.
- `benchmark/reports.yaml` (reports + answer key), `benchmark/requirements.md` (the client request).
- Review memos are generated deterministically by `checker/memo.py`.
- Benchmark presentation (user-delegated, recommended option): headline the frozen v1.0 run, mark 07-10 pending,
  and show the run history with what changed and why.
- Absent: no customers, users, testimonials or production deployments. No held-out result yet. Do not fabricate.

## Product Principles
1. Evidence over opinion: every flag shows what the data says and the query that says it.
2. Separate the checker's mistakes from the analyst's mistakes.
3. Report the benchmark honestly: partial runs, tuning on the same set, and misses are shown, not smoothed over.
4. Built from real review practice, not from a demo idea.
