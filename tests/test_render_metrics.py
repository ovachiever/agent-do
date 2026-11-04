#!/usr/bin/env python3
"""agent-render metrics: the real endpoint, a readable series view, honest errors.

The old verb called /v1/services/<id>/metrics/<type>, which does not exist
(Render answers "404 page not found" as text), then crashed parsing it:
"Extra data: line 1 column 5". It also treated `--help` as a service name.
These checks run the tool's own functions with the HTTP call replaced, so no
key or network is used.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = (
    '[{"labels":[{"field":"service","value":"srv-test"},{"field":"resource","value":"srv-test"},'
    '{"field":"instance","value":"srv-test-abc12"}],"unit":"bytes",'
    '"values":[{"timestamp":"2026-11-03T22:00:00Z","value":314572800}]}]'
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(body: str, capture: Path) -> subprocess.CompletedProcess[str]:
    script = f"""
set -uo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
resolve_service() {{ [[ "$1" == "my-svc" ]] && echo "srv-test" || return 1; }}
resolve_postgres() {{ [[ "$1" == "my-db" ]] && echo "dpg-test" || return 1; }}
resolve_kv() {{ [[ "$1" == "my-cache" ]] && echo "red-test" || return 1; }}
render_get_or_fail() {{
  printf '%s\\n' "$1" >> "{capture}"
  case "$1" in
    /metrics/bogus*) echo "Error: HTTP 400: invalid metric name bogus" >&2; return 1 ;;
    /metrics/disk-usage*) echo '[]' ;;
    *) printf '%s' '{FIXTURE}' ;;
  esac
}}
{body}
"""
    return subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        capture = Path(tmp) / "calls.txt"

        r = run("cmd_metrics --help", capture)
        require(r.returncode == 0 and "Usage: agent-render metrics" in r.stdout, f"--help: {r.stdout!r} {r.stderr!r}")
        require(not capture.exists(), "--help must not call the API")

        r = run("cmd_metrics my-svc --type memory --since 30m", capture)
        require(r.returncode == 0, f"memory failed: {r.stderr}")
        call = capture.read_text().splitlines()[-1]
        require(call.startswith("/metrics/memory?resource=srv-test&startTime="), f"wrong endpoint: {call}")
        require("&endTime=" in call and call.endswith("&resolutionSeconds=60"), f"wrong window: {call}")
        require("T" in call.split("startTime=")[1][:20], f"startTime must be ISO 8601: {call}")
        require("instance=srv-test-abc12" in r.stdout and "300.0 MiB" in r.stdout, f"series view: {r.stdout!r}")

        r = run("cmd_metrics my-db --type disk-usage", capture)
        require(r.returncode == 0 and "resource=dpg-test" in capture.read_text().splitlines()[-1], "Postgres by name")
        require("no data in this window" in r.stdout, f"empty series must say so: {r.stdout!r}")

        r = run("cmd_metrics my-cache --type memory", capture)
        require(r.returncode == 0 and "resource=red-test" in capture.read_text().splitlines()[-1], "Key Value by name")

        r = run("cmd_metrics srv-test --type bogus", capture)
        require(r.returncode == 1 and "invalid metric name bogus" in r.stderr, f"API reason must surface: {r.stderr!r}")

        r = run("RENDER_JSON=1 cmd_metrics srv-test", capture)
        require(r.returncode == 0 and r.stdout.strip() == FIXTURE, f"--json passthrough: {r.stdout!r}")

        for args, code in (("--frob srv-test", 2), ("srv-test --since yesterday", 2), ("nope-svc", 1), ("", 2)):
            r = run(f"cmd_metrics {args}", capture)
            require(r.returncode == code, f"cmd_metrics {args!r}: expected exit {code}, got {r.returncode} {r.stderr!r}")

    print("render metrics tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
