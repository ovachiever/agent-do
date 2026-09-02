#!/usr/bin/env python3
"""Coverage for coord v2: identity, liveness, roles, territory, guard, focus, drops, history."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"

THREAD_ENV_KEYS = [
    "CODEX_THREAD_ID",
    "CLAUDE_THREAD_ID",
    "CLAUDE_SESSION_ID",
    "CLAUDE_AGENT_ID",
    "AGENT_DO_COORD_SESSION",
    "AGENT_DO_COORD_PID",
    "AGENT_DO_COORD_PID_START",
    "AGENT_DO_COORD_RUNTIME",
    "AGENT_DO_COORD_MODEL",
    "AGENT_DO_COORD_ISOLATION_NUDGE",
    "TMUX_PANE",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def iso_ago(seconds: int) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(seconds=seconds)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def coord(args: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return run([str(AGENT_DO), "coord", *args], cwd=cwd, env=env)


def coord_json(args: list[str], *, cwd: Path, env: dict[str, str]) -> dict:
    result = coord([*args, "--json"], cwd=cwd, env=env)
    require(result.returncode == 0, f"coord {' '.join(args)} failed: {result.stderr or result.stdout}")
    return json.loads(result.stdout)


def clean_env(base: dict[str, str]) -> dict[str, str]:
    env = dict(base)
    for key in THREAD_ENV_KEYS:
        env.pop(key, None)
    return env


def lstart(pid: int) -> str:
    return subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def make_project(tmp_path: Path, name: str) -> Path:
    project = tmp_path / name
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    return project


def live_env(base: dict[str, str], pane: str = "%9") -> dict[str, str]:
    """Env for an agent anchored to the (live) test-runner process."""
    env = clean_env(base)
    env["TMUX_PANE"] = pane
    env["AGENT_DO_COORD_PID"] = str(os.getpid())
    env["AGENT_DO_COORD_PID_START"] = lstart(os.getpid())
    return env


def test_identity(tmp_path: Path, env_base: dict[str, str]) -> None:
    project = make_project(tmp_path, "identity")

    # A pane-fallback identity is a minted session UUID, stable across invocations.
    proc = subprocess.Popen(["sleep", "60"])
    try:
        pid_a = proc.pid
        start_a = lstart(pid_a)
        env_a = clean_env(env_base)
        env_a["TMUX_PANE"] = "%9"
        env_a["AGENT_DO_COORD_PID"] = str(pid_a)
        env_a["AGENT_DO_COORD_PID_START"] = start_a

        who_a = coord_json(["whoami"], cwd=project, env=env_a)
        require(who_a["agent_id"].startswith("session-"), f"expected minted session identity: {who_a}")
        require(who_a["pane"] == "%9", f"expected pane hint: {who_a}")
        require(who_a["pid"] == pid_a, f"expected anchored pid: {who_a}")

        who_a2 = coord_json(["whoami"], cwd=project, env=env_a)
        require(who_a2["agent_id"] == who_a["agent_id"], f"identity not stable: {who_a} vs {who_a2}")
    finally:
        proc.kill()
        proc.wait()

    # Pane reused by a NEW process mints a NEW identity; the old record tombstones as DEAD.
    env_b = live_env(env_base, pane="%9")
    who_b = coord_json(["whoami"], cwd=project, env=env_b)
    require(who_b["agent_id"].startswith("session-"), f"expected minted session identity: {who_b}")
    require(who_b["agent_id"] != who_a["agent_id"], f"pane reuse must mint a new identity: {who_b}")

    peers = coord_json(["peers", "--all"], cwd=project, env=env_b)["peers"]
    old = next(item for item in peers if item["agent_id"] == who_a["agent_id"])
    require(old["status"] == "dead", f"expected superseded pane identity to be dead: {old}")

    # Explicit session env wins.
    env_c = clean_env(env_base)
    env_c["AGENT_DO_COORD_SESSION"] = "feedbeef-cafe-4000-8000-123456789abc"
    who_c = coord_json(["whoami"], cwd=project, env=env_c)
    require(who_c["agent_id"] == "session-feedbeefcafe", f"expected explicit session identity: {who_c}")

    # Runtime and model are recorded.
    env_d = live_env(env_base, pane="%10")
    env_d["AGENT_DO_COORD_RUNTIME"] = "claude"
    env_d["AGENT_DO_COORD_MODEL"] = "claude-fable-5"
    who_d = coord_json(["whoami"], cwd=project, env=env_d)
    require(who_d["runtime"] == "claude", f"expected runtime field: {who_d}")
    require(who_d["model"] == "claude-fable-5", f"expected model field: {who_d}")

    # Thread-env identities keep their v1 shape (and pick up runtime detection).
    env_e = clean_env(env_base)
    env_e["CODEX_THREAD_ID"] = "gamma-789"
    who_e = coord_json(["whoami"], cwd=project, env=env_e)
    require(who_e["agent_id"] == "codex-gamma789", f"expected v1-form thread identity: {who_e}")
    require(who_e["runtime"] == "codex", f"expected detected runtime: {who_e}")


def test_presence(tmp_path: Path, env_base: dict[str, str]) -> None:
    project = make_project(tmp_path, "presence")

    # Idle retention default dropped far below 14 days.
    env_live = live_env(env_base, pane="%20")
    who = coord_json(["whoami"], cwd=project, env=env_live)
    require(who["idle_window_seconds"] == 2 * 24 * 60 * 60, f"expected 2-day idle default: {who}")

    # DEAD via exited process.
    proc = subprocess.Popen(["sleep", "60"])
    env_gone = clean_env(env_base)
    env_gone["TMUX_PANE"] = "%21"
    env_gone["AGENT_DO_COORD_PID"] = str(proc.pid)
    env_gone["AGENT_DO_COORD_PID_START"] = lstart(proc.pid)
    who_gone = coord_json(["whoami"], cwd=project, env=env_gone)
    proc.kill()
    proc.wait()

    # DEAD via pid reuse: live pid, mismatched start time.
    env_reused = clean_env(env_base)
    env_reused["TMUX_PANE"] = "%22"
    env_reused["AGENT_DO_COORD_PID"] = str(os.getpid())
    env_reused["AGENT_DO_COORD_PID_START"] = "Thu Jan  1 00:00:00 1970"
    who_reused = coord_json(["whoami"], cwd=project, env=env_reused)

    peers = coord_json(["peers", "--all"], cwd=project, env=env_live)["peers"]
    by_id = {item["agent_id"]: item for item in peers}
    require(by_id[who_gone["agent_id"]]["status"] == "dead", f"expected dead on exited pid: {by_id}")
    require(by_id[who_reused["agent_id"]]["status"] == "dead", f"expected dead on start-time mismatch: {by_id}")
    require(by_id[who["agent_id"]]["status"] == "active", f"expected live agent active: {by_id}")

    # peers always carries last_seen age, in JSON and in text.
    for item in peers:
        require(isinstance(item.get("age"), str) and item["age"].endswith("ago"), f"expected age string: {item}")
    peers_text = coord(["peers", "--all"], cwd=project, env=env_live)
    require(peers_text.returncode == 0, f"peers text failed: {peers_text.stderr}")
    require("ago)" in peers_text.stdout, f"expected age in text output: {peers_text.stdout}")
    require("dead" in peers_text.stdout, f"expected dead state in text output: {peers_text.stdout}")

    # --active-only filter for hook consumption.
    active_only = coord_json(["peers", "--active-only"], cwd=project, env=env_live)["peers"]
    require(
        all(item["status"] == "active" for item in active_only),
        f"expected only active peers: {active_only}",
    )
    require(
        any(item["agent_id"] == who["agent_id"] for item in active_only),
        f"expected live agent in active-only: {active_only}",
    )

    # Clean retirement: stop marks stopped (idempotent), excluded from active peers.
    stop_one = coord_json(["stop", "--note", "lane 14 shipped"], cwd=project, env=env_live)
    require(stop_one["agent"]["stopped"] is True, f"expected stopped record: {stop_one}")
    stop_two = coord(["stop", "--json"], cwd=project, env=env_live)
    require(stop_two.returncode == 0, f"stop must be idempotent: {stop_two.stderr}")

    env_other = clean_env(env_base)
    env_other["CODEX_THREAD_ID"] = "watcher-1"
    peers_after_stop = coord_json(["peers", "--all"], cwd=project, env=env_other)["peers"]
    stopped = next(item for item in peers_after_stop if item["agent_id"] == who["agent_id"])
    require(stopped["status"] == "stopped", f"expected stopped status: {stopped}")
    require(stopped.get("stop_note") == "lane 14 shipped", f"expected stop note: {stopped}")
    touch_other = coord_json(["touch"], cwd=project, env=env_other)
    require(
        all(peer["agent_id"] != who["agent_id"] for peer in touch_other["active_peers"]),
        f"stopped agent must not be an active peer: {touch_other['active_peers']}",
    )
    counts = touch_other["peer_counts"]
    require(counts["dead"] >= 2, f"expected dead peers counted for hook collapse: {counts}")
    require(counts["stopped"] >= 1, f"expected stopped peers counted: {counts}")

    # bye deletes the record entirely.
    env_bye = clean_env(env_base)
    env_bye["CODEX_THREAD_ID"] = "byebye-1"
    coord_json(["focus", "set", "temp work", "--path", "docs/tmp.md"], cwd=project, env=env_bye)
    coord_json(["claim", "docs/tmp.md", "--reason", "temp"], cwd=project, env=env_bye)
    bye = coord_json(["bye"], cwd=project, env=env_bye)
    require(bye["success"] is True, f"bye failed: {bye}")
    peers_after_bye = coord_json(["peers", "--all"], cwd=project, env=env_other)["peers"]
    require(
        all(item["agent_id"] != "codex-byebye1" for item in peers_after_bye),
        f"expected bye to delete record: {peers_after_bye}",
    )
    claims_after_bye = coord_json(["claims"], cwd=project, env=env_other)["claims"]
    require(
        all(item.get("owner") != "codex-byebye1" for item in claims_after_bye),
        f"expected bye to release claims: {claims_after_bye}",
    )

    # Tombstones age out on the next write.
    agents_path = project / ".git" / "agent-do" / "coord" / "agents.json"
    agents_payload = json.loads(agents_path.read_text())
    dead_id = who_gone["agent_id"]
    agents_payload["agents"][dead_id]["tombstoned_at"] = iso_ago(2 * 24 * 3600)
    agents_payload["agents"][dead_id]["dead"] = True
    agents_path.write_text(json.dumps(agents_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    coord_json(["touch"], cwd=project, env=env_other)
    agents_payload = json.loads(agents_path.read_text())
    require(
        dead_id not in agents_payload["agents"],
        f"expected aged tombstone to be pruned: {sorted(agents_payload['agents'])}",
    )


def test_roles_territory(tmp_path: Path, env_base: dict[str, str]) -> None:
    project = make_project(tmp_path, "territory")

    env_a = clean_env(env_base)
    env_a["CODEX_THREAD_ID"] = "builder-a"
    env_b = clean_env(env_base)
    env_b["CODEX_THREAD_ID"] = "builder-b"
    env_c = clean_env(env_base)
    env_c["CODEX_THREAD_ID"] = "auditor-c"

    # Roles carry default modes: builder writes, auditor reads.
    role_a = coord_json(
        ["role", "set", "builder", "--territory", "dm-ephemeris", "--territory", "shared/schema.json"],
        cwd=project,
        env=env_a,
    )
    require(role_a["role"]["role"] == "builder", f"unexpected role payload: {role_a}")
    require(role_a["role"]["mode"] == "writer", f"builder defaults to writer: {role_a}")
    require(role_a["overlaps"] == [], f"no overlap expected yet: {role_a}")

    # A second writer declaring overlapping territory is told immediately...
    role_b = coord_json(
        ["role", "set", "builder", "--territory", "shared"],
        cwd=project,
        env=env_b,
    )
    require(bool(role_b["overlaps"]), f"expected immediate overlap warning: {role_b}")
    require(
        role_b["overlaps"][0]["peer"] == "codex-buildera",
        f"expected overlap against builder-a: {role_b}",
    )

    # ...and the contention interrupt fires on BOTH agents.
    for env, other in ((env_a, "codex-builderb"), (env_b, "codex-buildera")):
        payload = coord_json(["interrupts"], cwd=project, env=env)
        contentions = [
            item
            for item in payload["interrupts"]
            if item["kind"] == "contention" and item["peer"] == other
        ]
        require(bool(contentions), f"expected territory contention against {other}: {payload}")
        require(
            any("shared" in path for item in contentions for path in item["paths"]),
            f"expected shared path in contention: {contentions}",
        )

    # Auditor on a writer's territory: courtesy notice to the writer, no contention.
    role_c = coord_json(
        ["role", "set", "auditor", "--territory", "dm-ephemeris"],
        cwd=project,
        env=env_c,
    )
    require(role_c["role"]["mode"] == "read-only", f"auditor defaults to read-only: {role_c}")
    payload_a = coord_json(["interrupts"], cwd=project, env=env_a)
    notices = [item for item in payload_a["interrupts"] if item["kind"] == "notice"]
    require(bool(notices), f"expected auditor notice for writer: {payload_a}")
    require(notices[0]["peer"] == "codex-auditorc", f"expected notice from auditor: {notices}")
    contentions_from_auditor = [
        item
        for item in payload_a["interrupts"]
        if item["kind"] == "contention" and item["peer"] == "codex-auditorc"
    ]
    require(not contentions_from_auditor, f"auditor must not contend: {payload_a}")

    # territory show renders the full ownership map with overlap annotations.
    territory = coord_json(["territory", "show"], cwd=project, env=env_a)
    owners = {item["agent_id"]: item for item in territory["territories"]}
    require("codex-buildera" in owners and "codex-builderb" in owners, f"missing owners: {territory}")
    require(owners["codex-auditorc"]["mode"] == "read-only", f"auditor mode in map: {territory}")
    require(territory["overlaps"], f"expected overlap annotation in map: {territory}")
    territory_text = coord(["territory", "show"], cwd=project, env=env_a)
    require("dm-ephemeris" in territory_text.stdout, f"expected paths in text map: {territory_text.stdout}")
    require("OVERLAP" in territory_text.stdout, f"expected overlap callout: {territory_text.stdout}")

    # peers --writers keeps auditors and the dead out of hook payloads.
    writers = coord_json(["peers", "--writers"], cwd=project, env=env_a)["peers"]
    writer_ids = {item["agent_id"] for item in writers}
    require("codex-buildera" in writer_ids and "codex-builderb" in writer_ids, f"writers missing: {writers}")
    require("codex-auditorc" not in writer_ids, f"auditor leaked into writers: {writers}")


def test_guard(tmp_path: Path, env_base: dict[str, str]) -> None:
    project = make_project(tmp_path, "guard")

    env_writer = clean_env(env_base)
    env_writer["CODEX_THREAD_ID"] = "writer-1"
    env_me = clean_env(env_base)
    env_me["CODEX_THREAD_ID"] = "committer-1"

    coord_json(["claim", "src/core.py", "--reason", "refactoring"], cwd=project, env=env_writer)
    coord_json(["role", "set", "builder", "--territory", "dm-ck"], cwd=project, env=env_writer)

    # Intersecting a LIVE agent's claim or territory warns — and never blocks.
    check = coord(["guard", "check", "src/core.py", "dm-ck/render.yaml", "docs/free.md"], cwd=project, env=env_me)
    require(check.returncode == 0, f"guard check must never block: {check.stderr}")
    require("src/core.py" in check.stdout and "WARN" in check.stdout, f"expected claim warning: {check.stdout}")
    require("dm-ck" in check.stdout, f"expected territory warning: {check.stdout}")
    check_json = coord_json(["guard", "check", "src/core.py", "docs/free.md"], cwd=project, env=env_me)
    require(check_json["clean"] is False, f"expected warnings: {check_json}")
    kinds = {item["kind"] for item in check_json["warnings"]}
    require("claim" in kinds, f"expected claim kind: {check_json}")

    # Clean paths stay quiet.
    clean_check = coord_json(["guard", "check", "docs/free.md"], cwd=project, env=env_me)
    require(clean_check["clean"] is True, f"expected clean check: {clean_check}")

    # A DEAD owner's claims no longer warn.
    proc = subprocess.Popen(["sleep", "60"])
    env_dead = clean_env(env_base)
    env_dead["TMUX_PANE"] = "%30"
    env_dead["AGENT_DO_COORD_PID"] = str(proc.pid)
    env_dead["AGENT_DO_COORD_PID_START"] = lstart(proc.pid)
    coord_json(["claim", "src/ghost.py", "--reason", "was working"], cwd=project, env=env_dead)
    proc.kill()
    proc.wait()
    ghost_check = coord_json(["guard", "check", "src/ghost.py"], cwd=project, env=env_me)
    require(ghost_check["clean"] is True, f"dead owner must not warn: {ghost_check}")

    # --staged reads the index.
    staged_file = project / "src" / "core.py"
    staged_file.parent.mkdir(parents=True, exist_ok=True)
    staged_file.write_text("print('hello')\n")
    subprocess.run(["git", "add", "src/core.py"], cwd=project, check=True)
    staged_check = coord_json(["guard", "check", "--staged"], cwd=project, env=env_me)
    require(staged_check["clean"] is False, f"expected staged warning: {staged_check}")
    require(
        any(item["path"] == "src/core.py" for item in staged_check["warnings"]),
        f"expected staged path warning: {staged_check}",
    )

    # guard install drops a warn-only pre-commit hook without clobbering an existing one.
    hook_path = project / ".git" / "hooks" / "pre-commit"
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text("#!/bin/sh\necho existing-hook\n")
    hook_path.chmod(0o755)
    install = coord_json(["guard", "install"], cwd=project, env=env_me)
    require(install["installed"] is True, f"guard install failed: {install}")
    content = hook_path.read_text()
    require("echo existing-hook" in content, f"existing hook clobbered: {content}")
    require("coord guard check --staged" in content, f"guard line missing: {content}")
    coord_json(["guard", "install"], cwd=project, env=env_me)
    content_again = hook_path.read_text()
    require(
        content_again.count("coord guard check --staged") == 1,
        f"guard install must be idempotent: {content_again}",
    )
    require(os.access(hook_path, os.X_OK), "pre-commit hook must stay executable")


def test_structured_focus(tmp_path: Path, env_base: dict[str, str]) -> None:
    project = make_project(tmp_path, "focus")

    env_a = clean_env(env_base)
    env_a["CODEX_THREAD_ID"] = "lane-14"

    # v1 form keeps working and lands in a sane default phase.
    v1_form = coord_json(
        ["focus", "set", "lane 14 packaging", "--path", "dm-ck"],
        cwd=project,
        env=env_a,
    )
    require(v1_form["focus"]["goal"] == "lane 14 packaging", f"v1 focus form broken: {v1_form}")
    require(v1_form["focus"]["phase"] == "building", f"expected default phase: {v1_form}")

    # Structured fields, goal stable while phase moves.
    full = coord_json(
        [
            "focus", "set", "lane 14 packaging",
            "--phase", "quiet",
            "--note", "QUIET while audit runs",
            "--blocking-on", "codex-auditorc",
            "--blocking-on", "dm-sdk@1.2.2",
            "--last-ship", "commit abc123",
        ],
        cwd=project,
        env=env_a,
    )
    focus = full["focus"]
    require(focus["phase"] == "quiet", f"expected quiet phase: {focus}")
    require(focus["paths"] == ["dm-ck"], f"omitted --path must preserve paths: {focus}")
    require(focus["note"] == "QUIET while audit runs", f"expected note: {focus}")
    require(focus["blocking_on"] == ["codex-auditorc", "dm-sdk@1.2.2"], f"expected blocking refs: {focus}")
    require(focus["last_ship"] == "commit abc123", f"expected last_ship: {focus}")

    # Empty string clears a field; omission preserves it.
    cleared = coord_json(
        ["focus", "set", "lane 14 packaging", "--note", ""],
        cwd=project,
        env=env_a,
    )
    require(cleared["focus"]["note"] is None, f"empty note must clear: {cleared}")
    require(cleared["focus"]["phase"] == "quiet", f"omitted phase must preserve: {cleared}")

    # peers renders phase distinctly so watchers stop looking like workers.
    env_b = clean_env(env_base)
    env_b["CODEX_THREAD_ID"] = "watcher-2"
    peers_text = coord(["peers"], cwd=project, env=env_b)
    require("phase:quiet" in peers_text.stdout, f"expected phase in peers text: {peers_text.stdout}")

    # stop retires the focus phase too.
    coord_json(["stop", "--note", "done"], cwd=project, env=env_a)
    focus_after_stop = coord_json(["focus", "show", "codex-lane14"], cwd=project, env=env_b)
    require(focus_after_stop["focus"]["phase"] == "stopped", f"stop must set phase stopped: {focus_after_stop}")

    # The phase enum is enforced.
    bad = coord(["focus", "set", "goal", "--phase", "vibing"], cwd=project, env=env_a)
    require(bad.returncode != 0, f"invalid phase must be rejected: {bad.stdout}")


def test_isolation_nudge(tmp_path: Path, env_base: dict[str, str]) -> None:
    """Concurrent builders and branch/path contention name the worktree remedy."""
    project = make_project(tmp_path, "isolation")
    head = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        cwd=project,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()

    env_a = clean_env(env_base)
    env_a["CODEX_THREAD_ID"] = "iso-writer-a"
    env_b = clean_env(env_base)
    env_b["CODEX_THREAD_ID"] = "iso-writer-b"

    coord_json(["role", "set", "builder", "--territory", "shared"], cwd=project, env=env_a)
    coord_json(["role", "set", "builder", "--territory", "shared/api"], cwd=project, env=env_b)

    # A lone building writer stays quiet. The second active building writer is
    # nudged even though its source paths are disjoint: compile state and build
    # artifacts belong to the checkout, not to either path claim.
    lone = coord_json(
        ["focus", "set", "writer a", "--path", "source-a", "--phase", "building"],
        cwd=project,
        env=env_a,
    )
    require(lone["isolation_nudge"] is None, f"lone builder must stay silent: {lone}")
    joined = coord_json(
        ["focus", "set", "writer b", "--path", "source-b", "--phase", "building"],
        cwd=project,
        env=env_b,
    )
    nudge = joined["isolation_nudge"]
    require(nudge and nudge["count"] == 1, f"second builder must be nudged: {joined}")
    require(
        nudge["peers"] == ["codex-isowritera"],
        f"nudge must identify the active building writer: {nudge}",
    )
    require("compile state" in nudge["summary"], f"nudge must name checkout-wide risk: {nudge}")
    require("source paths are disjoint" in nudge["summary"], f"nudge must cover disjoint lanes: {nudge}")
    require("agent-do git worktree add" in nudge["summary"], f"nudge must name the remedy: {nudge}")
    require("does not share this board" in nudge["summary"], f"nudge must keep the board caveat: {nudge}")

    # The warning remains visible to both building writers through the normal
    # interrupt surface, but it is one aggregate advisory rather than one row
    # per peer.
    for env, other in ((env_a, "codex-isowriterb"), (env_b, "codex-isowritera")):
        payload = coord_json(["interrupts"], cwd=project, env=env)
        builder_nudges = [
            item
            for item in payload["interrupts"]
            if item.get("reason") == "concurrent_builders"
        ]
        require(len(builder_nudges) == 1, f"expected one concurrent-builder nudge: {payload}")
        require(builder_nudges[0]["peers"] == [other], f"nudge must identify peer: {builder_nudges}")
        require(builder_nudges[0]["severity"] == "warning", f"nudge must be advisory: {builder_nudges}")

    # Both sides of the contention are told what to do, ownership-splitting first.
    for env, other in ((env_a, "codex-isowriterb"), (env_b, "codex-isowritera")):
        payload = coord_json(["interrupts"], cwd=project, env=env)
        contention = next(
            item
            for item in payload["interrupts"]
            if item["kind"] == "contention" and item["peer"] == other
        )
        summary = contention["summary"]
        require("split ownership" in summary, f"remedy must name ownership-splitting: {summary}")
        require("agent-do git worktree add" in summary, f"remedy must name the worktree command: {summary}")
        require(
            summary.index("split ownership") < summary.index("agent-do git worktree add"),
            f"ownership-splitting is the cheaper fix and must be named first: {summary}",
        )
        require(
            "does not share this board" in summary,
            # The board is per-checkout by design (agent-manna store.rs:17); mn-68d471
            # bound only memory. Drop this with the caveat if the board ever binds.
            f"worktree remedy must carry the per-checkout board caveat: {summary}",
        )
        require(
            contention["remedy"] and "split ownership" in contention["remedy"][0],
            f"structured remedy must lead with ownership-splitting: {contention}",
        )

    # The opt-out suppresses this warning at declaration and on the interrupt
    # surface. It remains a nudge: focus set still succeeds.
    env_a_build_off = dict(env_a)
    env_a_build_off["AGENT_DO_COORD_ISOLATION_NUDGE"] = "0"
    off_declaration = coord_json(
        ["focus", "set", "writer a", "--phase", "building"],
        cwd=project,
        env=env_a_build_off,
    )
    require(
        off_declaration["isolation_nudge"] is None,
        f"kill switch must silence declaration nudge: {off_declaration}",
    )
    off_building = coord_json(["interrupts"], cwd=project, env=env_a_build_off)
    require(
        not [item for item in off_building["interrupts"] if item.get("reason") == "concurrent_builders"],
        f"kill switch must silence concurrent-builder interrupt: {off_building}",
    )

    # A building read-only role never triggers the writer nudge and is not
    # counted as another building writer.
    env_reader = clean_env(env_base)
    env_reader["CODEX_THREAD_ID"] = "iso-reader"
    coord_json(["role", "set", "auditor", "--territory", "research"], cwd=project, env=env_reader)
    reader = coord_json(
        ["focus", "set", "reader", "--path", "research", "--phase", "building"],
        cwd=project,
        env=env_reader,
    )
    require(reader["isolation_nudge"] is None, f"read-only role must not receive builder nudge: {reader}")

    # Leave only the read-only lane building before the matching-branch case.
    quiet_a = coord_json(["focus", "set", "writer a", "--phase", "quiet"], cwd=project, env=env_a)
    require(quiet_a["isolation_nudge"] is None, f"non-building phase must stay silent: {quiet_a}")
    quiet_b = coord_json(["focus", "set", "writer b", "--phase", "quiet"], cwd=project, env=env_b)
    require(quiet_b["isolation_nudge"] is None, f"non-building phase must stay silent: {quiet_b}")

    # A lane on this checkout's branch is silent.
    env_c = clean_env(env_base)
    env_c["CODEX_THREAD_ID"] = "iso-lane-c"
    same = coord_json(
        ["focus", "set", "lane c", "--path", "docs", "--branch", head],
        cwd=project,
        env=env_c,
    )
    require(same["focus"]["branch"] == head, f"branch must be recorded on focus: {same}")
    require(same["branch_mismatch"] is None, f"same branch must not flag isolation: {same}")
    require(same["isolation_nudge"] is None, f"read-only building peer must not count: {same}")
    quiet = coord_json(["interrupts"], cwd=project, env=env_c)
    require(
        not [item for item in quiet["interrupts"] if item["kind"] == "contention"],
        f"matching branch must stay silent: {quiet}",
    )

    # A lane needing another branch cannot share this working tree.
    diverged = coord_json(
        ["focus", "set", "lane c", "--branch", "feat/elsewhere"],
        cwd=project,
        env=env_c,
    )
    mismatch = diverged["branch_mismatch"]
    require(mismatch and mismatch["declared"] == "feat/elsewhere", f"expected mismatch at declaration: {diverged}")
    require(mismatch["head"] == head, f"mismatch must name the checkout branch: {diverged}")
    payload_c = coord_json(["interrupts"], cwd=project, env=env_c)
    branch_items = [
        item
        for item in payload_c["interrupts"]
        if item["kind"] == "contention" and item["peer"] is None
    ]
    require(bool(branch_items), f"expected branch-mismatch interrupt: {payload_c}")
    branch_summary = branch_items[0]["summary"]
    require(
        "one working tree holds one branch" in branch_summary,
        f"branch interrupt must say why isolation is mandatory: {branch_summary}",
    )
    require(
        "agent-do git worktree add feat/elsewhere" in branch_summary,
        f"branch interrupt must name the remedy command: {branch_summary}",
    )

    # Nudge only: never a non-zero exit.
    plain = coord(["interrupts"], cwd=project, env=env_c)
    require(plain.returncode == 0, f"isolation nudge must never block: {plain.stderr}")

    # Kill switch: contention survives, the nudge does not.
    env_a_off = dict(env_a)
    env_a_off["AGENT_DO_COORD_ISOLATION_NUDGE"] = "0"
    off_payload = coord_json(["interrupts"], cwd=project, env=env_a_off)
    off_contention = next(
        item
        for item in off_payload["interrupts"]
        if item["kind"] == "contention" and item["peer"] == "codex-isowriterb"
    )
    require("worktree" not in off_contention["summary"], f"kill switch must silence remedy: {off_contention}")
    require(off_contention["remedy"] == [], f"kill switch must empty the structured remedy: {off_contention}")

    env_c_off = dict(env_c)
    env_c_off["AGENT_DO_COORD_ISOLATION_NUDGE"] = "0"
    off_c = coord_json(["interrupts"], cwd=project, env=env_c_off)
    require(
        not [item for item in off_c["interrupts"] if item["peer"] is None],
        f"kill switch must silence the branch trigger: {off_c}",
    )

    # v1 focus records (no branch key) and malformed values read fine and stay silent.
    focus_path = project / ".git" / "agent-do" / "coord" / "focus.json"
    stored = json.loads(focus_path.read_text())
    stored["focus"]["codex-v1lane"] = {
        "agent_id": "codex-v1lane",
        "goal": "v1 lane",
        "paths": ["legacy"],
        "updated_at": iso_ago(60),
    }
    stored["focus"]["codex-junklane"] = {
        "agent_id": "codex-junklane",
        "goal": "junk lane",
        "paths": [],
        "branch": {"not": "a branch"},
        "updated_at": iso_ago(60),
    }
    focus_path.write_text(json.dumps(stored, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for thread in ("v1lane", "junklane"):
        env_legacy = clean_env(env_base)
        env_legacy["CODEX_THREAD_ID"] = thread
        legacy = coord(["interrupts"], cwd=project, env=env_legacy)
        require(legacy.returncode == 0, f"{thread} record must not crash interrupts: {legacy.stderr}")
        legacy_payload = coord_json(["interrupts"], cwd=project, env=env_legacy)
        require(
            not [item for item in legacy_payload["interrupts"] if item["peer"] is None],
            f"{thread} record must not raise a branch interrupt: {legacy_payload}",
        )
    v1_focus = coord_json(["focus", "show", "codex-v1lane"], cwd=project, env=env_c)
    require(v1_focus["focus"]["goal"] == "v1 lane", f"v1 focus record must still read: {v1_focus}")


def test_drops_and_history(tmp_path: Path, env_base: dict[str, str]) -> None:
    project = make_project(tmp_path, "drops")

    env_researcher = clean_env(env_base)
    env_researcher["CODEX_THREAD_ID"] = "researcher-1"
    env_builder = clean_env(env_base)
    env_builder["CODEX_THREAD_ID"] = "builder-9"
    env_bystander = clean_env(env_base)
    env_bystander["CODEX_THREAD_ID"] = "bystander-1"

    # Drops are file pointers on the board, addressed to an agent, a role, or anyone.
    drop = coord_json(
        [
            "drop", "add", ".dev/research-drops/ephemeris.md",
            "--for", "codex-builder9",
            "--note", "ephemeris findings",
        ],
        cwd=project,
        env=env_researcher,
    )
    require(drop["drop"]["path"] == ".dev/research-drops/ephemeris.md", f"unexpected drop payload: {drop}")
    require(drop["drop"]["for"] == "codex-builder9", f"unexpected drop target: {drop}")

    coord_json(
        ["drop", "add", ".dev/research-drops/shared.md", "--for", "any", "--key", "dm-report"],
        cwd=project,
        env=env_researcher,
    )

    # drops --for-me sees direct addressing and broadcasts, not other people's mail.
    mine = coord_json(["drops", "--for-me"], cwd=project, env=env_builder)["drops"]
    require(len(mine) == 2, f"builder should see direct + broadcast: {mine}")
    bystander_view = coord_json(["drops", "--for-me"], cwd=project, env=env_bystander)["drops"]
    require(len(bystander_view) == 1, f"bystander should see only broadcast: {bystander_view}")
    all_drops = coord_json(["drops"], cwd=project, env=env_bystander)["drops"]
    require(len(all_drops) == 2, f"expected full drop list: {all_drops}")

    # A drop addressed to me raises a dependency interrupt; so does a need-key match.
    builder_interrupts = coord_json(["interrupts"], cwd=project, env=env_builder)
    drop_deps = [
        item
        for item in builder_interrupts["interrupts"]
        if item["kind"] == "dependency" and ".dev/research-drops/ephemeris.md" in item.get("paths", [])
    ]
    require(bool(drop_deps), f"expected drop dependency interrupt: {builder_interrupts}")

    coord_json(["need", "add", "dm-report", "--why", "waiting on research"], cwd=project, env=env_bystander)
    bystander_interrupts = coord_json(["interrupts"], cwd=project, env=env_bystander)
    key_deps = [
        item
        for item in bystander_interrupts["interrupts"]
        if item["kind"] == "dependency" and "dm-report" in item.get("keys", [])
    ]
    require(bool(key_deps), f"expected need-key drop match: {bystander_interrupts}")

    # Publishes gain the same file-pointer field.
    publish = coord_json(
        [
            "publish", "add", "dm-report",
            "--status", "ready",
            "--summary", "research consolidated",
            "--file", ".dev/research-drops/shared.md",
        ],
        cwd=project,
        env=env_researcher,
    )
    require(
        publish["publish"]["file"] == ".dev/research-drops/shared.md",
        f"expected publish file pointer: {publish}",
    )

    # History reads the events journal without grepping it.
    coord_json(["focus", "set", "drop consumption", "--path", "dm-ck"], cwd=project, env=env_builder)
    history = coord_json(["history", "--limit", "50"], cwd=project, env=env_bystander)
    require(bool(history["events"]), f"expected history events: {history}")
    kinds = {item["kind"] for item in history["events"]}
    require("drop_add" in kinds and "focus_set" in kinds, f"expected drop/focus history: {kinds}")
    first_two = [item["seq"] for item in history["events"][:2]]
    require(first_two == sorted(first_two, reverse=True), f"history must be newest-first: {first_two}")

    builder_history = coord_json(["history", "codex-builder9"], cwd=project, env=env_bystander)
    require(
        all(item["agent_id"] == "codex-builder9" for item in builder_history["events"]),
        f"peer filter leaked: {builder_history}",
    )
    history_text = coord(["history", "--limit", "5"], cwd=project, env=env_bystander)
    require("focus_set" in history_text.stdout, f"expected readable history: {history_text.stdout}")


def test_v1_migration(tmp_path: Path, env_base: dict[str, str]) -> None:
    """v1 records must be readable by v2 and upgraded lazily on write."""
    project = make_project(tmp_path, "migration")
    coord_root = project / ".git" / "agent-do" / "coord"
    coord_root.mkdir(parents=True)

    v1_agent = {
        "agent_id": "codex-old1",
        "alias": "veteran",
        "identity_raw": "old-1",
        "identity_source": "CODEX_THREAD_ID",
        "last_seen": iso_ago(60),
        "lease_expires_at": (
            datetime.now(timezone.utc) + timedelta(seconds=600)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "project_root": str(project),
    }
    (coord_root / "agents.json").write_text(json.dumps({"agents": {"codex-old1": v1_agent}}, indent=2) + "\n")
    v1_focus = {
        "agent_id": "codex-old1",
        "alias": "veteran",
        "goal": "legacy lane",
        "paths": ["dm-ck/render.yaml"],
        "updated_at": iso_ago(60),
    }
    (coord_root / "focus.json").write_text(json.dumps({"focus": {"codex-old1": v1_focus}}, indent=2) + "\n")
    v1_claim = {
        "path": "dm-ck/render.yaml",
        "owner": "codex-old1",
        "owner_alias": "veteran",
        "reason": "legacy work",
        "strength": "soft",
        "created_at": iso_ago(60),
        "updated_at": iso_ago(60),
    }
    (coord_root / "claims.json").write_text(json.dumps({"claims": [v1_claim]}, indent=2) + "\n")

    # A v2 agent reads the v1 board.
    env_new = clean_env(env_base)
    env_new["CODEX_THREAD_ID"] = "fresh-1"
    peers = coord_json(["peers", "--all"], cwd=project, env=env_new)["peers"]
    veteran = next(item for item in peers if item["agent_id"] == "codex-old1")
    require(veteran["status"] == "active", f"v1 record must classify by lease: {veteran}")
    require(veteran["age"].endswith("ago"), f"v1 record still gets an age: {veteran}")
    focus_show = coord_json(["focus", "show", "veteran"], cwd=project, env=env_new)
    require(focus_show["focus"]["goal"] == "legacy lane", f"v1 focus unreadable: {focus_show}")
    claims = coord_json(["claims"], cwd=project, env=env_new)["claims"]
    require(claims and claims[0]["owner"] == "codex-old1", f"v1 claims unreadable: {claims}")

    # v1 records still participate in contention.
    coord_json(["focus", "set", "new lane", "--path", "dm-ck/render.yaml"], cwd=project, env=env_new)
    interrupts = coord_json(["interrupts"], cwd=project, env=env_new)
    contentions = [item for item in interrupts["interrupts"] if item["kind"] == "contention"]
    require(bool(contentions), f"v1 peer must still contend: {interrupts}")

    # Lazy upgrade on write: the v1 agent's next contact fills v2 fields in place.
    env_old = clean_env(env_base)
    env_old["CODEX_THREAD_ID"] = "old-1"
    who_old = coord_json(["whoami"], cwd=project, env=env_old)
    require(who_old["agent_id"] == "codex-old1", f"identity continuity broken: {who_old}")
    agents_after = json.loads((coord_root / "agents.json").read_text())["agents"]
    upgraded = agents_after["codex-old1"]
    require(upgraded.get("pid") is not None, f"expected lazy pid upgrade: {upgraded}")
    require(upgraded.get("runtime") == "codex", f"expected lazy runtime upgrade: {upgraded}")
    require(upgraded.get("alias") == "veteran", f"upgrade must not lose v1 fields: {upgraded}")

    focus_upgraded = coord_json(
        ["focus", "set", "legacy lane", "--phase", "watching"],
        cwd=project,
        env=env_old,
    )["focus"]
    require(focus_upgraded["phase"] == "watching", f"expected phase on upgraded focus: {focus_upgraded}")
    require(
        focus_upgraded["paths"] == ["dm-ck/render.yaml"],
        f"v1 focus paths must survive upgrade: {focus_upgraded}",
    )


def test_agent_process_anchor(tmp_path: Path, env_base: dict[str, str]) -> None:
    """Coord anchors to the long-lived agent process, not the per-call shell.

    Claude Code spawns a fresh shell (its own session leader) for every Bash
    call, so anchoring to os.getsid(0) would mint a new identity per call and
    record a pid that dies seconds later. The anchor walk must find the
    nearest ancestor named like an agent runtime (claude/codex) instead.
    """
    project = make_project(tmp_path, "anchor")

    # A fake binary named "claude" cannot be spawned here (macOS AMFI kills
    # relocated platform binaries; sandboxes stall symlink execs in dyld), so
    # exercise the same ancestry walk through its extension point: a long-lived
    # python3 intermediary added to AGENT_DO_COORD_ANCHOR_NAMES. Under the
    # broken sid-anchor both whoamis still agree (they share the test runner's
    # session) — the discriminating assertion is the anchored pid.
    out_dir = tmp_path / "anchor-out"
    out_dir.mkdir()
    intermediary = tmp_path / "intermediary.py"
    intermediary.write_text(
        "import os, subprocess, sys\n"
        "out_dir, agent_do, project = sys.argv[1:4]\n"
        "open(os.path.join(out_dir, 'anchor.pid'), 'w').write(str(os.getpid()))\n"
        # The interpreter's process name varies by build (pyenv: python3;
        # framework/runner builds: Python), so read this process's real comm
        # and hand THAT to the anchor walk instead of hardcoding a name.
        "comm = subprocess.run(['ps', '-o', 'comm=', '-p', str(os.getpid())],\n"
        "                      capture_output=True, text=True).stdout.strip()\n"
        "env = dict(os.environ)\n"
        "env['AGENT_DO_COORD_ANCHOR_NAMES'] = os.path.basename(comm)\n"
        "for n in (1, 2):\n"
        "    result = subprocess.run(\n"
        "        [agent_do, 'coord', 'whoami', '--json'],\n"
        "        capture_output=True, text=True, cwd=project, check=True, env=env,\n"
        "    )\n"
        "    open(os.path.join(out_dir, f'who{n}.json'), 'w').write(result.stdout)\n"
    )

    env = clean_env(env_base)
    env["TMUX_PANE"] = "%40"
    result = subprocess.run(
        ["python3", str(intermediary), str(out_dir), str(AGENT_DO), str(project)],
        env=env,
        capture_output=True,
        text=True,
    )
    require(result.returncode == 0, f"intermediary run failed: {result.stderr}")

    anchor_pid = int((out_dir / "anchor.pid").read_text().strip())
    who1 = json.loads((out_dir / "who1.json").read_text())
    who2 = json.loads((out_dir / "who2.json").read_text())
    require(who1["agent_id"] == who2["agent_id"], f"identity churned across calls: {who1} vs {who2}")
    require(who1["agent_id"].startswith("session-"), f"expected minted identity: {who1}")
    require(
        who1["pid"] == anchor_pid,
        f"anchor must be the named agent ancestor {anchor_pid}, got {who1['pid']}",
    )


def pulse_event(payload: dict, *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(AGENT_DO), "coord", "pulse", "record", "--from-hook"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
        input=json.dumps(payload),
    )


def test_pulse(tmp_path: Path, env_base: dict[str, str]) -> None:
    project = tmp_path / "pulse_project"
    project.mkdir()

    def session_env(name: str) -> dict[str, str]:
        env = {k: v for k, v in env_base.items() if k not in THREAD_ENV_KEYS}
        env["AGENT_DO_COORD_SESSION"] = name
        return env

    env_a = session_env("pulse-aaa")
    env_b = session_env("pulse-bbb")
    env_c = session_env("pulse-ccc")
    env_d = session_env("pulse-ddd")

    # Reducer basics: prompt, activity, todo, attention.
    result = pulse_event(
        {"hook_event_name": "UserPromptSubmit", "session_id": "pulse-aaa", "cwd": str(project), "prompt": "fix the parser"},
        cwd=project,
        env=env_a,
    )
    require(result.returncode == 0 and result.stdout == "", f"from-hook must be silent success: {result.stdout!r} {result.stderr!r}")
    pulse_event(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "pulse-aaa",
            "cwd": str(project),
            "tool_name": "TodoWrite",
            "tool_input": {
                "todos": [
                    {"content": "write failing test", "status": "completed"},
                    {"content": "fix unicode", "status": "in_progress"},
                    {"content": "run suite", "status": "pending"},
                ]
            },
        },
        cwd=project,
        env=env_a,
    )
    pulse_event(
        {"hook_event_name": "Notification", "session_id": "pulse-aaa", "cwd": str(project), "message": "needs permission for Bash"},
        cwd=project,
        env=env_a,
    )
    shown = coord(["pulse", "show", "--json"], cwd=project, env=env_a)
    require(shown.returncode == 0, f"pulse show failed: {shown.stderr}")
    state = json.loads(shown.stdout)["pulse"]
    require(state["status"] == "needs-user", f"expected needs-user, got {state['status']}")
    require(state["latest_prompt"] == "fix the parser", f"latest_prompt wrong: {state}")
    require(state["turns"] == 1 and state["event_count"] == 3, f"counters wrong: {state}")
    require(state["todo"] == {"done": 1, "total": 3, "current": "fix unicode"}, f"todo wrong: {state['todo']}")
    require(state["attention"] == {"message": "needs permission for Bash"}, f"attention wrong: {state}")

    # B working, C present with no pulse, D finished.
    pulse_event(
        {"hook_event_name": "UserPromptSubmit", "session_id": "pulse-bbb", "cwd": str(project), "prompt": "audit release notes"},
        cwd=project,
        env=env_b,
    )
    coord(["touch"], cwd=project, env=env_c)
    pulse_event(
        {"hook_event_name": "UserPromptSubmit", "session_id": "pulse-ddd", "cwd": str(project), "prompt": "ship the docs"},
        cwd=project,
        env=env_d,
    )
    pulse_event({"hook_event_name": "Stop", "session_id": "pulse-ddd", "cwd": str(project)}, cwd=project, env=env_d)

    # Unknown events are ignored, malformed stdin is silent success.
    pulse_event({"hook_event_name": "SomeFutureEvent", "session_id": "pulse-ddd", "cwd": str(project)}, cwd=project, env=env_d)
    garbage = subprocess.run(
        [str(AGENT_DO), "coord", "pulse", "record", "--from-hook"],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
        env=env_d,
        input="not json",
    )
    require(garbage.returncode == 0 and garbage.stdout == "", "malformed stdin must be silent success")
    shown_d = json.loads(coord(["pulse", "show", "--json"], cwd=project, env=env_d).stdout)["pulse"]
    require(shown_d["status"] == "finished" and shown_d["event_count"] == 2, f"unknown event must not count: {shown_d}")

    # Attention-first ordering among live peers: needs-user, working, no-pulse, finished.
    peers = json.loads(coord(["peers", "--json"], cwd=project, env=env_c).stdout)["peers"]
    order = [peer["agent_id"] for peer in peers]
    expected = ["session-pulseaaa", "session-pulsebbb", "session-pulseccc", "session-pulseddd"]
    require(order == expected, f"attention-first order wrong: {order}")
    by_id = {peer["agent_id"]: peer for peer in peers}
    require(by_id["session-pulseccc"]["pulse"] is None, "no-pulse peer must carry pulse: null (trust latch)")

    # The payload's session_id outranks an inherited env pin.
    pulse_event(
        {"hook_event_name": "UserPromptSubmit", "session_id": "pulse-bbb", "cwd": str(project), "prompt": "crossed env delivery"},
        cwd=project,
        env=env_a,
    )
    crossed = json.loads(coord(["pulse", "show", "--json"], cwd=project, env=env_b).stdout)["pulse"]
    require(crossed["latest_prompt"] == "crossed env delivery", f"payload session_id must win: {crossed}")
    intact = json.loads(coord(["pulse", "show", "--json"], cwd=project, env=env_a).stdout)["pulse"]
    require(intact["latest_prompt"] == "fix the parser", f"env session's row must stay untouched: {intact}")

    # Long prompts are clipped with an honest marker.
    pulse_event(
        {"hook_event_name": "UserPromptSubmit", "session_id": "pulse-ddd", "cwd": str(project), "prompt": "x" * 500},
        cwd=project,
        env=env_d,
    )
    clipped = json.loads(coord(["pulse", "show", "--json"], cwd=project, env=env_d).stdout)["pulse"]
    require(len(clipped["latest_prompt"]) <= 160, f"prompt not clipped: {len(clipped['latest_prompt'])}")
    require(clipped["latest_prompt"].endswith("…"), "clipped prompt must carry the truncation marker")

    # bye clears the pulse row.
    coord(["bye"], cwd=project, env=env_a)
    gone = coord(["pulse", "show", "--json"], cwd=project, env=env_a)
    require(gone.returncode == 2, f"pulse for a departed agent must be gone: {gone.stdout}")


def test_explicit_pulse(tmp_path: Path, env_base: dict[str, str]) -> None:
    project = make_project(tmp_path, "explicit_pulse")
    harness_session = "019d8abc-dead-7eef-9000-aabbccddeeff"
    target_env = clean_env(env_base)
    target_env["AGENT_DO_COORD_SESSION"] = harness_session
    supervisor_env = clean_env(env_base)

    pulse_event(
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": harness_session,
            "cwd": str(project),
            "prompt": "keep the prompt and todo fields",
        },
        cwd=project,
        env=target_env,
    )
    target_id = "session-019d8abcdead"
    coord_root = project / ".git" / "agent-do" / "coord"
    agents_before = (coord_root / "agents.json").read_bytes()

    verdict_args = [
        "pulse",
        "record",
        "--session",
        harness_session,
        "--status",
        "needs-user",
        "--activity",
        "pane is waiting for input",
        "--updated-at",
        "2026-08-31T22:00:00-05:00",
    ]
    first = coord_json(verdict_args, cwd=project, env=supervisor_env)
    require(first["changed"] is True, f"first explicit verdict must change the row: {first}")
    require(first["pulse"]["agent_id"] == target_id, f"full harness id mapped to wrong row: {first}")
    require(first["pulse"]["status"] == "needs-user", f"explicit status missing: {first}")
    require(first["pulse"]["activity"] == "pane is waiting for input", f"activity missing: {first}")
    require(first["pulse"]["updated_at"] == "2026-09-01T03:00:00Z", f"timestamp not normalized: {first}")
    require(first["pulse"]["latest_prompt"] == "keep the prompt and todo fields", f"hook field lost: {first}")
    require(first["pulse"]["event_count"] == 1, f"external verdict must not count as a hook event: {first}")
    require(
        (coord_root / "agents.json").read_bytes() == agents_before,
        "external verdict must not renew or impersonate target presence",
    )
    require(
        not (coord_root / "sessions.json").exists(),
        "external verdict must not mint caller session bookkeeping",
    )
    shown_by_harness_id = coord_json(["pulse", "show", harness_session], cwd=project, env=supervisor_env)["pulse"]
    require(shown_by_harness_id == first["pulse"], f"full harness id must read the shared row: {shown_by_harness_id}")

    second = coord_json(verdict_args, cwd=project, env=supervisor_env)
    require(
        second["changed"] is False and second["pulse"] == first["pulse"],
        f"duplicate verdict must be idempotent: {second}",
    )

    preserve_activity = coord_json(
        [
            "pulse",
            "record",
            "--session",
            target_id,
            "--status",
            "idle",
            "--updated-at",
            "2026-09-01T03:00:01Z",
        ],
        cwd=project,
        env=supervisor_env,
    )["pulse"]
    require(
        preserve_activity["activity"] == "pane is waiting for input",
        f"omitted activity must preserve its field: {preserve_activity}",
    )
    cleared = coord_json(
        [
            "pulse",
            "record",
            "--session",
            harness_session,
            "--status",
            "finished",
            "--clear-activity",
            "--updated-at",
            "2026-09-01T03:00:02Z",
        ],
        cwd=project,
        env=supervisor_env,
    )["pulse"]
    require("activity" not in cleared, f"explicit clear must remove activity: {cleared}")

    before_invalid = (coord_root / "pulse.json").read_bytes()
    invalid = coord(
        [
            "pulse",
            "record",
            "--session",
            harness_session,
            "--status",
            "failed",
            "--updated-at",
            "not-a-time",
        ],
        cwd=project,
        env=supervisor_env,
    )
    require(invalid.returncode == 2, f"invalid explicit timestamp must fail closed: {invalid.stdout} {invalid.stderr}")
    require((coord_root / "pulse.json").read_bytes() == before_invalid, "invalid explicit verdict mutated pulse state")

    missing = coord(["pulse", "record", "--status", "working"], cwd=project, env=supervisor_env)
    require(missing.returncode == 2, f"partial explicit verdict must fail: {missing.stdout} {missing.stderr}")

    # The six-state vocabulary is shared with Holy. An explicit idle pulse
    # ranks below a live peer with no pulse but above finished.
    no_pulse_env = clean_env(env_base)
    no_pulse_env["AGENT_DO_COORD_SESSION"] = "no-pulse"
    finished_env = clean_env(env_base)
    finished_env["AGENT_DO_COORD_SESSION"] = "finished-peer"
    coord_json(["touch"], cwd=project, env=no_pulse_env)
    coord_json(["touch"], cwd=project, env=finished_env)
    coord_json(
        [
            "pulse",
            "record",
            "--session",
            "finished-peer",
            "--status",
            "finished",
            "--updated-at",
            "2026-09-01T03:00:03Z",
        ],
        cwd=project,
        env=supervisor_env,
    )
    coord_json(
        [
            "pulse",
            "record",
            "--session",
            harness_session,
            "--status",
            "idle",
            "--updated-at",
            "2026-09-01T03:00:04Z",
        ],
        cwd=project,
        env=supervisor_env,
    )
    peers = coord_json(["peers"], cwd=project, env=supervisor_env)["peers"]
    order = [peer["agent_id"] for peer in peers]
    require(
        order.index("session-nopulse") < order.index(target_id) < order.index("session-finishedpeer"),
        f"idle rank is wrong: {order}",
    )

    # Hook and supervisor writers share one lock. Concurrent hook events must
    # all increment event_count while explicit field merges leave the JSON valid.
    processes: list[subprocess.Popen[str]] = []
    for index in range(4):
        hook = subprocess.Popen(
            [str(AGENT_DO), "coord", "pulse", "record", "--from-hook"],
            cwd=project,
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=target_env,
        )
        require(hook.stdin is not None, "hook writer did not expose stdin")
        hook.stdin.write(
            json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "session_id": harness_session,
                    "cwd": str(project),
                    "tool_name": f"HookTool{index}",
                }
            )
        )
        hook.stdin.close()
        hook.stdin = None
        processes.append(hook)
        processes.append(
            subprocess.Popen(
                [
                    str(AGENT_DO),
                    "coord",
                    "pulse",
                    "record",
                    "--session",
                    harness_session,
                    "--status",
                    "failed",
                    "--activity",
                    f"Supervisor verdict {index}",
                    "--updated-at",
                    f"2026-09-01T03:00:1{index}Z",
                ],
                cwd=project,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=supervisor_env,
            )
        )
    for process in processes:
        stdout, stderr = process.communicate()
        require(process.returncode == 0, f"concurrent pulse writer failed: {stdout} {stderr}")
    concurrent = coord_json(["pulse", "show", target_id], cwd=project, env=supervisor_env)["pulse"]
    require(concurrent["event_count"] == 5, f"concurrent hook increments were lost: {concurrent}")
    require(
        concurrent["latest_prompt"] == "keep the prompt and todo fields",
        f"concurrent merge lost hook-owned fields: {concurrent}",
    )
    require(
        concurrent["status"] in {"working", "failed"},
        f"concurrent status is not from a complete writer: {concurrent}",
    )


def test_liveness_dead_records_prune(tmp_path: Path, env_base: dict[str, str]) -> None:
    """Records whose process is verifiably gone age out like tombstones."""
    project = make_project(tmp_path, "deadprune")

    proc = subprocess.Popen(["sleep", "60"])
    env_dead = clean_env(env_base)
    env_dead["TMUX_PANE"] = "%50"
    env_dead["AGENT_DO_COORD_PID"] = str(proc.pid)
    env_dead["AGENT_DO_COORD_PID_START"] = lstart(proc.pid)
    who_dead = coord_json(["whoami"], cwd=project, env=env_dead)
    proc.kill()
    proc.wait()

    agents_path = project / ".git" / "agent-do" / "coord" / "agents.json"
    payload = json.loads(agents_path.read_text())
    payload["agents"][who_dead["agent_id"]]["last_seen"] = iso_ago(25 * 3600)
    agents_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    env_other = clean_env(env_base)
    env_other["CODEX_THREAD_ID"] = "pruner-1"
    coord_json(["touch"], cwd=project, env=env_other)
    payload = json.loads(agents_path.read_text())
    require(
        who_dead["agent_id"] not in payload["agents"],
        f"verifiably-dead record must prune after tombstone TTL: {sorted(payload['agents'])}",
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        env_base = dict(os.environ)
        env_base["AGENT_DO_HOME"] = str(fake_home)

        test_identity(tmp_path, env_base)
        test_presence(tmp_path, env_base)
        test_roles_territory(tmp_path, env_base)
        test_guard(tmp_path, env_base)
        test_structured_focus(tmp_path, env_base)
        test_isolation_nudge(tmp_path, env_base)
        test_drops_and_history(tmp_path, env_base)
        test_pulse(tmp_path, env_base)
        test_explicit_pulse(tmp_path, env_base)
        test_v1_migration(tmp_path, env_base)
        test_agent_process_anchor(tmp_path, env_base)
        test_liveness_dead_records_prune(tmp_path, env_base)

    print("coord v2 tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
