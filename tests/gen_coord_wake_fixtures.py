#!/usr/bin/env python3
"""Generate the coord-wake/1 wire fixtures from the real CLI in a throwaway board.

Writes tests/fixtures/coord-wake/*.json. Every file is an actual `agent-do coord`
payload (success or exit-2 refusal) produced in an isolated project with
synthetic sessions anchored to this process; no live board or session is
touched. `tests/test_coord_v2.py::test_wake_fixtures` checks the committed
files against the contract's shape, so regenerating after a contract change
keeps consumers (Holy) honest.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_coord_v2 import clean_env, coord, coord_json, lstart, make_project, manna  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "coord-wake"


def refusal(args: list[str], *, cwd: Path, env: dict[str, str]) -> dict:
    result = coord([*args, "--json"], cwd=cwd, env=env)
    if result.returncode != 2:
        raise SystemExit(f"expected an exit-2 refusal for coord {' '.join(args)}: {result.returncode} {result.stdout} {result.stderr}")
    return json.loads(result.stdout)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    def write(name: str, payload: dict) -> None:
        (OUT / f"{name}.json").write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
        written.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        home = tmp_path / "home"
        home.mkdir()
        env_base = dict(os.environ, AGENT_DO_HOME=str(home))
        project = make_project(tmp_path, "coord-wake-fixtures")
        subprocess.run(["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "init"], cwd=project, check=True)
        base = clean_env(env_base)
        base.update(AGENT_DO_HOOK_AI="off", AGENT_DO_TELEMETRY_SUPPRESS="1")

        def session(sid: str) -> dict[str, str]:
            return dict(base, CLAUDE_SESSION_ID=sid, AGENT_DO_COORD_SESSION=sid)

        def host(hid: str) -> dict[str, str]:
            return dict(base, AGENT_DO_COORD_SESSION=hid, AGENT_DO_COORD_PID=str(os.getpid()), AGENT_DO_COORD_PID_START=lstart(os.getpid()))

        lead = session("fixture-lead")
        worker = session("fixture-worker")
        host_a = host("holy-fixture-a")
        host_b = host("holy-fixture-b")
        if manna(["init"], cwd=project, env=lead).returncode != 0:
            raise SystemExit("manna init failed")

        def create(title: str) -> str:
            created = manna(["create", title, "fixture work order"], cwd=project, env=lead)
            return re.search(r"^  id: (mn-[0-9a-f]{6})$", created.stdout, re.MULTILINE).group(1)

        item = create("Overview loader: one SQL aggregation per card")
        if manna(["claim", item], cwd=project, env=worker).returncode != 0:
            raise SystemExit("claim failed")
        coord_json(["touch"], cwd=project, env=worker)
        coord_json(["role", "set", "overseer", "--territory", "."], cwd=project, env=host_a)
        coord_json(["role", "set", "overseer", "--territory", "."], cwd=project, env=host_b)
        (project / ".dev").mkdir()
        approval_args = [
            "drop", "add", ".dev/approval-2026-11-03.md", "--for-item", item,
            "--allows", "write the migration file", "--allows", "local build and test",
            "--excludes", "applying it to staging or production",
            "--authorized-by", "Erik, 2026-11-03, via Claude", "--note", "migration approval",
        ]
        approval = coord_json(approval_args, cwd=project, env=lead)["drop"]
        coord_json(["drop", "add", ".dev/fyi.md", "--for-item", item, "--note", "fyi only"], cwd=project, env=lead)
        coord_json(["drop", "add", ".dev/builders.md", "--for", "any", "--action", "--note", "everyone"], cwd=project, env=lead)
        quiet = create("Quiet lane")
        manna(["claim", quiet], cwd=project, env=session("fixture-quiet-worker"))
        coord_json(["drop", "add", ".dev/quiet.md", "--for-item", quiet, "--action", "--note", "worker never registered"], cwd=project, env=lead)

        write("demands-wanted", coord_json(["drops", "--wake"], cwd=project, env=host_a))
        write("refusal-recipient-is-caller", refusal(["drop", "wake", approval["id"]], cwd=project, env=worker))
        request = coord_json(["drop", "wake", approval["id"]], cwd=project, env=host_a)
        write("request-requested", request)
        rid = request["request"]["id"]
        write("refusal-held-by-other", refusal(["drop", "wake", approval["id"]], cwd=project, env=host_b))
        write("request-duplicate", coord_json(["drop", "wake", approval["id"]], cwd=project, env=host_a))
        write("waiting-pending-readiness", coord_json(["drop", "wake", approval["id"], "--request", rid, "--waiting", "session busy: a tool call is in flight"], cwd=project, env=host_a))
        write("demands-held-by-consumer", coord_json(["drops", "--wake"], cwd=project, env=host_b))
        write("outcome-submitted", coord_json(["drop", "wake", approval["id"], "--request", rid, "--outcome", "submitted", "--evidence", "tmux pane %5, server epoch 12, composer empty before submit"], cwd=project, env=host_a))
        write("outcome-submitted-replay", coord_json(["drop", "wake", approval["id"], "--request", rid, "--outcome", "submitted", "--evidence", "replayed after reconnect"], cwd=project, env=host_a))
        write("refusal-submitted-needs-after", refusal(["drop", "wake", approval["id"]], cwd=project, env=host_b))
        coord_json(["drop", "ack", approval["id"]], cwd=project, env=worker)
        write("demands-acknowledged-held", coord_json(["drops", "--wake"], cwd=project, env=host_a))
        write("refusal-acknowledged", refusal(["drop", "wake", approval["id"]], cwd=project, env=host_a))
        revised = coord_json([*approval_args[:-1], "migration approval, scope clarified"], cwd=project, env=lead)["drop"]
        r2 = coord_json(["drop", "wake", revised["id"], "--revision", "2"], cwd=project, env=host_a)
        write("request-new-revision", r2)
        write("outcome-unknown", coord_json(["drop", "wake", revised["id"], "--request", r2["request"]["id"], "--outcome", "unknown", "--evidence", "the host link reconnected before the submit reply arrived"], cwd=project, env=host_a))
        write("refusal-unknown-outstanding", refusal(["drop", "wake", revised["id"]], cwd=project, env=host_b))
        write("outcome-failed-after-unknown", coord_json(["drop", "wake", revised["id"], "--request", r2["request"]["id"], "--outcome", "failed", "--evidence", "pane scrollback shows no submission; composer still holds the draft"], cwd=project, env=host_a))
        write("refusal-no-evidence", refusal(["drop", "wake", revised["id"], "--request", r2["request"]["id"], "--outcome", "submitted"], cwd=project, env=host_a))
        manna(["abandon", item], cwd=project, env=worker)
        manna(["claim", item], cwd=project, env=session("fixture-replacement"))
        coord_json(["touch"], cwd=project, env=session("fixture-replacement"))
        write("demands-stale-reassigned", coord_json(["drops", "--wake"], cwd=project, env=host_a))
        write("refusal-stale", refusal(["drop", "wake", revised["id"]], cwd=project, env=host_a))

    readme = OUT / "README.md"
    readme.write_text(
        "# coord-wake/1 fixtures\n\n"
        "Real `agent-do coord` payloads from an isolated board, written by `tests/gen_coord_wake_fixtures.py`.\n"
        "Session ids, pids, paths and timestamps are the fixture run's own. `tests/test_coord_v2.py::test_wake_fixtures`\n"
        "checks every file against the contract's required keys. Contract: `docs/COORD-WAKE.md`.\n\n"
        + "".join(f"- `{name}.json`\n" for name in written)
    )
    print(f"wrote {len(written)} fixtures to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
