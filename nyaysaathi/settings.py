"""Resolve configuration without initializing a model or exposing credentials."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None = field(default=None, repr=False)
    gemini_model: str | None = None
    gemini_transcription_model: str = "gemini-3.5-transcribe"


def get_settings(
    secrets: Mapping[str, object] | None = None,
    env_file: Path | None = None,
) -> Settings:
    """Per-key precedence: Streamlit secrets > environment > project .env.

    Blank values fall through. Reading .env does not mutate the environment.
    Streamlit stays outside this module so providers and tests need no UI.
    """
    local = dotenv_values(
        env_file if env_file is not None else PROJECT_ROOT / ".env",
        interpolate=False,
        encoding="utf-8-sig",
    )

    def value(name: str) -> str | None:
        for source in (secrets or {}, os.environ, local):
            candidate = source.get(name)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    return Settings(
        gemini_api_key=value("GEMINI_API_KEY"), gemini_model=value("GEMINI_MODEL"),
        gemini_transcription_model=value("GEMINI_TRANSCRIPTION_MODEL") or "gemini-3.5-transcribe",
    )
