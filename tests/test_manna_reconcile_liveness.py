#!/usr/bin/env python3
"""`manna reconcile --fix` never closes an item: landed_open is advisory in every path, and only a claim coord has positively verified gone is released (mn-4e7229, mn-880173).

Replays three probes in an isolated estate with the real manna and coord
binaries. An in_progress item with a landed `Manna:` trailer commit, claimed by
a session with a living process, is reconciled by a different session with the
call the SessionEnd hook used to make. Before mn-4e7229 the landed_open cure
matched the claimant by respelling its label, read the miss as the orphan
wedge, and closed the item. The independent review of that fix (mn-880173)
aged a living claimant's coord record three days: `peers` without `--all`
omitted the stale record, the guard saw absence, and the item closed over a
living process; a living claimant that had never run a coord command went the
same way. The review's acceptance boundary then retired the close from every
reconcile path: a trailer identifies the work a commit advanced, it does not
approve completion. Reconcile now makes two transitions only, releasing a
claim coord positively verified gone (every bound record dead or stopped) and
clearing resolved blockers; closure is `manna done` or managed acceptance.

Claimants reconcile leaves exactly as it found them (status and claim kept,
nothing fixed, nothing failed, the landed finding and its next step reported):
  1. underscore label with --write-drift (the hook's old exact call)
  2. underscore label without the drift file
  3. plain label with --write-drift
  4. the hook pairing: AGENT_DO_COORD_SESSION and CLAUDE_SESSION_ID both the
     session uuid, no MANNA_* pins
  5. the hook pairing whose coord record aged three days (stale: an aged lease
     on a process coord could not call dead; only the throwaway store's
     timestamps are seeded)
  6. the hook pairing that never ran a coord command (no record bound)
  7. a pinned label worn by a second shell under another token (ambiguous
     identity; dead_claim reports it as a skipped repair and releases nothing)
  8. a pinned scripted lane coord never saw (absence is not evidence of death)
A dead worker's committed but unreviewed item stays unfinished through both
cleanup entry points, and explicit completion still works:
  9. explicit `manna reconcile --fix`: dead_claim names the bound record, the
     claim is released, the row reopens, nothing is marked done; `--only
     landed_open` is refused by name; the operator then closes it with
     `manna done` on the landed evidence
 10. the serve daemon's Apply action, run with the argv its ACTIONS table
     defines under a pinned daemon identity: the same release, never a close
 11. the SessionEnd hook's own call (--only dead_claim,blocker_desync): the
     same release, the landed finding kept in drift.yaml
 12. a live claim-holder closes its own landed item with `manna done`

Nothing here touches the developer's repositories or $HOME.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "test_git_integration.py"
SERVE_DIR = ROOT / "tools" / "agent-manna" / "serve"

_spec = importlib.util.spec_from_file_location("git_integration_fixtures", FIXTURES)
assert _spec is not None and _spec.loader is not None
fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fx)

require = fx.require

CLOSED = "closed on landed evidence"
ADVISORY = "landed_open is advisory"
HOOK_ONLY = "dead_claim,blocker_desync"


def serve_module():
    """The daemon's own module, so the Apply action's argv is read from its ACTIONS table, never retyped here."""
    sys.path.insert(0, str(SERVE_DIR))
    try:
        return importlib.import_module("serve")
    finally:
        sys.path.pop(0)


class Owner:
    """A claimant on a pipe, anchored to a process the fixture owns, in one of the label shapes the probes exercised."""

    def __init__(
        self,
        base: dict[str, str],
        *,
        name: str | None = None,
        hook_pairing: bool = False,
        token: str | None = None,
        coord_session: str | None = None,
    ) -> None:
        self.anchor = subprocess.Popen(["sleep", "600"])
        env = dict(base)
        if hook_pairing:
            # What the Claude SessionStart hook leaves in the shell: the coord
            # anchor and the harness session id, both the session uuid, and no
            # MANNA_* pins. manna derives `claude-<16 hex>` under the fixture's
            # machine key; coord names the session `session-<12 hex>`.
            session = str(uuid.uuid4())
            env["AGENT_DO_COORD_SESSION"] = session
            env["CLAUDE_SESSION_ID"] = session
        else:
            assert name is not None
            env["MANNA_SESSION_ID"] = name
            env["MANNA_SESSION_TOKEN"] = token or (f"{name}-token-" + "x" * 40)
            env["AGENT_DO_COORD_SESSION"] = coord_session or name
        env["AGENT_DO_COORD_PID"] = str(self.anchor.pid)
        env["AGENT_DO_COORD_PID_START"] = fx.lstart(self.anchor.pid)
        self.env = env

    def identity(self, cwd: Path) -> dict:
        """The label and proof manna itself reports for this environment; never predicted."""
        return fx.manna_json(["identity"], cwd=cwd, env=self.env)

    def alive(self) -> bool:
        return self.anchor.poll() is None

    def kill(self) -> None:
        self.anchor.kill()
        self.anchor.wait()


def reconcile(estate: fx.Estate, session: fx.Session, *flags: str, fix: bool = True) -> tuple[int, dict]:
    args = ["reconcile", *(["--fix"] if fix else []), *flags, "--json"]
    proc = fx.manna(args, cwd=estate.primary, env=session.env)
    require(proc.stdout.strip(), f"manna {' '.join(args)} printed no JSON: {proc.stderr}")
    return proc.returncode, json.loads(proc.stdout)


def entries(payload: dict, key: str, item: str) -> list[str]:
    return [entry for entry in (payload.get(key) or []) if item in entry]


def findings(payload: dict, kind: str, item: str) -> list[dict]:
    return [f for f in (payload.get("findings") or []) if f.get("kind") == kind and f.get("issue_id") == item]


def peer_record(estate: fx.Estate, reader: fx.Session, agent_id: str, *flags: str) -> dict | None:
    peers = fx.coord_json(["peers", *flags], cwd=estate.primary, env=reader.env)["peers"]
    return next((peer for peer in peers if peer["agent_id"] == agent_id), None)


def bound_records(estate: fx.Estate, reader: fx.Session, row: dict) -> list[dict]:
    """Every record in coord's complete list that the matcher would bind to this claim."""
    peers = fx.coord_json(["peers", "--all"], cwd=estate.primary, env=reader.env)["peers"]
    return [
        peer
        for peer in peers
        if peer["agent_id"] == row["claimed_by"]
        or (peer.get("manna") or {}).get("proof") == row["claim_token_hash"]
        or (peer.get("manna") or {}).get("session") == row["claimed_by"]
    ]


