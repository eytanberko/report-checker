# Benchmark results

Models: extraction `gemini-3.5-flash-lite`, judge `gemini-3.6-flash`; prompt version(s) `38701a08`; run 2026-11-05 09:29 UTC (live).

> **Partial:** 6 of 10 reports scored.

- **Recall** (planted errors caught): 10/10 = 100%
- **Precision** (flags that were real errors): 100%
- **False alarms**: 0 across 6 reports
- **Cascade errors caught** (downstream of a planted error; not in recall or precision): 1
- **Query mismatches** (checker-side, the claim was not checked; not counted): 2

## By error type

| type | caught | planted |
|---|---|---|
| wrong_number | 2 | 2 |
| unsupported_conclusion | 2 | 2 |
| wrong_calculation | 2 | 2 |
| wrong_period | 1 | 1 |
| missing_requirement | 2 | 2 |
| wrong_entity | 1 | 1 |

## By report

| report | planted | caught | cascade | false alarms | false-alarm details |
|---|---|---|---|---|---|
| report_01 | 0 | 0 | 0 | 0 |  |
| report_02 | 2 | 2 | 0 | 0 |  |
| report_03 | 3 | 3 | 1 | 0 |  |
| report_04 | 2 | 2 | 0 | 0 |  |
| report_05 | 0 | 0 | 0 | 0 |  |
| report_06 | 3 | 3 | 0 | 0 |  |
| report_07 | 2 | not run | | | |
| report_08 | 0 | not run | | | |
| report_09 | 2 | not run | | | |
| report_10 | 2 | not run | | | |
