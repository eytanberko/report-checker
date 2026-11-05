# Benchmark results

Model `gemini-3.5-flash-lite`, prompt version(s) `7a00fa6a`, run 2026-11-05 08:16 UTC (live).

- **Recall** (planted errors caught): 15/16 = 94%
- **Precision** (flags that were real errors): 68%
- **False alarms**: 7 across 10 reports
- **Cascade errors caught** (downstream of a planted error; not in recall or precision): 1
- **Query mismatches** (checker-side, the claim was not checked; not counted): 3

## By error type

| type | caught | planted |
|---|---|---|
| wrong_number | 2 | 2 |
| unsupported_conclusion | 1 | 2 |
| wrong_calculation | 2 | 2 |
| wrong_period | 2 | 2 |
| missing_requirement | 2 | 2 |
| wrong_entity | 2 | 2 |
| misread_requirement | 2 | 2 |
| plausible_calculation | 2 | 2 |

## By report

| report | planted | caught | cascade | false alarms | false-alarm details |
|---|---|---|---|---|---|
| report_01 | 0 | 0 | 0 | 0 |  |
| report_02 | 2 | 2 | 0 | 0 |  |
| report_03 | 3 | 3 | 0 | 2 | requirement R1 marked not covered; requirement R2 marked not covered |
| report_04 | 2 | 2 | 0 | 2 | requirement R3 marked not covered; requirement R4 marked not covered |
| report_05 | 0 | 0 | 0 | 0 |  |
| report_06 | 3 | 2 | 0 | 1 | requirement R4 marked not covered |
| report_07 | 2 | 2 | 1 | 2 | Solar provided 13.1% of electricity in 2025 and is the main ; requirement R3 marked not covered |
| report_08 | 0 | 0 | 0 | 0 |  |
| report_09 | 2 | 2 | 0 | 0 |  |
| report_10 | 2 | 2 | 0 | 0 |  |
