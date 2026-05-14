"""Snapshot envelope and time helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_github_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def envelope(command: str, *, ref: str | None = None, data: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "tool": "gh",
        "command": command,
        "timestamp": now_iso(),
        "data": data,
    }
    if ref is not None:
        result["ref"] = ref
    return result
