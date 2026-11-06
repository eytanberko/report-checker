"""Tests for the deterministic SQL verification (no LLM, no API key needed)."""
import pytest

from checker.dataset import default_dataset
from checker.verify import run_sql, verify_claim


@pytest.fixture(scope="module")
def con():
    return default_dataset().connect()


def claim(sql, stated):
    return {"id": "C1", "quote": "x", "kind": "numeric", "sql": sql, "stated_value": stated}


RENEW_2025 = "SELECT renewables_share_elec FROM energy WHERE country='Israel' AND year=2025"
GEN_PCT = ("SELECT 100.0*(a.electricity_generation-b.electricity_generation)/b.electricity_generation "
           "FROM energy a, energy b WHERE a.country='Israel' AND b.country='Israel' AND a.year=2025 AND b.year=2015")


def test_correct_rounded_value_is_verified(con):
    assert verify_claim(con, claim(RENEW_2025, 16.9))["status"] == "verified"


def test_wrong_value_is_contradicted(con):
    r = verify_claim(con, claim(RENEW_2025, 13.4))
    assert r["status"] == "contradicted" and r["actual"] == pytest.approx(16.93, abs=0.01)


def test_percent_change(con):
    assert verify_claim(con, claim(GEN_PCT, 28))["status"] == "verified"
    assert verify_claim(con, claim(GEN_PCT, 17.9))["status"] == "contradicted"


def test_comparison_claim(con):
    sql = ("SELECT CASE WHEN (SELECT renewables_share_elec FROM energy WHERE country='Greece' AND year=2025) > "
           "(SELECT renewables_share_elec FROM energy WHERE country='Israel' AND year=2025) THEN 1 ELSE 0 END")
    assert verify_claim(con, claim(sql, 1))["status"] == "verified"


def test_missing_year_is_unverifiable(con):
    sql = "SELECT renewables_share_elec FROM energy WHERE country='Jordan' AND year=2025"
    assert verify_claim(con, claim(sql, 25))["status"] == "unverifiable"


@pytest.mark.parametrize("bad", ["DROP TABLE energy", "SELECT 1; DROP TABLE energy",
                                 "SELECT * FROM read_csv_auto('x'); COPY energy TO 'y'"])
def test_only_select_allowed(con, bad):
    assert run_sql(con, bad)[1].startswith("rejected")


def test_sql_errors_and_text_results_are_reported_not_raised(con):
    value, err = run_sql(con, "SELECT no_such_column FROM energy")
    assert value is None and err.startswith("sql error:")
    value, err = run_sql(con, "SELECT country FROM energy WHERE country='Israel' LIMIT 1")
    assert value is None and err == "non-numeric result: 'Israel'"


def test_a_failing_query_makes_the_claim_unverifiable(con):
    out = verify_claim(con, claim("SELECT no_such_column FROM energy", 16.9))
    assert out["status"] == "unverifiable" and out["actual"] is None and out["note"].startswith("sql error:")
