#!/usr/bin/env python3
"""Managed Integration behind `agent-do git integration` (mn-54fe40).

One repository opts in; one workspace (worktree + branch) exists per assignment
attempt; a submission requests integration; one integrator per repository
builds the candidate against the current target, validates that exact
combined tree, and advances the target only against the unchanged tested
base. Nothing here lands a commit that was not submitted, closes an item, or
deletes a branch or worktree.

Where things live (all shared by every worktree of the repository):

- policy: the common git dir's config, section `[agent-do "integration"]`.
  A tracked file would be a branch policy, rewritable by the very branch
  being landed; the private config is per-repository and untracked.
- state: `<common git dir>/agent-do/integration/` holds `workspaces.json`,
  `queue.json`, a write-ahead `intent.json` for the landing in flight,
  `events.jsonl`, and `receipts/<entry>/` (check logs, report, summary).
- refs: `refs/integration/submissions/<entry>` pins the exact submitted
  commit; `refs/integration/candidates/<entry>` keeps the tested candidate
  reachable for recovery. Worker branches are `integration/<mn-id>-a<N>`.

The board is read at the checkout that owns the common git dir (the same
rule coord uses), never at a worktree's copy; worker board copies are never
merged into canonical state, and a submission that touches `.manna/` or
`.handoff/` is refused.

Landing invariants (each held by a fixture in tests/test_git_integration.py):
the checks run on the candidate commit's own tree and that tree is verified
unchanged (HEAD, index, tracked files) before anything lands; the policy in
force at the ref update is, by digest, the policy the checks ran under; the
assignment is re-read immediately before the ref update; recovery before the
ref update re-verifies target, policy digest and assignment from the intent
and voids the landing otherwise, while recovery after the ref update only
finishes the record; the intent is retired after the queue row, the receipt,
the routing record and the audit line; and the integrator resets only a
candidate worktree carrying its own ownership marker.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CONFIG_SECTION = "agent-do.integration"
CONFIG_KEYS = {
    "enabled",
    "target",
    "check",
    "authorized-by",
    "authorized-at",
    "enabled-by",
    "board-id",
    "workspace-root",
    "candidate-path",
    "disabled-reason",
    "disabled-at",
    "disabled-by",
}
# Width of the hex tail every id here carries (`int-<12 hex>`), derived from
# the id format itself so the two read beside each other.
ID_HEX = len("int-1a2b3c4d5e6f") - len("int-")
BRANCH_PREFIX = "integration/"
SUBMISSION_REF_PREFIX = "refs/integration/submissions/"
CANDIDATE_REF_PREFIX = "refs/integration/candidates/"
BOARD_OWNED_PREFIXES = (".manna/", ".handoff/")
INTEGRATOR_IDENT = ["-c", "user.name=agent-do integrator", "-c", "user.email=integrator@agent-do.invalid"]

# Test seam, mirroring manna's MANNA_MANAGED_FAULT: the process exits here,
# before the next write, so interruption before the ref update, after it, and
# after the landed queue row (before routing, audit and intent retirement) can
# be reproduced deterministically.
FAULT_ENV = "AGENT_GIT_INTEGRATION_FAULT"
FAULT_EXIT = 70
FAULT_POINTS = ("after_intent", "after_ref_update", "after_landed_row")

# The check command runs the candidate's own scripts (a submitted branch can
# rewrite ci.sh), so the integrator's identity and credentials are withheld
# from its environment: names in IDENTITY_ENV, and any name carrying a
# secret-shaped marker. Names only are reported in the check log; values never.
IDENTITY_ENV = {
    "MANNA_SESSION_ID",
    "MANNA_SESSION_TOKEN",
    "MANNA_OPERATOR",
    "CLAUDE_SESSION_ID",
    "CLAUDE_THREAD_ID",
    "CLAUDE_AGENT_ID",
    "CODEX_THREAD_ID",
    "AGENT_DO_COORD_SESSION",
    "AGENT_DO_COORD_PID",
    "AGENT_DO_COORD_PID_START",
}
SECRET_NAME_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "API_KEY", "ACCESS_KEY", "PRIVATE_KEY", "AUTH_KEY", "SESSION_KEY")

# Ownership marker the integrator writes into its candidate worktree's private
# git dir when it creates the tree; a detached worktree at the candidate path
# without it belongs to someone else and is never reset or cleaned.
CANDIDATE_MARKER = "agent-do-integration-candidate"

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_CONTENDED = 2

# Blocked reasons the worker must act on (routed as action drops) versus
# reasons the integrator retries on its own once the operator clears them.
WORKER_REASONS = {"conflict", "checks_failed", "candidate_changed", "board_paths", "stale_submission", "reassigned", "item_closed"}
RETRYABLE_REASONS = {"target_checkout_busy", "config_disabled", "config_invalid", "config_changed"}


class Refusal(Exception):
    def __init__(self, message: str, code: int = EXIT_REFUSED, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.extra = extra


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(args: list[str], *, cwd: Path | str | None = None, env: dict[str, str] | None = None, stdin_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        input=stdin_text,
        text=True,
        capture_output=True,
        check=False,
        stdin=None if stdin_text is not None else subprocess.DEVNULL,
    )


def git(args: list[str], *, cwd: Path | str, check: bool = True) -> str:
    proc = run(["git", *args], cwd=cwd)
    if check and proc.returncode != 0:
        raise Refusal(f"git {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()}")
    return proc.stdout.strip()


def fault(point: str) -> None:
    if os.environ.get(FAULT_ENV, "") == point:
        print(f"git integration: injected fault `{point}`; exiting before the next write", file=sys.stderr)
        sys.exit(FAULT_EXIT)


def short_hex(value: str) -> str:
    return value[:ID_HEX]


def new_id(prefix: str, *parts: str) -> str:
    material = "\x1f".join([*parts, now_iso(), str(os.getpid()), os.urandom(ID_HEX).hex()])
    return prefix + hashlib.sha256(material.encode("utf-8")).hexdigest()[:ID_HEX]


# ---------------------------------------------------------------------------
# Repository resolution
# ---------------------------------------------------------------------------


class Repo:
    """The repository seen from cwd, with the canonical checkout resolved."""

    def __init__(self, cwd: Path) -> None:
        probe = run(["git", "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir", "--show-toplevel"], cwd=cwd)
        if probe.returncode != 0:
            raise Refusal("not a git repository")
        lines = probe.stdout.strip().splitlines()
        if len(lines) < 3:
            raise Refusal("not inside a git working tree")
        self.git_dir = Path(lines[0]).resolve()
        self.common_dir = Path(lines[1]).resolve()
        self.toplevel = Path(lines[2]).resolve()
        self.via_worktree = self.git_dir != self.common_dir
        self.canonical_root = self.common_dir.parent if self.common_dir.name == ".git" else self.toplevel
        self.repo_name = self.canonical_root.name
        self.integration_dir = self.common_dir / "agent-do" / "integration"
        self.config_path = self.common_dir / "config"
        self.board_dir = self.canonical_root / ".manna"

    def tip(self, branch: str) -> str | None:
        proc = run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}"], cwd=self.canonical_root)
        return proc.stdout.strip() if proc.returncode == 0 else None

    def resolve(self, reference: str) -> str | None:
        proc = run(["git", "rev-parse", "--verify", "--quiet", f"{reference}^{{commit}}"], cwd=self.canonical_root)
        return proc.stdout.strip() if proc.returncode == 0 else None

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        return run(["git", "merge-base", "--is-ancestor", ancestor, descendant], cwd=self.canonical_root).returncode == 0

    def merge_base(self, left: str, right: str) -> str | None:
        proc = run(["git", "merge-base", left, right], cwd=self.canonical_root)
        return proc.stdout.strip() if proc.returncode == 0 else None

    def worktrees(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for line in git(["worktree", "list", "--porcelain"], cwd=self.canonical_root).splitlines():
            if line.startswith("worktree "):
                if current:
                    items.append(current)
                current = {"path": line[len("worktree "):], "head": None, "branch": None, "detached": False, "bare": False}
            elif current is not None and line.startswith("HEAD "):
                current["head"] = line[len("HEAD "):]
            elif current is not None and line.startswith("branch refs/heads/"):
                current["branch"] = line[len("branch refs/heads/"):]
            elif current is not None and line == "detached":
                current["detached"] = True
            elif current is not None and line == "bare":
                current["bare"] = True
        if current:
            items.append(current)
        return items

    def checkout_holding(self, branch: str) -> Path | None:
        for item in self.worktrees():
            if item.get("branch") == branch:
                return Path(item["path"])
        return None

    def board_id(self) -> str | None:
        path = self.board_dir / "federation.yaml"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        match = re.search(r"^board_id:\s*(\S+)\s*$", text, re.MULTILINE)
        return match.group(1) if match else None

    def changed_paths(self, base: str, head: str) -> list[str]:
        out = git(["diff", "--name-only", base, head], cwd=self.canonical_root)
        return [line for line in out.splitlines() if line]


# ---------------------------------------------------------------------------
# Policy: the common git dir's config
# ---------------------------------------------------------------------------


def config_pairs(repo: Repo) -> list[tuple[str, str]]:
    proc = run(["git", "config", "--file", str(repo.config_path), "--get-regexp", f"^{re.escape(CONFIG_SECTION)}\\."], cwd=repo.canonical_root)
    pairs: list[tuple[str, str]] = []
    if proc.returncode != 0:
        return pairs
    for line in proc.stdout.splitlines():
        key, _, value = line.partition(" ")
        pairs.append((key[len(CONFIG_SECTION) + 1:], value))
    return pairs


def config_digest(pairs: list[tuple[str, str]]) -> str:
    material = "\n".join(f"{key}={value}" for key, value in sorted(pairs))
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


class Config:
    def __init__(self, repo: Repo) -> None:
        self.repo = repo
        self.pairs = config_pairs(repo)
        self.present = bool(self.pairs)
        self.digest = config_digest(self.pairs)
        values: dict[str, list[str]] = {}
        for key, value in self.pairs:
            values.setdefault(key, []).append(value)
        self.values = values
        self.unknown = sorted(key for key in values if key not in CONFIG_KEYS)
        self.enabled_raw = values.get("enabled", [None])[-1]
        self.target = (values.get("target") or [None])[-1]
        self.checks = values.get("check", [])
        self.authorized_by = (values.get("authorized-by") or [None])[-1]
        self.authorized_at = (values.get("authorized-at") or [None])[-1]
        self.enabled_by = (values.get("enabled-by") or [None])[-1]
        self.board_id = (values.get("board-id") or [None])[-1]
        self.workspace_root = (values.get("workspace-root") or [None])[-1]
        self.candidate_path = (values.get("candidate-path") or [None])[-1]
        self.disabled_reason = (values.get("disabled-reason") or [None])[-1]
        self.disabled_at = (values.get("disabled-at") or [None])[-1]
        self.state, self.problems = self._validate()

    @property
    def enabled(self) -> bool | None:
        if self.enabled_raw is None:
            return None
        lowered = self.enabled_raw.strip().lower()
        if lowered in {"true", "yes", "on", "1"}:
            return True
        if lowered in {"false", "no", "off", "0"}:
            return False
        return None

    def _validate(self) -> tuple[str, list[str]]:
        problems: list[str] = []
        if not self.present:
            return "off", problems
        if self.unknown:
            problems.append("unknown keys under [agent-do \"integration\"]: " + ", ".join(self.unknown))
        enabled = self.enabled
        if self.enabled_raw is None:
            problems.append("`enabled` is missing")
        elif enabled is None:
            problems.append(f"`enabled` must be true or false, not {self.enabled_raw!r}")
        if len(self.values.get("enabled", [])) > 1:
            problems.append("`enabled` is set more than once")
        for key in ("target", "authorized-by", "workspace-root", "candidate-path", "board-id"):
            if len(self.values.get(key, [])) > 1:
                problems.append(f"`{key}` is set more than once")
        for key, value in (("workspace-root", self.workspace_root), ("candidate-path", self.candidate_path)):
            if value is not None and not Path(value).is_absolute():
                problems.append(f"`{key}` must be an absolute path, got {value!r}")
        if self.candidate_path and Path(self.candidate_path).resolve() == self.repo.canonical_root:
            problems.append("`candidate-path` must not be the primary checkout")
        if enabled:
            if not self.target:
                problems.append("`target` (the branch submissions land on) is missing")
            else:
                if run(["git", "check-ref-format", "--branch", self.target], cwd=self.repo.canonical_root).returncode != 0:
                    problems.append(f"`target` is not a valid branch name: {self.target!r}")
                elif self.repo.tip(self.target) is None:
                    problems.append(f"`target` is not a local branch of this repository: {self.target!r}")
            if not self.checks:
                problems.append("at least one `check` command is required; reuse the repository's own validation commands")
            if not (self.authorized_by or "").strip():
                problems.append("`authorized-by` is missing: integration authority must be explicit")
            board = self.repo.board_id()
            if self.board_id and board and self.board_id != board:
                problems.append(f"`board-id` {self.board_id} does not match the canonical board {board}")
        if problems:
            return "invalid", problems
        return ("enabled" if enabled else "disabled"), problems

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "problems": self.problems,
            "digest": self.digest,
            "config_file": str(self.repo.config_path),
            "enabled": self.enabled,
            "target": self.target,
            "checks": list(self.checks),
            "authorized_by": self.authorized_by,
            "authorized_at": self.authorized_at,
            "enabled_by": self.enabled_by,
            "board_id": self.board_id,
            "workspace_root": self.workspace_root or str(self.repo.canonical_root.parent),
            "candidate_path": self.candidate_path or str(default_candidate_path(self.repo)),
            "disabled_reason": self.disabled_reason,
            "disabled_at": self.disabled_at,
            "unknown_keys": self.unknown,
        }

    def require_enabled(self, verb: str) -> None:
        if self.state == "enabled":
            return
        if self.state == "off":
            raise Refusal(
                f"Managed Integration is not enabled for this repository; `{verb}` does nothing and the existing workflow is unchanged "
                f"(opt in with: agent-do git integration enable --target <branch> --check <cmd> --authorized-by <who>)",
                state="off",
            )
        if self.state == "disabled":
            raise Refusal(
                f"Managed Integration is disabled for this repository ({self.disabled_reason or 'no reason recorded'}, {self.disabled_at or 'time unknown'}); "
                f"`{verb}` starts no new dispatch or landing. Status, recovery, pending submissions and worktrees are retained.",
                state="disabled",
            )
        raise Refusal(
            "Managed Integration configuration is invalid; refusing `" + verb + "`: " + "; ".join(self.problems),
            state="invalid",
            problems=self.problems,
        )


def default_candidate_path(repo: Repo) -> Path:
    return repo.canonical_root.parent / f"{repo.repo_name}-integration"


def config_set(repo: Repo, key: str, value: str | None, *, add: bool = False) -> None:
    full = f"{CONFIG_SECTION}.{key}"
    if value is None:
        run(["git", "config", "--file", str(repo.config_path), "--unset-all", full], cwd=repo.canonical_root)
        return
    args = ["git", "config", "--file", str(repo.config_path)]
    if add:
        args.append("--add")
    proc = run([*args, full, value], cwd=repo.canonical_root)
    if proc.returncode != 0:
        raise Refusal(f"could not write {full}: {(proc.stderr or proc.stdout).strip()}")


# ---------------------------------------------------------------------------
# Board and coordination access (always at the canonical checkout)
# ---------------------------------------------------------------------------


def manna_program() -> list[str]:
    beside = ROOT / "tools" / "agent-manna" / "agent-manna"
    if beside.is_file() and os.access(beside, os.X_OK):
        return [str(beside)]
    return [str(ROOT / "agent-do"), "manna"]


def coord_program() -> list[str]:
    beside = ROOT / "tools" / "agent-coord"
    if beside.is_file() and os.access(beside, os.X_OK):
        return [str(beside)]
    return [str(ROOT / "agent-do"), "coord"]


def _json_call(program: list[str], args: list[str], *, cwd: Path, env: dict[str, str] | None) -> tuple[dict[str, Any] | None, str | None]:
    call_env = dict(env or os.environ)
    call_env["AGENT_DO_TELEMETRY_SUPPRESS"] = "1"
    try:
        proc = run([*program, *args], cwd=cwd, env=call_env)
    except OSError as exc:
        return None, f"{' '.join(program)} could not start: {exc}"
    text = proc.stdout.strip()
    payload: dict[str, Any] | None = None
    if text:
        try:
            parsed = json.loads(text)
            payload = parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            payload = None
    if proc.returncode != 0 or payload is None or payload.get("success") is False or payload.get("ok") is False:
        message = None
        if payload:
            message = payload.get("error") or payload.get("message")
        if not message:
            message = (proc.stderr or proc.stdout).strip() or f"{program[-1]} {' '.join(args)} exited {proc.returncode}"
        return (payload if payload and payload.get("success") is not False and payload.get("ok") is not False else None), message
    return payload, None


def manna_json(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> tuple[dict[str, Any] | None, str | None]:
    return _json_call(manna_program(), [*args, "--json"], cwd=cwd, env=env)


def coord_json(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> tuple[dict[str, Any] | None, str | None]:
    return _json_call(coord_program(), [*args, "--json"], cwd=cwd, env=env)


def caller_identity(repo: Repo, env: dict[str, str] | None = None) -> dict[str, Any]:
    payload, error = manna_json(["identity"], cwd=repo.canonical_root, env=env)
    if not payload or not payload.get("proof"):
        raise Refusal(
            "no Manna session identity in this process: " + (error or "manna identity printed no proof")
            + ". Run from your agent session (the hooks pin it) or export MANNA_SESSION_ID and a secret MANNA_SESSION_TOKEN.",
            code=EXIT_CONTENDED,
        )
    return {"session": payload.get("session"), "proof": payload.get("proof"), "operator": bool(payload.get("operator"))}


def best_effort_label(repo: Repo, env: dict[str, str] | None = None) -> str:
    payload, _ = manna_json(["identity"], cwd=repo.canonical_root, env=env)
    if payload and payload.get("session"):
        return str(payload["session"])
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown"
    return f"process-{user}-{os.getpid()}"


def require_board(repo: Repo) -> None:
    if not repo.board_dir.is_dir():
        raise Refusal(
            f"no Manna board at {repo.board_dir}; Managed Integration dispatches board items, so the canonical checkout needs `agent-do manna init`"
        )


def board_row(repo: Repo, item: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    require_board(repo)
    payload, error = manna_json(["show", item], cwd=repo.canonical_root, env=env)
    issue = (payload or {}).get("issue") if payload else None
    if not isinstance(issue, dict) or not issue.get("id"):
        raise Refusal(f"canonical board at {repo.board_dir}: {error or f'manna show {item} returned no issue'}")
    return issue


def managed_state(repo: Repo, item: str) -> dict[str, Any]:
    """The managed sidecar's recorded attempt and current submission, read directly.

    Missing means unmanaged (attempt 1 by convention); unreadable never does.
    """
    path = repo.board_dir / "managed.json"
    source = str(path)
    try:
        if path.is_symlink():
            raise ValueError("managed metadata is a symlink")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"managed": False, "attempt": 1, "submission_id": None, "required": [], "source": source}
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, dict):
            raise ValueError("invalid managed metadata")
        record = items.get(item)
        if record is None:
            return {"managed": False, "attempt": 1, "submission_id": None, "required": [], "source": source}
        if not isinstance(record, dict) or type(record.get("attempt")) is not int or record["attempt"] < 1:
            raise ValueError("invalid managed attempt")
        submission = record.get("submission") if isinstance(record.get("submission"), dict) else None
        submission_id = None
        if submission and submission.get("attempt") == record["attempt"]:
            submission_id = submission.get("id") or f"legacy:{submission.get('attempt')}:{submission.get('at')}"
        return {
            "managed": True,
            "attempt": record["attempt"],
            "submission_id": submission_id,
            "required": list(record.get("required") or []),
            "source": source,
        }
    except (OSError, ValueError) as exc:
        raise Refusal(f"managed metadata at {source} is unreadable: {exc}")


# ---------------------------------------------------------------------------
# Durable state under the common git dir
# ---------------------------------------------------------------------------


class Store:
    def __init__(self, repo: Repo) -> None:
        self.repo = repo
        self.dir = repo.integration_dir
        self.receipts = self.dir / "receipts"

    def ensure(self) -> None:
        self.receipts.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.dir / name

    def load(self, name: str, default: Any) -> Any:
        path = self.path(name)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return default
        except (OSError, json.JSONDecodeError) as exc:
            raise Refusal(f"{path} is unreadable: {exc}")

    def save(self, name: str, data: Any) -> None:
        self.ensure()
        path = self.path(name)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)

    def remove(self, name: str) -> None:
        try:
            self.path(name).unlink()
        except FileNotFoundError:
            pass

    def event(self, kind: str, **fields: Any) -> None:
        self.ensure()
        row = {"at": now_iso(), "kind": kind, **fields}
        with open(self.path("events.jsonl"), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    def workspaces(self) -> list[dict[str, Any]]:
        data = self.load("workspaces.json", {"version": 1, "workspaces": []})
        return list(data.get("workspaces", []))

    def save_workspaces(self, rows: list[dict[str, Any]]) -> None:
        self.save("workspaces.json", {"version": 1, "workspaces": rows})

    def queue(self) -> list[dict[str, Any]]:
        data = self.load("queue.json", {"version": 1, "entries": []})
        return list(data.get("entries", []))

    def save_queue(self, rows: list[dict[str, Any]]) -> None:
        self.save("queue.json", {"version": 1, "entries": rows})

    def intent(self) -> dict[str, Any] | None:
        return self.load("intent.json", None)

    def lock(self, name: str, *, blocking: bool) -> "Lock":
        self.ensure()
        return Lock(self.path(name), blocking=blocking)


class Lock:
    def __init__(self, path: Path, *, blocking: bool) -> None:
        self.path = path
        self.blocking = blocking
        self.handle: Any = None
        self.held = False

    def __enter__(self) -> "Lock":
        self.handle = open(self.path, "a+", encoding="utf-8")
        flags = fcntl.LOCK_EX | (0 if self.blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(self.handle.fileno(), flags)
            self.held = True
        except OSError:
            self.held = False
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self.handle is not None:
            if self.held:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def latest_workspace(rows: list[dict[str, Any]], item: str) -> dict[str, Any] | None:
    candidates = [row for row in rows if row.get("item") == item]
    if not candidates:
        return None
    return max(candidates, key=lambda row: int(row.get("attempt") or 0))


def find_workspace(rows: list[dict[str, Any]], item: str, attempt: int) -> dict[str, Any] | None:
    for row in rows:
        if row.get("item") == item and int(row.get("attempt") or 0) == attempt:
            return row
    return None


def latest_entry(entries: list[dict[str, Any]], item: str) -> dict[str, Any] | None:
    """The newest entry for an item: the queue is append-only in time order, so
    the last row wins even when two submissions share a `queued_at` second."""
    candidates = [row for row in entries if row.get("item") == item]
    if not candidates:
        return None
    return candidates[-1]


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class Out:
    def __init__(self, json_mode: bool) -> None:
        self.json_mode = json_mode

    def emit(self, payload: dict[str, Any], lines: list[str], code: int = EXIT_OK) -> int:
        if self.json_mode:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for line in lines:
                print(line)
        return code

    def refuse(self, refusal: Refusal) -> int:
        if self.json_mode:
            print(json.dumps({"ok": False, "error": refusal.message, **refusal.extra}, indent=2, sort_keys=True))
        else:
            print(f"Error: {refusal.message}", file=sys.stderr)
        return refusal.code


# ---------------------------------------------------------------------------
# enable / disable / config
# ---------------------------------------------------------------------------


def cmd_enable(repo: Repo, args: argparse.Namespace, out: Out) -> int:
    if not args.target:
        raise Refusal("--target <branch> is required")
    if not args.check:
        raise Refusal("at least one --check <command> is required; reuse the repository's own validation commands")
    if not (args.authorized_by or "").strip():
        raise Refusal("--authorized-by <who> is required: say who approved integration authority for this repository")
    if run(["git", "check-ref-format", "--branch", args.target], cwd=repo.canonical_root).returncode != 0:
        raise Refusal(f"--target is not a valid branch name: {args.target!r}")
    if repo.tip(args.target) is None:
        raise Refusal(f"--target {args.target!r} is not a local branch of this repository")
    for name, value in (("--workspace-root", args.workspace_root), ("--candidate-path", args.candidate_path)):
        if value is not None and not Path(value).is_absolute():
            raise Refusal(f"{name} must be an absolute path")
    if args.candidate_path and Path(args.candidate_path).resolve() == repo.canonical_root:
        raise Refusal("--candidate-path must not be the primary checkout")
    label = best_effort_label(repo)
    config_set(repo, "enabled", "true")
    config_set(repo, "target", args.target)
    config_set(repo, "check", None)
    for command in args.check:
        config_set(repo, "check", command, add=True)
    config_set(repo, "authorized-by", args.authorized_by.strip())
    config_set(repo, "authorized-at", now_iso())
    config_set(repo, "enabled-by", label)
    board = repo.board_id()
    config_set(repo, "board-id", board)
    config_set(repo, "workspace-root", args.workspace_root)
    config_set(repo, "candidate-path", args.candidate_path)
    config_set(repo, "disabled-reason", None)
    config_set(repo, "disabled-at", None)
    config_set(repo, "disabled-by", None)
    cfg = Config(repo)
    Store(repo).event("enabled", by=label, target=args.target, checks=list(args.check), authorized_by=args.authorized_by.strip(), digest=cfg.digest)
    if cfg.state != "enabled":
        raise Refusal("configuration written but invalid: " + "; ".join(cfg.problems), problems=cfg.problems)
    payload = {"ok": True, "config": cfg.as_dict()}
    lines = [
        f"Managed Integration enabled for {repo.canonical_root}",
        f"  policy: {repo.config_path} [agent-do \"integration\"]",
        f"  target: {cfg.target}",
        *[f"  check: {command}" for command in cfg.checks],
        f"  authorized by: {cfg.authorized_by} at {cfg.authorized_at}",
        f"  board: {board or 'no federation id (board absent or pre-federation)'}",
        "Policy lives in the repository's private config, never in a branch; disable with `agent-do git integration disable --reason <text>`.",
    ]
    return out.emit(payload, lines)


def cmd_disable(repo: Repo, args: argparse.Namespace, out: Out) -> int:
    cfg = Config(repo)
    if cfg.state == "off":
        raise Refusal("Managed Integration was never enabled here; nothing to disable", state="off")
    label = best_effort_label(repo)
    config_set(repo, "enabled", "false")
    config_set(repo, "disabled-reason", (args.reason or "").strip() or None)
    config_set(repo, "disabled-at", now_iso())
    config_set(repo, "disabled-by", label)
    after = Config(repo)
    store = Store(repo)
    store.event("disabled", by=label, reason=args.reason, digest=after.digest)
    queued = [row for row in store.queue() if row.get("status") in {"queued", "blocked", "integrating"}]
    payload = {"ok": True, "config": after.as_dict(), "retained": {"queued_entries": len(queued), "workspaces": len(store.workspaces()), "intent": store.intent() is not None}}
    lines = [
        f"Managed Integration disabled for {repo.canonical_root}: no new dispatch, no automatic landing.",
        f"  retained: {len(queued)} pending submission(s), {len(store.workspaces())} workspace(s), landing intent {'present' if store.intent() else 'absent'}",
        "  status and recovery keep working; re-enable with `agent-do git integration enable ...`.",
    ]
    return out.emit(payload, lines)


def cmd_config(repo: Repo, args: argparse.Namespace, out: Out) -> int:
    cfg = Config(repo)
    store = Store(repo)
    payload = {"ok": cfg.state != "invalid", "config": cfg.as_dict(), "canonical_root": str(repo.canonical_root), "via_worktree": repo.via_worktree, "state_dir": str(store.dir), "intent": store.intent()}
    lines = [f"Managed Integration: {cfg.state} ({repo.canonical_root})"]
    if cfg.state == "off":
        lines.append("  no [agent-do \"integration\"] keys in " + str(repo.config_path) + "; the existing workflow is unchanged")
    else:
        lines.append(f"  policy file: {repo.config_path}")
        lines.append(f"  target: {cfg.target}")
        for command in cfg.checks:
            lines.append(f"  check: {command}")
        lines.append(f"  authorized by: {cfg.authorized_by} at {cfg.authorized_at} (enabled by {cfg.enabled_by})")
        if cfg.state == "disabled":
            lines.append(f"  disabled: {cfg.disabled_reason or 'no reason recorded'} at {cfg.disabled_at}")
        lines.append(f"  digest: {cfg.digest}")
    for problem in cfg.problems:
        lines.append(f"  problem: {problem}")
    if store.intent():
        lines.append(f"  landing in flight: entry {store.intent().get('entry')} (run `agent-do git integration recover`)")
    return out.emit(payload, lines, EXIT_OK if cfg.state != "invalid" else EXIT_REFUSED)


# ---------------------------------------------------------------------------
# workspace add / list
# ---------------------------------------------------------------------------


def touch_coord(repo: Repo, where: Path, env: dict[str, str] | None) -> dict[str, Any]:
    payload, error = coord_json(["touch"], cwd=where, env=env)
    if not payload:
        return {"where": str(where), "ok": False, "error": error}
    return {"where": str(where), "ok": True, "agent_id": payload.get("agent_id"), "manna": payload.get("manna")}


def cmd_workspace_add(repo: Repo, args: argparse.Namespace, out: Out) -> int:
    cfg = Config(repo)
    cfg.require_enabled("workspace add")
    item = args.item
    row = board_row(repo, item)
    me = caller_identity(repo)
    if row.get("status") != "in_progress" or not row.get("claimed_by"):
        raise Refusal(f"{item} is {row.get('status')} with claimant {row.get('claimed_by') or 'nobody'}; claim it first (`agent-do manna claim {item}` at {repo.canonical_root})")
    if row.get("claim_token_hash") != me["proof"]:
        raise Refusal(
            f"{item} is claimed by {row.get('claimed_by')} and this session is {me['session']}; the claimant registers its own workspace (proof mismatch, no label matching)",
            code=EXIT_CONTENDED,
        )
    managed = managed_state(repo, item)
    attempt = int(managed["attempt"])
    store = Store(repo)
    target = cfg.target or ""
    with store.lock("state.lock", blocking=True):
        rows = store.workspaces()
        existing = find_workspace(rows, item, attempt)
        previous = latest_workspace(rows, item)
        created = False
        restored = False
        rebound = False
        if existing:
            record = existing
            path = Path(record["path"])
            if not path.exists():
                if repo.resolve(f"refs/heads/{record['branch']}") is None:
                    raise Refusal(f"workspace {record['branch']} for {item} attempt {attempt} is recorded at {path} but neither the directory nor the branch exists; nothing to restore")
                run(["git", "worktree", "prune"], cwd=repo.canonical_root)
                add = run(["git", "worktree", "add", str(path), record["branch"]], cwd=repo.canonical_root)
                if add.returncode != 0:
                    raise Refusal(f"could not restore the workspace worktree at {path}: {(add.stderr or add.stdout).strip()}")
                restored = True
                record.setdefault("history", []).append({"at": now_iso(), "event": "restored", "by": me["session"]})
            if record.get("worker", {}).get("proof") != me["proof"]:
                record.setdefault("history", []).append({"at": now_iso(), "event": "rebound", "from": record.get("worker"), "to": {"label": me["session"], "proof": me["proof"]}})
                record["worker"] = {"label": me["session"], "proof": me["proof"], "bound_at": now_iso(), "claimed_at": row.get("claimed_at")}
                rebound = True
        else:
            branch = f"{BRANCH_PREFIX}{item}-a{attempt}"
            if run(["git", "check-ref-format", "--branch", branch], cwd=repo.canonical_root).returncode != 0:
                raise Refusal(f"derived branch name is invalid: {branch}")
            if repo.resolve(f"refs/heads/{branch}") is not None:
                raise Refusal(f"branch {branch} already exists but no workspace record names it; decide what it is before registering (nothing was deleted or reused)")
            base = repo.tip(target)
            if base is None:
                raise Refusal(f"target branch {target!r} has no commit")
            inherited_from = None
            start = base
            if previous:
                prior_tip = repo.resolve(f"refs/heads/{previous['branch']}")
                if prior_tip:
                    start = prior_tip
                    inherited_from = {"attempt": previous.get("attempt"), "branch": previous.get("branch"), "sha": prior_tip}
            root = Path(cfg.workspace_root) if cfg.workspace_root else repo.canonical_root.parent
            path = Path(args.path).expanduser().resolve() if args.path else root / f"{repo.repo_name}-{item}-a{attempt}"
            if path.exists():
                raise Refusal(f"workspace destination already exists; refusing to overwrite: {path}")
            if path == repo.canonical_root or path.resolve() == (Path(cfg.candidate_path) if cfg.candidate_path else default_candidate_path(repo)).resolve():
                raise Refusal(f"workspace destination collides with the primary checkout or the integrator's candidate tree: {path}")
            git(["branch", branch, start], cwd=repo.canonical_root)
            add = run([str(ROOT / "tools" / "agent-git"), "worktree", "add", branch, "--path", str(path), "--json"], cwd=repo.canonical_root)
            if add.returncode != 0:
                run(["git", "branch", "-D", branch], cwd=repo.canonical_root)
                raise Refusal(f"could not create the workspace worktree: {(add.stderr or add.stdout).strip()}")
            record = {
                "item": item,
                "attempt": attempt,
                "branch": branch,
                "path": str(path),
                "target": target,
                "base_sha": base,
                "start_sha": start,
                "inherited_from": inherited_from,
                "board": {"root": str(repo.canonical_root), "path": str(repo.board_dir), "id": repo.board_id()},
                "managed": managed["managed"],
                "worker": {"label": me["session"], "proof": me["proof"], "bound_at": now_iso(), "claimed_at": row.get("claimed_at")},
                "work_order": {"prompt": row.get("prompt"), "digest": row.get("handoff_digest")},
                "created_at": now_iso(),
                "created_by": me["session"],
                "status": "building",
                "superseded_by": None,
                "history": [],
            }
            if previous:
                previous["superseded_by"] = {"attempt": attempt, "branch": branch}
                previous.setdefault("history", []).append({"at": now_iso(), "event": "superseded", "by_attempt": attempt})
            rows.append(record)
            created = True
        store.save_workspaces(rows)
        store.event("workspace_add", item=item, attempt=attempt, branch=record["branch"], path=record["path"], created=created, restored=restored, rebound=rebound, by=me["session"])
    bindings = [touch_coord(repo, repo.canonical_root, None)]
    if Path(record["path"]).is_dir():
        bindings.append(touch_coord(repo, Path(record["path"]), None))
    payload = {"ok": True, "created": created, "restored": restored, "rebound": rebound, "workspace": record, "coord": bindings, "canonical_root": str(repo.canonical_root), "via_worktree": repo.via_worktree}
    verb = "Created" if created else ("Restored" if restored else ("Rebound" if rebound else "Existing"))
    lines = [
        f"{verb} workspace for {item} attempt {attempt}: {record['path']}",
        f"  branch: {record['branch']} (from {short_hex(record['start_sha'])}{', inherited from attempt ' + str(record['inherited_from']['attempt']) if record.get('inherited_from') else ', the ' + target + ' tip'})",
        f"  bound worker: {record['worker']['label']} (claim proof matched exactly)",
        f"  canonical board: {record['board']['path']}",
        f"  coord binding at the canonical root: {'ok' if bindings[0].get('ok') else 'failed: ' + str(bindings[0].get('error'))}",
        "Next: work inside the workspace, commit with a `Manna: " + item + "` trailer, then `agent-do git integration submit " + item + "`.",
        "Board commands (claim, submit, handoff seal) run against the canonical checkout: " + str(repo.canonical_root),
    ]
    return out.emit(payload, lines)


def cmd_workspace_list(repo: Repo, args: argparse.Namespace, out: Out) -> int:
    store = Store(repo)
    rows = store.workspaces()
    entries = store.queue()
    for row in rows:
        row["exists"] = Path(row.get("path", "")).is_dir()
        row["branch_tip"] = repo.resolve(f"refs/heads/{row.get('branch')}")
        latest = latest_entry([e for e in entries if e.get("attempt") == row.get("attempt")], row.get("item", ""))
        row["latest_entry"] = {"id": latest.get("id"), "status": latest.get("status"), "reason": (latest.get("result") or {}).get("reason")} if latest else None
    payload = {"ok": True, "count": len(rows), "workspaces": rows}
    lines = [f"{len(rows)} workspace(s) registered under {store.dir}"]
    for row in rows:
        latest = row.get("latest_entry") or {}
        lines.append(
            f"  {row.get('item')} a{row.get('attempt')} {row.get('branch')} -> {row.get('path')} [{'present' if row['exists'] else 'missing'}] worker {row.get('worker', {}).get('label')} "
            f"{'entry ' + str(latest.get('id')) + ' ' + str(latest.get('status')) if latest else 'no submission'}"
        )
    return out.emit(payload, lines)


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------


def board_paths_in(paths: list[str]) -> list[str]:
    return [path for path in paths if path.startswith(BOARD_OWNED_PREFIXES)]


def cmd_submit(repo: Repo, args: argparse.Namespace, out: Out) -> int:
    cfg = Config(repo)
    cfg.require_enabled("submit")
    item = args.item
    row = board_row(repo, item)
    me = caller_identity(repo)
    if row.get("status") != "in_progress" or not row.get("claimed_by"):
        raise Refusal(f"{item} is {row.get('status')} with claimant {row.get('claimed_by') or 'nobody'}; only the live claimant submits")
    if row.get("claim_token_hash") != me["proof"]:
        raise Refusal(f"{item} is claimed by {row.get('claimed_by')}; this session ({me['session']}) does not hold that claim", code=EXIT_CONTENDED)
    managed = managed_state(repo, item)
    attempt = int(managed["attempt"])
    store = Store(repo)
    target = cfg.target or ""
    with store.lock("state.lock", blocking=True):
        rows = store.workspaces()
        record = find_workspace(rows, item, attempt)
        if record is None:
            raise Refusal(f"no workspace registered for {item} attempt {attempt}; run `agent-do git integration workspace add {item}` first")
        intent = store.intent()
        if intent and intent.get("item") == item:
            raise Refusal(f"a landing for {item} (entry {intent.get('entry')}) is in flight; run `agent-do git integration recover` before submitting again")
        branch = record["branch"]
        source = repo.resolve(f"refs/heads/{branch}")
        if source is None:
            raise Refusal(f"workspace branch {branch} no longer exists; nothing to submit")
        base = repo.tip(target)
        if base is None:
            raise Refusal(f"target branch {target!r} has no commit")
        merge_base = repo.merge_base(base, source)
        if merge_base == source or source == base:
            raise Refusal(f"nothing to integrate: {branch} has no commits beyond {target} ({short_hex(base)})")
        changed = repo.changed_paths(merge_base or base, source)
        owned = board_paths_in(changed)
        if owned:
            raise Refusal(
                "the submission changes board-owned paths, which are never merged from a worker branch into canonical state: " + ", ".join(owned)
                + ". Board edits (claims, seals, handoffs) belong to the canonical checkout; remove them from the branch and resubmit.",
                board_paths=owned,
            )
        commits: list[dict[str, str]] = []
        for line in git(["log", "--format=%H%x1f%s%x1f%(trailers:key=Manna,valueonly)", f"{merge_base or base}..{source}"], cwd=repo.canonical_root).splitlines():
            parts = line.split("\x1f")
            if len(parts) >= 2:
                commits.append({"sha": parts[0], "subject": parts[1], "trailer": (parts[2].strip() if len(parts) > 2 else "")})
        trailer_commits = [commit["sha"] for commit in commits if commit["trailer"] == item]
        entry_id = new_id("int-", item, source)
        receipts = store.receipts / entry_id
        receipts.mkdir(parents=True, exist_ok=True)
        if args.report:
            try:
                report_text = Path(args.report).read_text(encoding="utf-8")
            except OSError as exc:
                raise Refusal(f"cannot read --report {args.report}: {exc}")
            if not report_text.strip():
                raise Refusal("the report is empty; a submission carries what was done, the receipts, and what was left")
        else:
            evidence_lines = [f"- {line}" for line in (args.evidence or [])] or ["- (none stated; the integrator's checks are the receipts)"]
            report_text = "\n".join(
                [
                    f"# Submission {entry_id} for {item}",
                    "",
                    f"Source: {source} on {branch}",
                    f"Base ({target}): {base}",
                    f"Attempt: {attempt}",
                    "",
                    "Commits:",
                    *[f"- {commit['sha']} {commit['subject']}" for commit in commits],
                    "",
                    "Worker evidence:",
                    *evidence_lines,
                    "",
                ]
            )
        report_path = receipts / "report.md"
        report_path.write_text(report_text, encoding="utf-8")
        manna_submission: dict[str, Any] | None = None
        submission_id: str
        if managed["managed"]:
            payload, error = manna_json(["submit", item, "--report", str(report_path), "--revision", source], cwd=repo.canonical_root)
            sub = ((payload or {}).get("managed") or {}).get("submission") if payload else None
            if not payload or not isinstance(sub, dict) or not sub.get("id"):
                raise Refusal(f"manna submit refused: {error or 'no submission id returned'}")
            submission_id = str(sub["id"])
            manna_submission = {"id": submission_id, "attempt": sub.get("attempt"), "at": sub.get("at"), "revision": sub.get("revision")}
            if int(sub.get("attempt") or attempt) != attempt:
                raise Refusal(f"manna recorded attempt {sub.get('attempt')} but this workspace is attempt {attempt}; register the current attempt's workspace first")
        else:
            submission_id = new_id("isub-", item, source)
        git(["update-ref", f"{SUBMISSION_REF_PREFIX}{entry_id}", source], cwd=repo.canonical_root)
        entries = store.queue()
        superseded: list[str] = []
        for other in entries:
            if other.get("item") == item and other.get("attempt") == attempt and other.get("status") in {"queued", "blocked", "integrating"}:
                other["status"] = "superseded"
                other["superseded_by"] = entry_id
                other.setdefault("history", []).append({"at": now_iso(), "event": "superseded", "by": entry_id})
                superseded.append(str(other.get("id")))
        entry = {
            "id": entry_id,
            "item": item,
            "attempt": attempt,
            "submission": {"id": submission_id, "source": "manna" if managed["managed"] else "local", "manna": manna_submission},
            "branch": branch,
            "source_sha": source,
            "base_sha": base,
            "target": target,
            "worker": {"label": me["session"], "proof": me["proof"]},
            "work_order": {"prompt": row.get("prompt"), "digest": row.get("handoff_digest")},
            "commits": commits,
            "trailer_commits": trailer_commits,
            "evidence": list(args.evidence or []),
            "report": str(report_path),
            "receipts": str(receipts),
            "submission_ref": f"{SUBMISSION_REF_PREFIX}{entry_id}",
            "queued_at": now_iso(),
            "queued_by": me["session"],
            "config_digest": cfg.digest,
            "status": "queued",
            "result": None,
            "rebuilds": [],
            "routing": [],
            "history": [{"at": now_iso(), "event": "queued"}],
        }
        entries.append(entry)
        store.save_queue(entries)
        record["status"] = "queued"
        record["latest_entry"] = entry_id
        store.save_workspaces(rows)
        store.event("submit", item=item, attempt=attempt, entry=entry_id, source=source, base=base, submission=submission_id, superseded=superseded, by=me["session"])
    touch_coord(repo, repo.canonical_root, None)
    payload = {"ok": True, "entry": entry, "superseded": superseded, "managed": managed["managed"]}
    lines = [
        f"Queued {entry_id} for {item} attempt {attempt}: {short_hex(source)} on {branch} against {target} at {short_hex(base)}",
        f"  submission: {submission_id} ({'manna submit recorded it; the item stays in_progress' if managed['managed'] else 'local id; the item is not under managed closure'})",
        f"  commits: {len(commits)} ({len(trailer_commits)} carry `Manna: {item}`)",
        f"  report: {report_path}",
        *([f"  superseded earlier submission(s): {', '.join(superseded)}"] if superseded else []),
        "Next: the integrator lands it with `agent-do git integration run`; a commit saves progress, a submission requests integration, `manna done` records closure.",
    ]
    return out.emit(payload, lines)


# ---------------------------------------------------------------------------
# The integrator
# ---------------------------------------------------------------------------


class Integrator:
    def __init__(self, repo: Repo, cfg: Config, store: Store, out: Out, *, once: bool = False) -> None:
        self.repo = repo
        self.cfg = cfg
        self.store = store
        self.out = out
        self.once = once
        self.label = best_effort_label(repo)
        self.candidate_path: Path | None = None

    # -- candidate tree -----------------------------------------------------

    def configured_candidate_path(self) -> Path:
        return Path(self.cfg.candidate_path) if self.cfg.candidate_path else default_candidate_path(self.repo)

    def candidate_marker(self, path: Path) -> Path | None:
        probe = run(["git", "rev-parse", "--path-format=absolute", "--git-dir"], cwd=path)
        if probe.returncode != 0:
            return None
        return Path(probe.stdout.strip()) / CANDIDATE_MARKER

    def ensure_candidate(self) -> Path:
        """The integrator's own detached worktree. An existing tree is adopted only
        when it carries this integrator's ownership marker; anything else at the
        candidate path is left exactly as it is and the run refuses."""
        path = self.configured_candidate_path()
        registered = {Path(item["path"]).resolve(): item for item in self.repo.worktrees()}
        base = self.repo.tip(self.cfg.target or "")
        if base is None:
            raise Refusal(f"target branch {self.cfg.target!r} has no commit")
        if path.exists():
            item = registered.get(path.resolve())
            if item is None:
                raise Refusal(f"candidate path exists but is not a worktree of this repository; refusing to touch it: {path}")
            if item.get("branch"):
                raise Refusal(f"candidate worktree at {path} has branch {item['branch']} checked out; the integrator's tree must be detached")
            marker = self.candidate_marker(path)
            if marker is None or not marker.is_file():
                raise Refusal(
                    f"a detached worktree exists at {path} that this integrator did not create (no {CANDIDATE_MARKER} marker in its git dir); "
                    "refusing to reset or clean it. Remove it yourself (`git worktree remove <path>`) or set `candidate-path` to a path of the integrator's own.",
                    candidate_path=str(path),
                )
        else:
            if path.resolve() in registered:
                run(["git", "worktree", "prune"], cwd=self.repo.canonical_root)
            add = run(["git", "worktree", "add", "--detach", str(path), base], cwd=self.repo.canonical_root)
            if add.returncode != 0:
                raise Refusal(f"could not create the candidate worktree at {path}: {(add.stderr or add.stdout).strip()}")
            marker = self.candidate_marker(path)
            if marker is None:
                raise Refusal(f"created the candidate worktree at {path} but cannot resolve its git dir to record ownership")
            created = {"created_at": now_iso(), "by": self.label, "path": str(path), "common_dir": str(self.repo.common_dir)}
            marker.write_text(json.dumps(created, sort_keys=True) + "\n", encoding="utf-8")
            self.store.save("candidate.json", {"version": 1, "marker": str(marker), **created})
            self.store.event("candidate_created", path=str(path), marker=str(marker), by=self.label)
        self.candidate_path = path
        return path

    def verify_candidate(self, candidate: str, receipts: Path) -> dict[str, Any]:
        """The tree the checks ran in must still be the candidate commit itself:
        HEAD at it and detached, index and tracked files identical to it. A check
        that repaired a tracked file, staged one, or committed has validated
        something other than what would land. Untracked files are build output
        outside the landed tree: reported, allowed."""
        path = self.candidate_path
        assert path is not None
        head = run(["git", "rev-parse", "--verify", "HEAD"], cwd=path).stdout.strip()
        detached = run(["git", "symbolic-ref", "-q", "HEAD"], cwd=path).returncode != 0
        run(["git", "update-index", "-q", "--refresh"], cwd=path)
        # Porcelain `git diff` compares content, not stat: a touched file whose
        # bytes equal the candidate's is clean, and a staged blob that differs
        # from both the candidate and the working file is an index change only.
        index_clean = run(["git", "diff", "--cached", "--quiet", candidate, "--"], cwd=path).returncode == 0
        tree_clean = run(["git", "diff", "--quiet", candidate, "--"], cwd=path).returncode == 0
        listed = run(["git", "diff", "--name-status", candidate, "--"], cwd=path).stdout + run(["git", "diff", "--cached", "--name-status", candidate, "--"], cwd=path).stdout
        changed = sorted({line.strip() for line in listed.splitlines() if line.strip()})
        untracked = [line[3:] for line in run(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=path).stdout.splitlines() if line.startswith("?? ")]
        ok = head == candidate and detached and index_clean and tree_clean
        record: dict[str, Any] = {
            "ok": ok,
            "candidate": candidate,
            "head": head,
            "detached": detached,
            "index_clean": index_clean,
            "tree_clean": tree_clean,
            "changed": changed,
            "untracked": untracked,
            "verified_at": now_iso(),
        }
        if not ok:
            drift = receipts / "candidate-drift.patch"
            drift.write_text(
                f"# candidate {candidate}\n"
                f"# HEAD now {head} ({'detached' if detached else 'ATTACHED to a branch'})\n"
                f"# index {'clean' if index_clean else 'CHANGED'}, tracked files {'clean' if tree_clean else 'CHANGED'}\n\n"
                "# --- working tree vs the candidate ---\n" + run(["git", "diff", candidate, "--"], cwd=path).stdout
                + "\n# --- index vs the candidate ---\n" + run(["git", "diff", "--cached", candidate, "--"], cwd=path).stdout,
                encoding="utf-8",
            )
            record["patch"] = str(drift)
        return record

    def check_env(self) -> tuple[dict[str, str], list[str]]:
        env: dict[str, str] = {}
        withheld: list[str] = []
        for name, value in os.environ.items():
            upper = name.upper()
            if name in IDENTITY_ENV or any(marker in upper for marker in SECRET_NAME_MARKERS):
                withheld.append(name)
                continue
            env[name] = value
        env["MANNA_OPERATOR"] = "0"
        return env, sorted(withheld)

    def reset_candidate(self, sha: str) -> None:
        """Put the owned candidate tree exactly at `sha`: abandon any merge, discard
        whatever the last checks left in the index and tracked files (a check may
        dirty the tree; the previous landing refused it, the next build must not
        trip over it), detach at the commit, and drop untracked files."""
        path = self.candidate_path
        assert path is not None
        run(["git", "-C", str(path), "merge", "--abort"], cwd=path)
        for args in (["reset", "-q", "--hard"], ["checkout", "-q", "-f", "--detach", sha], ["reset", "-q", "--hard"], ["clean", "-q", "-fd"]):
            proc = run(["git", "-C", str(path), *args], cwd=path)
            if proc.returncode != 0:
                raise Refusal(f"candidate tree at {path}: git {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()}")

    # -- persistence helpers ------------------------------------------------

    def save_entry(self, entry: dict[str, Any]) -> None:
        with self.store.lock("state.lock", blocking=True):
            entries = self.store.queue()
            for index, other in enumerate(entries):
                if other.get("id") == entry.get("id"):
                    entries[index] = entry
                    break
            else:
                entries.append(entry)
            self.store.save_queue(entries)
            rows = self.store.workspaces()
            record = find_workspace(rows, entry["item"], int(entry["attempt"]))
            if record is not None and record.get("latest_entry") == entry.get("id"):
                record["status"] = entry.get("status")
                self.store.save_workspaces(rows)

    def receipts_for(self, entry: dict[str, Any]) -> Path:
        path = Path(entry.get("receipts") or (self.store.receipts / entry["id"]))
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_summary(self, entry: dict[str, Any], state: str, reason: str | None, detail: list[str]) -> Path:
        receipts = self.receipts_for(entry)
        result = entry.get("result") or {}
        lines = [
            f"# Integration {entry['id']}: {state}" + (f" ({reason})" if reason else ""),
            "",
            f"- item: {entry['item']} attempt {entry['attempt']}",
            f"- branch: {entry['branch']}",
            f"- submission: {entry['submission']['id']} ({entry['submission']['source']})",
            f"- source: {entry['source_sha']} (pinned at {entry['submission_ref']})",
            f"- target: {entry['target']} at {result.get('base_sha') or entry['base_sha']}",
            f"- candidate: {result.get('candidate_sha') or 'none'}" + (f" (pinned at {result.get('candidate_ref')})" if result.get("candidate_ref") else ""),
            f"- integrated: {result.get('integrated_sha') or 'not landed'}",
            f"- policy: tested under {result.get('config_digest') or result.get('policy_digest') or 'no checks run'}"
            + (f", in force at landing {result.get('policy_digest_at_landing')}" if result.get("policy_digest_at_landing") else ""),
            "- candidate tree after the checks: "
            + (
                ("verified unchanged" if (result.get("candidate_integrity") or {}).get("ok") else "CHANGED: " + ", ".join((result.get("candidate_integrity") or {}).get("changed") or ["HEAD or index"]))
                if result.get("candidate_integrity")
                else "not verified (no checks ran)"
            ),
            f"- recorded at: {now_iso()} by {self.label}",
            "",
        ]
        checks = result.get("checks") or []
        if checks:
            lines.append("Checks:")
            for check in checks:
                lines.append(f"- [{'ok' if check.get('ok') else 'FAILED exit ' + str(check.get('exit'))}] {check['command']} -> {check['log']}")
            lines.append("")
        if detail:
            lines.append("Detail:")
            lines.extend(f"- {line}" for line in detail)
            lines.append("")
        lines.append("Next action: " + next_action_for(entry))
        path = receipts / "summary.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    # -- routing ------------------------------------------------------------

    def route(self, entry: dict[str, Any], kind: str, summary: Path, note: str) -> dict[str, Any]:
        args = ["drop", "add", str(summary), "--for-item", entry["item"], "--note", note]
        if kind == "action":
            args.append("--action")
        payload, error = coord_json(args, cwd=self.repo.canonical_root)
        drop = (payload or {}).get("drop") if payload else None
        record = {
            "at": now_iso(),
            "kind": kind,
            "store": str(self.repo.common_dir / "agent-do" / "coord"),
            "state": "recorded" if drop else "failed",
            "drop_id": (drop or {}).get("id"),
            "delivery": (drop or {}).get("delivery"),
            "error": None if drop else error,
            "path": str(summary),
        }
        entry.setdefault("routing", []).append(record)
        return record

    # -- outcomes -----------------------------------------------------------

    def block(self, entry: dict[str, Any], reason: str, detail: list[str], *, result: dict[str, Any] | None = None) -> dict[str, Any]:
        entry["status"] = "blocked"
        merged = dict(entry.get("result") or {})
        merged.update(result or {})
        merged["reason"] = reason
        merged["detail"] = detail
        merged["retryable"] = reason in RETRYABLE_REASONS
        merged["blocked_at"] = now_iso()
        entry["result"] = merged
        entry.setdefault("history", []).append({"at": now_iso(), "event": "blocked", "reason": reason})
        summary = self.write_summary(entry, "blocked", reason, detail)
        routing: dict[str, Any] | None = None
        if reason in WORKER_REASONS:
            routing = self.route(entry, "action", summary, f"integration of {entry['item']} blocked: {reason}; see {summary.name} for the receipts and the next action")
        self.save_entry(entry)
        self.store.event("blocked", entry=entry["id"], item=entry["item"], reason=reason, retryable=merged["retryable"], routing=routing)
        return {"entry": entry["id"], "item": entry["item"], "outcome": "blocked", "reason": reason, "retryable": merged["retryable"], "summary": str(summary), "routing": routing}

    def complete(self, entry: dict[str, Any], candidate: str, base: str, via: str, *, recovered: bool = False, tested_digest: str | None = None) -> dict[str, Any]:
        """Record a landing whose ref has moved. Order matters for recovery: the
        queue row first (the landing is then durable), the receipt, the routing
        record, the audit line, and the intent last, so an interruption anywhere
        in the tail is finished by `recover`, never replayed as a landing."""
        already_recorded = entry.get("status") == "landed"
        if already_recorded and self.store.intent() is None:
            return {"entry": entry["id"], "item": entry["item"], "outcome": "landed", "already": True}
        live = Config(self.repo)
        if not already_recorded:
            target_after = self.repo.tip(entry["target"])
            result = dict(entry.get("result") or {})
            tested = tested_digest or result.get("policy_digest") or self.cfg.digest
            result.update(
                {
                    "reason": None,
                    "candidate_sha": candidate,
                    "candidate_ref": f"{CANDIDATE_REF_PREFIX}{entry['id']}",
                    "integrated_sha": candidate,
                    "base_sha": base,
                    "target_before": base,
                    "target_after": target_after,
                    "fast_forward": candidate == entry["source_sha"],
                    "landed_at": now_iso(),
                    "landed_via": via,
                    "landed_by": self.label,
                    "recovered": recovered,
                    "config_digest": tested,
                    "policy_digest_at_landing": live.digest,
                    "policy_changed_since_test": live.digest != tested,
                    "provenance": {"submission_sha": entry["source_sha"], "integrated_sha": candidate, "submission_id": entry["submission"]["id"], "attempt": entry["attempt"]},
                }
            )
            entry["result"] = result
            entry["status"] = "landed"
            entry.setdefault("history", []).append({"at": now_iso(), "event": "landed", "via": via, "recovered": recovered})
            self.save_entry(entry)
        result = entry.get("result") or {}
        fault("after_landed_row")
        detail = [f"landed via {via}", f"target {entry['target']}: {short_hex(base)} -> {short_hex(candidate)}"]
        if result.get("policy_changed_since_test"):
            detail.append(f"the policy changed after this candidate was validated (tested {result.get('config_digest')}, now {result.get('policy_digest_at_landing')}); the ref had already moved, so the landing is recorded as it happened")
        summary = self.write_summary(entry, "landed", None, detail)
        recorded = [row for row in entry.get("routing") or [] if row.get("kind") == "info" and row.get("state") == "recorded"]
        if recorded:
            routing = recorded[-1]
        else:
            routing = self.route(entry, "info", summary, f"{entry['item']} landed on {entry['target']} as {short_hex(candidate)} (submission {short_hex(entry['source_sha'])}); receipts in {summary.parent}")
            self.save_entry(entry)
        self.store.event("landed" if not already_recorded else "landed_tail_recovered", entry=entry["id"], item=entry["item"], integrated=candidate, base=base, via=via, recovered=recovered, routing=routing)
        self.store.remove("intent.json")
        return {"entry": entry["id"], "item": entry["item"], "outcome": "landed", "integrated_sha": candidate, "fast_forward": result.get("fast_forward"), "via": via, "summary": str(summary), "routing": routing, "recovered": recovered, "tail_recovered": already_recorded}

    # -- landing ------------------------------------------------------------

    def land(self, entry: dict[str, Any], candidate: str, base: str, *, tested_digest: str) -> tuple[str, str]:
        """Advance the target from `base` to `candidate`. Returns (state, detail).

        The write-ahead intent carries the tested policy digest, the worker
        binding, the attempt, the submission id, the check results and the
        candidate-tree verification, so recovery before the ref update can
        re-verify all of it instead of trusting a candidate that was validated
        under a policy or an assignment that no longer holds."""
        target = entry["target"]
        holder = self.repo.checkout_holding(target)
        result = entry.get("result") or {}
        self.store.save(
            "intent.json",
            {
                "version": 2,
                "entry": entry["id"],
                "item": entry["item"],
                "attempt": entry["attempt"],
                "submission_id": entry["submission"]["id"],
                "source_sha": entry["source_sha"],
                "candidate": candidate,
                "base": base,
                "target": target,
                "holder": str(holder) if holder else None,
                "config_digest": tested_digest,
                "worker": entry.get("worker"),
                "checks": result.get("checks"),
                "candidate_integrity": result.get("candidate_integrity"),
                "written_at": now_iso(),
                "by": self.label,
            },
        )
        self.store.event("landing_intent", entry=entry["id"], candidate=candidate, base=base, target=target, holder=str(holder) if holder else None, config_digest=tested_digest)
        fault("after_intent")
        if holder is not None:
            proc = run(["git", *INTEGRATOR_IDENT, "merge", "--ff-only", "--no-edit", candidate], cwd=holder)
            if proc.returncode != 0:
                self.store.remove("intent.json")
                tip = self.repo.tip(target)
                if tip != base:
                    return "moved", f"{target} moved to {tip} while landing"
                return "busy", f"the checkout holding {target} at {holder} refused the fast-forward: {(proc.stderr or proc.stdout).strip()}"
            via = f"git merge --ff-only in the checkout holding {target} ({holder}); dirty files there were preserved by git's own overwrite guard"
        else:
            proc = run(["git", "update-ref", "-m", f"integrate {entry['item']} {entry['id']}", f"refs/heads/{target}", candidate, base], cwd=self.repo.canonical_root)
            if proc.returncode != 0:
                self.store.remove("intent.json")
                return "moved", f"compare-and-swap on refs/heads/{target} refused: {(proc.stderr or proc.stdout).strip()}"
            via = f"git update-ref compare-and-swap on refs/heads/{target} (no checkout holds it)"
        fault("after_ref_update")
        return "landed", via

    # -- staleness ----------------------------------------------------------

    def staleness(self, entry: dict[str, Any]) -> tuple[str, list[str]] | None:
        try:
            row = board_row(self.repo, entry["item"])
        except Refusal as refusal:
            return "stale_submission", [f"canonical board unreadable: {refusal.message}"]
        if row.get("status") == "done":
            return "item_closed", [f"{entry['item']} is done on the canonical board; a closed item is not landed automatically"]
        if row.get("claim_token_hash") != entry["worker"]["proof"]:
            return "reassigned", [f"the claim moved from {entry['worker']['label']} to {row.get('claimed_by') or 'nobody'}; the submission came from a superseded claim and is not forwarded"]
        managed = managed_state(self.repo, entry["item"])
        if managed["managed"]:
            if int(managed["attempt"]) != int(entry["attempt"]):
                return "stale_submission", [f"managed attempt is now {managed['attempt']}, this submission was attempt {entry['attempt']}"]
            if managed["submission_id"] != entry["submission"]["id"]:
                return "stale_submission", [f"the managed record's current submission is {managed['submission_id']}, not {entry['submission']['id']}"]
        return None

    # -- one entry ----------------------------------------------------------

    def policy_reason(self, cfg: Config) -> tuple[str, list[str]]:
        reason = "config_disabled" if cfg.state == "disabled" else "config_invalid"
        return reason, ["the policy is " + cfg.state + ": " + (cfg.disabled_reason or "; ".join(cfg.problems) or "not enabled")]

    def integrate(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Build, validate and land one entry. Invariants the fixtures hold:

        - the checks run on the candidate commit's own tree, and the tree is
          verified unchanged (HEAD, index, tracked files) before anything lands;
        - the policy in force when the ref moves is the policy the checks ran
          under (digest equality); a policy that changed during validation is
          adopted once and the candidate revalidated under it; one that moves
          again during that revalidation blocks (`config_changed`, retryable);
        - the assignment (claim proof, managed attempt and submission, item not
          closed) is re-read immediately before the ref update, not only before
          the checks;
        - the target must still equal the tested base, else rebuild.
        """
        repo = self.repo
        target = entry["target"]
        self.cfg = Config(repo)
        if self.cfg.state != "enabled":
            reason, detail = self.policy_reason(self.cfg)
            return self.block(entry, reason, detail)
        if target != self.cfg.target:
            return self.block(entry, "config_changed", [f"submitted against {target}; the policy now targets {self.cfg.target}"])
        if self.candidate_path is None or self.candidate_path != self.configured_candidate_path():
            self.ensure_candidate()
        entry["status"] = "integrating"
        entry.setdefault("history", []).append({"at": now_iso(), "event": "integrating", "by": self.label})
        self.save_entry(entry)
        stale = self.staleness(entry)
        if stale:
            return self.block(entry, stale[0], stale[1])
        source = entry["source_sha"]
        if repo.resolve(source) is None:
            return self.block(entry, "stale_submission", [f"the submitted commit {source} is no longer in this repository"])
        receipts = self.receipts_for(entry)
        rebuilds: list[dict[str, Any]] = list(entry.get("rebuilds") or [])
        revalidations: list[dict[str, Any]] = list(entry.get("revalidations") or [])
        adopted_digest: str | None = None
        validation_pass = 0
        while True:
            base = repo.tip(target)
            if base is None:
                return self.block(entry, "config_invalid", [f"target {target} has no commit"])
            if repo.is_ancestor(source, base):
                entry["result"] = dict(entry.get("result") or {}, candidate_sha=source, base_sha=base, checks=[], policy_digest=self.cfg.digest)
                git(["update-ref", f"{CANDIDATE_REF_PREFIX}{entry['id']}", source], cwd=repo.canonical_root)
                return self.complete(entry, source, base, f"already contained in {target} at {short_hex(base)}; nothing moved", tested_digest=self.cfg.digest)
            self.reset_candidate(base)
            path = self.candidate_path
            assert path is not None
            if repo.is_ancestor(base, source):
                self.reset_candidate(source)
                candidate = source
                built = "fast-forward"
            else:
                message = f"integrate {entry['item']}: {short_hex(source)} onto {target} ({short_hex(base)})\n\nSubmission: {entry['submission']['id']}\nSource: {source}\nEntry: {entry['id']}\nManna: {entry['item']}"
                merge = run(["git", *INTEGRATOR_IDENT, "merge", "--no-ff", "-m", message, source], cwd=path)
                if merge.returncode != 0:
                    unmerged = [line for line in run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=path).stdout.splitlines() if line]
                    run(["git", "merge", "--abort"], cwd=path)
                    detail = [f"merge of {short_hex(source)} onto {target} at {short_hex(base)} conflicts in: " + (", ".join(unmerged) or "(see git output)")]
                    detail.append("resolve by merging " + target + " into " + entry["branch"] + " in the workspace, then resubmit")
                    return self.block(entry, "conflict", detail, result={"base_sha": base, "conflicts": unmerged, "candidate_sha": None})
                candidate = git(["rev-parse", "HEAD"], cwd=path)
                built = "merge"
            git(["update-ref", f"{CANDIDATE_REF_PREFIX}{entry['id']}", candidate], cwd=repo.canonical_root)
            owned = board_paths_in(repo.changed_paths(base, candidate))
            if owned:
                return self.block(entry, "board_paths", ["the combined result changes board-owned paths: " + ", ".join(owned)], result={"base_sha": base, "candidate_sha": candidate, "candidate_ref": f"{CANDIDATE_REF_PREFIX}{entry['id']}"})
            tested = self.cfg
            validation_pass += 1
            checks = self.run_checks(entry, candidate, receipts, validation_pass=validation_pass)
            integrity = self.verify_candidate(candidate, receipts)
            entry["result"] = dict(
                entry.get("result") or {},
                base_sha=base,
                candidate_sha=candidate,
                candidate_ref=f"{CANDIDATE_REF_PREFIX}{entry['id']}",
                built=built,
                checks=checks,
                candidate_integrity=integrity,
                policy_digest=tested.digest,
                validation_passes=validation_pass,
            )
            if not integrity["ok"]:
                detail = ["the checks changed the candidate tree, so what they validated is not what would land:"]
                if integrity["head"] != candidate:
                    detail.append(f"HEAD moved from {short_hex(candidate)} to {short_hex(integrity['head'])}")
                if not integrity["detached"]:
                    detail.append("the candidate worktree now has a branch checked out")
                if not integrity["index_clean"]:
                    detail.append("the index differs from the candidate commit")
                if not integrity["tree_clean"]:
                    detail.append("tracked files differ from the candidate commit")
                detail.extend(f"changed: {line}" for line in integrity["changed"])
                if integrity.get("patch"):
                    detail.append(f"diff of the tree the checks left behind: {integrity['patch']}")
                detail.append("commit what the checks generate (or fix the check command with the operator) and resubmit; the original candidate stays pinned and untouched")
                return self.block(entry, "candidate_changed", detail)
            failed = [check for check in checks if not check["ok"]]
            if failed:
                return self.block(entry, "checks_failed", [f"{check['command']} exited {check['exit']}; log: {check['log']}" for check in failed])
            live = Config(repo)
            if live.state != "enabled":
                reason, detail = self.policy_reason(live)
                return self.block(entry, reason, ["the policy changed before landing"] + detail)
            if live.target != target:
                return self.block(entry, "config_changed", [f"the policy now targets {live.target}, not {target}"])
            if live.digest != tested.digest:
                revalidations.append({"at": now_iso(), "tested_digest": tested.digest, "live_digest": live.digest, "candidate": candidate, "base": base, "checks": checks, "validation_pass": validation_pass})
                entry["revalidations"] = revalidations
                self.store.event("policy_changed_during_validation", entry=entry["id"], tested_digest=tested.digest, live_digest=live.digest, validation_pass=validation_pass)
                if adopted_digest is not None:
                    return self.block(
                        entry,
                        "config_changed",
                        [
                            f"the policy changed while it was being validated, twice in one run: tested {short_hex(tested.digest.split(':')[-1])} after adopting {short_hex(adopted_digest.split(':')[-1])}, and it now reads {short_hex(live.digest.split(':')[-1])}",
                            "a policy that moves during its own validation is not trusted as integration authority; settle the policy (`agent-do git integration config`) and run the integrator again",
                        ],
                    )
                adopted_digest = live.digest
                self.cfg = live
                if self.candidate_path != self.configured_candidate_path():
                    self.ensure_candidate()
                continue
            stale = self.staleness(entry)
            if stale:
                return self.block(entry, stale[0], stale[1] + ["found after the checks, immediately before the ref update; nothing landed"])
            tip = repo.tip(target)
            if tip != base:
                rebuilds.append({"at": now_iso(), "tested_base": base, "target_now": tip, "candidate": candidate})
                entry["rebuilds"] = rebuilds
                self.store.event("rebuild", entry=entry["id"], tested_base=base, target_now=tip)
                continue
            state, detail = self.land(entry, candidate, base, tested_digest=tested.digest)
            if state == "landed":
                return self.complete(entry, candidate, base, detail, tested_digest=tested.digest)
            if state == "moved":
                rebuilds.append({"at": now_iso(), "tested_base": base, "target_now": repo.tip(target), "candidate": candidate, "note": detail})
                entry["rebuilds"] = rebuilds
                self.store.event("rebuild", entry=entry["id"], tested_base=base, note=detail)
                continue
            return self.block(entry, "target_checkout_busy", [detail, "nothing was changed in that checkout; clean it (or commit) and run the integrator again"])

    def run_checks(self, entry: dict[str, Any], candidate: str, receipts: Path, *, validation_pass: int = 1) -> list[dict[str, Any]]:
        path = self.candidate_path
        assert path is not None
        env, withheld = self.check_env()
        env.update(
            {
                "AGENT_GIT_INTEGRATION": "1",
                "AGENT_GIT_INTEGRATION_ITEM": entry["item"],
                "AGENT_GIT_INTEGRATION_ENTRY": entry["id"],
                "AGENT_GIT_INTEGRATION_CANDIDATE": candidate,
                "AGENT_GIT_INTEGRATION_POLICY": self.cfg.digest,
            }
        )
        results: list[dict[str, Any]] = []
        for number, command in enumerate(self.cfg.checks, start=1):
            log = receipts / (f"check-{number}.log" if validation_pass == 1 else f"check-{number}.pass{validation_pass}.log")
            with open(log, "w", encoding="utf-8") as handle:
                handle.write(f"$ {command}\n(cwd {path}, candidate {candidate}, policy {self.cfg.digest}, validation pass {validation_pass})\n")
                handle.write(f"(withheld from the environment: {', '.join(withheld) if withheld else 'nothing'})\n\n")
                handle.flush()
                proc = subprocess.run(command, shell=True, cwd=str(path), env=env, stdout=handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, check=False)
            results.append({"n": number, "command": command, "exit": proc.returncode, "ok": proc.returncode == 0, "log": str(log), "pass": validation_pass})
            if proc.returncode != 0:
                break
        return results

    # -- recovery -----------------------------------------------------------

    def recover(self) -> list[dict[str, Any]]:
        """Settle an interrupted landing. A ref that already moved gets its record
        finished (never a second landing). A ref that did not move is re-landed
        only when the target, the policy digest and the assignment are exactly
        what the candidate was validated under; otherwise the intent is voided
        and the submission requeued (policy) or blocked (assignment)."""
        outcomes: list[dict[str, Any]] = []
        intent = self.store.intent()
        if intent:
            entries = self.store.queue()
            entry = next((row for row in entries if row.get("id") == intent.get("entry")), None)
            if entry is None:
                self.store.remove("intent.json")
                self.store.event("intent_voided", entry=intent.get("entry"), reason="entry missing from the queue")
                outcomes.append({"entry": intent.get("entry"), "outcome": "voided", "reason": "entry missing from the queue; intent retired"})
            else:
                candidate, base, target = intent["candidate"], intent["base"], intent["target"]
                tested_digest = intent.get("config_digest")
                tip = self.repo.tip(target)
                self.cfg = Config(self.repo)
                if entry.get("status") == "landed":
                    outcomes.append(self.complete(entry, candidate, base, "recovered: the landed row was durable; finished its receipt, routing and audit", recovered=True, tested_digest=tested_digest))
                elif tip is not None and self.repo.is_ancestor(candidate, tip):
                    outcomes.append(self.complete(entry, candidate, base, f"recovered: refs/heads/{target} already contains the candidate (interrupted after the ref update)", recovered=True, tested_digest=tested_digest))
                elif tip != base:
                    outcomes.append(self.void_intent(entry, f"target {target} moved from {short_hex(base)} to {short_hex(tip or '')} while a landing was interrupted; the candidate stays pinned and the next run rebuilds"))
                elif self.cfg.state != "enabled" or self.cfg.target != target:
                    outcomes.append(self.void_intent(entry, "integration is not enabled for that target any more; the interrupted landing is voided, the candidate stays pinned"))
                elif tested_digest is None or tested_digest != self.cfg.digest:
                    reason = (
                        "the interrupted landing recorded no tested policy (written by an earlier version); voided, requeued for validation under the current policy"
                        if tested_digest is None
                        else f"the policy changed after the candidate was validated (tested {tested_digest}, now {self.cfg.digest}); the interrupted landing is voided and the submission requeued for validation under the current policy; the candidate stays pinned"
                    )
                    outcomes.append(self.void_intent(entry, reason))
                else:
                    stale = self.staleness(entry)
                    if stale:
                        self.store.remove("intent.json")
                        self.store.event("intent_voided", entry=entry["id"], reason=stale[0])
                        outcomes.append(self.block(entry, stale[0], stale[1] + ["found while recovering an interrupted landing; the landing was voided and nothing moved"]))
                    else:
                        self.store.event("recover_retry", entry=entry["id"], candidate=candidate, base=base, config_digest=tested_digest)
                        state, detail = self.land(entry, candidate, base, tested_digest=tested_digest)
                        if state == "landed":
                            outcomes.append(self.complete(entry, candidate, base, f"recovered: {detail} (interrupted before the ref update; target, policy and assignment unchanged, same tested candidate)", recovered=True, tested_digest=tested_digest))
                        elif state == "moved":
                            entry["status"] = "queued"
                            entry.setdefault("history", []).append({"at": now_iso(), "event": "requeued", "reason": detail})
                            self.save_entry(entry)
                            outcomes.append({"entry": entry["id"], "outcome": "requeued", "reason": detail})
                        else:
                            outcomes.append(self.block(entry, "target_checkout_busy", [detail]))
        for entry in self.store.queue():
            if entry.get("status") == "integrating":
                entry["status"] = "queued"
                entry.setdefault("history", []).append({"at": now_iso(), "event": "requeued", "reason": "interrupted before any landing intent"})
                self.save_entry(entry)
                self.store.event("requeued", entry=entry["id"], reason="interrupted before any landing intent")
                outcomes.append({"entry": entry["id"], "outcome": "requeued", "reason": "interrupted before any landing intent"})
        return outcomes

    def void_intent(self, entry: dict[str, Any], reason: str) -> dict[str, Any]:
        self.store.remove("intent.json")
        entry["status"] = "queued"
        entry.setdefault("history", []).append({"at": now_iso(), "event": "requeued", "reason": reason})
        self.save_entry(entry)
        self.store.event("intent_voided", entry=entry["id"], reason=reason)
        return {"entry": entry["id"], "outcome": "requeued", "reason": reason}

    # -- the loop -----------------------------------------------------------

    def pending(self) -> list[dict[str, Any]]:
        rows = []
        for entry in self.store.queue():
            if entry.get("status") == "queued":
                rows.append(entry)
            elif entry.get("status") == "blocked" and (entry.get("result") or {}).get("retryable"):
                rows.append(entry)
        rows.sort(key=lambda row: str(row.get("queued_at") or ""))
        return rows

    def process(self) -> list[dict[str, Any]]:
        self.ensure_candidate()
        outcomes: list[dict[str, Any]] = []
        for entry in self.pending():
            outcomes.append(self.integrate(entry))
            if self.once:
                break
        return outcomes


