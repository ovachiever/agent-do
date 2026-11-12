#!/usr/bin/env python3
"""agent-render db allowlist: list, add, remove, dry-run, guards and read-back.

Runs the real cmd_db_allowlist against a stubbed Render API (full-list
replacement on PATCH, like the real endpoint), so no network or key is needed.
Every API call is logged so the tests can prove what was and was not sent.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INITIAL = [
    {"cidrBlock": "203.0.113.10/32", "description": "office"},
    {"cidrBlock": "198.51.100.0/24", "description": "vpn range"},
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(args: str, state: Path, log: Path, mode: str = "ok", render_json: str = "0") -> subprocess.CompletedProcess[str]:
    script = f"""
set -euo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
resolve_postgres() {{ echo "dpg-test"; }}
render_request_checked() {{
  echo "$1 $2" >> "{log}"
  case "$1 $2" in
    "GET /postgres/dpg-test")
      python3 -c 'import json,sys; print(json.dumps({{"id":"dpg-test","name":"test-db","ipAllowList":json.load(open(sys.argv[1]))}}))' "{state}" ;;
    "PATCH /postgres/dpg-test")
      if [[ "{mode}" == "mismatch" ]]; then
        echo '[{{"cidrBlock":"192.0.2.99/32","description":"someone else"}}]' > "{state}"
      else
        printf '%s' "$3" | python3 -c 'import json,sys; json.dump(json.load(sys.stdin)["ipAllowList"], open(sys.argv[1],"w"))' "{state}"
      fi
      echo '{{}}' ;;
    *) echo "unexpected: $1 $2" >&2; return 1 ;;
  esac
}}
RENDER_JSON={render_json}
cmd_db_allowlist {args}
"""
    return subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False)


def fresh(tmp: Path) -> tuple[Path, Path]:
    state = tmp / "state.json"
    state.write_text(json.dumps(INITIAL))
    log = tmp / "calls.log"
    log.write_text("")
    return state, log


def cidrs(state: Path) -> list[str]:
    return [e["cidrBlock"] for e in json.loads(state.read_text())]


def patches(log: Path) -> int:
    return sum(1 for line in log.read_text().splitlines() if line.startswith("PATCH"))


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)

        # list (text and --json) sends nothing
        state, log = fresh(tmp)
        r = run("test-db", state, log)
        require(r.returncode == 0, f"list failed: {r.stderr}")
        require("203.0.113.10/32" in r.stdout and "vpn range" in r.stdout, f"list output: {r.stdout}")
        r = run("test-db", state, log, render_json="1")
        data = json.loads(r.stdout)
        require(data["ipAllowList"] == INITIAL and data["id"] == "dpg-test", f"list --json: {data}")
        require(patches(log) == 0, "list sent a PATCH")

        # add: one entry appended, everything else kept, read back verified
        state, log = fresh(tmp)
        r = run("test-db add 192.0.2.7 --label laptop", state, log)
        require(r.returncode == 0, f"add failed: {r.stdout} {r.stderr}")
        require(cidrs(state) == ["203.0.113.10/32", "198.51.100.0/24", "192.0.2.7/32"], f"add result: {state.read_text()}")
        require(json.loads(state.read_text())[2]["description"] == "laptop", "add lost the label")
        require(patches(log) == 1, "add should send exactly one PATCH")
        require(log.read_text().splitlines()[-1] == "GET /postgres/dpg-test", "add did not read back after writing")

        # add duplicate (same network, different spelling): no-op, nothing sent
        state, log = fresh(tmp)
        r = run("test-db add 203.0.113.10 --label again", state, log)
        require(r.returncode == 0 and patches(log) == 0 and cidrs(state) == [e["cidrBlock"] for e in INITIAL],
                f"duplicate add changed something: {r.stdout} {state.read_text()}")

        # add requires a label (the API requires a description)
        state, log = fresh(tmp)
        r = run("test-db add 192.0.2.8", state, log)
        require(r.returncode == 2 and patches(log) == 0, f"add without --label accepted: {r.stdout}")

        # remove: exactly one entry gone, rest kept
        state, log = fresh(tmp)
        r = run("test-db remove 198.51.100.0/24", state, log)
        require(r.returncode == 0 and cidrs(state) == ["203.0.113.10/32"], f"remove result: {r.stdout} {state.read_text()}")

        # remove a missing entry: error, nothing sent
        state, log = fresh(tmp)
        r = run("test-db remove 192.0.2.200", state, log)
        require(r.returncode != 0 and patches(log) == 0, f"remove of a missing entry: rc={r.returncode} {r.stdout}")

        # everywhere rules need an explicit flag
        for everywhere in ("0.0.0.0/0", "::/0"):
            state, log = fresh(tmp)
            r = run(f"test-db add {everywhere} --label anyone", state, log)
            require(r.returncode == 2 and patches(log) == 0, f"{everywhere} added without --allow-everywhere: {r.stdout}")
        state, log = fresh(tmp)
        r = run("test-db add 0.0.0.0/0 --label anyone --allow-everywhere", state, log)
        require(r.returncode == 0 and "0.0.0.0/0" in cidrs(state), f"--allow-everywhere did not add: {r.stdout} {r.stderr}")

        # dry-run: shows the change, sends nothing
        state, log = fresh(tmp)
        r = run("test-db add 192.0.2.9/32 --label maybe --dry-run", state, log)
        require(r.returncode == 0 and patches(log) == 0 and cidrs(state) == [e["cidrBlock"] for e in INITIAL],
                f"dry-run wrote: {r.stdout} {state.read_text()}")
        require("192.0.2.9/32" in r.stdout, f"dry-run did not show the change: {r.stdout}")

        # read-back mismatch (someone else changed it): fails loudly
        state, log = fresh(tmp)
        r = run("test-db add 192.0.2.10 --label laptop", state, log, mode="mismatch")
        require(r.returncode != 0, f"read-back mismatch reported success: {r.stdout}")
        require("mismatch" in (r.stdout + r.stderr).lower(), f"mismatch not explained: {r.stdout} {r.stderr}")

        # malformed input: exit 2, nothing sent
        for bad in ("add not-an-ip --label x", "add 192.0.2.1/33 --label x", "frobnicate 1.2.3.4", "add 192.0.2.1 --label x --bogus"):
            state, log = fresh(tmp)
            r = run(f"test-db {bad}", state, log)
            require(r.returncode == 2 and patches(log) == 0, f"bad input accepted ({bad}): rc={r.returncode} {r.stdout}")

    print("render db allowlist tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
