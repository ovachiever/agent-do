#!/usr/bin/env python3
"""coord proves a session gone only through a verified durable anchor; a tool-call shell exiting never does (mn-dd9be1).

Reproduces the Claude case with the real coord and manna binaries in an
isolated estate. A long-lived runtime process stands for the Claude Code
process; coord calls made from its children walk the ancestry back to it and
record `pid`, `pid_start`, `anchor: runtime`, `anchor_verified: true`. The
pulse hook, by contrast, backgrounds and disowns its coord call and exits
first, so that call runs orphaned: its ancestry ends at launchd, the walk
cannot reach the runtime, and the fallback is a shell gone in milliseconds.
Before the fix that registration rewrote the live lane's record (observed
2026-11-04 on the agent-do board: `pid` of an exited shell, `pid_start` empty),
`process_liveness` read the missing pid as death, and another session's
SessionEnd reconcile released the lane's claim.

Scenarios:
  1. the Claude case: a foreground registration anchors to the runtime; an
     orphaned pulse registration refreshes presence but never downgrades the
     verified anchor; another session reads the lane active; the SessionEnd
     reconcile (`--fix --only dead_claim,blocker_desync`) and the full
     `--fix` both keep the lane's claim; the Manna binding is preserved
  2. first contact from an orphaned process: the record is marked
     unverified; it reads active, then idle, then stale by lease, never dead;
     the lane's claim survives the SessionEnd reconcile; the owning session's
     next foreground registration repairs the anchor to the runtime
  3. genuine death preserved: the runtime process ends; peers read the lane
     dead with the verdict `gone`, and the SessionEnd reconcile releases its
     claim (the row reopens; nothing is marked done)
  4. process-reuse protection and `stop` preserved: an explicit pin whose
     start time does not match reads dead; a stopped session reads stopped
  5. legacy records (written before the anchor kind existed): a gone pid with
     an empty start time reads by lease, never dead; a gone pid with a real
     start time still reads dead

Nothing here touches the developer's repositories or $HOME.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "test_git_integration.py"

_spec = importlib.util.spec_from_file_location("git_integration_fixtures", FIXTURES)
assert _spec is not None and _spec.loader is not None
fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fx)

require = fx.require
COORD = fx.COORD
MANNA = fx.MANNA
HOOK_ONLY = "dead_claim,blocker_desync"
CLOSED = "closed on landed evidence"

# The runtime process: reads one JSON request per line and runs it as its
# child, so every coord call made through it has this process as an ancestor
# (the way every tool-call shell has the Claude Code process as one).
RUNTIME_SCRIPT = r'''
import json, os, subprocess, sys
comm = subprocess.run(["ps", "-o", "comm=", "-p", str(os.getpid())], capture_output=True, text=True).stdout.strip()
lstart = subprocess.run(["ps", "-p", str(os.getpid()), "-o", "lstart="], capture_output=True, text=True).stdout.strip()
print(json.dumps({"hello": True, "pid": os.getpid(), "lstart": lstart, "comm": os.path.basename(comm)}), flush=True)
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    if req.get("exit"):
        break
    env = dict(os.environ)
    env.update(req.get("env") or {})
    if req.get("detach"):
        proc = subprocess.run(["bash", "-c", req["script"]], env=env, cwd=req.get("cwd"), capture_output=True, text=True)
    else:
        proc = subprocess.run(req["argv"], env=env, cwd=req.get("cwd"), input=req.get("stdin"), capture_output=True, text=True)
    print(json.dumps({"code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}), flush=True)
'''

# The pulse hook's shape (hooks/claude/agent-do-pulse-record.sh): the coord
# call runs in a subshell that is backgrounded and disowned, and the hook
# shell exits at once. The subshell is reparented to launchd before coord runs.
PULSE_SCRIPT = r'''
( printf '%s' "$PULSE_PAYLOAD" | "$COORD" pulse record --from-hook >/dev/null 2>&1; : > "$MARKER" ) &
disown 2>/dev/null || true
exit 0
'''

WHOAMI_SCRIPT = r'''
( "$COORD" whoami --json > "$OUT" 2>/dev/null; : > "$MARKER" ) &
disown 2>/dev/null || true
exit 0
'''


class Runtime:
    """A long-lived agent runtime process. Its children are the tool-call shells."""

    def __init__(self, root: Path, base: dict[str, str], name: str) -> None:
        script = root / f"runtime-{name}.py"
        script.write_text(RUNTIME_SCRIPT, encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=base, bufsize=1
        )
        assert self.proc.stdout is not None and self.proc.stdin is not None
        hello = json.loads(self.proc.stdout.readline())
        self.pid: int = hello["pid"]
        self.lstart: str = hello["lstart"]
        self.comm: str = hello["comm"]
        require(bool(self.lstart) and bool(self.comm), f"the runtime reports its start time and process name: {hello}")

    def _ask(self, request: dict) -> dict:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def run(self, argv: list[str], *, env: dict[str, str], cwd: Path, stdin: str | None = None) -> dict:
        return self._ask({"argv": [str(a) for a in argv], "env": env, "cwd": str(cwd), "stdin": stdin})

    def run_ok(self, argv: list[str], *, env: dict[str, str], cwd: Path, label: str) -> str:
        result = self.run(argv, env=env, cwd=cwd)
        require(result["code"] == 0, f"{label}: {' '.join(str(a) for a in argv)} failed: {result['stderr'] or result['stdout']}")
        return result["stdout"]

    def detach(self, script: str, *, env: dict[str, str], cwd: Path) -> None:
        result = self._ask({"detach": True, "script": script, "env": env, "cwd": str(cwd)})
        require(result["code"] == 0, f"the hook shell exited cleanly: {result}")

    def alive(self) -> bool:
        return self.proc.poll() is None

    def end(self) -> None:
        """The session's process ends, the way a closed Claude Code session's does."""
        if self.proc.poll() is None:
            try:
                self._ask_no_reply({"exit": True})
                self.proc.wait(timeout=10)
            except Exception:
                self.proc.terminate()
                self.proc.wait()

    def _ask_no_reply(self, request: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()


def lane_env(base: dict[str, str], runtime: Runtime, session: str) -> dict[str, str]:
    """What the Claude SessionStart hook leaves in a lane's shells: the coord anchor and the harness session id, no process pins; plus the runtime name the ancestry walk recognizes (the real walk knows `claude` and `codex`)."""
    env = dict(base)
    env["AGENT_DO_COORD_SESSION"] = session
    env["CLAUDE_SESSION_ID"] = session
    env["AGENT_DO_COORD_ANCHOR_NAMES"] = runtime.comm
    return env


