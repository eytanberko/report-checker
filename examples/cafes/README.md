Tiny **synthetic** demo dataset (invented numbers) showing that the checker works on any CSV:
the schema description is built automatically from `cafes.csv`.

    python -m checker check --report examples/cafes/report.md \
        --requirements examples/cafes/requirements.md --data examples/cafes/cafes.csv
