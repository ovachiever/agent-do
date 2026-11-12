#!/usr/bin/env python3
"""agent-betterstack heartbeats: the ping URL is a write credential and must
be redacted in --json unless --reveal; the table must not show a LAST PING
column the list endpoint never populates."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_URL = "https://uptime.betterstack.com/api/v1/heartbeat/AbCdEf123456SecretToken"
UNEXPECTED_URL = "https://status.invalid/ping/SyntheticUnexpectedCredential"
PAYLOAD = json.dumps(
    {
        "data": [
            {
                "id": "1",
                "type": "heartbeat",
                "attributes": {
                    "name": "job-a",
                    "status": "up",
                    "period": 300,
                    "grace": 180,
                    "url": EXPECTED_URL,
                },
            },
            {
                "id": "2",
                "type": "heartbeat",
                "attributes": {
                    "name": "job-unexpected",
                    "status": "up",
                    "period": 60,
                    "grace": 30,
                    "url": UNEXPECTED_URL,
                },
            },
        ]
    },
    separators=(",", ":"),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(cmd: str) -> subprocess.CompletedProcess[str]:
    script = f"""
set -uo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-betterstack'}")
bs_get() {{ printf '%s' '{PAYLOAD}'; }}
{cmd}
"""
    return subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False)


def test_heartbeats_contract_is_sensitive() -> None:
    sys.path.insert(0, str(ROOT / "lib"))
    from registry import _load_yaml_data, get_tool_contract_attributes

    registry = _load_yaml_data(ROOT / "registry.yaml")
    attributes = get_tool_contract_attributes(registry["tools"]["betterstack"])
    require(
        "sensitive" in attributes.get("heartbeats", []),
        "heartbeats must remain sensitive because --json --reveal emits its write credential",
    )


def main() -> int:
    test_heartbeats_contract_is_sensitive()

    r = run("cmd_heartbeats --json")
    require(r.returncode == 0, f"heartbeats --json failed: {r.stderr}")
    default_data = json.loads(r.stdout)
    default_urls = [item["attributes"]["url"] for item in default_data["data"]]
    require(default_urls == ["<redacted>", "<redacted>"], f"heartbeat URLs not fully redacted: {r.stdout}")
    require(EXPECTED_URL not in r.stdout, f"standard heartbeat URL leaked in --json: {r.stdout}")
    require(UNEXPECTED_URL not in r.stdout, f"unexpected heartbeat URL leaked in --json: {r.stdout}")

    r = run("cmd_heartbeats --json --reveal")
    require(r.returncode == 0, f"heartbeats --json --reveal failed: {r.stderr}")
    revealed_data = json.loads(r.stdout)
    revealed_urls = [item["attributes"]["url"] for item in revealed_data["data"]]
    require(revealed_urls == [EXPECTED_URL, UNEXPECTED_URL], f"--reveal did not preserve URLs: {r.stdout}")
    require("<redacted>" not in r.stdout, f"--reveal still redacted: {r.stdout}")

    r = run("cmd_heartbeats")
    require(r.returncode == 0, f"heartbeats table failed: {r.stderr}")
    require(EXPECTED_URL not in r.stdout, f"standard heartbeat URL in table: {r.stdout}")
    require(UNEXPECTED_URL not in r.stdout, f"unexpected heartbeat URL in table: {r.stdout}")
    require("LAST PING" not in r.stdout, f"dead LAST PING column still rendered: {r.stdout}")
    require("PERIOD" in r.stdout and "job-a" in r.stdout, f"table lost content: {r.stdout}")

    print("betterstack heartbeat tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
