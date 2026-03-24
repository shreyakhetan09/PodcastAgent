from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _truthy(value: str) -> bool:
    """Return True if ``value`` looks like an enabled boolean flag."""
    return value.strip().lower() in ("1", "true", "yes", "on")


def _load_env() -> None:
    """Load variables from the project-root ``.env`` file, overriding existing shell values."""
    load_dotenv(_ENV_PATH, override=True)


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    groq_api_key: str
    gemini_api_key: str
    use_groq_only: bool
    gemini_model: str = "gemini-2.0-flash"
    groq_model: str = "llama-3.3-70b-versatile"
    whisper_model: str = "tiny"
    clip_minutes: int = 4
    max_workers: int = 3
    output_path: str = "intelligence_briefing.md"


def get_settings() -> Settings:
    """Read and validate settings from the environment (after loading ``.env``)."""
    _load_env()
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    use_groq_only = _truthy(os.getenv("USE_GROQ_ONLY", ""))

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"
    groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"

    if use_groq_only:
        if not groq_api_key:
            raise ValueError("Missing GROQ_API_KEY (required when USE_GROQ_ONLY is set).")
    else:
        if not gemini_api_key:
            raise ValueError("Missing GEMINI_API_KEY, or set USE_GROQ_ONLY=1 with GROQ_API_KEY.")

    return Settings(
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        use_groq_only=use_groq_only,
        gemini_model=gemini_model,
        groq_model=groq_model,
    )
