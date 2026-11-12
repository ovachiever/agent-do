#!/usr/bin/env python3
"""A secret passed on the command line must never reach telemetry/events.jsonl.

Records real tool calls through lib/telemetry.record_tool_call (the function
agent-do calls before every tool run) in a throwaway AGENT_DO_HOME, then checks
the raw log bytes. No tool is executed and nothing touches the network.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET = "sk-test-DO-NOT-LOG-7f3a9c2e41b8"
PASSWORD = "pw-DO-NOT-LOG-91c4"

# (tool, args, text that must still be visible so the log stays useful)
CASES: list[tuple[str, list[str], list[str]]] = [
    ("render", ["env-set", "my-api", "OPENAI_API_KEY", SECRET], ["env-set", "my-api", "OPENAI_API_KEY"]),
    ("render", ["env-group", "set", "shared", "SESSION_SECRET", SECRET], ["env-group", "set", "shared", "SESSION_SECRET"]),
    ("render", ["create", "web", "my-api", "--env", f"OKTA_CLIENT_SECRET={SECRET}"], ["--env", "OKTA_CLIENT_SECRET="]),
    ("render", ["env-group", "create", "shared", "--env", f"DB={SECRET}"], ["--env", "DB="]),
    ("creds", ["store", "SENTRY_AUTH_TOKEN", SECRET], ["store", "SENTRY_AUTH_TOKEN"]),
    ("creds", ["store", "--stdin", "SENTRY_AUTH_TOKEN", SECRET], ["store", "SENTRY_AUTH_TOKEN"]),
    ("psql", ["connect", f"postgresql://app:{PASSWORD}@db.example.com:5432/app"], ["connect"]),
    ("psql", ["profile", "add", "prod", f"postgresql://app:{PASSWORD}@db.example.com/app"], ["profile", "add", "prod"]),
    ("vercel", ["env-set", "site", "API_KEY", SECRET, "--target", "prod"], ["env-set", "site", "API_KEY", "--target", "prod"]),
    ("vercel", ["env-set", "--target", "prod", "site", "API_KEY", SECRET], ["--target", "prod", "site", "API_KEY"]),
    ("supabase", ["secret-set", "abcd1234", "RESEND_KEY", SECRET], ["secret-set", "abcd1234", "RESEND_KEY"]),
    ("supabase", ["create", "app", "--org", "vid", "--db-pass", SECRET, "--yes"], ["--org", "vid", "--db-pass", "--yes"]),
    ("gcp", ["secret-set", "proj", "name", SECRET], ["secret-set", "proj", "name"]),
    # A value that starts with "-" is still the value.
    ("render", ["env-set", "my-api", "TOKEN_X", "-" + SECRET], ["env-set", "my-api", "TOKEN_X"]),
    ("creds", ["store", "KEY_X", "-" + SECRET], ["store", "KEY_X"]),
    # Generic URL-userinfo rule catches tools without a positional rule.
    ("gh", ["api", f"https://user:{PASSWORD}@example.com/x"], ["api"]),
]

# Calls that carry no secret must be recorded unchanged.
UNCHANGED: list[tuple[str, list[str]]] = [
    ("render", ["env", "my-api"]),
    ("psql", ["connect", "--profile", "palantir-db"]),
    ("creds", ["get", "SENTRY_AUTH_TOKEN", "--reveal"]),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def record(home: Path, tool: str, args: list[str]) -> None:
    env = os.environ.copy()
    env["AGENT_DO_HOME"] = str(home)
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "from telemetry import record_tool_call;"
        "record_tool_call(sys.argv[2], sys.argv[3:])"
    )
    result = subprocess.run(
        ["python3", "-c", code, str(ROOT / "lib"), tool, *args],
        env=env, text=True, capture_output=True, check=False,
    )
    require(result.returncode == 0, f"record_tool_call failed for {tool} {args[:1]}: {result.stderr}")


def last_event(log: Path) -> dict:
    lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    return json.loads(lines[-1])


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir) / "agent-home"
        log = home / "telemetry" / "events.jsonl"

        for tool, args, visible in CASES:
            record(home, tool, args)
            event = last_event(log)
            preview = event.get("command_preview", "")
            for text in visible:
                require(text in preview, f"{tool} {args[0]}: expected {text!r} to stay visible in {preview!r}")
            require("<redacted>" in preview, f"{tool} {args[0]}: no redaction marker in {preview!r}")

        for tool, args in UNCHANGED:
            record(home, tool, args)
            preview = last_event(log).get("command_preview", "")
            require(preview == " ".join(["agent-do", tool, *args]), f"{tool} {args}: changed to {preview!r}")

        raw = log.read_bytes()
        require(SECRET.encode() not in raw, "a secret value reached events.jsonl")
        require(PASSWORD.encode() not in raw, "a connection-string password reached events.jsonl")

    print("telemetry secret redaction tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