def next_action_for(entry: dict[str, Any]) -> str:
    status = entry.get("status")
    result = entry.get("result") or {}
    reason = result.get("reason")
    item = entry.get("item")
    if status == "landed":
        return f"coordinator: review the receipts, then `manna accept {item} --check <name> --target {result.get('integrated_sha')} --evidence <receipt> --submission {entry['submission']['id']} --attempt {entry['attempt']}` and `manna done {item} --assessment <digest>` when every check is accepted"
    if status == "queued":
        return "integrator: `agent-do git integration run`"
    if status == "integrating":
        return "a run is in progress or was interrupted; `agent-do git integration recover` settles it"
    if status == "superseded":
        return f"nothing; superseded by {entry.get('superseded_by')}"
    if reason == "conflict":
        return f"worker: merge {entry.get('target')} into {entry.get('branch')} in the workspace, resolve, commit, then `agent-do git integration submit {item}`"
    if reason == "checks_failed":
        return f"worker: read the failing check log, fix in the workspace, commit, then `agent-do git integration submit {item}`"
    if reason == "candidate_changed":
        return f"worker: the checks changed the candidate tree (see candidate-drift.patch in the receipts); commit what they generate, or fix the check command with the operator, then `agent-do git integration submit {item}`"
    if reason == "board_paths":
        return "worker: drop board-owned paths from the branch (board edits belong to the canonical checkout) and resubmit"
    if reason in {"stale_submission", "reassigned", "item_closed"}:
        return "the current claimant submits from the current attempt's workspace; this entry is history"
    if reason == "target_checkout_busy":
        return "operator: clean or commit the checkout holding the target, then `agent-do git integration run`"
    if reason in {"config_disabled", "config_invalid", "config_changed"}:
        return "operator: fix or re-enable the policy (`agent-do git integration config`), then `agent-do git integration run`"
    return "see the summary"