def coord_store(estate: fx.Estate) -> Path:
    git_dir = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=str(estate.primary), text=True, capture_output=True, check=True).stdout.strip()
    return (estate.primary / git_dir).resolve() / "agent-do" / "coord" / "agents.json"


def record(estate: fx.Estate, agent_id: str) -> dict:
    agents = json.loads(coord_store(estate).read_text(encoding="utf-8"))["agents"]
    require(agent_id in agents, f"coord carries a record for {agent_id}: {sorted(agents)}")
    return agents[agent_id]


def seed(estate: fx.Estate, agent_id: str, **fields) -> None:
    """Edit one record in the throwaway coord store (timestamps, or a legacy shape). Only the store changes; no process is touched."""
    path = coord_store(estate)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["agents"].setdefault(agent_id, {"agent_id": agent_id}).update(fields)
    path.write_text(json.dumps(data), encoding="utf-8")


def iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def peer(estate: fx.Estate, reader: fx.Session, agent_id: str) -> dict:
    peers = fx.coord_json(["peers", "--all"], cwd=estate.primary, env=reader.env)["peers"]
    row = next((p for p in peers if p["agent_id"] == agent_id), None)
    require(row is not None, f"peers --all lists {agent_id}: {[p['agent_id'] for p in peers]}")
    return row


def peers_text(estate: fx.Estate, reader: fx.Session) -> str:
    proc = fx.run([str(COORD), "peers", "--all"], cwd=estate.primary, env=reader.env)
    return proc.stdout


def reconcile(estate: fx.Estate, reader: fx.Session, *flags: str) -> tuple[int, dict]:
    args = ["reconcile", "--fix", *flags, "--json"]
    proc = fx.manna(args, cwd=estate.primary, env=reader.env)
    require(proc.stdout.strip(), f"manna {' '.join(args)} printed no JSON: {proc.stderr}")
    return proc.returncode, json.loads(proc.stdout)


def findings(payload: dict, kind: str, item: str) -> list[dict]:
    return [f for f in (payload.get("findings") or []) if f.get("kind") == kind and f.get("issue_id") == item]


def entries(payload: dict, key: str, item: str) -> list[str]:
    return [e for e in (payload.get(key) or []) if item in e]


