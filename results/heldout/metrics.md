# Benchmark results

Models: extraction `gemini-3.5-flash-lite`, judge `gemini-3.5-flash-lite`; prompt version(s) `38701a08`; run 6 Nov 2026, 08:31 UTC (live).

- **Recall** (planted errors caught): 6/7 = 86%
- **Precision** (flags that were real errors): 100%
- **False alarms**: 0 across 4 reports
- **Cascade errors caught** (downstream of a planted error; not in recall or precision): 2
- **Query mismatches** (checker-side, the claim was not checked; not counted): 0

## By error type

| type | caught | planted |
|---|---|---|
| wrong_number | 0 | 1 |
| wrong_period | 1 | 1 |
| wrong_calculation | 1 | 1 |
| wrong_entity | 1 | 1 |
| plausible_calculation | 1 | 1 |
| misread_requirement | 1 | 1 |
| unsupported_conclusion | 1 | 1 |

## By report

| report | planted | caught | cascade | false alarms | false-alarm details |
|---|---|---|---|---|---|
| holdout_01 | 0 | 0 | 0 | 0 |  |
| holdout_02 | 3 | 2 | 0 | 0 |  |
| holdout_03 | 2 | 2 | 2 | 0 |  |
| holdout_04 | 2 | 2 | 0 | 0 |  |
