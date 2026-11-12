#!/usr/bin/env python3
"""`manna reconcile --fix` never closes a track, and `manna done` keeps the track gate under the lock (mn-9b4359; mn-880173).

Replays the independent review's probe in an isolated estate with the real
manna binary: a paired track, claimed, with a landed `Manna:` trailer commit,
whose every item is done when reconcile inspects the board. Reconcile then
reads coord to rule on the claimant; that read is the synchronization boundary.
A stand-in `agent-do` on PATH answers it, and the first time it is asked it
runs one real manna command against the same board before answering: it
creates a new item under the track, or moves an open item into it. Round two
of mn-9b4359 (408b5e7) put the track gate inside the locked write so the late
item refused the cure's close. mn-880173 then retired the close from every
reconcile path: `landed_open` is advisory, a trailer identifies work and does
not approve completion, so the only transitions reconcile makes are releasing
a claim coord positively verified gone and clearing resolved blockers. The
stand-in therefore reports the track owner dead and bound by its claim proof,
and what this fixture proves at the boundary is:

Variants (the late item arrives between inspection and the repair):
  1. an item is created under the track: the track is not done; its dead
     claim is released and the track reopens; the late item is open under it
  2. an open item is moved into the track: the same
Controls:
  3. `--only landed_open` is refused by name as advisory, nothing written
  4. explicit completion keeps the gate: `manna done` on the track refuses
     while an item is open, naming it, and closes once every item is done

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
ADVISORY = "landed_open is advisory"

# The stand-in agent-do. manna resolves `agent-do` on PATH, finds no sibling
# tools/agent-coord beside it, and routes `coord peers --all --json` through it.
# The first peers read runs the boundary action (one real manna-core command on
# the same board) and then answers with the records in GATE_SHIM_PEERS (the
# track owner, dead, bound by its claim proof); every later call answers the
# same without acting. Every invocation is logged.
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
    print(json.dumps({"success": True, "peers": json.loads(os.environ.get("GATE_SHIM_PEERS", "[]"))}))
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

    def __init__(
        self, root: Path, estate: fx.Estate, stranger: fx.Session, tag: str, action: dict | None, claimant: dict | None = None
    ) -> None:
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
        # coord's verdict on the claimant, as `peers --all --json` would render
        # it: the pinned track owner's record, dead, bound by its claim proof.
        # Positive evidence is the only thing that lets the cure reach its
        # write (mn-880173); an empty estate would refuse as "unseen".
        self.env["GATE_SHIM_PEERS"] = json.dumps(
            [
                {
                    "agent_id": "session-trackowner",
                    "status": "dead",
                    "manna": {"session": claimant["claimed_by"], "proof": claimant["claim_token_hash"], "source": "fixture"},
                }
            ]
            if claimant
            else []
        )
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


def advisory_pass(root: Path, estate: fx.Estate, stranger: fx.Session, tag: str, track: str, claimant: dict) -> None:
    quiet = Boundary(root, estate, stranger, f"{tag}-advisory", None, claimant)
    _, payload = quiet.reconcile()
    require(findings(payload, "landed_open", track), f"{tag}: the track's landed evidence is reported before any fix: {payload.get('findings')}")
    require(estate.row(track)["status"] == "in_progress", f"{tag}: an advisory pass mutates nothing")


def boundary_variant(root: Path, estate: fx.Estate, stranger: fx.Session, label: str, action_for: callable) -> None:
    owner = fx.Session(estate.base, "track-owner")
    track, item, before = build_landed_track(estate, owner, label)
    advisory_pass(root, estate, stranger, label, track, before)
    boundary = Boundary(root, estate, stranger, label, action_for(track), before)
    code, payload = boundary.reconcile("--fix")

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
    require(after["status"] != "done", f"{label}: reconcile never closes a track: {after}")
    require(
        after["status"] == "open" and not after.get("claimed_by") and not after.get("claim_token_hash"),
        f"{label}: the dead claim is released and the track reopens; ownership released is not work accepted: {after}",
    )
    require(entries(payload, "fixed", track) == [track], f"{label}: the release is the only repair recorded for the track: {payload.get('fixed')}")
    require(not any(CLOSED in entry for entry in payload.get("fixed") or []), f"{label}: nothing is closed on landed evidence: {payload.get('fixed')}")
    require(not entries(payload, "fix_failures", track), f"{label}: no failure for the track: {payload.get('fix_failures')}")
    require(findings(payload, "landed_open", track), f"{label}: the landed evidence stays a finding with its next step")
    require(estate.row(item)["status"] == "done", f"{label}: the item done before inspection stays done")
    print(f"  ok: {label}: {late} reached {track} at the boundary; reconcile released the dead claim (now {after['status']}), closed nothing (exit {code})")


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


def only_landed_open_refused(root: Path, estate: fx.Estate, stranger: fx.Session) -> None:
    label = "--only landed_open"
    owner = fx.Session(estate.base, "track-owner")
    track, item, before = build_landed_track(estate, owner, label)
    boundary = Boundary(root, estate, stranger, label, None, before)
    proc = fx.manna(["reconcile", "--fix", "--only", "landed_open", "--json"], cwd=estate.primary, env=boundary.env)
    text = proc.stdout + proc.stderr
    require(proc.returncode != 0 and ADVISORY in text and "manna done" in text, f"{label}: refused by name, naming what closes an item: {proc.returncode} {text[:400]}")
    after = estate.row(track)
    require(
        after["status"] == before["status"] and after["claimed_by"] == before["claimed_by"] and after["claim_token_hash"] == before["claim_token_hash"],
        f"{label}: nothing written: {after}",
    )
    require(estate.row(item)["status"] == "done", f"{label}: the item stays done")
    print(f"  ok: {label}: refused (exit {proc.returncode}); the track is untouched")


def explicit_done_keeps_the_gate(estate: fx.Estate) -> None:
    label = "explicit done"
    owner = fx.Session(estate.base, "track-owner")
    track, item, before = build_landed_track(estate, owner, label)
    late = create_row(estate, owner, "late item", "open under the track", "--track", track)
    commit_board(estate, f"board: file {late}")
    refused = fx.manna(["done", track], cwd=estate.primary, env=owner.env)
    text = refused.stdout + refused.stderr
    require(refused.returncode != 0 and GATE in text and late in text, f"{label}: done refuses over the open item, naming it: {refused.returncode} {text[:400]}")
    require(estate.row(track)["status"] == "in_progress", f"{label}: the track stays in_progress under its claim")
    estate.claim(late, owner)
    closed_late = fx.manna(["done", late], cwd=estate.primary, env=owner.env)
    require(closed_late.returncode == 0, f"{label}: the owner closes the late item: {closed_late.stderr or closed_late.stdout}")
    closed = fx.manna(["done", track], cwd=estate.primary, env=owner.env)
    require(closed.returncode == 0, f"{label}: the owner closes the track once every item is done: {closed.stderr or closed.stdout}")
    after = estate.row(track)
    require(after["status"] == "done", f"{label}: closed by its claim-holder: {after}")
    print(f"  ok: {label}: done refused over {late}, then closed {track} once it was done")


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
        print("items reaching the track between inspection and the repair (reconcile closes nothing):")
        boundary_variant(root, estate, stranger, "item-created-at-boundary", added_action)
        boundary_variant(root, estate, stranger, "item-moved-in-at-boundary", moved_action_for(estate, fx.Session(base, "track-owner")))
        print("controls (the advisory finding is refused as a repair; explicit completion keeps the gate):")
        only_landed_open_refused(root, estate, stranger)
        explicit_done_keeps_the_gate(estate)
    print("manna reconcile track gate tests passed")


if __name__ == "__main__":
    main()
