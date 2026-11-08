"""Network guard: automated tests must never construct a real Gemini client."""

from unittest.mock import Mock

import pytest


@pytest.fixture(autouse=True)
def block_live_gemini(monkeypatch):
    monkeypatch.setattr(
        "google.genai.Client",
        Mock(side_effect=AssertionError("Live Gemini calls are forbidden in tests")),
    )
