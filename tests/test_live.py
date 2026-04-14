#!/usr/bin/env python3
"""Focused tests for the +live runtime substrate."""

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

from live.lease import activate_lease, find_matching_lease, list_active_leases  # noqa: E402
from live.parser import build_live_modifier, parse_live_modifier  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def main() -> int:
    parsed = parse_live_modifier('+live(scope=browser,app="Google Chrome",ttl=15m,reason="cloudflare auth")')
    require(parsed["scope"] == "browser", f"unexpected scope: {parsed}")
    require(parsed["app"] == "Google Chrome", f"unexpected app: {parsed}")
    require(parsed["ttl_seconds"] == 900, f"unexpected ttl: {parsed}")
    require(parsed["reason"] == "cloudflare auth", f"unexpected reason: {parsed}")

    rebuilt = build_live_modifier(
        scope="browser",
        app="Google Chrome",
        ttl_seconds=900,
        reason="cloudflare auth",
    )
    require(rebuilt == '+live(scope=browser,app="Google Chrome",ttl=15m,reason="cloudflare auth")', f"unexpected rebuilt modifier: {rebuilt}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_home = tmp / "home"
        fake_home.mkdir(parents=True, exist_ok=True)
        fake_bin = tmp / "bin"
        fake_bin.mkdir(parents=True, exist_ok=True)

        fake_tool = fake_bin / "agent-fake-live"
        write_executable(
            fake_tool,
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import os
                print(os.environ.get("AGENT_DO_LIVE_CONTEXT", ""))
                """
            ),
        )

        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(fake_home)
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        previous_home = os.environ.get("AGENT_DO_HOME")
        os.environ["AGENT_DO_HOME"] = str(fake_home)

        try:
            lease = activate_lease(
                {
                    "enabled": True,
                    "scope": "desktop",
                    "ttl_seconds": 300,
                    "app": None,
                    "reason": "macos:click",
                }
            )
            require(lease is not None, "expected ttl-based lease activation")
            require(find_matching_lease("browser") is not None, "desktop lease should allow browser scope")
            require(len(list_active_leases()) == 1, "expected one active lease")
        finally:
            if previous_home is None:
                os.environ.pop("AGENT_DO_HOME", None)
            else:
                os.environ["AGENT_DO_HOME"] = previous_home

        status = run(str(AGENT_DO), "--status", env=env)
        require("Live Leases:" in status.stdout, f"expected live leases in status output: {status.stdout}")

        live_cmd = run(
            str(AGENT_DO),
            '+live(scope=browser,app=Arc,ttl=15m,reason="cf auth")',
            "fake-live",
            "inspect",
            env=env,
        )
        require(live_cmd.returncode == 0, f"fake live tool failed: {live_cmd.stderr}")
        live_context = json.loads(live_cmd.stdout.strip())
        require(live_context["scope"] == "browser", f"unexpected exported live scope: {live_context}")
        require(live_context["app"] == "Arc", f"unexpected exported live app: {live_context}")

        macos_denied = run(str(AGENT_DO), "macos", "click", "@g1", env=env)
        require("LIVE_APPROVAL_REQUIRED" not in macos_denied.stdout, f"active lease should satisfy macos live gate: {macos_denied.stdout}")

        fresh_home = tmp / "fresh-home"
        fresh_home.mkdir(parents=True, exist_ok=True)
        fresh_env = dict(env)
        fresh_env["AGENT_DO_HOME"] = str(fresh_home)

        macos_blocked = run(str(AGENT_DO), "macos", "click", "@g1", env=fresh_env)
        require("LIVE_APPROVAL_REQUIRED" in macos_blocked.stdout, f"expected macos live gate: {macos_blocked.stdout}")
        require("+live(scope=desktop" in macos_blocked.stdout, f"expected macos rerun hint: {macos_blocked.stdout}")

        screen_blocked = run(str(AGENT_DO), "screen", "click", "1", "1", env=fresh_env)
        require("LIVE_APPROVAL_REQUIRED" in screen_blocked.stdout, f"expected screen live gate: {screen_blocked.stdout}")
        require("+live(scope=desktop" in screen_blocked.stdout, f"expected screen rerun hint: {screen_blocked.stdout}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
