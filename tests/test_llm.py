"""LLM client with a mocked HTTP layer: cache, offline mode, throttle, quota handling. No real calls."""
import json

import pytest

from checker import llm


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


OK = Resp(200, {"candidates": [{"content": {"parts": [{"text": '{"answer": 42}'}]}}]})
PER_DAY = Resp(429, {"error": {"details": [
    {"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "30056s"}]}})
PER_MINUTE = Resp(429, {"error": {"details": [
    {"violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
    {"retryDelay": "12s"}]}})


@pytest.fixture
def http(tmp_path, monkeypatch):
    """Queue of fake responses; records requests and sleeps instead of waiting."""
    state = {"responses": [], "posts": 0, "sleeps": []}

    def post(url, **kw):
        state["posts"] += 1
        assert kw["headers"]["x-goog-api-key"] == "test-key"
        return state["responses"].pop(0)

    monkeypatch.setattr(llm, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(llm, "OFFLINE", False)
    monkeypatch.setattr(llm.requests, "post", post)
    monkeypatch.setattr(llm.time, "sleep", lambda s: state["sleeps"].append(s))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    return state


def test_answer_is_cached(http):
    http["responses"] = [OK]
    calls0, hits0 = llm.stats["calls"], llm.stats["cache_hits"]
    assert llm.ask_json("p") == {"answer": 42} and llm.ask_json("p") == {"answer": 42}
    assert http["posts"] == 1 and llm.stats["calls"] - calls0 == 1 and llm.stats["cache_hits"] - hits0 == 1


def test_offline_never_calls(http, monkeypatch):
    monkeypatch.setattr(llm, "OFFLINE", True)
    with pytest.raises(llm.CacheMiss):
        llm.ask_json("p")
    assert http["posts"] == 0


def test_daily_quota_stops_immediately(http):
    http["responses"] = [PER_DAY, OK]
    with pytest.raises(llm.QuotaExhausted, match="Retry in about 8.3 h"):
        llm.ask_json("p")
    assert http["posts"] == 1


def test_per_minute_limit_waits_as_told_then_succeeds(http):
    http["responses"] = [PER_MINUTE, OK]
    assert llm.ask_json("p") == {"answer": 42}
    assert 12.0 in http["sleeps"] and http["posts"] == 2


def test_throttle_spaces_out_calls(http, monkeypatch):
    clock = iter([100.0, 100.0, 101.0, 101.0])
    monkeypatch.setattr(llm.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(llm, "_last_call", 0.0)
    monkeypatch.setattr(llm, "MIN_INTERVAL", 7.0)
    http["responses"] = [OK, OK]
    llm.ask_json("a")
    llm.ask_json("b")
    assert http["sleeps"] == [6.0]


def test_missing_key_is_a_clear_error(http, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(llm.LLMError, match="Set GEMINI_API_KEY"):
        llm.ask_json("p")
