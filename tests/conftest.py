"""Tests never call a real LLM: remove API keys so any accidental live call fails fast."""
import pytest


@pytest.fixture(autouse=True)
def _no_api_keys(monkeypatch):
    for var in ("GEMINI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
