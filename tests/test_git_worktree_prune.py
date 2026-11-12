#!/usr/bin/env python3
"""git worktree prune clears registrations whose directory is gone (D50).

Agents working in /private/tmp or mktemp checkouts leave registrations behind
when the directory is deleted; `worktree remove` cannot clear them (there is
no tree). On 2026-09-17 eight such registrations sat across three repos.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools/agent-git"


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo, gone, locked = root / "repo", root / "gone", root / "locked"
        repo.mkdir()
        env = dict(os.environ, AGENT_DO_HOME=str(root / "home"), GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

        def git(*args: str) -> None:
            subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)

        def tool(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([str(TOOL), *args], cwd=repo, env=env, text=True, capture_output=True)

        git("init", "-q", "-b", "main")
        git("commit", "-q", "--allow-empty", "-m", "init")
        git("worktree", "add", "-q", str(gone), "-b", "gone")
        git("worktree", "add", "-q", str(locked), "-b", "locked")
        git("worktree", "lock", str(locked))
        shutil.rmtree(gone)
        shutil.rmtree(locked)

        listed = {Path(w["path"]).name: w for w in json.loads(tool("worktree", "list", "--json").stdout)["worktrees"]}
        require(listed["gone"]["prunable"], f"gone tree should be marked prunable: {listed}")
        require(listed["locked"]["locked"] and not listed["locked"]["prunable"], f"locked tree: {listed}")

        dry = tool("worktree", "prune", "--dry-run")
        require(dry.returncode == 0 and "Would prune" in dry.stdout and "gone" in dry.stdout, dry.stdout)
        dry_json = json.loads(tool("worktree", "prune", "--dry-run", "--json").stdout)
        require("pruned" not in dry_json and [Path(p["path"]).name for p in dry_json["would_prune"]] == ["gone"],
                f"dry-run JSON must say would_prune: {dry_json}")
        require(len(subprocess.run(["git", "worktree", "list"], cwd=repo, capture_output=True, text=True)
                    .stdout.splitlines()) == 3, "--dry-run must not prune")

        pruned = json.loads(tool("worktree", "prune", "--json").stdout)
        require([Path(p["path"]).name for p in pruned["pruned"]] == ["gone"], f"pruned: {pruned}")
        remaining = subprocess.run(["git", "worktree", "list"], cwd=repo, capture_output=True, text=True).stdout
        require("locked" in remaining and "gone" not in remaining, f"locked must survive: {remaining}")

        again = tool("worktree", "prune")
        require("No stale worktree registrations." in again.stdout, again.stdout)
        require(tool("worktree", "prune", "--bogus").returncode == 2, "unknown option must exit 2")
        git("worktree", "unlock", str(locked))

    print("git worktree prune tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
