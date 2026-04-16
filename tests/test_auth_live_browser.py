#!/usr/bin/env python3
"""Tests for auth live-browser-control strategy over the +live substrate."""

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
        fake_home.mkdir(parents=True, exist_ok=True)
        state_path = tmp / "live-state.json"

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

                state_path = Path(os.environ["FAKE_LIVE_STATE"])
                url = sys.argv[-1]
                if "dash.cloudflare.com" in url:
                    payload = {"step": "cloudflare-login", "focus": None, "username": "", "password": "", "typed": ""}
                else:
                    payload = {"step": "opened-link", "focus": None}
                state_path.write_text(json.dumps(payload))
                raise SystemExit(0)
                """
            ),
        )

        fake_macos = tmp / "fake-macos"
        write_executable(
            fake_macos,
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import sys

                args = sys.argv[1:]
                cmd = args[0] if args else ""

                if cmd == "permissions":
                    print(json.dumps({"granted": True}))
                    raise SystemExit(0)
                if cmd == "frontmost":
                    print(json.dumps({"app": "Comet"}))
                    raise SystemExit(0)
                if cmd == "focus":
                    print(json.dumps({"focused": args[1] if len(args) > 1 else "Comet"}))
                    raise SystemExit(0)
                if cmd == "dialog":
                    print(json.dumps({"type": None, "buttons": []}))
                    raise SystemExit(0)

                print(json.dumps({"ok": True}))
                """
            ),
        )

        fake_screen = tmp / "fake-screen"
        write_executable(
            fake_screen,
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import os
                import sys
                from pathlib import Path

                state_path = Path(os.environ["FAKE_LIVE_STATE"])
                expected_username = os.environ["GITHUB_EMAIL"]
                expected_password = os.environ["GITHUB_PASSWORD"]
                expected_totp = "123456"

                def load_state():
                    if state_path.exists():
                        return json.loads(state_path.read_text())
                    return {"step": "idle", "focus": None, "username": "", "password": "", "typed": ""}

                def save_state(state):
                    state_path.write_text(json.dumps(state))

                def texts_for(step):
                    mapping = {
                        "cloudflare-login": ["Cloudflare", "Continue with GitHub", "Sign in"],
                        "github-login": ["Sign in to GitHub", "Username or email address", "Password"],
                        "github-totp": ["Two-factor authentication", "Authentication code"],
                        "cloudflare-consent": ["Authorize", "Cloudflare wants to access your GitHub account"],
                        "cloudflare-dashboard": ["Cloudflare", "Dashboard", "Websites"],
                        "opened-link": ["Dashboard"],
                    }
                    return mapping.get(step, ["Idle"])

                state = load_state()
                args = sys.argv[1:]
                cmd = args[0] if args else ""

                if cmd == "snapshot":
                    elements = [{"text": text} for text in texts_for(state.get("step", "idle"))]
                    print(json.dumps({"ok": True, "elements": elements, "element_count": len(elements)}))
                    raise SystemExit(0)

                if cmd == "click" and "--text" in args:
                    text = args[args.index("--text") + 1]
                    step = state.get("step")
                    if step == "cloudflare-login" and "GitHub" in text:
                        state.update({"step": "github-login", "focus": "username", "typed": ""})
                    elif step == "github-login" and "Username" in text:
                        state["focus"] = "username"
                    elif step == "github-login" and "Password" in text:
                        state["focus"] = "password"
                    elif step == "github-totp" and ("Authentication" in text or "code" in text.lower()):
                        state["focus"] = "totp"
                    elif step == "cloudflare-consent" and text in {"Authorize", "Continue", "Allow"}:
                        state["step"] = "cloudflare-dashboard"
                    save_state(state)
                    print(json.dumps({"ok": True, "clicked": text}))
                    raise SystemExit(0)

                if cmd == "type":
                    text = " ".join(args[1:])
                    focus = state.get("focus")
                    if state.get("step") == "github-login" and focus == "username":
                        state["username"] = text
                    elif state.get("step") == "github-login" and focus == "password":
                        state["password"] = text
                    elif state.get("step") == "github-totp" and focus == "totp":
                        state["typed"] = text
                    save_state(state)
                    print(json.dumps({"ok": True, "typed": text}))
                    raise SystemExit(0)

                if cmd == "press":
                    key = " ".join(args[1:]).lower()
                    step = state.get("step")
                    if step == "github-login" and key == "tab":
                        state["focus"] = "password"
                    elif step == "github-login" and key == "enter":
                        if state.get("username") == expected_username and state.get("password") == expected_password:
                            state.update({"step": "github-totp", "focus": "totp", "typed": ""})
                    elif step == "github-totp" and key == "enter":
                        if state.get("typed") == expected_totp:
                            state.update({"step": "cloudflare-consent", "focus": None, "typed": ""})
                    save_state(state)
                    print(json.dumps({"ok": True, "pressed": key}))
                    raise SystemExit(0)

                print(json.dumps({"ok": True}))
                """
            ),
        )

        fake_browse = tmp / "fake-browse"
        write_executable(
            fake_browse,
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import sys

                args = [arg for arg in sys.argv[1:] if arg != "--json"]
                if args[:2] == ["auth", "totp"]:
                    print(json.dumps({"success": True, "data": {"code": "123456"}}))
                    raise SystemExit(0)
                if args[:2] == ["session", "delete"]:
                    print(json.dumps({"success": True, "data": {"deleted": True}}))
                    raise SystemExit(0)
                print(json.dumps({"success": True, "data": {}}))
                """
            ),
        )

        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(fake_home)
        env["AGENT_DO_AUTH_OPEN_CMD"] = str(fake_open)
        env["AGENT_DO_AUTH_MACOS_CMD"] = str(fake_macos)
        env["AGENT_DO_AUTH_SCREEN_CMD"] = str(fake_screen)
        env["AGENT_DO_AUTH_BROWSE_CMD"] = str(fake_browse)
        env["FAKE_LIVE_STATE"] = str(state_path)
        env["AUTH_SESSION_MASTER_KEY_V1"] = "test-master-key"
        env["GITHUB_EMAIL"] = "ovachiever"
        env["GITHUB_PASSWORD"] = "DfMktioRxdrhsnO3dMHk!"
        env["GITHUB_TOTP_SECRET"] = "otpauth://totp/test"

        init = run(
            str(AGENT_DO),
            "auth",
            "init",
            "cloudflare",
            "--domain",
            "dash.cloudflare.com",
            "--login-url",
            "https://dash.cloudflare.com/login",
            "--provider",
            "github",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(init.returncode == 0, f"auth init failed: {init.stderr}")

        missing_live = run(
            str(AGENT_DO),
            "auth",
            "ensure",
            "cloudflare",
            "--strategy",
            "live-browser-control",
            "--timeout",
            "5",
            "--interval",
            "1",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(missing_live.returncode == 1, f"expected live approval failure: {missing_live.stdout}")
        missing_live_payload = json.loads(missing_live.stdout)
        require(missing_live_payload["action_required"] == "LIVE_APPROVAL_REQUIRED", f"unexpected missing-live payload: {missing_live_payload}")

        ensure_live = run(
            str(AGENT_DO),
            "+live(scope=browser,app='Comet',ttl=15m)",
            "auth",
            "ensure",
            "cloudflare",
            "--strategy",
            "live-browser-control",
            "--timeout",
            "5",
            "--interval",
            "1",
            "--json",
            cwd=ROOT,
            env=env,
        )
        require(ensure_live.returncode == 0, f"live-browser ensure failed: {ensure_live.stderr}\n{ensure_live.stdout}")
        ensure_payload = json.loads(ensure_live.stdout)
        require(ensure_payload["ok"] is True, f"expected successful live-browser payload: {ensure_payload}")
        require(ensure_payload["strategy_used"] == "live-browser-control", f"unexpected strategy: {ensure_payload}")

        status = run(str(AGENT_DO), "auth", "status", "cloudflare", "--json", cwd=ROOT, env=env)
        require(status.returncode == 0, f"auth status failed: {status.stderr}")
        status_payload = json.loads(status.stdout)
        require(status_payload["session"]["storage"] == "live-browser", f"expected live-browser storage: {status_payload}")
        require(status_payload["session"]["live_browser_app"] == "Comet", f"unexpected live browser app: {status_payload}")

        probe = run(str(AGENT_DO), "auth", "probe", "cloudflare", "--json", cwd=ROOT, env=env)
        require(probe.returncode == 0, f"auth probe failed: {probe.stderr}")
        probe_payload = json.loads(probe.stdout)
        require(probe_payload["mode"] == "live-browser", f"expected live-browser mode: {probe_payload}")
        require(probe_payload["state"] == "authenticated", f"expected authenticated live probe: {probe_payload}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
