#!/usr/bin/env python3
"""Passkey escalation tests for agent-do auth."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def run(*args: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def write_profile(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8")


FAKE_BROWSE = """\
#!/usr/bin/env python3
import json
import os
import sys

state_path = os.environ["FAKE_BROWSE_STATE"]


def load():
    try:
        with open(state_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {"url": "about:blank", "text": "", "selectors": []}


def save(data):
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)


def success(data):
    print(json.dumps({"success": True, "data": data}))
    raise SystemExit(0)


def fail(message):
    print(json.dumps({"success": False, "error": message}))
    raise SystemExit(1)


args = sys.argv[1:]
if args and args[0] == "--json":
    args = args[1:]

if not args:
    fail("missing command")

current = load()
command = args[0]

if command == "open":
    current = {
        "url": args[1],
        "text": "Sign in",
        "selectors": ["input[type=\\"email\\"]", "input[type=\\"password\\"]", "button[type=\\"submit\\"]"],
    }
    save(current)
    success({"url": args[1]})

if command == "auth" and args[1] == "autofill":
    current = {
        "url": "https://app.example.com/passkey",
        "text": "Use a passkey to continue",
        "selectors": [],
    }
    save(current)
    success({"filled": True})

if command == "get" and args[1] == "url":
    success({"url": current.get("url", "about:blank")})

if command == "get" and args[1] == "count":
    selector = args[2]
    success({"count": 1 if selector in current.get("selectors", []) else 0})

if command == "eval":
    success({"result": current.get("text", "")})

if command == "wait":
    success({"waited": True})

fail(f"unsupported args: {args}")
"""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_browse = tmp / "fake-browse"
        write_executable(fake_browse, textwrap.dedent(FAKE_BROWSE))

        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(tmp / "home")
        env["AGENT_DO_AUTH_BROWSE_CMD"] = str(fake_browse)
        env["FAKE_BROWSE_STATE"] = str(tmp / "browse-state.json")
        env["APP_EXAMPLE_COM_EMAIL"] = "agent@example.com"
        env["APP_EXAMPLE_COM_PASSWORD"] = "super-secret"

        profile_path = Path(env["AGENT_DO_HOME"]) / "auth" / "profiles" / "app-passkey.yaml"
        write_profile(
            profile_path,
            """
            id: app-passkey
            title: App Passkey
            domains:
              - app.example.com
            login_url: https://app.example.com/login
            validation:
              url_patterns:
                - https://app.example.com/dashboard*
              signed_out_markers:
                - Sign in
              signed_in_markers:
                - Dashboard
            strategies:
              - site-creds
              - interactive
            provider:
              type: generic
            credentials:
              site:
                username: APP_EXAMPLE_COM_EMAIL
                password: APP_EXAMPLE_COM_PASSWORD
            """,
        )

        ensure = run(str(AGENT_DO), "auth", "ensure", "app-passkey", "--json", cwd=ROOT, env=env)
        require(ensure.returncode == 1, f"expected passkey action-required failure: {ensure.stdout} {ensure.stderr}")
        payload = json.loads(ensure.stdout)
        require(payload["action_required"] == "PASSKEY_CHALLENGE_REQUIRED", f"unexpected passkey payload: {payload}")

    print("auth passkey tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
