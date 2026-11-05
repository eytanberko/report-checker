"""Minimal LLM client (Gemini by default, Groq optional) with a disk cache, a throttle and clear quota errors.

The cache makes runs reproducible and free after the first call:
the same prompt always returns the same saved answer.

Env vars:
  LLM_PROVIDER      gemini (default) or groq
  GEMINI_API_KEY    free key from aistudio.google.com;  GEMINI_MODEL (default gemini-3.5-flash-lite)
  GROQ_API_KEY      free key from console.groq.com;     GROQ_MODEL   (default llama-3.3-70b-versatile)
  LLM_OFFLINE=1     answer from the cache only, never call an API
  LLM_MIN_INTERVAL  seconds between API calls (default 7, under the free-tier per-minute limits)
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

PROVIDERS = {
    "gemini": {"key_env": "GEMINI_API_KEY", "model_env": "GEMINI_MODEL", "model": "gemini-3.5-flash-lite",
               "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
               "signup": "aistudio.google.com"},
    "groq": {"key_env": "GROQ_API_KEY", "model_env": "GROQ_MODEL", "model": "llama-3.3-70b-versatile",
             "url": "https://api.groq.com/openai/v1/chat/completions",
             "signup": "console.groq.com"},
}
PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
if PROVIDER not in PROVIDERS:
    raise ValueError(f"LLM_PROVIDER must be one of {', '.join(PROVIDERS)}, not {PROVIDER!r}")
MODEL = os.getenv(PROVIDERS[PROVIDER]["model_env"], PROVIDERS[PROVIDER]["model"])
CACHE = Path(".llm_cache")
OFFLINE = os.getenv("LLM_OFFLINE") == "1"
MIN_INTERVAL = float(os.getenv("LLM_MIN_INTERVAL", "7"))

stats = {"calls": 0, "cache_hits": 0}  # API requests made (incl. retries) / answers served from cache
_last_call = 0.0


class LLMError(RuntimeError):
    """The LLM could not give an answer."""


class CacheMiss(LLMError):
    """Offline mode and the answer is not in the cache."""


class BadOutput(LLMError):
    """The model answered, but not with usable JSON (never cached)."""


class QuotaExhausted(LLMError):
    """The daily free-tier quota is used up; retrying today is pointless."""


def _throttle() -> None:
    global _last_call
    wait = MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _post(prompt: str, api_key: str) -> requests.Response:
    """One request to the configured provider, asking for a JSON answer at temperature 0."""
    url = PROVIDERS[PROVIDER]["url"].format(model=MODEL)
    if PROVIDER == "groq":
        body = {"model": MODEL, "temperature": 0, "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}]}
        return requests.post(url, json=body, timeout=300, headers={"Authorization": f"Bearer {api_key}"})
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    return requests.post(url, json=body, timeout=300, headers={"x-goog-api-key": api_key})


def _answer_text(r: requests.Response) -> str:
    data = r.json()
    if PROVIDER == "groq":
        return data["choices"][0]["message"]["content"]
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _quota_info(r: requests.Response) -> tuple[bool, float | None]:
    """(is a per-day quota, suggested retry delay in seconds) from a 429 response."""
    if PROVIDER == "groq":  # message says e.g. "Limit 1000, ... requests per day (RPD)"; delay in a header
        try:
            message = r.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = r.text
        delay = r.headers.get("retry-after")
        return "per day" in message.lower(), float(delay) if delay else None
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
    """Where the answer to this prompt (for the current model) is cached."""
    key = hashlib.sha256(f"{MODEL}\n{prompt}".encode()).hexdigest()[:16]
    return CACHE / f"{key}.json"


def ask_json(prompt: str, retries: int = 8) -> dict:
    """Send a prompt, get back parsed JSON."""
    CACHE.mkdir(exist_ok=True)
    cached = cache_path(prompt)
    if cached.exists():
        stats["cache_hits"] += 1
        return json.loads(cached.read_text(encoding="utf-8"))
    if OFFLINE:
        raise CacheMiss("offline mode: this prompt has no cached answer")

    conf = PROVIDERS[PROVIDER]
    api_key = os.getenv(conf["key_env"])
    if not api_key:
        raise LLMError(f"Set {conf['key_env']} (free key from {conf['signup']})")

    for attempt in range(retries):
        _throttle()
        stats["calls"] += 1
        r = _post(prompt, api_key)
        if r.status_code == 429:
            per_day, delay = _quota_info(r)
            if per_day:
                hours = f" Retry in about {delay / 3600:.1f} h." if delay else ""
                raise QuotaExhausted(f"Daily free-tier quota for {MODEL} is used up.{hours}")
            time.sleep(delay or 15 * (attempt + 1))  # per-minute limit: wait as the server asks
            continue
        if r.status_code in (500, 503):  # overload: back off 15, 30, 60, 120, 120 ... s (~10 min in total)
            time.sleep(min(120, 15 * 2 ** attempt))
            continue
        r.raise_for_status()
        try:
            result = json.loads(_answer_text(r))
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise BadOutput(f"{PROVIDER} did not return usable JSON ({type(e).__name__}: {str(e)[:80]})") from e
        if not isinstance(result, dict):
            raise BadOutput(f"{PROVIDER} returned JSON {type(result).__name__}, expected an object")
        cached.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    raise LLMError(f"{PROVIDER} kept failing: {r.status_code} {r.text[:200]}")
