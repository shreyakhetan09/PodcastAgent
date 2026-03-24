from __future__ import annotations

import argparse
import os

from src.agent_pipeline import run_pipeline
from src.config import _ENV_PATH, _load_env, get_settings


def main() -> None:
    """CLI entry: load env, optional ``--debug-env``, then run the full pipeline."""
    parser = argparse.ArgumentParser(description="Podcast Intelligence pipeline runner")
    parser.add_argument(
        "--debug-env",
        action="store_true",
        help="Print safe .env diagnostics (length/prefix only; never prints secrets).",
    )
    args = parser.parse_args()

    _load_env()

    if args.debug_env:
        key = os.getenv("GROQ_API_KEY", "")
        print("Loaded .env path:", _ENV_PATH)
        print(".env file exists:", _ENV_PATH.is_file())
        print("GROQ_API_KEY length:", len(key))
        print("GROQ_API_KEY starts with gsk_:", key.startswith("gsk_"))
        print("USE_GROQ_ONLY:", repr(os.getenv("USE_GROQ_ONLY", "")))
        print("GEMINI_API_KEY set:", bool(os.getenv("GEMINI_API_KEY", "").strip()))
        return

    settings = get_settings()
    # Assignment: google-adk end-to-end — InMemoryRunner, LlmAgent, ingest + transcribe FunctionTools → .md
    report = run_pipeline(settings=settings)
    print("Saved intelligence briefing to:", settings.output_path)
    print()
    print(report[:1200] + ("..." if len(report) > 1200 else ""))


if __name__ == "__main__":
    main()
