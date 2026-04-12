"""Local telemetry helpers for agent-do nudges and suggestions."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))


def get_telemetry_dir() -> Path:
    path = AGENT_DO_HOME / "telemetry"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_nudge_log_path() -> Path:
    return get_telemetry_dir() / "nudges.jsonl"


def record_nudge_event(event_type: str, source: str, **payload: Any) -> None:
    """Append one nudge-related event to the local telemetry log."""
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "source": source,
    }
    event.update({key: value for key, value in payload.items() if value not in (None, "", [], {})})

    path = get_nudge_log_path()
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def iter_nudge_events() -> list[dict[str, Any]]:
    path = get_nudge_log_path()
    if not path.exists():
        return []

    events: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def summarize_nudges() -> dict[str, Any]:
    events = iter_nudge_events()
    by_source = Counter()
    by_type = Counter()
    by_tool = Counter()

    for event in events:
        by_source[event.get("source", "unknown")] += 1
        by_type[event.get("event_type", "unknown")] += 1
        if event.get("tool"):
            by_tool[event["tool"]] += 1
        for tool in event.get("tools", []):
            by_tool[tool] += 1

    return {
        "total_events": len(events),
        "sources": dict(by_source.most_common()),
        "event_types": dict(by_type.most_common()),
        "tools": dict(by_tool.most_common()),
        "last_event": events[-1] if events else None,
    }


def recent_nudges(limit: int = 20) -> list[dict[str, Any]]:
    events = iter_nudge_events()
    return events[-limit:]


def clear_nudges() -> None:
    path = get_nudge_log_path()
    if path.exists():
        path.unlink()
