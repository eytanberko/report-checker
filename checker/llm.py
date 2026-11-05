"""Minimal Gemini client (free tier) with a disk cache, a throttle and clear quota errors.

The cache makes runs reproducible and free after the first call:
the same prompt always returns the same saved answer.
Needs env var GEMINI_API_KEY (get one at aistudio.google.com).

Env vars: GEMINI_MODEL, LLM_OFFLINE=1 (cache only), LLM_MIN_INTERVAL (seconds between API calls).
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
CACHE = Path(".llm_cache")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OFFLINE = os.getenv("LLM_OFFLINE") == "1"  # answer from the cache only, never call the API
MIN_INTERVAL = float(os.getenv("LLM_MIN_INTERVAL", "7"))  # free tier allows ~10 requests/minute

stats = {"calls": 0, "cache_hits": 0}  # API requests made (incl. retries) / answers served from cache
_last_call = 0.0


class LLMError(RuntimeError):
    """The LLM could not give an answer."""


class CacheMiss(LLMError):
    """Offline mode and the answer is not in the cache."""


class QuotaExhausted(LLMError):
    """The daily free-tier quota is used up; retrying today is pointless."""


def _throttle() -> None:
    global _last_call
    wait = MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _quota_info(r: requests.Response) -> tuple[bool, float | None]:
    """(is a per-day quota, server's suggested retry delay in seconds) from a 429 response."""
    try:
        details = r.json()["error"].get("details", [])
    except (ValueError, KeyError, AttributeError):
        return False, None
    per_day, delay = False, None
    for d in details:
        for v in d.get("violations", []):
            per_day = per_day or "PerDay" in v.get("quotaId", "")
        if "retryDelay" in d:
            m = re.match(r"([\d.]+)s", d["retryDelay"])
            delay = float(m.group(1)) if m else None
    return per_day, delay


def cache_path(prompt: str) -> Path:
    key = hashlib.sha256(f"{MODEL}\n{prompt}".encode()).hexdigest()[:16]
    return CACHE / f"{key}.json"


def ask_json(prompt: str, retries: int = 5) -> dict:
    """Send a prompt, get back parsed JSON."""
    CACHE.mkdir(exist_ok=True)
    cached = cache_path(prompt)
    if cached.exists():
        stats["cache_hits"] += 1
        return json.loads(cached.read_text(encoding="utf-8"))
    if OFFLINE:
        raise CacheMiss("offline mode: this prompt has no cached answer")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise LLMError("Set GEMINI_API_KEY (free key from aistudio.google.com)")

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    for attempt in range(retries):
        _throttle()
        stats["calls"] += 1
        r = requests.post(URL.format(model=MODEL), json=body, timeout=300,
                          headers={"x-goog-api-key": api_key})
        if r.status_code == 429:
            per_day, delay = _quota_info(r)
            if per_day:
                hours = f" Retry in about {delay / 3600:.1f} h." if delay else ""
                raise QuotaExhausted(f"Daily free-tier quota for {MODEL} is used up.{hours}")
            time.sleep(delay or 15 * (attempt + 1))  # per-minute limit: wait as the server asks
            continue
        if r.status_code in (500, 503):  # overload
            time.sleep(15 * (attempt + 1))
            continue
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
        cached.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    raise LLMError(f"Gemini kept failing: {r.status_code} {r.text[:200]}")
