#!/usr/bin/env python3
"""Provider-aware auth adapter tests for agent-do auth."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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


def github_success():
    return {
        "page": "github_success",
        "url": "https://github.com/settings/profile",
        "text": "View profile and more",
        "selectors": [],
        "fields": {},
    }


def google_success():
    return {
        "page": "google_success",
        "url": "https://myaccount.google.com/",
        "text": "Manage your Google Account",
        "selectors": [],
        "fields": {},
    }


def maybe_require_totp(provider):
    return os.environ.get(f"FAKE_{provider.upper()}_REQUIRE_TOTP", "0") == "1"


def maybe_require_backup(provider):
    return os.environ.get(f"FAKE_{provider.upper()}_REQUIRE_BACKUP", "0") == "1"


args = sys.argv[1:]
if args and args[0] == "--json":
    args = args[1:]

if not args:
    fail("missing command")

current = load_current()
command = args[0]

if command == "open":
    url = args[1]
    if "github.com/login" in url:
        current = {
            "page": "github_login",
            "url": url,
            "text": "Sign in to GitHub",
            "selectors": ["#login_field", "#password", "input[name=\\"commit\\"]"],
            "fields": {},
        }
    elif "accounts.google.com" in url:
        current = {
            "page": "google_email",
            "url": url,
            "text": "Sign in - Google Accounts",
            "selectors": ["input[type=\\"email\\"]", "#identifierNext"],
            "fields": {},
        }
    else:
        current = {
            "page": "generic_login",
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
    fields = current.setdefault("fields", {})
    fields[selector] = value
    save_current(current)
    success({"filled": True, "selector": selector})

if command == "click":
    selector = args[1]
    page = current.get("page")
    fields = current.setdefault("fields", {})

    if page == "github_login" and selector in {"input[name=\\"commit\\"]", "input[type=\\"submit\\"]", "button[type=\\"submit\\"]"}:
        if maybe_require_totp("github"):
            current = {
                "page": "github_totp",
                "url": "https://github.com/sessions/two-factor",
                "text": "Two-factor authentication",
                "selectors": ["input[name=\\"app_otp\\"]", "button[type=\\"submit\\"]"],
                "fields": fields,
            }
        elif maybe_require_backup("github"):
            current = {
                "page": "github_backup",
                "url": "https://github.com/sessions/recovery",
                "text": "Use a recovery code",
                "selectors": ["input[name=\\"recovery_code\\"]", "button[type=\\"submit\\"]"],
                "fields": fields,
            }
        else:
            current = github_success()
        save_current(current)
        success({"clicked": True})

    if page == "github_totp" and selector in {"button[type=\\"submit\\"]", "input[type=\\"submit\\"]"}:
        if fields.get("input[name=\\"app_otp\\"]"):
            current = github_success()
            save_current(current)
            success({"clicked": True})
        fail("missing github totp code")

    if page == "github_backup" and selector in {"button[type=\\"submit\\"]", "input[type=\\"submit\\"]"}:
        if any(value for key, value in fields.items() if "recovery" in key or "backup" in key):
            current = github_success()
            save_current(current)
            success({"clicked": True})
        fail("missing github backup code")

    if page == "google_email" and selector in {"#identifierNext", "#identifierNext button", "button[type=\\"button\\"]"}:
        current = {
            "page": "google_password",
            "url": "https://accounts.google.com/v3/signin/challenge/pwd",
            "text": "Enter your password",
            "selectors": ["input[type=\\"password\\"]", "#passwordNext"],
            "fields": fields,
        }
        save_current(current)
        success({"clicked": True})

    if page == "google_password" and selector in {"#passwordNext", "#passwordNext button", "button[type=\\"button\\"]"}:
        if maybe_require_totp("google"):
            current = {
                "page": "google_totp",
                "url": "https://accounts.google.com/v3/signin/challenge/totp",
                "text": "2-Step Verification",
                "selectors": ["input[name=\\"totpPin\\"]", "#totpNext"],
                "fields": fields,
            }
        elif maybe_require_backup("google"):
            current = {
                "page": "google_backup",
                "url": "https://accounts.google.com/v3/signin/challenge/backup",
                "text": "Enter one of your 8-digit backup codes",
                "selectors": ["input[name=\\"backupCode\\"]", "button[type=\\"button\\"]"],
                "fields": fields,
            }
        else:
            current = google_success()
        save_current(current)
        success({"clicked": True})

    if page == "google_totp" and selector in {"#totpNext", "#totpNext button", "button[type=\\"button\\"]"}:
        if fields.get("input[name=\\"totpPin\\"]"):
            current = google_success()
            save_current(current)
            success({"clicked": True})
        fail("missing google totp code")

    if page == "google_backup" and selector in {"button[type=\\"button\\"]", "button[type=\\"submit\\"]", "input[type=\\"submit\\"]"}:
        if any(value for key, value in fields.items() if "backup" in key or "recovery" in key):
            current = google_success()
            save_current(current)
            success({"clicked": True})
        fail("missing google backup code")

    if page == "generic_login" and selector in {"button[type=\\"submit\\"]", "input[type=\\"submit\\"]"}:
        current = {
            "page": "generic_success",
            "url": current.get("url", "").replace("/login", "/dashboard"),
            "text": "Dashboard",
            "selectors": [],
            "fields": {},
        }
        save_current(current)
        success({"clicked": True})

    fail(f"unsupported click: {selector} on {page}")

if command == "auth" and args[1] == "autofill":
    username = args[2]
    password = args[3]
    page = current.get("page")
    if page == "generic_login":
        current.setdefault("fields", {})["input[type=\\"email\\"]"] = username
        current.setdefault("fields", {})["input[type=\\"password\\"]"] = password
        if "--submit" in args:
            current = {
                "page": "generic_success",
                "url": current.get("url", "").replace("/login", "/dashboard"),
                "text": "Dashboard",
                "selectors": [],
                "fields": {},
            }
        save_current(current)
        success({"filled": True})
    fail(f"unsupported autofill page: {page}")

if command == "auth" and args[1] == "totp":
    code = "123456"
    if "--fill" in args:
        selector = args[args.index("--fill") + 1]
        current.setdefault("fields", {})[selector] = code
        save_current(current)
        success({"code": code, "filled": selector})
    success({"code": code})

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
        name = args[2]
        state = github_success()
        session_file(name).write_text(json.dumps(state))
        success({"imported": True, "name": name})

fail(f"unsupported args: {args}")
"""


