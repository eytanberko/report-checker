# Benchmark results

Model `gemini-3.6-flash`, prompt version(s) `legacy`, run 2026-11-05 00:35 UTC (offline).

> **Partial:** 7 of 10 reports scored.

- **Recall** (planted errors caught): 12/12 = 100%
- **Precision** (flags that were real errors): 92%
- **False alarms**: 1 across 7 reports
- **Cascade errors caught** (downstream of a planted error; not in recall or precision): 3
- **Query mismatches** (checker-side, the claim was not checked; not counted): 0

## By error type

| type | caught | planted |
|---|---|---|
| wrong_number | 2 | 2 |
| unsupported_conclusion | 2 | 2 |
| wrong_calculation | 2 | 2 |
| wrong_period | 2 | 2 |
| missing_requirement | 2 | 2 |
| wrong_entity | 2 | 2 |

## By report

| report | planted | caught | cascade | false alarms | false-alarm details |
|---|---|---|---|---|---|
| report_01 | 0 | 0 | 0 | 0 |  |
| report_02 | 2 | 2 | 1 | 0 |  |
| report_03 | 3 | 3 | 1 | 0 |  |
| report_04 | 2 | 2 | 0 | 0 |  |
| report_05 | 0 | 0 | 0 | 1 | The main risk |
| report_06 | 3 | 3 | 0 | 0 |  |
| report_07 | 2 | 2 | 1 | 0 |  |
| report_08 | 0 | not run | | | |
| report_09 | 2 | not run | | | |
| report_10 | 2 | not run | | | |
