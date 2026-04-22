"""Shared notify subsystem for agent-do root notifications."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

from live.errors import LiveApprovalRequiredError
from live.policy import require_live_control


AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))
NOTIFY_DIR = AGENT_DO_HOME / "notify"
RECIPIENTS_PATH = NOTIFY_DIR / "recipients.json"
RULES_PATH = NOTIFY_DIR / "rules.json"
STATE_PATH = NOTIFY_DIR / "state.json"

DEFAULT_CONFIG = {
    "defaults": {
        "via": ["sms"],
        "subject": "agent-do notification",
    },
    "recipients": {},
}

DEFAULT_RULES = {
    "rules": {},
}

DEFAULT_STATE = {
    "deliveries": {},
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
    "messenger": {
        "mode": "live",
        "summary": "Meta Messenger delivery through explicit +live desktop control",
    },
    "pipe": {
        "mode": "pipe",
        "summary": "Local shell command with message piped on stdin",
    },
}

TEMPLATES: dict[str, dict[str, Any]] = {
    "approval_needed": {
        "summary": "Human approval is required for a named action or resource",
        "event": "approval",
        "message": "Approval needed for {item}",
        "subject": "Approval needed: {item}",
        "via": ["messenger", "sms"],
        "match": {"status": "needed"},
        "fingerprint": "{item}:{status}",
        "cooldown_seconds": 900,
        "required_facts": ["item", "status"],
    },
    "build_failed": {
        "summary": "Build failed for a service or branch",
        "event": "build",
        "message": "Build failed for {service} on {branch}",
        "subject": "Build failed: {service}",
        "via": ["sms", "email"],
        "match": {"status": "failed"},
        "fingerprint": "{service}:{branch}:{status}",
        "cooldown_seconds": 1800,
        "required_facts": ["service", "branch", "status"],
    },
    "deploy_done": {
        "summary": "Deployment completed successfully",
        "event": "deploy",
        "message": "Deploy finished for {service} in {environment}",
        "subject": "Deploy finished: {service}",
        "via": ["slack", "sms"],
        "match": {"status": "succeeded"},
        "fingerprint": "{service}:{environment}:{status}",
        "cooldown_seconds": 900,
        "required_facts": ["service", "environment", "status"],
    },
    "deploy_failed": {
        "summary": "Deployment failed",
        "event": "deploy",
        "message": "Deploy failed for {service} in {environment}",
        "subject": "Deploy failed: {service}",
        "via": ["messenger", "sms", "email"],
        "match": {"status": "failed"},
        "fingerprint": "{service}:{environment}:{status}",
        "cooldown_seconds": 1800,
        "required_facts": ["service", "environment", "status"],
    },
    "job_stalled": {
        "summary": "Long-running job appears stuck or stalled",
        "event": "job",
        "message": "Job stalled: {job}",
        "subject": "Job stalled: {job}",
        "via": ["slack", "sms"],
        "match": {"status": "stalled"},
        "fingerprint": "{job}:{status}",
        "cooldown_seconds": 1800,
        "required_facts": ["job", "status"],
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


def load_rules() -> dict[str, Any]:
    if not RULES_PATH.exists():
        return json.loads(json.dumps(DEFAULT_RULES))
    data = json.loads(RULES_PATH.read_text())
    merged = json.loads(json.dumps(DEFAULT_RULES))
    merged["rules"].update(data.get("rules", {}))
    return merged


def save_config(config: dict[str, Any]) -> None:
    ensure_notify_dir()
    RECIPIENTS_PATH.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")


def save_rules(rules: dict[str, Any]) -> None:
    ensure_notify_dir()
    RULES_PATH.write_text(json.dumps(rules, indent=2, sort_keys=True) + "\n")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return json.loads(json.dumps(DEFAULT_STATE))
    data = json.loads(STATE_PATH.read_text())
    merged = json.loads(json.dumps(DEFAULT_STATE))
    merged["deliveries"].update(data.get("deliveries", {}))
    return merged


def save_state(state: dict[str, Any]) -> None:
    ensure_notify_dir()
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def delete_rule(rules_config: dict[str, Any], name: str) -> dict[str, Any] | None:
    rules = rules_config.setdefault("rules", {})
    removed = rules.pop(name, None)
    if removed is None:
        return None
    return dict(removed)


def reset_state(state: dict[str, Any], *, rule_name: str | None = None) -> dict[str, Any]:
    deliveries = state.setdefault("deliveries", {})
    if rule_name is None:
        cleared_rules = sorted(deliveries.keys())
        cleared_count = sum(len(items) for items in deliveries.values())
        state["deliveries"] = {}
        return {
            "scope": "all",
            "cleared_rules": cleared_rules,
            "cleared_count": cleared_count,
        }

    existing = deliveries.pop(rule_name, {})
    return {
        "scope": "rule",
        "rule": rule_name,
        "cleared_count": len(existing),
    }


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


def parse_key_value_pairs(values: list[str] | None) -> dict[str, str]:
    items: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"Expected key=value, got: {value}")
        key, item = value.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Expected non-empty key in pair: {value}")
        items[key] = item
    return items


def parse_duration_seconds(value: str | None) -> int:
    if value is None:
        return 0
    raw = value.strip().lower()
    if not raw:
        return 0
    suffix_map = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }
    suffix = raw[-1]
    if suffix.isdigit():
        return int(raw)
    if suffix not in suffix_map:
        raise ValueError(f"Unsupported duration suffix in: {value}")
    return int(raw[:-1]) * suffix_map[suffix]


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
    messenger: str | None = None,
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
    if messenger is not None:
        recipient["messenger"] = messenger
    if pipe is not None:
        recipient["pipe"] = pipe
    if prefer is not None:
        recipient["prefer"] = prefer
    if subject is not None:
        recipient["subject"] = subject

    recipients[alias] = recipient
    return recipient


def list_rules(rules_config: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for name, data in sorted(rules_config.get("rules", {}).items()):
        items.append(
            {
                "name": name,
                "event": data.get("event"),
                "recipient": data.get("recipient"),
                "via": data.get("via", []),
                "match": data.get("match", {}),
                "cooldown_seconds": int(data.get("cooldown_seconds", 0) or 0),
            }
        )
    return items


def list_templates() -> list[dict[str, Any]]:
    items = []
    for name, data in sorted(TEMPLATES.items()):
        items.append(
            {
                "name": name,
                "summary": data.get("summary"),
                "event": data.get("event"),
                "via": list(data.get("via", [])),
                "match": dict(data.get("match", {})),
                "cooldown_seconds": int(data.get("cooldown_seconds", 0) or 0),
                "required_facts": list(data.get("required_facts", [])),
            }
        )
    return items


def get_template(name: str) -> dict[str, Any] | None:
    template = TEMPLATES.get(name)
    if template is None:
        return None
    return dict(template)


def get_rule(rules_config: dict[str, Any], name: str) -> dict[str, Any] | None:
    rule = rules_config.get("rules", {}).get(name)
    if rule is None:
        return None
    return dict(rule)


def update_rule(
    rules_config: dict[str, Any],
    name: str,
    *,
    recipient: str,
    event: str,
    message: str,
    via: list[str] | None = None,
    subject: str | None = None,
    match: dict[str, str] | None = None,
    fingerprint: str | None = None,
    cooldown_seconds: int | None = None,
) -> dict[str, Any]:
    rules = rules_config.setdefault("rules", {})
    rule = dict(rules.get(name, {}))
    rule["recipient"] = recipient
    rule["event"] = event
    rule["message"] = message
    if via is not None:
        rule["via"] = via
    if subject is not None:
        rule["subject"] = subject
    if match is not None:
        rule["match"] = match
    if fingerprint is not None:
        rule["fingerprint"] = fingerprint
    if cooldown_seconds is not None:
        rule["cooldown_seconds"] = max(0, int(cooldown_seconds))
    rules[name] = rule
    return rule


def apply_template(
    rules_config: dict[str, Any],
    template_name: str,
    *,
    rule_name: str,
    recipient: str,
    via: list[str] | None = None,
    subject: str | None = None,
    match: dict[str, str] | None = None,
    cooldown_seconds: int | None = None,
) -> dict[str, Any]:
    template = get_template(template_name)
    if template is None:
        raise ValueError(f"Unknown notify template: {template_name}")

    merged_match = dict(template.get("match", {}))
    if match:
        merged_match.update(match)

    return update_rule(
        rules_config,
        rule_name,
        recipient=recipient,
        event=str(template["event"]),
        message=str(template["message"]),
        via=via if via is not None else list(template.get("via", [])),
        subject=subject if subject is not None else template.get("subject"),
        match=merged_match,
        fingerprint=template.get("fingerprint"),
        cooldown_seconds=cooldown_seconds if cooldown_seconds is not None else int(template.get("cooldown_seconds", 0) or 0),
    )


class NotifyFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        raise ValueError(f"Missing fact for template field: {key}")


def render_template(template: str, facts: dict[str, str]) -> str:
    return template.format_map(NotifyFormatDict(facts))


def rule_matches(rule: dict[str, Any], event: str, facts: dict[str, str]) -> bool:
    if rule.get("event") != event:
        return False
    for key, expected in (rule.get("match") or {}).items():
        if facts.get(key) != expected:
            return False
    return True


def build_rule_fingerprint(rule_name: str, rule: dict[str, Any], facts: dict[str, str]) -> str:
    template = rule.get("fingerprint")
    if template:
        raw = render_template(str(template), facts)
    else:
        raw = json.dumps({"rule": rule_name, "facts": facts}, sort_keys=True)
    digest = sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{rule_name}:{digest}"


def should_send_rule(
    state: dict[str, Any],
    rule_name: str,
    fingerprint: str,
    cooldown_seconds: int,
    now: float,
) -> tuple[bool, dict[str, Any] | None]:
    if cooldown_seconds <= 0:
        return True, None
    deliveries = state.setdefault("deliveries", {}).setdefault(rule_name, {})
    last_sent = deliveries.get(fingerprint)
    if last_sent is None:
        return True, None
    elapsed = max(0, int(now - float(last_sent)))
    remaining = max(0, cooldown_seconds - elapsed)
    if remaining <= 0:
        return True, None
    return False, {
        "rule": rule_name,
        "fingerprint": fingerprint,
        "cooldown_seconds": cooldown_seconds,
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "skipped": "cooldown",
    }


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


def _run_agent_do(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_agent_do_path(), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _normalize_messenger_target(target: str) -> str:
    if target.startswith(("http://", "https://", "messenger://")):
        return target
    return f"https://www.messenger.com/t/{target}"


def _send_messenger(
    *,
    target: str,
    message: str,
    subject: str,
    recipient_name: str,
) -> dict[str, Any]:
    reason = "notify:messenger"
    approval = require_live_control(
        scope="desktop",
        tool="notify",
        argv=["send", recipient_name, message, "--via", "messenger"],
        app="Messenger",
        reason=reason,
    )

    if os.environ.get("AGENT_DO_NOTIFY_MESSENGER_TEST_MODE", "").strip():
        return {
            "provider": "messenger",
            "target": target,
            "command": ["messenger-test-mode"],
            "exit_code": 0,
            "success": True,
            "stdout": "messenger sent",
            "stderr": "",
            "approval": approval,
        }

    if os.uname().sysname != "Darwin":
        return {
            "provider": "messenger",
            "target": target,
            "command": [],
            "exit_code": 1,
            "success": False,
            "stdout": "",
            "stderr": "Messenger notify is currently implemented for macOS live control only",
            "approval": approval,
        }

    app_name = os.environ.get("AGENT_DO_NOTIFY_MESSENGER_APP", "Messenger").strip() or "Messenger"
    target_url = _normalize_messenger_target(target)

    launch = subprocess.run(
        ["open", "-a", app_name, target_url],
        text=True,
        capture_output=True,
        check=False,
    )
    if launch.returncode != 0:
        launch = subprocess.run(
            ["open", target_url],
            text=True,
            capture_output=True,
            check=False,
        )
    time.sleep(1.0)

    focus = _run_agent_do("macos", "focus", app_name)
    time.sleep(0.5)

    clicked_text = None
    for candidate in ["Message", "Aa", "Type a message", "Write a message", "Reply", "Send message"]:
        click = _run_agent_do("screen", "click", "--text", candidate)
        if click.returncode == 0:
            clicked_text = candidate
            time.sleep(0.2)
            break

    typed = _run_agent_do("screen", "type", message)
    if typed.returncode != 0:
        return {
            "provider": "messenger",
            "target": target,
            "command": ["screen", "type", message],
            "exit_code": typed.returncode,
            "success": False,
            "stdout": typed.stdout.strip(),
            "stderr": typed.stderr.strip() or "Failed to type message into Messenger",
            "approval": approval,
            "clicked_text": clicked_text,
        }

    pressed = _run_agent_do("screen", "press", "Enter")
    return {
        "provider": "messenger",
        "target": target,
        "command": ["open", "-a", app_name, target_url],
        "exit_code": pressed.returncode,
        "success": pressed.returncode == 0,
        "stdout": "\n".join(
            [item for item in [launch.stdout.strip(), focus.stdout.strip(), typed.stdout.strip(), pressed.stdout.strip()] if item]
        ),
        "stderr": "\n".join(
            [item for item in [launch.stderr.strip(), focus.stderr.strip(), typed.stderr.strip(), pressed.stderr.strip()] if item]
        ),
        "approval": approval,
        "clicked_text": clicked_text,
        "subject": subject,
    }


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

    if PROVIDERS[provider]["mode"] == "live":
        if provider == "messenger":
            return _send_messenger(
                target=target,
                message=message,
                subject=subject,
                recipient_name=recipient_name,
            )
        raise ValueError(f"Unsupported live notify provider: {provider}")

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


def emit_event(
    config: dict[str, Any],
    rules_config: dict[str, Any],
    event: str,
    *,
    facts: dict[str, str],
    dry_run: bool = False,
    send_all: bool = False,
) -> dict[str, Any]:
    rules = rules_config.get("rules", {})
    matched: list[dict[str, Any]] = []
    triggered: list[dict[str, Any]] = []
    state = load_state()
    state_dirty = False
    now = time.time()

    for rule_name, rule in sorted(rules.items()):
        if not rule_matches(rule, event, facts):
            continue

        matched.append(
            {
                "name": rule_name,
                "recipient": rule.get("recipient"),
                "event": event,
                "match": rule.get("match", {}),
            }
        )

        try:
            message = render_template(str(rule["message"]), facts)
            subject_template = rule.get("subject")
            subject = render_template(str(subject_template), facts) if subject_template else None
            fingerprint = build_rule_fingerprint(rule_name, rule, facts)
        except ValueError as exc:
            triggered.append(
                {
                    "rule": rule_name,
                    "success": False,
                    "error": str(exc),
                    "skipped": "template_error",
                }
            )
            continue

        cooldown_seconds = int(rule.get("cooldown_seconds", 0) or 0)
        allowed, cooldown_payload = should_send_rule(state, rule_name, fingerprint, cooldown_seconds, now)
        if not allowed:
            triggered.append(cooldown_payload or {"rule": rule_name, "skipped": "cooldown"})
            continue

        if dry_run:
            payload = send_notification(
                config,
                str(rule["recipient"]),
                message,
                via=list(rule.get("via", [])),
                subject=subject,
                send_all=send_all,
                dry_run=True,
            )
            triggered.append(
                {
                    "rule": rule_name,
                    "fingerprint": fingerprint,
                    "cooldown_seconds": cooldown_seconds,
                    "notification": payload,
                    "planned": True,
                    "success": True,
                }
            )
            continue

        payload = send_notification(
            config,
            str(rule["recipient"]),
            message,
            via=list(rule.get("via", [])),
            subject=subject,
            send_all=send_all,
            dry_run=False,
        )
        triggered.append(
            {
                "rule": rule_name,
                "fingerprint": fingerprint,
                "cooldown_seconds": cooldown_seconds,
                "notification": payload,
                "success": bool(payload.get("success")),
            }
        )
        if payload.get("success"):
            state.setdefault("deliveries", {}).setdefault(rule_name, {})[fingerprint] = now
            state_dirty = True

    if state_dirty:
        save_state(state)

    overall_success = all(item.get("success", False) or item.get("skipped") for item in triggered) if triggered else True
    return {
        "success": overall_success,
        "event": event,
        "facts": facts,
        "dry_run": dry_run,
        "matched_rules": matched,
        "results": triggered,
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
