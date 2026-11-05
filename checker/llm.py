"""Minimal Gemini client (free tier) with a disk cache.

The cache makes runs reproducible and free after the first call:
the same prompt always returns the same saved answer.
Needs env var GEMINI_API_KEY (get one at aistudio.google.com).
"""
import hashlib
import json
import os
import time
from pathlib import Path

import requests

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
CACHE = Path(".llm_cache")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def ask_json(prompt: str, retries: int = 5) -> dict:
    """Send a prompt, get back parsed JSON."""
    CACHE.mkdir(exist_ok=True)
    key = hashlib.sha256(f"{MODEL}\n{prompt}".encode()).hexdigest()[:16]
    cached = CACHE / f"{key}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY (free key from aistudio.google.com)")

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    for attempt in range(retries):
        r = requests.post(URL.format(model=MODEL), json=body, timeout=300,
                          headers={"x-goog-api-key": api_key})
        if r.status_code in (429, 500, 503):          # free-tier rate limit / overload
            time.sleep(15 * (attempt + 1))
            continue
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
        cached.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    raise RuntimeError(f"Gemini kept failing: {r.status_code} {r.text[:200]}")
