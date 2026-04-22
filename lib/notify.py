"""Shared notify subsystem for agent-do root notifications."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))
NOTIFY_DIR = AGENT_DO_HOME / "notify"
RECIPIENTS_PATH = NOTIFY_DIR / "recipients.json"

DEFAULT_CONFIG = {
    "defaults": {
        "via": ["sms"],
        "subject": "agent-do notification",
    },
    "recipients": {},
}

PROVIDERS: dict[str, dict[str, str]] = {
    "sms": {
        "mode": "tool",
        "summary": "SMS delivery via Messages.app, Twilio, or AWS SNS",
    },
    "email": {
        "mode": "tool",
        "summary": "Email delivery via SMTP or Mail.app",
    },
    "slack": {
        "mode": "tool",
        "summary": "Slack message delivery via bot token or webhook",
    },
    "pipe": {
        "mode": "pipe",
        "summary": "Local shell command with message piped on stdin",
    },
}


def ensure_notify_dir() -> None:
    NOTIFY_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    if not RECIPIENTS_PATH.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))

    data = json.loads(RECIPIENTS_PATH.read_text())
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    merged["defaults"].update(data.get("defaults", {}))
    merged["recipients"].update(data.get("recipients", {}))
    return merged


def save_config(config: dict[str, Any]) -> None:
    ensure_notify_dir()
    RECIPIENTS_PATH.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")


def normalize_provider(provider: str) -> str:
    return provider.strip().lower().replace("-", "_")


def parse_provider_list(value: str | None) -> list[str]:
    if not value:
        return []
    providers: list[str] = []
    for item in value.split(","):
        provider = normalize_provider(item)
        if provider:
            providers.append(provider)
    return providers


def list_recipients(config: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for alias, data in sorted(config.get("recipients", {}).items()):
        items.append(
            {
                "alias": alias,
                "providers": sorted([key for key in data.keys() if key in PROVIDERS]),
                "prefer": data.get("prefer", []),
                "subject": data.get("subject"),
            }
        )
    return items


def get_recipient(config: dict[str, Any], alias: str) -> dict[str, Any] | None:
    recipient = config.get("recipients", {}).get(alias)
    if recipient is None:
        return None
    return dict(recipient)


def update_recipient(
    config: dict[str, Any],
    alias: str,
    *,
    sms: str | None = None,
    email: str | None = None,
    slack: str | None = None,
    pipe: str | None = None,
    prefer: list[str] | None = None,
    subject: str | None = None,
) -> dict[str, Any]:
    recipients = config.setdefault("recipients", {})
    recipient = dict(recipients.get(alias, {}))

    if sms is not None:
        recipient["sms"] = sms
    if email is not None:
        recipient["email"] = email
    if slack is not None:
        recipient["slack"] = slack
    if pipe is not None:
        recipient["pipe"] = pipe
    if prefer is not None:
        recipient["prefer"] = prefer
    if subject is not None:
        recipient["subject"] = subject

    recipients[alias] = recipient
    return recipient


def resolve_attempts(
    config: dict[str, Any],
    recipient_name: str,
    *,
    via: list[str] | None = None,
) -> list[dict[str, str]]:
    recipient = get_recipient(config, recipient_name)

    if recipient is not None:
        available = {provider: recipient[provider] for provider in PROVIDERS if recipient.get(provider)}
        order = via or recipient.get("prefer") or config.get("defaults", {}).get("via", [])
        if not order:
            order = list(available.keys())
        attempts = []
        for provider in order:
            provider = normalize_provider(provider)
            if provider not in PROVIDERS:
                continue
            target = available.get(provider)
            if target:
                attempts.append({"provider": provider, "target": target, "recipient": recipient_name})
        return attempts

    order = via or config.get("defaults", {}).get("via", [])
    if not order:
        raise ValueError(
            f"Recipient '{recipient_name}' is not configured. "
            "Use agent-do notify set-recipient <alias> ... or pass --via <provider>."
        )

    return [
        {
            "provider": normalize_provider(provider),
            "target": recipient_name,
            "recipient": recipient_name,
        }
        for provider in order
        if normalize_provider(provider) in PROVIDERS
    ]


def _agent_do_path() -> str:
    override = os.environ.get("AGENT_DO_NOTIFY_AGENT_DO")
    if override:
        return override
    return str(Path(__file__).resolve().parents[1] / "agent-do")


def execute_provider(
    provider: str,
    *,
    target: str,
    message: str,
    subject: str,
    recipient_name: str,
) -> dict[str, Any]:
    provider = normalize_provider(provider)
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown notify provider: {provider}")

    if PROVIDERS[provider]["mode"] == "pipe":
        env = dict(os.environ)
        env["AGENT_DO_NOTIFY_PROVIDER"] = provider
        env["AGENT_DO_NOTIFY_RECIPIENT"] = recipient_name
        env["AGENT_DO_NOTIFY_SUBJECT"] = subject
        completed = subprocess.run(
            target,
            shell=True,
            text=True,
            input=message,
            capture_output=True,
            check=False,
            env=env,
        )
        return {
            "provider": provider,
            "target": target,
            "command": target,
            "exit_code": completed.returncode,
            "success": completed.returncode == 0,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }

    agent_do = _agent_do_path()
    if provider == "sms":
        command = [agent_do, "sms", "send", target, message]
    elif provider == "email":
        command = [agent_do, "email", "send", target, subject, "--body", message]
    elif provider == "slack":
        command = [agent_do, "slack", "send", target, message]
    else:
        raise ValueError(f"Unsupported notify provider: {provider}")

    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "provider": provider,
        "target": target,
        "command": command,
        "exit_code": completed.returncode,
        "success": completed.returncode == 0,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def send_notification(
    config: dict[str, Any],
    recipient_name: str,
    message: str,
    *,
    via: list[str] | None = None,
    subject: str | None = None,
    send_all: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    attempts = resolve_attempts(config, recipient_name, via=via)
    recipient = get_recipient(config, recipient_name) or {}
    subject = subject or recipient.get("subject") or config.get("defaults", {}).get("subject", "agent-do notification")

    results = []
    overall_success = False
    for attempt in attempts:
        planned = {
            "provider": attempt["provider"],
            "target": attempt["target"],
            "recipient": recipient_name,
            "subject": subject,
        }
        if dry_run:
            planned["planned"] = True
            results.append(planned)
            continue

        result = execute_provider(
            attempt["provider"],
            target=attempt["target"],
            message=message,
            subject=subject,
            recipient_name=recipient_name,
        )
        result["recipient"] = recipient_name
        result["subject"] = subject
        results.append(result)

        if result["success"]:
            overall_success = True
            if not send_all:
                break

    if dry_run:
        overall_success = True

    return {
        "success": overall_success,
        "recipient": recipient_name,
        "subject": subject,
        "message": message,
        "send_all": send_all,
        "dry_run": dry_run,
        "attempts": results,
    }


def providers_payload() -> list[dict[str, str]]:
    items = []
    for name, info in sorted(PROVIDERS.items()):
        items.append(
            {
                "provider": name,
                "mode": info["mode"],
                "summary": info["summary"],
            }
        )
    return items


def render_text_result(payload: dict[str, Any]) -> str:
    lines = []
    if payload.get("dry_run"):
        lines.append(f"Planned notification for {payload['recipient']}:")
    else:
        lines.append(f"Notification for {payload['recipient']}:")

    for attempt in payload.get("attempts", []):
        status = "planned" if payload.get("dry_run") else ("sent" if attempt.get("success") else "failed")
        lines.append(f"  - {attempt['provider']} -> {attempt['target']} [{status}]")
        stdout = attempt.get("stdout")
        stderr = attempt.get("stderr")
        if stdout:
            lines.append(f"    stdout: {stdout}")
        if stderr:
            lines.append(f"    stderr: {stderr}")

    if not payload.get("attempts"):
        lines.append("  - no matching providers")

    return "\n".join(lines)


def shell_join(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def main_json(data: Any) -> None:
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")
