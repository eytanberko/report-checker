# Benchmark results

Models: extraction `gemini-3.5-flash-lite`, judge `gemini-3.5-flash-lite`; prompt version(s) `38701a08`; run 6 Nov 2026, 08:58 UTC (live).

- **Recall** (planted errors caught): 14/16 = 88%
- **Precision** (flags that were real errors): 93%
- **False alarms**: 1 across 10 reports
- **Cascade errors caught** (downstream of a planted error; not in recall or precision): 3
- **Query mismatches** (checker-side, the claim was not checked; not counted): 2

## By error type

| type | caught | planted |
|---|---|---|
| wrong_number | 2 | 2 |
| unsupported_conclusion | 1 | 2 |
| wrong_calculation | 2 | 2 |
| wrong_period | 2 | 2 |
| missing_requirement | 2 | 2 |
| wrong_entity | 2 | 2 |
| misread_requirement | 1 | 2 |
| plausible_calculation | 2 | 2 |

## By report

| report | planted | caught | cascade | false alarms | false-alarm details |
|---|---|---|---|---|---|
| report_01 | 0 | 0 | 0 | 0 |  |
| report_02 | 2 | 2 | 0 | 0 |  |
| report_03 | 3 | 3 | 0 | 0 |  |
| report_04 | 2 | 2 | 1 | 0 |  |
| report_05 | 0 | 0 | 0 | 1 | Generation increased
by roughly 28%, from 64.2 TWh to 82.1 T |
| report_06 | 3 | 2 | 1 | 0 |  |
| report_07 | 2 | 2 | 0 | 0 |  |
| report_08 | 0 | 0 | 0 | 0 |  |
| report_09 | 2 | 1 | 1 | 0 |  |
| report_10 | 2 | 2 | 0 | 0 |  |
