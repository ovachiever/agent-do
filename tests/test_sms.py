#!/usr/bin/env python3
"""Focused tests for agent-sms query helpers."""

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
        fixture = tmp / "sms.json"
        fixture.write_text(
            json.dumps(
                {
                    "platform": "fixture",
                    "unread_count": 2,
                    "messages": [
                        {
                            "id": "msg-link",
                            "contact": "WidgetHub",
                            "status": "unread",
                            "date": "2026-04-12T12:01:00Z",
                            "text": "Tap https://app.example.com/magic?token=abc123 to sign in.",
                        },
                        {
                            "id": "msg-code",
                            "contact": "WidgetHub",
                            "status": "unread",
                            "date": "2026-04-12T12:00:00Z",
                            "text": "Your WidgetHub verification code is 482911.",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["AGENT_SMS_FIXTURE"] = str(fixture)

        snapshot = run(str(AGENT_DO), "sms", "snapshot", "--json", cwd=ROOT, env=env)
        require(snapshot.returncode == 0, f"sms snapshot failed: {snapshot.stderr}")
        snapshot_payload = json.loads(snapshot.stdout)
        require(snapshot_payload["unread_count"] == 2, f"unexpected snapshot payload: {snapshot_payload}")

        latest = run(str(AGENT_DO), "sms", "latest", "--from", "widgethub", "--json", cwd=ROOT, env=env)
        require(latest.returncode == 0, f"sms latest failed: {latest.stderr}")
        latest_payload = json.loads(latest.stdout)
        require(latest_payload["message"]["id"] == "msg-link", f"unexpected latest payload: {latest_payload}")

        code = run(
            str(AGENT_DO),
            "sms",
            "code",
            "--from",
            "widgethub",
            "--contains",
            "verification",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(code.returncode == 0, f"sms code failed: {code.stderr}")
        code_payload = json.loads(code.stdout)
        require(code_payload["code"] == "482911", f"unexpected code payload: {code_payload}")

        code_excluding = run(
            str(AGENT_DO),
            "sms",
            "code",
            "--from",
            "widgethub",
            "--contains",
            "verification",
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

        link = run(
            str(AGENT_DO),
            "sms",
            "link",
            "--from",
            "widgethub",
            "--domain",
            "app.example.com",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(link.returncode == 0, f"sms link failed: {link.stderr}")
        link_payload = json.loads(link.stdout)
        require(
            link_payload["link"] == "https://app.example.com/magic?token=abc123",
            f"unexpected link payload: {link_payload}",
        )

    print("sms tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
