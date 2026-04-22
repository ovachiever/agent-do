#!/usr/bin/env python3
"""Focused coverage for the root notify contract."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_exec(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        stub = tmp_path / "agent-do-provider-stub"
        log_path = tmp_path / "notify-calls.jsonl"

        make_exec(
            stub,
            """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

log_path = Path(os.environ["NOTIFY_TEST_LOG"])
entry = {"argv": sys.argv[1:]}
with log_path.open("a") as f:
    f.write(json.dumps(entry) + "\\n")

provider = sys.argv[1]
fail = {item for item in os.environ.get("NOTIFY_TEST_FAIL", "").split(",") if item}
if provider in fail:
    print(f"{provider} failed", file=sys.stderr)
    raise SystemExit(1)

print(f"{provider} sent")
""",
        )

        env = dict(os.environ)
        env["AGENT_DO_HOME"] = str(fake_home)
        env["AGENT_DO_NOTIFY_AGENT_DO"] = str(stub)
        env["NOTIFY_TEST_LOG"] = str(log_path)

        help_result = run([str(AGENT_DO), "notify", "--help"], env=env)
        require(help_result.returncode == 0, f"notify help failed: {help_result.stderr}")
        require("Cross-provider notification contract" in help_result.stdout, f"unexpected notify help: {help_result.stdout}")

        providers = run([str(AGENT_DO), "notify", "providers", "--json"], env=env)
        require(providers.returncode == 0, f"notify providers failed: {providers.stderr}")
        providers_payload = json.loads(providers.stdout)
        require(
            [item["provider"] for item in providers_payload["providers"]] == ["email", "messenger", "pipe", "slack", "sms"],
            f"unexpected providers payload: {providers_payload}",
        )

        save = run(
            [
                str(AGENT_DO),
                "notify",
                "set-recipient",
                "me",
                "--sms",
                "+15551234567",
                "--email",
                "me@example.com",
                "--slack",
                "@erik",
                "--messenger",
                "https://www.messenger.com/t/example-thread",
                "--pipe",
                "cat >/tmp/notify.out",
                "--prefer",
                "sms,email,slack",
                "--subject",
                "Ops alert",
                "--json",
            ],
            env=env,
        )
        require(save.returncode == 0, f"set-recipient failed: {save.stderr}")
        save_payload = json.loads(save.stdout)
        require(save_payload["recipient"]["sms"] == "+15551234567", f"unexpected save payload: {save_payload}")
        require(save_payload["recipient"]["messenger"] == "https://www.messenger.com/t/example-thread", f"unexpected save payload: {save_payload}")

        recipients = run([str(AGENT_DO), "notify", "recipients", "--json"], env=env)
        require(recipients.returncode == 0, f"notify recipients failed: {recipients.stderr}")
        recipients_payload = json.loads(recipients.stdout)
        require(recipients_payload["recipients"][0]["alias"] == "me", f"unexpected recipients payload: {recipients_payload}")

        dry_run = run([str(AGENT_DO), "notify", "me", "Build complete", "--dry-run", "--json"], env=env)
        require(dry_run.returncode == 0, f"notify dry-run failed: {dry_run.stderr}")
        dry_run_payload = json.loads(dry_run.stdout)
        require(dry_run_payload["dry_run"] is True, f"unexpected dry-run payload: {dry_run_payload}")
        require(dry_run_payload["attempts"][0]["provider"] == "sms", f"unexpected dry-run attempt order: {dry_run_payload}")

        sent = run([str(AGENT_DO), "notify", "me", "Build complete", "--json"], env=env)
        require(sent.returncode == 0, f"notify send failed: {sent.stderr}")
        sent_payload = json.loads(sent.stdout)
        require(sent_payload["success"] is True, f"unexpected notify send payload: {sent_payload}")
        require(sent_payload["attempts"][0]["provider"] == "sms", f"unexpected notify send attempt: {sent_payload}")

        env["NOTIFY_TEST_FAIL"] = "sms"
        fallback = run([str(AGENT_DO), "notify", "me", "Need backup", "--json"], env=env)
        require(fallback.returncode == 0, f"notify fallback failed: {fallback.stderr}")
        fallback_payload = json.loads(fallback.stdout)
        require(len(fallback_payload["attempts"]) == 2, f"expected fallback attempts: {fallback_payload}")
        require(
            [attempt["provider"] for attempt in fallback_payload["attempts"]] == ["sms", "email"],
            f"unexpected fallback order: {fallback_payload}",
        )
        require(fallback_payload["attempts"][1]["success"] is True, f"expected email fallback success: {fallback_payload}")

        messenger_denied = run([str(AGENT_DO), "notify", "me", "Ping", "--via", "messenger", "--json"], env=env)
        require(messenger_denied.returncode == 1, f"expected messenger live approval failure: {messenger_denied.stdout} {messenger_denied.stderr}")
        messenger_denied_payload = json.loads(messenger_denied.stdout)
        require(messenger_denied_payload["action_required"] == "LIVE_APPROVAL_REQUIRED", f"unexpected messenger denied payload: {messenger_denied_payload}")
        require("notify" in messenger_denied_payload["rerun"], f"expected notify rerun hint: {messenger_denied_payload}")

        env["AGENT_DO_NOTIFY_MESSENGER_TEST_MODE"] = "1"
        messenger_live = run(
            [
                str(AGENT_DO),
                '+live(scope=desktop,app=Messenger,ttl=15m,reason="notify:messenger")',
                "notify",
                "me",
                "Ping",
                "--via",
                "messenger",
                "--json",
            ],
            env=env,
        )
        require(messenger_live.returncode == 0, f"messenger live send failed: {messenger_live.stderr}")
        messenger_live_payload = json.loads(messenger_live.stdout)
        require(messenger_live_payload["success"] is True, f"unexpected messenger live payload: {messenger_live_payload}")
        require(messenger_live_payload["attempts"][0]["provider"] == "messenger", f"unexpected messenger attempt payload: {messenger_live_payload}")

    print("notify tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
