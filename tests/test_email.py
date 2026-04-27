#!/usr/bin/env python3
"""Focused tests for agent-email query helpers."""

from __future__ import annotations

import json
import os
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
        require(get_payload["message"]["attachments"][0]["name"] == "code.txt", f"unexpected attachments payload: {get_payload}")

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

    print("email tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
