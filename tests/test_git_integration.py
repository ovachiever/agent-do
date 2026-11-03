#!/usr/bin/env python3
"""Deterministic, isolated fixtures for Managed Integration (`agent-do git integration`, mn-54fe40).

Every scenario builds its own throwaway estate: a primary checkout with a real
Manna board, pinned worker and coordinator identities on pipes (never the
operator's terminal), coord sessions anchored to processes the fixture can
kill, the real agent-git, manna and coord binaries, and the real prompt-free
integrator. Nothing here touches the developer's repositories or $HOME.

Scenarios, in the work order's words: opt-in/off/invalid config, canonical
board across worktrees, two competing submissions, stale base, conflicts,
failed checks, dirty target checkout, worker disappearance and replacement,
authority and config change, interruption before and after the ref update,
replay without duplicate integration, branches that stay recoverable.
"""

from __future__ import annotations

import fcntl
import json
import os
import pty
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_GIT = ROOT / "tools" / "agent-git"
MANNA = ROOT / "tools" / "agent-manna" / "agent-manna"
COORD = ROOT / "tools" / "agent-coord"

THREAD_ENV_KEYS = [
    "MANNA_SESSION_ID",
    "MANNA_SESSION_TOKEN",
    "MANNA_OPERATOR",
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
    "AGENT_GIT_INTEGRATION_FAULT",
    "TMUX_PANE",
]

FAULT_EXIT = 70
CONTENDED = 2


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(args: list[str], *, cwd: Path, env: dict[str, str], stdin: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(a) for a in args],
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=False,
        stdin=subprocess.DEVNULL if stdin is None else stdin,
    )


def git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=str(cwd), text=True, capture_output=True, check=False)
    if check:
        require(proc.returncode == 0, f"git {' '.join(args)} failed in {cwd}: {proc.stderr or proc.stdout}")
    return proc.stdout.strip()