def coord_store(estate: fx.Estate) -> Path:
    git_dir = subprocess.run(
        ["git", "rev-parse", "--git-dir"], cwd=str(estate.primary), text=True, capture_output=True, check=True
    ).stdout.strip()
    return (estate.primary / git_dir).resolve() / "agent-do" / "coord" / "agents.json"


def age_record(estate: fx.Estate, agent_id: str, *, days: int) -> str:
    """Seed elapsed time on one record of the throwaway coord store: `last_seen` and `lease_expires_at` move back `days`. Only timestamps change; the process stays alive."""
    path = coord_store(estate)
    data = json.loads(path.read_text(encoding="utf-8"))
    agents = data.get("agents")
    require(isinstance(agents, dict) and agent_id in agents, f"the coord store carries {agent_id}: {sorted((agents or {}).keys())}")
    then = (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    agents[agent_id]["last_seen"] = then
    agents[agent_id]["lease_expires_at"] = then
    path.write_text(json.dumps(data), encoding="utf-8")
    return then


def claim_touch_land(estate: fx.Estate, owner: Owner, label: str) -> tuple[str, dict, str]:
    """Create, claim, bind the coord record, and land a trailer commit; returns (item, row, coord agent id)."""
    item = estate.create(f"guard matrix: {label}")
    estate.claim(item, owner)
    row = estate.row(item)
    identity = owner.identity(estate.primary)
    require(
        row["claimed_by"] == identity["session"] and row["claim_token_hash"] == identity["proof"],
        f"{label}: the claim row carries the owner's own label and proof: {row} vs {identity}",
    )
    touched = fx.coord_json(["touch"], cwd=estate.primary, env=owner.env)
    require(
        (touched.get("manna") or {}).get("proof") == row["claim_token_hash"],
        f"{label}: coord touch binds the claim proof in the owner's own process: {touched.get('manna')}",
    )
    estate.external_commit(f"src/{label}.txt", "work\n", f"feat: {label}\n\nManna: {item}")
    return item, row, touched["agent_id"]


def claim_land(estate: fx.Estate, owner: Owner | fx.Session, label: str, path: str) -> tuple[str, dict]:
    """Create, claim, and land a trailer commit without ever running a coord command in the owner's shell."""
    item = estate.create(f"guard matrix: {label}")
    estate.claim(item, owner)
    row = estate.row(item)
    estate.external_commit(f"src/{path}.txt", "work\n", f"feat: {label}\n\nManna: {item}")
    return item, row


def untouched(label: str, estate: fx.Estate, item: str, row: dict, payload: dict, *, skipped: bool = False) -> None:
    """What every claimant reconcile cannot act on has in common: status and claim as they were, nothing fixed, nothing failed, the landed evidence still a finding."""
    after = estate.row(item)
    require(
        after["status"] == "in_progress"
        and after["claimed_by"] == row["claimed_by"]
        and after["claim_token_hash"] == row["claim_token_hash"],
        f"{label}: the item stays in_progress under its claim: {after}",
    )
    require(not entries(payload, "fixed", item), f"{label}: nothing is fixed for this claimant: {payload.get('fixed')}")
    require(not entries(payload, "fix_failures", item), f"{label}: an advisory finding is not a failure: {payload.get('fix_failures')}")
    require(not any(CLOSED in entry for entry in payload.get("fixed") or []), f"{label}: nothing anywhere is closed on landed evidence: {payload.get('fixed')}")
    require(findings(payload, "landed_open", item), f"{label}: the landed evidence is still reported as a finding")
    require(not findings(payload, "dead_claim", item), f"{label}: this claimant is never reported as a dead claim")
    require(bool(findings(payload, "skipped", item)) == skipped, f"{label}: skipped finding expected={skipped}: {findings(payload, 'skipped', item)}")


def live_variant(estate: fx.Estate, other: fx.Session, label: str, owner: Owner, write_drift: bool) -> None:
    item, row, coord_id = claim_touch_land(estate, owner, label)
    record = peer_record(estate, other, coord_id)
    require(record is not None and record["status"] == "active", f"{label}: the owner's coord record is active before reconcile: {record}")
    manna = record.get("manna") or {}
    require(
        manna.get("proof") == row["claim_token_hash"] and manna.get("session") == row["claimed_by"],
        f"{label}: peers --json carries the owner's stored binding: {manna}",
    )
    flags = ("--write-drift",) if write_drift else ()
    _, payload = reconcile(estate, other, *flags)
    untouched(label, estate, item, row, payload)
    if write_drift:
        require((estate.primary / ".manna" / "drift.yaml").is_file(), f"{label}: --write-drift wrote the drift file")
    owner.kill()
    print(f"  ok: {label}: claimant {row['claimed_by']} is coord {coord_id} ({record['status']}); untouched")


def stale_variant(estate: fx.Estate, other: fx.Session, base: dict[str, str]) -> None:
    label = "hook-pairing, record aged three days, process alive"
    owner = Owner(base, hook_pairing=True)
    item, row, coord_id = claim_touch_land(estate, owner, label)
    aged_to = age_record(estate, coord_id, days=3)
    require(owner.alive(), f"{label}: the anchor process is alive before reconcile")
    complete = peer_record(estate, other, coord_id, "--all")
    require(complete is not None and complete["status"] == "stale", f"{label}: coord's complete list classifies the aged record stale: {complete}")
    require((complete.get("manna") or {}).get("proof") == row["claim_token_hash"], f"{label}: the stale record is still bound by the claim proof: {complete}")
    require(peer_record(estate, other, coord_id) is None, f"{label}: the default peers read omits the stale record (the read the old guard took)")
    _, payload = reconcile(estate, other, "--write-drift")
    untouched(label, estate, item, row, payload)
    require(owner.alive(), f"{label}: the anchor process is alive after reconcile")
    owner.kill()
    print(f"  ok: {label}: coord saw {coord_id} stale (last_seen {aged_to}); untouched")


def unbound_variant(estate: fx.Estate, other: fx.Session, base: dict[str, str]) -> None:
    label = "hook-pairing, never ran a coord command, process alive"
    owner = Owner(base, hook_pairing=True)
    item, row = claim_land(estate, owner, label, "unbound")
    require(not bound_records(estate, other, row), f"{label}: no coord record is bound to the claim")
    require(owner.alive(), f"{label}: the anchor process is alive before reconcile")
    _, payload = reconcile(estate, other, "--write-drift")
    untouched(label, estate, item, row, payload)
    require(owner.alive(), f"{label}: the anchor process is alive after reconcile")
    owner.kill()
    print(f"  ok: {label}: claimant {row['claimed_by']} unseen by coord; untouched")


def ambiguous_variant(estate: fx.Estate, other: fx.Session, base: dict[str, str]) -> None:
    label = "pinned label worn by a second shell under another token"
    owner = Owner(base, name="owner-shared")
    item, row = claim_land(estate, owner, label, "shared")
    impostor = Owner(base, name="owner-shared", token="impostor-secret-" + "y" * 40, coord_session="impostor-shell")
    touched = fx.coord_json(["touch"], cwd=estate.primary, env=impostor.env)
    worn = touched.get("manna") or {}
    require(
        worn.get("session") == row["claimed_by"] and worn.get("proof") and worn.get("proof") != row["claim_token_hash"],
        f"{label}: the second shell's record wears the label under a different proof: {worn} vs {row['claim_token_hash']}",
    )
    _, payload = reconcile(estate, other, "--write-drift")
    untouched(label, estate, item, row, payload, skipped=True)
    skipped = findings(payload, "skipped", item)
    require(
        len(skipped) == 1 and "ambiguous" in skipped[0]["detail"] and touched["agent_id"] in skipped[0]["detail"] and "under a different proof" in skipped[0]["detail"],
        f"{label}: dead_claim reports the ambiguity as a skipped repair naming the item and the record: {skipped}",
    )
    owner.kill()
    impostor.kill()
    print(f"  ok: {label}: {touched['agent_id']} wears {row['claimed_by']}; untouched, reported as skipped")


def absent_variant(estate: fx.Estate, other: fx.Session, base: dict[str, str]) -> None:
    label = "pinned scripted lane coord never saw"
    ghost = fx.Session(base, "ghost-session")  # claims through manna, never runs a coord command
    item, row = claim_land(estate, ghost, label, "ghost")
    require(not bound_records(estate, other, row), f"{label}: no coord record is bound to the ghost's claim")
    _, payload = reconcile(estate, other)
    untouched(label, estate, item, row, payload)
    print(f"  ok: {label}: untouched")


def released_not_done(label: str, estate: fx.Estate, item: str, payload: dict) -> dict:
    """A dead worker's committed but unreviewed item after a cleanup entry point: claim released, row reopened, nothing marked done."""
    after = estate.row(item)
    require(after["status"] != "done", f"{label}: a trailer identifies work, it does not approve completion: {after}")
    require(
        after["status"] == "open" and not after.get("claimed_by") and not after.get("claim_token_hash"),
        f"{label}: the dead claim is released and the row reopens: {after}",
    )
    require(entries(payload, "fixed", item) == [item], f"{label}: the release is the only repair recorded for the row: {payload.get('fixed')}")
    require(not any(CLOSED in entry for entry in payload.get("fixed") or []), f"{label}: nothing anywhere is closed on landed evidence: {payload.get('fixed')}")
    require(not entries(payload, "fix_failures", item), f"{label}: the release is clean: {payload.get('fix_failures')}")
    landed = findings(payload, "landed_open", item)
    require(landed and "claim and done" in (landed[0].get("proposed_fix") or ""), f"{label}: the landed evidence stays a finding with its next step: {landed}")
    return after


def dead_variant(estate: fx.Estate, other: fx.Session, base: dict[str, str]) -> None:
    label = "worker dead, committed, unreviewed: explicit --fix"
    owner = Owner(base, hook_pairing=True)
    item, row, coord_id = claim_touch_land(estate, owner, label)
    owner.kill()
    record = peer_record(estate, other, coord_id, "--all")
    require(record is not None and record["status"] == "dead", f"{label}: coord verifies the anchor gone: {record}")

    # Advisory pass: the bound record lets dead_claim name a hook-paired
    # claimant at all (the respelled lookup never found one), and mutates nothing.
    _, advisory = reconcile(estate, other, fix=False)
    dead = findings(advisory, "dead_claim", item)
    require(
        len(dead) == 1 and coord_id in (dead[0].get("evidence") or "") and row["claimed_by"] in dead[0]["detail"],
        f"{label}: dead_claim names the bound record and the claimant: {dead}",
    )
    require(findings(advisory, "landed_open", item), f"{label}: landed_open is reported beside it")
    require(estate.row(item)["status"] == "in_progress", f"{label}: an advisory pass mutates nothing")

    # --only landed_open is refused by name: there is no such repair.
    proc = fx.manna(["reconcile", "--fix", "--only", "landed_open", "--json"], cwd=estate.primary, env=other.env)
    text = proc.stdout + proc.stderr
    require(proc.returncode != 0 and ADVISORY in text and "manna done" in text, f"{label}: --only landed_open refused by name: {proc.returncode} {text[:300]}")
    require(estate.row(item)["status"] == "in_progress", f"{label}: the refusal wrote nothing")

    code, payload = reconcile(estate, other)
    after = released_not_done(label, estate, item, payload)

    # Explicit completion still works: the operator closes it on the landed
    # evidence, the one path that approves the work.
    done = fx.operator_manna(["done", item], cwd=estate.primary, env=base)
    require(done.returncode == 0, f"{label}: the operator closes the reopened item: {done.stderr or done.stdout}")
    require(re.search(r"^authority: evidence$", done.stdout, re.MULTILINE), f"{label}: the close is authorized by the landed evidence: {done.stdout}")
    closed = estate.row(item)
    require(closed["status"] == "done", f"{label}: closed by an explicit hand: {closed}")
    print(f"  ok: {label}: dead_claim named {coord_id}; --fix released the claim (row {after['status']}), closed nothing (exit {code}); operator done closed it on evidence")


def serve_apply_variant(estate: fx.Estate, other: fx.Session, base: dict[str, str]) -> None:
    label = "worker dead, committed, unreviewed: the serve daemon's Apply action"
    serve = serve_module()
    argv = list(serve.ACTIONS["fix"]["argv"])
    require(argv[:2] == ["manna", "reconcile"] and "--fix" in argv, f"{label}: the Apply action is a reconcile --fix: {argv}")
    owner = Owner(base, hook_pairing=True)
    item, row, coord_id = claim_touch_land(estate, owner, label)
    owner.kill()
    record = peer_record(estate, other, coord_id, "--all")
    require(record is not None and record["status"] == "dead", f"{label}: coord verifies the anchor gone: {record}")
    # The daemon runs the dispatcher with its own pinned identity (serve.py
    # run_manna): the same env shape, the same argv, the same cwd.
    env = dict(base)
    env["MANNA_SESSION_ID"] = "serve-fixture"
    env["MANNA_SESSION_TOKEN"] = "serve-fixture-token-" + "z" * 40
    proc = fx.run([str(serve.AGENT_DO), *argv], cwd=estate.primary, env=env)
    require(proc.stdout.strip(), f"{label}: the Apply argv printed JSON: {proc.stderr}")
    payload = json.loads(proc.stdout)
    after = released_not_done(label, estate, item, payload)
    print(f"  ok: {label}: {' '.join(argv)} released the claim on {item} (row {after['status']}), closed nothing (exit {proc.returncode})")


def owner_done_variant(estate: fx.Estate, base: dict[str, str]) -> None:
    label = "live claim-holder closes its own landed item"
    owner = Owner(base, hook_pairing=True)
    item, row, coord_id = claim_touch_land(estate, owner, label)
    done = fx.manna(["done", item], cwd=estate.primary, env=owner.env)
    require(done.returncode == 0, f"{label}: the claim-holder closes: {done.stderr or done.stdout}")
    authority = re.search(r"^authority: (\S+)$", done.stdout, re.MULTILINE)
    closed = estate.row(item)
    require(closed["status"] == "done", f"{label}: closed by its own claim-holder: {closed}")
    owner.kill()
    print(f"  ok: {label}: done closed {item} (authority {authority.group(1) if authority else 'unreported'})")


def hook_path_variant(estate: fx.Estate, other: fx.Session, base: dict[str, str]) -> None:
    label = "worker dead, committed, unreviewed: the SessionEnd hook's own call"
    owner = Owner(base, hook_pairing=True)
    item, row, coord_id = claim_touch_land(estate, owner, label)
    owner.kill()
    record = peer_record(estate, other, coord_id, "--all")
    require(record is not None and record["status"] == "dead", f"{label}: coord verifies the anchor gone: {record}")
    code, payload = reconcile(estate, other, "--only", HOOK_ONLY, "--write-drift")
    after = estate.row(item)
    require(
        after["status"] == "open" and not after.get("claimed_by") and not after.get("claim_token_hash"),
        f"{label}: the dead claim is released and the row reopens; nothing is closed: {after}",
    )
    require(entries(payload, "fixed", item) == [item], f"{label}: the release is the only repair recorded for the row: {payload.get('fixed')}")
    require(not any(CLOSED in entry for entry in payload.get("fixed") or []), f"{label}: the hook's call never closes on a trailer: {payload.get('fixed')}")
    require(not entries(payload, "fix_failures", item), f"{label}: the release is clean: {payload.get('fix_failures')}")
    landed = findings(payload, "landed_open", item)
    require(landed and "claim and done" in (landed[0].get("proposed_fix") or ""), f"{label}: the landed evidence stays a finding with its next step: {landed}")
    drift = (estate.primary / ".manna" / "drift.yaml").read_text(encoding="utf-8")
    require(item in drift and "landed_open" in drift, f"{label}: drift.yaml carries the finding for the next SessionStart")
    print(f"  ok: {label}: --only {HOOK_ONLY} released the claim on {item} (now {after['status']}); nothing closed (exit {code})")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        base = {k: v for k, v in os.environ.items() if k not in fx.THREAD_ENV_KEYS}
        base["AGENT_DO_HOME"] = str(root / "home")
        base["AGENT_DO_TELEMETRY_SUPPRESS"] = "1"
        base["AGENT_DO_HOOK_AI"] = "off"
        base["MANNA_OPERATOR"] = "0"
        base["AGENT_DO_COORD_ISOLATION_NUDGE"] = "0"
        estate = fx.Estate(root, "guard", base, enable=False)
        # The session whose SessionEnd reconcile closed mn-54fe40: pinned,
        # not the claimant, not the operator.
        other = fx.Session(base, "other-session")
        print("live claimants (each untouched):")
        live_variant(estate, other, "underscore-label+write-drift", Owner(base, name="owner-owner_alive"), True)
        live_variant(estate, other, "underscore-label", Owner(base, name="owner-other_alive"), False)
        live_variant(estate, other, "plain-label+write-drift", Owner(base, name="owner-plain"), True)
        live_variant(estate, other, "hook-pairing+write-drift", Owner(base, hook_pairing=True), True)
        print("living claimants coord cannot vouch for (each untouched; status and claim kept):")
        stale_variant(estate, other, base)
        unbound_variant(estate, other, base)
        ambiguous_variant(estate, other, base)
        absent_variant(estate, other, base)
        print("a dead worker's committed but unreviewed item stays unfinished through every cleanup entry point:")
        dead_variant(estate, other, base)
        serve_apply_variant(estate, other, base)
        hook_path_variant(estate, other, base)
        print("explicit completion still works:")
        owner_done_variant(estate, base)
    print("manna reconcile liveness tests passed")


if __name__ == "__main__":
    main()
