#!/usr/bin/env python3
"""Dispatcher regressions around external agent-* binaries on PATH."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_exec(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        fake_home = tmp_path / "home"
        fake_home.mkdir()

        make_exec(
            fake_bin / "agent-mail",
            "#!/usr/bin/env bash\n"
            "echo 'external agent-mail invoked'\n",
        )

        make_exec(
            fake_bin / "agent-externaldemo",
            "#!/usr/bin/env bash\n"
            "if [[ \"${1:-}\" == \"--help\" ]]; then\n"
            "  echo 'agent-externaldemo - external test tool'\n"
            "else\n"
            "  echo 'externaldemo:' \"$@\"\n"
            "fi\n",
        )

        registry = {
            "tools": {
                "externaldemo": {
                    "description": "External test tool",
                    "commands": {
                        "ping": "Ping command",
                    },
                }
            }
        }
        (fake_home / "registry.yaml").write_text(json.dumps(registry))

        env = dict(os.environ)
        env["AGENT_DO_HOME"] = str(fake_home)
        env["PATH"] = f"{fake_bin}:{env['PATH']}"

        mail = run([str(AGENT_DO), "mail", "--help"], env=env)
        require(mail.returncode != 0, f"expected unregistered external tool to fail: {mail.stdout} {mail.stderr}")
        combined = f"{mail.stdout}\n{mail.stderr}"
        require("Unknown tool: mail" in combined, f"unexpected mail output: {combined}")
        require("external agent-mail invoked" not in combined, "unregistered external tool should not execute")

        external = run([str(AGENT_DO), "externaldemo", "--help"], env=env)
        require(external.returncode == 0, f"expected registered external tool to work: {external.stderr}")
        require(
            "agent-externaldemo - external test tool" in external.stdout,
            f"unexpected external tool help output: {external.stdout}",
        )

    print("dispatch tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