def base_env(tmp: Path, fake_browse: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["AGENT_DO_HOME"] = str(tmp / "home")
    env["AGENT_DO_AUTH_BROWSE_CMD"] = str(fake_browse)
    env["FAKE_BROWSE_ROOT"] = str(tmp / "fake-browse-state")
    env["AUTH_SESSION_MASTER_KEY_V1"] = "test-master-key"
    return env


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_browse = tmp / "fake-browse"
        write_executable(fake_browse, textwrap.dedent(FAKE_BROWSE))

        github_env = base_env(tmp / "github-case", fake_browse)
        github_env["GITHUB_EMAIL"] = "agent@example.com"
        github_env["GITHUB_PASSWORD"] = "super-secret"
        github_env["GITHUB_TOTP_SECRET"] = "JBSWY3DPEHPK3PXP"
        github_env["FAKE_GITHUB_REQUIRE_TOTP"] = "1"

        init = run(str(AGENT_DO), "auth", "init", "github", "--no-browser-import", "--json", cwd=ROOT, env=github_env)
        require(init.returncode == 0, f"github auth init failed: {init.stderr}")

        ensure = run(str(AGENT_DO), "auth", "ensure", "github", "--json", cwd=ROOT, env=github_env)
        require(ensure.returncode == 0, f"github auth ensure failed: {ensure.stderr}")
        ensure_payload = json.loads(ensure.stdout)
        require(ensure_payload["strategy_used"] == "site-creds", f"unexpected github ensure payload: {ensure_payload}")

        github_status = run(str(AGENT_DO), "auth", "status", "github", "--json", cwd=ROOT, env=github_env)
        require(github_status.returncode == 0, f"github auth status failed: {github_status.stderr}")
        github_status_payload = json.loads(github_status.stdout)
        require(github_status_payload["state"] == "authenticated", f"unexpected github auth state: {github_status_payload}")

        google_env = base_env(tmp / "google-case", fake_browse)
        google_env["GOOGLE_EMAIL"] = "agent@example.com"
        google_env["GOOGLE_PASSWORD"] = "super-secret"
        google_env["GOOGLE_TOTP_SECRET"] = "JBSWY3DPEHPK3PXP"
        google_env["FAKE_GOOGLE_REQUIRE_TOTP"] = "1"

        init_google = run(str(AGENT_DO), "auth", "init", "google", "--no-browser-import", "--json", cwd=ROOT, env=google_env)
        require(init_google.returncode == 0, f"google auth init failed: {init_google.stderr}")

        ensure_google = run(str(AGENT_DO), "auth", "ensure", "google", "--json", cwd=ROOT, env=google_env)
        require(ensure_google.returncode == 0, f"google auth ensure failed: {ensure_google.stderr}")
        ensure_google_payload = json.loads(ensure_google.stdout)
        require(ensure_google_payload["strategy_used"] == "site-creds", f"unexpected google ensure payload: {ensure_google_payload}")

        github_backup_env = base_env(tmp / "github-backup", fake_browse)
        github_backup_env["GITHUB_EMAIL"] = "agent@example.com"
        github_backup_env["GITHUB_PASSWORD"] = "super-secret"
        github_backup_env["GITHUB_BACKUP_CODES"] = "backup-one backup-two"
        github_backup_env["FAKE_GITHUB_REQUIRE_BACKUP"] = "1"

        init_github_backup = run(str(AGENT_DO), "auth", "init", "github", "--no-browser-import", "--json", cwd=ROOT, env=github_backup_env)
        require(init_github_backup.returncode == 0, f"github backup init failed: {init_github_backup.stderr}")

        ensure_github_backup = run(str(AGENT_DO), "auth", "ensure", "github", "--json", cwd=ROOT, env=github_backup_env)
        require(ensure_github_backup.returncode == 0, f"github backup ensure failed: {ensure_github_backup.stdout} {ensure_github_backup.stderr}")
        ensure_github_backup_payload = json.loads(ensure_github_backup.stdout)
        require(ensure_github_backup_payload["strategy_used"] == "site-creds", f"unexpected github backup payload: {ensure_github_backup_payload}")

        backup_state_path = Path(github_backup_env["AGENT_DO_HOME"]) / "auth" / "backup-codes.json"
        backup_state = json.loads(backup_state_path.read_text())
        require(len((backup_state.get("GITHUB_BACKUP_CODES") or {}).get("used", [])) == 1, f"expected one used github backup code: {backup_state}")

        clear_github_backup = run(str(AGENT_DO), "auth", "clear", "github", "--json", cwd=ROOT, env=github_backup_env)
        require(clear_github_backup.returncode == 0, f"github backup clear failed: {clear_github_backup.stderr}")
        ensure_github_backup_second = run(str(AGENT_DO), "auth", "ensure", "github", "--json", cwd=ROOT, env=github_backup_env)
        require(ensure_github_backup_second.returncode == 0, f"github second backup ensure failed: {ensure_github_backup_second.stdout} {ensure_github_backup_second.stderr}")
        backup_state_second = json.loads(backup_state_path.read_text())
        require(len((backup_state_second.get("GITHUB_BACKUP_CODES") or {}).get("used", [])) == 2, f"expected two used github backup codes: {backup_state_second}")

        google_backup_env = base_env(tmp / "google-backup", fake_browse)
        google_backup_env["GOOGLE_EMAIL"] = "agent@example.com"
        google_backup_env["GOOGLE_PASSWORD"] = "super-secret"
        google_backup_env["GOOGLE_BACKUP_CODES"] = "12345678 87654321"
        google_backup_env["FAKE_GOOGLE_REQUIRE_BACKUP"] = "1"

        init_google_backup = run(str(AGENT_DO), "auth", "init", "google", "--no-browser-import", "--json", cwd=ROOT, env=google_backup_env)
        require(init_google_backup.returncode == 0, f"google backup init failed: {init_google_backup.stderr}")

        ensure_google_backup = run(str(AGENT_DO), "auth", "ensure", "google", "--json", cwd=ROOT, env=google_backup_env)
        require(ensure_google_backup.returncode == 0, f"google backup ensure failed: {ensure_google_backup.stdout} {ensure_google_backup.stderr}")
        ensure_google_backup_payload = json.loads(ensure_google_backup.stdout)
        require(ensure_google_backup_payload["strategy_used"] == "site-creds", f"unexpected google backup payload: {ensure_google_backup_payload}")

        missing_totp_env = base_env(tmp / "github-missing-totp", fake_browse)
        missing_totp_env["GITHUB_EMAIL"] = "agent@example.com"
        missing_totp_env["GITHUB_PASSWORD"] = "super-secret"
        missing_totp_env["FAKE_GITHUB_REQUIRE_TOTP"] = "1"
        missing_totp_env.pop("GITHUB_TOTP_SECRET", None)

        init_missing = run(str(AGENT_DO), "auth", "init", "github", "--no-browser-import", "--json", cwd=ROOT, env=missing_totp_env)
        require(init_missing.returncode == 0, f"github missing-totp init failed: {init_missing.stderr}")
        missing_totp_profile = Path(missing_totp_env["AGENT_DO_HOME"]) / "auth" / "profiles" / "github.yaml"
        missing_totp_profile.write_text(
            missing_totp_profile.read_text(encoding="utf-8").replace("GITHUB_TOTP_SECRET", "TEST_GITHUB_TOTP_SECRET_MISSING"),
            encoding="utf-8",
        )

        ensure_missing = run(str(AGENT_DO), "auth", "ensure", "github", "--json", cwd=ROOT, env=missing_totp_env)
        require(ensure_missing.returncode == 1, f"github missing-totp ensure should fail: {ensure_missing.stdout} {ensure_missing.stderr}")
        ensure_missing_payload = json.loads(ensure_missing.stdout)
        require(ensure_missing_payload["action_required"] == "MISSING_CREDENTIALS", f"unexpected missing-totp payload: {ensure_missing_payload}")
        require("TEST_GITHUB_TOTP_SECRET_MISSING" in ensure_missing_payload["missing"], f"expected missing github totp secret: {ensure_missing_payload}")

        instructions = run(str(AGENT_DO), "auth", "instructions", "github", "--json", cwd=ROOT, env=missing_totp_env)
        require(instructions.returncode == 0, f"github instructions failed: {instructions.stderr}")
        instructions_payload = json.loads(instructions.stdout)
        require(
            any("TEST_GITHUB_TOTP_SECRET_MISSING" in item for item in instructions_payload["guidance"]),
            f"expected TOTP guidance in instructions: {instructions_payload}",
        )

        missing_backup_env = base_env(tmp / "github-missing-backup", fake_browse)
        missing_backup_env["GITHUB_EMAIL"] = "agent@example.com"
        missing_backup_env["GITHUB_PASSWORD"] = "super-secret"
        missing_backup_env["FAKE_GITHUB_REQUIRE_BACKUP"] = "1"
        missing_backup_env.pop("GITHUB_BACKUP_CODES", None)

        init_missing_backup = run(str(AGENT_DO), "auth", "init", "github", "--no-browser-import", "--json", cwd=ROOT, env=missing_backup_env)
        require(init_missing_backup.returncode == 0, f"github missing-backup init failed: {init_missing_backup.stderr}")
        missing_backup_profile = Path(missing_backup_env["AGENT_DO_HOME"]) / "auth" / "profiles" / "github.yaml"
        missing_backup_profile.write_text(
            missing_backup_profile.read_text(encoding="utf-8").replace("GITHUB_BACKUP_CODES", "TEST_GITHUB_BACKUP_CODES_MISSING"),
            encoding="utf-8",
        )

        ensure_missing_backup = run(str(AGENT_DO), "auth", "ensure", "github", "--json", cwd=ROOT, env=missing_backup_env)
        require(ensure_missing_backup.returncode == 1, f"github missing-backup ensure should fail: {ensure_missing_backup.stdout} {ensure_missing_backup.stderr}")
        ensure_missing_backup_payload = json.loads(ensure_missing_backup.stdout)
        require(ensure_missing_backup_payload["action_required"] == "MISSING_CREDENTIALS", f"unexpected missing-backup payload: {ensure_missing_backup_payload}")
        require("TEST_GITHUB_BACKUP_CODES_MISSING" in ensure_missing_backup_payload["missing"], f"expected missing github backup codes: {ensure_missing_backup_payload}")

        instructions_backup = run(str(AGENT_DO), "auth", "instructions", "github", "--json", cwd=ROOT, env=missing_backup_env)
        require(instructions_backup.returncode == 0, f"github backup instructions failed: {instructions_backup.stderr}")
        instructions_backup_payload = json.loads(instructions_backup.stdout)
        require(
            any("TEST_GITHUB_BACKUP_CODES_MISSING" in item for item in instructions_backup_payload["guidance"]),
            f"expected backup-code guidance in instructions: {instructions_backup_payload}",
        )

    print("auth adapter tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
