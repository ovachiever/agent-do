#!/usr/bin/env python3
"""Focused Slack tool tests with a local fake Slack API."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


class FakeSlackHandler(BaseHTTPRequestHandler):
    calls: list[dict[str, object]] = []

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        FakeSlackHandler.calls.append(
            {
                "method": "GET",
                "path": parsed.path,
                "params": params,
                "auth": self.headers.get("Authorization"),
            }
        )

        if parsed.path == "/api/users.list":
            self.respond(
                {
                    "ok": True,
                    "members": [
                        {
                            "id": "UDANA",
                            "name": "dexample",
                            "real_name": "Dana Example",
                            "deleted": False,
                            "is_bot": False,
                            "profile": {
                                "display_name": "Dana",
                                "real_name": "Dana Example",
                                "email": "dana@example.com",
                            },
                        }
                    ],
                    "response_metadata": {"next_cursor": ""},
                }
            )
            return

        self.respond({"ok": False, "error": "unknown_method"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        body = json.loads(raw.decode("utf-8")) if raw else {}
        FakeSlackHandler.calls.append(
            {
                "method": "POST",
                "path": parsed.path,
                "body": body,
                "auth": self.headers.get("Authorization"),
            }
        )

        if parsed.path == "/api/conversations.open":
            self.respond({"ok": True, "channel": {"id": "DDANA"}})
            return

        if parsed.path == "/api/chat.postMessage":
            self.respond({"ok": True, "channel": body.get("channel"), "ts": "123.456"})
            return

        self.respond({"ok": False, "error": "unknown_method"})

    def respond(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_agent(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(AGENT_DO), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), FakeSlackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as agent_home:
            base_env = os.environ.copy()
            base_env["AGENT_DO_HOME"] = agent_home
            base_env["AGENT_DO_CREDS_SERVICE"] = f"agent-do-test-slack-{os.getpid()}"
            base_env["SLACK_API_BASE_URL"] = f"http://127.0.0.1:{server.server_port}/api"
            base_env["SLACK_USER_TOKEN"] = "xoxp-user-token"
            base_env["SLACK_BOT_TOKEN"] = "xoxb-bot-token"

            FakeSlackHandler.calls = []
            dm_result = run_agent(["slack", "dm", "--as-user", "--json", "Dana Example", "hello from me"], base_env)
            require(dm_result.returncode == 0, f"dm failed: {dm_result.stderr}")
            dm_payload = json.loads(dm_result.stdout)
            require(dm_payload["channel"] == "DDANA", f"unexpected dm payload: {dm_payload}")
            require(dm_payload["identity"] == "user", f"expected user identity: {dm_payload}")
            require(
                [call["path"] for call in FakeSlackHandler.calls]
                == ["/api/users.list", "/api/conversations.open", "/api/chat.postMessage"],
                f"unexpected dm API calls: {FakeSlackHandler.calls}",
            )
            require(FakeSlackHandler.calls[-1]["body"]["channel"] == "DDANA", f"unexpected post body: {FakeSlackHandler.calls}")
            require(FakeSlackHandler.calls[-1]["auth"] == "Bearer xoxp-user-token", f"unexpected auth: {FakeSlackHandler.calls}")

            FakeSlackHandler.calls = []
            direct_id_result = run_agent(["slack", "send", "--as-user", "--json", "DDANA", "hello again"], base_env)
            require(direct_id_result.returncode == 0, f"direct ID send failed: {direct_id_result.stderr}")
            require(
                [call["path"] for call in FakeSlackHandler.calls] == ["/api/chat.postMessage"],
                f"expected direct send to skip resolution: {FakeSlackHandler.calls}",
            )
            require(FakeSlackHandler.calls[0]["body"]["channel"] == "DDANA", f"unexpected direct post: {FakeSlackHandler.calls}")

            FakeSlackHandler.calls = []
            bot_channel_result = run_agent(["slack", "send", "--as-bot", "--json", "engineering", "deploy complete"], base_env)
            require(bot_channel_result.returncode == 0, f"bot channel send failed: {bot_channel_result.stderr}")
            require(FakeSlackHandler.calls[0]["body"]["channel"] == "#engineering", f"unexpected channel post: {FakeSlackHandler.calls}")
            require(FakeSlackHandler.calls[0]["auth"] == "Bearer xoxb-bot-token", f"unexpected bot auth: {FakeSlackHandler.calls}")

            no_token_env = os.environ.copy()
            no_token_env["AGENT_DO_HOME"] = agent_home
            no_token_env["AGENT_DO_CREDS_SERVICE"] = base_env["AGENT_DO_CREDS_SERVICE"]
            no_token_env["SLACK_API_BASE_URL"] = base_env["SLACK_API_BASE_URL"]
            for key in ["SLACK_USER_TOKEN", "SLACK_TOKEN", "SLACK_BOT_TOKEN", "SLACK_WEBHOOK_URL"]:
                no_token_env.pop(key, None)
            missing_result = run_agent(["slack", "dm", "--as-user", "Dana Example", "hello"], no_token_env)
            require(missing_result.returncode != 0, "expected --as-user without token to fail")
            require("SLACK_USER_TOKEN is required" in missing_result.stderr, f"unexpected missing-token error: {missing_result.stderr}")

            creds_result = run_agent(["creds", "check", "--tool", "slack", "--json"], base_env)
            require(creds_result.returncode == 0, f"slack creds check failed: {creds_result.stderr}")
            creds_payload = json.loads(creds_result.stdout)
            require(creds_payload["ok"] is True, f"unexpected slack creds payload: {creds_payload}")
    finally:
        server.shutdown()
        thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
