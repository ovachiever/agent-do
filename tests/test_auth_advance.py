#!/usr/bin/env python3
"""Checkpoint advancement tests for agent-do auth."""

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
mode = os.environ.get("FAKE_AUTH_ADVANCE_MODE", "email")
command = args[0]

if command == "open":
    url = args[1]
    if "login" in url:
        current = {
            "page": "login",
            "url": url,
            "text": "Sign in",
            "selectors": ["input[type=\\"email\\"]", "input[type=\\"password\\"]", "button[type=\\"submit\\"]"],
            "fields": {},
        }
    elif "magic?token=fresh123" in url or "magic?token=abc123" in url:
        current = dashboard()
    else:
        current = {"page": "other", "url": url, "text": "Other", "selectors": [], "fields": {}}
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
    if current.get("page") == "device-approval" and os.environ.get("FAKE_DEVICE_APPROVAL_RESOLVE") == "1":
        current = dashboard()
        save_current(current)
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
        if mode == "email":
            current = {
                "page": "email_code",
                "url": "https://app.example.com/verify",
                "text": "Enter the verification code we emailed you",
                "selectors": ["input[name=\\"code\\"]", "button[type=\\"submit\\"]"],
                "fields": fields,
            }
        elif mode == "passkey":
            current = {
                "page": "passkey",
                "url": "https://app.example.com/passkey",
                "text": "Use a passkey to continue",
                "selectors": [],
                "fields": fields,
            }
        elif mode == "backup":
            current = {
                "page": "backup",
                "url": "https://app.example.com/recovery",
                "text": "Use a recovery code",
                "selectors": ['input[name="recovery_code"]', 'button[type="submit"]'],
                "fields": fields,
            }
        elif mode == "device":
            current = {
                "page": "device-approval",
                "url": "https://app.example.com/device",
                "text": "Check your phone to approve sign in",
                "selectors": [],
                "fields": fields,
            }
        elif mode == "device-alt":
            current = {
                "page": "device-approval",
                "url": "https://app.example.com/device",
                "text": "Check your phone to approve sign in",
                "selectors": ['text=Try another way'],
                "fields": fields,
            }
        save_current(current)
        success({"clicked": True, "selector": selector})
    if page == "device-approval" and selector == "text=Try another way":
        current = {
            "page": "totp",
            "url": "https://app.example.com/totp",
            "text": "Enter the code from your authenticator app",
            "selectors": ["input[name=\\"app_otp\\"]", "button[type=\\"submit\\"]"],
            "fields": fields,
        }
        save_current(current)
        success({"clicked": True, "selector": selector})
    if page == "totp" and selector == "button[type=\\"submit\\"]":
        if fields.get("input[name=\\"app_otp\\"]") == "123456":
            current = dashboard()
            save_current(current)
            success({"clicked": True, "selector": selector})
        fail("wrong totp code")
    if page == "email_code" and selector == "button[type=\\"submit\\"]":
        if fields.get("input[name=\\"code\\"]") == "731902":
            current = dashboard()
            save_current(current)
            success({"clicked": True, "selector": selector})
        fail("wrong email code")
    if page == "backup" and selector == "button[type=\\"submit\\"]":
        if any(value for key, value in fields.items() if "recovery" in key or "backup" in key):
            current = dashboard()
            save_current(current)
            success({"clicked": True, "selector": selector})
        fail("wrong backup code")
    if page == "chooser" and selector == "[data-login=\\"agent\\"]":
        current = {
            "page": "consent",
            "url": "https://widgethub.example.com/consent",
            "text": "Authorize WidgetHub to access your account",
            "selectors": ["button[name=\\"authorize\\"]"],
            "fields": {},
        }
        save_current(current)
        success({"clicked": True, "selector": selector})
    if page == "consent" and selector == "button[name=\\"authorize\\"]":
        current = dashboard()
        save_current(current)
        success({"clicked": True, "selector": selector})
    fail(f"unsupported click: {selector} on {page}")

