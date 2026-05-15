#!/usr/bin/env python3
"""Compatibility tests for v1.2 PR action commands preserved through the package refactor.

Proves that close, reopen, checkout, edit, and update-branch still work after
agent-gh was restructured from a flat script into a Python package.  This is
the exact surface ovachiever verified was missing on the PR head.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def make_exec(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, env=env, text=True, capture_output=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        log_path = tmp / "gh-calls.jsonl"

        # Fake gh binary: logs every invocation and returns a minimal valid response
        make_exec(
            fake_bin / "gh",
            f"""#!/usr/bin/env python3
import json, sys
from pathlib import Path

log = Path({str(log_path)!r})
args = sys.argv[1:]
with log.open("a") as f:
    f.write(json.dumps(args) + "\\n")

# Return enough for any auth/user check the package may call
if args[:2] == ["api", "user"]:
    print(json.dumps({{"login": "testuser", "id": 1, "name": "Test User", "html_url": "https://github.com/testuser"}}))
else:
    # Silent success for write operations
    pass
sys.exit(0)
""",
        )

        base_env: dict[str, str] = {
            **os.environ,
            "PATH": str(fake_bin) + ":" + os.environ.get("PATH", ""),
            "HOME": str(tmp / "home"),
            "AGENT_GH_BIN": str(fake_bin / "gh"),
            "AGENT_DO_HOME": str(tmp / "agent_home"),
        }

        fails = 0

        def check(label: str, cond: bool, detail: str = "") -> None:
            nonlocal fails
            if cond:
                print(f"  ok  {label}")
            else:
                print(f"FAIL  {label}" + (f": {detail}" if detail else ""))
                fails += 1

        def last_gh_call() -> list[str]:
            lines = log_path.read_text().strip().splitlines()
            return json.loads(lines[-1]) if lines else []

        def clear_log() -> None:
            if log_path.exists():
                log_path.write_text("")

        print("\n=== agent-gh v1.2 PR action compat tests ===\n")

        # ── --help smoke tests ─────────────────────────────────────────────────
        # This is exactly what ovachiever ran: agent-do gh update-branch --help
        print("--- --help smoke tests ---")

        for cmd_name in ("close", "reopen", "checkout", "edit", "update-branch"):
            r = run([str(AGENT_DO), "gh", cmd_name, "--help"], env=base_env)
            check(f"gh {cmd_name} --help exits 0", r.returncode == 0, r.stderr[:200])
            check(f"gh {cmd_name} --help mentions {cmd_name}", cmd_name in r.stdout)

        # ── functional tests: verify gh CLI args ───────────────────────────────
        print("\n--- functional invocations ---")

        # close
        clear_log()
        r = run([str(AGENT_DO), "gh", "close", "ovachiever/agent-do#3"], env=base_env)
        check("gh close exits 0", r.returncode == 0, r.stderr)
        check("gh close: calls gh pr close", "pr" in last_gh_call() and "close" in last_gh_call())
        check("gh close: passes repo flag", "--repo" in last_gh_call())
        check("gh close: passes PR number", "3" in last_gh_call())
        check("gh close: output mentions PR ref", "ovachiever/agent-do#3" in r.stdout)

        clear_log()
        r = run([str(AGENT_DO), "gh", "close", "ovachiever/agent-do#3",
                 "--delete-branch", "--comment", "closing"], env=base_env)
        check("gh close --delete-branch --comment exits 0", r.returncode == 0, r.stderr)
        call = last_gh_call()
        check("gh close --delete-branch: flag forwarded", "--delete-branch" in call)
        check("gh close --comment: text forwarded", "closing" in call)

        # reopen
        clear_log()
        r = run([str(AGENT_DO), "gh", "reopen", "ovachiever/agent-do#3"], env=base_env)
        check("gh reopen exits 0", r.returncode == 0, r.stderr)
        check("gh reopen: calls gh pr reopen", "pr" in last_gh_call() and "reopen" in last_gh_call())
        check("gh reopen: output mentions PR ref", "ovachiever/agent-do#3" in r.stdout)

        # checkout
        clear_log()
        r = run([str(AGENT_DO), "gh", "checkout", "ovachiever/agent-do#5",
                 "--branch", "review/pr-5"], env=base_env)
        check("gh checkout exits 0", r.returncode == 0, r.stderr)
        call = last_gh_call()
        check("gh checkout: calls gh pr checkout", "pr" in call and "checkout" in call)
        check("gh checkout --branch: forwarded", "--branch" in call and "review/pr-5" in call)
        check("gh checkout: output mentions PR ref", "ovachiever/agent-do#5" in r.stdout)

        # checkout alias 'co'
        clear_log()
        r = run([str(AGENT_DO), "gh", "co", "ovachiever/agent-do#5"], env=base_env)
        check("gh co (alias) exits 0", r.returncode == 0, r.stderr)
        check("gh co alias calls gh pr checkout", "checkout" in last_gh_call())

        # edit
        clear_log()
        r = run([str(AGENT_DO), "gh", "edit", "ovachiever/agent-do#5",
                 "--add-reviewer", "alice", "--add-label", "review-needed"], env=base_env)
        check("gh edit exits 0", r.returncode == 0, r.stderr)
        call = last_gh_call()
        check("gh edit: calls gh pr edit", "pr" in call and "edit" in call)
        check("gh edit --add-reviewer: forwarded", "--add-reviewer" in call and "alice" in call)
        check("gh edit --add-label: forwarded", "--add-label" in call and "review-needed" in call)
        check("gh edit: output mentions PR ref", "ovachiever/agent-do#5" in r.stdout)

        # update-branch — the exact command from ovachiever's review comment
        clear_log()
        r = run([str(AGENT_DO), "gh", "update-branch", "ovachiever/agent-do#3"], env=base_env)
        check("gh update-branch exits 0", r.returncode == 0, r.stderr)
        call = last_gh_call()
        check("gh update-branch: calls gh pr update-branch", "pr" in call and "update-branch" in call)
        check("gh update-branch: passes repo flag", "--repo" in call)
        check("gh update-branch: output mentions PR ref", "ovachiever/agent-do#3" in r.stdout)

        clear_log()
        r = run([str(AGENT_DO), "gh", "update-branch", "ovachiever/agent-do#3", "--rebase"],
                env=base_env)
        check("gh update-branch --rebase exits 0", r.returncode == 0, r.stderr)
        check("gh update-branch --rebase: flag forwarded", "--rebase" in last_gh_call())

        # ── summary ───────────────────────────────────────────────────────────
        print(f"\n{'=' * 45}")
        if fails:
            print(f"FAILED: {fails} test(s) failed")
            return 1
        print("All compat tests passed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
