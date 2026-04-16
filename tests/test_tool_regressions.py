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
    browse_source = (ROOT / "tools/agent-browse/agent-browse").read_text()
    require("Library/Application Support/Comet/Default/Cookies" in browse_source, "expected Comet cookie path in agent-browse")
    require("user-*/Cookies" in browse_source, "expected Atlas user-profile cookie discovery in agent-browse")
    require("Chromium Safe Storage" in browse_source, "expected Chromium Safe Storage fallback in agent-browse")
    require('"extractor": "chromium"' in browse_source, "expected Atlas to use the Chromium extractor path")
    require("default: comet" in browse_source, "expected Comet to remain the default browser import source")

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
printf '\\n---\\n'
build_clipboard_cmd read
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
    require(browse_parts[4]["action"] == "clipboard", f"unexpected clipboard action: {browse_parts[4]}")
    require(browse_parts[4]["operation"] == "read", f"unexpected clipboard payload: {browse_parts[4]}")

    namecheap_script = f"""
set -euo pipefail
source <(sed '$d' "{ROOT / 'tools/agent-namecheap'}")
_get_hosts_json() {{
  printf '%s\\n' '{{"records":[]}}'
}}
verify_record_provider_exact() {{
  return 0
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
    require("Verified: Namecheap API read-back matches" in namecheap.stdout, f"expected verification output: {namecheap.stdout}")

    suspicious_script = f"""
set -euo pipefail
source <(sed '$d' "{ROOT / 'tools/agent-namecheap'}")
cmd_dns_verify example.com TXT resend._domainkey "p=MIGfMA[...]IDAQAB"
"""
    suspicious = run_bash(suspicious_script)
    require(suspicious.returncode != 0, "expected suspicious DNS value to fail")
    require(
        "looks masked or truncated" in suspicious.stderr,
        f"unexpected suspicious-value stderr: {suspicious.stderr}",
    )

    print("tool regression tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