if command == "auth" and args[1] == "autofill":
    current.setdefault("fields", {})["input[type=\\"email\\"]"] = args[2]
    current.setdefault("fields", {})["input[type=\\"password\\"]"] = args[3]
    if "--submit" in args:
        selector = "button[type=\\"submit\\"]"
        if selector not in current.get("selectors", []):
            current.setdefault("selectors", []).append(selector)
        save_current(current)
        # Reuse the click path so each mode lands on the right checkpoint page.
        args = ["click", selector]
        command = "click"
        selector = args[1]
        page = current.get("page")
        fields = current.get("fields", {})
        if page == "login" and selector == "button[type=\\"submit\\"]":
            if mode == "email":
                current = {
                    "page": "email_code",
                    "url": "https://app.example.com/verify",
                    "text": "Enter the verification code we emailed you",
                    "selectors": ["input[name=\\"code\\"]", "button[type=\\"submit\\"]"],
                    "fields": fields,
                }
            elif mode == "passkey":
                current = {
                    "page": "passkey",
                    "url": "https://app.example.com/passkey",
                    "text": "Use a passkey to continue",
                    "selectors": [],
                    "fields": fields,
                }
            elif mode == "backup":
                current = {
                    "page": "backup",
                    "url": "https://app.example.com/recovery",
                    "text": "Use a recovery code",
                    "selectors": ['input[name="recovery_code"]', 'button[type="submit"]'],
                    "fields": fields,
                }
            elif mode == "device":
                current = {
                    "page": "device-approval",
                    "url": "https://app.example.com/device",
                    "text": "Check your phone to approve sign in",
                    "selectors": [],
                    "fields": fields,
                }
            elif mode == "device-alt":
                current = {
                    "page": "device-approval",
                    "url": "https://app.example.com/device",
                    "text": "Check your phone to approve sign in",
                    "selectors": ['text=Try another way'],
                    "fields": fields,
                }
            save_current(current)
    else:
        save_current(current)
    success({"filled": True})

if command == "auth" and args[1] == "detect-login":
    success({"found": current.get("page") == "login"})

if command == "auth" and args[1] == "detect-captcha":
    success({"hasCaptcha": False, "types": []})

if command == "auth" and args[1] == "totp":
    success({"code": "123456"})

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
        success({"exported": True, "name": name})
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


FAKE_MACOS = """\
#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

current_path = Path(os.environ["FAKE_BROWSE_ROOT"]) / "current.json"
args = sys.argv[1:]

def current():
    if current_path.exists():
        return json.loads(current_path.read_text())
    return {"page": "blank"}

if args == ["permissions"]:
    print(json.dumps({"granted": True}))
    raise SystemExit(0)

if args == ["frontmost"]:
    print(json.dumps({"app": "Safari", "pid": 123}))
    raise SystemExit(0)

if args == ["dialog", "detect"]:
    page = current().get("page")
    if page == "passkey":
        print(json.dumps({"type": "dialog", "title": "Use Passkey?", "buttons": ["Cancel", "Continue"], "app": "Safari"}))
    else:
        print(json.dumps({"type": None, "message": "No dialog detected"}))
    raise SystemExit(0)

if args == ["dialog", "click", "--default"]:
    data = current()
    if data.get("page") == "passkey":
        current_path.write_text(json.dumps({"page": "dashboard", "url": "https://app.example.com/dashboard", "text": "Dashboard", "selectors": [], "fields": {}}))
        print(json.dumps({"ok": True, "clicked": "--default"}))
        raise SystemExit(0)
    print(json.dumps({"error": "No default dialog action available"}))
    raise SystemExit(1)

print(json.dumps({"error": f"unsupported args: {args}"}))
raise SystemExit(1)
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
exclude_ids = []
i = 1
while i < len(args):
    if args[i] == "--exclude-id" and i + 1 < len(args):
        exclude_ids.append(args[i + 1])
        i += 2
    else:
        i += 1

if command == "snapshot":
    print(json.dumps({
        "ok": True,
        "platform": "fixture",
        "accounts": {"count": 1, "items": [{"name": "Primary", "type": "IMAP"}]},
        "inbox_unread": 1,
        "recent_messages": {
            "count": 1,
            "items": [
                {
                    "id": "msg-old-code",
                    "subject": "Verification email",
                    "from": "WidgetHub <login@widgethub.com>",
                    "status": "unread",
                    "date": "2026-04-12T12:00:00Z",
                    "body": "Old verification message",
                }
            ],
        },
    }))
    raise SystemExit(0)

if os.environ.get("FAKE_AUTH_EMAIL_TIMEOUT") == "1":
    print(json.dumps({"ok": False, "message": "Timed out waiting for matching email"}))
    raise SystemExit(1)

if command == "code":
    code = "731902" if "msg-old-code" in exclude_ids else "000000"
    print(json.dumps({
        "ok": True,
        "code": code,
        "message": {
            "id": "msg-fresh-code",
            "subject": "Verification email",
            "from": "WidgetHub <login@widgethub.com>",
            "body": f"Your verification code is {code}",
        },
    }))
    raise SystemExit(0)

print(json.dumps({"ok": False, "message": f"unsupported args: {args}"}))
raise SystemExit(1)
"""


