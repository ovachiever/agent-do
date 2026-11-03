#!/usr/bin/env python3
"""betterstack incidents: a date window, every page on request, and a hint when more exist.

`incidents` returned the API's first page (10) with no sign that more
existed, and had no time filter (D68). The API call is stubbed.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def page(ids, nxt):
    return json.dumps({"data": [{"id": str(i), "attributes": {"name": f"m{i}", "status": "Resolved",
                                                              "started_at": "2026-11-03T08:00:00Z"}} for i in ids],
                       "pagination": {"next": nxt}})


def run(cmd: str, calls: Path) -> subprocess.CompletedProcess[str]:
    p1 = page(range(1, 4), "https://uptime.betterstack.com/api/v3/incidents?page=2&per_page=50").replace("'", "")
    p2 = page(range(4, 6), None).replace("'", "")
    script = f"""
set -uo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-betterstack'}")
bs_get() {{
  printf '%s\\n' "$1" >> "{calls}"
  case "$1" in *page=2*) printf '%s' '{p2}' ;; *) printf '%s' '{p1}' ;; esac
}}
{cmd}
"""
    return subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True)


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        calls = Path(tmp) / "calls"

        r = run("cmd_incidents --since 2026-10-01 --until 2026-11-03", calls)
        require(r.returncode == 0, r.stderr)
        require(calls.read_text().splitlines()[-1].endswith("/incidents?from=2026-10-01&to=2026-11-03"),
                f"window query: {calls.read_text()}")
        require("more incidents exist" in r.stderr and r.stdout.count("m") >= 3, f"first page + hint: {r.stderr!r}")

        calls.unlink()
        r = run("cmd_incidents --all --json", calls)
        lines = calls.read_text().splitlines()
        require(len(lines) == 2 and "per_page=50" in lines[0] and "page=2" in lines[1], f"pages fetched: {lines}")
        require([d["id"] for d in json.loads(r.stdout)["data"]] == ["1", "2", "3", "4", "5"], r.stdout[:300])

        r = run("cmd_incidents --since 7d", calls)
        require("from=20" in calls.read_text().splitlines()[-1], "Nd becomes a date")

        r = run("cmd_incidents --since yesterday || echo rc=$?", calls)
        require("rc=2" in r.stdout, f"bad date must exit 2: {r.stdout!r}")

    print("betterstack incidents window tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
