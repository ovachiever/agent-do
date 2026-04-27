#!/usr/bin/env python3
"""Structured mailbox query helpers for agent-email."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


OUTPUT_JSON = os.environ.get("AGENT_EMAIL_OUTPUT_JSON") == "1"
FIXTURE_PATH = os.environ.get("AGENT_EMAIL_FIXTURE")
FIELD_SEP = chr(31)
RECORD_SEP = chr(30)
ATTACH_SEP = chr(29)
ATTACH_FIELD_SEP = chr(28)
INBOX_NAMES = {"inbox", "in box", "inbox/"}


def emit(payload: dict[str, Any], *, raw: str | None = None) -> None:
    if OUTPUT_JSON:
        print(json.dumps(payload, indent=2))
        return
    if raw is not None:
        print(raw)
        return
    print(json.dumps(payload, indent=2))


def fail(message: str, *, error: str, code: int = 1, extra: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"ok": False, "error": error, "message": message}
    if extra:
        payload.update(extra)
    if OUTPUT_JSON:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_key(value: str) -> str:
    return normalize_text(value).lower()


def parse_date(value: str) -> tuple[int, str]:
    if not value:
        return (0, "")
    try:
        if value.endswith("Z"):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (int(parsed.timestamp()), parsed.isoformat())
    except Exception:
        pass
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (int(parsed.timestamp()), parsed.isoformat())
    except Exception:
        return (0, value)


def sort_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(item: dict[str, Any]) -> tuple[int, str]:
        stamp, normalized = parse_date(str(item.get("date", "")))
        return (stamp, normalized)

    return sorted(messages, key=sort_key, reverse=True)


def normalize_attachments(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if isinstance(item, dict):
            normalized.append(
                {
                    "name": normalize_text(item.get("name")) or f"attachment-{index}",
                    "mime_type": normalize_text(item.get("mime_type")),
                }
            )
        else:
            normalized.append({"name": normalize_text(item) or f"attachment-{index}", "mime_type": ""})
    return normalized


def availability_from_message(
    *,
    body: str,
    source: str,
    attachments: list[dict[str, Any]],
    override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    override = override or {}
    attachment_count = int(override.get("attachment_count") or len(attachments))
    body_available = bool(body.strip()) if "body_available" not in override else bool(override.get("body_available"))
    source_available = bool(source.strip()) if "source_available" not in override else bool(override.get("source_available"))
    state = str(override.get("state") or ("hydrated" if (body_available or source_available or attachment_count > 0) else "metadata_only"))
    return {
        "metadata_found": bool(override.get("metadata_found", True)),
        "body_available": body_available,
        "source_available": source_available,
        "attachment_count": attachment_count,
        "state": state,
    }


def normalize_message(item: dict[str, Any], index: int) -> dict[str, Any]:
    body = str(item.get("body") or item.get("content") or "")
    source = str(item.get("source") or "")
    attachments = normalize_attachments(item.get("attachments"))
    availability = availability_from_message(
        body=body,
        source=source,
        attachments=attachments,
        override=item.get("availability") if isinstance(item.get("availability"), dict) else None,
    )
    return {
        "id": str(item.get("id") or item.get("message_id") or f"message-{index}"),
        "account": normalize_text(item.get("account")),
        "mailbox": normalize_text(item.get("mailbox")) or "Inbox",
        "subject": normalize_text(item.get("subject")),
        "from": normalize_text(item.get("from") or item.get("sender")),
        "status": "unread" if str(item.get("status", "")).lower() == "unread" or item.get("read") is False else "read",
        "date": normalize_text(item.get("date")),
        "body": body,
        "source": source,
        "attachments": attachments,
        "availability": availability,
    }


def project_message(message: dict[str, Any], *, include_source: bool = False, include_attachments: bool = False) -> dict[str, Any]:
    projected = {
        "id": message.get("id", ""),
        "account": message.get("account", ""),
        "mailbox": message.get("mailbox", ""),
        "subject": message.get("subject", ""),
        "from": message.get("from", ""),
        "status": message.get("status", ""),
        "date": message.get("date", ""),
        "body": message.get("body", ""),
        "availability": dict(message.get("availability") or {}),
    }
    if include_source:
        projected["source"] = message.get("source", "")
    if include_attachments:
        projected["attachments"] = list(message.get("attachments") or [])
    return projected


def applescript_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class FixtureSource:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        raw_messages = payload.get("messages", [])
        self.messages = sort_messages(
            [
                normalize_message(item, index + 1)
                for index, item in enumerate(raw_messages if isinstance(raw_messages, list) else [])
                if isinstance(item, dict)
            ]
        )
        self.accounts = self._normalize_accounts()
        self.mailboxes = self._normalize_mailboxes()

    @property
    def platform(self) -> str:
        return str(self.payload.get("platform") or "fixture")

    def _normalize_accounts(self) -> list[dict[str, Any]]:
        accounts = self.payload.get("accounts", {})
        items = accounts.get("items") if isinstance(accounts, dict) else None
        normalized: list[dict[str, Any]] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                normalized.append({"name": normalize_text(item.get("name")), "type": normalize_text(item.get("type"))})
        if normalized:
            return normalized
        names = sorted({message.get("account", "") for message in self.messages if message.get("account")})
        return [{"name": name, "type": ""} for name in names]

    def _normalize_mailboxes(self) -> list[dict[str, Any]]:
        raw_mailboxes = self.payload.get("mailboxes")
        normalized: list[dict[str, Any]] = []
        if isinstance(raw_mailboxes, dict):
            raw_mailboxes = raw_mailboxes.get("items")
        if isinstance(raw_mailboxes, list):
            for item in raw_mailboxes:
                if not isinstance(item, dict):
                    continue
                normalized.append(
                    {
                        "account": normalize_text(item.get("account")),
                        "mailbox": normalize_text(item.get("mailbox") or item.get("name")),
                    }
                )
        if normalized:
            return normalized
        seen: set[tuple[str, str]] = set()
        derived: list[dict[str, Any]] = []
        for message in self.messages:
            key = (message.get("account", ""), message.get("mailbox", ""))
            if key in seen:
                continue
            seen.add(key)
            derived.append({"account": key[0], "mailbox": key[1]})
        return sorted(derived, key=lambda item: (normalize_key(item["account"]), normalize_key(item["mailbox"])))

    def selected_mailboxes(self, args: argparse.Namespace) -> list[dict[str, Any]]:
        selected = scope_mailboxes(self.mailboxes, args)
        return selected

    def count_messages(self, selected: list[dict[str, Any]]) -> tuple[int, int]:
        scoped = [message for message in self.messages if message_in_mailboxes(message, selected)]
        return (len(scoped), sum(1 for message in scoped if message.get("status") == "unread"))

    def list_messages(self, selected: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        scoped = [message for message in self.messages if message_in_mailboxes(message, selected)]
        return sort_messages(scoped)[:limit]

    def get_message(self, selected: list[dict[str, Any]], message_id: str) -> dict[str, Any] | None:
        for message in self.messages:
            if message.get("id") == message_id and message_in_mailboxes(message, selected):
                return message
        return None


class MacMailSource:
    def __init__(self) -> None:
        if sys.platform != "darwin":
            fail("Email querying currently requires macOS Mail.app or AGENT_EMAIL_FIXTURE", error="unsupported_platform")
        self._accounts: list[dict[str, Any]] | None = None
        self._mailboxes: list[dict[str, Any]] | None = None

    @property
    def platform(self) -> str:
        return "macOS Mail.app"

    def _run_osascript(self, script: str, *, timeout: int = 30) -> str:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "osascript failed")
        return proc.stdout.strip()

    def accounts(self) -> list[dict[str, Any]]:
        if self._accounts is not None:
            return self._accounts
        script = f'''
        tell application "Mail"
            set fieldSep to ASCII character 31
            set recordSep to ASCII character 30
            set output to ""
            repeat with acct in accounts
                set output to output & (name of acct as string) & fieldSep & (account type of acct as string) & recordSep
            end repeat
            return output
        end tell
        '''
        raw = self._run_osascript(script, timeout=10)
        accounts: list[dict[str, Any]] = []
        for row in [item for item in raw.split(RECORD_SEP) if item]:
            parts = row.split(FIELD_SEP)
            accounts.append({"name": parts[0] if len(parts) > 0 else "", "type": parts[1] if len(parts) > 1 else ""})
        self._accounts = accounts
        return accounts

    def mailboxes(self) -> list[dict[str, Any]]:
        if self._mailboxes is not None:
            return self._mailboxes
        script = f'''
        tell application "Mail"
            set fieldSep to ASCII character 31
            set recordSep to ASCII character 30
            set output to ""
            repeat with acct in accounts
                set acctName to name of acct as string
                repeat with mbx in every mailbox of acct
                    set output to output & acctName & fieldSep & (name of mbx as string) & recordSep
                end repeat
            end repeat
            return output
        end tell
        '''
        raw = self._run_osascript(script, timeout=15)
        mailboxes: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in [item for item in raw.split(RECORD_SEP) if item]:
            parts = row.split(FIELD_SEP)
            account = parts[0] if len(parts) > 0 else ""
            mailbox = parts[1] if len(parts) > 1 else ""
            key = (account, mailbox)
            if key in seen:
                continue
            seen.add(key)
            mailboxes.append({"account": account, "mailbox": mailbox})
        self._mailboxes = sorted(mailboxes, key=lambda item: (normalize_key(item["account"]), normalize_key(item["mailbox"])))
        return self._mailboxes

    def selected_mailboxes(self, args: argparse.Namespace) -> list[dict[str, Any]]:
        return scope_mailboxes(self.mailboxes(), args)

    def count_messages(self, selected: list[dict[str, Any]]) -> tuple[int, int]:
        if not selected:
            return (0, 0)
        blocks: list[str] = []
        for item in selected:
            account = applescript_quote(item["account"])
            mailbox = applescript_quote(item["mailbox"])
            blocks.append(
                f'''
                try
                    set acct to first account whose name is {account}
                    set mbx to first mailbox of acct whose name is {mailbox}
                    set totalCount to totalCount + (count of messages of mbx)
                    set unreadCount to unreadCount + (count of (every message of mbx whose read status is false))
                end try
                '''
            )
        script = f'''
        tell application "Mail"
            set totalCount to 0
            set unreadCount to 0
            {"".join(blocks)}
            return (totalCount as string) & "{FIELD_SEP}" & (unreadCount as string)
        end tell
        '''
        raw = self._run_osascript(script, timeout=20)
        parts = raw.split(FIELD_SEP)
        total = int(parts[0]) if parts and parts[0].isdigit() else 0
        unread = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return (total, unread)

    def list_messages(self, selected: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if not selected:
            return []
        per_mailbox_limit = max(limit, 50)
        blocks: list[str] = []
        for item in selected:
            account = applescript_quote(item["account"])
            mailbox = applescript_quote(item["mailbox"])
            blocks.append(
                f'''
                try
                    set acct to first account whose name is {account}
                    set mbx to first mailbox of acct whose name is {mailbox}
                    set mailboxCount to count of messages of mbx
                    if mailboxCount > 0 then
                        set msgCount to {per_mailbox_limit}
                        if mailboxCount < msgCount then set msgCount to mailboxCount
                        set msgs to messages 1 thru msgCount of mbx
                        repeat with m in msgs
                            set msgId to ""
                            try
                                set msgId to message id of m as string
                            end try
                            set subj to ""
                            try
                                set subj to subject of m as string
                            end try
                            set sndr to ""
                            try
                                set sndr to sender of m as string
                            end try
                            set isRead to "false"
                            try
                                set isRead to read status of m as string
                            end try
                            set dt to ""
                            try
                                set dt to date received of m as string
                            end try
                            set bodyText to ""
                            try
                                set bodyText to content of m as string
                            end try
                            set sourceText to ""
                            try
                                set sourceText to source of m as string
                            end try
                            set bodyAvailable to "false"
                            if length of bodyText > 0 then set bodyAvailable to "true"
                            set sourceAvailable to "false"
                            if length of sourceText > 0 then set sourceAvailable to "true"
                            set attCount to 0
                            try
                                set attCount to count of mail attachments of m
                            end try
                            set output to output & msgId & "{FIELD_SEP}" & {account} & "{FIELD_SEP}" & {mailbox} & "{FIELD_SEP}" & subj & "{FIELD_SEP}" & sndr & "{FIELD_SEP}" & isRead & "{FIELD_SEP}" & dt & "{FIELD_SEP}" & bodyText & "{FIELD_SEP}" & bodyAvailable & "{FIELD_SEP}" & sourceAvailable & "{FIELD_SEP}" & (attCount as string) & "{RECORD_SEP}"
                        end repeat
                    end if
                end try
                '''
            )
        script = f'''
        tell application "Mail"
            set output to ""
            {"".join(blocks)}
            return output
        end tell
        '''
        raw = self._run_osascript(script, timeout=45)
        messages: list[dict[str, Any]] = []
        for index, row in enumerate([item for item in raw.split(RECORD_SEP) if item], start=1):
            parts = row.split(FIELD_SEP)
            body = parts[7] if len(parts) > 7 else ""
            availability = {
                "metadata_found": True,
                "body_available": (parts[8] if len(parts) > 8 else "").lower() == "true",
                "source_available": (parts[9] if len(parts) > 9 else "").lower() == "true",
                "attachment_count": int(parts[10]) if len(parts) > 10 and parts[10].isdigit() else 0,
            }
            availability["state"] = "hydrated" if (availability["body_available"] or availability["source_available"] or availability["attachment_count"] > 0) else "metadata_only"
            messages.append(
                normalize_message(
                    {
                        "id": parts[0] if len(parts) > 0 else f"message-{index}",
                        "account": parts[1] if len(parts) > 1 else "",
                        "mailbox": parts[2] if len(parts) > 2 else "",
                        "subject": parts[3] if len(parts) > 3 else "",
                        "from": parts[4] if len(parts) > 4 else "",
                        "status": "read" if (parts[5] if len(parts) > 5 else "").lower() == "true" else "unread",
                        "date": parts[6] if len(parts) > 6 else "",
                        "body": body,
                        "availability": availability,
                    },
                    index,
                )
            )
        return sort_messages(messages)[:limit]

    def get_message(self, selected: list[dict[str, Any]], message_id: str) -> dict[str, Any] | None:
        if not selected:
            return None
        blocks: list[str] = []
        for item in selected:
            account = applescript_quote(item["account"])
            mailbox = applescript_quote(item["mailbox"])
            blocks.append(
                f'''
                try
                    set acct to first account whose name is {account}
                    set mbx to first mailbox of acct whose name is {mailbox}
                    repeat with m in messages of mbx
                        set msgId to ""
                        try
                            set msgId to message id of m as string
                        end try
                        if msgId is {applescript_quote(message_id)} then
                            set subj to ""
                            try
                                set subj to subject of m as string
                            end try
                            set sndr to ""
                            try
                                set sndr to sender of m as string
                            end try
                            set isRead to "false"
                            try
                                set isRead to read status of m as string
                            end try
                            set dt to ""
                            try
                                set dt to date received of m as string
                            end try
                            set bodyText to ""
                            try
                                set bodyText to content of m as string
                            end try
                            set sourceText to ""
                            try
                                set sourceText to source of m as string
                            end try
                            set attOutput to ""
                            try
                                repeat with att in mail attachments of m
                                    set attName to ""
                                    try
                                        set attName to name of att as string
                                    end try
                                    set attOutput to attOutput & attName & "{ATTACH_SEP}"
                                end repeat
                            end try
                            return msgId & "{FIELD_SEP}" & {account} & "{FIELD_SEP}" & {mailbox} & "{FIELD_SEP}" & subj & "{FIELD_SEP}" & sndr & "{FIELD_SEP}" & isRead & "{FIELD_SEP}" & dt & "{FIELD_SEP}" & bodyText & "{FIELD_SEP}" & sourceText & "{FIELD_SEP}" & attOutput
                        end if
                    end repeat
                end try
                '''
            )
        script = f'''
        tell application "Mail"
            {"".join(blocks)}
            return ""
        end tell
        '''
        raw = self._run_osascript(script, timeout=60)
        if not raw:
            return None
        parts = raw.split(FIELD_SEP)
        attachment_names = [item for item in (parts[9] if len(parts) > 9 else "").split(ATTACH_SEP) if item]
        attachments = [{"name": item, "mime_type": ""} for item in attachment_names]
        return normalize_message(
            {
                "id": parts[0] if len(parts) > 0 else message_id,
                "account": parts[1] if len(parts) > 1 else "",
                "mailbox": parts[2] if len(parts) > 2 else "",
                "subject": parts[3] if len(parts) > 3 else "",
                "from": parts[4] if len(parts) > 4 else "",
                "status": "read" if (parts[5] if len(parts) > 5 else "").lower() == "true" else "unread",
                "date": parts[6] if len(parts) > 6 else "",
                "body": parts[7] if len(parts) > 7 else "",
                "source": parts[8] if len(parts) > 8 else "",
                "attachments": attachments,
            },
            1,
        )


def load_fixture_source() -> FixtureSource | None:
    if not FIXTURE_PATH:
        return None
    path = Path(FIXTURE_PATH)
    if not path.exists():
        fail(f"fixture not found: {path}", error="fixture_not_found")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        payload = {"messages": payload}
    if not isinstance(payload, dict):
        fail("fixture payload must be a JSON object or array", error="invalid_fixture")
    return FixtureSource(payload)


def current_source() -> FixtureSource | MacMailSource:
    fixture = load_fixture_source()
    if fixture is not None:
        return fixture
    return MacMailSource()


def is_inbox_mailbox(name: str) -> bool:
    lowered = normalize_key(name)
    return lowered in INBOX_NAMES


def scope_mailboxes(mailboxes: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    target_account = normalize_key(getattr(args, "account", ""))
    target_mailbox = normalize_key(getattr(args, "mailbox", ""))
    all_mailboxes = bool(getattr(args, "all_mailboxes", False))
    selected: list[dict[str, Any]] = []
    for item in mailboxes:
        account = normalize_key(item.get("account", ""))
        mailbox = normalize_key(item.get("mailbox", ""))
        if target_account and account != target_account:
            continue
        if target_mailbox:
            if mailbox != target_mailbox:
                continue
        elif not all_mailboxes and not is_inbox_mailbox(mailbox):
            continue
        selected.append({"account": item.get("account", ""), "mailbox": item.get("mailbox", "")})
    return selected


def message_in_mailboxes(message: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
    msg_account = normalize_key(str(message.get("account", "")))
    msg_mailbox = normalize_key(str(message.get("mailbox", "")))
    for item in selected:
        if normalize_key(item.get("account", "")) == msg_account and normalize_key(item.get("mailbox", "")) == msg_mailbox:
            return True
    return False


def scope_payload(args: argparse.Namespace, selected: list[dict[str, Any]]) -> dict[str, Any]:
    mode = "all_mailboxes" if getattr(args, "all_mailboxes", False) else ("mailbox" if getattr(args, "mailbox", "") else "inbox")
    return {
        "mode": mode,
        "account": normalize_text(getattr(args, "account", "")),
        "mailbox": normalize_text(getattr(args, "mailbox", "")),
        "selected_mailboxes": {"count": len(selected), "items": selected},
    }


def matches(message: dict[str, Any], args: argparse.Namespace) -> bool:
    subject = str(message.get("subject", "")).lower()
    sender = str(message.get("from", "")).lower()
    body = str(message.get("body", "")).lower()
    text = f"{subject}\n{body}"
    exclude_ids = {item for item in getattr(args, "exclude_ids", []) if item}
    if message.get("id") in exclude_ids:
        return False
    if args.from_filter and args.from_filter.lower() not in sender:
        return False
    if args.subject_filter and args.subject_filter.lower() not in subject:
        return False
    if getattr(args, "query_text", "") and args.query_text.lower() not in text:
        return False
    if args.contains and args.contains.lower() not in text:
        return False
    if args.unread and message.get("status") != "unread":
        return False
    return True


def filtered_messages(source: FixtureSource | MacMailSource, args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[int, int]]:
    selected = source.selected_mailboxes(args)
    messages = source.list_messages(selected, max(1, args.limit))
    counts = source.count_messages(selected)
    matches_list = [item for item in messages if matches(item, args)]
    return selected, matches_list, counts


def find_message(source: FixtureSource | MacMailSource, args: argparse.Namespace, *, require_body: bool = False) -> dict[str, Any]:
    _, matches_list, _ = filtered_messages(source, args)
    if not matches_list:
        fail("No matching email found", error="no_match")
    message = matches_list[0]
    if require_body and not message.get("availability", {}).get("body_available"):
        fail(
            "Matching email metadata was found but the body is unavailable",
            error="metadata_only",
            extra={
                "message_id": message.get("id"),
                "account": message.get("account", ""),
                "mailbox": message.get("mailbox", ""),
            },
        )
    return message


def extract_code(message: dict[str, Any], args: argparse.Namespace) -> str:
    availability = message.get("availability", {}) or {}
    if not availability.get("body_available"):
        fail(
            "Matching email metadata was found but the body is unavailable",
            error="metadata_only",
            extra={
                "message_id": message.get("id"),
                "account": message.get("account", ""),
                "mailbox": message.get("mailbox", ""),
            },
        )
    text = f"{message.get('subject', '')}\n{message.get('body', '')}"
    if args.regex:
        pattern = re.compile(args.regex)
    else:
        if args.length:
            pattern = re.compile(rf"(?<!\d)(\d{{{args.length}}})(?!\d)")
        else:
            pattern = re.compile(r"(?<!\d)(\d{6,8})(?!\d)")
    match = pattern.search(text)
    if not match:
        fail(
            "No verification code found in matching email",
            error="code_not_found",
            extra={"message_id": message.get("id"), "account": message.get("account", ""), "mailbox": message.get("mailbox", "")},
        )
    return match.group(1) if match.groups() else match.group(0)


def extract_link(message: dict[str, Any], args: argparse.Namespace) -> str:
    availability = message.get("availability", {}) or {}
    if not availability.get("body_available"):
        fail(
            "Matching email metadata was found but the body is unavailable",
            error="metadata_only",
            extra={
                "message_id": message.get("id"),
                "account": message.get("account", ""),
                "mailbox": message.get("mailbox", ""),
            },
        )
    text = f"{message.get('subject', '')}\n{message.get('body', '')}"
    links = re.findall(r"https?://[^\s<>\")']+", text)
    if args.domain:
        links = [item for item in links if args.domain.lower() in item.lower()]
    if not links:
        fail(
            "No matching link found in email",
            error="link_not_found",
            extra={"message_id": message.get("id"), "account": message.get("account", ""), "mailbox": message.get("mailbox", "")},
        )
    return links[0]


def wait_for_message(source: FixtureSource | MacMailSource, args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], tuple[int, int]]:
    deadline = time.time() + max(1, args.timeout)
    last_count = 0
    selected: list[dict[str, Any]] = []
    counts = (0, 0)
    while True:
        selected, matches_list, counts = filtered_messages(source, args)
        last_count = len(matches_list)
        if matches_list:
            return selected, matches_list[0], counts
        if time.time() >= deadline:
            fail(
                "Timed out waiting for matching email",
                error="timeout",
                extra={
                    "timeout_seconds": args.timeout,
                    "matched_count": last_count,
                    "scope": scope_payload(args, selected),
                },
            )
        time.sleep(max(1, args.interval))


def handle_snapshot(source: FixtureSource | MacMailSource, args: argparse.Namespace) -> None:
    selected = source.selected_mailboxes(args)
    messages = source.list_messages(selected, max(1, args.limit))
    counts = source.count_messages(selected)
    payload = {
        "ok": True,
        "platform": source.platform,
        "accounts": {"count": len(source.accounts if isinstance(source, FixtureSource) else source.accounts()), "items": source.accounts if isinstance(source, FixtureSource) else source.accounts()},
        "mailboxes": {"count": len(source.mailboxes if isinstance(source, FixtureSource) else source.mailboxes()), "items": source.mailboxes if isinstance(source, FixtureSource) else source.mailboxes()},
        "scope": scope_payload(args, selected),
        "message_count": counts[0],
        "unread_count": counts[1],
        "inbox_unread": counts[1],
        "recent_messages": {"count": len(messages), "items": [project_message(item) for item in messages]},
    }
    emit(payload)


def handle_search(source: FixtureSource | MacMailSource, args: argparse.Namespace) -> None:
    selected, matches_list, counts = filtered_messages(source, args)
    payload = {
        "ok": True,
        "platform": source.platform,
        "scope": scope_payload(args, selected),
        "message_count": counts[0],
        "unread_count": counts[1],
        "messages": {"count": len(matches_list), "items": [project_message(item) for item in matches_list]},
    }
    emit(payload)


def handle_latest(source: FixtureSource | MacMailSource, args: argparse.Namespace) -> None:
    message = find_message(source, args)
    payload = {"ok": True, "message": project_message(message)}
    emit(payload, raw=json.dumps(project_message(message), indent=2))


def handle_wait(source: FixtureSource | MacMailSource, args: argparse.Namespace) -> None:
    _, message, _ = wait_for_message(source, args)
    payload = {"ok": True, "message": project_message(message)}
    emit(payload, raw=json.dumps(project_message(message), indent=2))


def handle_code(source: FixtureSource | MacMailSource, args: argparse.Namespace) -> None:
    _, message, _ = wait_for_message(source, args)
    code = extract_code(message, args)
    payload = {"ok": True, "code": code, "message": project_message(message)}
    emit(payload, raw=code)


def handle_link(source: FixtureSource | MacMailSource, args: argparse.Namespace) -> None:
    _, message, _ = wait_for_message(source, args)
    link = extract_link(message, args)
    payload = {"ok": True, "link": link, "message": project_message(message)}
    emit(payload, raw=link)


def handle_get(source: FixtureSource | MacMailSource, args: argparse.Namespace) -> None:
    selected = source.selected_mailboxes(args)
    message = source.get_message(selected, args.message_id)
    if message is None:
        fail(
            "No email found for the requested message id",
            error="message_not_found",
            extra={"message_id": args.message_id, "scope": scope_payload(args, selected)},
        )
    payload = {"ok": True, "message": project_message(message, include_source=True, include_attachments=True)}
    emit(payload, raw=json.dumps(project_message(message, include_source=True, include_attachments=True), indent=2))


def handle_count(source: FixtureSource | MacMailSource, args: argparse.Namespace) -> None:
    selected = source.selected_mailboxes(args)
    counts = source.count_messages(selected)
    payload = {
        "ok": True,
        "scope": scope_payload(args, selected),
        "message_count": counts[0],
        "unread_count": counts[1],
    }
    emit(payload, raw=str(counts[1]))


def handle_mailboxes(source: FixtureSource | MacMailSource, args: argparse.Namespace) -> None:
    mailboxes = source.selected_mailboxes(args) if getattr(args, "account", "") else (source.mailboxes if isinstance(source, FixtureSource) else source.mailboxes())
    payload = {
        "ok": True,
        "accounts": {"count": len(source.accounts if isinstance(source, FixtureSource) else source.accounts()), "items": source.accounts if isinstance(source, FixtureSource) else source.accounts()},
        "mailboxes": {"count": len(mailboxes), "items": mailboxes},
    }
    emit(payload)


def add_scope_args(subparser: argparse.ArgumentParser, *, allow_all_mailboxes: bool = True) -> None:
    subparser.add_argument("--account")
    subparser.add_argument("--mailbox")
    if allow_all_mailboxes:
        subparser.add_argument("--all-mailboxes", action="store_true")


def add_filter_args(subparser: argparse.ArgumentParser, *, allow_all_mailboxes: bool = True) -> None:
    subparser.add_argument("--from", dest="from_filter")
    subparser.add_argument("--subject", dest="subject_filter")
    subparser.add_argument("--contains")
    subparser.add_argument("--unread", action="store_true")
    subparser.add_argument("--limit", type=int, default=20)
    subparser.add_argument("--exclude-id", dest="exclude_ids", action="append", default=[])
    add_scope_args(subparser, allow_all_mailboxes=allow_all_mailboxes)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--limit", type=int, default=10)
    add_scope_args(snapshot)

    search = sub.add_parser("search")
    search.add_argument("query", nargs="?")
    add_filter_args(search)

    latest = sub.add_parser("latest")
    add_filter_args(latest)

    wait = sub.add_parser("wait")
    add_filter_args(wait)
    wait.add_argument("--timeout", type=int, default=60)
    wait.add_argument("--interval", type=int, default=5)

    code = sub.add_parser("code")
    add_filter_args(code)
    code.add_argument("--timeout", type=int, default=120)
    code.add_argument("--interval", type=int, default=5)
    code.add_argument("--length", type=int)
    code.add_argument("--regex")

    link = sub.add_parser("link")
    add_filter_args(link)
    link.add_argument("--timeout", type=int, default=120)
    link.add_argument("--interval", type=int, default=5)
    link.add_argument("--domain")

    get_parser = sub.add_parser("get")
    get_parser.add_argument("--id", dest="message_id", required=True)
    add_scope_args(get_parser)

    count = sub.add_parser("count")
    add_scope_args(count)

    mailboxes = sub.add_parser("mailboxes")
    mailboxes.add_argument("--account")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:])
    args.query_text = getattr(args, "query", None) or ""
    source = current_source()

    if args.command == "snapshot":
        handle_snapshot(source, args)
    elif args.command == "search":
        handle_search(source, args)
    elif args.command == "latest":
        handle_latest(source, args)
    elif args.command == "wait":
        handle_wait(source, args)
    elif args.command == "code":
        handle_code(source, args)
    elif args.command == "link":
        handle_link(source, args)
    elif args.command == "get":
        handle_get(source, args)
    elif args.command == "count":
        handle_count(source, args)
    elif args.command == "mailboxes":
        handle_mailboxes(source, args)
    else:
        fail("unknown command", error="unknown_command")


if __name__ == "__main__":
    main()
