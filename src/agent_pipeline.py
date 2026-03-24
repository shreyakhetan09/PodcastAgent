from __future__ import annotations

import asyncio
import os
from typing import Any, Callable

from google.genai import types

from .config import Settings
from .prompts import ADK_SYSTEM_INSTRUCTION, build_user_task
from .report import save_report
from .tools import ingest_latest_episodes, transcribe_all_parallel

DEFAULT_FEEDS = [
    "https://lexfridman.com/feed/podcast/",
    "https://changelog.com/practicalai/feed",
    "https://www.latent.space/feed",
]

APP_NAME = "podcast_intel_adk"
AGENT_NAME = "podcast_intel_agent"


def _clip_minutes(settings: Settings) -> int:
    return max(3, min(5, int(settings.clip_minutes)))


def _flatten_episode_dicts(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if item.get("audio_url"):
            out.append(item)
            continue
        inner = item.get("episode")
        if isinstance(inner, dict) and inner.get("audio_url"):
            out.append(inner)
            continue
        raise ValueError(
            "Each episode must include audio_url (use ingest output as-is). "
            f"Got keys: {list(item.keys())}"
        )
    if len(out) != 3:
        raise ValueError(f"Expected 3 episodes with audio_url; got {len(out)}")
    return out


def _make_tools(settings: Settings) -> tuple[Callable[..., Any], Callable[..., Any]]:
    # The LLM sometimes fabricates tool arguments; always transcribe the real ingest result.
    last_ingest: list[dict[str, Any]] | None = None

    def ingest_latest_podcast_episodes(feed_urls: list[str]) -> list[dict[str, Any]]:
        """Ingestion tool: three RSS feeds → latest episode each, with audio URL (ADK FunctionTool)."""
        nonlocal last_ingest
        last_ingest = ingest_latest_episodes(feed_urls, max_workers=settings.max_workers)
        return last_ingest

    def transcribe_intro_snippets(episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transcription tool: download 3–5 min clips, Whisper transcribe (ADK FunctionTool)."""
        nonlocal last_ingest
        if last_ingest is not None and len(last_ingest) == 3:
            flat = last_ingest
        else:
            flat = _flatten_episode_dicts(episodes)
        return transcribe_all_parallel(
            episodes=flat,
            whisper_model_name=settings.whisper_model,
            max_minutes=_clip_minutes(settings),
            max_workers=settings.max_workers,
        )

    return ingest_latest_podcast_episodes, transcribe_intro_snippets


def _apply_auth_env(settings: Settings) -> None:
    os.environ["GROQ_API_KEY"] = settings.groq_api_key
    if settings.gemini_api_key:
        os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key
        os.environ["GEMINI_API_KEY"] = settings.gemini_api_key


def _pick_final_briefing_text(chunks: list[str], min_substantial_chars: int = 400) -> str:
    """Choose assistant Markdown from streamed ADK events.

    The last **non-partial** chunk is usually the final briefing after tool calls. If it looks like a
    short stub (e.g. a preamble), fall back to the **longest** chunk. This is a heuristic; unusual
    provider chunking could still require tuning ``min_substantial_chars``.
    """
    if not chunks:
        return ""
    stripped = [c.strip() for c in chunks if c.strip()]
    if not stripped:
        return ""
    last = stripped[-1]
    if len(last) >= min_substantial_chars:
        return last
    longest = max(stripped, key=len)
    return longest if len(longest) > len(last) else last


async def _run_adk_agent(
    settings: Settings,
    feed_urls: list[str],
    ingest_fn: Callable[..., Any],
    transcribe_fn: Callable[..., Any],
) -> str:
    from google.adk.agents import LlmAgent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import InMemoryRunner
    from google.adk.tools.function_tool import FunctionTool
    from google.adk.utils.context_utils import Aclosing

    if settings.use_groq_only:
        model: Any = LiteLlm(model=f"groq/{settings.groq_model}")
    else:
        model = settings.gemini_model

    agent = LlmAgent(
        name=AGENT_NAME,
        model=model,
        instruction=ADK_SYSTEM_INSTRUCTION,
        tools=[
            FunctionTool(func=ingest_fn),
            FunctionTool(func=transcribe_fn),
        ],
    )

    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id="local",
        state={},
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=build_user_task(feed_urls))],
    )

    text_chunks: list[str] = []
    stream_buf = ""

    async with Aclosing(
        runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=user_message,
        )
    ) as agen:
        async for event in agen:
            if event.author != AGENT_NAME:
                continue
            if not event.content or not event.content.parts:
                continue
            piece = "".join(p.text or "" for p in event.content.parts)
            if not piece:
                continue
            if event.partial:
                stream_buf += piece
            else:
                combined = (stream_buf + piece).strip()
                stream_buf = ""
                if combined:
                    text_chunks.append(combined)

    if stream_buf.strip():
        text_chunks.append(stream_buf.strip())

    await runner.close()

    # Close LiteLLM httpx clients while this loop is still alive. Otherwise Groq/SSL can
    # log "Fatal error on SSL transport" / "Event loop is closed" after asyncio.run exits.
    try:
        from litellm.llms.custom_httpx.async_client_cleanup import (
            close_litellm_async_clients,
        )

        await close_litellm_async_clients()
    except Exception:
        pass

    out = _pick_final_briefing_text(text_chunks)
    if not out:
        raise RuntimeError("ADK finished with no model text; check API keys and logs above.")
    return out


def run_pipeline(settings: Settings, feed_urls: list[str] | None = None) -> str:
    """End-to-end ADK: ``LlmAgent`` + FunctionTools → Markdown saved to ``intelligence_briefing.md``."""
    feeds = feed_urls or DEFAULT_FEEDS
    _apply_auth_env(settings)
    ingest_fn, transcribe_fn = _make_tools(settings)
    briefing = asyncio.run(_run_adk_agent(settings, feeds, ingest_fn, transcribe_fn))
    save_report(settings.output_path, briefing)
    return briefing