def cmd_run(repo: Repo, args: argparse.Namespace, out: Out) -> int:
    store = Store(repo)
    with store.lock("integrator.lock", blocking=False) as lock:
        if not lock.held:
            raise Refusal("another integrator holds the lock for this repository; one integrator per repository", code=EXIT_CONTENDED)
        cfg = Config(repo)
        integrator = Integrator(repo, cfg, store, out, once=bool(args.once))
        recovered = integrator.recover()
        if cfg.state != "enabled":
            pending = [row.get("id") for row in store.queue() if row.get("status") == "queued"]
            payload = {"ok": cfg.state != "invalid", "state": cfg.state, "problems": cfg.problems, "recovered": recovered, "retained_queued": pending, "processed": []}
            lines = [f"Managed Integration is {cfg.state}; no landing. {len(pending)} queued submission(s) retained."]
            lines.extend(f"  problem: {problem}" for problem in cfg.problems)
            lines.extend(f"  recovered: {outcome}" for outcome in recovered)
            return out.emit(payload, lines, EXIT_OK if cfg.state != "invalid" else EXIT_REFUSED)
        processed = integrator.process()
    payload = {"ok": True, "state": cfg.state, "recovered": recovered, "processed": processed, "candidate_path": str(integrator.candidate_path)}
    lines = [f"Integrator ran at {repo.canonical_root} (target {cfg.target}, candidate tree {integrator.candidate_path})"]
    lines.extend(f"  recovered: {outcome['entry']} {outcome['outcome']}" + (f" ({outcome.get('reason')})" if outcome.get("reason") else "") for outcome in recovered)
    if not processed:
        lines.append("  nothing queued")
    for outcome in processed:
        extra = ""
        if outcome["outcome"] == "landed":
            extra = f" integrated {short_hex(outcome['integrated_sha'])}{' (fast-forward)' if outcome.get('fast_forward') else ' (merge)'}"
        elif outcome["outcome"] == "blocked":
            extra = f" {outcome['reason']}{' (retryable)' if outcome.get('retryable') else ''}; summary {outcome['summary']}"
        lines.append(f"  {outcome['item']} {outcome['entry']}: {outcome['outcome']}{extra}")
    return out.emit(payload, lines)


