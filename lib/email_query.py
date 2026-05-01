#!/usr/bin/env python3
"""Structured mailbox query helpers for agent-email."""

from __future__ import annotations

import argparse
import html
import imaplib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


OUTPUT_JSON = os.environ.get("AGENT_EMAIL_OUTPUT_JSON") == "1"
FIXTURE_PATH = os.environ.get("AGENT_EMAIL_FIXTURE")
FIELD_SEP = chr(31)
RECORD_SEP = chr(30)
ATTACH_SEP = chr(29)
ATTACH_FIELD_SEP = chr(28)
INBOX_NAMES = {"inbox", "in box", "inbox/"}
REMOTE_HYDRATION_DISABLED = os.environ.get("AGENT_EMAIL_DISABLE_REMOTE_HYDRATION") == "1"


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
            attachment = {
                "name": normalize_text(item.get("name")) or f"attachment-{index}",
                "mime_type": normalize_text(item.get("mime_type")),
            }
            if "size" in item:
                attachment["size"] = item.get("size")
            if "download_available" in item:
                attachment["download_available"] = bool(item.get("download_available"))
            normalized.append(attachment)
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
    body_kind = str(override.get("body_kind") or ("full" if body_available else "none"))
    body_is_full = bool(override.get("body_is_full", body_available and body_kind != "summary"))
    attachment_metadata_available = bool(override.get("attachment_metadata_available", attachment_count > 0))
    attachment_download_available = bool(override.get("attachment_download_available", False))
    if override.get("state"):
        state = str(override["state"])
    elif source_available:
        state = "raw_source"
    elif body_available and body_is_full:
        state = "full_body"
    elif body_available:
        state = "summary_only"
    elif attachment_download_available:
        state = "attachment_downloaded"
    elif attachment_metadata_available:
        state = "attachment_metadata"
    else:
        state = "metadata_only"
    export_formats = ["json"]
    if source_available:
        export_formats.append("eml")
    if body_available and body_is_full:
        export_formats.extend(["txt", "html", "pdf"])
    return {
        "metadata_found": bool(override.get("metadata_found", True)),
        "body_available": body_available,
        "source_available": source_available,
        "attachment_count": attachment_count,
        "attachment_metadata_available": attachment_metadata_available,
        "attachment_download_available": attachment_download_available,
        "body_kind": body_kind,
        "body_is_full": body_is_full,
        "export_formats": export_formats,
        "state": state,
    }


def normalize_message(item: dict[str, Any], index: int) -> dict[str, Any]:
    body = str(item.get("body") or item.get("content") or "")
    source = str(item.get("source") or "")
    attachments = normalize_attachments(item.get("attachments"))
    provider = item.get("provider") if isinstance(item.get("provider"), dict) else {}
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
        "provider": dict(provider),
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

    def query_messages(self, args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[int, int]]:
        selected = self.selected_mailboxes(args)
        counts = self.count_messages(selected)
        messages = self.list_messages(selected, max(1, args.limit))
        matches_list = [item for item in messages if matches(item, args)]
        return selected, matches_list, counts


