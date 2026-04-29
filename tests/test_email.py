#!/usr/bin/env python3
"""Focused tests for agent-email query helpers."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def run(*args: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_envelope_index_fixture(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE mailboxes (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL);
        CREATE TABLE senders (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, contact_identifier TEXT, bucket INTEGER NOT NULL DEFAULT 0, user_initiated INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE sender_addresses (address INTEGER PRIMARY KEY, sender INTEGER NOT NULL);
        CREATE TABLE addresses (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, address TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '');
        CREATE TABLE subjects (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL);
        CREATE TABLE summaries (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, summary TEXT NOT NULL);
        CREATE TABLE messages (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL DEFAULT 0,
            global_message_id INTEGER NOT NULL DEFAULT 0,
            remote_id INTEGER,
            document_id TEXT,
            sender INTEGER,
            subject_prefix TEXT,
            subject INTEGER NOT NULL,
            summary INTEGER,
            date_sent INTEGER,
            date_received INTEGER,
            mailbox INTEGER NOT NULL,
            remote_mailbox INTEGER,
            flags INTEGER NOT NULL DEFAULT 0,
            read INTEGER NOT NULL DEFAULT 0,
            flagged INTEGER NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0,
            size INTEGER NOT NULL DEFAULT 0,
            conversation_id INTEGER NOT NULL DEFAULT 0,
            date_last_viewed INTEGER,
            list_id_hash INTEGER,
            unsubscribe_type INTEGER,
            searchable_message INTEGER,
            brand_indicator INTEGER,
            display_date INTEGER,
            flag_color INTEGER,
            is_urgent INTEGER NOT NULL DEFAULT 0,
            color TEXT,
            type INTEGER,
            fuzzy_ancestor INTEGER,
            automated_conversation INTEGER DEFAULT 0,
            root_status INTEGER DEFAULT -1
        );
        CREATE TABLE searchable_messages (message_id INTEGER PRIMARY KEY, message INTEGER, transaction_id INTEGER NOT NULL DEFAULT 0, message_body_indexed INTEGER NOT NULL DEFAULT 0, reindex_type INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE attachments (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, message INTEGER NOT NULL, attachment_id TEXT, name TEXT);
        """
    )
    conn.execute("INSERT INTO mailboxes (ROWID, url) VALUES (1, 'imap://primary/Inbox')")
    conn.execute("INSERT INTO senders (ROWID, contact_identifier) VALUES (10, 'sender-contact')")
    conn.execute("INSERT INTO addresses (ROWID, address, comment) VALUES (20, 'sender@example.com', '')")
    conn.execute("INSERT INTO sender_addresses (address, sender) VALUES (20, 10)")
    conn.execute("INSERT INTO subjects (ROWID, subject) VALUES (30, 'Indexed invoice')")
    conn.execute("INSERT INTO summaries (ROWID, summary) VALUES (40, 'Invoice summary contains 731902')")
    conn.execute(
        """
        INSERT INTO messages (ROWID, message_id, global_message_id, sender, subject, summary, date_received, mailbox, read, deleted)
        VALUES (100, 9001, 9001, 10, 30, 40, 1770000000, 1, 0, 0)
        """
    )
    conn.execute("INSERT INTO searchable_messages (message_id, message, message_body_indexed) VALUES (100, 100, 1)")
    conn.execute("INSERT INTO attachments (message, attachment_id, name) VALUES (100, 'att-1', 'invoice.pdf')")
    conn.commit()
    conn.close()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fixture = tmp / "mail.json"
        fixture.write_text(
            json.dumps(
                {
                    "platform": "fixture",
                    "accounts": {
                        "count": 2,
                        "items": [
                            {"name": "Primary", "type": "IMAP"},
                            {"name": "Work", "type": "Exchange"},
                        ],
                    },
                    "mailboxes": {
                        "count": 3,
                        "items": [
                            {"account": "Primary", "mailbox": "Inbox"},
                            {"account": "Primary", "mailbox": "Archive"},
                            {"account": "Work", "mailbox": "Inbox"},
                        ],
                    },
                    "messages": [
                        {
                            "id": "msg-metadata",
                            "account": "Work",
                            "mailbox": "Inbox",
                            "subject": "Your WidgetHub verification code",
                            "from": "WidgetHub <login@widgethub.com>",
                            "status": "unread",
                            "date": "2026-04-12T12:02:00Z",
                            "body": "",
                            "source": "",
                            "attachments": [],
                        },
                        {
                            "id": "msg-magic",
                            "account": "Primary",
                            "mailbox": "Inbox",
                            "subject": "Your WidgetHub magic link",
                            "from": "WidgetHub <login@widgethub.com>",
                            "status": "unread",
                            "date": "2026-04-12T12:01:00Z",
                            "body": "Click https://app.example.com/magic?token=abc123 to sign in.",
                            "source": "From: login@widgethub.com",
                        },
                        {
                            "id": "msg-code",
                            "account": "Primary",
                            "mailbox": "Inbox",
                            "subject": "Your WidgetHub verification code",
                            "from": "WidgetHub <login@widgethub.com>",
                            "status": "unread",
                            "date": "2026-04-12T12:00:00Z",
                            "body": "Your verification code is 731902.",
                            "source": "From: login@widgethub.com",
                            "attachments": [{"name": "code.txt", "mime_type": "text/plain"}],
                        },
                        {
                            "id": "msg-archive",
                            "account": "Primary",
                            "mailbox": "Archive",
                            "subject": "Archived invoice",
                            "from": "Billing <billing@example.com>",
                            "status": "read",
                            "date": "2026-04-12T11:00:00Z",
                            "body": "Invoice 2026 is ready for review.",
                            "source": "From: billing@example.com",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["AGENT_EMAIL_FIXTURE"] = str(fixture)

        snapshot = run(str(AGENT_DO), "email", "snapshot", "--json", cwd=ROOT, env=env)
        require(snapshot.returncode == 0, f"email snapshot failed: {snapshot.stderr}")
        snapshot_payload = json.loads(snapshot.stdout)
        require(snapshot_payload["unread_count"] == 3, f"unexpected snapshot payload: {snapshot_payload}")
        require(snapshot_payload["scope"]["mode"] == "inbox", f"unexpected snapshot scope: {snapshot_payload}")
        require(snapshot_payload["recent_messages"]["items"][0]["id"] == "msg-metadata", f"unexpected snapshot messages: {snapshot_payload}")

        latest = run(
            str(AGENT_DO),
            "email",
            "latest",
            "--from",
            "widgethub",
            "--account",
            "Primary",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(latest.returncode == 0, f"email latest failed: {latest.stderr}")
        latest_payload = json.loads(latest.stdout)
        require(latest_payload["message"]["id"] == "msg-magic", f"unexpected latest payload: {latest_payload}")

        search = run(
            str(AGENT_DO),
            "email",
            "search",
            "invoice",
            "--all-mailboxes",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(search.returncode == 0, f"email search failed: {search.stderr}")
        search_payload = json.loads(search.stdout)
        require(search_payload["messages"]["count"] == 1, f"unexpected search payload: {search_payload}")
        require(search_payload["messages"]["items"][0]["id"] == "msg-archive", f"unexpected search match: {search_payload}")

        mailboxes = run(str(AGENT_DO), "email", "mailboxes", "--json", cwd=ROOT, env=env)
        require(mailboxes.returncode == 0, f"email mailboxes failed: {mailboxes.stderr}")
        mailboxes_payload = json.loads(mailboxes.stdout)
        require(mailboxes_payload["mailboxes"]["count"] == 3, f"unexpected mailboxes payload: {mailboxes_payload}")

        count = run(str(AGENT_DO), "email", "count", "--all-mailboxes", "--json", cwd=ROOT, env=env)
        require(count.returncode == 0, f"email count failed: {count.stderr}")
        count_payload = json.loads(count.stdout)
        require(count_payload["message_count"] == 4, f"unexpected count payload: {count_payload}")
        require(count_payload["unread_count"] == 3, f"unexpected unread count payload: {count_payload}")

        get_message = run(
            str(AGENT_DO),
            "email",
            "get",
            "--id",
            "msg-code",
            "--account",
            "Primary",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(get_message.returncode == 0, f"email get failed: {get_message.stderr}")
        get_payload = json.loads(get_message.stdout)
        require(get_payload["message"]["availability"]["source_available"] is True, f"unexpected get payload: {get_payload}")
        require(get_payload["message"]["availability"]["state"] == "raw_source", f"unexpected get state: {get_payload}")
        require("eml" in get_payload["message"]["availability"]["export_formats"], f"unexpected export formats: {get_payload}")
        require(get_payload["message"]["attachments"][0]["name"] == "code.txt", f"unexpected attachments payload: {get_payload}")

        export_html_path = tmp / "archive.html"
        export_html = run(
            str(AGENT_DO),
            "email",
            "export",
            "--id",
            "msg-archive",
            "--all-mailboxes",
            "--format",
            "html",
            "--output",
            str(export_html_path),
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(export_html.returncode == 0, f"email html export failed: {export_html.stderr}")
        export_payload = json.loads(export_html.stdout)
        require(export_payload["export"]["output"] == str(export_html_path), f"unexpected export payload: {export_payload}")
        require("Archived invoice" in export_html_path.read_text(encoding="utf-8"), "exported html missing subject")

        export_eml = run(
            str(AGENT_DO),
            "email",
            "export",
            "--id",
            "msg-code",
            "--account",
            "Primary",
            "--format",
            "eml",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(export_eml.returncode == 0, f"email eml export failed: {export_eml.stderr}")
        export_eml_payload = json.loads(export_eml.stdout)
        require("From: login@widgethub.com" in export_eml_payload["content"], f"unexpected eml export: {export_eml_payload}")

        code = run(
            str(AGENT_DO),
            "email",
            "code",
            "--from",
            "widgethub",
            "--subject",
            "verification code",
            "--account",
            "Primary",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(code.returncode == 0, f"email code failed: {code.stderr}")
        code_payload = json.loads(code.stdout)
        require(code_payload["code"] == "731902", f"unexpected code payload: {code_payload}")

        metadata_only = run(
            str(AGENT_DO),
            "email",
            "code",
            "--from",
            "widgethub",
            "--account",
            "Work",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(metadata_only.returncode != 0, "expected metadata-only code lookup to fail")
        metadata_payload = json.loads(metadata_only.stdout)
        require(metadata_payload["error"] == "metadata_only", f"unexpected metadata-only payload: {metadata_payload}")
        require(metadata_payload["message_id"] == "msg-metadata", f"unexpected metadata-only id: {metadata_payload}")

        export_metadata = run(
            str(AGENT_DO),
            "email",
            "export",
            "--id",
            "msg-metadata",
            "--account",
            "Work",
            "--format",
            "html",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(export_metadata.returncode != 0, "expected metadata-only export to fail")
        export_metadata_payload = json.loads(export_metadata.stdout)
        require(export_metadata_payload["error"] == "metadata_only", f"unexpected metadata export payload: {export_metadata_payload}")

        code_excluding = run(
            str(AGENT_DO),
            "email",
            "code",
            "--from",
            "widgethub",
            "--subject",
            "verification code",
            "--account",
            "Primary",
            "--exclude-id",
            "msg-code",
            "--timeout",
            "1",
            "--interval",
            "1",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(code_excluding.returncode != 0, "expected excluded code lookup to fail when only stale message remains")
        exclude_payload = json.loads(code_excluding.stdout)
        require(exclude_payload["error"] == "timeout", f"unexpected excluded code payload: {exclude_payload}")

        link = run(
            str(AGENT_DO),
            "email",
            "link",
            "--from",
            "widgethub",
            "--account",
            "Primary",
            "--domain",
            "app.example.com",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(link.returncode == 0, f"email link failed: {link.stderr}")
        link_payload = json.loads(link.stdout)
        require(
            link_payload["link"] == "https://app.example.com/magic?token=abc123",
            f"unexpected link payload: {link_payload}",
        )

        send_env = os.environ.copy()
        send_env.pop("SMTP_USER", None)
        send_env.pop("SMTP_PASS", None)
        injection = run(
            str(AGENT_DO),
            "email",
            "send",
            "recipient@example.com",
            "Subject",
            "--method",
            "smtp",
            "--from",
            '"; print("AGENT_EMAIL_INJECTION_PROOF"); x="',
            cwd=ROOT,
            env=send_env,
        )
        require(injection.returncode != 0, "expected smtp send without credentials to fail")
        require(
            "AGENT_EMAIL_INJECTION_PROOF" not in f"{injection.stdout}\n{injection.stderr}",
            f"send path executed interpolated input: {injection.stdout} {injection.stderr}",
        )

        envelope_index = tmp / "Envelope Index"
        write_envelope_index_fixture(envelope_index)
        live_env = os.environ.copy()
        live_env.pop("AGENT_EMAIL_FIXTURE", None)
        live_env["AGENT_EMAIL_ENVELOPE_INDEX"] = str(envelope_index)
        live_search = run(
            str(AGENT_DO),
            "email",
            "search",
            "invoice",
            "--from",
            "sender@example.com",
            "--all-mailboxes",
            "--json",
            cwd=ROOT,
            env=live_env,
        )
        require(live_search.returncode == 0, f"envelope index search failed: {live_search.stderr}")
        live_payload = json.loads(live_search.stdout)
        require(live_payload["messages"]["count"] == 1, f"unexpected live search payload: {live_payload}")
        live_message = live_payload["messages"]["items"][0]
        require(live_message["from"] == "sender@example.com", f"sender join failed: {live_payload}")
        require(live_message["availability"]["state"] == "summary_only", f"unexpected live availability: {live_payload}")
        require(live_message["availability"]["body_is_full"] is False, f"expected summary-only body: {live_payload}")

        summary_export = run(
            str(AGENT_DO),
            "email",
            "export",
            "--id",
            "db:100",
            "--all-mailboxes",
            "--format",
            "html",
            "--json",
            cwd=ROOT,
            env=live_env,
        )
        require(summary_export.returncode != 0, "expected summary-only export without opt-in to fail")
        summary_payload = json.loads(summary_export.stdout)
        require(summary_payload["error"] == "summary_only", f"unexpected summary-only payload: {summary_payload}")

        summary_html_path = tmp / "summary.html"
        summary_export_allowed = run(
            str(AGENT_DO),
            "email",
            "export",
            "--id",
            "db:100",
            "--all-mailboxes",
            "--format",
            "html",
            "--allow-summary",
            "--output",
            str(summary_html_path),
            "--json",
            cwd=ROOT,
            env=live_env,
        )
        require(summary_export_allowed.returncode == 0, f"summary export failed: {summary_export_allowed.stderr}")
        require("Apple Mail index summary only" in summary_html_path.read_text(encoding="utf-8"), "summary export missing warning")

    print("email tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
