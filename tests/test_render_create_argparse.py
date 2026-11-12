#!/usr/bin/env python3
"""agent-render: write-side `create` verbs must never take a flag as the name.

`kv create --help` once POSTed a Key Value instance named "--help" (a real
instance was created and had to be deleted). Every create branch parsed
"first unknown positional = name" with no guard for '-'-prefixed tokens.
Here every create branch runs with a stubbed render_request that fails the
test if any POST is attempted.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(cmd: str) -> subprocess.CompletedProcess[str]:
    script = f"""
set -uo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
default_owner_id() {{ echo "tea-test"; }}
resolve_owner() {{ echo "tea-test"; }}
render_request() {{ echo "FORBIDDEN_API_CALL $1 $2" >&2; exit 99; }}
render_request_checked() {{ echo "FORBIDDEN_API_CALL $1 $2" >&2; exit 99; }}
{cmd}
"""
    return subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False)


CASES = [
    "cmd_db_create",
    "cmd_kv create",
    "cmd_env_group create",
    "cmd_project create",
    "cmd_environment create",
]


def main() -> int:
    for base in CASES:
        for flag in ("--help", "-h"):
            r = run(f"{base} {flag}")
            require("FORBIDDEN_API_CALL" not in r.stderr, f"{base} {flag} reached the API: {r.stderr}")
            require(r.returncode == 0, f"{base} {flag} should exit 0 with usage, got {r.returncode}: {r.stderr}")
            require("Usage:" in r.stdout, f"{base} {flag} did not print usage: {r.stdout}")
        r = run(f"{base} --not-a-real-flag")
        require("FORBIDDEN_API_CALL" not in r.stderr, f"{base} --not-a-real-flag reached the API: {r.stderr}")
        require(r.returncode == 1, f"{base} unknown flag should exit 1, got {r.returncode}")
        require("unknown option '--not-a-real-flag'" in r.stderr, f"{base} unknown flag message: {r.stderr}")
        # An unknown flag placed after a valid name must also refuse, not silently drop.
        r = run(f"{base} valid-name --not-a-real-flag")
        require("FORBIDDEN_API_CALL" not in r.stderr, f"{base} name+bad flag reached the API: {r.stderr}")
        require(r.returncode == 1, f"{base} name+bad flag should exit 1, got {r.returncode}")

    print("render create argparse tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
