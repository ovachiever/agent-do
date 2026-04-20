#!/usr/bin/env python3
"""Regression tests for implicit browse daemon-session isolation."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


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


def run_bash(script: str, *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", script],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def session_name(output: str) -> str:
    prefix = "Session: "
    require(output.startswith(prefix), f"unexpected session output: {output!r}")
    return output.strip()[len(prefix):]


def main() -> int:
    base_env = dict(os.environ)
    base_env.pop("AGENT_BROWSER_SESSION", None)

    explicit_default = dict(base_env)
    explicit_default.pop("CODEX_THREAD_ID", None)
    explicit_default.pop("CLAUDE_THREAD_ID", None)
    explicit_default.pop("CLAUDE_SESSION_ID", None)
    explicit_default.pop("CLAUDE_AGENT_ID", None)
    explicit_default.pop("TMUX_PANE", None)

    default_res = run(str(AGENT_DO), "browse", "session", env=explicit_default)
    require(default_res.returncode == 0, f"default browse session failed: {default_res.stderr}")
    require(session_name(default_res.stdout) == "default", f"expected default session: {default_res.stdout}")

    thread_a = dict(explicit_default)
    thread_a["CODEX_THREAD_ID"] = "019d7912-5a47-7c01-b9ae-90ac2060a27e"
    res_a = run(str(AGENT_DO), "browse", "session", env=thread_a)
    require(res_a.returncode == 0, f"thread A browse session failed: {res_a.stderr}")
    name_a = session_name(res_a.stdout)
    require(name_a == "codex-019d79125a477c01", f"unexpected thread A session: {name_a}")

    thread_b = dict(explicit_default)
    thread_b["CODEX_THREAD_ID"] = "f6f9b9b4-1234-5678-9999-aaaaaaaaaaaa"
    res_b = run(str(AGENT_DO), "browse", "session", env=thread_b)
    require(res_b.returncode == 0, f"thread B browse session failed: {res_b.stderr}")
    name_b = session_name(res_b.stdout)
    require(name_b == "codex-f6f9b9b412345678", f"unexpected thread B session: {name_b}")
    require(name_a != name_b, f"expected distinct derived sessions: {name_a} vs {name_b}")

    explicit_env = dict(thread_a)
    explicit_env["AGENT_BROWSER_SESSION"] = "travelbank-shared"
    explicit_res = run(str(AGENT_DO), "browse", "session", env=explicit_env)
    require(explicit_res.returncode == 0, f"explicit env session failed: {explicit_res.stderr}")
    require(session_name(explicit_res.stdout) == "travelbank-shared", f"explicit env should win: {explicit_res.stdout}")

    explicit_flag = run(str(AGENT_DO), "browse", "--session", "manual-override", "session", env=thread_a)
    require(explicit_flag.returncode == 0, f"explicit flag session failed: {explicit_flag.stderr}")
    require(session_name(explicit_flag.stdout) == "manual-override", f"explicit flag should win: {explicit_flag.stdout}")

    tmux_env = dict(explicit_default)
    tmux_env["TMUX_PANE"] = "%58"
    tmux_res = run(str(AGENT_DO), "browse", "session", env=tmux_env)
    require(tmux_res.returncode == 0, f"tmux fallback failed: {tmux_res.stderr}")
    require(session_name(tmux_res.stdout) == "tmux-58", f"unexpected tmux fallback: {tmux_res.stdout}")

    with tempfile.TemporaryDirectory() as tmp:
        temp_home = Path(tmp)
        shared_dir = temp_home / ".agent-browse" / "sessions" / "travelbank"
        shared_dir.mkdir(parents=True, exist_ok=True)
        (shared_dir / "storage.json").write_text("{}")

        fork_env = dict(explicit_default)
        fork_env["HOME"] = str(temp_home)
        fork_env["AGENT_BROWSER_SESSION"] = "codex-alpha"

        helper = run_bash(
            f"""
source <(sed '$d' "{ROOT / 'tools/agent-browse/agent-browse'}")
printf '%s\\n' "$(resolve_save_target_name travelbank false)"
printf '%s\\n' "$(resolve_save_target_name travelbank true)"
printf '%s\\n' "$(resolve_save_target_name freshsession false)"
printf '%s\\n' "$(resolve_save_target_name travelbank@codex-alpha false)"
""",
            env=fork_env,
        )
        require(helper.returncode == 0, f"browse helper source failed: {helper.stderr}")
        lines = [line.strip() for line in helper.stdout.splitlines() if line.strip()]
        require(lines[0] == "travelbank@codex-alpha", f"expected shared session to fork: {lines}")
        require(lines[1] == "travelbank", f"expected --shared to preserve literal name: {lines}")
        require(lines[2] == "freshsession", f"expected new session name to remain literal: {lines}")
        require(lines[3] == "travelbank@codex-alpha", f"expected agent-scoped names to remain unchanged: {lines}")

    print("browse session default tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
