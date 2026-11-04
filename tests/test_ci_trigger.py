#!/usr/bin/env python3
"""ci trigger passes workflow_dispatch inputs (-f key=value) through to gh.

On 2026-10-15 the Mr. President ios-release workflow needed
upload_to_testflight=true and `agent-do ci trigger` could only send --ref,
so the run went through raw `gh workflow run -f`. A stub `gh` records argv.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# One line per call; arguments separated by a unit separator (\\x1f) so a
# value with spaces is visibly one argument.
STUB_GH = """#!/bin/bash
(IFS=$'\\x1f'; printf '%s\\n' "$*") >> "$GH_LOG"
exit 0
"""


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        stub = tmpdir / "bin"
        stub.mkdir()
        (stub / "gh").write_text(STUB_GH)
        (stub / "gh").chmod(0o755)
        repo = tmpdir / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/acme/widgets.git"], cwd=repo, check=True)
        log = tmpdir / "gh.log"
        env = dict(os.environ, PATH=f"{stub}:{os.environ['PATH']}", GH_LOG=str(log))

        def ci(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([str(ROOT / "tools/agent-ci"), "trigger", *args], cwd=repo, env=env,
                                  text=True, capture_output=True, check=False)

        r = ci("ios-release.yml", "main", "-f", "upload_to_testflight=true", "--field", "notes=a b=c")
        require(r.returncode == 0, f"trigger failed: {r.stderr}")
        call = log.read_text().splitlines()[-1].split("\x1f")
        require(call == ["workflow", "run", "ios-release.yml", "--ref", "main", "--repo", "acme/widgets",
                         "-f", "upload_to_testflight=true", "-f", "notes=a b=c"], f"unexpected gh argv: {call}")
        require("with 2 input(s)" in r.stdout, f"summary: {r.stdout!r}")

        r = ci("deploy.yml", "--ref", "v1.2.3")
        require(r.returncode == 0, r.stderr)
        require(log.read_text().splitlines()[-1].split("\x1f") ==
                ["workflow", "run", "deploy.yml", "--ref", "v1.2.3", "--repo", "acme/widgets"], "--ref and no inputs")

        r = ci("deploy.yml")
        require(log.read_text().splitlines()[-1].split("\x1f")[:5] == ["workflow", "run", "deploy.yml", "--ref", "main"],
                "defaults to current branch")

        for bad in (["deploy.yml", "-f", "novalue"], ["deploy.yml", "--bogus"], ["deploy.yml", "main", "extra"]):
            before = len(log.read_text().splitlines())
            r = ci(*bad)
            require(r.returncode == 2, f"{bad}: expected exit 2, got {r.returncode}")
            require(len(log.read_text().splitlines()) == before, f"{bad}: gh must not run")

    print("ci trigger tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
