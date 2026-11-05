# 🔎 Report Checker

**An AI reviewer that checks an analyst's report against the data, and against what the client asked, before it ships.**

**Showcase: [eytanberko.github.io/report-checker](https://eytanberko.github.io/report-checker/)** (the reports, ticked, with the evidence and SQL behind every flag) · **App: [report-checkerwitz.streamlit.app](https://report-checkerwitz.streamlit.app/)** (saved runs; live checks are off in the public demo)

## Why I built this
I lead a team of data analysts, and I review every product before it ships: are the numbers right,
do the conclusions follow from the data, does it answer what the client asked?
This is slow, manual, and it doesn't scale. Report Checker automates the parts that can be
automated, and shows its work for everything else.

**Design principle:** the LLM never decides whether a number is correct. It only translates text
into SQL; the database decides. Every verdict shows the SQL behind it, so a human can audit it.

## How it works
```mermaid
flowchart LR
    R[/"Report"/] --> X
    D[("Any CSV")] --> S["Schema description<br/>(auto-built or hand-written)"]
    S --> X["1 · Extract (LLM)<br/>atomic claims +<br/>one SQL query per number"]
    X --> G{"2 · Guardrails<br/>columns, values, years,<br/>SQL matches the claim?"}
    G -- no --> M["query_mismatch<br/>(checker issue,<br/>not a report error)"]
    G -- yes --> V["3 · Verify (DuckDB)<br/>run SQL, compare<br/>to the stated value"]
    V --> C["4 · Consistency<br/>report's numbers<br/>vs each other"]
    C --> J["5 · Judge + coverage (LLM)<br/>conclusions vs verified facts;<br/>each requirement answered?"]
    Q[/"Client requirements"/] --> J
    J --> O["Verdict · highlighted report<br/>· review memo for the analyst"]
```

| Stage | How | Output |
|---|---|---|
| Extract | LLM splits the report into atomic claims and writes one DuckDB query per numeric claim | claims + SQL |
| Guardrails | Python, before execution: columns exist, values (e.g. countries) exist, years in range, the query's country/year are named or implied by the claim's sentence | 🔧 `query_mismatch` |
| Verify | DuckDB runs the query; the stated value must match within rounding | ✅ `verified` / ❌ `contradicted` |
| Consistency | Python, **no data access**: a stated change vs its stated endpoints under the claim's own wording (%, percentage points, per year compounded), shares above 100%, the same metric stated twice | 🟧 `inconsistent` |
| Judge | LLM checks conclusions against the verified facts and a data table built in Python (every column for the countries/years the report mentions) | ✅ `supported` / ⚠️ `unsupported` |
| Coverage | LLM checks each client requirement; a wrong scope (period, comparison group, metric) is `partial` | ✅ / ⚠️ / ❌ |

**Two models, by design.** The LLM stages need different things, so they run on different models:
- **Extraction** (`GEMINI_MODEL`, default `gemini-3.5-flash-lite`) is mechanical: split text into claims and
  translate each number into SQL. Every query is checked by guardrails and the database, so a cheap, fast model
  with a high free daily quota (~500 requests) is enough.
- **Judge + coverage** (`JUDGE_MODEL`, default `gemini-3.6-flash`) needs reasoning: weigh a cause against the
  data context, notice an answer to the wrong question. Flash-lite missed both kinds on the benchmark while
  quoting the very evidence it needed. It is one call per report, so the stronger model's low free quota
  (~20 requests/day) still covers the 10-report benchmark.

Spend where it changes the answer: the cheap model does the high-volume, verifiable work; the expensive one
does the low-volume work that nothing downstream can verify. Both models are recorded with every result,
in `metrics.md` and in `history.csv`.

Anything the checker can't use (malformed LLM output, a claim without a number) becomes ❔ `unverifiable`
with the reason, never a crash. Data verdicts take precedence: a number the data contradicts stays
"contradicted", and an internal inconsistency it explains is added to its note.

## What it catches
The benchmark's error taxonomy, built from the mistakes I see most in real analyst work:

| Error type | Example |
|---|---|
| wrong_number | coal at "13.4%" (data: 3.4%) |
| wrong_period | correct metric, value from the previous year |
| wrong_entity | Greece's number attributed to Cyprus |
| wrong_calculation | "+15%" where it is +15 percentage points |
| plausible_calculation | looks right, wrong method: "2.8% per year" as 28%/10 (compound: 2.5%); "+891%" as a ratio (change: +791%) |
| unsupported_conclusion | "coal phase-out was driven by solar" (it was gas) |
| missing_requirement | the client asked for a peer comparison; there is none |
| misread_requirement | answers a different question: change since 2020 when the client asked since 2015; Germany as a "Mediterranean peer" |

## Benchmark
10 reports answering the same client request (`benchmark/`): 3 clean, 7 with **16 planted errors**.
Results: [`results/metrics.md`](results/metrics.md) (recall, precision, false alarms, by error type) and
[`results/history.csv`](results/history.csv) (one row per run: model, prompt version, metrics, API calls).

### Benchmark notes: what changed after the first run, and why
The first run (then 8 reports; 7 scored before the free-tier quota ran out) caught all 12 planted errors in
those reports, with 4 flags counted as false alarms. Reviewing each one led to these changes:
- **Cascade errors.** 3 of the 4 "false alarms" were correct flags caused by a planted error, e.g. the
  conclusion "the phase-out is far from complete" built on a wrong coal figure. Planted errors can now list
  them under `also` (quote substrings) or `also_requirements` (requirement ids). Matching flags are reported
  as "cascade errors caught": not false alarms, and not extra recall.
- **Judge prompt adjusted once.** The 4th false alarm was the judge rejecting a data-grounded risk statement
  (made worse by the extractor splitting off the fragment "The main risk").
  A risk or recommendation grounded in numbers from the data now counts as supported; "unsupported" is
  reserved for claims contradicted by the data or relying on facts not in it. *Because this change was made
  after seeing results, the benchmark is no longer a fully blind test of the judge.*
- **Two error types and two reports added** (`misread_requirement`, `plausible_calculation`), with matching
  prompt rules: a wrong-scope answer is "partial", and "X% per year on average" means compound growth.
- **Deterministic stages added** (guardrails, internal consistency). They change no LLM prompt; saved
  results are re-checked with them for free.

After the first full 10-report run on one model (`gemini-3.5-flash-lite`: recall 15/16, 7 false alarms),
two scoring rules and one judge change were added. *All three were added after seeing that run's results.*
- **One planted error, many flags:** if several flagged claims contain the same planted error's match, the
  error counts once and the extra flags are not false alarms (report_07's "13.1%" appeared in a numeric
  claim and in a judgment claim that bundled it).
- **Requirement-level cascades, as a general rule:** a requirement marked partial/missing is a cascade of a
  planted claim error, not a false alarm, when its evidence quote contains that error's match, or overlaps
  (in the report text) a claim the checker flagged. 6 of the 7 false alarms were the coverage judge marking
  an answered requirement "partial" *because its number was wrong*; that error is already caught by the SQL
  check, so counting it again would double-penalise one mistake. This replaces per-report labels for
  requirements; quote-level `also` labels remain.
- **Judge data context:** the judge missed "the coal phase-out was driven mainly by solar" because it only
  saw the report's own numbers, and the report never mentions gas. It now also gets a table built in Python,
  with no extra LLM call: for every country and year in the extracted claims, all `*_share_elec` columns and
  `electricity_generation`, plus the absolute change from the first to the last year (gas +28.0 points,
  solar +14.4).

The re-run with the data context (recall 14/16, 1 false alarm) led to the last changes before the freeze,
*also made after seeing results*:
- **Query mismatches shown to the judge as "not checked (checker query failed)".** The judge had read the
  status `query_mismatch` as a problem in the report and marked a requirement partial (report_10 R4). A failed
  checker query is never a report problem. (Mismatched queries are also no longer used by the consistency
  checks, since their SQL doesn't measure what the claim says.)
- **Judge moved to `gemini-3.6-flash`.** Both remaining misses were judge reasoning errors on flash-lite: it
  cited solar +14.4 / coal -42.0 but ignored gas +28.0, and it noted "2020 instead of 2015" yet marked the
  requirement covered.

### Frozen configuration: `v1.0-frozen`
| | |
|---|---|
| Prompt version | `38701a08` (hash of both prompt templates and the judge's fact wording) |
| Extraction model | `gemini-3.5-flash-lite` |
| Judge model | `gemini-3.6-flash` |
| Frozen on | 2026-11-05 |

From this tag on there are no prompt, scoring-rule or model changes until the held-out test. Everything
above was tuned on this benchmark, so only a held-out set can show how well it generalises.

**Status: the benchmark run is incomplete.** Reports 01-06 are scored with this configuration (see
`results/metrics.md`). The free daily quota of the judge model (~20 requests) ran out, mostly on retries
during server overloads. **Reports 07-10 are pending** and will run with the same frozen configuration once
the quota resets (`python evaluate.py` resumes where it stopped).

Infrastructure changes after the freeze (no effect on prompts, rules, models or scores):
- **Overload retries:** on 500/503 the client waits 2, 4, then 8 minutes, at most 3 retries per call, then
  stops cleanly. Every retry counts against the daily quota, so fewer, longer-spaced retries protect it.

Each run records the prompt version (a hash of both prompt templates); `legacy` marks results made with the
first-run prompts. Scores for different prompt versions are not directly comparable.

## Run it
```bash
pip install -r requirements-dev.txt    # app + tests + lint (the app alone: requirements.txt)
python -m pytest -q                    # offline tests, no API key needed
streamlit run app.py                   # demo UI: saved runs work offline; "Run live check" calls the API
                                       # (hidden when no API key is set, e.g. in the public demo)

# CLI: prints the verdict, writes <report>.review.md; exit 0 = clean, 1 = issues, 2 = could not run
python -m checker check --report r.md --requirements req.md --data data.csv [--offline]

# Benchmark: resumable (reports finished with the current prompts are reused), throttled,
# stops cleanly when the daily free-tier quota runs out; re-run to resume.
set GEMINI_API_KEY=your_key            # Windows (mac/linux: export ...). Free key: aistudio.google.com
python evaluate.py
python evaluate.py --offline           # score saved results only, no API calls
```
- **LLM provider:** Gemini by default: extraction on `GEMINI_MODEL` (default `gemini-3.5-flash-lite`), judge on
  `JUDGE_MODEL` (default `gemini-3.6-flash`); see "Two models, by design". Check your free-tier limits at
  aistudio.google.com/rate-limit. Groq is optional:
  `LLM_PROVIDER=groq`, `GROQ_API_KEY` (free key at console.groq.com), `GROQ_MODEL`.
- **Cache:** LLM answers are cached in `.llm_cache/` (committed), so re-runs are free and reproducible.
  `LLM_OFFLINE=1` never calls an API.
- **Your own data:** `--data any.csv`. The schema description for the LLM (columns, types, ranges, example
  values, categories) is built from the file. `examples/cafes/` is a tiny synthetic example.

### Showcase site (GitHub Pages, `/docs`)
A static site (plain HTML/CSS/JS, no build step) generated from the saved results. After every benchmark run:
```bash
python scripts/build_site.py           # rewrites docs/data/site.js from results/ and benchmark/ (no API calls)
```
then commit and push; GitHub Pages serves `/docs` from `main`. A held-out result appears on the site once
`results/heldout/metrics.json` exists. Design context: `PRODUCT.md`, `DESIGN.md`.

### Public demo (Streamlit Community Cloud)
The app runs without any API key: it shows the saved benchmark runs (highlighting, memo, metrics) and hides
live checks. Deploy from this repo with `app.py` as the main file; `requirements.txt` holds only what the app
needs. To enable live checks in a private deployment, add `GEMINI_API_KEY` under the app's Secrets.

## Project layout
| Path | What |
|---|---|
| `checker/core.py` | the pipeline; `recheck()` re-runs the deterministic stages on a saved result |
| `checker/verify.py`, `guardrails.py`, `consistency.py` | the deterministic checks (no LLM) |
| `checker/llm.py`, `prompts.py`, `normalize.py` | LLM client (cache, throttle, quota), prompts, defensive parsing |
| `checker/dataset.py`, `schema.py` | pluggable CSV data; hand-written energy description |
| `checker/highlight.py`, `memo.py`, `cli.py` | inline highlighting, review memo, command line |
| `app.py`, `evaluate.py` | Streamlit demo, benchmark runner |
| `benchmark/` | the 10 reports, answer key and client request |

## Data
Our World in Data, energy dataset (electricity mix by country, 2010-2025), trimmed to 17 countries.

## Limitations & next steps
- **Small, self-written benchmark:** 10 reports, one client request, one dataset, errors planted by me.
  The judge prompt was tuned once after seeing results. Next: real (anonymised) reports labelled by a
  second reviewer.
- **The LLM can still write a wrong query.** Guardrails catch the wrong country, year, column or value,
  but not a wrong formula. Next: generate each query twice and flag disagreement.
- **Claim splitting is an LLM step.** A fragment like "The main risk" can be judged on its own. Next: a
  deterministic check that every quote is a full clause.
- **Consistency checks parse simple SQL** (one column, one entity, one or two years). Comparisons and
  complex queries are skipped, not guessed.
- **Judging conclusions is an LLM opinion**, not a proof; it is labelled as a warning, not an error.
