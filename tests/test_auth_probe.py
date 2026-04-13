#!/usr/bin/env python3
"""Checkpoint probe tests for agent-do auth."""

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
from pathlib import Path

state_path = Path(os.environ["FAKE_BROWSE_STATE"])


def load():
    if state_path.exists():
        return json.loads(state_path.read_text())
    return {"page": "blank", "url": "about:blank", "text": "", "selectors": []}


def save(data):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(data))


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
mode = os.environ.get("FAKE_AUTH_PROBE_MODE", "passkey")
command = args[0]

if command == "open":
    current = {
        "page": "login",
        "url": args[1],
        "text": "Sign in",
        "selectors": ["input[type=\\"email\\"]", "input[type=\\"password\\"]", "button[type=\\"submit\\"]"],
    }
    save(current)
    success({"url": args[1]})

if command == "auth" and args[1] == "autofill":
    if mode == "passkey":
        current = {
            "page": "passkey",
            "url": "https://app.example.com/passkey",
            "text": "Use a passkey to continue",
            "selectors": [],
        }
    else:
        current = {
            "page": "device-approval",
            "url": "https://app.example.com/device-check",
            "text": "Check your phone to approve sign in",
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

if command == "auth" and args[1] == "detect-login":
    success({"found": current.get("page") == "login"})

if command == "auth" and args[1] == "detect-captcha":
    success({"hasCaptcha": False, "types": []})

if command == "session":
    action = args[1]
    if action == "load":
        success({"loaded": True})
    if action == "delete":
        success({"deleted": True})
    if action == "save":
        success({"saved": True})
    if action == "export":
        out = Path(args[3])
        out.write_text(json.dumps({"storage": current}))
        success({"exported": True})
    if action == "import":
        payload = json.loads(Path(args[2]).read_text())
        save(payload.get("storage", {}))
        success({"imported": True})

fail(f"unsupported args: {args}")
"""


FAKE_MACOS = """\
#!/usr/bin/env python3
import json
import os
import sys

mode = os.environ.get("FAKE_AUTH_PROBE_MODE", "passkey")
args = sys.argv[1:]

if args == ["permissions"]:
    print(json.dumps({"granted": True, "message": "Granted"}))
    raise SystemExit(0)

if args == ["frontmost"]:
    print(json.dumps({"app": "Safari", "pid": 123}))
    raise SystemExit(0)

if args == ["dialog", "detect"]:
    if mode == "passkey":
        print(json.dumps({"type": "dialog", "title": "Use Passkey?", "buttons": ["Cancel", "Continue"], "app": "Safari"}))
    else:
        print(json.dumps({"type": None, "message": "No dialog detected"}))
    raise SystemExit(0)

print(json.dumps({"error": f"unsupported args: {args}"}))
raise SystemExit(1)
"""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_browse = tmp / "fake-browse"
        fake_macos = tmp / "fake-macos"
        write_executable(fake_browse, textwrap.dedent(FAKE_BROWSE))
        write_executable(fake_macos, textwrap.dedent(FAKE_MACOS))

        def make_env(mode: str, home_name: str) -> dict[str, str]:
            env = os.environ.copy()
            env["AGENT_DO_HOME"] = str(tmp / home_name)
            env["AGENT_DO_AUTH_BROWSE_CMD"] = str(fake_browse)
            env["AGENT_DO_AUTH_MACOS_CMD"] = str(fake_macos)
            env["FAKE_BROWSE_STATE"] = str(tmp / f"{home_name}-browse.json")
            env["FAKE_AUTH_PROBE_MODE"] = mode
            env["APP_EXAMPLE_COM_EMAIL"] = "agent@example.com"
            env["APP_EXAMPLE_COM_PASSWORD"] = "super-secret"
            return env

        def seed_profile(env: dict[str, str], site: str) -> None:
            profile_path = Path(env["AGENT_DO_HOME"]) / "auth" / "profiles" / f"{site}.yaml"
            write_profile(
                profile_path,
                f"""
                id: {site}
                title: {site}
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

        passkey_env = make_env("passkey", "passkey-home")
        seed_profile(passkey_env, "app-passkey-probe")
        ensure_passkey = run(str(AGENT_DO), "auth", "ensure", "app-passkey-probe", "--json", cwd=ROOT, env=passkey_env)
        require(ensure_passkey.returncode == 1, f"expected passkey ensure failure: {ensure_passkey.stdout} {ensure_passkey.stderr}")
        ensure_passkey_payload = json.loads(ensure_passkey.stdout)
        require(ensure_passkey_payload["action_required"] == "PASSKEY_CHALLENGE_REQUIRED", f"unexpected passkey ensure payload: {ensure_passkey_payload}")

        probe_passkey = run(str(AGENT_DO), "auth", "probe", "app-passkey-probe", "--json", cwd=ROOT, env=passkey_env)
        require(probe_passkey.returncode == 0, f"auth probe passkey failed: {probe_passkey.stderr}")
        probe_passkey_payload = json.loads(probe_passkey.stdout)
        require(probe_passkey_payload["state"] == "checkpoint", f"unexpected passkey probe payload: {probe_passkey_payload}")
        require(
            any(item["action_required"] == "PASSKEY_CHALLENGE_REQUIRED" for item in probe_passkey_payload["checkpoints"]),
            f"missing passkey checkpoint: {probe_passkey_payload}",
        )
        require(probe_passkey_payload["desktop_dialog"]["type"] == "dialog", f"expected desktop dialog: {probe_passkey_payload}")
        require(
            "agent-do macos dialog click --default" in probe_passkey_payload["recommended"],
            f"expected macos dialog recommendation: {probe_passkey_payload}",
        )

        status_passkey = run(str(AGENT_DO), "auth", "status", "app-passkey-probe", "--json", cwd=ROOT, env=passkey_env)
        require(status_passkey.returncode == 0, f"auth status passkey failed: {status_passkey.stderr}")
        status_passkey_payload = json.loads(status_passkey.stdout)
        require(status_passkey_payload["state"] == "checkpoint", f"expected checkpoint status: {status_passkey_payload}")
        require(status_passkey_payload["last_action_required"] == "PASSKEY_CHALLENGE_REQUIRED", f"missing last action required: {status_passkey_payload}")

        instructions_passkey = run(str(AGENT_DO), "auth", "instructions", "app-passkey-probe", "--json", cwd=ROOT, env=passkey_env)
        require(instructions_passkey.returncode == 0, f"auth instructions passkey failed: {instructions_passkey.stderr}")
        instructions_passkey_payload = json.loads(instructions_passkey.stdout)
        require(
            instructions_passkey_payload["recommended"][0] == "agent-do auth probe app-passkey-probe",
            f"expected probe-first instructions: {instructions_passkey_payload}",
        )

        device_env = make_env("device", "device-home")
        seed_profile(device_env, "app-device-probe")
        ensure_device = run(str(AGENT_DO), "auth", "ensure", "app-device-probe", "--json", cwd=ROOT, env=device_env)
        require(ensure_device.returncode == 1, f"expected device approval ensure failure: {ensure_device.stdout} {ensure_device.stderr}")
        ensure_device_payload = json.loads(ensure_device.stdout)
        require(ensure_device_payload["action_required"] == "DEVICE_APPROVAL_REQUIRED", f"unexpected device ensure payload: {ensure_device_payload}")

        probe_device = run(str(AGENT_DO), "auth", "probe", "app-device-probe", "--json", cwd=ROOT, env=device_env)
        require(probe_device.returncode == 0, f"auth probe device failed: {probe_device.stderr}")
        probe_device_payload = json.loads(probe_device.stdout)
        require(
            any(item["action_required"] == "DEVICE_APPROVAL_REQUIRED" for item in probe_device_payload["checkpoints"]),
            f"missing device approval checkpoint: {probe_device_payload}",
        )
        require(probe_device_payload["desktop_dialog"]["type"] is None, f"unexpected device desktop dialog: {probe_device_payload}")

    print("auth probe tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
