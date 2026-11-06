"""Bring your own data: auto-built schema + the deterministic pipeline on a second dataset (fake LLM)."""
from pathlib import Path

import pytest

from checker.core import check_report
from checker.dataset import BadCSV, load_dataset, load_upload, table_name
from checker.schema import SCHEMA

CAFES = "examples/cafes/cafes.csv"
REPORT = Path("examples/cafes/report.md").read_text(encoding="utf-8")


def test_table_name():
    assert table_name("data/Cafe sales-2024.csv") == "cafe_sales_2024"
    assert table_name("2024.csv") == "t_2024"
    assert table_name("select.csv") == "t_select"          # an SQL keyword would break the model's queries


@pytest.mark.parametrize("name,data,message", [
    ("a.csv", b"  \n", "The file is empty."),
    ("a.csv", b"city,year\n", "header row but no data rows"),
    ("a.csv", b"city,name\nHaifa,Dana\n", "no numeric columns"),
    ("a.csv", bytes(range(256)) * 20, "Could not read the file as a CSV"),
])
def test_uploaded_csv_that_cannot_be_used_says_why(tmp_path, name, data, message):
    with pytest.raises(BadCSV, match=message):
        load_upload(name, data, tmp_path)


def test_uploaded_csv_gets_the_same_auto_schema(tmp_path):
    ds = load_upload("cafes.csv", Path(CAFES).read_bytes(), tmp_path)
    assert ds.description == load_dataset(CAFES).description and ds.table == "cafes"
    assert load_upload("Select.csv", b"city;year;v\nA;2020;1\n", tmp_path).table == "t_select"


def test_auto_schema_describes_columns_types_ranges_and_categories():
    ds = load_dataset(CAFES)
    assert (ds.table, ds.entity_col, ds.time_col) == ("cafes", "city", "year")
    d = ds.description
    assert "Table `cafes` (8 rows, from cafes.csv; one row per city per year)." in d
    assert "- city (text): 3 distinct values: Haifa, Jerusalem, Tel Aviv" in d
    assert "- year (int): 2,022 to 2,024" not in d and "- year (int): 2022 to 2024" in d
    assert "- revenue_k_usd (int): 870 to 2,135, e.g. 1,050" in d
    assert "- avg_price_usd (number): 2.9 to 3.5, e.g. 3" in d
    assert "1 of 3 city values have no row for the latest year." in d


def test_energy_keeps_hand_written_description_and_override_works():
    assert load_dataset("data/energy.csv").description == SCHEMA
    assert load_dataset(CAFES, description="my words").description == "my words"


def q(col, city, year):
    return f"SELECT {col} FROM cafes WHERE city = '{city}' AND year = {year}"


def fake_llm(prompt: str) -> dict:
    if "Split the REPORT" in prompt:
        assert "over table `cafes`" in prompt and "Use the city and year the claim refers to" in prompt
        assert "city (text): 3 distinct values" in prompt
        def claim(i, quote, v, sql):
            return {"id": i, "quote": quote, "kind": "numeric", "stated_value": v, "sql": sql}
        return {"claims": [
            claim("C1", "Haifa sold 412 thousand cups in 2024", 412, q("cups_sold_k", "Haifa", 2024)),
            claim("C2", "up from 350 thousand in 2022", 350, q("cups_sold_k", "Haifa", 2022)),
            claim("C3", "an increase of 25%", 25, "SELECT 100.0 * ((" + q("cups_sold_k", "Haifa", 2024) + ") - ("
                  + q("cups_sold_k", "Haifa", 2022) + ")) / (" + q("cups_sold_k", "Haifa", 2022) + ")"),
            claim("C4", "Haifa's revenue reached 1,480 thousand USD in 2024", 1480, q("revenue_k_usd", "Haifa", 2024)),
            claim("C5", "Tel Aviv sold 610 thousand cups in 2024", 610, q("cups_sold_k", "Tel-Aviv", 2024)),
            {"id": "C6", "quote": "more than any other city", "kind": "judgment", "stated_value": None, "sql": None},
            claim("C7", "Jerusalem sold 345 thousand cups in 2024", 345, q("cups_sold_k", "Jerusalem", 2024)),
        ]}
    return {"judgments": [{"id": "C6", "verdict": "supported", "reason": "610 is the highest"}],
            "requirements": [{"id": "R1", "status": "covered"}, {"id": "R2", "status": "covered"}]}


def test_pipeline_on_second_dataset():
    result = check_report(REPORT, "reqs", ask=fake_llm, dataset=load_dataset(CAFES))
    by_id = {c["id"]: c for c in result["claims"]}
    assert {i: c["status"] for i, c in by_id.items()} == {
        "C1": "verified", "C2": "verified", "C3": "contradicted", "C4": "contradicted",
        "C5": "query_mismatch", "C6": "supported", "C7": "unverifiable"}
    assert "also inconsistent" in by_id["C3"]["note"] and "+17.7%" in by_id["C3"]["note"]   # consistency
    assert by_id["C4"]["actual"] == 1318                                                       # verify
    assert "'Tel-Aviv'" in by_id["C5"]["note"]                                                 # guardrails
    assert by_id["C7"]["note"] == "no data for this claim"


def test_auto_schema_formats_large_numbers_readably():
    from checker.dataset import Dataset, describe
    text, entity, time = describe(Dataset("data/energy.csv", "energy", "", None, None).connect(), "energy")
    assert (entity, time) == ("country", "year") and "e+" not in text
    assert "- electricity_generation (number): 4.29 to 31,772" in text
