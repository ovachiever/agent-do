from __future__ import annotations

import re
from typing import Any


MODIFIER_RE = re.compile(r"^\+live(?:\((?P<body>.*)\))?$")
ALLOWED_KEYS = {"scope", "app", "ttl", "reason"}
ALLOWED_SCOPES = {"browser", "desktop", "ios", "android", "any"}


def split_pairs(body: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None

    for char in body:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue

        if char in ("'", '"'):
            quote = char
            current.append(char)
            continue

        if char == ",":
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue

        current.append(char)

    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_duration(value: str) -> int:
    raw = value.strip().lower()
    match = re.fullmatch(r"(\d+)([smhd]?)", raw)
    if not match:
        raise ValueError(f"Invalid live ttl '{value}'")

    amount = int(match.group(1))
    unit = match.group(2) or "s"
    multiplier = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }[unit]
    return amount * multiplier


def quote_if_needed(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9._:/-]+", value):
        return value
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'


def format_duration(seconds: int) -> str:
    if seconds % 86400 == 0 and seconds >= 86400:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0 and seconds >= 3600:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0 and seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def parse_live_modifier(raw: str) -> dict[str, Any]:
    match = MODIFIER_RE.fullmatch(raw.strip())
    if not match:
        raise ValueError(f"Invalid runtime modifier '{raw}'")

    payload: dict[str, Any] = {
        "enabled": True,
        "raw": raw.strip(),
        "scope": None,
        "app": None,
        "ttl_seconds": None,
        "reason": None,
    }
    body = (match.group("body") or "").strip()
    if not body:
        return payload

    for part in split_pairs(body):
        if "=" not in part:
            raise ValueError(f"Invalid live modifier segment '{part}'")
        key, value = part.split("=", 1)
        key = key.strip()
        if key not in ALLOWED_KEYS:
            raise ValueError(f"Unsupported live modifier option '{key}'")
        value = strip_quotes(value)
        if key == "scope":
            scope = value.strip().lower()
            if scope not in ALLOWED_SCOPES:
                raise ValueError(f"Unsupported live scope '{value}'")
            payload["scope"] = scope
        elif key == "app":
            payload["app"] = value.strip() or None
        elif key == "ttl":
            payload["ttl_seconds"] = parse_duration(value)
        elif key == "reason":
            payload["reason"] = value.strip() or None
    return payload


def build_live_modifier(
    *,
    scope: str | None = None,
    app: str | None = None,
    ttl_seconds: int | None = None,
    reason: str | None = None,
) -> str:
    parts: list[str] = []
    if scope:
        parts.append(f"scope={scope}")
    if app:
        parts.append(f"app={quote_if_needed(app)}")
    if ttl_seconds:
        parts.append(f"ttl={format_duration(ttl_seconds)}")
    if reason:
        parts.append(f"reason={quote_if_needed(reason)}")
    if not parts:
        return "+live"
    return f"+live({','.join(parts)})"
