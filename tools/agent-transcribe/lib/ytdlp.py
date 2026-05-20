"""yt-dlp argument helpers for agent-transcribe.

These helpers keep downloader-specific flags consistent across metadata probes,
subtitle downloads, and audio extraction.
"""

from __future__ import annotations

import re
from typing import Optional

PLAYER_CLIENT_RE = re.compile(r"^[A-Za-z0-9_,.+:-]+$")


def normalize_extractor_args(
    extractor_args: Optional[list[str]] = None,
    youtube_player_client: Optional[str] = None,
) -> list[str]:
    """Return safe yt-dlp --extractor-args values.

    Values are passed as argv elements, never through a shell. Newlines and
    leading dashes are rejected so an agent cannot smuggle additional flags
    through this narrow passthrough.
    """
    normalized: list[str] = []
    for spec in extractor_args or []:
        value = str(spec).strip()
        if not value:
            continue
        if "\n" in value or "\r" in value or "\x00" in value:
            raise ValueError("--extractor-args cannot contain control characters")
        if value.startswith("-"):
            raise ValueError("--extractor-args must be a yt-dlp extractor spec, not another flag")
        normalized.append(value)

    if youtube_player_client:
        client = str(youtube_player_client).strip()
        if not PLAYER_CLIENT_RE.fullmatch(client):
            raise ValueError("--youtube-player-client contains unsupported characters")
        normalized.append(f"youtube:player_client={client}")

    return normalized


def add_ytdlp_auth_args(
    cmd: list[str],
    cookies_path: Optional[str] = None,
    extractor_args: Optional[list[str]] = None,
) -> None:
    """Append auth/extractor arguments to an existing yt-dlp command."""
    if cookies_path:
        cmd.extend(["--cookies", cookies_path])
    for spec in extractor_args or []:
        cmd.extend(["--extractor-args", spec])
