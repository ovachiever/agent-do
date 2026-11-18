#!/usr/bin/env python3
"""sentry resolve/ignore name the issue they changed.

Sentry's org bulk endpoint (which `ignore` uses so the substatus sticks)
answers with the changed fields only — no shortId, no id — so the success line
used to read "Issue  ignored." with a blank id. A local stub server stands in
for Sentry; no token or network is used.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep test output quiet
        pass

    def _send(self, body: object) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if "/shortids/" in self.path:
            self._send({"groupId": "4242", "shortId": "TEST-PROJ-1A", "group": {"id": "4242"}})
        else:
            self._send({})

    def do_PUT(self):
        length = int(self.headers.get("Content-Length") or 0)
        sent = json.loads(self.rfile.read(length) or b"{}")
        if "/issues/?id=" in self.path:
            # Bulk mutate: Sentry echoes the applied fields, nothing else.
            self._send({"status": sent.get("status"), "substatus": sent.get("substatus"), "statusDetails": {}})
        else:
            self._send({"id": "4242", "shortId": "TEST-PROJ-1A", "status": sent.get("status")})


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = os.environ.copy()
    env.update(
        {
            "SENTRY_AUTH_TOKEN": "test-token",
            "SENTRY_ORG": "test-org",
            "SENTRY_REGION_URL": f"http://127.0.0.1:{server.server_port}",
        }
    )

    def sentry(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(ROOT / "tools/agent-sentry"), *args], capture_output=True, text=True, env=env, timeout=60
        )

    try:
        ignored = sentry("ignore", "TEST-PROJ-1A")
        require(ignored.returncode == 0, f"ignore failed: {ignored.stderr}")
        require(
            ignored.stdout.strip() == "Issue TEST-PROJ-1A ignored (archived_until_escalating).",
            f"ignore must name the issue: {ignored.stdout!r}",
        )

        ignored_json = sentry("ignore", "TEST-PROJ-1A", "--json")
        require(ignored_json.returncode == 0, f"ignore --json failed: {ignored_json.stderr}")
        payload = json.loads(ignored_json.stdout)
        require(payload.get("requested_id") == "TEST-PROJ-1A", f"--json must carry the requested id: {payload}")

        resolved = sentry("resolve", "TEST-PROJ-1A")
        require(resolved.returncode == 0, f"resolve failed: {resolved.stderr}")
        require(resolved.stdout.strip() == "Issue TEST-PROJ-1A resolved.", f"unexpected: {resolved.stdout!r}")
    finally:
        server.shutdown()
    print("sentry action tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
