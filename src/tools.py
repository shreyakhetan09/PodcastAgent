from __future__ import annotations

import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

import feedparser
import imageio_ffmpeg
import requests
import whisper

from .models import Episode, EpisodeTranscript


def _extract_audio_url(entry: dict[str, Any]) -> str:
    """Return the first HTTP(S) audio URL from an RSS entry (links or enclosures)."""
    links = entry.get("links", []) or []
    for link in links:
        href = link.get("href", "")
        media_type = (link.get("type", "") or "").lower()
        rel = (link.get("rel", "") or "").lower()
        if href and ("audio" in media_type or rel == "enclosure"):
            return href
    enclosures = entry.get("enclosures", []) or []
    for enclosure in enclosures:
        href = enclosure.get("href", "")
        media_type = (enclosure.get("type", "") or "").lower()
        if href and "audio" in media_type:
            return href
    return ""


def _ensure_ffmpeg_on_path() -> None:
    """Expose the bundled ``imageio-ffmpeg`` binary as ``ffmpeg`` on ``PATH`` for Whisper."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg_link_dir = Path(tempfile.gettempdir()) / "podcast_intel_ffmpeg_bin"
    ffmpeg_link_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_link = ffmpeg_link_dir / "ffmpeg"

    if not ffmpeg_link.exists():
        try:
            ffmpeg_link.symlink_to(ffmpeg_exe)
        except FileExistsError:
            pass

    current_path = os.environ.get("PATH", "")
    if str(ffmpeg_link_dir) not in current_path.split(os.pathsep):
        os.environ["PATH"] = f"{ffmpeg_link_dir}{os.pathsep}{current_path}" if current_path else str(ffmpeg_link_dir)


def _ingest_single_feed(feed_url: str) -> dict[str, Any]:
    """Fetch and parse one RSS URL; return the latest episode as a dict (raises on failure)."""
    parsed = feedparser.parse(feed_url)
    if not parsed.entries:
        raise ValueError(f"No entries found for feed: {feed_url}")

    latest = parsed.entries[0]
    audio_url = _extract_audio_url(latest)
    if not audio_url:
        raise ValueError(f"No audio URL found in latest entry for feed: {feed_url}")

    podcast_name = getattr(parsed.feed, "title", None) or latest.get("title", "Unknown Podcast")
    episode = Episode(
        podcast_name=podcast_name,
        feed_url=feed_url,
        title=latest.get("title", "Unknown Title"),
        author=latest.get("author", "Unknown Author"),
        published=latest.get("published", latest.get("updated", "Unknown Date")),
        audio_url=audio_url,
    )
    return episode.to_dict()


def ingest_latest_episodes(
    feed_urls: list[str],
    max_workers: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Ingestion: exactly three RSS URLs → latest item per feed with audio URL (parallel fetch)."""
    if len(feed_urls) != 3:
        raise ValueError("Exactly 3 feed URLs are required.")

    workers = max_workers if max_workers is not None else len(feed_urls)
    workers = max(1, min(workers, len(feed_urls)))

    by_url: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_url = {pool.submit(_ingest_single_feed, url): url for url in feed_urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            by_url[url] = future.result()

    return [by_url[u] for u in feed_urls]


def _download_audio_prefix(audio_url: str, max_minutes: int) -> str:
    """Stream-download only the first ~``max_minutes`` of audio to a temp file; return its path."""
    max_bytes = max_minutes * 60 * 32_000
    response = requests.get(audio_url, stream=True, timeout=60)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
        bytes_written = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            temp_audio.write(chunk)
            bytes_written += len(chunk)
            if bytes_written >= max_bytes:
                break
        return temp_audio.name


def transcribe_intro_clip(audio_url: str, whisper_model_name: str = "tiny", max_minutes: int = 4) -> str:
    """Transcription: stream only the first ``max_minutes`` (3–5) of audio; Whisper tiny/base."""
    _ensure_ffmpeg_on_path()
    audio_path = _download_audio_prefix(audio_url=audio_url, max_minutes=max_minutes)
    try:
        model = whisper.load_model(whisper_model_name)
        result = model.transcribe(audio_path, fp16=False)
        transcript = (result.get("text", "") or "").strip()
        if not transcript:
            return "No transcript extracted from intro clip."
        return transcript
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


def transcribe_all_parallel(
    episodes: list[dict[str, Any]],
    whisper_model_name: str,
    max_minutes: int,
    max_workers: int = 3,
) -> list[dict[str, Any]]:
    """Run intro transcription for all episodes in parallel (Whisper open-source)."""
    transcripts: list[EpisodeTranscript] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_episode = {
            pool.submit(
                transcribe_intro_clip,
                episode["audio_url"],
                whisper_model_name,
                max_minutes,
            ): episode
            for episode in episodes
        }
        for future in as_completed(future_to_episode):
            episode_dict = future_to_episode[future]
            transcript = future.result()
            episode = Episode(**episode_dict)
            transcripts.append(EpisodeTranscript(episode=episode, transcript=transcript))

    order = {ep["feed_url"]: idx for idx, ep in enumerate(episodes)}
    transcripts.sort(key=lambda x: order.get(x.episode.feed_url, 999))
    return [t.to_dict() for t in transcripts]


def transcripts_to_json(transcript_payload: list[dict[str, Any]]) -> str:
    """Pretty-print transcript payload as ASCII-safe JSON for LLM consumption."""
    return json.dumps(transcript_payload, indent=2, ensure_ascii=True)
