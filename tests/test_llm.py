"""LLM client with a mocked HTTP layer: cache, offline mode, throttle, quota handling, Groq. No real calls."""
import json

import pytest

from checker import llm


class Resp:
    def __init__(self, status, body, headers=None):
        self.status_code, self._body, self.text = status, body, json.dumps(body)
        self.headers = headers or {}

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
GROQ_OK = Resp(200, {"choices": [{"message": {"content": '{"answer": 7}'}}]})
GROQ_PER_MINUTE = Resp(429, {"error": {"message": "Rate limit reached ... requests per minute (RPM)"}},
                       {"retry-after": "3"})
GROQ_PER_DAY = Resp(429, {"error": {"message": "Rate limit reached ... tokens per day (TPD): Limit 100000"}},
                    {"retry-after": "7200"})


@pytest.fixture
def http(tmp_path, monkeypatch):
    """Queue of fake responses; records requests and sleeps instead of waiting."""
    state = {"responses": [], "requests": [], "sleeps": []}

    def post(url, **kw):
        state["requests"].append((url, kw))
        return state["responses"].pop(0)

    monkeypatch.setattr(llm, "PROVIDER", "gemini")
    monkeypatch.setattr(llm, "MODEL", "gemini-test")
    monkeypatch.setattr(llm, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(llm, "OFFLINE", False)
    monkeypatch.setattr(llm, "_report_overloads", None)
    monkeypatch.setattr(llm.requests, "post", post)
    monkeypatch.setattr(llm.time, "sleep", lambda s: state["sleeps"].append(s))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    return state


@pytest.fixture
def groq(http, monkeypatch):
    monkeypatch.setattr(llm, "PROVIDER", "groq")
    monkeypatch.setattr(llm, "MODEL", "llama-test")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    return http


def test_answer_is_cached(http):
    http["responses"] = [OK]
    calls0, hits0 = llm.stats["calls"], llm.stats["cache_hits"]
    assert llm.ask_json("p") == {"answer": 42} and llm.ask_json("p") == {"answer": 42}
    assert len(http["requests"]) == 1 and llm.stats["calls"] - calls0 == 1 and llm.stats["cache_hits"] - hits0 == 1
    url, kw = http["requests"][0]
    assert "models/gemini-test:generateContent" in url and kw["headers"] == {"x-goog-api-key": "test-key"}


def test_offline_never_calls(http, monkeypatch):
    monkeypatch.setattr(llm, "OFFLINE", True)
    with pytest.raises(llm.CacheMiss):
        llm.ask_json("p")
    assert http["requests"] == []


def test_daily_quota_stops_immediately(http):
    http["responses"] = [PER_DAY, OK]
    with pytest.raises(llm.QuotaExhausted, match="Retry in about 8.3 h"):
        llm.ask_json("p")
    assert len(http["requests"]) == 1


def test_per_minute_limit_waits_as_told_then_succeeds(http):
    http["responses"] = [PER_MINUTE, OK]
    assert llm.ask_json("p") == {"answer": 42}
    assert 12.0 in http["sleeps"] and len(http["requests"]) == 2


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


def test_groq_request_shape_and_answer(groq):
    groq["responses"] = [GROQ_OK]
    assert llm.ask_json("p") == {"answer": 7}
    url, kw = groq["requests"][0]
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert kw["headers"] == {"Authorization": "Bearer groq-key"}
    assert kw["json"] == {"model": "llama-test", "temperature": 0, "response_format": {"type": "json_object"},
                          "messages": [{"role": "user", "content": "p"}]}


def test_groq_cache_is_separate_from_gemini(groq, monkeypatch):
    gemini_path = llm.cache_path("p")
    monkeypatch.setattr(llm, "MODEL", "gemini-test")
    assert llm.cache_path("p") != gemini_path


def test_groq_rate_limits(groq):
    groq["responses"] = [GROQ_PER_MINUTE, GROQ_OK]
    assert llm.ask_json("p") == {"answer": 7} and 3.0 in groq["sleeps"]
    groq["responses"] = [GROQ_PER_DAY]
    with pytest.raises(llm.QuotaExhausted, match="llama-test.*Retry in about 2.0 h"):
        llm.ask_json("q")


def test_groq_missing_key(groq, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    with pytest.raises(llm.LLMError, match="Set GROQ_API_KEY .*console.groq.com"):
        llm.ask_json("p")


def test_overload_waits_2_4_8_minutes_then_succeeds(http):
    busy = Resp(503, {"error": {"code": 503, "message": "high demand"}})
    http["responses"] = [busy, busy, busy, OK]
    assert llm.ask_json("p") == {"answer": 42}
    assert [s for s in http["sleeps"] if s >= 60] == [120, 240, 480] and len(http["requests"]) == 4


def test_overload_stops_cleanly_after_three_retries(http):
    busy = Resp(503, {"error": {"code": 503, "message": "high demand"}})
    http["responses"] = [busy] * 4 + [OK]
    with pytest.raises(llm.Overloaded, match="still overloaded after 3 retries; stopping to save quota"):
        llm.ask_json("p")
    assert len(http["requests"]) == 4          # 1 call + 3 retries, never a 5th
    assert isinstance(llm.Overloaded("x"), llm.LLMError)   # so evaluate.py stops cleanly and can resume


def test_overload_budget_is_per_report_across_calls(http, monkeypatch):
    busy = Resp(503, {"error": {"code": 503, "message": "high demand"}})
    llm.start_report()
    http["responses"] = [busy, busy, OK, busy, busy]        # call 1 uses 2 retries, call 2 has 1 left
    assert llm.ask_json("a") == {"answer": 42}
    with pytest.raises(llm.Overloaded):
        llm.ask_json("b")
    assert len(http["requests"]) == 5
    monkeypatch.setattr(llm, "_report_overloads", None)


def test_votes_and_salts_get_their_own_cache_entries(http, monkeypatch):
    plain = llm.cache_path("p", "m")
    assert plain == llm.CACHE / (__import__("hashlib").sha256(b"m\np").hexdigest()[:16] + ".json")  # unchanged key
    assert len({plain, llm.cache_path("p", "m", "vote-1"), llm.cache_path("p", "m", "vote-2"),
                llm.cache_path("p", "m", "repeat-1")}) == 4
    monkeypatch.setattr(llm, "JUDGE_MODEL", "judge-test")
    http["responses"] = [OK, OK]
    llm.ask_judge("p")
    llm.ask_judge("p", vote=1)
    temps = [kw["json"]["generationConfig"]["temperature"] for _, kw in http["requests"]]
    assert temps == [0.0, llm.VOTE_TEMPERATURE]
