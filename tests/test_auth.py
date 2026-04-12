#!/usr/bin/env python3
"""Focused tests for the initial agent-do auth surface."""

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
sys.path.insert(0, str(ROOT / "lib"))

from registry import load_registry, match_prompt_tools  # noqa: E402


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


def main() -> int:
    registry = load_registry()
    matches = match_prompt_tools(registry, "reuse github auth and check if we are signed in", limit=3)
    require(matches, "expected auth routing matches")
    require(matches[0]["tool"] == "auth", f"unexpected auth match order: {matches}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_home = tmp / "home"
        fake_state = tmp / "fake-browse-state"
        fake_home.mkdir(parents=True, exist_ok=True)
        fake_state.mkdir(parents=True, exist_ok=True)

        fake_browse = tmp / "fake-browse"
        write_executable(
            fake_browse,
            textwrap.dedent(
                """\
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
                    return {"url": "about:blank", "text": ""}

                def save_current(data):
                    current_path.write_text(json.dumps(data))

                def session_file(name):
                    return sessions_dir / f"{name}.json"

                args = sys.argv[1:]
                if args and args[0] == "--json":
                    args = args[1:]

                if not args:
                    print(json.dumps({"success": False, "error": "missing command"}))
                    raise SystemExit(1)

                command = args[0]
                current = load_current()

                def success(data):
                    print(json.dumps({"success": True, "data": data}))
                    raise SystemExit(0)

                if command == "open":
                    url = args[1]
                    text = "Sign in"
                    if "github.com/login" in url:
                        text = "Sign in to GitHub"
                    current = {"url": url, "text": text}
                    save_current(current)
                    success({"url": url})

                if command == "get" and args[1] == "url":
                    success({"url": current.get("url", "about:blank")})

                if command == "eval":
                    success({"result": current.get("text", "")})

                if command == "wait":
                    success({"waited": True})

                if command == "auth" and args[1] == "autofill":
                    url = current.get("url", "")
                    if "github.com" in url:
                        current = {"url": "https://github.com/settings/profile", "text": "View profile and more"}
                    else:
                        current = {"url": url.replace("/login", "/dashboard"), "text": "Dashboard"}
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
                            print(json.dumps({"success": False, "error": "session not found"}))
                            raise SystemExit(1)
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
                            print(json.dumps({"success": False, "error": "session not found"}))
                            raise SystemExit(1)
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
                        state = {"url": "https://github.com/settings/profile", "text": "View profile and more"}
                        session_file(name).write_text(json.dumps(state))
                        success({"imported": True, "name": name})

                print(json.dumps({"success": False, "error": f"unsupported args: {args}"}))
                raise SystemExit(1)
                """
            ),
        )

        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(fake_home)
        env["AGENT_DO_AUTH_BROWSE_CMD"] = str(fake_browse)
        env["FAKE_BROWSE_ROOT"] = str(fake_state)
        env["AUTH_SESSION_MASTER_KEY_V1"] = "test-master-key"

        init = run(str(AGENT_DO), "auth", "init", "github", "--json", cwd=ROOT, env=env)
        require(init.returncode == 0, f"auth init failed: {init.stderr}")
        init_payload = json.loads(init.stdout)
        require(init_payload["ok"] is True, f"unexpected init payload: {init_payload}")
        require((fake_home / "auth" / "profiles" / "github.yaml").exists(), "expected github auth profile")

        auth_list = run(str(AGENT_DO), "auth", "list", "--json", cwd=ROOT, env=env)
        require(auth_list.returncode == 0, f"auth list failed: {auth_list.stderr}")
        list_payload = json.loads(auth_list.stdout)
        require(list_payload["profiles"][0]["site"] == "github", f"unexpected auth list: {list_payload}")
        require(list_payload["profiles"][0]["state"] == "configured", f"unexpected initial auth state: {list_payload}")

        show = run(str(AGENT_DO), "auth", "show", "github", "--json", cwd=ROOT, env=env)
        require(show.returncode == 0, f"auth show failed: {show.stderr}")
        show_payload = json.loads(show.stdout)
        require(show_payload["profile"]["provider"]["type"] == "github", f"unexpected show payload: {show_payload}")

        instructions = run(str(AGENT_DO), "auth", "instructions", "github", "--json", cwd=ROOT, env=env)
        require(instructions.returncode == 0, f"auth instructions failed: {instructions.stderr}")
        instructions_payload = json.loads(instructions.stdout)
        require(any("ensure github" in cmd for cmd in instructions_payload["recommended"]), f"unexpected instructions: {instructions_payload}")

        ensure = run(str(AGENT_DO), "auth", "ensure", "github", "--json", cwd=ROOT, env=env)
        require(ensure.returncode == 0, f"auth ensure failed: {ensure.stderr}")
        ensure_payload = json.loads(ensure.stdout)
        require(ensure_payload["strategy_used"] == "browser-import", f"unexpected ensure payload: {ensure_payload}")
        require((fake_home / "auth" / "sessions" / "github" / "default" / "state.enc").exists(), "expected encrypted auth session bundle")
        require(not any((fake_state / "sessions").glob("*.json")), "expected transient browse session aliases to be cleaned up")

        status = run(str(AGENT_DO), "auth", "status", "github", "--json", cwd=ROOT, env=env)
        require(status.returncode == 0, f"auth status failed: {status.stderr}")
        status_payload = json.loads(status.stdout)
        require(status_payload["state"] == "authenticated", f"unexpected status payload: {status_payload}")

        validate = run(str(AGENT_DO), "auth", "validate", "github", "--json", cwd=ROOT, env=env)
        require(validate.returncode == 0, f"auth validate failed: {validate.stderr}")
        validate_payload = json.loads(validate.stdout)
        require(validate_payload["ok"] is True, f"unexpected validate payload: {validate_payload}")

        clear = run(str(AGENT_DO), "auth", "clear", "github", "--all", "--json", cwd=ROOT, env=env)
        require(clear.returncode == 0, f"auth clear failed: {clear.stderr}")
        cleared_payload = json.loads(clear.stdout)
        require("default" in cleared_payload["cleared"], f"unexpected clear payload: {cleared_payload}")

        status_after = run(str(AGENT_DO), "auth", "status", "github", "--json", cwd=ROOT, env=env)
        require(status_after.returncode == 0, f"auth status after clear failed: {status_after.stderr}")
        status_after_payload = json.loads(status_after.stdout)
        require(status_after_payload["state"] == "configured", f"unexpected status after clear: {status_after_payload}")

    print("auth tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
