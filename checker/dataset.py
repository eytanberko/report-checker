"""Pluggable data: any CSV becomes a table plus an auto-built schema description for the LLM.

The hand-written energy description (schema.py) is kept as an optional override, because a human
description (units, coverage caveats) beats an automatic one when you have it.
"""
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from .consistency import ENERGY_SHARES
from .guardrails import Catalog
from .schema import DATA_PATH, SCHEMA, TABLE

TIME_NAMES = re.compile(r"^(year|yr|fiscal_year|period)$", re.I)
RESERVED = {k for (k,) in duckdb.connect().execute("SELECT keyword_name FROM duckdb_keywords()").fetchall()}
MAX_LISTED = 30  # list every category value up to this many distinct values
ENERGY_CONTEXT = ["renewables_share_elec", "solar_share_elec", "wind_share_elec", "gas_share_elec",
                  "coal_share_elec", "oil_share_elec", "fossil_share_elec", "electricity_generation"]


@dataclass
class Dataset:
    """A CSV loaded as one DuckDB table, plus what the checker needs to know about it."""
    path: str
    table: str
    description: str
    entity_col: str | None
    time_col: str | None
    shares: dict[str, list[str]] = field(default_factory=dict)
    context_columns: list[str] | None = None  # columns shown to the judge; None = all numeric columns

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Fresh in-memory connection with the CSV loaded as `self.table`."""
        con = duckdb.connect()
        path = self.path.replace("'", "''")
        con.execute(f'CREATE TABLE "{self.table}" AS SELECT * FROM read_csv_auto(\'{path}\')')
        return con

    def catalog(self, con: duckdb.DuckDBPyConnection) -> Catalog:
        """Columns, category values and ranges of this dataset's table, for the guardrails."""
        return Catalog.from_connection(con, self.table, self.entity_col, self.time_col)


def table_name(path: str) -> str:
    """SQL-friendly table name from a file name: 'Cafe sales-2024.csv' -> 'cafe_sales_2024'; keywords get a prefix."""
    name = re.sub(r"\W+", "_", Path(path).stem).strip("_").lower() or "data"
    return "t_" + name if name[0].isdigit() or name in RESERVED else name


def _fmt(x: float) -> str:
    x = float(x)
    return f"{x:,.0f}" if x.is_integer() or abs(x) >= 1000 else f"{x:.4g}"


def _one(con: duckdb.DuckDBPyConnection, sql: str) -> Any:
    """The first value of the first row of an aggregate query (which always returns one row)."""
    row = con.execute(sql).fetchone()
    assert row is not None
    return row[0]


def describe(con: duckdb.DuckDBPyConnection, table: str, source: str = "") -> tuple[str, str | None, str | None]:
    """Schema description for the LLM, plus the detected entity and time columns."""
    cat = Catalog.from_connection(con, table, entity_col=None, time_col=None)
    n_rows = _one(con, f'SELECT COUNT(*) FROM "{table}"')
    time_col = next((c for c, t in cat.columns.items() if TIME_NAMES.match(c) and "INT" in t), None)
    entity_col = next((c for c in cat.categories if c != time_col), None)

    lines = [f"Table `{table}` ({n_rows} rows{', from ' + Path(source).name if source else ''}"
             + (f"; one row per {entity_col} per {time_col}" if entity_col and time_col else "") + ").", "",
             "Columns:"]
    for col, typ in cat.columns.items():
        q = f'"{col}"'
        if col in cat.categories:
            values = sorted(cat.categories[col])
            shown = ", ".join(values[:MAX_LISTED]) + (", ..." if len(values) > MAX_LISTED else "")
            lines.append(f"- {col} (text): {len(values)} distinct values: {shown}")
        elif col in cat.ranges:
            lo, hi = cat.ranges[col]
            kind = "int" if "INT" in typ else "number"
            if col == time_col:
                lines.append(f"- {col} ({kind}): {lo:.0f} to {hi:.0f}")
                continue
            example = _one(con, f'SELECT {q} FROM "{table}" WHERE {q} IS NOT NULL LIMIT 1')
            nulls = _one(con, f'SELECT COUNT(*) FROM "{table}" WHERE {q} IS NULL')
            lines.append(f"- {col} ({kind}): {_fmt(lo)} to {_fmt(hi)}, e.g. {_fmt(example)}"
                         + (f"; {nulls} missing" if nulls else ""))
        else:
            example = con.execute(f'SELECT {q} FROM "{table}" WHERE {q} IS NOT NULL LIMIT 1').fetchone()
            lines.append(f"- {col} ({typ.lower()})" + (f", e.g. {example[0]}" if example else ""))
    if time_col and entity_col:
        latest = _one(con, f'SELECT COUNT(DISTINCT "{entity_col}") FROM "{table}" '
                           f'WHERE "{time_col}" = (SELECT MAX("{time_col}") FROM "{table}")')
        total = len(cat.categories[entity_col])
        if latest < total:
            lines.append(f"\n{total - latest} of {total} {entity_col} values have no row for the latest {time_col}.")
    return "\n".join(lines) + "\n", entity_col, time_col


def load_dataset(path: str, description: str | None = None, table: str | None = None) -> Dataset:
    """Load any CSV. `description` overrides the auto-built schema text (the energy file has one built in)."""
    if Path(path).resolve() == Path(DATA_PATH).resolve():
        return Dataset(path, TABLE, description or SCHEMA, "country", "year", ENERGY_SHARES, ENERGY_CONTEXT)
    table = table or table_name(path)
    ds = Dataset(path, table, "", None, None)
    auto, ds.entity_col, ds.time_col = describe(ds.connect(), table, path)
    ds.description = description or auto
    return ds


def default_dataset() -> Dataset:
    """The benchmark's energy dataset."""
    return load_dataset(DATA_PATH)


MAX_UPLOAD_MB = 50


class BadCSV(ValueError):
    """An uploaded file the checker cannot use; the message says why, in plain words."""


def load_upload(name: str, data: bytes, folder: Path) -> Dataset:
    """Save uploaded CSV bytes under `folder` (one subfolder per file content) and load it with an auto-built schema."""
    if not data.strip():
        raise BadCSV("The file is empty.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise BadCSV(f"The file is larger than {MAX_UPLOAD_MB} MB.")
    path = folder / hashlib.sha256(data).hexdigest()[:16] / (table_name(name) + ".csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    probe = Dataset(str(path), table_name(name), "", None, None)
    try:
        con = probe.connect()
    except duckdb.Error as e:
        raise BadCSV(f"Could not read the file as a CSV: {str(e).splitlines()[0][:200]}") from e
    if _one(con, f'SELECT COUNT(*) FROM "{probe.table}"') == 0:
        raise BadCSV("The file has a header row but no data rows.")
    cat = Catalog.from_connection(con, probe.table, entity_col=None, time_col=None)
    if not cat.ranges:
        raise BadCSV("The file has no numeric columns, so there are no numbers to check a report against. "
                     f"Columns read: {', '.join(cat.columns) or 'none'}.")
    return load_dataset(str(path), table=probe.table)
