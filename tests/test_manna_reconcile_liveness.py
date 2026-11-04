#!/usr/bin/env python3
"""`manna reconcile --fix` never closes an in_progress item over a live claimant (mn-4e7229).

Replays the 2026-11-03 probe in an isolated estate with the real manna and
coord binaries: an in_progress item with a landed `Manna:` trailer commit,
claimed by a session whose coord record is live (touched seconds earlier,
anchor process alive), reconciled by a different session with the exact call
the SessionEnd hook makes. Before the fix the landed_open cure matched the
claimant by respelling its label (`session-` plus sixteen alphanumerics),
which names nothing coord uses for a hook-pinned Claude session (manna labels
it `claude-<16 hex>`, coord names it `session-<12 hex>`), read the miss as the
orphan wedge, and closed the item. The claimant is now found by the coord
record's bound Manna proof or label, and any bound record coord has not
classified dead, stopped, or stale blocks the close.

Live claimants, each refused:
  1. underscore label with --write-drift (the hook's exact call)
  2. underscore label without the drift file
  3. plain label with --write-drift (matched before the fix too; still refused)
  4. the hook pairing: AGENT_DO_COORD_SESSION and CLAUDE_SESSION_ID both the
     session uuid, no MANNA_* pins
Controls, so the cure still breaks the wedge it was built for:
  5. the hook pairing whose anchor process died: dead_claim names the bound
     record (impossible before the binding match) and --fix closes on the
     landed evidence without a second, stale release
  6. a claimant coord never saw: absence is still the orphan wedge and closes

Nothing here touches the developer's repositories or $HOME.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "test_git_integration.py"

_spec = importlib.util.spec_from_file_location("git_integration_fixtures", FIXTURES)
assert _spec is not None and _spec.loader is not None
fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fx)

require = fx.require

LIVE_REFUSAL = "not closing over live work"
CLOSED = "closed on landed evidence"


class Owner:
    """A claimant on a pipe, anchored to a process the fixture owns, in one of the label shapes the probe exercised."""

    def __init__(self, base: dict[str, str], *, name: str | None = None, hook_pairing: bool = False) -> None:
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
            env["MANNA_SESSION_TOKEN"] = f"{name}-token-" + "x" * 40
            env["AGENT_DO_COORD_SESSION"] = name
        env["AGENT_DO_COORD_PID"] = str(self.anchor.pid)
        env["AGENT_DO_COORD_PID_START"] = fx.lstart(self.anchor.pid)
        self.env = env

    def identity(self, cwd: Path) -> dict:
        """The label and proof manna itself reports for this environment; never predicted."""
        return fx.manna_json(["identity"], cwd=cwd, env=self.env)

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
    code, payload = reconcile(estate, other, *flags)
    after = estate.row(item)
    require(
        after["status"] == "in_progress"
        and after["claimed_by"] == row["claimed_by"]
        and after["claim_token_hash"] == row["claim_token_hash"],
        f"{label}: the live claimant's item stays in_progress under its claim: {after}",
    )
    require(not entries(payload, "fixed", item), f"{label}: nothing is fixed for a live claimant: {payload.get('fixed')}")
    refusals = entries(payload, "fix_failures", item)
    require(
        len(refusals) == 1 and LIVE_REFUSAL in refusals[0] and coord_id in refusals[0],
        f"{label}: one refusal names the live coord session: {refusals}",
    )
    require(code != 0, f"{label}: a refused fix exits nonzero, got {code}")
    require(findings(payload, "landed_open", item), f"{label}: the landed evidence is still reported as a finding")
    require(not findings(payload, "dead_claim", item), f"{label}: a live claimant is never a dead claim")
    if write_drift:
        require((estate.primary / ".manna" / "drift.yaml").is_file(), f"{label}: --write-drift wrote the drift file")
    owner.kill()
    print(f"  ok: {label}: claimant {row['claimed_by']} is coord {coord_id}; refused: {refusals[0].split(': ', 1)[1]}")


def dead_variant(estate: fx.Estate, other: fx.Session, base: dict[str, str]) -> None:
    label = "hook-pairing, anchor died"
    owner = Owner(base, hook_pairing=True)
    item, row, coord_id = claim_touch_land(estate, owner, label)
    owner.kill()
    record = peer_record(estate, other, coord_id)
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

    code, payload = reconcile(estate, other)
    closed = entries(payload, "fixed", item)
    require(len(closed) == 1 and CLOSED in closed[0] and row["claimed_by"] in closed[0], f"{label}: the cure closes on the landed evidence: {closed}")
    require(not entries(payload, "fix_failures", item), f"{label}: no second release is attempted for the row the close already released: {payload.get('fix_failures')}")
    after = estate.row(item)
    require(after["status"] == "done" and not after.get("claimed_by") and not after.get("claim_token_hash"), f"{label}: closed and released: {after}")
    print(f"  ok: {label}: dead_claim named {coord_id}; --fix closed {item} (exit {code})")


def absent_variant(estate: fx.Estate, other: fx.Session, base: dict[str, str]) -> None:
    label = "claimant coord never saw"
    ghost = fx.Session(base, "ghost-session")  # claims through manna, never runs a coord command
    item = estate.create(f"guard matrix: {label}")
    estate.claim(item, ghost)
    row = estate.row(item)
    estate.external_commit(f"src/{label.replace(' ', '-')}.txt", "work\n", f"feat: {label}\n\nManna: {item}")
    peers = fx.coord_json(["peers", "--all"], cwd=estate.primary, env=other.env)["peers"]
    require(
        all(
            peer["agent_id"] != "session-ghostsession"
            and (peer.get("manna") or {}).get("proof") != row["claim_token_hash"]
            and (peer.get("manna") or {}).get("session") != row["claimed_by"]
            for peer in peers
        ),
        f"{label}: no coord record is bound to the ghost's claim: {peers}",
    )
    code, payload = reconcile(estate, other)
    closed = entries(payload, "fixed", item)
    require(len(closed) == 1 and CLOSED in closed[0], f"{label}: absence is the orphan wedge and still closes: {closed} / {payload.get('fix_failures')}")
    after = estate.row(item)
    require(after["status"] == "done" and not after.get("claimed_by"), f"{label}: closed and released: {after}")
    print(f"  ok: {label}: --fix closed {item} (exit {code})")


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
        print("live claimants (each refused):")
        live_variant(estate, other, "underscore-label+write-drift", Owner(base, name="owner-owner_alive"), True)
        live_variant(estate, other, "underscore-label", Owner(base, name="owner-other_alive"), False)
        live_variant(estate, other, "plain-label+write-drift", Owner(base, name="owner-plain"), True)
        live_variant(estate, other, "hook-pairing+write-drift", Owner(base, hook_pairing=True), True)
        print("controls (the wedge still closes):")
        dead_variant(estate, other, base)
        absent_variant(estate, other, base)
    print("manna reconcile liveness tests passed")


if __name__ == "__main__":
    main()
