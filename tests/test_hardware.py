#!/usr/bin/env python3
"""Focused coverage for the hardware family tool."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_stub(path: Path, body: str) -> None:
    path.write_text(body.strip() + "\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def main() -> int:
    help_result = run(["./agent-do", "hardware", "--help"])
    require(help_result.returncode == 0, f"hardware help failed: {help_result.stderr}")
    require("Unified hardware device control" in help_result.stdout, f"unexpected hardware help: {help_result.stdout}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        write_stub(
            tmp / "agent-serial",
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                case "${1:-}" in
                  list) printf '%s\n' '/dev/tty.TEST1' '/dev/tty.TEST2' ;;
                  *) echo "serial:$*" ;;
                esac
                """
            ),
        )
        write_stub(
            tmp / "agent-bluetooth",
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                case "${1:-}" in
                  status) printf '%s\n' 'Power: On' 'Discoverable: No' ;;
                  devices) printf '%s\n' 'Magic Keyboard 11-22-33' 'Trackpad 44-55-66' ;;
                  *) echo "bluetooth:$*" ;;
                esac
                """
            ),
        )
        write_stub(
            tmp / "agent-usb",
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                case "${1:-}" in
                  list) printf '%s\n' 'USB Flash Drive' 'Docking Station' ;;
                  *) echo "usb:$*" ;;
                esac
                """
            ),
        )
        write_stub(
            tmp / "agent-printer",
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                case "${1:-}" in
                  list) printf '%s\n' 'printer Office is idle.' '' 'Default: Office' ;;
                  *) echo "printer:$*" ;;
                esac
                """
            ),
        )
        write_stub(
            tmp / "agent-midi",
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                case "${1:-}" in
                  snapshot) printf '%s\n' '{"tool":"midi","platform":"macOS","devices":[{"name":"Launchkey"}],"tools":{"python:mido":true}}' ;;
                  *) echo "midi:$*" ;;
                esac
                """
            ),
        )

        env = os.environ.copy()
        env["AGENT_DO_HARDWARE_TOOL_DIR"] = str(tmp)

        snapshot_result = run(["./agent-do", "hardware", "snapshot"], env=env)
        require(snapshot_result.returncode == 0, f"hardware snapshot failed: {snapshot_result.stderr}")
        snapshot = json.loads(snapshot_result.stdout)
        require(snapshot["tool"] == "hardware", f"unexpected snapshot tool: {snapshot}")
        require(snapshot["serial"]["ports"] == ["/dev/tty.TEST1", "/dev/tty.TEST2"], f"unexpected serial snapshot: {snapshot}")
        require(
            snapshot["bluetooth"]["status"]["status_lines"] == ["Power: On", "Discoverable: No"],
            f"unexpected bluetooth status: {snapshot}",
        )
        require(
            snapshot["usb"]["devices"] == ["USB Flash Drive", "Docking Station"],
            f"unexpected usb devices: {snapshot}",
        )
        require(snapshot["printer"]["printers"] == ["printer Office is idle.", "Default: Office"], f"unexpected printers: {snapshot}")
        require(snapshot["midi"]["snapshot"]["devices"][0]["name"] == "Launchkey", f"unexpected midi snapshot: {snapshot}")

        delegate_result = run(["./agent-do", "hardware", "serial", "list", "--json"], env=env)
        require(delegate_result.returncode == 0, f"hardware serial delegation failed: {delegate_result.stderr}")
        delegated = json.loads(delegate_result.stdout)
        require(delegated["success"] is True, f"unexpected delegated payload: {delegated}")
        require(delegated["domain"] == "serial", f"unexpected delegated domain: {delegated}")
        require(delegated["command"] == ["list"], f"unexpected delegated command: {delegated}")
        require("/dev/tty.TEST1" in delegated["result"], f"unexpected delegated result: {delegated}")

    print("hardware tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
