#!/usr/bin/env python3
"""`manna reconcile --fix` never closes a track over an item that reached it after inspection (mn-9b4359, review round two).

Replays the independent review's probe in an isolated estate with the real
manna binary: a paired track, claimed, with a landed `Manna:` trailer commit,
whose every item is done when reconcile inspects the board. The landed_open
cure then reads coord to rule on the claimant's liveness; that read is the
synchronization boundary. A stand-in `agent-do` on PATH answers it, and the
first time it is asked it runs one real manna command against the same board
before answering: it creates a new item under the track, or moves an open item
into it. Before the fix the cure checked the track gate against the issue list
it had loaded before the coord read, and its locked write compared only the
track row with that list, so the late item was invisible and the track closed
over it (review.md, race.log, 2026-11-04). The gate now re-runs against the
rows under the board lock, inside the write itself, and the store refuses any
transition to done that would close a track over an open item, whatever path
asks for it.

Variants:
  1. an item is created under the track between inspection and the write:
     refused, the refusal names the new item, the track keeps its claim
  2. an open item is moved into the track between inspection and the write:
     refused, the refusal names the moved item, the track keeps its claim
Control:
  3. nothing changes at the boundary: the cure still closes the track on the
     landed evidence and releases the orphaned claim

Nothing here touches the developer's repositories or $HOME.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "test_git_integration.py"
MANNA_CORE = ROOT / "tools" / "agent-manna" / "target" / "release" / "manna-core"

_spec = importlib.util.spec_from_file_location("git_integration_fixtures", FIXTURES)
assert _spec is not None and _spec.loader is not None
fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fx)

require = fx.require

GATE = "A track closes only when every item in it is done"
CLOSED = "closed on landed evidence"

# The stand-in agent-do. manna resolves `agent-do` on PATH, finds no sibling
# tools/agent-coord beside it, and routes `coord peers --json` through it. The
# first peers read runs the boundary action (one real manna-core command on the
# same board) and then answers like an empty estate; every later call answers
# the same without acting. Every invocation is logged.
SHIM = """#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
with Path(os.environ["GATE_SHIM_LOG"]).open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1:3] == ["coord", "peers"]:
    marker = Path(os.environ["GATE_SHIM_ONCE"])
    if not marker.exists():
        marker.write_text("fired", encoding="utf-8")
        action = json.loads(os.environ["GATE_SHIM_ACTION"])
        if action:
            env = dict(os.environ)
            env.update(action["env"])
            proc = subprocess.run(
                [os.environ["GATE_SHIM_CORE"], *action["args"]],
                cwd=os.environ["GATE_SHIM_CWD"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            Path(os.environ["GATE_SHIM_RESULT"]).write_text(
                json.dumps({"code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}),
                encoding="utf-8",
            )
    print(json.dumps({"success": True, "peers": []}))
    sys.exit(0)
print(json.dumps({"success": True}))
"""

LATE_ARRIVAL = {
    "MANNA_SESSION_ID": "late-arrival",
    "MANNA_SESSION_TOKEN": "late-arrival-token-" + "x" * 40,
}


def create_row(estate: fx.Estate, session: fx.Session, *args: str) -> str:
    proc = fx.manna(["create", *args], cwd=estate.primary, env=session.env)
    require(proc.returncode == 0, f"manna create {' '.join(args)} failed: {proc.stderr or proc.stdout}")
    return fx.extract_id(proc.stdout)


def commit_board(estate: fx.Estate, message: str) -> None:
    fx.git(estate.primary, "add", ".manna", ".handoff")
    fx.git(estate.primary, "commit", "-qm", message)


def build_landed_track(estate: fx.Estate, owner: fx.Session, label: str) -> tuple[str, str, dict]:
    """A claimed paired track with one done item and a landed trailer commit; returns (track, item, track row)."""
    track = create_row(estate, owner, f"track {label}", "fixture track", "--type", "track")
    item = create_row(estate, owner, f"item {label}", "fixture item", "--track", track)
    commit_board(estate, f"board: file {track} and {item}")
    estate.claim(track, owner)
    estate.claim(item, owner)
    estate.external_commit(f"src/{label}.txt", "work\n", f"feat: {label}\n\nManna: {track}")
    done = fx.manna(["done", item], cwd=estate.primary, env=owner.env)
    require(done.returncode == 0, f"{label}: the owner closes the item: {done.stderr or done.stdout}")
    row = estate.row(track)
    require(
        row["status"] == "in_progress" and row["claimed_by"] == "track-owner" and row.get("claim_token_hash"),
        f"{label}: the track is in_progress under the owner's claim before reconcile: {row}",
    )
    children = fx.manna_json(["show", track], cwd=estate.primary, env=owner.env)["children"]
    require(children["total"] == 1 and children["done"] == 1, f"{label}: every item is done at inspection: {children}")
    return track, item, row


class Boundary:
    """One reconcile run with the stand-in on PATH and a boundary action, or none."""

    def __init__(self, root: Path, estate: fx.Estate, stranger: fx.Session, tag: str, action: dict | None) -> None:
        self.dir = root / "shims" / tag
        self.dir.mkdir(parents=True)
        shim = self.dir / "agent-do"
        shim.write_text(SHIM, encoding="utf-8")
        shim.chmod(0o755)
        self.log = self.dir / "calls.jsonl"
        self.marker = self.dir / "fired"
        self.result = self.dir / "result.json"
        self.env = dict(stranger.env)
        self.env["PATH"] = f"{self.dir}:{stranger.env['PATH']}"
        self.env["GATE_SHIM_LOG"] = str(self.log)
        self.env["GATE_SHIM_ONCE"] = str(self.marker)
        self.env["GATE_SHIM_ACTION"] = json.dumps(action)
        self.env["GATE_SHIM_CORE"] = str(MANNA_CORE)
        self.env["GATE_SHIM_CWD"] = str(estate.primary)
        self.env["GATE_SHIM_RESULT"] = str(self.result)
        self.estate = estate

    def reconcile(self, *flags: str) -> tuple[int, dict]:
        args = ["reconcile", *flags, "--json"]
        proc = fx.manna(args, cwd=self.estate.primary, env=self.env)
        require(proc.stdout.strip(), f"manna {' '.join(args)} printed no JSON: {proc.stderr}")
        return proc.returncode, json.loads(proc.stdout)

    def peers_reads(self) -> int:
        if not self.log.exists():
            return 0
        return sum(1 for line in self.log.read_text(encoding="utf-8").splitlines() if json.loads(line)[:2] == ["coord", "peers"])

    def action_result(self) -> dict:
        require(self.marker.exists(), "the boundary fired during reconcile")
        require(self.result.exists(), "the boundary action ran and recorded its result")
        return json.loads(self.result.read_text(encoding="utf-8"))


def entries(payload: dict, key: str, item: str) -> list[str]:
    return [entry for entry in (payload.get(key) or []) if item in entry]


def findings(payload: dict, kind: str, item: str) -> list[dict]:
    return [f for f in (payload.get("findings") or []) if f.get("kind") == kind and f.get("issue_id") == item]


def advisory_pass(root: Path, estate: fx.Estate, stranger: fx.Session, tag: str, track: str) -> None:
    quiet = Boundary(root, estate, stranger, f"{tag}-advisory", None)
    _, payload = quiet.reconcile()
    require(findings(payload, "landed_open", track), f"{tag}: the track's landed evidence is reported before any fix: {payload.get('findings')}")
    require(estate.row(track)["status"] == "in_progress", f"{tag}: an advisory pass mutates nothing")


def refused_variant(root: Path, estate: fx.Estate, stranger: fx.Session, label: str, action_for: callable) -> None:
    owner = fx.Session(estate.base, "track-owner")
    track, item, before = build_landed_track(estate, owner, label)
    advisory_pass(root, estate, stranger, label, track)
    boundary = Boundary(root, estate, stranger, label, action_for(track))
    code, payload = boundary.reconcile("--fix", "--only", "landed_open")

    acted = boundary.action_result()
    require(acted["code"] == 0, f"{label}: the boundary's manna command succeeded against the live board: {acted}")
    late = fx.extract_id(acted["stdout"])
    late_row = estate.row(late)
    require(
        late_row["status"] == "open" and late_row.get("track") == track,
        f"{label}: the late item is open under the track after reconcile: {late_row}",
    )
    require(boundary.peers_reads() >= 1, f"{label}: reconcile read coord at least once: {boundary.log.read_text() if boundary.log.exists() else ''}")

    after = estate.row(track)
    require(
        after["status"] == "in_progress"
        and after["claimed_by"] == before["claimed_by"]
        and after["claim_token_hash"] == before["claim_token_hash"]
        and after.get("claimed_at") == before.get("claimed_at"),
        f"{label}: the track stays in_progress under its claim: {after}",
    )
    require(not entries(payload, "fixed", track), f"{label}: nothing is fixed for the track: {payload.get('fixed')}")
    refusals = entries(payload, "fix_failures", track)
    require(
        len(refusals) == 1 and GATE in refusals[0] and late in refusals[0],
        f"{label}: one refusal names the gate and the late item {late}: {refusals}",
    )
    require(code != 0, f"{label}: a refused fix exits nonzero, got {code}")
    require(estate.row(item)["status"] == "done", f"{label}: the item done before inspection stays done")
    print(f"  ok: {label}: {late} reached {track} at the boundary; refused: {refusals[0].split(': ', 1)[1]}")


def added_action(track: str) -> dict:
    return {"env": LATE_ARRIVAL, "args": ["create", "late item", "created after inspection", "--track", track]}


def moved_action_for(estate: fx.Estate, owner: fx.Session) -> callable:
    other = create_row(estate, owner, "track elsewhere", "holds the stray until the boundary", "--type", "track")
    stray = create_row(estate, owner, "stray item", "moves at the boundary", "--track", other)
    commit_board(estate, f"board: file {other} and {stray}")
    require(estate.row(stray)["status"] == "open" and not estate.row(stray).get("claimed_by"), "the stray is open and unclaimed")

    def action(track: str) -> dict:
        return {"env": LATE_ARRIVAL, "args": ["update", stray, "--track", track]}

    return action


def control_variant(root: Path, estate: fx.Estate, stranger: fx.Session) -> None:
    label = "all-items-done"
    owner = fx.Session(estate.base, "track-owner")
    track, item, before = build_landed_track(estate, owner, label)
    advisory_pass(root, estate, stranger, label, track)
    boundary = Boundary(root, estate, stranger, label, None)
    code, payload = boundary.reconcile("--fix", "--only", "landed_open")
    closed = entries(payload, "fixed", track)
    require(
        len(closed) == 1 and CLOSED in closed[0] and before["claimed_by"] in closed[0],
        f"{label}: the cure closes the track on the landed evidence and names the released claim: {closed} / {payload.get('fix_failures')}",
    )
    require(not entries(payload, "fix_failures", track), f"{label}: no refusal for a track whose items are all done: {payload.get('fix_failures')}")
    after = estate.row(track)
    require(
        after["status"] == "done" and not after.get("claimed_by") and not after.get("claim_token_hash"),
        f"{label}: closed and released: {after}",
    )
    require(estate.row(item)["status"] == "done", f"{label}: the item stays done")
    print(f"  ok: {label}: --fix closed {track} (exit {code})")


def main() -> None:
    require(MANNA_CORE.is_file(), f"release binary missing at {MANNA_CORE}; run cargo build --release")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        base = {k: v for k, v in os.environ.items() if k not in fx.THREAD_ENV_KEYS}
        base["AGENT_DO_HOME"] = str(root / "home")
        base["AGENT_DO_TELEMETRY_SUPPRESS"] = "1"
        base["AGENT_DO_HOOK_AI"] = "off"
        base["MANNA_OPERATOR"] = "0"
        base["AGENT_DO_COORD_ISOLATION_NUDGE"] = "0"
        estate = fx.Estate(root, "track-gate", base, enable=False)
        # The reconciling session: pinned, not the claimant, not the operator,
        # exactly as the SessionEnd hook's reconcile runs in another lane.
        stranger = fx.Session(base, "other-session")
        print("items reaching the track between inspection and the write (each refused):")
        refused_variant(root, estate, stranger, "item-created-at-boundary", added_action)
        refused_variant(root, estate, stranger, "item-moved-in-at-boundary", moved_action_for(estate, fx.Session(base, "track-owner")))
        print("control (legitimate completion still closes):")
        control_variant(root, estate, stranger)
    print("manna reconcile track gate tests passed")


if __name__ == "__main__":
    main()
