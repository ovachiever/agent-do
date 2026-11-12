#!/usr/bin/env python3
"""agent-render resolve_service: srv-* and crn-* are both already-resolved IDs
and must never trigger a name lookup; anything else resolves by name."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(arg: str) -> subprocess.CompletedProcess[str]:
    script = f"""
set -uo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
render_request() {{
  echo "LOOKUP $2" >&2
  case "$2" in
    "/services?name=my-cron&limit=1") printf '%s\\n' '[{{"service":{{"id":"crn-fromname","name":"my-cron"}}}}]' ;;
    *) printf '%s\\n' '[]' ;;
  esac
}}
resolve_service "{arg}"
"""
    return subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    for ident in ("srv-abc123", "crn-abc123"):
        r = run(ident)
        require(r.returncode == 0, f"{ident} should resolve: {r.stderr}")
        require(r.stdout.strip() == ident, f"{ident} should pass through unchanged, got {r.stdout!r}")
        require("LOOKUP" not in r.stderr, f"{ident} triggered a name lookup: {r.stderr}")

    r = run("my-cron")
    require(r.returncode == 0, f"name lookup failed: {r.stderr}")
    require(r.stdout.strip() == "crn-fromname", f"name should resolve to the cron id, got {r.stdout!r}")
    require("LOOKUP /services?name=my-cron" in r.stderr, f"expected a name lookup: {r.stderr}")

    r = run("no-such-service")
    require(r.returncode == 1, f"unknown name should fail, got {r.returncode}")
    require("not found" in r.stderr, f"expected not-found error: {r.stderr}")

    print("render resolve tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
