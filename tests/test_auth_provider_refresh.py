#!/usr/bin/env python3
"""Provider refresh strategy tests for agent-do auth."""

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
    return {"page": "blank", "url": "about:blank", "text": "", "selectors": [], "fields": {}, "providers": []}


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
        "providers": ["github"],
    }


def app_login(providers):
    return {
        "page": "app_login",
        "url": "https://app.example.com/login",
        "text": "Login to WidgetHub",
        "selectors": ["text=Continue with GitHub"],
        "fields": {},
        "providers": providers,
    }


def app_dashboard():
    return {
        "page": "app_dashboard",
        "url": "https://app.example.com/dashboard",
        "text": "Dashboard",
        "selectors": [],
        "fields": {},
        "providers": ["github"],
    }


args = sys.argv[1:]
if args and args[0] == "--json":
    args = args[1:]

if not args:
    fail("missing command")

current = load_current()
command = args[0]

if command == "open":
    url = args[1]
    providers = current.get("providers", [])
    if "github.com/login" in url:
        current = {
            "page": "github_login",
            "url": url,
            "text": "Sign in to GitHub",
            "selectors": ["#login_field", "#password", "input[name=\\"commit\\"]"],
            "fields": {},
            "providers": providers,
        }
    elif "app.example.com/login" in url:
        current = app_login(providers)
    else:
        current = {"page": "generic", "url": url, "text": "", "selectors": [], "fields": {}, "providers": providers}
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
    fields = current.setdefault("fields", {})
    providers = current.get("providers", [])

    if page == "github_login" and selector in {"input[name=\\"commit\\"]", "button[type=\\"submit\\"]", "input[type=\\"submit\\"]"}:
        if os.environ.get("FAKE_GITHUB_REQUIRE_TOTP", "0") == "1":
            current = {
                "page": "github_totp",
                "url": "https://github.com/sessions/two-factor",
                "text": "Two-factor authentication",
                "selectors": ["input[name=\\"app_otp\\"]", "button[type=\\"submit\\"]"],
                "fields": fields,
                "providers": providers,
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

    if page == "app_login" and selector == "text=Continue with GitHub":
        if "github" not in providers:
            fail("github session missing")
        if os.environ.get("FAKE_GITHUB_ACCOUNT_CHOOSER", "0") == "1":
            account_email = os.environ.get("GITHUB_EMAIL", "agent@example.com")
            current = {
                "page": "github_account_chooser",
                "url": "https://github.com/account/choose",
                "text": "Choose an account",
                "selectors": [f"text={account_email}", f"text={account_email.split('@')[0]}"],
                "fields": {},
                "providers": providers,
            }
            save_current(current)
            success({"clicked": True})
        current = {
            "page": "github_authorize",
            "url": "https://github.com/login/oauth/authorize",
            "text": "Authorize WidgetHub",
            "selectors": ["text=Authorize"],
            "fields": {},
            "providers": providers,
        }
        save_current(current)
        success({"clicked": True})

    if page == "github_account_chooser" and selector in set(current.get("selectors", [])):
        current = {
            "page": "github_authorize",
            "url": "https://github.com/login/oauth/authorize",
            "text": "Authorize WidgetHub",
            "selectors": ["text=Authorize"],
            "fields": {},
            "providers": providers,
        }
        save_current(current)
        success({"clicked": True})

    if page == "github_authorize" and selector == "text=Authorize":
        current = app_dashboard()
        save_current(current)
        success({"clicked": True})

    fail(f"unsupported click: {selector} on {page}")

if command == "auth" and args[1] == "autofill":
    username = args[2]
    password = args[3]
    if current.get("page") != "github_login":
        fail(f"unsupported autofill page: {current.get('page')}")
    current.setdefault("fields", {})["#login_field"] = username
    current.setdefault("fields", {})["#password"] = password
    if "--submit" in args:
        if os.environ.get("FAKE_GITHUB_REQUIRE_TOTP", "0") == "1":
            current = {
                "page": "github_totp",
                "url": "https://github.com/sessions/two-factor",
                "text": "Two-factor authentication",
                "selectors": ["input[name=\\"app_otp\\"]", "button[type=\\"submit\\"]"],
                "fields": current.get("fields", {}),
                "providers": current.get("providers", []),
            }
        else:
            current = github_success()
    save_current(current)
    success({"filled": True})

if command == "auth" and args[1] == "totp":
    code = "123456"
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
        domain = ""
        if "--domain" in args:
            domain = args[args.index("--domain") + 1]
        if "github.com" in domain and os.environ.get("FAKE_GITHUB_BROWSER_IMPORT_FAIL", "0") != "1":
            session_file(name).write_text(json.dumps(github_success()))
        else:
            session_file(name).write_text(json.dumps(app_login([])))
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

        import_env = base_env(tmp / "import-case", fake_browse)
        init = run(
            str(AGENT_DO),
            "auth",
            "init",
            "widgethub",
            "--domain",
            "app.example.com",
            "--login-url",
            "https://app.example.com/login",
            "--provider",
            "github",
            "--json",
            cwd=ROOT,
            env=import_env,
        )
        require(init.returncode == 0, f"widgethub init failed: {init.stderr}")
        init_payload = json.loads(init.stdout)
        require("provider-refresh" in init_payload["strategies"], f"provider refresh missing from init: {init_payload}")

        instructions = run(str(AGENT_DO), "auth", "instructions", "widgethub", "--json", cwd=ROOT, env=import_env)
        require(instructions.returncode == 0, f"widgethub instructions failed: {instructions.stderr}")
        instructions_payload = json.loads(instructions.stdout)
        require(
            any("Provider refresh can reuse GitHub auth" in item for item in instructions_payload["guidance"]),
            f"expected provider refresh guidance: {instructions_payload}",
        )

        ensure = run(str(AGENT_DO), "auth", "ensure", "widgethub", "--json", cwd=ROOT, env=import_env)
        require(ensure.returncode == 0, f"widgethub ensure via provider import failed: {ensure.stderr}")
        ensure_payload = json.loads(ensure.stdout)
        require(ensure_payload["strategy_used"] == "provider-refresh", f"unexpected provider-refresh payload: {ensure_payload}")
        require(ensure_payload["provider_strategy_used"] == "browser-import", f"unexpected provider strategy: {ensure_payload}")

        creds_env = base_env(tmp / "provider-creds-case", fake_browse)
        creds_env["FAKE_GITHUB_BROWSER_IMPORT_FAIL"] = "1"
        creds_env["FAKE_GITHUB_REQUIRE_TOTP"] = "1"
        creds_env["GITHUB_EMAIL"] = "agent@example.com"
        creds_env["GITHUB_PASSWORD"] = "super-secret"
        creds_env["GITHUB_TOTP_SECRET"] = "JBSWY3DPEHPK3PXP"

        init_creds = run(
            str(AGENT_DO),
            "auth",
            "init",
            "widgethub-creds",
            "--domain",
            "app.example.com",
            "--login-url",
            "https://app.example.com/login",
            "--provider",
            "github",
            "--json",
            cwd=ROOT,
            env=creds_env,
        )
        require(init_creds.returncode == 0, f"widgethub-creds init failed: {init_creds.stderr}")

        ensure_creds = run(str(AGENT_DO), "auth", "ensure", "widgethub-creds", "--json", cwd=ROOT, env=creds_env)
        require(ensure_creds.returncode == 0, f"widgethub-creds ensure failed: {ensure_creds.stderr}")
        ensure_creds_payload = json.loads(ensure_creds.stdout)
        require(ensure_creds_payload["strategy_used"] == "provider-refresh", f"unexpected provider creds payload: {ensure_creds_payload}")
        require(ensure_creds_payload["provider_strategy_used"] == "site-creds", f"expected provider site-creds fallback: {ensure_creds_payload}")

        chooser_env = base_env(tmp / "provider-chooser-case", fake_browse)
        chooser_env["GITHUB_EMAIL"] = "agent@example.com"
        chooser_env["FAKE_GITHUB_ACCOUNT_CHOOSER"] = "1"

        init_chooser = run(
            str(AGENT_DO),
            "auth",
            "init",
            "widgethub-chooser",
            "--domain",
            "app.example.com",
            "--login-url",
            "https://app.example.com/login",
            "--provider",
            "github",
            "--json",
            cwd=ROOT,
            env=chooser_env,
        )
        require(init_chooser.returncode == 0, f"widgethub-chooser init failed: {init_chooser.stderr}")

        ensure_chooser = run(str(AGENT_DO), "auth", "ensure", "widgethub-chooser", "--json", cwd=ROOT, env=chooser_env)
        require(ensure_chooser.returncode == 0, f"widgethub-chooser ensure failed: {ensure_chooser.stderr}")
        ensure_chooser_payload = json.loads(ensure_chooser.stdout)
        require(ensure_chooser_payload["strategy_used"] == "provider-refresh", f"unexpected provider chooser payload: {ensure_chooser_payload}")

        show_chooser = run(str(AGENT_DO), "auth", "show", "widgethub-chooser", "--json", cwd=ROOT, env=chooser_env)
        require(show_chooser.returncode == 0, f"widgethub-chooser show failed: {show_chooser.stderr}")
        show_chooser_payload = json.loads(show_chooser.stdout)
        require(show_chooser_payload["sessions"], f"expected chooser session metadata: {show_chooser_payload}")
        latest_session = show_chooser_payload["sessions"][0]
        require(
            latest_session.get("provider_checkpoint", {}).get("account_selector") == "text=agent@example.com",
            f"expected stored provider checkpoint selector: {latest_session}",
        )
        require(
            latest_session.get("provider_checkpoint", {}).get("consent_selector") == "text=Authorize",
            f"expected stored consent checkpoint selector: {latest_session}",
        )

    print("auth provider refresh tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
