#!/usr/bin/env python3
"""A failed bootstrap opens a blocking dialog only when a person answered the prompt.

With AGENT_DO_BOOTSTRAP_AUTO_RESPONSE set (tests, CI, headless lanes) nobody is
at the screen, so a failure must report through a notification and stderr and
never open `display dialog` — that dialog blocked test runs for 10+ minutes.
Both session-start hooks (Claude, Codex) are exercised against stub
`agent-do` and `osascript` executables, so nothing real runs or appears.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HOOKS = [
    ["bash", str(ROOT / "hooks/claude/agent-do-session-start.sh")],
    [sys.executable, str(ROOT / "hooks/codex/agent-do-session-start.py")],
]

STUB_AGENT_DO = """#!/bin/bash
case "$*" in
  "bootstrap --recommend --json --cwd "*)
    printf '{"needs_bootstrap":true,"ask_prompt":"Bootstrap this project?","project_root":"%s","commands":["agent-do zpc init"]}\\n' "$5"
    ;;
  "bootstrap --yes")
    echo "simulated bootstrap failure" >&2
    exit 3
    ;;
esac
exit 0
"""

# Records every call; answers "Bootstrap" to the first-run prompt the way a
# person clicking the default button would.
STUB_OSASCRIPT = """#!/bin/bash
input="$*"
if [ ! -t 0 ]; then input="$input $(cat)"; fi
printf '%s\\n---\\n' "$input" >> "$OSASCRIPT_LOG"
case "$input" in
  *'buttons {"Not now", "Bootstrap"}'*) echo "Bootstrap" ;;
  *'buttons {"Dismiss", "Open log"}'*) echo "Dismiss" ;;
esac
exit 0
"""


def write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def run_hook(hook: list[str], auto_response: str | None) -> tuple[subprocess.CompletedProcess, str]:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        stub = tmpdir / "bin"
        stub.mkdir()
        write_exec(stub / "agent-do", STUB_AGENT_DO)
        write_exec(stub / "osascript", STUB_OSASCRIPT)
        project = tmpdir / "project"
        project.mkdir()
        home = tmpdir / "home"
        home.mkdir()
        log = tmpdir / "osascript.log"
        log.touch()

        env = {
            "PATH": f"{stub}:{os.environ.get('PATH', '')}",
            "HOME": str(home),
            "AGENT_DO_HOME": str(home / ".agent-do"),
            "AGENT_DO_BOOTSTRAP_PROMPT_MODE": "native",
            "OSASCRIPT_LOG": str(log),
        }
        if auto_response:
            env["AGENT_DO_BOOTSTRAP_AUTO_RESPONSE"] = auto_response
        result = subprocess.run(
            hook,
            input=json.dumps({"cwd": str(project)}),
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        return result, log.read_text(encoding="utf-8")


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def main() -> int:
    for hook in HOOKS:
        name = Path(hook[1]).parent.name

        result, calls = run_hook(hook, "bootstrap")
        require(result.returncode == 0, f"{name}: hook exited {result.returncode}: {result.stderr}")
        require("display notification" in calls, f"{name}: expected a failure notification, got: {calls!r}")
        require("display dialog" not in calls, f"{name}: auto-response run must never open a dialog, got: {calls!r}")
        require("FAILED" in result.stderr, f"{name}: expected the failure on stderr, got: {result.stderr!r}")
        json.loads(result.stdout)  # stdout stays the hook's JSON payload

        result, calls = run_hook(hook, None)
        require(result.returncode == 0, f"{name}: hook exited {result.returncode}: {result.stderr}")
        require(
            calls.count("display dialog") == 2,
            f"{name}: a person who clicked Bootstrap should still be offered the log, got: {calls!r}",
        )
        print(f"  ok {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
