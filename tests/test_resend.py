#!/usr/bin/env python3
"""Focused tests for agent-do resend."""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import subprocess
import tempfile
import textwrap
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


DOMAIN_ID = "d-123"
DOMAIN_NAME = "example.com"
DKIM_VALUE = "p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCgbkgjfWpa9tGYTV7c9MNcwo0zPART1PART2IDAQAB"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class ResendHandler(http.server.BaseHTTPRequestHandler):
    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/domains":
            self._send(
                {
                    "data": [
                        {
                            "id": DOMAIN_ID,
                            "name": DOMAIN_NAME,
                            "status": "pending",
                            "region": "us-east-1",
                            "capabilities": {"sending": True, "receiving": False},
                        }
                    ]
                }
            )
            return

        if self.path == f"/domains/{DOMAIN_ID}":
            self._send(
                {
                    "id": DOMAIN_ID,
                    "name": DOMAIN_NAME,
                    "status": "pending",
                    "region": "us-east-1",
                    "created_at": "2026-04-12T00:00:00.000Z",
                    "capabilities": {"sending": True, "receiving": False},
                    "records": [
                        {
                            "record": "DKIM",
                            "name": "resend._domainkey",
                            "type": "TXT",
                            "value": DKIM_VALUE,
                            "status": "pending",
                        },
                        {
                            "record": "SPF",
                            "name": "send",
                            "type": "TXT",
                            "value": "v=spf1 include:amazonses.com ~all",
                            "status": "pending",
                        },
                        {
                            "record": "SPF",
                            "name": "send",
                            "type": "MX",
                            "value": "feedback-smtp.us-east-1.amazonses.com",
                            "priority": 10,
                            "status": "pending",
                        },
                    ],
                }
            )
            return

        self._send({"error": {"message": "not found"}}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/domains":
            self._send(
                {
                    "id": "d-456",
                    "name": "new.example.com",
                    "status": "pending",
                    "records": [],
                },
                status=201,
            )
            return

        if self.path == f"/domains/{DOMAIN_ID}/verify":
            self._send({"object": "domain", "id": DOMAIN_ID})
            return

        self._send({"error": {"message": "not found"}}, status=404)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def run(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir(parents=True, exist_ok=True)

        dig_path = fake_bin / "dig"
        dig_path.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env bash
                set -euo pipefail
                type="$2"
                name="$3"
                case "$type:$name" in
                  TXT:resend._domainkey.{DOMAIN_NAME})
                    printf '"p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCgbkgjfWpa9tGYTV7c9MNcwo0zPART1" "PART2IDAQAB"\\n'
                    ;;
                  TXT:send.{DOMAIN_NAME})
                    printf '"v=spf1 include:amazonses.com ~all"\\n'
                    ;;
                  MX:send.{DOMAIN_NAME})
                    printf '10 feedback-smtp.us-east-1.amazonses.com.\\n'
                    ;;
                esac
                """
            ),
            encoding="utf-8",
        )
        dig_path.chmod(0o755)

        server = socketserver.TCPServer(("127.0.0.1", 0), ResendHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = os.environ.copy()
            env["RESEND_API_KEY"] = "re_test_123"
            env["RESEND_API_URL"] = f"http://127.0.0.1:{server.server_address[1]}"
            env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"

            records = run(str(AGENT_DO), "resend", "records", DOMAIN_NAME, env=env)
            require(records.returncode == 0, f"resend records failed: {records.stderr}")
            require(DKIM_VALUE in records.stdout, f"expected full DKIM value in output: {records.stdout}")
            require("resend._domainkey.example.com" in records.stdout, f"expected fqdn in output: {records.stdout}")

            dns_check = run(str(AGENT_DO), "resend", "--json", "dns-check", DOMAIN_NAME, env=env)
            require(dns_check.returncode == 0, f"dns-check failed: {dns_check.stderr}")
            dns_payload = json.loads(dns_check.stdout)
            require(dns_payload["all_matched"] is True, f"expected dns-check match: {dns_payload}")
            require(len(dns_payload["checks"]) == 3, f"unexpected dns-check payload: {dns_payload}")

            verify = run(str(AGENT_DO), "resend", "--json", "verify", DOMAIN_NAME, env=env)
            require(verify.returncode == 0, f"verify failed: {verify.stderr}")
            verify_payload = json.loads(verify.stdout)
            require(verify_payload["verify"]["id"] == DOMAIN_ID, f"unexpected verify payload: {verify_payload}")

            add = run(str(AGENT_DO), "resend", "--json", "add", "new.example.com", env=env)
            require(add.returncode == 0, f"resend add failed: {add.stderr}")
            add_payload = json.loads(add.stdout)
            require(add_payload["name"] == "new.example.com", f"unexpected add payload: {add_payload}")
        finally:
            server.shutdown()
            server.server_close()

    print("resend tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
