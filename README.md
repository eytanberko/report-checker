# 🔎 Report Checker

**An AI reviewer that checks an analyst's report against the data before it reaches the client.**

## Why I built this
I lead a team of data analysts. Before any product goes out, I review it: are the numbers right,
do the conclusions follow from the data, does it answer what the client asked?
This is slow, manual, and it doesn't scale. Report Checker automates the parts that can be
automated, and shows its work for everything else.

## How it works
```
report + client requirements + data
   │
   ├─ 1. Extract   (LLM)    split the report into atomic claims; write one SQL query per numeric claim
   ├─ 2. Verify    (DuckDB) run the SQL on the real data, compare to the stated value  → ✅ / ❌
   ├─ 3. Judge     (LLM)    check conclusions against the verified facts               → ✅ / ⚠️
   └─ 4. Coverage  (LLM)    did the report answer each client requirement?            → ✅ / ❌
```
**Design principle:** the LLM never decides whether a number is correct. It only translates
text into SQL. The database decides. Every verdict shows the SQL behind it, so a human can audit it.

## Benchmark
10 reports answering the same client request (`benchmark/`): 3 clean, 7 with **16 planted errors**
from a taxonomy of mistakes I see in real analyst work:

| Error type | Example |
|---|---|
| wrong_number | coal at "13.4%" (data: 3.4%) |
| wrong_period | correct metric, value from the previous year |
| wrong_entity | Greece's number attributed to Cyprus |
| wrong_calculation | "+15%" where it is +15 percentage points |
| unsupported_conclusion | "coal phase-out was driven by solar" (it was gas) |
| missing_requirement | the client asked for a peer comparison; there is none |
| misread_requirement | answers a different question: change since 2020 when the client asked since 2015; Germany as a "Mediterranean peer" |
| plausible_calculation | looks right, wrong method: "2.8% per year" as 28%/10 (compound: 2.5%); "+891%" as a ratio (change: +791%) |

Results: see [`results/metrics.md`](results/metrics.md) (recall, precision, false alarms, by error type).

### Benchmark notes
- **Cascade errors** were identified after the first run: some flags were correct but were
  *consequences* of a planted error (e.g. a conclusion built on a wrong number). Planted errors can
  list them under `also` (quote substrings) or `also_requirements` (requirement ids). Matching flags
  are reported as "cascade errors caught": they are not false alarms and do not add to recall.
- **The judge prompt was adjusted once** after that first run: a risk or recommendation grounded in
  numbers from the data now counts as supported; "unsupported" is reserved for claims contradicted
  by the data or relying on facts not in it. Because this change was made after seeing results,
  the benchmark is no longer a fully blind test of the judge.

## Run it
```bash
pip install -r requirements.txt
python -m pytest -q                    # offline tests, no API key needed
set GEMINI_API_KEY=your_key            # Windows (mac/linux: export ...). Free key: aistudio.google.com
python evaluate.py                     # run the benchmark
streamlit run app.py                   # demo UI
```
LLM answers are cached in `.llm_cache/`, so re-runs are free and reproducible.

## Data
Our World in Data, energy dataset (electricity mix by country, 2010-2025), trimmed to 17 countries.

## Limitations & next steps
- The LLM can write a wrong SQL query and flag a correct claim. Mitigation today: the SQL is shown
  for audit. Next: generate the query twice and flag disagreement.
- Judging conclusions is still an LLM opinion, not a proof; it is labelled as a warning, not an error.
- Next: support any CSV + schema, not just this dataset.
