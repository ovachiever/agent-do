#!/usr/bin/env python3
"""Email challenge tests for agent-do auth."""

from __future__ import annotations

import os
import json
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


FAKE_BROWSE = """\
#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["FAKE_BROWSE_ROOT"])
current_path = root / "current.json"
sessions_dir = root / "sessions"
sessions_dir.mkdir(parents=True, exist_ok=True)


def load_current():
    if current_path.exists():
        return json.loads(current_path.read_text())
    return {"page": "blank", "url": "about:blank", "text": "", "selectors": [], "fields": {}}


def save_current(data):
    current_path.write_text(json.dumps(data))


def session_file(name):
    return sessions_dir / f"{name}.json"


def success(data):
    print(json.dumps({"success": True, "data": data}))
    raise SystemExit(0)


def fail(message):
    print(json.dumps({"success": False, "error": message}))
    raise SystemExit(1)


def dashboard():
    return {"page": "dashboard", "url": "https://app.example.com/dashboard", "text": "Dashboard", "selectors": [], "fields": {}}


args = sys.argv[1:]
if args and args[0] == "--json":
    args = args[1:]

if not args:
    fail("missing command")

current = load_current()
command = args[0]

if command == "open":
    url = args[1]
    if "magic" in url:
        current = dashboard()
    elif "login" in url:
        current = {
            "page": "login",
            "url": url,
            "text": "Sign in",
            "selectors": ["input[type=\\"email\\"]", "input[type=\\"password\\"]", "button[type=\\"submit\\"]"],
            "fields": {},
        }
    save_current(current)
    success({"url": url})

if command == "get" and args[1] == "url":
    success({"url": current.get("url", "about:blank")})

if command == "get" and args[1] == "count":
    selector = args[2]
    success({"count": 1 if selector in current.get("selectors", []) else 0})

if command == "eval":
    success({"result": current.get("text", "")})

if command == "wait":
    success({"waited": True})

if command == "fill":
    selector = args[1]
    value = args[2]
    current.setdefault("fields", {})[selector] = value
    save_current(current)
    success({"filled": True, "selector": selector})

if command == "click":
    selector = args[1]
    page = current.get("page")
    fields = current.get("fields", {})
    if page == "login" and selector == "button[type=\\"submit\\"]":
        mode = os.environ.get("FAKE_AUTH_EMAIL_MODE", "code")
        if mode == "code":
            current = {
                "page": "email_code",
                "url": "https://app.example.com/verify",
                "text": "Enter the verification code we emailed you",
                "selectors": ["input[name=\\"code\\"]", "button[type=\\"submit\\"]"],
                "fields": fields,
            }
        else:
            current = {
                "page": "email_link",
                "url": "https://app.example.com/check-email",
                "text": "Check your email for the magic link",
                "selectors": [],
                "fields": fields,
            }
        save_current(current)
        success({"clicked": True})
    if page == "email_code" and selector == "button[type=\\"submit\\"]":
        if fields.get("input[name=\\"code\\"]") == "731902":
            current = dashboard()
            save_current(current)
            success({"clicked": True})
        fail("wrong email code")
    fail(f"unsupported click: {selector} on {page}")

if command == "auth" and args[1] == "autofill":
    current.setdefault("fields", {})["input[type=\\"email\\"]"] = args[2]
    current.setdefault("fields", {})["input[type=\\"password\\"]"] = args[3]
    if "--submit" in args:
        current = {
            "page": "email_code" if os.environ.get("FAKE_AUTH_EMAIL_MODE", "code") == "code" else "email_link",
            "url": "https://app.example.com/verify" if os.environ.get("FAKE_AUTH_EMAIL_MODE", "code") == "code" else "https://app.example.com/check-email",
            "text": "Enter the verification code we emailed you" if os.environ.get("FAKE_AUTH_EMAIL_MODE", "code") == "code" else "Check your email for the magic link",
            "selectors": ["input[name=\\"code\\"]", "button[type=\\"submit\\"]"] if os.environ.get("FAKE_AUTH_EMAIL_MODE", "code") == "code" else [],
            "fields": current.get("fields", {}),
        }
    save_current(current)
    success({"filled": True})

if command == "session":
    action = args[1]
    if action == "save":
        name = args[2]
        session_file(name).write_text(json.dumps(current))
        success({"saved": True, "name": name})
    if action == "load":
        name = args[2]
        path = session_file(name)
        if not path.exists():
            fail("session not found")
        current = json.loads(path.read_text())
        save_current(current)
        success({"loaded": True, "name": name})
    if action == "delete":
        name = args[2]
        session_file(name).unlink(missing_ok=True)
        success({"deleted": True, "name": name})
    if action == "export":
        name = args[2]
        out = Path(args[3])
        path = session_file(name)
        if not path.exists():
            fail("session not found")
        out.write_text(json.dumps({"name": name, "storage": json.loads(path.read_text())}))
        success({"exported": True, "name": name, "path": str(out)})
    if action == "import":
        input_path = Path(args[2])
        name = args[3]
        payload = json.loads(input_path.read_text())
        session_file(name).write_text(json.dumps(payload.get("storage", {})))
        success({"imported": True, "name": name})
    if action == "import-browser":
        fail("browser import not used in this test")

fail(f"unsupported args: {args}")
"""


