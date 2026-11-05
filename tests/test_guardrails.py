"""SQL guardrails: deliberately bad queries must be caught as query_mismatch, good ones must pass."""
import pytest

from checker.core import check_numeric
from checker.dataset import default_dataset
from checker.guardrails import Catalog, check_query

REPORT = ("Renewables provided 16.9% of Israel's electricity in 2025, up from 1.9% in 2015. "
          "Coal dropped to 3.4% in 2025 from 45.4% ten years earlier. "
          "Generation grew from 64.2 TWh to 82.1 TWh. "
          "In the region, Egypt reached 13.0% renewables in 2025, behind Israel, while Greece reached 49.7%.")


@pytest.fixture(scope="module")
def db():
    con = default_dataset().connect()
    return con, Catalog.from_connection(con, "energy")


def q(col, country, year):
    return f"SELECT {col} FROM energy WHERE country = '{country}' AND year = {year}"


@pytest.mark.parametrize("quote,sql", [
    ("16.9% of Israel's electricity in 2025", q("renewables_share_elec", "Israel", 2025)),
    ("from 45.4% ten years earlier", q("coal_share_elec", "Israel", 2015)),       # implied year
    ("to 82.1 TWh", q("electricity_generation", "Israel", 2025)),                 # implied country + year
    ("behind Israel", "SELECT CASE WHEN (" + q("renewables_share_elec", "Egypt", 2025) + ") < ("
                      + q("renewables_share_elec", "Israel", 2025) + ") THEN 1 ELSE 0 END"),
    ("Greece reached 49.7%", q("renewables_share_elec", "Greece", 2025)),
])
def test_good_queries_pass(db, quote, sql):
    assert check_query(*db, sql, quote, REPORT) is None


@pytest.mark.parametrize("quote,sql,reason", [
    ("16.9% of Israel's electricity in 2025", q("renewable_share", "Israel", 2025), "not in the data"),
    ("16.9% of Israel's electricity in 2025", q("renewables_share_elec", "Isreal", 2025), "'Isreal'"),
    ("16.9% of Israel's electricity in 2025", q("renewables_share_elec", "israel", 2025), "'israel'"),
    ("16.9% of Israel's electricity in 2025", q("renewables_share_elec", "Israel", 2030), "outside the data"),
    ("16.9% of Israel's electricity in 2025", "SELECT renewables_share_elec FROM energy WHERE country = 'Israel' "
                                              "AND year BETWEEN 2005 AND 2025", "outside the data"),
    ("Greece reached 49.7%", q("renewables_share_elec", "Cyprus", 2025), "uses Cyprus"),
    ("16.9% of Israel's electricity in 2025", q("renewables_share_elec", "Israel", 2024), "year 2024"),
    ("from 45.4% ten years earlier", q("coal_share_elec", "Israel", 2016), "year 2016"),
    ("16.9% of Israel's electricity in 2025", "SELECT renewables_share_elec FROM energies WHERE year = 2025",
     "not in the data"),
])
def test_bad_queries_are_caught(db, quote, sql, reason):
    msg = check_query(*db, sql, quote, REPORT)
    assert msg is not None and reason in msg


def test_pipeline_marks_query_mismatch_not_report_error(db):
    con, _ = db
    claims = [{"id": "C1", "kind": "numeric", "quote": "Greece reached 49.7%", "stated_value": 49.7,
               "sql": q("renewables_share_elec", "Cyprus", 2025)},
              {"id": "C2", "kind": "numeric", "quote": "Greece reached 49.7%", "stated_value": 49.7,
               "sql": q("renewables_share_elec", "Greece", 2025)}]
    out = check_numeric(con, claims, REPORT)
    assert [c["status"] for c in out] == ["query_mismatch", "verified"]
    assert out[0]["actual"] is None and "uses Cyprus" in out[0]["note"]


def test_unsafe_sql_is_still_rejected_by_the_verifier(db):
    con, _ = db
    out = check_numeric(con, [{"id": "C1", "kind": "numeric", "quote": "x", "stated_value": 1,
                               "sql": "DROP TABLE energy"}], REPORT)
    assert out[0]["status"] == "unverifiable" and out[0]["note"].startswith("rejected")
