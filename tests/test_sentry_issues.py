#!/usr/bin/env python3
"""sentry issues: an unknown project fails in --json mode too; a full page says so.

Sentry answers `project:<unknown>` with {"detail": "Invalid query. Project(s)
… do not exist …"}. The text view already exited 1; `--json` printed it and
exited 0, so a typo'd slug read as a valid (odd) result. A page that hits
--limit gave no hint that more issues exist. A local stub stands in for Sentry.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        if "project:nope" in q.get("query", [""])[0]:
            body = {"detail": "Invalid query. Project(s) nope do not exist or are not actively selected."}
        else:
            n = int(q.get("limit", ["25"])[0])
            body = [{"shortId": f"P-{i}", "title": "t", "count": "1", "userCount": 0, "lastSeen": ""} for i in range(n)]
        data = json.dumps(body).encode()
        self.send_response(400 if isinstance(body, dict) else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = dict(os.environ, SENTRY_AUTH_TOKEN="t", SENTRY_ORG="o",
               SENTRY_REGION_URL=f"http://127.0.0.1:{server.server_port}")

    def sentry(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(ROOT / "tools/agent-sentry"), "issues", *args], env=env,
                              text=True, capture_output=True, timeout=120)

    try:
        r = sentry("--project", "nope", "--json")
        require(r.returncode == 1 and "do not exist" in r.stdout, f"--json unknown project: {r.returncode} {r.stdout!r}")
        r = sentry("--project", "nope")
        require(r.returncode == 1 and "do not exist" in r.stderr, f"text unknown project: {r.returncode}")
        r = sentry("--project", "real", "--limit", "3")
        require(r.returncode == 0 and "more may exist" in r.stderr, f"full page hint: {r.stderr!r}")
        r = sentry("--project", "real", "--limit", "3", "--json")
        require(r.returncode == 0 and len(json.loads(r.stdout)) == 3, "json list passes through")
        r = sentry("--limit", "500")
        require(r.returncode == 2, f"--limit over 100 must exit 2, got {r.returncode}")
    finally:
        server.shutdown()
    print("sentry issues tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
