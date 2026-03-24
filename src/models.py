from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Episode:
    """Metadata for one RSS episode (latest item from a feed)."""

    podcast_name: str
    feed_url: str
    title: str
    author: str
    published: str
    audio_url: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return asdict(self)


@dataclass
class EpisodeTranscript:
    """Episode metadata plus Whisper transcript text for the intro clip."""

    episode: Episode
    transcript: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize with nested ``episode`` as a dict."""
        payload = asdict(self)
        payload["episode"] = self.episode.to_dict()
        return payload