FAKE_EMAIL = """\
#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if args and args[0] == "--json":
    args = args[1:]

command = args[0]
mode = os.environ.get("FAKE_AUTH_EMAIL_MODE", "code")

if os.environ.get("FAKE_AUTH_EMAIL_TIMEOUT") == "1":
    print(json.dumps({"ok": False, "message": "Timed out waiting for matching email"}))
    raise SystemExit(1)

if command == "code":
    print(json.dumps({"ok": True, "code": "731902", "message": {"id": "msg-code"}}))
    raise SystemExit(0)

if command == "link":
    print(json.dumps({"ok": True, "link": "https://app.example.com/magic?token=abc123", "message": {"id": "msg-link"}}))
    raise SystemExit(0)

print(json.dumps({"ok": False, "message": f"unsupported command: {command}"}))
raise SystemExit(1)
"""


def write_profile(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_browse = tmp / "fake-browse"
        fake_email = tmp / "fake-email"
        write_executable(fake_browse, textwrap.dedent(FAKE_BROWSE))
        write_executable(fake_email, textwrap.dedent(FAKE_EMAIL))

        base_env = os.environ.copy()
        base_env["AGENT_DO_AUTH_BROWSE_CMD"] = str(fake_browse)
        base_env["AGENT_DO_AUTH_EMAIL_CMD"] = str(fake_email)
        base_env["AUTH_SESSION_MASTER_KEY_V1"] = "test-master-key"
        base_env["APP_EXAMPLE_COM_EMAIL"] = "agent@example.com"
        base_env["APP_EXAMPLE_COM_PASSWORD"] = "super-secret"

        code_home = tmp / "code-home"
        code_env = dict(base_env)
        code_env["AGENT_DO_HOME"] = str(code_home)
        code_env["FAKE_BROWSE_ROOT"] = str(tmp / "code-browse-state")

        init_seed = run(
            str(AGENT_DO),
            "auth",
            "init",
            "seeded-email",
            "--domain",
            "app.example.com",
            "--login-url",
            "https://app.example.com/login",
            "--email-code",
            "--email-from",
            "WidgetHub",
            "--email-subject",
            "verification code",
            "--json",
            cwd=ROOT,
            env=code_env,
        )
        require(init_seed.returncode == 0, f"auth init with email challenge failed: {init_seed.stderr}")
        show_seed = run(str(AGENT_DO), "auth", "show", "seeded-email", "--json", cwd=ROOT, env=code_env)
        require(show_seed.returncode == 0, f"auth show seeded-email failed: {show_seed.stderr}")
        show_seed_payload = json.loads(show_seed.stdout)
        require(
            show_seed_payload["profile"]["email_challenge"]["type"] == "code",
            f"expected seeded email challenge profile: {show_seed_payload}",
        )

        code_profile = code_home / "auth" / "profiles" / "app-code.yaml"
        write_profile(
            code_profile,
            """
            id: app-code
            title: App Code
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
            email_challenge:
              type: code
              from_contains: WidgetHub
              subject_contains: verification code
              code_length: 6
              timeout_seconds: 30
              poll_interval_seconds: 1
            """,
        )

        ensure_code = run(str(AGENT_DO), "auth", "ensure", "app-code", "--json", cwd=ROOT, env=code_env)
        require(ensure_code.returncode == 0, f"auth email code ensure failed: {ensure_code.stderr}")

        link_home = tmp / "link-home"
        link_env = dict(base_env)
        link_env["AGENT_DO_HOME"] = str(link_home)
        link_env["FAKE_BROWSE_ROOT"] = str(tmp / "link-browse-state")
        link_env["FAKE_AUTH_EMAIL_MODE"] = "link"
        link_profile = link_home / "auth" / "profiles" / "app-link.yaml"
        write_profile(
            link_profile,
            """
            id: app-link
            title: App Link
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
            email_challenge:
              type: link
              from_contains: WidgetHub
              domain: app.example.com
              timeout_seconds: 30
              poll_interval_seconds: 1
            """,
        )

        ensure_link = run(str(AGENT_DO), "auth", "ensure", "app-link", "--json", cwd=ROOT, env=link_env)
        require(ensure_link.returncode == 0, f"auth email link ensure failed: {ensure_link.stderr}")

        timeout_home = tmp / "timeout-home"
        timeout_env = dict(base_env)
        timeout_env["AGENT_DO_HOME"] = str(timeout_home)
        timeout_env["FAKE_BROWSE_ROOT"] = str(tmp / "timeout-browse-state")
        timeout_env["FAKE_AUTH_EMAIL_MODE"] = "code"
        timeout_env["FAKE_AUTH_EMAIL_TIMEOUT"] = "1"
        timeout_profile = timeout_home / "auth" / "profiles" / "app-timeout.yaml"
        write_profile(
            timeout_profile,
            """
            id: app-timeout
            title: App Timeout
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
            email_challenge:
              type: code
              from_contains: WidgetHub
              subject_contains: verification code
              code_length: 6
              timeout_seconds: 5
              poll_interval_seconds: 1
            """,
        )

        ensure_timeout = run(str(AGENT_DO), "auth", "ensure", "app-timeout", "--json", cwd=ROOT, env=timeout_env)
        require(ensure_timeout.returncode == 1, f"expected email timeout failure: {ensure_timeout.stdout} {ensure_timeout.stderr}")
        require("EMAIL_CHALLENGE_TIMEOUT" in ensure_timeout.stdout, f"expected email timeout action_required: {ensure_timeout.stdout}")

    print("auth email challenge tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
