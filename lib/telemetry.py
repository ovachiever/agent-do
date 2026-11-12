"""Local telemetry helpers for agent-do nudges, suggestions, and outcomes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))
PENDING_TTL_SECONDS = int(os.environ.get("AGENT_DO_TELEMETRY_PENDING_TTL", "600"))
PENDING_MAX_ACTIONS = int(os.environ.get("AGENT_DO_TELEMETRY_PENDING_ACTIONS", "5"))


def get_telemetry_dir() -> Path:
    path = AGENT_DO_HOME / "telemetry"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_nudge_log_path() -> Path:
    return get_telemetry_dir() / "nudges.jsonl"


def get_event_log_path() -> Path:
    return get_telemetry_dir() / "events.jsonl"


def get_pending_dir() -> Path:
    path = get_telemetry_dir() / "pending"
    path.mkdir(parents=True, exist_ok=True)
    return path


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def current_git_root(cwd: str | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd or os.getcwd(),
            text=True,
            capture_output=True,
            check=False,
            timeout=2,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def session_id() -> str | None:
    for key in ("CODEX_THREAD_ID", "CLAUDE_SESSION_ID", "AGENT_DO_SESSION_ID", "TMUX_PANE"):
        value = os.environ.get(key)
        if value:
            return value
    return None


def host_name() -> str:
    if os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SANDBOX"):
        return "codex"
    if os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDECODE"):
        return "claude"
    return os.environ.get("AGENT_DO_HOST", "unknown")


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def redact_text(value: str, limit: int = 240) -> str:
    # Redact before truncating, so a secret cut by the limit cannot slip past
    # a pattern that needs its trailing delimiter.
    text = value
    text = re.sub(r"(?i)(api[_-]?key|token|secret|password|passwd|authorization)=\S+", r"\1=<redacted>", text)
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+", r"\1<redacted>", text)
    # Password in a URL's userinfo (postgresql://user:pass@host, https://u:p@h)
    text = re.sub(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+):[^\s@/]+@", r"\1:<redacted>@", text)
    return text[:limit]


def clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def append_event(event_type: str, source: str, **payload: Any) -> dict[str, Any]:
    """Append one structured telemetry event and return it."""
    cwd = payload.pop("cwd", os.getcwd())
    event = {
        "event_id": payload.pop("event_id", f"evt_{uuid.uuid4().hex}"),
        "timestamp": now_iso(),
        "event_type": event_type,
        "source": source,
        "host": host_name(),
        "session_id": session_id(),
        "cwd": cwd,
        "git_root": payload.pop("git_root", current_git_root(cwd)),
    }
    event.update(clean_payload(payload))

    path = get_event_log_path()
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def iter_events() -> list[dict[str, Any]]:
    path = get_event_log_path()
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
    return events


def prompt_fields(prompt: str | None) -> dict[str, str]:
    if not prompt:
        return {}
    return {
        "prompt_hash": stable_hash(prompt),
        "prompt_excerpt": redact_text(prompt, 160),
    }


def hook_name(source: str) -> str:
    if source == "prompt_router":
        return "UserPromptSubmit"
    if source == "pretool":
        return "PreToolUse"
    if source == "session_start":
        return "SessionStart"
    return source


def pending_path(correlation_id: str) -> Path:
    return get_pending_dir() / f"{correlation_id}.json"


def create_pending_nudge(event: dict[str, Any]) -> None:
    tools = list(dict.fromkeys([str(item) for item in event.get("tools", []) if item]))
    if event.get("tool"):
        tools.append(str(event["tool"]))
        tools = list(dict.fromkeys(tools))
    commands = [str(item) for item in event.get("commands", []) if item]
    if event.get("replacement"):
        commands.append(str(event["replacement"]))

    if not tools and not commands:
        return

    pending = {
        "correlation_id": event["correlation_id"],
        "created_at": event["timestamp"],
        "source": event["source"],
        "hook": event.get("hook"),
        "event_type": event.get("event_type"),
        "tools": tools,
        "commands": list(dict.fromkeys(commands)),
        "cwd": event.get("cwd"),
        "git_root": event.get("git_root"),
        "session_id": event.get("session_id"),
        "observed_actions": 0,
        "max_actions": PENDING_MAX_ACTIONS,
    }
    path = pending_path(event["correlation_id"])
    path.write_text(json.dumps(pending, indent=2) + "\n", encoding="utf-8")


def record_nudge_event(event_type: str, source: str, **payload: Any) -> None:
    """Append one nudge-related event to the local telemetry log."""
    correlation_id = payload.pop("correlation_id", f"nudge_{uuid.uuid4().hex}")
    prompt = payload.pop("prompt", None)
    cwd = payload.get("cwd") or os.getcwd()
    event = {
        "timestamp": now_iso(),
        "event_type": event_type,
        "source": source,
        "correlation_id": correlation_id,
    }
    event.update(clean_payload(payload))
    event.update(prompt_fields(prompt))

    path = get_nudge_log_path()
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    structured = append_event(
        "hook_emitted",
        source,
        correlation_id=correlation_id,
        hook=hook_name(source),
        hook_event_type=event_type,
        cwd=cwd,
        tool=event.get("tool"),
        tools=event.get("tools") or [],
        commands=event.get("commands") or [],
        replacement=event.get("replacement"),
        prompt_hash=event.get("prompt_hash"),
        prompt_excerpt=event.get("prompt_excerpt"),
    )
    create_pending_nudge(structured)


def record_hook_decision(
    hook: str,
    source: str,
    decision: str,
    *,
    prompt: str | None = None,
    cwd: str | None = None,
    tools: list[str] | None = None,
    commands: list[str] | None = None,
    reason: str | None = None,
    confidence: float | None = None,
) -> None:
    """Record one hook decision, including silence/suppression."""
    append_event(
        "hook_decision",
        source,
        hook=hook,
        decision=decision,
        cwd=cwd or os.getcwd(),
        tools=tools or [],
        commands=commands or [],
        reason=reason,
        confidence=confidence,
        **prompt_fields(prompt),
    )


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
        "outcomes": summarize_hook_outcomes(),
    }


def recent_nudges(limit: int = 20) -> list[dict[str, Any]]:
    events = iter_nudge_events()
    return events[-limit:]


def clear_nudges() -> None:
    path = get_nudge_log_path()
    if path.exists():
        path.unlink()
    event_path = get_event_log_path()
    if event_path.exists():
        event_path.unlink()
    pending = get_pending_dir()
    for item in pending.glob("*.json"):
        item.unlink()


REDACTED = "<redacted>"


def _positionals(
    args: list[str],
    start: int,
    value_flags: tuple[str, ...] = (),
    bool_flags: tuple[str, ...] = (),
) -> list[int]:
    """Indexes of positional arguments from ``start``.

    Only the flags each tool actually parses are skipped, so a secret that
    happens to start with "-" is still treated as the positional it is.
    """
    positions: list[int] = []
    i = start
    while i < len(args):
        arg = args[i]
        if arg in value_flags:
            i += 2
            continue
        if arg not in bool_flags:
            positions.append(i)
        i += 1
    return positions


def _flag_values(args: list[str], flags: tuple[str, ...]) -> set[int]:
    """Indexes of the values that follow any of ``flags``."""
    return {i + 1 for i, arg in enumerate(args[:-1]) if arg in flags}


def _secret_value_indexes(tool: str, args: list[str]) -> set[int]:
    """Argument positions that carry a secret value for verbs known to take one.

    Mirrors each tool's own argument parsing:
      render   env-set <svc> <KEY> <VALUE>
      render   env-group set <eg> <KEY> <VALUE>
      creds    store <KEY> [VALUE] [--stdin]
      psql     connect <conn_string> | --profile <name>
      psql     profile add <name> <conn_string>
      vercel   env-set <project> <KEY> <VALUE> [--target t]
      supabase secret-set <ref> <KEY> <VALUE>
      supabase create ... --db-pass|--password <p>
      gcp      secret-set <project> <name> <value>
    """
    sub = args[0] if args else ""
    sub2 = args[1] if len(args) > 1 else ""
    if tool == "render" and sub == "env-set":
        return set(range(3, len(args)))
    if tool == "render" and sub == "env-group" and sub2 == "set":
        return set(range(4, len(args)))
    if tool == "creds" and sub == "store":
        return set(_positionals(args, 1, bool_flags=("--stdin",))[1:])
    if tool == "psql" and sub == "connect":
        return set(_positionals(args, 1, ("--profile", "-p"), ("--help", "-h")))
    if tool == "psql" and sub == "profile" and sub2 == "add":
        return set(range(3, len(args)))
    if tool == "vercel" and sub == "env-set":
        return set(_positionals(args, 1, ("--target",))[2:])
    if tool in ("supabase", "gcp") and sub == "secret-set":
        return set(range(3, len(args)))
    if tool == "supabase" and sub == "create":
        return _flag_values(args, ("--db-pass", "--password"))
    return set()


def redact_tool_args(tool: str, args: list[str]) -> list[str]:
    """Redact tool-specific sensitive argument payloads before telemetry.

    Secret values (env var values, stored credentials, connection strings) must
    never reach events.jsonl: they would sit in plain text in a local log that
    every later `nudges`/`harness` read can surface.
    """
    out = list(args)
    for i in _secret_value_indexes(tool, args):
        out[i] = REDACTED
    if tool == "render":
        # --env KEY=VALUE (render create, env-group create, project create):
        # keep the key name, drop the value.
        for i, arg in enumerate(args[:-1]):
            if arg == "--env":
                key, sep, _ = args[i + 1].partition("=")
                out[i + 1] = f"{key}={REDACTED}" if sep else REDACTED
    args = out

    if tool != "appleevents":
        return list(args)

    redacted: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        redacted.append(arg)
        if arg == "--script" and i + 1 < len(args):
            redacted.append(f"<script:{stable_hash(args[i + 1])}>")
            i += 2
            continue
        i += 1
    return redacted


def command_preview(tool: str, args: list[str]) -> str:
    parts = ["agent-do", tool, *redact_tool_args(tool, args)]
    return redact_text(" ".join(parts), 320)


def args_shape(args: list[str], *, tool: str | None = None) -> list[str]:
    safe_args = redact_tool_args(tool, args) if tool else args
    shape = []
    for arg in safe_args[:12]:
        if arg.startswith("-"):
            shape.append(arg)
        elif "/" in arg or len(arg) > 32:
            shape.append("<arg>")
        else:
            shape.append(redact_text(arg, 48))
    if len(safe_args) > 12:
        shape.append("...")
    return shape


def load_pending() -> list[dict[str, Any]]:
    pending = []
    for path in get_pending_dir().glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload["_path"] = str(path)
            pending.append(payload)
    return pending


def same_context(pending: dict[str, Any], event: dict[str, Any]) -> bool:
    if pending.get("session_id") and event.get("session_id") and pending["session_id"] == event["session_id"]:
        return True
    if pending.get("git_root") and event.get("git_root") and pending["git_root"] == event["git_root"]:
        return True
    if pending.get("cwd") and event.get("cwd") and pending["cwd"] == event["cwd"]:
        return True
    return not pending.get("session_id") and not pending.get("git_root")


def pending_expired(pending: dict[str, Any], now: datetime) -> bool:
    created = parse_iso(str(pending.get("created_at") or ""))
    if not created:
        return False
    return now - created > timedelta(seconds=PENDING_TTL_SECONDS)


def pending_matches_tool(pending: dict[str, Any], tool: str, args: list[str]) -> bool:
    if tool in set(pending.get("tools") or []):
        return True
    command = command_preview(tool, args)
    for suggested in pending.get("commands") or []:
        if suggested.startswith(f"agent-do {tool}") or command.startswith(str(suggested).rstrip()):
            return True
    return False


def delete_pending(pending: dict[str, Any]) -> None:
    path = pending.get("_path")
    if not path:
        return
    try:
        Path(path).unlink()
    except OSError:
        pass


def update_pending(pending: dict[str, Any]) -> None:
    path = pending.get("_path")
    if not path:
        return
    payload = {key: value for key, value in pending.items() if key != "_path"}
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def resolve_pending_for_tool_call(call_event: dict[str, Any], tool: str, args: list[str]) -> None:
    now = datetime.now(timezone.utc)
    for pending in load_pending():
        if not same_context(pending, call_event):
            continue
        correlation_id = pending.get("correlation_id")
        if pending_expired(pending, now):
            append_event(
                "hook_expired",
                "telemetry",
                correlation_id=correlation_id,
                hook=pending.get("hook"),
                suggested_tools=pending.get("tools") or [],
                observed_tool=tool,
                reason="ttl_expired",
            )
            delete_pending(pending)
            continue
        if pending_matches_tool(pending, tool, args):
            append_event(
                "hook_followed",
                "telemetry",
                correlation_id=correlation_id,
                hook=pending.get("hook"),
                suggested_tools=pending.get("tools") or [],
                observed_tool=tool,
                invocation_id=call_event.get("invocation_id"),
            )
            delete_pending(pending)
            continue
        pending["observed_actions"] = int(pending.get("observed_actions") or 0) + 1
        if pending["observed_actions"] >= int(pending.get("max_actions") or PENDING_MAX_ACTIONS):
            append_event(
                "hook_ignored",
                "telemetry",
                correlation_id=correlation_id,
                hook=pending.get("hook"),
                suggested_tools=pending.get("tools") or [],
                observed_tool=tool,
                reason="max_unrelated_actions",
            )
            delete_pending(pending)
        else:
            update_pending(pending)


def record_tool_call(tool: str, args: list[str], *, cwd: str | None = None) -> str:
    """Record a structured agent-do tool invocation and resolve pending nudges."""
    invocation_id = f"call_{uuid.uuid4().hex}"
    event = append_event(
        "agent_tool_call",
        "agent-do",
        invocation_id=invocation_id,
        tool=tool,
        args_shape=args_shape(args, tool=tool),
        command_preview=command_preview(tool, args),
        cwd=cwd or os.getcwd(),
    )
    resolve_pending_for_tool_call(event, tool, args)
    return invocation_id


def record_tool_result(invocation_id: str, exit_code: int) -> None:
    if not invocation_id:
        return
    append_event(
        "agent_tool_result",
        "agent-do",
        invocation_id=invocation_id,
        exit_code=exit_code,
        success=exit_code == 0,
    )


def summarize_hook_outcomes(events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    event_list = events if events is not None else iter_events()
    by_type = Counter(str(event.get("event_type") or "unknown") for event in event_list)
    by_hook = Counter(str(event.get("hook") or "unknown") for event in event_list if event.get("hook"))
    by_tool = Counter()
    for event in event_list:
        if event.get("tool"):
            by_tool[str(event["tool"])] += 1
        for tool in event.get("tools", []) or []:
            by_tool[str(tool)] += 1
        for tool in event.get("suggested_tools", []) or []:
            by_tool[str(tool)] += 1

    followed = by_type.get("hook_followed", 0)
    ignored = by_type.get("hook_ignored", 0)
    expired = by_type.get("hook_expired", 0)
    resolved = followed + ignored + expired
    pending = len(load_pending())

    return {
        "events": len(event_list),
        "decisions": by_type.get("hook_decision", 0),
        "emitted": by_type.get("hook_emitted", 0),
        "followed": followed,
        "ignored": ignored,
        "expired": expired,
        "pending": pending,
        "resolved": resolved,
        "follow_through_rate": (followed / resolved) if resolved else None,
        "by_type": dict(by_type.most_common()),
        "by_hook": dict(by_hook.most_common()),
        "by_tool": dict(by_tool.most_common()),
    }
