#!/usr/bin/env python3
"""Focused wrapper regressions for browse and Namecheap."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    browse_script = f"""
set -euo pipefail
source <(sed '$d' "{ROOT / 'tools/agent-browse/agent-browse'}")
build_get_cmd text '@e32'
printf '\\n---\\n'
build_get_cmd html '@e32'
printf '\\n---\\n'
build_get_cmd value '@email'
printf '\\n---\\n'
build_get_cmd attr href '@link'
"""
    browse = run_bash(browse_script)
    require(browse.returncode == 0, f"browse builder failed: {browse.stderr}")
    browse_parts = [json.loads(part.strip()) for part in browse.stdout.split("\n---\n")]
    require(browse_parts[0]["action"] == "gettext", f"unexpected text action: {browse_parts[0]}")
    require(browse_parts[1]["action"] == "innerhtml", f"unexpected html action: {browse_parts[1]}")
    require(browse_parts[2]["action"] == "inputvalue", f"unexpected value action: {browse_parts[2]}")
    require(
        browse_parts[3] == {
            "id": browse_parts[3]["id"],
            "action": "getattribute",
            "selector": "@link",
            "attribute": "href",
        },
        f"unexpected attr payload: {browse_parts[3]}",
    )

    namecheap_script = f"""
set -euo pipefail
source <(sed '$d' "{ROOT / 'tools/agent-namecheap'}")
_get_hosts_json() {{
  printf '%s\\n' '{{"records":[]}}'
}}
_set_hosts() {{
  cat <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<ApiResponse Status="OK" xmlns="http://api.namecheap.com/xml.response">
  <CommandResponse>
    <DomainDNSSetHostsResult IsSuccess="true" />
  </CommandResponse>
</ApiResponse>
EOF
}}
nc_check_error() {{
  cat
}}
cmd_dns_add example.com TXT resend._domainkey "p=test-value" --ttl 600
"""
    namecheap = run_bash(namecheap_script)
    require(namecheap.returncode == 0, f"namecheap dns-add failed: {namecheap.stderr}")
    require(
        "Added: TXT resend._domainkey → p=test-value  (TTL: 600)" in namecheap.stdout,
        f"unexpected dns-add output: {namecheap.stdout}",
    )

    print("tool regression tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
