"""CLI: saved benchmark runs, offline cache misses, any dataset (fake LLM), memo file, exit codes."""
from pathlib import Path

import pytest
import yaml

from checker import cli, llm
from tests.test_dataset import fake_llm

TEXTS = {r["id"]: r["text"] for r in
         yaml.safe_load(Path("benchmark/reports.yaml").read_text(encoding="utf-8"))["reports"]}


@pytest.fixture(autouse=True)
def _restore_offline(monkeypatch):
    monkeypatch.setattr(llm, "OFFLINE", False)


def run(tmp_path, text, *extra):
    report = tmp_path / "r.md"
    report.write_text(text, encoding="utf-8")
    return cli.main(["check", "--report", str(report), "--requirements", "benchmark/requirements.md", *extra])


def test_saved_benchmark_run_prints_verdict_and_writes_memo(tmp_path, capsys):
    assert run(tmp_path, TEXTS["report_03"], "--offline") == 1
    out = capsys.readouterr().out
    assert "Using saved run results/report_03.json" in out and "VERDICT: 3 of 9 claims flagged" in out
    memo = (tmp_path / "r.review.md").read_text(encoding="utf-8")
    assert memo.startswith("# Review: r.md") and "## 1. Wrong numbers (2)" in memo


def test_clean_report_exits_zero_and_custom_out(tmp_path):
    out = tmp_path / "memo.md"
    assert run(tmp_path, TEXTS["report_01"], "--offline", "--out", str(out)) == 0
    assert "Good to send." in out.read_text(encoding="utf-8")


def test_offline_without_cache_exits_two(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(llm, "CACHE", tmp_path / "empty_cache")
    assert run(tmp_path, "Israel's renewables were 99% in 2025.", "--offline") == 2
    assert "No saved or cached result" in capsys.readouterr().err


def test_any_dataset_with_fake_llm(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(llm, "ask_json", fake_llm)
    out = tmp_path / "cafes.review.md"
    code = cli.main(["check", "--report", "examples/cafes/report.md", "--requirements",
                     "examples/cafes/requirements.md", "--data", "examples/cafes/cafes.csv", "--out", str(out)])
    assert code == 1 and "VERDICT: 3 of 7 claims flagged" in capsys.readouterr().out
    memo = out.read_text(encoding="utf-8")
    assert "Correct it to 1,318" in memo and "'Tel-Aviv'" in memo
