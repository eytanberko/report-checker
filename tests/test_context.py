"""Judge data context: built deterministically from the claims' entities and years, passed to the judge."""
from pathlib import Path

from checker.context import data_context, scope
from checker.core import check_report
from checker.dataset import default_dataset, load_dataset

Q = "SELECT {col} FROM energy WHERE country = '{c}' AND year = {y}"
CLAIMS = [
    {"id": "C1", "quote": "Israel's renewables share went from 1.9% in 2015", "kind": "numeric",
     "sql": Q.format(col="renewables_share_elec", c="Israel", y=2015)},
    {"id": "C2", "quote": "Coal fell to 3.4%", "kind": "numeric",
     "sql": Q.format(col="coal_share_elec", c="Israel", y=2025)},
    {"id": "C3", "quote": "Greece (49.7%) is well ahead", "kind": "judgment", "sql": None},
    {"id": "C4", "quote": "The coal phase-out was driven mainly by the growth of solar.", "kind": "judgment"},
]


def test_scope_reads_entities_and_years_from_sql_and_quotes():
    ds = default_dataset()
    assert scope(ds.connect(), ds, CLAIMS) == (["Greece", "Israel"], [2015, 2025])


def test_context_shows_rows_and_absolute_changes():
    ds = default_dataset()
    ctx = data_context(ds.connect(), ds, CLAIMS)
    assert ctx.splitlines()[0].startswith("| country | year | renewables_share_elec | solar_share_elec")
    assert "| Israel | 2025 | 16.9 | 16.2 | 0.6 | 79.7 | 3.4 |" in ctx
    assert "| Israel | change 2015->2025 (absolute) | 15.0 | 14.4 | 0.5 | 28.0 | -42.0 |" in ctx


def test_no_scope_gives_none():
    ds = default_dataset()
    assert data_context(ds.connect(), ds, [{"id": "C1", "quote": "Things improved.", "kind": "judgment"}]) == "(none)"


def test_other_dataset_uses_all_numeric_columns():
    ds = load_dataset("examples/cafes/cafes.csv")
    claims = [{"id": "C1", "quote": "Haifa sold 412 thousand cups in 2024, up from 350 thousand in 2022",
               "kind": "numeric", "sql": None}]
    ctx = data_context(ds.connect(), ds, claims)
    assert "| city | year | cups_sold_k | revenue_k_usd | avg_price_usd |" in ctx
    assert "| Haifa | change 2022->2024 (absolute) | 62.0 | 268.0 | 0.2 |" in ctx


def test_judge_prompt_receives_the_context():
    seen = {}

    def fake(prompt):
        if "Split the REPORT" in prompt:
            return {"claims": CLAIMS}
        seen["judge"] = prompt
        return {"judgments": [], "requirements": []}
    report = Path("benchmark/reports.yaml").read_text(encoding="utf-8")  # any text containing the quotes
    check_report(report, "reqs", ask=fake)
    assert "DATA CONTEXT" in seen["judge"] and "| Israel | change 2015->2025 (absolute) |" in seen["judge"]