class MacMailSource:
    def __init__(self) -> None:
        if sys.platform != "darwin" and not os.environ.get("AGENT_EMAIL_ENVELOPE_INDEX"):
            fail("Email querying currently requires macOS Mail.app or AGENT_EMAIL_FIXTURE", error="unsupported_platform")
        self.db_path = self._locate_envelope_index()
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._accounts: list[dict[str, Any]] | None = None
        self._mailboxes: list[dict[str, Any]] | None = None

    @property
    def platform(self) -> str:
        return "macOS Mail Envelope Index"

    def _locate_envelope_index(self) -> Path:
        override = os.environ.get("AGENT_EMAIL_ENVELOPE_INDEX")
        if override:
            path = Path(override).expanduser()
            if path.exists():
                return path
            fail(f"Envelope Index not found: {path}", error="envelope_index_not_found")
        roots = sorted((Path.home() / "Library" / "Mail").glob("V*/MailData/Envelope Index"), reverse=True)
        for path in roots:
            if path.exists():
                return path
        fail("Could not locate Apple Mail Envelope Index", error="envelope_index_not_found")

    def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, params))

    def _decode_mailbox(self, url: str) -> tuple[str, str, str]:
        parsed = urlparse(url or "")
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc
        account = f"{scheme}://{netloc}" if netloc else (scheme or "mail")
        mailbox = unquote(parsed.path.lstrip("/")) or "Inbox"
        mailbox_type = scheme.upper() if scheme else ""
        return account, mailbox, mailbox_type

    def accounts(self) -> list[dict[str, Any]]:
        if self._accounts is not None:
            return self._accounts
        accounts: dict[str, dict[str, Any]] = {}
        for item in self.mailboxes():
            name = item.get("account", "")
            if not name or name in accounts:
                continue
            accounts[name] = {"name": name, "type": item.get("type", "")}
        self._accounts = sorted(accounts.values(), key=lambda item: normalize_key(item["name"]))
        return self._accounts

    def mailboxes(self) -> list[dict[str, Any]]:
        if self._mailboxes is not None:
            return self._mailboxes
        rows = self._query("SELECT url FROM mailboxes ORDER BY url")
        mailboxes: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            url = str(row["url"] or "")
            if not url or url in seen:
                continue
            seen.add(url)
            account, mailbox, mailbox_type = self._decode_mailbox(url)
            mailboxes.append({"account": account, "mailbox": mailbox, "url": url, "type": mailbox_type})
        self._mailboxes = sorted(mailboxes, key=lambda item: (normalize_key(item["account"]), normalize_key(item["mailbox"])))
        return self._mailboxes

    def selected_mailboxes(self, args: argparse.Namespace) -> list[dict[str, Any]]:
        return scope_mailboxes(self.mailboxes(), args)

    def count_messages(self, selected: list[dict[str, Any]]) -> tuple[int, int]:
        if not selected:
            return (0, 0)
        urls = [item["url"] for item in selected if item.get("url")]
        placeholders = ",".join("?" for _ in urls)
        row = self.conn.execute(
            f"""
            SELECT COUNT(*) AS total_count,
                   COALESCE(SUM(CASE WHEN COALESCE(m.read, 0) = 0 THEN 1 ELSE 0 END), 0) AS unread_count
            FROM messages m
            JOIN mailboxes mb ON m.mailbox = mb.ROWID
            WHERE COALESCE(m.deleted, 0) = 0
              AND mb.url IN ({placeholders})
            """,
            tuple(urls),
        ).fetchone()
        return (int(row["total_count"] or 0), int(row["unread_count"] or 0))

    def list_messages(self, selected: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        args = argparse.Namespace(
            from_filter="",
            subject_filter="",
            contains="",
            query_text="",
            unread=False,
            limit=limit,
            exclude_ids=[],
            account="",
            mailbox="",
            all_mailboxes=True,
        )
        _, messages, _ = self.query_messages(args, selected_override=selected)
        return messages

    def get_message(self, selected: list[dict[str, Any]], message_id: str) -> dict[str, Any] | None:
        if not selected:
            return None
        args = argparse.Namespace(
            from_filter="",
            subject_filter="",
            contains="",
            query_text="",
            unread=False,
            limit=1,
            exclude_ids=[],
            account="",
            mailbox="",
            all_mailboxes=True,
        )
        _, matches_list, _ = self.query_messages(args, selected_override=selected, message_id=message_id)
        return matches_list[0] if matches_list else None

    def query_messages(
        self,
        args: argparse.Namespace,
        *,
        selected_override: list[dict[str, Any]] | None = None,
        message_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[int, int]]:
        selected = selected_override or self.selected_mailboxes(args)
        counts = self.count_messages(selected)
        if not selected:
            return selected, [], counts

        urls = [item["url"] for item in selected if item.get("url")]
        placeholders = ",".join("?" for _ in urls)
        where = [
            "COALESCE(m.deleted, 0) = 0",
            f"mb.url IN ({placeholders})",
        ]
        params: list[Any] = list(urls)

        if message_id:
            if message_id.startswith("db:"):
                try:
                    rowid = int(message_id.split(":", 1)[1])
                except ValueError:
                    rowid = -1
                where.append("m.ROWID = ?")
                params.append(rowid)
            else:
                where.append("CAST(m.message_id AS TEXT) = ?")
                params.append(message_id)

        if args.from_filter:
            where.append(
                """
                (
                    lower(COALESCE(a_direct.address, '')) LIKE ?
                    OR EXISTS (
                        SELECT 1
                        FROM sender_addresses sax
                        JOIN addresses ax ON sax.address = ax.ROWID
                        WHERE sax.sender = m.sender
                          AND lower(COALESCE(ax.address, '')) LIKE ?
                    )
                )
                """
            )
            needle = f"%{args.from_filter.lower()}%"
            params.extend([needle, needle])
        if args.subject_filter:
            where.append("lower(COALESCE(sub.subject, '')) LIKE ?")
            params.append(f"%{args.subject_filter.lower()}%")
        query_text = args.query_text or ""
        contains = args.contains or ""
        if query_text:
            where.append("(lower(COALESCE(sub.subject, '')) LIKE ? OR lower(COALESCE(sumry.summary, '')) LIKE ?)")
            needle = f"%{query_text.lower()}%"
            params.extend([needle, needle])
        if contains:
            where.append("(lower(COALESCE(sub.subject, '')) LIKE ? OR lower(COALESCE(sumry.summary, '')) LIKE ?)")
            needle = f"%{contains.lower()}%"
            params.extend([needle, needle])
        if args.unread:
            where.append("COALESCE(m.read, 0) = 0")

        limit = max(1, int(args.limit))
        query = f"""
            SELECT
                m.ROWID AS rowid,
                m.message_id AS message_id_value,
                COALESCE(m.remote_id, '') AS remote_id,
                COALESCE(mgd.message_id_header, '') AS message_id_header,
                COALESCE(
                    a_direct.address,
                    (
                        SELECT group_concat(addr.address, ', ')
                        FROM sender_addresses sax
                        JOIN addresses addr ON sax.address = addr.ROWID
                        WHERE sax.sender = m.sender
                    ),
                    ''
                ) AS sender_address,
                COALESCE(sub.subject, '') AS subject_text,
                COALESCE(sumry.summary, '') AS summary_text,
                COALESCE(m.read, 0) AS is_read,
                COALESCE(m.date_received, m.date_sent, 0) AS display_date,
                mb.url AS mailbox_url,
                COALESCE(att.attachment_count, 0) AS attachment_count,
                COALESCE(att.attachment_names, '') AS attachment_names,
                COALESCE(sm.message_body_indexed, 0) AS message_body_indexed
            FROM messages m
            JOIN mailboxes mb ON m.mailbox = mb.ROWID
            LEFT JOIN message_global_data mgd ON mgd.ROWID = m.global_message_id
            LEFT JOIN addresses a_direct ON m.sender = a_direct.ROWID
            LEFT JOIN subjects sub ON m.subject = sub.ROWID
            LEFT JOIN summaries sumry ON m.summary = sumry.ROWID
            LEFT JOIN searchable_messages sm ON sm.message = m.ROWID
            LEFT JOIN (
                SELECT message,
                       COUNT(*) AS attachment_count,
                       group_concat(COALESCE(name, ''), char(29)) AS attachment_names
                FROM attachments
                GROUP BY message
            ) att ON att.message = m.ROWID
            WHERE {" AND ".join(where)}
            ORDER BY COALESCE(m.date_received, m.date_sent, 0) DESC
            LIMIT ?
        """
        params.append(limit)
        rows = self._query(query, tuple(params))
        matches_list: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            account, mailbox, _mailbox_type = self._decode_mailbox(str(row["mailbox_url"] or ""))
            attachments: list[dict[str, Any]] = []
            attachment_count = int(row["attachment_count"] or 0)
            if attachment_count:
                attachment_names = [item for item in str(row["attachment_names"] or "").split(ATTACH_SEP)]
                attachments = [
                    {
                        "name": normalize_text(attachment_names[i] if i < len(attachment_names) else "") or f"attachment-{i+1}",
                        "mime_type": "",
                        "download_available": False,
                    }
                    for i in range(attachment_count)
                ]
            summary_text = normalize_text(row["summary_text"])
            body = summary_text if summary_text else ""
            availability = {
                "metadata_found": True,
                "body_available": bool(body),
                "source_available": False,
                "attachment_count": attachment_count,
                "attachment_metadata_available": attachment_count > 0,
                "attachment_download_available": False,
                "body_kind": "summary" if body else "none",
                "body_is_full": False,
                "state": "summary_only" if body else ("attachment_metadata" if attachment_count else "metadata_only"),
            }
            matches_list.append(
                normalize_message(
                    {
                        "id": f"db:{int(row['rowid'])}",
                        "account": account,
                        "mailbox": mailbox,
                        "subject": row["subject_text"],
                        "from": row["sender_address"],
                        "status": "read" if int(row["is_read"] or 0) else "unread",
                        "date": datetime.fromtimestamp(int(row["display_date"] or 0), tz=timezone.utc).isoformat() if int(row["display_date"] or 0) else "",
                        "body": body,
                        "source": "",
                        "attachments": attachments,
                        "provider": {
                            "mailbox_url": row["mailbox_url"],
                            "remote_id": row["remote_id"],
                            "message_id_header": row["message_id_header"],
                        },
                        "availability": availability,
                    },
                    index,
                )
            )
        return selected, matches_list, counts


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
        selected.append(dict(item))
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
        "selected_mailboxes": {
            "count": len(selected),
            "items": [{"account": item.get("account", ""), "mailbox": item.get("mailbox", "")} for item in selected],
        },
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
    return source.query_messages(args)


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


class RemoteHydrationError(Exception):
    """Raised when a configured remote provider cannot hydrate a message."""


def truthy_env(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return normalize_key(value) not in {"", "0", "false", "no", "off"}


def remote_provider_config(message: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if REMOTE_HYDRATION_DISABLED:
        return None, None
    provider = normalize_key(os.environ.get("AGENT_EMAIL_PROVIDER", ""))
    if not provider and os.environ.get("AGENT_EMAIL_IMAP_HOST"):
        provider = "imap"
    if not provider:
        return None, None
    if provider not in {"imap", "gmail", "exchange", "outlook", "office365", "ews"}:
        return None, {
            "attempted": ["apple_mail_envelope_index", provider],
            "available": False,
            "provider": provider,
            "error": "unsupported_provider",
            "next": "Use AGENT_EMAIL_PROVIDER=imap, gmail, exchange, outlook, office365, or ews.",
        }

    host = normalize_text(os.environ.get("AGENT_EMAIL_IMAP_HOST"))
    if not host and provider == "gmail":
        host = "imap.gmail.com"
    if not host and provider in {"exchange", "outlook", "office365", "ews"}:
        host = "outlook.office365.com"
    user = normalize_text(os.environ.get("AGENT_EMAIL_IMAP_USER") or os.environ.get("EMAIL_USER"))
    password = str(os.environ.get("AGENT_EMAIL_IMAP_PASS") or os.environ.get("EMAIL_PASS") or "")
    missing = [
        name
        for name, value in [
            ("AGENT_EMAIL_IMAP_HOST", host),
            ("AGENT_EMAIL_IMAP_USER", user),
            ("AGENT_EMAIL_IMAP_PASS", password),
        ]
        if not value
    ]
    if missing:
        return None, {
            "attempted": ["apple_mail_envelope_index", provider],
            "available": False,
            "provider": provider,
            "error": "provider_not_configured",
            "missing": missing,
            "next": "Configure IMAP provider env vars, or leave remote hydration disabled.",
        }

    port = int(os.environ.get("AGENT_EMAIL_IMAP_PORT") or "993")
    timeout = int(os.environ.get("AGENT_EMAIL_IMAP_TIMEOUT") or "20")
    mailboxes_env = normalize_text(os.environ.get("AGENT_EMAIL_IMAP_MAILBOXES") or os.environ.get("AGENT_EMAIL_IMAP_MAILBOX"))
    mailboxes = [normalize_text(item) for item in mailboxes_env.split(",") if normalize_text(item)] if mailboxes_env else []
    for candidate in [normalize_text(message.get("mailbox")), "INBOX"]:
        if candidate and candidate not in mailboxes:
            mailboxes.append(candidate)
    return {
        "provider": provider,
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "ssl": truthy_env("AGENT_EMAIL_IMAP_SSL", default=True),
        "timeout": timeout,
        "mailboxes": mailboxes or ["INBOX"],
    }, None


def remote_provider_status() -> dict[str, Any]:
    provider = normalize_key(os.environ.get("AGENT_EMAIL_PROVIDER", ""))
    if not provider and os.environ.get("AGENT_EMAIL_IMAP_HOST"):
        provider = "imap"
    config, error = remote_provider_config({"mailbox": "INBOX"})
    if config:
        return {
            "configured": True,
            "disabled": False,
            "provider": config["provider"],
            "mode": "imap_compatible",
            "host": config["host"],
            "port": config["port"],
            "user_present": bool(config["user"]),
            "password_present": bool(config["password"]),
            "mailboxes": config["mailboxes"],
        }
    if REMOTE_HYDRATION_DISABLED:
        return {
            "configured": False,
            "disabled": True,
            "provider": provider,
            "mode": "imap_compatible",
            "missing": [],
            "next": "Unset AGENT_EMAIL_DISABLE_REMOTE_HYDRATION to enable provider fallback.",
        }
    if error:
        return {
            "configured": False,
            "disabled": False,
            "provider": error.get("provider", provider),
            "mode": "imap_compatible",
            "missing": error.get("missing", []),
            "error": error.get("error", ""),
            "next": error.get("next", ""),
        }
    return {
        "configured": False,
        "disabled": False,
        "provider": "",
        "mode": "imap_compatible",
        "missing": ["AGENT_EMAIL_PROVIDER", "AGENT_EMAIL_IMAP_HOST", "AGENT_EMAIL_IMAP_USER", "AGENT_EMAIL_IMAP_PASS"],
        "next": "Store or export IMAP-compatible provider env vars to hydrate metadata-only Mail rows.",
    }


def message_id_candidates(value: Any) -> list[str]:
    raw = normalize_text(value)
    if not raw:
        return []
    stripped = raw.strip()
    inner = stripped[1:-1].strip() if stripped.startswith("<") and stripped.endswith(">") else stripped
    candidates = [stripped]
    if inner and inner != stripped:
        candidates.append(inner)
    if inner and not stripped.startswith("<"):
        candidates.insert(0, f"<{inner}>")
    seen: set[str] = set()
    normalized: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            normalized.append(candidate)
    return normalized


def decode_mime_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw_payload = part.get_payload()
        return raw_payload if isinstance(raw_payload, str) else ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def html_body_to_text(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    text = re.sub(r"(?s)<br\s*/?>", "\n", text)
    text = re.sub(r"(?s)</p\s*>", "\n\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text)).strip()


def extract_remote_body(parsed: Message) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    for part in parsed.walk():
        if part.is_multipart():
            continue
        disposition = normalize_key(part.get_content_disposition() or "")
        if disposition == "attachment" or part.get_filename():
            continue
        content_type = normalize_key(part.get_content_type())
        if content_type == "text/plain":
            text = decode_mime_part(part).strip()
            if text:
                plain_parts.append(text)
        elif content_type == "text/html":
            text = html_body_to_text(decode_mime_part(part))
            if text:
                html_parts.append(text)
    if plain_parts:
        return "\n\n".join(plain_parts).strip()
    return "\n\n".join(html_parts).strip()


def extract_remote_attachments(parsed: Message) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for index, part in enumerate(parsed.walk(), start=1):
        if part.is_multipart():
            continue
        disposition = normalize_key(part.get_content_disposition() or "")
        filename = normalize_text(part.get_filename())
        if disposition != "attachment" and not filename:
            continue
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            {
                "name": filename or f"attachment-{index}",
                "mime_type": normalize_text(part.get_content_type()),
                "size": len(payload),
                "download_available": False,
            }
        )
    return attachments


def imap_client(config: dict[str, Any]) -> imaplib.IMAP4:
    cls = imaplib.IMAP4_SSL if config["ssl"] else imaplib.IMAP4
    try:
        return cls(config["host"], config["port"], timeout=config["timeout"])
    except TypeError:
        return cls(config["host"], config["port"])


def response_ok(status: Any) -> bool:
    return normalize_key(status.decode("utf-8", errors="replace") if isinstance(status, bytes) else str(status)) == "ok"


def first_fetch_payload(data: list[Any]) -> bytes | None:
    for item in data:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
            return bytes(item[1])
    return None


def fetch_remote_source_by_message_id(config: dict[str, Any], candidates: list[str]) -> tuple[bytes, dict[str, Any]]:
    client = imap_client(config)
    try:
        status, _ = client.login(config["user"], config["password"])
        if not response_ok(status):
            raise RemoteHydrationError("IMAP login failed")
        for mailbox in config["mailboxes"]:
            status, _ = client.select(mailbox, readonly=True)
            if not response_ok(status):
                continue
            for candidate in candidates:
                status, data = client.search(None, "HEADER", "Message-ID", candidate)
                if not response_ok(status):
                    continue
                raw_ids = data[0] if data else b""
                if isinstance(raw_ids, str):
                    raw_ids = raw_ids.encode("utf-8")
                ids = [item for item in bytes(raw_ids).split() if item]
                if not ids:
                    continue
                status, fetch_data = client.fetch(ids[-1], "(RFC822)")
                if not response_ok(status):
                    continue
                payload = first_fetch_payload(fetch_data)
                if payload:
                    return payload, {"mailbox": mailbox, "matched_by": "message_id_header", "message_id": candidate}
        raise RemoteHydrationError("No remote message matched the Apple Mail Message-ID")
    finally:
        try:
            client.logout()
        except Exception:
            pass


def with_hydration_status(message: dict[str, Any], hydration: dict[str, Any]) -> dict[str, Any]:
    cloned = dict(message)
    availability = dict(cloned.get("availability") or {})
    availability["hydration"] = hydration
    cloned["availability"] = availability
    return cloned


def hydrate_remote_message(message: dict[str, Any]) -> dict[str, Any]:
    availability = message.get("availability", {}) or {}
    if availability.get("source_available") or (availability.get("body_available") and availability.get("body_is_full")):
        return message
    provider_meta = message.get("provider") if isinstance(message.get("provider"), dict) else {}
    candidates = message_id_candidates(provider_meta.get("message_id_header"))
    if not candidates:
        return with_hydration_status(
            message,
            {
                "attempted": ["apple_mail_envelope_index"],
                "available": False,
                "error": "missing_message_id_header",
                "next": "Remote hydration needs Apple Mail's RFC822 Message-ID metadata.",
            },
        )
    config, config_error = remote_provider_config(message)
    if config_error:
        return with_hydration_status(message, config_error)
    if not config:
        return with_hydration_status(
            message,
            {
                "attempted": ["apple_mail_envelope_index"],
                "available": False,
                "next": "Configure AGENT_EMAIL_PROVIDER plus IMAP env vars to fetch remote body/source.",
            },
        )
    try:
        raw_source, match = fetch_remote_source_by_message_id(config, candidates)
        source = raw_source.decode("utf-8", errors="replace")
        parsed = BytesParser(policy=policy.default).parsebytes(raw_source)
        body = extract_remote_body(parsed)
        attachments = extract_remote_attachments(parsed) or list(message.get("attachments") or [])
        hydration = {
            "attempted": ["apple_mail_envelope_index", config["provider"]],
            "available": True,
            "provider": config["provider"],
            "host": config["host"],
            "mailbox": match.get("mailbox", ""),
            "matched_by": match.get("matched_by", ""),
        }
        hydrated = dict(message)
        hydrated["body"] = body or message.get("body", "")
        hydrated["source"] = source
        hydrated["attachments"] = attachments
        hydrated["availability"] = availability_from_message(
            body=str(hydrated["body"] or ""),
            source=source,
            attachments=attachments,
            override={
                "metadata_found": True,
                "body_kind": "full" if body else "none",
                "body_is_full": bool(body),
                "source_available": True,
                "attachment_metadata_available": bool(attachments),
                "attachment_download_available": False,
                "state": "raw_source",
            },
        )
        hydrated["availability"]["hydration"] = hydration
        return hydrated
    except Exception as exc:
        return with_hydration_status(
            message,
            {
                "attempted": ["apple_mail_envelope_index", config["provider"]],
                "available": False,
                "provider": config["provider"],
                "host": config["host"],
                "error": exc.__class__.__name__,
                "message": str(exc),
                "next": "Verify provider credentials, mailbox scope, and Message-ID search support.",
            },
        )


def message_text_for_export(message: dict[str, Any], args: argparse.Namespace) -> str:
    availability = message.get("availability", {}) or {}
    state = str(availability.get("state") or "")
    body = str(message.get("body") or "")
    source = str(message.get("source") or "")
    if body:
        if state == "summary_only" and not getattr(args, "allow_summary", False):
            fail(
                "Message only has an Apple Mail index summary; full body/source is unavailable",
                error="summary_only",
                extra={
                    "message_id": message.get("id"),
                    "availability": availability,
                    "hint": "Use --allow-summary to export the non-authoritative Mail index summary.",
                },
            )
        return body
    if source:
        return source
    fail(
        "Message content is unavailable; only metadata was found",
        error="metadata_only",
        extra={
            "message_id": message.get("id"),
            "availability": availability,
            "hydration": availability.get("hydration")
            or {
                "attempted": ["apple_mail_envelope_index"],
                "available": False,
                "next": "Configure a remote provider fallback or export/forward the message.",
            },
        },
    )


def message_headers_text(message: dict[str, Any]) -> str:
    headers = [
        ("Subject", message.get("subject", "")),
        ("From", message.get("from", "")),
        ("Date", message.get("date", "")),
        ("Account", message.get("account", "")),
        ("Mailbox", message.get("mailbox", "")),
        ("Message-ID", message.get("id", "")),
    ]
    return "\n".join(f"{name}: {normalize_text(value)}" for name, value in headers if normalize_text(value))


def render_text_export(message: dict[str, Any], args: argparse.Namespace) -> str:
    return f"{message_headers_text(message)}\n\n{message_text_for_export(message, args)}\n"


def render_html_export(message: dict[str, Any], args: argparse.Namespace) -> str:
    availability = message.get("availability", {}) or {}
    warning = ""
    if availability.get("state") == "summary_only":
        warning = "<p><strong>Availability:</strong> Apple Mail index summary only; full body/source is unavailable.</p>\n"
    rows = "\n".join(
        f"<tr><th>{html.escape(name)}</th><td>{html.escape(normalize_text(value))}</td></tr>"
        for name, value in [
            ("Subject", message.get("subject", "")),
            ("From", message.get("from", "")),
            ("Date", message.get("date", "")),
            ("Account", message.get("account", "")),
            ("Mailbox", message.get("mailbox", "")),
            ("Message ID", message.get("id", "")),
            ("Availability", availability.get("state", "")),
        ]
        if normalize_text(value)
    )
    text = html.escape(message_text_for_export(message, args))
    return (
        "<!doctype html>\n"
        "<html><head><meta charset=\"utf-8\"><title>Email Export</title>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;line-height:1.45;margin:32px;}"
        "table{border-collapse:collapse;margin-bottom:20px;}th{text-align:left;padding:4px 12px 4px 0;}"
        "td{padding:4px 0;}pre{white-space:pre-wrap;border-top:1px solid #ddd;padding-top:16px;}</style>"
        "</head><body>\n"
        "<h1>Email Export</h1>\n"
        f"{warning}<table>{rows}</table>\n"
        f"<pre>{text}</pre>\n"
        "</body></html>\n"
    )


def render_eml_export(message: dict[str, Any]) -> str:
    source = str(message.get("source") or "")
    if source.strip():
        return source
    fail(
        "Raw email source is unavailable for this message",
        error="source_unavailable",
        extra={"message_id": message.get("id"), "availability": message.get("availability", {})},
    )


def write_text_export(content: str, args: argparse.Namespace) -> str | None:
    output = normalize_text(getattr(args, "output", ""))
    if not output:
        return None
    path = Path(output).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def write_pdf_export(message: dict[str, Any], args: argparse.Namespace) -> str:
    output = normalize_text(getattr(args, "output", ""))
    if not output:
        fail("--output is required for pdf export", error="missing_output")
    textutil = shutil.which("textutil")
    if not textutil:
        fail("pdf export requires macOS textutil", error="pdf_unavailable")
    path = Path(output).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = Path(tmpdir) / "message.html"
        html_path.write_text(render_html_export(message, args), encoding="utf-8")
        proc = subprocess.run(
            [textutil, "-convert", "pdf", "-output", str(path), str(html_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        fail(proc.stderr.strip() or proc.stdout.strip() or "pdf export failed", error="pdf_export_failed")
    return str(path)


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
    all_mailboxes = source.mailboxes if isinstance(source, FixtureSource) else source.mailboxes()
    all_accounts = source.accounts if isinstance(source, FixtureSource) else source.accounts()
    selected = source.selected_mailboxes(args)
    messages = source.list_messages(selected, max(1, args.limit))
    counts = source.count_messages(selected)
    inbox_args = argparse.Namespace(account=getattr(args, "account", ""), mailbox="", all_mailboxes=False)
    inbox_selected = scope_mailboxes(all_mailboxes, inbox_args)
    inbox_counts = source.count_messages(inbox_selected)
    payload = {
        "ok": True,
        "platform": source.platform,
        "accounts": {"count": len(all_accounts), "items": all_accounts},
        "mailboxes": {"count": len(all_mailboxes), "items": all_mailboxes},
        "scope": scope_payload(args, selected),
        "message_count": counts[0],
        "unread_count": counts[1],
        "inbox_unread": inbox_counts[1],
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
    message = hydrate_remote_message(message)
    payload = {"ok": True, "message": project_message(message, include_source=True, include_attachments=True)}
    emit(payload, raw=json.dumps(project_message(message, include_source=True, include_attachments=True), indent=2))


def handle_export(source: FixtureSource | MacMailSource, args: argparse.Namespace) -> None:
    selected = source.selected_mailboxes(args)
    message = source.get_message(selected, args.message_id)
    if message is None:
        fail(
            "No email found for the requested message id",
            error="message_not_found",
            extra={"message_id": args.message_id, "scope": scope_payload(args, selected)},
        )
    message = hydrate_remote_message(message)

    export_format = normalize_key(args.format)
    content: str | None = None
    output_path: str | None = None
    if export_format == "json":
        content = json.dumps(project_message(message, include_source=True, include_attachments=True), indent=2) + "\n"
        output_path = write_text_export(content, args)
    elif export_format == "txt":
        content = render_text_export(message, args)
        output_path = write_text_export(content, args)
    elif export_format == "html":
        content = render_html_export(message, args)
        output_path = write_text_export(content, args)
    elif export_format == "eml":
        content = render_eml_export(message)
        output_path = write_text_export(content, args)
    elif export_format == "pdf":
        output_path = write_pdf_export(message, args)
    else:
        fail(f"unsupported export format: {args.format}", error="unsupported_format")

    payload = {
        "ok": True,
        "message": project_message(message),
        "export": {
            "format": export_format,
            "output": output_path or "",
            "summary_only": bool((message.get("availability") or {}).get("state") == "summary_only"),
        },
    }
    if OUTPUT_JSON:
        if output_path is None and content is not None:
            payload["content"] = content
        emit(payload)
    else:
        if output_path:
            print(output_path)
        elif content is not None:
            print(content, end="")


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


def handle_status(source: FixtureSource | MacMailSource, args: argparse.Namespace) -> None:
    payload: dict[str, Any] = {
        "ok": True,
        "platform": source.platform,
        "features": {
            "search_local_index": True,
            "get_exact_message": True,
            "export": True,
            "remote_hydration": True,
            "remote_body_search": False,
        },
        "provider": remote_provider_status(),
    }
    if isinstance(source, MacMailSource):
        payload["apple_mail"] = {
            "envelope_index": str(source.db_path),
            "source": "metadata_index",
        }
    else:
        payload["fixture"] = True
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
    parser = argparse.ArgumentParser(description="Query and export local Mail index messages.")
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

    export = sub.add_parser("export")
    export.add_argument("--id", dest="message_id", required=True)
    export.add_argument("--format", choices=["json", "txt", "html", "eml", "pdf"], default="html")
    export.add_argument("--output")
    export.add_argument("--allow-summary", action="store_true")
    add_scope_args(export)

    count = sub.add_parser("count")
    add_scope_args(count)

    mailboxes = sub.add_parser("mailboxes")
    mailboxes.add_argument("--account")

    sub.add_parser("status")

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
    elif args.command == "export":
        handle_export(source, args)
    elif args.command == "count":
        handle_count(source, args)
    elif args.command == "mailboxes":
        handle_mailboxes(source, args)
    elif args.command == "status":
        handle_status(source, args)
    else:
        fail("unknown command", error="unknown_command")


if __name__ == "__main__":
    main()
