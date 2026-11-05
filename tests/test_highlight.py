"""Inline highlighting: quote location (exact / whitespace / fuzzy), nesting, verdict banner."""
import json
from pathlib import Path

import pytest
import yaml

from checker.core import FLAGGED
from checker.highlight import locate, render_html, verdict

TEXT = "Coal fell from 45.4% of generation in 2015\nto just 3.4% in 2025, while gas reached 79.7%."


def test_locate_exact():
    s, e = locate(TEXT, "to just 3.4% in 2025")
    assert TEXT[s:e] == "to just 3.4% in 2025"


def test_locate_across_line_break_and_case():
    s, e = locate(TEXT, "generation in 2015 to just")
    assert TEXT[s:e] == "generation in 2015\nto just"


def test_locate_fuzzy_paraphrase():
    s, e = locate(TEXT, "while natural gas reached 79.7%")   # extractor added a word
    assert TEXT[s:e] == "while gas reached 79.7%"


def test_locate_returns_none_for_unrelated_quote():
    assert locate(TEXT, "Spain reached 55.9% renewables") is None
    assert locate(TEXT, "") is None


def claim(cid, quote, status, **kw):
    return {"id": cid, "quote": quote, "status": status, "note": kw.get("note", ""), "actual": kw.get("actual")}


def test_render_nests_inner_claims_and_reports_missing():
    claims = [claim("C1", "Coal fell from 45.4% of generation in 2015", "verified"),
              claim("C2", "45.4%", "contradicted", note="data says 40.00", actual=40.0),
              claim("C3", "nowhere in the text at all", "unsupported")]
    body, missing = render_html(TEXT, claims)
    assert [c["id"] for c in missing] == ["C3"]
    assert body.index("rc-green") < body.index("rc-red") < body.index("</sup></span> of generation")
    assert 'title="C2 · CONTRADICTED — data: 40 — data says 40.00"' in body


def test_render_clips_partial_overlap_and_escapes_html():
    text = "A <b>bold</b> claim about 5% and 6%"
    body, missing = render_html(text, [claim("C1", "claim about 5%", "verified"),
                                       claim("C2", "5% and 6%", "contradicted")])
    assert not missing and "&lt;b&gt;" in body and "<b>" not in body
    assert body.count("<span") == body.count("</span>") == 2


def test_verdict_text_and_level():
    result = {"claims": [claim("C1", "a", "verified"), claim("C2", "b", "contradicted"),
                         claim("C3", "c", "unsupported")],
              "requirements": [{"id": "R1", "status": "covered"}, {"id": "R2", "status": "partial"}]}
    assert verdict(result, FLAGGED) == ("error", "2 of 3 claims flagged, 1 requirement not covered")
    clean = {"claims": [claim("C1", "a", "verified")], "requirements": [{"id": "R1", "status": "covered"}]}
    assert verdict(clean, FLAGGED) == ("ok", "0 of 1 claims flagged, 0 requirements not covered")


SAVED = sorted(Path("results").glob("report_*.json"))
TEXTS = {r["id"]: r["text"] for r in
         yaml.safe_load(Path("benchmark/reports.yaml").read_text(encoding="utf-8"))["reports"]}


@pytest.mark.parametrize("path", SAVED, ids=[p.stem for p in SAVED])
def test_every_saved_claim_is_located(path):
    result = json.loads(path.read_text(encoding="utf-8"))
    _, missing = render_html(TEXTS[path.stem], result["claims"])
    assert not missing


def test_locate_stitched_quote_falls_back_to_longest_run():
    text = "Peers in 2025: Greece 49.7%,\n  Italy 48.8%, Cyprus 27.8% renewables."
    s, e = locate(text, "Greece 49.7% renewables")
    assert text[s:e] == "Greece 49.7%"
