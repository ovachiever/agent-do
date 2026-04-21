#!/usr/bin/env python3
"""Focused coverage for the meetings family tool."""

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
    help_result = run(["./agent-do", "meetings", "--help"])
    require(help_result.returncode == 0, f"meetings help failed: {help_result.stderr}")
    require("Unified enterprise meeting orchestration" in help_result.stdout, f"unexpected meetings help: {help_result.stdout}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        write_stub(
            tmp / "agent-zoom",
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                echo "zoom:$*"
                """
            ),
        )
        write_stub(
            tmp / "agent-meet",
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                echo "meet:$*"
                """
            ),
        )
        write_stub(
            tmp / "agent-teams",
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                echo "teams:$*"
                """
            ),
        )

        env = os.environ.copy()
        env["AGENT_DO_MEETINGS_TOOL_DIR"] = str(tmp)
        env["AGENT_DO_MEETINGS_ACTIVE_PROVIDER"] = "teams"
        env["AGENT_DO_MEETINGS_FRONTMOST_URL"] = "https://teams.microsoft.com/l/meetup-join/example"

        snapshot_result = run(["./agent-do", "meetings", "snapshot"], env=env)
        require(snapshot_result.returncode == 0, f"meetings snapshot failed: {snapshot_result.stderr}")
        snapshot = json.loads(snapshot_result.stdout)
        require(snapshot["tool"] == "meetings", f"unexpected meetings snapshot: {snapshot}")
        require(snapshot["active_provider"] == "teams", f"unexpected active provider: {snapshot}")
        require(snapshot["providers"]["zoom"]["available"] is True, f"expected zoom availability: {snapshot}")
        require(snapshot["providers"]["teams"]["running"] is True, f"expected teams running: {snapshot}")

        meet_join = run(
            ["./agent-do", "meetings", "join", "https://meet.google.com/abc-defg-hij", "--json"],
            env=env,
        )
        require(meet_join.returncode == 0, f"meet join failed: {meet_join.stderr}")
        meet_join_payload = json.loads(meet_join.stdout)
        require(meet_join_payload["provider"] == "meet", f"unexpected meet provider: {meet_join_payload}")
        require(meet_join_payload["command"] == ["join", "https://meet.google.com/abc-defg-hij"], f"unexpected meet command: {meet_join_payload}")

        teams_mute = run(["./agent-do", "meetings", "mute", "--json"], env=env)
        require(teams_mute.returncode == 0, f"teams mute failed: {teams_mute.stderr}")
        teams_mute_payload = json.loads(teams_mute.stdout)
        require(teams_mute_payload["provider"] == "teams", f"unexpected mute provider: {teams_mute_payload}")
        require(teams_mute_payload["command"] == ["mute"], f"unexpected mute command: {teams_mute_payload}")

        zoom_passthrough = run(["./agent-do", "meetings", "zoom", "start", "--json"], env=env)
        require(zoom_passthrough.returncode == 0, f"zoom passthrough failed: {zoom_passthrough.stderr}")
        zoom_payload = json.loads(zoom_passthrough.stdout)
        require(zoom_payload["provider"] == "zoom", f"unexpected zoom payload: {zoom_payload}")
        require(zoom_payload["command"] == ["start"], f"unexpected zoom command: {zoom_payload}")

    print("meetings tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
