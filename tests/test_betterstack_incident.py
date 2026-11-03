#!/usr/bin/env python3
"""betterstack incident shows what the uptime checker received.

The 2026-11-03 morning burst of "site down" incidents were Cloudflare
challenges (cf-mitigated: challenge) in front of healthy apps, but
`incident <id>` showed only "Status 403". The response code, IP and
diagnostic headers come from the incident's response_options; cookies and
other headers must never be printed. The API call is stubbed.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HEADERS = (
    "HTTP/1.1 301 Moved Permanently\r\nlocation: https://example.test/health\r\n\r\n"
    "HTTP/2 403 \r\ndate: Tue, 03 Nov 2026 14:01:16 GMT\r\ncontent-type: text/html; charset=UTF-8\r\n"
    "cf-mitigated: challenge\r\nset-cookie: __cf_bm=SECRETCOOKIE; path=/\r\nserver: cloudflare\r\n"
    "cf-ray: 0123456789abcdef-IAD\r\n\r\n"
)
INCIDENT = {
    "data": {
        "id": "42",
        "attributes": {
            "name": "example",
            "cause": "Status 403",
            "status": "Resolved",
            "response_options": json.dumps(
                {
                    "response_code": 403,
                    "primary_ip": "203.0.113.7",
                    "effective_url": "https://example.test/health",
                    "total_time": 0.02,
                    "response_headers": HEADERS,
                }
            ),
        },
        "relationships": {"monitor": {"data": {"id": "7"}}},
    }
}


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def run(payload: dict) -> subprocess.CompletedProcess[str]:
    body = json.dumps(payload).replace("'", "'\\''")
    script = f"""
set -uo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-betterstack'}")
bs_get() {{ printf '%s' '{body}'; }}
cmd_incident 42
"""
    return subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    r = run(INCIDENT)
    require(r.returncode == 0, f"incident failed: {r.stderr}")
    out = json.loads(r.stdout)
    resp = out.get("response") or {}
    require(resp.get("code") == 403 and resp.get("primary_ip") == "203.0.113.7", f"response basics: {resp}")
    h = resp.get("headers", {})
    require(h.get("cf-mitigated") == "challenge" and h.get("server") == "cloudflare", f"final-hop headers: {h}")
    require("location" not in h, f"headers must come from the last response only: {h}")
    require("SECRETCOOKIE" not in r.stdout and "set-cookie" not in h, "cookies must never be printed")
    require("may be up" in resp.get("note", ""), f"challenge note: {resp}")

    bare = json.loads(json.dumps(INCIDENT))
    del bare["data"]["attributes"]["response_options"]
    r = run(bare)
    require(r.returncode == 0 and json.loads(r.stdout)["response"] is None, f"no response_options: {r.stdout}")

    print("betterstack incident tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
