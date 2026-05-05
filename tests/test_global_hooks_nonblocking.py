#!/usr/bin/env python3
"""Regression tests for installed global hooks that must stay advisory-only.

These tests are intentionally tolerant for public checkouts: if the user's
global hook files are not installed, the test exits successfully.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


HOME = Path.home()
CODEX_STOP = HOME / ".codex" / "hooks" / "stop-quality-gate.py"
CODEX_ANNOTATE = HOME / ".codex" / "hooks" / "annotate.py"
CLAUDE_ANNOTATE = HOME / ".claude" / "hooks" / "annotate.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_hook(path: Path, payload: dict, cwd: Path | None = None, home: Path | None = None) -> dict:
    env = os.environ.copy()
    if home is not None:
        env["HOME"] = str(home)
    proc = subprocess.run(
        ["python3", str(path)],
        cwd=str(cwd) if cwd else None,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    require(proc.returncode == 0, f"{path} failed: {proc.stderr}")
    if not proc.stdout.strip():
        return {}
    return json.loads(proc.stdout)


def assert_not_blocking(payload: dict, label: str) -> None:
    require(payload.get("decision") != "block", f"{label} emitted decision:block: {payload}")
    require(payload.get("continue") is not False, f"{label} emitted continue:false: {payload}")


def test_codex_stop_is_advisory() -> None:
    if not CODEX_STOP.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
        ui_file = repo / "app" / "page.tsx"
        ui_file.parent.mkdir(parents=True)
        ui_file.write_text("export default function Page() { return <main>Hello</main>; }\n")

        payload = run_hook(CODEX_STOP, {"cwd": str(repo)}, cwd=repo)
        assert_not_blocking(payload, "codex stop hook")
        require(payload.get("continue") is True, f"codex stop hook should continue: {payload}")
        require("systemMessage" in payload, f"codex stop hook should emit advisory context: {payload}")


def test_annotation_hooks_are_advisory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        for label, hook in (("codex annotate", CODEX_ANNOTATE), ("claude annotate", CLAUDE_ANNOTATE)):
            if not hook.exists():
                continue
            payload = run_hook(hook, {"prompt": "#tag:review", "session_id": "test-session"}, home=home)
            assert_not_blocking(payload, label)
            require("hookSpecificOutput" in payload, f"{label} should emit context: {payload}")


def main() -> int:
    test_codex_stop_is_advisory()
    test_annotation_hooks_are_advisory()
    print("global hook nonblocking tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
