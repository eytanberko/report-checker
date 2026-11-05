"""Every report page must tell one story: the marked report, the tile, the requirements, the memo and the answer
key are all derived from the same result, so their counts and statuses have to agree."""
import re

import pytest

from evaluate import FLAGGED
from scripts import build_site


@pytest.fixture(scope="module")
def data():
    return build_site.build()


def memo_section(memo, title):
    m = re.search(rf"## \d+\. {title} \((\d+)\)", memo)
    return int(m.group(1)) if m else 0


@pytest.mark.parametrize("i", range(10))
def test_report_page_is_internally_consistent(data, i):
    r = data["reports"][i]
    n = lambda *s: sum(c["status"] in s for c in r["claims"])  # noqa: E731
    # memo counts == the claims' statuses == what the tile shows
    assert memo_section(r["memo"], "Wrong numbers") == n("contradicted", "inconsistent")
    assert memo_section(r["memo"], "Unsupported conclusions") == n("unsupported")
    assert memo_section(r["memo"], "Could not verify") == n("unverifiable")
    assert memo_section(r["memo"], "Requirements not met") == sum(q["status"] != "covered" for q in r["requirements"])
    # the answer key's flagged list is exactly the flagged claims
    assert set(r["answer_key"]["flagged"]) == {c["id"] for c in r["claims"] if c["status"] in FLAGGED}
    # a planted claim error marked caught has a flagged claim on the page (requirement errors: a gap)
    for p in r["answer_key"]["planted"]:
        if p["caught"] and not p["target"].startswith("R"):
            assert any(c["status"] in FLAGGED and (p["target"].lower() in c["quote"].lower()
                                                   or c["quote"].lower() in p["target"].lower())
                       for c in r["claims"]), (r["id"], p)
        if p["caught"] and p["target"].startswith("R"):
            assert any(q["id"] == p["target"] and q["status"] != "covered" for q in r["requirements"])
    # "answered, but with a contradicted figure" only on answered requirements
    for q in r["requirements"]:
        assert q["flag"] is None or q["status"] == "covered"
