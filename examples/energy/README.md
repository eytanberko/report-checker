A short **correct** report on the benchmark's energy data (`data/energy.csv`, Our World in Data), for trying the
checker live: every number matches the data, and the requirements are the benchmark's client request
(`benchmark/requirements.md`). In the app ("Try your own" → "Fill in the energy example"), change a number or add
a conclusion and run the check.

    python -m checker check --report examples/energy/report.md --requirements benchmark/requirements.md

Edits that show the checker at work: 16.9% → 19.6% (wrong number), "about 28%" → "about 35%" (wrong
calculation), Italy → Greece with 48.8% (wrong entity; Greece is 49.7%), or a new sentence such as "At this pace
renewables will pass 50% by 2030." (a conclusion the data does not support). A small change such as 16.9% → 16.8%
passes: numbers within 1% of the data count as matching (see the held-out results in the main README).