def integ(args: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return run([AGENT_GIT, "integration", *args], cwd=cwd, env=env)


def integ_json(args: list[str], *, cwd: Path, env: dict[str, str], expect: int = 0) -> dict:
    proc = integ([*args, "--json"], cwd=cwd, env=env)
    require(proc.returncode == expect, f"integration {' '.join(args)} exited {proc.returncode}, expected {expect}: {proc.stdout}\n{proc.stderr}")
    require(proc.stdout.strip(), f"integration {' '.join(args)} printed no JSON: {proc.stderr}")
    return json.loads(proc.stdout)


def manna(args: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return run([MANNA, *args], cwd=cwd, env=env)


def manna_json(args: list[str], *, cwd: Path, env: dict[str, str]) -> dict:
    proc = manna([*args, "--json"], cwd=cwd, env=env)
    require(proc.returncode == 0, f"manna {' '.join(args)} failed: {proc.stderr or proc.stdout}")
    return json.loads(proc.stdout)


def coord_json(args: list[str], *, cwd: Path, env: dict[str, str]) -> dict:
    proc = run([COORD, *args, "--json"], cwd=cwd, env=env)
    require(proc.returncode == 0, f"coord {' '.join(args)} failed: {proc.stderr or proc.stdout}")
    return json.loads(proc.stdout)


def operator_manna(args: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run manna as the operator: stdin is a pseudo-terminal and no identity is pinned."""
    clean = {k: v for k, v in env.items() if k not in THREAD_ENV_KEYS}
    clean.setdefault("USER", os.environ.get("USER", "fixture"))
    master, slave = pty.openpty()
    try:
        proc = subprocess.run([str(MANNA), *args], cwd=str(cwd), env=clean, text=True, capture_output=True, check=False, stdin=slave)
    finally:
        os.close(slave)
        os.close(master)
    return proc


def extract_id(text: str) -> str:
    match = re.search(r"^  id: (mn-[0-9a-f]{6})$", text, re.MULTILINE)
    require(match is not None, f"no item id in: {text}")
    return match.group(1)


def lstart(pid: int) -> str:
    return subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], text=True, capture_output=True, check=True).stdout.strip()


class Session:
    """A pinned identity on a pipe, anchored (for coord liveness) to a process the fixture owns."""

    def __init__(self, base: dict[str, str], name: str, *, anchor: subprocess.Popen | None = None) -> None:
        self.name = name
        self.anchor = anchor
        env = dict(base)
        env["MANNA_SESSION_ID"] = name
        env["MANNA_SESSION_TOKEN"] = f"{name}-token-" + "x" * 40
        env["AGENT_DO_COORD_SESSION"] = name
        pid = anchor.pid if anchor else os.getpid()
        env["AGENT_DO_COORD_PID"] = str(pid)
        env["AGENT_DO_COORD_PID_START"] = lstart(pid)
        self.env = env

    def proof(self, cwd: Path) -> str:
        return manna_json(["identity"], cwd=cwd, env=self.env)["proof"]

    def kill(self) -> None:
        require(self.anchor is not None, "only anchored sessions can die")
        self.anchor.send_signal(signal.SIGKILL)
        self.anchor.wait()


class Estate:
    """A primary checkout with a Manna board, policy enabled unless told otherwise."""

    def __init__(self, root: Path, name: str, base: dict[str, str], *, enable: bool = True) -> None:
        self.root = root
        self.base = base
        self.primary = root / name
        self.primary.mkdir()
        git(self.primary, "init", "-q", "-b", "main")
        git(self.primary, "config", "user.email", "fixture@example.invalid")
        git(self.primary, "config", "user.name", "fixture")
        (self.primary / "README.md").write_text("# fixture\n\nline one\n", encoding="utf-8")
        (self.primary / "src").mkdir()
        (self.primary / "src" / "app.txt").write_text("app v1\n", encoding="utf-8")
        (self.primary / "ci.sh").write_text(
            "#!/bin/sh\n"
            "# the repository's own validation: fails when any tracked file says BROKEN\n"
            "if git grep -q BROKEN -- . ':!ci.sh'; then echo 'BROKEN found'; exit 1; fi\n"
            "echo 'ci ok'\n",
            encoding="utf-8",
        )
        os.chmod(self.primary / "ci.sh", 0o755)
        git(self.primary, "add", ".")
        git(self.primary, "commit", "-qm", "chore: initial")
        self.lead = Session(base, "lead-session")
        self.integrator = Session(base, "integrator-session")
        init = manna(["init"], cwd=self.primary, env=self.lead.env)
        require(init.returncode == 0, f"manna init failed: {init.stderr or init.stdout}")
        git(self.primary, "add", ".manna", ".handoff")
        git(self.primary, "commit", "-qm", "board: init")
        self.candidate = root / f"{name}-integration"
        if enable:
            self.enable()

    def enable(self, target: str = "main", checks: list[str] | None = None) -> dict:
        args = ["enable", "--target", target, "--authorized-by", "fixture operator, 2026-11-03"]
        for check in checks or ["sh ./ci.sh"]:
            args += ["--check", check]
        return integ_json(args, cwd=self.primary, env=self.integrator.env)

    def create(self, title: str) -> str:
        created = manna(["create", title, "fixture work"], cwd=self.primary, env=self.lead.env)
        require(created.returncode == 0, f"manna create failed: {created.stderr or created.stdout}")
        item = extract_id(created.stdout)
        git(self.primary, "add", ".manna", ".handoff")
        git(self.primary, "commit", "-qm", f"board: file {item}")
        return item

    def claim(self, item: str, session: Session) -> dict:
        claimed = manna(["claim", item], cwd=self.primary, env=session.env)
        require(claimed.returncode == 0, f"claim failed: {claimed.stderr or claimed.stdout}")
        return self.row(item)

    def row(self, item: str) -> dict:
        return manna_json(["show", item], cwd=self.primary, env=self.lead.env)["issue"]

    def tip(self, branch: str = "main") -> str:
        return git(self.primary, "rev-parse", f"refs/heads/{branch}")

    def workspace(self, item: str, session: Session, cwd: Path | None = None) -> dict:
        return integ_json(["workspace", "add", item], cwd=cwd or self.primary, env=session.env)

    def submit(self, item: str, session: Session, cwd: Path, *evidence: str) -> dict:
        args = ["submit", item]
        for line in evidence:
            args += ["--evidence", line]
        return integ_json(args, cwd=cwd, env=session.env)

    def run_integrator(self, *extra: str, env: dict[str, str] | None = None) -> dict:
        return integ_json(["run", *extra], cwd=self.primary, env=env or self.integrator.env)

    def status(self, item: str | None = None) -> dict:
        payload = integ_json(["status", *([item] if item else [])], cwd=self.primary, env=self.lead.env)
        return payload

    def item_state(self, item: str) -> dict:
        rows = [row for row in self.status(item)["items"] if row["item"] == item]
        require(len(rows) == 1, f"status rows for {item}: {rows}")
        return rows[0]

    def external_commit(self, path: str, content: str, message: str = "chore: main moves") -> str:
        target = self.primary / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        git(self.primary, "add", path)
        git(self.primary, "commit", "-qm", message)
        return self.tip()

    def state_dir(self) -> Path:
        return self.primary / ".git" / "agent-do" / "integration"


def commit(ws: Path, item: str, path: str, content: str, message: str) -> str:
    target = ws / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    git(ws, "add", path)
    git(ws, "commit", "-qm", f"{message}\n\nManna: {item}")
    return git(ws, "rev-parse", "HEAD")


def count_commits(repo: Path, branch: str = "main") -> int:
    """Landings on the first-parent line: a fast-forward of one commit and a merge commit each count once."""
    return int(git(repo, "rev-list", "--count", "--first-parent", f"refs/heads/{branch}"))


def drops_for(estate: Estate, session: Session, item: str) -> list[dict]:
    payload = coord_json(["drops", "--for-me", "--all"], cwd=estate.primary, env=session.env)
    return [d for d in payload["drops"] if isinstance(d.get("for_item"), dict) and d["for_item"].get("id") == item]


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def test_config_states(root: Path, base: dict[str, str]) -> None:
    estate = Estate(root, "config", base, enable=False)
    item = estate.create("config gate")
    worker = Session(base, "worker-config")
    estate.claim(item, worker)
    primary = estate.primary

    off = integ_json(["config"], cwd=primary, env=estate.lead.env)
    require(off["config"]["state"] == "off", f"fresh repo must be off: {off['config']}")
    refused = integ(["workspace", "add", item], cwd=primary, env=worker.env)
    require(refused.returncode == 1 and "not enabled" in refused.stderr, f"off must refuse dispatch and say so: {refused.stderr}")
    require(not (primary / ".git/agent-do/integration/workspaces.json").exists(), "off wrote state")
    missing_check = integ(["enable", "--target", "main", "--authorized-by", "x"], cwd=primary, env=estate.integrator.env)
    require(missing_check.returncode == 1 and "--check" in missing_check.stderr, f"enable needs a check: {missing_check.stderr}")
    bad_target = integ(["enable", "--target", "nope", "--check", "true", "--authorized-by", "x"], cwd=primary, env=estate.integrator.env)
    require(bad_target.returncode == 1 and "not a local branch" in bad_target.stderr, f"enable needs a real branch: {bad_target.stderr}")
    no_authority = integ(["enable", "--target", "main", "--check", "true"], cwd=primary, env=estate.integrator.env)
    require(no_authority.returncode == 1 and "--authorized-by" in no_authority.stderr, f"enable needs explicit authority: {no_authority.stderr}")

    tree_before = git(primary, "status", "--porcelain")
    enabled = estate.enable()
    cfg = enabled["config"]
    require(cfg["state"] == "enabled" and cfg["target"] == "main" and cfg["checks"] == ["sh ./ci.sh"], f"enable payload: {cfg}")
    require(cfg["authorized_by"].startswith("fixture operator") and cfg["board_id"] and cfg["board_id"].startswith("mb-"), f"authority and board pinned: {cfg}")
    stored = git(primary, "config", "--file", ".git/config", "--get-regexp", r"^agent-do\.integration\.")
    require("agent-do.integration.enabled true" in stored and "agent-do.integration.check sh ./ci.sh" in stored, f"policy lives in the private config: {stored}")
    require(git(primary, "status", "--porcelain") == tree_before, "enable must not touch the working tree (policy is not a tracked file)")

    git(primary, "config", "--file", ".git/config", "agent-do.integration.bogus", "1")
    invalid = integ(["config", "--json"], cwd=primary, env=estate.lead.env)
    require(invalid.returncode == 1 and json.loads(invalid.stdout)["config"]["state"] == "invalid", f"unknown key must invalidate: {invalid.stdout}")
    refused = integ(["workspace", "add", item, "--json"], cwd=primary, env=worker.env)
    require(refused.returncode == 1 and json.loads(refused.stdout)["state"] == "invalid", f"invalid must refuse dispatch: {refused.stdout}")
    run_invalid = integ(["run", "--json"], cwd=primary, env=estate.integrator.env)
    require(run_invalid.returncode == 1 and json.loads(run_invalid.stdout)["state"] == "invalid", f"invalid must refuse landing: {run_invalid.stdout}")
    git(primary, "config", "--file", ".git/config", "--unset", "agent-do.integration.bogus")
    git(primary, "config", "--file", ".git/config", "agent-do.integration.enabled", "maybe")
    invalid = integ(["config", "--json"], cwd=primary, env=estate.lead.env)
    require(invalid.returncode == 1 and any("true or false" in p for p in json.loads(invalid.stdout)["config"]["problems"]), f"non-boolean enabled: {invalid.stdout}")
    git(primary, "config", "--file", ".git/config", "agent-do.integration.enabled", "true")

    ws = estate.workspace(item, worker)
    require(ws["created"], f"workspace should be created once enabled: {ws}")
    disabled = integ_json(["disable", "--reason", "pause for review"], cwd=primary, env=estate.integrator.env)
    require(disabled["config"]["state"] == "disabled" and disabled["retained"]["workspaces"] == 1, f"disable payload: {disabled}")
    refused = integ(["workspace", "add", item], cwd=primary, env=worker.env)
    require(refused.returncode == 1 and "disabled" in refused.stderr and "pause for review" in refused.stderr, f"disabled must refuse new dispatch: {refused.stderr}")
    source = commit(Path(ws["workspace"]["path"]), item, "src/feature.txt", "feature\n", "feat: feature")
    refused = integ(["submit", item], cwd=Path(ws["workspace"]["path"]), env=worker.env)
    require(refused.returncode == 1 and "disabled" in refused.stderr, f"disabled must refuse new submissions: {refused.stderr}")
    ran = estate.run_integrator()
    require(ran["state"] == "disabled" and ran["processed"] == [], f"disabled run lands nothing: {ran}")
    state = estate.item_state(item)
    require(state["state"] == "building" and Path(state["workspace"]["path"]).is_dir(), f"status and worktree survive disable: {state}")
    require(git(primary, "rev-parse", f"refs/heads/{ws['workspace']['branch']}") == source, "the worker branch survives disable")
    estate.enable()
    queued = estate.submit(item, worker, Path(ws["workspace"]["path"]))
    require(queued["entry"]["status"] == "queued", f"re-enabled accepts submissions: {queued['entry']['status']}")
    print("  ok: opt-in off / enabled / invalid / disabled")


def test_canonical_board_and_workspace(root: Path, base: dict[str, str]) -> None:
    estate = Estate(root, "canonical", base)
    item = estate.create("canonical board across worktrees")
    unclaimed_item = estate.create("unclaimed")
    worker = Session(base, "worker-canon")
    claimed = estate.claim(item, worker)
    primary = estate.primary

    stranger = integ(["workspace", "add", item, "--json"], cwd=primary, env=estate.lead.env)
    require(stranger.returncode == CONTENDED and "proof mismatch" in json.loads(stranger.stdout)["error"], f"a non-claimant must be refused by proof: {stranger.stdout}")
    refused = integ(["workspace", "add", unclaimed_item, "--json"], cwd=primary, env=worker.env)
    require(refused.returncode == 1 and "claim it first" in json.loads(refused.stdout)["error"], f"an unclaimed item has no worker: {refused.stdout}")

    created = estate.workspace(item, worker)
    ws = created["workspace"]
    path = Path(ws["path"])
    require(created["created"] and path.is_dir(), f"workspace not created: {created}")
    require(ws["branch"] == f"integration/{item}-a1" and ws["attempt"] == 1, f"branch and attempt: {ws}")
    require(path.resolve() == (root / f"canonical-{item}-a1").resolve(), f"default path beside the repository: {path}")
    require(ws["base_sha"] == estate.tip() and git(path, "rev-parse", "HEAD") == estate.tip(), "workspace starts at the target tip")
    require(ws["worker"]["proof"] == claimed["claim_token_hash"] and ws["worker"]["label"] == claimed["claimed_by"], f"exact worker binding: {ws['worker']}")
    require(ws["board"]["path"] == str(primary / ".manna") and ws["board"]["id"].startswith("mb-"), f"canonical board pinned: {ws['board']}")
    require(ws["work_order"]["digest"] == claimed["handoff_digest"], "work order digest pinned")
    binding = created["coord"][0]
    require(binding["ok"] and binding["manna"]["proof"] == claimed["claim_token_hash"], f"coord binding at the canonical root: {binding}")
    lookup = coord_json(["worker", item], cwd=primary, env=estate.lead.env)
    require(lookup["recipient_state"] == "resolved" and lookup["session"]["agent_id"] == binding["agent_id"], f"the worker resolves in the canonical coord store: {lookup}")
    require(lookup["session"]["binding"]["proof"] == claimed["claim_token_hash"], f"bound by claim proof: {lookup['session']['binding']}")

    # The worktree carries its own copy of the board, at the committed state,
    # which does not know the claim: the divergent copy the work order names.
    copy = path / ".manna" / "issues.jsonl"
    require(copy.is_file(), "the worktree carries a board copy")
    copy_before = copy.read_bytes()
    copy_rows = [json.loads(line) for line in copy_before.decode().splitlines() if line.strip()]
    require([row for row in copy_rows if row.get("id") == item][0].get("claimed_by") is None, "the worktree copy predates the claim")
    again = estate.workspace(item, worker, cwd=path)
    require(again["created"] is False and again["workspace"]["path"] == ws["path"], f"idempotent from inside the worktree: {again}")
    require(again["via_worktree"] is True and again["canonical_root"] == str(primary), f"the canonical checkout is resolved from the worktree: {again}")
    require(copy.read_bytes() == copy_before, "the worktree's board copy is never written")
    canonical_row = estate.row(item)
    require(canonical_row["claimed_by"] == claimed["claimed_by"], "the canonical row is the one read")

    listed = integ_json(["workspace", "list"], cwd=path, env=worker.env)
    require(listed["count"] == 1 and listed["workspaces"][0]["exists"], f"workspace list: {listed}")

    # Board-owned paths never ride a worker branch into canonical state.
    copy.write_text(copy_before.decode() + "\n", encoding="utf-8")
    git(path, "add", ".manna/issues.jsonl")
    git(path, "commit", "-qm", f"board edit in a worktree\n\nManna: {item}")
    (path / ".handoff" / "stray.md").write_text("stray\n", encoding="utf-8")
    git(path, "add", ".handoff/stray.md")
    git(path, "commit", "-qm", f"stray handoff\n\nManna: {item}")
    refused = integ(["submit", item, "--json"], cwd=path, env=worker.env)
    payload = json.loads(refused.stdout)
    require(refused.returncode == 1 and sorted(payload["board_paths"]) == [".handoff/stray.md", ".manna/issues.jsonl"], f"board paths must be refused: {payload}")
    git(path, "reset", "-q", "--hard", ws["base_sha"])
    empty = integ(["submit", item, "--json"], cwd=path, env=worker.env)
    require(empty.returncode == 1 and "nothing to integrate" in json.loads(empty.stdout)["error"], f"no commits, no submission: {empty.stdout}")
    print("  ok: canonical board across worktrees, exact binding, board paths refused")


def test_submit_land_replay(root: Path, base: dict[str, str]) -> None:
    estate = Estate(root, "land", base)
    item = estate.create("land a fast-forward")
    worker = Session(base, "worker-land")
    estate.claim(item, worker)
    primary = estate.primary
    ws = Path(estate.workspace(item, worker)["workspace"]["path"])
    before = count_commits(primary)
    source = commit(ws, item, "src/feature.txt", "feature\n", "feat: feature")

    queued = estate.submit(item, worker, ws, "sh ./ci.sh passed in the workspace")
    entry = queued["entry"]
    require(entry["status"] == "queued" and entry["source_sha"] == source and entry["base_sha"] == estate.tip(), f"queue entry: {entry}")
    require(entry["submission"]["source"] == "local" and entry["submission"]["id"].startswith("isub-"), f"unmanaged submission id: {entry['submission']}")
    require(entry["trailer_commits"] == [source] and entry["evidence"] == ["sh ./ci.sh passed in the workspace"], f"evidence pinned: {entry}")
    require(git(primary, "rev-parse", entry["submission_ref"]) == source, "the submitted commit is pinned by ref")
    require(Path(entry["report"]).read_text(encoding="utf-8").startswith("# Submission"), "a report was written")
    require(estate.item_state(item)["state"] == "queued", "status says queued")

    ran = estate.run_integrator()
    outcome = ran["processed"][0]
    require(outcome["outcome"] == "landed" and outcome["fast_forward"] is True and outcome["integrated_sha"] == source, f"landing: {outcome}")
    require("merge --ff-only" in outcome["via"], f"the primary holds main, so the landing fast-forwards it: {outcome['via']}")
    require(estate.tip() == source and (primary / "src" / "feature.txt").read_text() == "feature\n", "the primary checkout advanced with its working tree")
    require(count_commits(primary) == before + 1, "exactly one commit landed")
    state = estate.item_state(item)
    result = state["entry"]["result"]
    require(state["state"] == "landed" and result["provenance"] == {"submission_sha": source, "integrated_sha": source, "submission_id": entry["submission"]["id"], "attempt": 1}, f"provenance: {result}")
    require(result["checks"][0]["ok"] and Path(result["checks"][0]["log"]).read_text().strip().endswith("ci ok"), f"check receipt: {result['checks']}")
    require(Path(state["evidence"]["receipts"], "summary.md").is_file(), "summary receipt written")
    require(git(primary, "rev-parse", result["candidate_ref"]) == source, "the tested candidate is pinned by ref")
    require("manna accept" in state["next_action"] and source in state["next_action"], f"next action names the acceptance: {state['next_action']}")
    require(not (estate.state_dir() / "intent.json").exists(), "no intent survives a completed landing")
    info = [d for d in drops_for(estate, worker, item) if d["kind"] == "info"]
    require(len(info) == 1 and "landed" in info[0]["note"] and info[0]["delivery"]["recipient"]["state"] == "resolved", f"the worker is told, by item: {info}")
    require(result and state["evidence"]["routing"][-1]["state"] == "recorded", f"routing receipt: {state['evidence']['routing']}")

    replay = estate.run_integrator()
    require(replay["processed"] == [] and replay["recovered"] == [], f"replay must find nothing: {replay}")
    recovered = integ_json(["recover"], cwd=primary, env=estate.integrator.env)
    require(recovered["recovered"] == [], f"recover with nothing pending: {recovered}")
    require(estate.tip() == source and count_commits(primary) == before + 1, "replay landed nothing twice")
    again = integ(["submit", item, "--json"], cwd=ws, env=worker.env)
    require(again.returncode == 1 and "nothing to integrate" in json.loads(again.stdout)["error"], "a landed branch has nothing new to submit")
    print("  ok: submit, land (fast-forward in the holder), receipts, info drop, replay is a no-op")


def test_stale_base_and_competing_submissions(root: Path, base: dict[str, str]) -> None:
    estate = Estate(root, "stale", base)
    item_a = estate.create("stale base A")
    item_b = estate.create("stale base B")
    worker_a = Session(base, "worker-stale-a")
    worker_b = Session(base, "worker-stale-b")
    estate.claim(item_a, worker_a)
    estate.claim(item_b, worker_b)
    primary = estate.primary
    ws_a = Path(estate.workspace(item_a, worker_a)["workspace"]["path"])
    ws_b = Path(estate.workspace(item_b, worker_b)["workspace"]["path"])
    first_a = commit(ws_a, item_a, "src/a.txt", "a1\n", "feat: a1")
    entry_a1 = estate.submit(item_a, worker_a, ws_a)["entry"]
    source_a = commit(ws_a, item_a, "src/a.txt", "a2\n", "feat: a2")
    competing = estate.submit(item_a, worker_a, ws_a)
    require(competing["superseded"] == [entry_a1["id"]], f"the second submission supersedes the first: {competing['superseded']}")
    source_b = commit(ws_b, item_b, "src/b.txt", "b\n", "feat: b")
    entry_b = estate.submit(item_b, worker_b, ws_b)["entry"]
    moved = estate.external_commit("src/main-only.txt", "main\n")
    require(moved != entry_b["base_sha"], "main moved after both submissions")

    ran = estate.run_integrator()
    outcomes = {o["item"]: o for o in ran["processed"]}
    require(set(outcomes) == {item_a, item_b} and all(o["outcome"] == "landed" for o in outcomes.values()), f"both land: {ran}")
    require(outcomes[item_a]["fast_forward"] is False and outcomes[item_b]["fast_forward"] is False, "a moved base means a merge candidate, not a fast-forward")
    tip = estate.tip()
    require(tip == outcomes[item_b]["integrated_sha"], "the last landing is the tip")
    require(git(primary, "merge-base", "--is-ancestor", outcomes[item_a]["integrated_sha"], tip) == "", "A landed before B")
    require(git(primary, "merge-base", "--is-ancestor", moved, outcomes[item_a]["integrated_sha"]) == "", "A was rebuilt on the moved base")
    for path, content in (("src/a.txt", "a2\n"), ("src/b.txt", "b\n"), ("src/main-only.txt", "main\n")):
        require((primary / path).read_text() == content, f"{path} present after landing")
    state_a = estate.item_state(item_a)
    require(state_a["entry"]["source_sha"] == source_a and state_a["entry"]["result"]["base_sha"] == moved, f"A tested against the base at run time: {state_a['entry']['result']}")
    require(state_a["entry"]["result"]["provenance"]["submission_sha"] == source_a != state_a["entry"]["result"]["integrated_sha"], "original submission and integrated SHA both recorded")
    history = {e["id"]: e for e in json.loads((estate.state_dir() / "queue.json").read_text())["entries"]}
    require(history[entry_a1["id"]]["status"] == "superseded" and history[entry_a1["id"]]["superseded_by"] == state_a["entry"]["id"], "the superseded entry is history, not landed")
    require(git(primary, "rev-parse", history[entry_a1["id"]]["submission_ref"]) == first_a, "the superseded submission stays recoverable by ref")
    state_b = estate.item_state(item_b)
    require(state_b["entry"]["result"]["base_sha"] == outcomes[item_a]["integrated_sha"], "B was built against A's landing, the base at its run time")
    print("  ok: competing submissions supersede, stale base rebuilds, serial landings keep provenance")


def test_conflict_routes_action_drop(root: Path, base: dict[str, str]) -> None:
    estate = Estate(root, "conflict", base)
    item = estate.create("conflicting change")
    worker = Session(base, "worker-conflict")
    estate.claim(item, worker)
    primary = estate.primary
    ws = Path(estate.workspace(item, worker)["workspace"]["path"])
    source = commit(ws, item, "README.md", "# fixture\n\nline one from the worker\n", "docs: worker line")
    estate.submit(item, worker, ws)
    estate.external_commit("README.md", "# fixture\n\nline one from main\n", "docs: main line")
    tip_before = estate.tip()

    ran = estate.run_integrator()
    outcome = ran["processed"][0]
    require(outcome["outcome"] == "blocked" and outcome["reason"] == "conflict" and outcome["retryable"] is False, f"conflict blocks: {outcome}")
    state = estate.item_state(item)
    require(state["state"] == "blocked" and state["entry"]["result"]["conflicts"] == ["README.md"], f"conflict evidence: {state['entry']['result']}")
    require(estate.tip() == tip_before and git(primary, "rev-parse", f"refs/heads/integration/{item}-a1") == source, "nothing moved; the worker branch is intact")
    require(not git(estate.candidate, "status", "--porcelain"), "the candidate tree is clean after the aborted merge")
    require(outcome["routing"]["state"] == "recorded" and outcome["routing"]["delivery"]["recipient"]["state"] == "resolved", f"action drop routed to the worker: {outcome['routing']}")
    actions = [d for d in drops_for(estate, worker, item) if d["kind"] == "action"]
    require(len(actions) == 1 and actions[0]["status"] == "open" and "conflict" in actions[0]["note"], f"the worker sees one obligation: {actions}")
    pointer = Path(actions[0]["path"])
    pointer = pointer if pointer.is_absolute() else primary / pointer
    require(pointer.read_text(encoding="utf-8").startswith(f"# Integration {state['entry']['id']}: blocked (conflict)"), "the drop points at the summary receipt")
    require("merge main into" in state["next_action"], f"next action tells the worker what to do: {state['next_action']}")
    lookup = coord_json(["worker", item], cwd=primary, env=estate.lead.env)
    require([o["id"] for o in lookup["obligations"]] == [actions[0]["id"]], f"coord worker shows the obligation: {lookup['obligations']}")

    again = estate.run_integrator()
    require(again["processed"] == [], f"a worker-owed block is not retried: {again}")
    require(len([d for d in drops_for(estate, worker, item) if d["kind"] == "action"]) == 1, "no duplicate obligation on rerun")

    git(ws, "-c", "user.email=w@x", "-c", "user.name=w", "merge", "main", check=False)
    (ws / "README.md").write_text("# fixture\n\nline one from main and the worker\n", encoding="utf-8")
    git(ws, "add", "README.md")
    git(ws, "-c", "user.email=w@x", "-c", "user.name=w", "commit", "-qm", f"merge main\n\nManna: {item}")
    resolved = commit(ws, item, "src/after.txt", "after\n", "feat: after the merge")
    resubmitted = estate.submit(item, worker, ws)
    require(resubmitted["superseded"] == [state["entry"]["id"]], "the resubmission supersedes the blocked entry")
    landed = estate.run_integrator()["processed"][0]
    require(landed["outcome"] == "landed" and landed["integrated_sha"] == resolved and landed["fast_forward"] is True, f"resolved submission lands: {landed}")
    require((primary / "README.md").read_text().endswith("main and the worker\n"), "the resolution is what landed")
    print("  ok: conflict blocks with evidence, routes one action drop, resubmission lands")


def test_failed_checks(root: Path, base: dict[str, str]) -> None:
    estate = Estate(root, "checks", base)
    item = estate.create("failing checks")
    worker = Session(base, "worker-checks")
    estate.claim(item, worker)
    primary = estate.primary
    ws = Path(estate.workspace(item, worker)["workspace"]["path"])
    commit(ws, item, "src/app.txt", "app v2 BROKEN\n", "feat: broken")
    estate.submit(item, worker, ws)
    tip_before = estate.tip()
    ran = estate.run_integrator()
    outcome = ran["processed"][0]
    require(outcome["outcome"] == "blocked" and outcome["reason"] == "checks_failed", f"failed checks block: {outcome}")
    state = estate.item_state(item)
    check = state["entry"]["result"]["checks"][0]
    require(check["ok"] is False and check["exit"] == 1 and "BROKEN found" in Path(check["log"]).read_text(), f"check log is the receipt: {check}")
    require(estate.tip() == tip_before, "a failing candidate never lands")
    require(git(primary, "rev-parse", state["entry"]["result"]["candidate_ref"]) == state["entry"]["result"]["candidate_sha"], "the failing candidate stays pinned for inspection")
    actions = [d for d in drops_for(estate, worker, item) if d["kind"] == "action"]
    require(len(actions) == 1 and "checks_failed" in actions[0]["note"], f"the worker is told what failed: {actions}")
    fixed = commit(ws, item, "src/app.txt", "app v2\n", "fix: unbroken")
    estate.submit(item, worker, ws)
    landed = estate.run_integrator()["processed"][0]
    require(landed["outcome"] == "landed" and landed["integrated_sha"] == fixed, f"the fix lands: {landed}")
    print("  ok: failed checks block with the log, the fix lands")


def test_dirty_target_checkout(root: Path, base: dict[str, str]) -> None:
    estate = Estate(root, "dirty", base)
    item = estate.create("dirty primary")
    worker = Session(base, "worker-dirty")
    estate.claim(item, worker)
    primary = estate.primary
    ws = Path(estate.workspace(item, worker)["workspace"]["path"])
    (primary / "README.md").write_text("# fixture\n\nuncommitted operator edit\n", encoding="utf-8")
    source = commit(ws, item, "src/x.txt", "x1\n", "feat: x1")
    estate.submit(item, worker, ws)
    landed = estate.run_integrator()["processed"][0]
    require(landed["outcome"] == "landed" and estate.tip() == source, f"a non-overlapping dirty checkout still fast-forwards: {landed}")
    require((primary / "README.md").read_text() == "# fixture\n\nuncommitted operator edit\n", "the operator's uncommitted edit survived the landing")
    require((primary / "src" / "x.txt").read_text() == "x1\n", "the landed file is in the primary working tree")

    (primary / "src" / "x.txt").write_text("x1 with an uncommitted overlap\n", encoding="utf-8")
    second = commit(ws, item, "src/x.txt", "x2\n", "feat: x2")
    estate.submit(item, worker, ws)
    blocked = estate.run_integrator()["processed"][0]
    require(blocked["outcome"] == "blocked" and blocked["reason"] == "target_checkout_busy" and blocked["retryable"] is True, f"an overlapping dirty checkout blocks, retryable: {blocked}")
    require(estate.tip() == source and (primary / "src" / "x.txt").read_text() == "x1 with an uncommitted overlap\n", "nothing moved and the dirty file is untouched")
    require(not (estate.state_dir() / "intent.json").exists(), "a refused landing leaves no intent behind")
    state = estate.item_state(item)
    require(git(primary, "rev-parse", state["entry"]["result"]["candidate_ref"]) == second, "the tested candidate is pinned for the retry")
    require([d for d in drops_for(estate, worker, item) if d["kind"] == "action"] == [], "an operator-side block is not an obligation for the worker")
    git(primary, "checkout", "--", "src/x.txt")
    retried = estate.run_integrator()["processed"][0]
    require(retried["outcome"] == "landed" and retried["integrated_sha"] == second and retried["entry"] == state["entry"]["id"], f"the same entry lands once the checkout is clean: {retried}")
    require((primary / "README.md").read_text().endswith("uncommitted operator edit\n"), "unrelated dirt still preserved")
    print("  ok: dirty target checkout: non-overlapping edits preserved, overlapping edits block and retry")


def test_interruptions(root: Path, base: dict[str, str]) -> None:
    estate = Estate(root, "interrupt", base)
    primary = estate.primary
    workers = {}
    items = {}
    for key in ("before", "after", "moved"):
        items[key] = estate.create(f"interrupted {key}")
        workers[key] = Session(base, f"worker-int-{key}")
        estate.claim(items[key], workers[key])
    spaces = {key: Path(estate.workspace(items[key], workers[key])["workspace"]["path"]) for key in items}

    # Interrupted after the landing intent, before the ref update.
    source = commit(spaces["before"], items["before"], "src/before.txt", "before\n", "feat: before")
    estate.submit(items["before"], workers["before"], spaces["before"])
    count = count_commits(primary)
    fault_env = dict(estate.integrator.env, AGENT_GIT_INTEGRATION_FAULT="after_intent")
    crashed = integ(["run", "--json"], cwd=primary, env=fault_env)
    require(crashed.returncode == FAULT_EXIT, f"the fault seam must stop the process: {crashed.returncode} {crashed.stderr}")
    intent = json.loads((estate.state_dir() / "intent.json").read_text())
    require(intent["candidate"] == source and intent["base"] == estate.tip() and estate.tip() != source, f"intent durable, ref untouched: {intent}")
    state = estate.item_state(items["before"])
    require(state["state"] == "integrating" and estate.status()["intent"]["entry"] == state["entry"]["id"], f"status shows the landing in flight: {state['state']}")
    blocked_submit = integ(["submit", items["before"], "--json"], cwd=spaces["before"], env=workers["before"].env)
    require(blocked_submit.returncode == 1 and "in flight" in json.loads(blocked_submit.stdout)["error"], "a landing in flight refuses a new submission for that item")
    recovered = integ_json(["recover"], cwd=primary, env=estate.integrator.env)
    outcome = recovered["recovered"][0]
    require(outcome["outcome"] == "landed" and outcome["recovered"] is True and "before the ref update" in outcome["via"], f"recover lands the tested candidate once: {outcome}")
    require(estate.tip() == source and count_commits(primary) == count + 1, "exactly one commit landed")
    require(not (estate.state_dir() / "intent.json").exists(), "intent retired")
    replay = integ_json(["recover"], cwd=primary, env=estate.integrator.env)
    require(replay["recovered"] == [] and count_commits(primary) == count + 1, "recover replay lands nothing")

    # Interrupted after the ref update, before the receipt.
    source = commit(spaces["after"], items["after"], "src/after.txt", "after\n", "feat: after")
    estate.submit(items["after"], workers["after"], spaces["after"])
    count = count_commits(primary)
    fault_env = dict(estate.integrator.env, AGENT_GIT_INTEGRATION_FAULT="after_ref_update")
    crashed = integ(["run", "--json"], cwd=primary, env=fault_env)
    require(crashed.returncode == FAULT_EXIT, "fault after the ref update")
    intent = json.loads((estate.state_dir() / "intent.json").read_text())
    candidate = intent["candidate"]
    require(estate.tip() == candidate and count_commits(primary) == count + 1, f"the ref advanced to the candidate before the crash: {estate.tip()} vs {candidate}")
    require(git(primary, "merge-base", "--is-ancestor", source, candidate) == "" and candidate != source, "the candidate merged the submission onto the moved base")
    require(estate.item_state(items["after"])["state"] == "integrating", "receipt incomplete, intent durable")
    ran = estate.run_integrator()
    outcome = ran["recovered"][0]
    require(outcome["outcome"] == "landed" and outcome["recovered"] is True and "already contains" in outcome["via"], f"run completes the receipt without landing again: {outcome}")
    require(ran["processed"] == [] and estate.tip() == candidate and count_commits(primary) == count + 1, "no second landing")
    state = estate.item_state(items["after"])
    require(state["state"] == "landed" and state["entry"]["result"]["recovered"] is True, f"the receipt says recovered: {state['entry']['result']}")

    # Interrupted before the ref update, then the target moves: void and rebuild.
    source = commit(spaces["moved"], items["moved"], "src/moved.txt", "moved\n", "feat: moved")
    estate.submit(items["moved"], workers["moved"], spaces["moved"])
    fault_env = dict(estate.integrator.env, AGENT_GIT_INTEGRATION_FAULT="after_intent")
    require(integ(["run", "--json"], cwd=primary, env=fault_env).returncode == FAULT_EXIT, "fault before the ref update")
    stale_candidate = json.loads((estate.state_dir() / "intent.json").read_text())["candidate"]
    moved = estate.external_commit("src/main-moved.txt", "main\n")
    recovered = integ_json(["recover"], cwd=primary, env=estate.integrator.env)
    outcome = recovered["recovered"][0]
    require(outcome["outcome"] == "requeued" and "moved" in outcome["reason"], f"a moved target voids the intent: {outcome}")
    require(estate.tip() == moved and not (estate.state_dir() / "intent.json").exists(), "nothing landed on the moved target; intent voided")
    require(git(primary, "rev-parse", f"refs/integration/candidates/{outcome['entry']}") == stale_candidate, "the voided candidate stays pinned")
    landed = estate.run_integrator()["processed"][0]
    require(landed["outcome"] == "landed" and landed["fast_forward"] is False and git(primary, "merge-base", "--is-ancestor", moved, landed["integrated_sha"]) == "", f"rebuilt on the moved base and landed: {landed}")
    require((primary / "src" / "moved.txt").read_text() == "moved\n" and (primary / "src" / "main-moved.txt").read_text() == "main\n", "both changes present")
    print("  ok: interruption before/after the ref update recovers exactly once; a moved target voids and rebuilds")


def test_authority_and_config_change(root: Path, base: dict[str, str]) -> None:
    estate = Estate(root, "authority", base)
    item = estate.create("authority change")
    worker = Session(base, "worker-auth")
    estate.claim(item, worker)
    primary = estate.primary
    ws = Path(estate.workspace(item, worker)["workspace"]["path"])
    source = commit(ws, item, "src/auth.txt", "auth\n", "feat: auth")
    entry = estate.submit(item, worker, ws)["entry"]
    tip_before = estate.tip()

    integ_json(["disable", "--reason", "authority withdrawn"], cwd=primary, env=estate.integrator.env)
    ran = estate.run_integrator()
    require(ran["state"] == "disabled" and ran["retained_queued"] == [entry["id"]] and estate.tip() == tip_before, f"disabled retains the queue and lands nothing: {ran}")

    git(primary, "branch", "release", "main")
    estate.enable(target="release")
    ran = estate.run_integrator()
    outcome = ran["processed"][0]
    require(outcome["outcome"] == "blocked" and outcome["reason"] == "config_changed" and outcome["retryable"] is True, f"a changed target fails closed: {outcome}")
    require(estate.tip() == tip_before and estate.tip("release") == tip_before, "no branch moved")

    estate.enable(target="main")
    git(primary, "config", "--file", ".git/config", "--unset", "agent-do.integration.authorized-by")
    invalid = integ(["run", "--json"], cwd=primary, env=estate.integrator.env)
    require(invalid.returncode == 1 and json.loads(invalid.stdout)["state"] == "invalid", f"authority removed means invalid, refuse: {invalid.stdout}")
    require(estate.tip() == tip_before, "invalid policy lands nothing")
    estate.enable(target="main")
    landed = estate.run_integrator()["processed"][0]
    require(landed["outcome"] == "landed" and landed["integrated_sha"] == source and landed["entry"] == entry["id"], f"restored authority lands the retained entry: {landed}")

    # Reassignment: a submission from a superseded claim is never forwarded.
    item2 = estate.create("reassigned")
    worker_a = Session(base, "worker-reassign-a")
    worker_b = Session(base, "worker-reassign-b")
    estate.claim(item2, worker_a)
    ws2 = Path(estate.workspace(item2, worker_a)["workspace"]["path"])
    first = commit(ws2, item2, "src/reassign.txt", "a\n", "feat: by a")
    estate.submit(item2, worker_a, ws2)
    require(manna(["abandon", item2], cwd=primary, env=worker_a.env).returncode == 0, "worker A abandons")
    estate.claim(item2, worker_b)
    tip_before = estate.tip()
    blocked = estate.run_integrator()["processed"][0]
    require(blocked["outcome"] == "blocked" and blocked["reason"] == "reassigned", f"a superseded claim's submission is not forwarded: {blocked}")
    require(estate.tip() == tip_before, "nothing landed for the reassigned item")
    rebound = estate.workspace(item2, worker_b)
    require(rebound["created"] is False and rebound["rebound"] is True and rebound["workspace"]["worker"]["label"] == "worker-reassign-b", f"the replacement inherits the workspace: {rebound}")
    require(git(ws2, "rev-parse", "HEAD") == first, "the inherited branch still carries A's commit")
    second = commit(ws2, item2, "src/reassign.txt", "a then b\n", "feat: by b")
    estate.submit(item2, worker_b, ws2)
    landed = estate.run_integrator()["processed"][0]
    require(landed["outcome"] == "landed" and landed["integrated_sha"] == second, f"the replacement's submission lands: {landed}")

    # Closure before landing: a done item is not landed automatically.
    item3 = estate.create("closed before landing")
    worker_c = Session(base, "worker-closed")
    estate.claim(item3, worker_c)
    ws3 = Path(estate.workspace(item3, worker_c)["workspace"]["path"])
    commit(ws3, item3, "src/closed.txt", "c\n", "feat: closed")
    estate.submit(item3, worker_c, ws3)
    require(manna(["done", item3], cwd=primary, env=worker_c.env).returncode == 0, "the claim-holder closes the item")
    tip_before = estate.tip()
    blocked = estate.run_integrator()["processed"][0]
    require(blocked["outcome"] == "blocked" and blocked["reason"] == "item_closed" and estate.tip() == tip_before, f"a closed item fails closed: {blocked}")
    print("  ok: disabled retains, changed target and removed authority fail closed, reassignment and closure are not forwarded")


def test_managed_replacement(root: Path, base: dict[str, str]) -> None:
    estate = Estate(root, "managed", base)
    item = estate.create("managed feature")
    primary = estate.primary
    lead = estate.lead
    lead_proof = lead.proof(primary)
    granted = operator_manna(["coordinator", "grant", "--session", lead.name, "--proof", lead_proof, "--item", item, "--reason", "lead for the managed feature"], cwd=primary, env=base)
    require(granted.returncode == 0, f"operator grant failed: {granted.stderr or granted.stdout}")
    required = manna(["managed", "require", item, "--check", "integrated"], cwd=primary, env=lead.env)
    require(required.returncode == 0, f"managed require failed: {required.stderr or required.stdout}")

    # The anchor never shares this process's stdio: an inherited pipe would hold
    # the suite's output open for the anchor's whole life if a step failed.
    anchor_a = subprocess.Popen(["sleep", "600"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _managed_replacement(estate, item, base, anchor_a)
    finally:
        if anchor_a.poll() is None:
            anchor_a.kill()
            anchor_a.wait()


def _managed_replacement(estate: Estate, item: str, base: dict[str, str], anchor_a: subprocess.Popen) -> None:
    primary = estate.primary
    lead = estate.lead
    worker_a = Session(base, "worker-managed-a", anchor=anchor_a)
    estate.claim(item, worker_a)
    registered_a = estate.workspace(item, worker_a)
    ws_a = Path(registered_a["workspace"]["path"])
    agent_a = registered_a["coord"][0]["agent_id"]
    broken = commit(ws_a, item, "src/app.txt", "app v3 BROKEN\n", "feat: broken by a")
    queued = estate.submit(item, worker_a, ws_a, "a ran nothing")
    entry_a = queued["entry"]
    require(queued["managed"] is True and entry_a["submission"]["source"] == "manna" and entry_a["submission"]["id"].startswith("sub-"), f"managed submission recorded through manna: {entry_a['submission']}")
    assessed = manna_json(["assess", item], cwd=primary, env=lead.env)
    require(assessed["submission_key"] == entry_a["submission"]["id"] and assessed["attempt"] == 1, f"manna holds the same submission: {assessed['submission_key']}")
    blocked = estate.run_integrator()["processed"][0]
    require(blocked["outcome"] == "blocked" and blocked["reason"] == "checks_failed", f"A's submission fails its checks: {blocked}")
    require(blocked["routing"] and blocked["routing"]["state"] == "recorded", f"the obligation must route to A: {blocked['routing']}")
    require([d for d in drops_for(estate, worker_a, item) if d["kind"] == "action"], "A owes an obligation")

    worker_a.kill()
    peers = coord_json(["peers", "--all"], cwd=primary, env=lead.env)["peers"]
    gone = [p for p in peers if p.get("agent_id") == agent_a]
    require(gone and gone[0]["status"] == "dead", f"coord must verify the worker dead: {gone}")
    released = manna(["managed", "release", item, "--reason", "worker died with failing checks"], cwd=primary, env=lead.env)
    require(released.returncode == 0, f"managed release failed: {released.stderr or released.stdout}")
    require(estate.row(item).get("claimed_by") is None and manna_json(["assess", item], cwd=primary, env=lead.env)["attempt"] == 2, "attempt 2, claim released")
    stale_late = integ(["submit", item, "--json"], cwd=ws_a, env=worker_a.env)
    require(stale_late.returncode == 1 and "only the live claimant" in json.loads(stale_late.stdout)["error"], "the dead worker's identity can no longer submit")

    worker_b = Session(base, "worker-managed-b")
    estate.claim(item, worker_b)
    inherited = estate.workspace(item, worker_b)
    ws_b = Path(inherited["workspace"]["path"])
    require(inherited["created"] and inherited["workspace"]["attempt"] == 2 and inherited["workspace"]["branch"] == f"integration/{item}-a2", f"attempt 2 workspace: {inherited['workspace']}")
    require(inherited["workspace"]["inherited_from"]["sha"] == broken and git(ws_b, "rev-parse", "HEAD") == broken, "the replacement inherits A's branch tip")
    require(ws_a.is_dir() and git(primary, "rev-parse", f"refs/heads/integration/{item}-a1") == broken, "A's worktree and branch are retained, never deleted")
    stale_add = integ(["workspace", "add", item, "--json"], cwd=ws_a, env=worker_a.env)
    require(stale_add.returncode == CONTENDED, "the superseded worker cannot re-register")

    fixed = commit(ws_b, item, "src/app.txt", "app v3\n", "fix: by b")
    queued_b = estate.submit(item, worker_b, ws_b, "sh ./ci.sh passed")
    entry_b = queued_b["entry"]
    require(entry_b["attempt"] == 2 and entry_b["submission"]["manna"]["attempt"] == 2 and queued_b["superseded"] == [], f"attempt 2 submission: {entry_b['submission']}")
    landed = estate.run_integrator()["processed"][0]
    require(landed["outcome"] == "landed" and landed["integrated_sha"] == fixed and landed["entry"] == entry_b["id"], f"B lands: {landed}")
    state = estate.item_state(item)
    require(state["state"] == "landed" and state["attempt"] == 2, f"status follows the live attempt: {state['state']} a{state['attempt']}")
    history = {e["id"]: e["status"] for e in json.loads((estate.state_dir() / "queue.json").read_text())["entries"]}
    require(history[entry_a["id"]] == "blocked" and history[entry_b["id"]] == "landed", f"A's entry is history, B's landed: {history}")

    # The coordinator accepts the landing manna already knows about and closes.
    assessed = manna_json(["assess", item], cwd=primary, env=lead.env)
    accepted = manna_json(
        ["accept", item, "--check", "integrated", "--target", fixed, "--evidence", str(Path(state["evidence"]["receipts"]) / "summary.md"), "--submission", assessed["submission_key"], "--attempt", str(assessed["attempt"])],
        cwd=primary,
        env=lead.env,
    )
    require(accepted.get("success", True), f"accept: {accepted}")
    verdict = manna_json(["assess", item], cwd=primary, env=lead.env)
    require(verdict["closable"] is True and verdict["assessment"].startswith("assess:v2:"), f"closable after acceptance at the integrated SHA: {verdict['blockers']}")
    closed = manna(["done", item, "--assessment", verdict["assessment"]], cwd=primary, env=lead.env)
    require(closed.returncode == 0 and estate.row(item)["status"] == "done", f"coordinator closes: {closed.stderr or closed.stdout}")
    print("  ok: managed item: worker dies, release verified through coord, replacement inherits, lands, coordinator accepts at the integrated SHA")


def test_integrator_lock(root: Path, base: dict[str, str]) -> None:
    estate = Estate(root, "lock", base)
    lock_path = estate.state_dir() / "integrator.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        contended = integ(["run", "--json"], cwd=estate.primary, env=estate.integrator.env)
        require(contended.returncode == CONTENDED and "another integrator" in json.loads(contended.stdout)["error"], f"one integrator per repository: {contended.stdout}")
        recover = integ(["recover", "--json"], cwd=estate.primary, env=estate.integrator.env)
        require(recover.returncode == CONTENDED, "recovery also waits for the lock")
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    released = estate.run_integrator()
    require(released["ok"] and released["processed"] == [], "the lock releases")
    print("  ok: one integrator per repository")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        base = {k: v for k, v in os.environ.items() if k not in THREAD_ENV_KEYS}
        base["AGENT_DO_HOME"] = str(root / "home")
        base["AGENT_DO_TELEMETRY_SUPPRESS"] = "1"
        base["AGENT_DO_HOOK_AI"] = "off"
        base["MANNA_OPERATOR"] = "0"
        base["AGENT_DO_COORD_ISOLATION_NUDGE"] = "0"
        scenarios = [
            test_config_states,
            test_canonical_board_and_workspace,
            test_submit_land_replay,
            test_stale_base_and_competing_submissions,
            test_conflict_routes_action_drop,
            test_failed_checks,
            test_dirty_target_checkout,
            test_interruptions,
            test_authority_and_config_change,
            test_managed_replacement,
            test_integrator_lock,
        ]
        chosen = sys.argv[1:]
        for scenario in scenarios:
            if chosen and scenario.__name__ not in chosen:
                continue
            print(f"{scenario.__name__}:")
            scenario(root, base)
    print("git managed integration tests passed")


if __name__ == "__main__":
    main()
