"""Internal consistency: the report's own numbers vs each other, no data access."""
import json
from pathlib import Path

import pytest
import yaml

from checker.consistency import ENERGY_SHARES, apply_issues, find_issues, parse_key
from checker.core import recheck

TEXTS = {r["id"]: r["text"] for r in
         yaml.safe_load(Path("benchmark/reports.yaml").read_text(encoding="utf-8"))["reports"]}

COLS = ["country", "year", "renewables_share_elec", "solar_share_elec", "wind_share_elec", "gas_share_elec",
        "coal_share_elec", "oil_share_elec", "fossil_share_elec", "electricity_generation"]


def point(cid, quote, value, col, year, country="Israel", status="unverifiable"):
    return {"id": cid, "kind": "numeric", "quote": quote, "stated_value": value, "status": status, "note": "",
            "sql": f"SELECT {col} FROM energy WHERE country='{country}' AND year={year}"}


def change(cid, quote, value, col, y1=2015, y2=2025, status="unverifiable"):
    sql = (f"SELECT (SELECT {col} FROM energy WHERE country='Israel' AND year={y2}) - "
           f"(SELECT {col} FROM energy WHERE country='Israel' AND year={y1})")
    return {"id": cid, "kind": "numeric", "quote": quote, "stated_value": value, "sql": sql,
            "status": status, "note": ""}


RENEW = [point("C1", "16.9% in 2025", 16.9, "renewables_share_elec", 2025),
         point("C2", "1.9% in 2015", 1.9, "renewables_share_elec", 2015)]
GEN = [point("C1", "82.1 TWh", 82.1, "electricity_generation", 2025),
       point("C2", "64.2 TWh", 64.2, "electricity_generation", 2015)]


def issues(claims):
    return find_issues(claims, COLS, shares=ENERGY_SHARES)


def test_parse_key():
    assert parse_key(RENEW[0]["sql"], COLS) == ("renewables_share_elec", "Israel", (2025,))
    assert parse_key(change("C", "x", 1, "gas_share_elec")["sql"], COLS) == ("gas_share_elec", "Israel", (2015, 2025))
    assert parse_key("SELECT CASE WHEN 1 > 0 THEN 1 ELSE 0 END", COLS) is None


@pytest.mark.parametrize("quote,value,base", [
    ("an increase of 15 percentage points", 15, RENEW),
    ("about 15 percentage points more", 15, RENEW),
    ("renewables grew by 791%", 791, RENEW),
    ("about 28%", 28, GEN),
    ("2.5% per year on average", 2.5, GEN),
    ("8.9 times as much", 8.9, RENEW),
])
def test_consistent_changes_pass(quote, value, base):
    col = base[0]["sql"].split()[1]
    assert issues(base + [change("C9", quote, value, col)]) == []


@pytest.mark.parametrize("quote,value,base,expect", [
    ("an increase of 15%", 15, RENEW, "+15.0 percentage points"),         # % vs percentage points
    ("renewables grew by 891%", 891, RENEW, "+789.5%"),                    # ratio x100, not % change
    ("2.8% per year on average", 2.8, GEN, "+2.49% per year compounded"),  # simple average, not CAGR
    ("an increase of 20 percentage points", 20, RENEW, "+15.0 percentage points"),
])
def test_inconsistent_changes_are_found(quote, value, base, expect):
    col = base[0]["sql"].split()[1]
    found = issues(base + [change("C9", quote, value, col)])
    assert len(found) == 1 and found[0].kind == "change" and [c["id"] for c in found[0].suspects] == ["C9"]
    assert expect in found[0].note


def test_a_fall_stated_as_positive_number_is_consistent():
    coal = [point("C1", "45.4% in 2015", 45.4, "coal_share_elec", 2015),
            point("C2", "3.4% in 2025", 3.4, "coal_share_elec", 2025)]
    assert issues(coal + [change("C3", "fell by 42 percentage points", 42, "coal_share_elec")]) == []


def test_change_without_both_endpoints_is_not_checked():
    assert issues([RENEW[0], change("C9", "rose by 15%", 15, "renewables_share_elec")]) == []


def test_shares_above_100_percent():
    claims = [point("C1", "16.9%", 16.9, "renewables_share_elec", 2025),
              point("C2", "79.7%", 79.7, "gas_share_elec", 2025),
              point("C3", "13.4%", 13.4, "coal_share_elec", 2025)]
    found = issues(claims)
    assert [i.kind for i in found] == ["shares"] and len(found[0].suspects) == 3
    assert issues(claims[:2] + [point("C3", "3.4%", 3.4, "coal_share_elec", 2025)]) == []


def test_part_larger_than_whole():
    found = issues([point("C1", "16.9%", 16.9, "renewables_share_elec", 2025),
                    point("C2", "solar 18.2%", 18.2, "solar_share_elec", 2025)])
    assert [i.kind for i in found] == ["parts"]


def test_same_metric_two_values():
    gas = point("C1", "79.7%", 79.7, "gas_share_elec", 2025)
    assert issues([gas, point("C2", "four out of five kilowatt-hours", 80, "gas_share_elec", 2025)]) == []
    found = issues([gas, point("C2", "gas at 69.7%", 69.7, "gas_share_elec", 2025)])
    assert [i.kind for i in found] == ["duplicate"]


def test_data_verdicts_take_precedence():
    claims = [point("C1", "16.9%", 16.9, "renewables_share_elec", 2025, status="verified"),
              point("C2", "79.7%", 79.7, "gas_share_elec", 2025, status="verified"),
              point("C3", "13.4%", 13.4, "coal_share_elec", 2025, status="contradicted")]
    out = {c["id"]: c for c in apply_issues(claims, issues(claims))}
    assert [out[i]["status"] for i in ("C1", "C2", "C3")] == ["verified", "verified", "contradicted"]
    assert "also inconsistent: shares for Israel 2025" in out["C3"]["note"]


def test_without_data_suspects_become_inconsistent():
    claims = RENEW + [change("C9", "an increase of 15%", 15, "renewables_share_elec")]
    out = apply_issues(claims, issues(claims))
    assert [c["status"] for c in out] == ["unverifiable", "unverifiable", "inconsistent"]


@pytest.mark.parametrize("rid", [f"report_0{i}" for i in range(1, 8)])
def test_recheck_of_saved_results_changes_no_verdicts(rid):
    saved = json.loads(Path(f"results/{rid}.json").read_text(encoding="utf-8"))
    after = recheck(saved, TEXTS[rid])
    assert [c["status"] for c in after["claims"]] == [c["status"] for c in saved["claims"]]
