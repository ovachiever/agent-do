#!/usr/bin/env python3
"""Tests for auth interactive system-browser handoff."""

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


def main() -> int:
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
                external_state_path = Path(os.environ["FAKE_EXTERNAL_STATE_PATH"])
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

                if command == "get" and args[1] == "count":
                    selector = args[2]
                    selectors = current.get("selectors", [])
                    success({"count": 1 if selector in selectors else 0})

                if command == "eval":
                    success({"result": current.get("text", "")})

                if command == "wait":
                    success({"waited": True})

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
                        state = payload.get("storage", {})
                        session_file(name).write_text(json.dumps(state))
                        save_current(state)
                        success({"imported": True, "name": name})
                    if action == "import-browser":
                        name = args[2]
                        if external_state_path.exists():
                            state = json.loads(external_state_path.read_text())
                        else:
                            state = {"url": "https://github.com/login", "text": "Sign in to GitHub"}
                        session_file(name).write_text(json.dumps(state))
                        save_current(state)
                        success({"imported": True, "name": name})

                print(json.dumps({"success": False, "error": f"unsupported args: {args}"}))
                raise SystemExit(1)
                """
            ),
        )

        fake_open = tmp / "fake-open"
        write_executable(
            fake_open,
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import os
                import sys
                from pathlib import Path

                log_path = Path(os.environ["FAKE_OPEN_LOG"])
                state_path = Path(os.environ["FAKE_EXTERNAL_STATE_PATH"])
                log_path.write_text(json.dumps({"args": sys.argv[1:]}))

                payload = os.environ.get("FAKE_OPEN_AUTH_STATE")
                if payload:
                    state_path.write_text(payload)
                raise SystemExit(0)
                """
            ),
        )

        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(fake_home)
        env["AGENT_DO_AUTH_BROWSE_CMD"] = str(fake_browse)
        env["AGENT_DO_AUTH_OPEN_CMD"] = str(fake_open)
        env["FAKE_BROWSE_ROOT"] = str(fake_state)
        env["FAKE_OPEN_LOG"] = str(tmp / "open-log.json")
        env["FAKE_EXTERNAL_STATE_PATH"] = str(tmp / "external-state.json")
        env["AUTH_SESSION_MASTER_KEY_V1"] = "test-master-key"

        init = run(str(AGENT_DO), "auth", "init", "github", "--json", cwd=ROOT, env=env)
        require(init.returncode == 0, f"auth init failed: {init.stderr}")

        env["FAKE_OPEN_AUTH_STATE"] = json.dumps(
            {"url": "https://github.com/settings/profile", "text": "View profile and more"}
        )
        ensure_ok = run(
            str(AGENT_DO),
            "auth",
            "ensure",
            "github",
            "--strategy",
            "interactive",
            "--timeout",
            "2",
            "--interval",
            "1",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(ensure_ok.returncode == 0, f"interactive ensure failed: {ensure_ok.stderr}")
        ensure_ok_payload = json.loads(ensure_ok.stdout)
        require(ensure_ok_payload["ok"] is True, f"unexpected interactive ensure payload: {ensure_ok_payload}")
        require(ensure_ok_payload["strategy_used"] == "interactive", f"unexpected strategy: {ensure_ok_payload}")
        require(ensure_ok_payload["source_browser"] == "comet", f"unexpected source browser: {ensure_ok_payload}")
        open_log = json.loads((tmp / "open-log.json").read_text())
        require(open_log["args"][0] == "https://github.com/login", f"unexpected open args: {open_log}")
        require("--browser" in open_log["args"], f"missing browser flag in open args: {open_log}")
        require((fake_home / "auth" / "sessions" / "github" / "default" / "state.enc").exists(), "expected encrypted auth session bundle")
        require(not any((fake_state / "sessions").glob("*.json")), "expected transient browse session aliases to be cleaned up after interactive success")

        env["FAKE_OPEN_AUTH_STATE"] = json.dumps(
            {
                "url": "https://github.com/sessions/two-factor/app",
                "text": "Two-factor authentication Enter the code from your app",
                "selectors": ['input[name="app_otp"]'],
            }
        )
        ensure_checkpoint = run(
            str(AGENT_DO),
            "auth",
            "ensure",
            "github",
            "--name",
            "checkpoint",
            "--strategy",
            "interactive",
            "--timeout",
            "2",
            "--interval",
            "1",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(ensure_checkpoint.returncode == 1, f"expected checkpoint action-required result: {ensure_checkpoint.stdout} {ensure_checkpoint.stderr}")
        ensure_checkpoint_payload = json.loads(ensure_checkpoint.stdout)
        require(ensure_checkpoint_payload["action_required"] == "TOTP_REQUIRED", f"unexpected checkpoint payload: {ensure_checkpoint_payload}")
        require(ensure_checkpoint_payload["probe"]["state"] == "checkpoint", f"unexpected probe state: {ensure_checkpoint_payload}")
        require((fake_home / "auth" / "sessions" / "github" / "checkpoint" / "state.enc").exists(), "expected encrypted checkpoint auth bundle")
        require(not any((fake_state / "sessions").glob("*.json")), "expected transient browse session aliases to be cleaned up after interactive checkpoint persistence")

        env.pop("FAKE_OPEN_AUTH_STATE", None)
        Path(env["FAKE_EXTERNAL_STATE_PATH"]).unlink(missing_ok=True)
        ensure_timeout = run(
            str(AGENT_DO),
            "auth",
            "ensure",
            "github",
            "--name",
            "timeout",
            "--strategy",
            "interactive",
            "--timeout",
            "1",
            "--interval",
            "1",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(ensure_timeout.returncode == 1, f"expected interactive timeout failure: {ensure_timeout.stdout} {ensure_timeout.stderr}")
        ensure_timeout_payload = json.loads(ensure_timeout.stdout)
        require(ensure_timeout_payload["action_required"] == "INTERACTIVE_LOGIN", f"unexpected timeout payload: {ensure_timeout_payload}")
        require(ensure_timeout_payload["opened"] is True, f"expected opened browser payload: {ensure_timeout_payload}")
        require("import-browser github" in " ".join(ensure_timeout_payload.get("recommended", [])), f"unexpected timeout guidance: {ensure_timeout_payload}")
        require(not any((fake_state / "sessions").glob("*.json")), "expected no leftover transient browse session aliases after interactive timeout")

    print("auth interactive tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