def seed_profile(home: Path, site: str, body: str) -> None:
    write_profile(home / "auth" / "profiles" / f"{site}.yaml", body)


def seed_current(root: Path, payload: dict[str, object]) -> None:
    (root / "current.json").write_text(json.dumps(payload), encoding="utf-8")


def base_env(tmp: Path, name: str, mode: str) -> dict[str, str]:
    env = os.environ.copy()
    env["AGENT_DO_HOME"] = str(tmp / name)
    env["FAKE_BROWSE_ROOT"] = str(tmp / f"{name}-browse")
    env["AGENT_DO_AUTH_BROWSE_CMD"] = str(tmp / "fake-browse")
    env["AGENT_DO_AUTH_MACOS_CMD"] = str(tmp / "fake-macos")
    env["AGENT_DO_AUTH_EMAIL_CMD"] = str(tmp / "fake-email")
    env["FAKE_AUTH_ADVANCE_MODE"] = mode
    return env


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        write_executable(tmp / "fake-browse", textwrap.dedent(FAKE_BROWSE))
        write_executable(tmp / "fake-macos", textwrap.dedent(FAKE_MACOS))
        write_executable(tmp / "fake-email", textwrap.dedent(FAKE_EMAIL))

        email_env = base_env(tmp, "email-home", "email")
        email_env["APP_EMAIL_ADVANCE_EMAIL"] = "agent@example.com"
        email_env["APP_EMAIL_ADVANCE_PASSWORD"] = "super-secret"
        email_home = Path(email_env["AGENT_DO_HOME"])
        seed_profile(
            email_home,
            "app-email-advance",
            """
            id: app-email-advance
            title: Email Advance
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
            provider:
              type: generic
            credentials:
              site:
                username: APP_EMAIL_ADVANCE_EMAIL
                password: APP_EMAIL_ADVANCE_PASSWORD
            email_challenge:
              type: code
              from_contains: WidgetHub
              subject_contains: Verification
            """,
        )
        email_env["FAKE_AUTH_EMAIL_TIMEOUT"] = "1"
        ensure_email = run(str(AGENT_DO), "auth", "ensure", "app-email-advance", "--json", cwd=ROOT, env=email_env)
        require(ensure_email.returncode == 1, f"email ensure should stop at checkpoint: {ensure_email.stdout} {ensure_email.stderr}")
        ensure_email_payload = json.loads(ensure_email.stdout)
        require(ensure_email_payload["action_required"] == "EMAIL_CHALLENGE_TIMEOUT", f"unexpected email ensure payload: {ensure_email_payload}")
        email_env.pop("FAKE_AUTH_EMAIL_TIMEOUT", None)
        advance_email = run(str(AGENT_DO), "auth", "advance", "app-email-advance", "--json", cwd=ROOT, env=email_env)
        require(advance_email.returncode == 0, f"email advance failed: {advance_email.stdout} {advance_email.stderr}")
        advance_email_payload = json.loads(advance_email.stdout)
        require(advance_email_payload["validated"] is True, f"email advance did not validate: {advance_email_payload}")
        require(advance_email_payload["action_taken"]["action_required"] == "EMAIL_CHALLENGE_PENDING", f"unexpected email action: {advance_email_payload}")
        require(advance_email_payload["after"]["state"] == "authenticated", f"email advance wrong state: {advance_email_payload}")

        passkey_env = base_env(tmp, "passkey-home", "passkey")
        passkey_env["APP_PASSKEY_ADVANCE_EMAIL"] = "agent@example.com"
        passkey_env["APP_PASSKEY_ADVANCE_PASSWORD"] = "super-secret"
        passkey_home = Path(passkey_env["AGENT_DO_HOME"])
        seed_profile(
            passkey_home,
            "app-passkey-advance",
            """
            id: app-passkey-advance
            title: Passkey Advance
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
            provider:
              type: generic
            credentials:
              site:
                username: APP_PASSKEY_ADVANCE_EMAIL
                password: APP_PASSKEY_ADVANCE_PASSWORD
            """,
        )
        ensure_passkey = run(str(AGENT_DO), "auth", "ensure", "app-passkey-advance", "--json", cwd=ROOT, env=passkey_env)
        require(ensure_passkey.returncode == 1, f"passkey ensure should stop at checkpoint: {ensure_passkey.stdout} {ensure_passkey.stderr}")
        ensure_passkey_payload = json.loads(ensure_passkey.stdout)
        require(ensure_passkey_payload["action_required"] == "PASSKEY_CHALLENGE_REQUIRED", f"unexpected passkey ensure payload: {ensure_passkey_payload}")
        advance_passkey = run(str(AGENT_DO), "auth", "advance", "app-passkey-advance", "--json", cwd=ROOT, env=passkey_env)
        require(advance_passkey.returncode == 0, f"passkey advance failed: {advance_passkey.stdout} {advance_passkey.stderr}")
        advance_passkey_payload = json.loads(advance_passkey.stdout)
        require(advance_passkey_payload["validated"] is True, f"passkey advance did not validate: {advance_passkey_payload}")
        require(advance_passkey_payload["action_taken"]["action_required"] == "PASSKEY_CHALLENGE_REQUIRED", f"unexpected passkey action: {advance_passkey_payload}")

        device_env = base_env(tmp, "device-home", "device")
        device_env["APP_DEVICE_ADVANCE_EMAIL"] = "agent@example.com"
        device_env["APP_DEVICE_ADVANCE_PASSWORD"] = "super-secret"
        device_home = Path(device_env["AGENT_DO_HOME"])
        seed_profile(
            device_home,
            "app-device-advance",
            """
            id: app-device-advance
            title: Device Advance
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
            provider:
              type: generic
            credentials:
              site:
                username: APP_DEVICE_ADVANCE_EMAIL
                password: APP_DEVICE_ADVANCE_PASSWORD
            """,
        )
        ensure_device = run(str(AGENT_DO), "auth", "ensure", "app-device-advance", "--json", cwd=ROOT, env=device_env)
        require(ensure_device.returncode == 1, f"device ensure should stop at checkpoint: {ensure_device.stdout} {ensure_device.stderr}")
        ensure_device_payload = json.loads(ensure_device.stdout)
        require(ensure_device_payload["action_required"] == "DEVICE_APPROVAL_REQUIRED", f"unexpected device ensure payload: {ensure_device_payload}")
        device_env["FAKE_DEVICE_APPROVAL_RESOLVE"] = "1"
        advance_device = run(str(AGENT_DO), "auth", "advance", "app-device-advance", "--json", "--timeout", "2", "--interval", "1", cwd=ROOT, env=device_env)
        require(advance_device.returncode == 0, f"device advance failed: {advance_device.stdout} {advance_device.stderr}")
        advance_device_payload = json.loads(advance_device.stdout)
        require(advance_device_payload["validated"] is True, f"device advance did not validate: {advance_device_payload}")
        require(advance_device_payload["action_taken"]["action_required"] == "DEVICE_APPROVAL_REQUIRED", f"unexpected device action: {advance_device_payload}")

        device_alt_env = base_env(tmp, "device-alt-home", "device-alt")
        device_alt_env["APP_DEVICE_ALT_EMAIL"] = "agent@example.com"
        device_alt_env["APP_DEVICE_ALT_PASSWORD"] = "super-secret"
        device_alt_env["APP_DEVICE_ALT_TOTP_SECRET"] = "dummy-secret"
        device_alt_home = Path(device_alt_env["AGENT_DO_HOME"])
        seed_profile(
            device_alt_home,
            "app-device-alt",
            """
            id: app-device-alt
            title: Device Alternate
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
            provider:
              type: generic
            credentials:
              site:
                username: APP_DEVICE_ALT_EMAIL
                password: APP_DEVICE_ALT_PASSWORD
              totp:
                secret: APP_DEVICE_ALT_TOTP_SECRET
            """,
        )
        ensure_device_alt = run(str(AGENT_DO), "auth", "ensure", "app-device-alt", "--json", cwd=ROOT, env=device_alt_env)
        require(ensure_device_alt.returncode == 1, f"device-alt ensure should stop at checkpoint: {ensure_device_alt.stdout} {ensure_device_alt.stderr}")
        ensure_device_alt_payload = json.loads(ensure_device_alt.stdout)
        require(ensure_device_alt_payload["action_required"] == "DEVICE_APPROVAL_REQUIRED", f"unexpected device-alt ensure payload: {ensure_device_alt_payload}")
        advance_device_alt = run(str(AGENT_DO), "auth", "advance", "app-device-alt", "--json", cwd=ROOT, env=device_alt_env)
        require(advance_device_alt.returncode == 0, f"device-alt advance failed: {advance_device_alt.stdout} {advance_device_alt.stderr}")
        advance_device_alt_payload = json.loads(advance_device_alt.stdout)
        require(advance_device_alt_payload["validated"] is False, f"device-alt advance should still be on a challenge branch: {advance_device_alt_payload}")
        require(advance_device_alt_payload["action_taken"]["alternate_selector"] == "text=Try another way", f"expected alternate method click: {advance_device_alt_payload}")
        require(
            any(item["action_required"] == "TOTP_REQUIRED" for item in advance_device_alt_payload["after"]["checkpoints"]),
            f"device-alt advance should shift to TOTP challenge: {advance_device_alt_payload}",
        )
        advance_device_alt_totp = run(str(AGENT_DO), "auth", "advance", "app-device-alt", "--json", cwd=ROOT, env=device_alt_env)
        require(advance_device_alt_totp.returncode == 0, f"device-alt totp advance failed: {advance_device_alt_totp.stdout} {advance_device_alt_totp.stderr}")
        advance_device_alt_totp_payload = json.loads(advance_device_alt_totp.stdout)
        require(advance_device_alt_totp_payload["validated"] is True, f"device-alt totp advance did not validate: {advance_device_alt_totp_payload}")

        chooser_env = base_env(tmp, "chooser-home", "chooser")
        chooser_env["GITHUB_EMAIL"] = "agent@example.com"
        chooser_home = Path(chooser_env["AGENT_DO_HOME"])
        seed_profile(
            chooser_home,
            "widgethub-chooser",
            """
            id: widgethub-chooser
            title: WidgetHub Chooser
            domains:
              - widgethub.example.com
            login_url: https://widgethub.example.com/login
            validation:
              url_patterns:
                - https://app.example.com/dashboard*
              signed_out_markers:
                - Sign in
              signed_in_markers:
                - Dashboard
            strategies:
              - provider-refresh
            provider:
              type: github
              refresh:
                account_selectors:
                  - '[data-login="{local_part}"]'
                consent_selectors:
                  - 'button[name="authorize"]'
            """,
        )
        browse_root = Path(chooser_env["FAKE_BROWSE_ROOT"])
        browse_root.mkdir(parents=True, exist_ok=True)
        seed_current(
            browse_root,
            {
                "page": "chooser",
                "url": "https://github.com/login/oauth/authorize",
                "text": "Choose an account",
                "selectors": ['[data-login="agent"]'],
                "fields": {},
            },
        )
        advance_chooser = run(str(AGENT_DO), "auth", "advance", "widgethub-chooser", "--json", cwd=ROOT, env=chooser_env)
        require(advance_chooser.returncode == 0, f"chooser advance failed: {advance_chooser.stdout} {advance_chooser.stderr}")
        advance_chooser_payload = json.loads(advance_chooser.stdout)
        require(advance_chooser_payload["validated"] is False, f"chooser advance should still need consent: {advance_chooser_payload}")
        require(advance_chooser_payload["action_taken"]["action_required"] == "ACCOUNT_CHOOSER_REQUIRED", f"unexpected chooser action: {advance_chooser_payload}")
        require(
            any(item["action_required"] == "CONSENT_REQUIRED" for item in advance_chooser_payload["after"]["checkpoints"]),
            f"chooser advance should surface consent next: {advance_chooser_payload}",
        )

        advance_consent = run(str(AGENT_DO), "auth", "advance", "widgethub-chooser", "--json", cwd=ROOT, env=chooser_env)
        require(advance_consent.returncode == 0, f"consent advance failed: {advance_consent.stdout} {advance_consent.stderr}")
        advance_consent_payload = json.loads(advance_consent.stdout)
        require(advance_consent_payload["validated"] is True, f"consent advance did not validate: {advance_consent_payload}")
        require(advance_consent_payload["action_taken"]["action_required"] == "CONSENT_REQUIRED", f"unexpected consent action: {advance_consent_payload}")

    print("auth advance tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
