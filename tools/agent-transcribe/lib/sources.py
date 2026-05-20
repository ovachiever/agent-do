"""Source identification, URL parsing, metadata probing."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

from .ytdlp import add_ytdlp_auth_args

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_URL_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})"),
]


def classify_source(raw: str) -> dict:
    """Return {kind, video_id?, url?, path?, canonical}.

    Kinds: youtube, url, file. `canonical` is a stable string for hashing.
    """
    candidate = raw.strip()

    if YOUTUBE_ID_RE.match(candidate):
        return {
            "kind": "youtube",
            "video_id": candidate,
            "url": f"https://www.youtube.com/watch?v={candidate}",
            "canonical": f"youtube:{candidate}",
        }

    for pattern in YOUTUBE_URL_PATTERNS:
        match = pattern.search(candidate)
        if match:
            video_id = match.group(1)
            return {
                "kind": "youtube",
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "canonical": f"youtube:{video_id}",
            }

    if candidate.startswith(("http://", "https://")):
        return {
            "kind": "url",
            "url": candidate,
            "canonical": f"url:{candidate}",
        }

    path = Path(candidate).expanduser()
    return {
        "kind": "file",
        "path": str(path),
        "canonical": f"file:{path.resolve()}" if path.exists() else f"file:{path}",
    }


def source_hash(source: dict) -> str:
    return hashlib.sha256(source["canonical"].encode("utf-8")).hexdigest()[:16]


def probe_metadata(source: dict, cookies_path: Optional[str] = None,
                   extractor_args: Optional[list[str]] = None) -> dict:
    """Use yt-dlp to fetch title, duration, channel, etc. Local files probed via ffprobe.

    Returns: {success, title?, duration_seconds?, channel?, requires_auth?, error?}
    Never raises on download failure — returns success=False.
    """
    if source["kind"] == "file":
        return _probe_file(source["path"])
    return _probe_yt_dlp(source.get("url") or source["canonical"], cookies_path, extractor_args)


def _probe_file(path: str) -> dict:
    if not Path(path).exists():
        return {"success": False, "error": f"file not found: {path}"}
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:format_tags=title,artist",
             "-of", "json", path],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if proc.returncode != 0:
            return {"success": True, "title": Path(path).stem, "duration_seconds": None}
        data = json.loads(proc.stdout or "{}")
        fmt = data.get("format", {})
        tags = fmt.get("tags", {})
        return {
            "success": True,
            "title": tags.get("title") or Path(path).stem,
            "channel": tags.get("artist"),
            "duration_seconds": float(fmt.get("duration", 0)) if fmt.get("duration") else None,
            "requires_auth": False,
        }
    except FileNotFoundError:
        return {"success": False, "error": "ffprobe not installed"}
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return {"success": False, "error": f"probe failed: {exc}"}


def _probe_yt_dlp(url: str, cookies_path: Optional[str],
                  extractor_args: Optional[list[str]]) -> dict:
    cmd = ["yt-dlp", "--no-playlist", "--skip-download", "--print-json",
           "--socket-timeout", "20", "--no-warnings"]
    add_ytdlp_auth_args(cmd, cookies_path, extractor_args)
    cmd.append(url)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
    except FileNotFoundError:
        return {"success": False, "error": "yt-dlp not installed"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "yt-dlp metadata probe timed out"}

    if proc.returncode != 0:
        stderr = proc.stderr or ""
        auth_required = bool(re.search(
            r"(members?-only|join this channel|sign in|login required|private video|"
            r"not a bot|confirm.*bot|requires.*authentication|available to .*members|"
            r"HTTP Error 403|Forbidden)",
            stderr, re.IGNORECASE,
        ))
        return {
            "success": False,
            "error": stderr.strip().splitlines()[-1] if stderr else "yt-dlp failed",
            "requires_auth": auth_required,
        }

    try:
        info = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"success": False, "error": "yt-dlp returned no JSON"}

    return {
        "success": True,
        "title": info.get("title"),
        "duration_seconds": info.get("duration"),
        "channel": info.get("channel") or info.get("uploader"),
        "requires_auth": bool(info.get("availability") in {"subscriber_only", "premium_only", "needs_auth"}),
        "raw": {
            "id": info.get("id"),
            "uploader_id": info.get("uploader_id"),
            "view_count": info.get("view_count"),
            "upload_date": info.get("upload_date"),
        },
    }