def wait_for(path: Path, *, label: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        require(time.monotonic() < deadline, f"{label}: the orphaned coord call did not finish within {timeout:g}s")
        time.sleep(0.1)


def pulse_payload(session: str, cwd: Path) -> str:
    return json.dumps({"hook_event_name": "PostToolUse", "session_id": session, "cwd": str(cwd), "tool_name": "Bash"})


def claim_kept(label: str, estate: fx.Estate, item: str, row: dict, payload: dict) -> None:
    after = estate.row(item)
    require(
        after["status"] == "in_progress" and after["claimed_by"] == row["claimed_by"] and after["claim_token_hash"] == row["claim_token_hash"],
        f"{label}: the living lane keeps its claim: {after}",
    )
    require(not findings(payload, "dead_claim", item), f"{label}: a living lane is never a dead claim: {findings(payload, 'dead_claim', item)}")
    require(not entries(payload, "fixed", item), f"{label}: nothing is repaired on the lane's item: {payload.get('fixed')}")


def claude_case(estate: fx.Estate, other: fx.Session, base: dict[str, str], root: Path) -> None:
    label = "live lane, pulse hooks orphaned"
    runtime = Runtime(root, base, "lane")
    session = str(uuid.uuid4())
    env = lane_env(base, runtime, session)

    # A foreground tool-call shell: the ancestry reaches the runtime.
    who = json.loads(runtime.run_ok([COORD, "whoami", "--json"], env=env, cwd=estate.primary, label=label))
    agent_id = who["agent_id"]
    require(
        who["pid"] == runtime.pid and who["pid_start"] == runtime.lstart and who["anchor"] == "runtime" and who["anchor_verified"] is True,
        f"{label}: the foreground call anchors to the runtime process with its start time: {who} vs pid {runtime.pid} {runtime.lstart!r}",
    )

    # The lane claims an item, binds its proof through touch, and lands a trailer.
    item = estate.create(f"anchor: {label}")
    runtime.run_ok([MANNA, "claim", item], env=env, cwd=estate.primary, label=label)
    row = estate.row(item)
    touched = json.loads(runtime.run_ok([COORD, "touch", "--json"], env=env, cwd=estate.primary, label=label))
    require((touched.get("manna") or {}).get("proof") == row["claim_token_hash"], f"{label}: touch binds the claim proof: {touched.get('manna')}")
    estate.external_commit("src/lane.txt", "work\n", f"feat: lane\n\nManna: {item}")
    before = record(estate, agent_id)
    require(before["anchor_verified"] is True and before["pid"] == runtime.pid, f"{label}: the record carries the verified runtime anchor: {before}")

    # The pulse hook: orphaned registration. The hook shell exits at once;
    # coord runs after its parent is gone and cannot reach the runtime.
    marker = root / "lane-pulse.done"
    runtime.detach(
        PULSE_SCRIPT,
        env={**env, "PULSE_PAYLOAD": pulse_payload(session, estate.primary), "COORD": str(COORD), "MARKER": str(marker)},
        cwd=estate.primary,
    )
    wait_for(marker, label=label)
    after = record(estate, agent_id)
    require(
        after["pid"] == runtime.pid and after["pid_start"] == runtime.lstart and after["anchor"] == "runtime" and after["anchor_verified"] is True,
        f"{label}: an orphaned registration never downgrades the verified anchor: {after}",
    )
    require(after["last_seen"] >= before["last_seen"], f"{label}: the pulse still refreshed presence: {after['last_seen']} vs {before['last_seen']}")
    require((after.get("manna") or {}).get("proof") == row["claim_token_hash"], f"{label}: the Manna binding is preserved across the orphaned registration: {after.get('manna')}")

    # Another session reads the lane alive, and the SessionEnd reconcile keeps its claim.
    row_view = peer(estate, other, agent_id)
    require(
        row_view["status"] == "active" and row_view["anchor"]["liveness"] == "alive" and row_view["anchor"]["verified"] is True and row_view["anchor"]["kind"] == "runtime",
        f"{label}: peers read the lane active on a verified runtime anchor: {row_view['status']} {row_view['anchor']}",
    )
    require((row_view.get("pulse") or {}).get("status") == "working", f"{label}: the orphaned pulse still landed on the pulse row: {row_view.get('pulse')}")
    _, payload = reconcile(estate, other, "--only", HOOK_ONLY, "--write-drift")
    claim_kept(f"{label}, SessionEnd call", estate, item, row, payload)
    _, payload = reconcile(estate, other)
    claim_kept(f"{label}, full --fix", estate, item, row, payload)
    print(f"  ok: {label}: anchor stayed pid {runtime.pid} ({runtime.comm}, runtime, verified) through the orphaned pulse; claim on {item} kept by both cleanup calls")

    # Genuine death: the session's process ends; coord verifies it gone and the
    # SessionEnd reconcile releases the claim without marking the work done.
    runtime.end()
    require(not runtime.alive(), f"{label}: the runtime process has ended")
    row_view = peer(estate, other, agent_id)
    require(row_view["status"] == "dead" and row_view["anchor"]["liveness"] == "gone", f"{label}: a verified runtime that is gone reads dead: {row_view['status']} {row_view['anchor']}")
    _, payload = reconcile(estate, other, "--only", HOOK_ONLY, "--write-drift")
    released = estate.row(item)
    require(released["status"] == "open" and not released.get("claimed_by"), f"{label}: the dead lane's claim is released and the row reopens: {released}")
    require(entries(payload, "fixed", item) == [item] and not any(CLOSED in e for e in payload.get("fixed") or []), f"{label}: the release is the only repair; nothing is closed: {payload.get('fixed')}")
    print(f"  ok: {label}, runtime ended: peers read dead (gone); the claim on {item} was released, nothing marked done")


def first_contact_from_an_orphan(estate: fx.Estate, other: fx.Session, base: dict[str, str], root: Path) -> None:
    label = "first contact from an orphaned hook process"
    runtime = Runtime(root, base, "orphan")
    session = str(uuid.uuid4())
    env = lane_env(base, runtime, session)
    out = root / "orphan-whoami.json"
    marker = root / "orphan-whoami.done"
    runtime.detach(WHOAMI_SCRIPT, env={**env, "COORD": str(COORD), "OUT": str(out), "MARKER": str(marker)}, cwd=estate.primary)
    wait_for(marker, label=label)
    who = json.loads(out.read_text(encoding="utf-8"))
    agent_id = who["agent_id"]
    require(
        who["anchor"] in {"session-leader", "parent"} and who["anchor_verified"] is False,
        f"{label}: the orphan cannot reach the runtime and says so: {who}",
    )
    rec = record(estate, agent_id)
    require(rec["anchor_verified"] is False and rec["anchor"] == who["anchor"], f"{label}: the record is marked unverified: {rec}")

    # Unverifiable reads by lease: active now, idle after the lease, stale
    # after the idle window. Never dead.
    row_view = peer(estate, other, agent_id)
    require(row_view["status"] == "active" and row_view["anchor"]["liveness"] == "unverifiable", f"{label}: a fresh lease reads active, liveness unverifiable: {row_view['status']} {row_view['anchor']}")
    require("liveness:unverifiable" in peers_text(estate, other), f"{label}: the text view marks the unverifiable record")
    seed(estate, agent_id, lease_expires_at=iso(timedelta(hours=-1)), last_seen=iso(timedelta(hours=-1)))
    row_view = peer(estate, other, agent_id)
    require(row_view["status"] == "idle", f"{label}: an expired lease reads idle, not dead: {row_view['status']} {row_view['anchor']}")
    seed(estate, agent_id, last_seen=iso(timedelta(days=-3)))
    row_view = peer(estate, other, agent_id)
    require(row_view["status"] == "stale", f"{label}: three days reads stale, not dead: {row_view['status']} {row_view['anchor']}")

    # The lane's claim survives the SessionEnd reconcile while its record is unverified.
    item = estate.create(f"anchor: {label}")
    runtime.run_ok([MANNA, "claim", item], env=env, cwd=estate.primary, label=label)
    row = estate.row(item)
    estate.external_commit("src/orphan.txt", "work\n", f"feat: orphan\n\nManna: {item}")
    _, payload = reconcile(estate, other, "--only", HOOK_ONLY, "--write-drift")
    claim_kept(f"{label}, SessionEnd call", estate, item, row, payload)

    # Repair through the owning session's normal registration: one foreground call.
    touched = json.loads(runtime.run_ok([COORD, "touch", "--json"], env=env, cwd=estate.primary, label=label))
    require(touched["agent_id"] == agent_id, f"{label}: the same identity: {touched['agent_id']} vs {agent_id}")
    rec = record(estate, agent_id)
    require(
        rec["pid"] == runtime.pid and rec["pid_start"] == runtime.lstart and rec["anchor"] == "runtime" and rec["anchor_verified"] is True,
        f"{label}: the foreground registration repairs the anchor to the runtime: {rec}",
    )
    require((rec.get("manna") or {}).get("proof") == row["claim_token_hash"], f"{label}: the repair bound the lane's claim proof: {rec.get('manna')}")
    row_view = peer(estate, other, agent_id)
    require(row_view["status"] == "active" and row_view["anchor"]["liveness"] == "alive", f"{label}: repaired, the lane reads active and verified alive: {row_view['status']} {row_view['anchor']}")
    runtime.end()
    print(f"  ok: {label}: unverified anchor ({who['anchor']}) read active/idle/stale, never dead; claim on {item} kept; repaired to pid {runtime.pid} by a foreground touch")


def reuse_and_stop(estate: fx.Estate, other: fx.Session, base: dict[str, str]) -> None:
    label = "process-reuse protection and stop"
    reused = fx.Session(base, "reused-pin")
    reused.env["AGENT_DO_COORD_PID"] = str(os.getpid())
    reused.env["AGENT_DO_COORD_PID_START"] = "Thu Jan  1 00:00:00 1970"
    fx.coord_json(["touch"], cwd=estate.primary, env=reused.env)
    row_view = peer(estate, other, "session-reusedpin")
    require(row_view["status"] == "dead" and row_view["anchor"]["kind"] == "explicit" and row_view["anchor"]["liveness"] == "gone", f"{label}: a pinned pid whose start time does not match reads dead: {row_view['status']} {row_view['anchor']}")
    stopper = fx.Session(base, "stopper")
    fx.coord_json(["touch"], cwd=estate.primary, env=stopper.env)
    fx.coord_json(["stop", "--note", "done for the day"], cwd=estate.primary, env=stopper.env)
    row_view = peer(estate, other, "session-stopper")
    require(row_view["status"] == "stopped", f"{label}: an explicit stop reads stopped: {row_view['status']}")
    print(f"  ok: {label}: reused pid read dead (gone); stop read stopped")


def legacy_shapes(estate: fx.Estate, other: fx.Session, base: dict[str, str]) -> None:
    label = "legacy records without an anchor kind"
    gone: list[tuple[int, str]] = []
    for _ in range(2):
        proc = subprocess.Popen(["sleep", "60"])
        start = fx.lstart(proc.pid)
        proc.terminate()
        proc.wait()
        gone.append((proc.pid, start))
    common = {
        "project_root": str(estate.primary),
        "host": socket.gethostname(),
        "runtime": "claude",
        "identity_source": "AGENT_DO_COORD_SESSION",
        "last_seen": iso(timedelta(hours=-1)),
        "lease_expires_at": iso(timedelta(hours=-1)),
    }
    # The mn-dd9be1 shape: the pid of an exited shell and no start time.
    seed(estate, "session-legacytransi", pid=gone[0][0], pid_start="", **common)
    # A runtime that verifiably ended: pid gone, start time known.
    seed(estate, "session-legacyruntim", pid=gone[1][0], pid_start=gone[1][1], **common)
    transient = peer(estate, other, "session-legacytransi")
    require(
        transient["status"] == "idle" and transient["anchor"]["kind"] == "legacy" and transient["anchor"]["verified"] is False and transient["anchor"]["liveness"] == "unverifiable",
        f"{label}: a gone pid with no start time reads by lease, never dead: {transient['status']} {transient['anchor']}",
    )
    ended = peer(estate, other, "session-legacyruntim")
    require(
        ended["status"] == "dead" and ended["anchor"]["kind"] == "legacy" and ended["anchor"]["verified"] is True and ended["anchor"]["liveness"] == "gone",
        f"{label}: a gone pid with a known start time still reads dead: {ended['status']} {ended['anchor']}",
    )
    print(f"  ok: {label}: empty start time read idle (unverifiable); known start time read dead (gone)")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        base = {k: v for k, v in os.environ.items() if k not in fx.THREAD_ENV_KEYS}
        base.pop("TMUX_PANE", None)
        base.pop("AGENT_DO_COORD_ANCHOR_NAMES", None)
        base["AGENT_DO_HOME"] = str(root / "home")
        base["AGENT_DO_TELEMETRY_SUPPRESS"] = "1"
        base["AGENT_DO_HOOK_AI"] = "off"
        base["MANNA_OPERATOR"] = "0"
        base["AGENT_DO_COORD_ISOLATION_NUDGE"] = "0"
        estate = fx.Estate(root, "anchor", base, enable=False)
        # The session whose SessionEnd reconcile runs: pinned to the fixture
        # process with its start time, an explicit verified anchor.
        other = fx.Session(base, "other-session")
        print("the Claude case (orphaned pulse registrations never prove death):")
        claude_case(estate, other, base, root)
        first_contact_from_an_orphan(estate, other, base, root)
        print("genuine detection preserved:")
        reuse_and_stop(estate, other, base)
        legacy_shapes(estate, other, base)
    print("coord anchor tests passed")


if __name__ == "__main__":
    main()
