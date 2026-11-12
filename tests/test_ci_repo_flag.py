#!/usr/bin/env python3
"""agent-ci: a global --repo owner/repo must be honoured by every verb (it was
silently taken as the workflow name by `runs`, returning the origin fork's runs)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


FAKE_GH = """#!/bin/sh
printf '%s\\n' "$*" >> "$GH_CALL_LOG"
echo '[]'
"""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        binp = tmp / "bin"; binp.mkdir()
        gh = binp / "gh"; gh.write_text(FAKE_GH); gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        log = tmp / "calls.log"
        work = tmp / "work"; work.mkdir()  # no git remote here
        env = dict(os.environ, PATH=f"{binp}:{os.environ['PATH']}", GH_CALL_LOG=str(log))

        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([str(ROOT / "tools" / "agent-ci"), *args], cwd=work, env=env,
                                  text=True, capture_output=True, check=False)

        for verb, args in (("runs", ["runs", "--repo", "o/r", "--json"]),
                           ("runs=", ["runs", "--repo=o/r"]),
                           ("status", ["--repo", "o/r", "status"]),
                           ("runs wf", ["runs", "deploy", "--repo", "o/r"])):
            if log.exists():
                log.unlink()
            r = run(*args)
            require(r.returncode == 0, f"{verb}: rc={r.returncode} stderr={r.stderr} stdout={r.stdout}")
            calls = log.read_text().splitlines()
            require(calls and "--repo o/r" in calls[-1], f"{verb}: gh not called with --repo o/r: {calls}")
            require("--repo" not in r.stdout, f"{verb}: --repo leaked into output: {r.stdout}")
            if verb == "runs wf":
                require("--workflow deploy" in calls[-1], f"workflow positional lost: {calls}")

        r = run("runs")
        require(r.returncode != 0 and "Not in a git repository" in r.stdout + r.stderr,
                f"no-remote fallback changed: {r.stdout} {r.stderr}")
        r = run("runs", "--repo")
        require(r.returncode == 2 and "requires a value" in r.stderr, f"dangling --repo: {r.stderr}")
        r = run("runs", "--repo", "nope")
        require(r.returncode == 2 and "must be owner/repo" in r.stderr, f"malformed --repo: {r.stderr}")

    print("ci repo flag tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