def cmd_recover(repo: Repo, args: argparse.Namespace, out: Out) -> int:
    store = Store(repo)
    with store.lock("integrator.lock", blocking=False) as lock:
        if not lock.held:
            raise Refusal("another integrator holds the lock for this repository; recovery waits for it", code=EXIT_CONTENDED)
        cfg = Config(repo)
        integrator = Integrator(repo, cfg, store, out)
        outcomes = integrator.recover()
    payload = {"ok": True, "state": cfg.state, "recovered": outcomes, "intent": store.intent()}
    lines = [f"Recovery at {repo.canonical_root}: {len(outcomes)} outcome(s)"] + [f"  {o.get('entry')}: {o.get('outcome')}" + (f" ({o.get('reason')})" if o.get("reason") else "") for o in outcomes]
    if not outcomes:
        lines.append("  nothing interrupted")
    return out.emit(payload, lines)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def item_status(repo: Repo, store: Store, item: str, workspaces: list[dict[str, Any]], entries: list[dict[str, Any]], drops: list[dict[str, Any]]) -> dict[str, Any]:
    workspace = latest_workspace(workspaces, item)
    entry = latest_entry([row for row in entries if row.get("status") != "superseded"], item) or latest_entry(entries, item)
    if workspace is None and entry is None:
        state, reason = "unregistered", None
    elif entry is None or entry.get("status") == "superseded":
        state, reason = "building", None
    else:
        state = str(entry.get("status"))
        reason = (entry.get("result") or {}).get("reason")
    obligations = [
        {"id": drop.get("id"), "kind": drop.get("kind"), "status": drop.get("status"), "stage": (drop.get("delivery") or {}).get("stage"), "stale": (drop.get("delivery") or {}).get("stale"), "note": drop.get("note"), "path": drop.get("path")}
        for drop in drops
        if isinstance(drop.get("for_item"), dict) and drop["for_item"].get("id") == item
    ]
    evidence: dict[str, Any] = {}
    if entry:
        result = entry.get("result") or {}
        evidence = {
            "receipts": entry.get("receipts"),
            "report": entry.get("report"),
            "submission_ref": entry.get("submission_ref"),
            "candidate_ref": result.get("candidate_ref"),
            "checks": result.get("checks"),
            "candidate_integrity": result.get("candidate_integrity"),
            "policy_digest": result.get("config_digest") or result.get("policy_digest"),
            "rebuilds": entry.get("rebuilds"),
            "revalidations": entry.get("revalidations"),
            "routing": entry.get("routing"),
        }
    return {
        "item": item,
        "state": state,
        "reason": reason,
        "attempt": (entry or workspace or {}).get("attempt"),
        "workspace": workspace,
        "entry": entry,
        "evidence": evidence,
        "obligations": obligations,
        "next_action": next_action_for(entry) if entry else (f"worker: commit in {workspace['path']} then `agent-do git integration submit {item}`" if workspace else f"claimant: `agent-do git integration workspace add {item}`"),
    }


