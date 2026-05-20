#!/usr/bin/env python3
"""Codex PreToolUse hook wrapper for the checked-in agent-do router.

Codex supports `hookSpecificOutput.additionalContext` on PreToolUse as of
the May 2026 hooks release, so this wrapper runs the repo's hook directly
with stdin/stdout pass-through via `runpy.run_path`. The agent sees the
nudge identically to how Claude Code sees it.

Install:
    cp hooks/codex/agent-do-pretooluse-check.py ~/.codex/hooks/

The repo location is resolved in priority order:
    1. AGENT_DO_REPO env var
    2. ~/.agent-do/install-path breadcrumb
    3. ~/Custom-Coding/agent-do (default fallback; edit if needed)
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def candidate_roots() -> list[Path]:
    roots: list[Path] = []

    env_root = os.environ.get("AGENT_DO_REPO")
    if env_root:
        roots.append(Path(env_root).expanduser())

    breadcrumb = Path.home() / ".agent-do" / "install-path"
    if breadcrumb.exists():
        try:
            roots.append(Path(breadcrumb.read_text().strip()).expanduser())
        except OSError:
            pass

    # Default fallback for single-user dev setups. The installer writes the
    # breadcrumb above so this fallback is rarely needed.
    roots.append(Path.home() / "Custom-Coding" / "agent-do")
    return roots


def main() -> None:
    for root in candidate_roots():
        hook = root / "hooks" / "claude" / "agent-do-pretooluse-check.py"
        if hook.exists():
            sys.path.insert(0, str(root / "lib"))
            os.environ["AGENT_DO_HOOK_RUNTIME"] = "codex"
            runpy.run_path(str(hook), run_name="__main__")
            return


if __name__ == "__main__":
    main()
