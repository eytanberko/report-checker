"""Every "Copy link to this claim" link must open the right report with that exact claim selected and on screen."""
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from scripts import build_site

ROOT = Path(__file__).resolve().parent.parent
EDGE = Path(os.environ.get("EDGE_PATH", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"))


@pytest.fixture(scope="module")
def data():
    return build_site.build()


def rendered_ids(segments):
    out = set()
    for s in segments:
        if "c" in s:
            out |= {s["c"]} | rendered_ids(s["k"])
    return out


def claim_links(data):
    """The link app.js builds for every claim: <page>#<report id>/<claim id>."""
    return [f"#{r['id']}/{c['id']}" for r in data["reports"] for c in r["claims"]]


def resolve(data, link):
    """Mirror of app.js fromHash(): the report and claim a link opens (None when it would not resolve)."""
    m = re.fullmatch(r"#(report_\d+)/(C\d+)", link)
    if not m:
        return None
    report = next((r for r in data["reports"] if r["id"] == m[1]), None)
    if report is None or m[2] not in {c["id"] for c in report["claims"]}:
        return None
    return report, m[2]


def test_every_claim_link_resolves_to_its_report_and_a_rendered_claim(data):
    links = claim_links(data)
    assert len(links) == sum(len(r["claims"]) for r in data["reports"]) == len(set(links))
    for link in links:
        hit = resolve(data, link)
        assert hit is not None, link
        report, claim_id = hit
        assert link == f"#{report['id']}/{claim_id}"
        assert claim_id in rendered_ids(report["segments"]), f"{link}: claim not drawn in the report text"


def test_bad_links_do_not_resolve(data):
    assert resolve(data, "#report_99/C1") is None
    assert resolve(data, "#report_02/C999") is None
    assert resolve(data, "#report_02") is None


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge not installed: browser check skipped")
@pytest.mark.parametrize("width", [1440, 390])
def test_every_claim_link_works_in_a_browser(width):
    page = (ROOT / "tests" / "site" / "linkcheck.html").as_uri() + f"?w={width}"
    out = subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--allow-file-access-from-files",
                          "--virtual-time-budget=120000", "--window-size=1500,900", "--dump-dom", page],
                         capture_output=True, text=True, timeout=300).stdout
    m = re.search(r'data-out="([^"]*)"', out)
    assert m, "the link check did not finish"
    result = json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    assert result["fails"] == [] and result["ok"] == result["total"] > 100, result