def cmd_status(repo: Repo, args: argparse.Namespace, out: Out) -> int:
    cfg = Config(repo)
    store = Store(repo)
    workspaces = store.workspaces()
    entries = store.queue()
    drops: list[dict[str, Any]] = []
    if repo.board_dir.is_dir():
        payload, _ = coord_json(["drops", "--all"], cwd=repo.canonical_root)
        if payload and isinstance(payload.get("drops"), list):
            drops = payload["drops"]
    items = [args.item] if args.item else sorted({*(row.get("item") for row in workspaces), *(row.get("item") for row in entries)})
    rows = [item_status(repo, store, item, workspaces, entries, drops) for item in items if item]
    intent = store.intent()
    payload = {"ok": True, "config": cfg.as_dict(), "canonical_root": str(repo.canonical_root), "via_worktree": repo.via_worktree, "state_dir": str(store.dir), "intent": intent, "items": rows}
    lines = [f"Managed Integration {cfg.state} at {repo.canonical_root}" + (f" (target {cfg.target})" if cfg.target else "")]
    if intent:
        lines.append(f"  landing in flight: {intent.get('entry')} for {intent.get('item')} (candidate {short_hex(intent.get('candidate', ''))}); `agent-do git integration recover` settles it")
    if not rows:
        lines.append("  no workspaces or submissions")
    for row in rows:
        entry = row.get("entry") or {}
        result = entry.get("result") or {}
        detail = ""
        if row["state"] == "landed":
            detail = f" integrated {short_hex(result.get('integrated_sha', ''))} onto {entry.get('target')} at {result.get('landed_at')}"
        elif row["state"] == "blocked":
            detail = f" ({row['reason']}{'; retryable' if result.get('retryable') else ''})"
        elif row["state"] in {"queued", "integrating"}:
            detail = f" source {short_hex(entry.get('source_sha', ''))} against {entry.get('target')} at {short_hex(entry.get('base_sha', ''))}"
        lines.append(f"  {row['item']}: {row['state']}{detail}")
        if row.get("workspace"):
            lines.append(f"    workspace a{row['workspace'].get('attempt')} {row['workspace'].get('branch')} -> {row['workspace'].get('path')} (worker {row['workspace'].get('worker', {}).get('label')})")
        if row["evidence"].get("receipts"):
            lines.append(f"    receipts: {row['evidence']['receipts']}")
        for obligation in row["obligations"]:
            lines.append(f"    drop {obligation['id']} {obligation['kind']} {obligation['status']} stage {obligation['stage']}" + (" STALE" if obligation.get("stale") else ""))
        lines.append(f"    next: {row['next_action']}")
    return out.emit(payload, lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-git integration", add_help=True)
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="verb", required=True)

    enable = sub.add_parser("enable")
    enable.add_argument("--target", required=False)
    enable.add_argument("--check", action="append", default=[])
    enable.add_argument("--authorized-by", dest="authorized_by")
    enable.add_argument("--workspace-root", dest="workspace_root")
    enable.add_argument("--candidate-path", dest="candidate_path")

    disable = sub.add_parser("disable")
    disable.add_argument("--reason")

    sub.add_parser("config")

    workspace = sub.add_parser("workspace")
    workspace_sub = workspace.add_subparsers(dest="workspace_verb", required=True)
    add = workspace_sub.add_parser("add")
    add.add_argument("item")
    add.add_argument("--path")
    workspace_sub.add_parser("list")

    submit = sub.add_parser("submit")
    submit.add_argument("item")
    submit.add_argument("--report")
    submit.add_argument("--evidence", action="append", default=[])

    run_parser = sub.add_parser("run")
    run_parser.add_argument("--once", action="store_true")

    sub.add_parser("recover")

    status = sub.add_parser("status")
    status.add_argument("item", nargs="?")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in argv
    argv = [arg for arg in argv if arg != "--json"]
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    out = Out(json_mode)
    try:
        repo = Repo(Path.cwd())
        if args.verb == "enable":
            return cmd_enable(repo, args, out)
        if args.verb == "disable":
            return cmd_disable(repo, args, out)
        if args.verb == "config":
            return cmd_config(repo, args, out)
        if args.verb == "workspace":
            return cmd_workspace_add(repo, args, out) if args.workspace_verb == "add" else cmd_workspace_list(repo, args, out)
        if args.verb == "submit":
            return cmd_submit(repo, args, out)
        if args.verb == "run":
            return cmd_run(repo, args, out)
        if args.verb == "recover":
            return cmd_recover(repo, args, out)
        if args.verb == "status":
            return cmd_status(repo, args, out)
        raise Refusal(f"unknown verb {args.verb}")
    except Refusal as refusal:
        return out.refuse(refusal)


if __name__ == "__main__":
    sys.exit(main())
