#!/usr/bin/env python3
"""Read helpers and the core-state adapter for `manna serve`.

The canonical whole-board derivation lives in the Rust core and is exposed as
`manna state --json`. This module invokes that contract for the page and keeps
the cheap raw/signature helpers used by the estate index. Nothing here authors
board state.

Read-only by construction: this module never writes into a project. Live state
runs `manna reconcile --json` without `--write-drift`; cached state reads the
last drift file and reports its age.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Title conventions that mean "a human must rule before this moves". Manna has
# no typed decision state yet; the board's own convention is a leading marker
# in the title, matched case-insensitively. A machine adds its own names
# (`manna serve --decision-marker "[NAME]"`); the shipped defaults name a role.
DECISION_MARKERS = ("[DECISION]", "[HUMAN]", "[OWNER]")

# Fields that never leave the board directory. claim_token_hash is the digest
# of a private bearer token (SCHEMA.md); legacy_migration is admission
# history a reader has no use for.
PRIVATE_FIELDS = frozenset({"claim_token_hash", "legacy_migration"})

# git log field separators (ASCII unit / record separators, never in a subject).
_FS = "\x1f"
_RS = "\x1e"

COORD_SIGNATURE_FILES = ("agents.json", "sessions.json", "claims.json", "focus.json")

_MN_ID = re.compile(r"\bmn-[0-9a-f]{6,}\b")
_BOARD_ID = re.compile(r"^mb-[0-9a-f]{32}$")
_MANNA_URI = re.compile(r"^manna://mb-[0-9a-f]{32}/mn-[0-9a-f]{6,}$")
RELATION_KINDS = frozenset({"counterpart", "informed_by", "depends_on", "supersedes"})
MANNA_TOOL_DIR = Path(__file__).resolve().parent.parent


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def mtime_iso(path: Path) -> str | None:
    try:
        return iso(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))
    except FileNotFoundError:
        return None


def find_board_root(start: Path) -> Path | None:
    """Nearest ancestor (inclusive) holding a .manna/ directory."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".manna").is_dir():
            return candidate
    return None


def run(cmd: list[str], cwd: Path, timeout: float, any_exit: bool = False) -> str:
    """stdout of a command, or "" when it failed. `any_exit` keeps stdout on a
    nonzero exit, for verbs like reconcile that exit 1 *because* they found
    something and still print the structured answer."""
    try:
        completed = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, check=False, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode == 0 or any_exit:
        return completed.stdout
    return ""


# ---------------------------------------------------------------- raw reads


def read_issues(board_dir: Path) -> list[dict[str, Any]]:
    path = board_dir / "issues.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                continue
            rows.append({k: v for k, v in row.items() if k not in PRIVATE_FIELDS})
    return rows


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def read_order(board_dir: Path) -> list[str]:
    items = read_yaml(board_dir / "handoff-order.yaml").get("items")
    return [i for i in items if isinstance(i, str)] if isinstance(items, list) else []


def read_federation(board_dir: Path) -> dict[str, Any]:
    """Read the portable declaration only. Resolution remains a separate,
    derived operation through the machine-local registry."""
    path = board_dir / "federation.yaml"
    if path.is_symlink():
        return {"enabled": True, "board_id": None, "relations": [], "error": "symlinked federation manifest refused"}
    if not path.is_file():
        return {"enabled": False, "board_id": None, "relations": []}
    data = read_yaml(path)
    board_id = data.get("board_id")
    rows = data.get("relations")
    if data.get("version") != 1 or not isinstance(board_id, str) or not _BOARD_ID.fullmatch(board_id):
        return {"enabled": True, "board_id": None, "relations": [], "error": "invalid federation manifest"}
    relations = []
    if not isinstance(rows, list):
        return {"enabled": True, "board_id": board_id, "relations": [], "error": "invalid federation relations"}
    for row in rows:
        if not isinstance(row, dict):
            return {"enabled": True, "board_id": board_id, "relations": [], "error": "invalid federation relation"}
        source, kind, target = row.get("from"), row.get("kind"), row.get("to")
        if (
            not isinstance(source, str)
            or not _MN_ID.fullmatch(source)
            or kind not in RELATION_KINDS
            or not isinstance(target, str)
            or not _MANNA_URI.fullmatch(target)
        ):
            return {"enabled": True, "board_id": board_id, "relations": [], "error": "invalid federation relation"}
        relation = {"from": source, "kind": kind, "to": target}
        if isinstance(row.get("hint"), str) and row["hint"].strip():
            relation["hint"] = row["hint"]
        relations.append(relation)
    return {"enabled": True, "board_id": board_id, "relations": relations}


def live_drift(root: Path, agent_do: Path | None) -> dict[str, Any] | None:
    """Findings as of now. `manna reconcile --json` reads the board and git
    without writing; the file it would write needs --write-drift, which the
    page never passes. None when the CLI is unavailable or fails."""
    if agent_do is None or not agent_do.is_file():
        return None
    out = run([str(agent_do), "manna", "reconcile", "--json"], root, timeout=60, any_exit=True)
    if not out:
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    findings = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(findings, list):
        return None
    findings = [f for f in findings if isinstance(f, dict)]
    kinds: dict[str, int] = {}
    for finding in findings:
        kind = str(finding.get("kind", "unknown"))
        kinds[kind] = kinds.get(kind, 0) + 1
    return {"findings": findings, "count": len(findings), "kinds": kinds, "generated_at": iso(utc_now())}


def read_drift(board_dir: Path) -> dict[str, Any]:
    path = board_dir / "drift.yaml"
    data = read_yaml(path)
    findings = data.get("findings")
    findings = [f for f in findings if isinstance(f, dict)] if isinstance(findings, list) else []
    kinds: dict[str, int] = {}
    for finding in findings:
        kind = str(finding.get("kind", "unknown"))
        kinds[kind] = kinds.get(kind, 0) + 1
    return {
        "present": path.is_file(),
        "generated_at": data.get("generated_at"),
        "findings": findings,
        "count": len(findings),
        "kinds": kinds,
    }


# ---------------------------------------------------------------- git


def git_dir(root: Path) -> Path | None:
    out = run(["git", "rev-parse", "--git-dir"], root, timeout=5).strip()
    if not out:
        return None
    path = Path(out)
    return (root / path).resolve() if not path.is_absolute() else path


def git_summary(root: Path) -> dict[str, Any]:
    branch = run(["git", "branch", "--show-current"], root, timeout=5).strip()
    head = run(["git", "rev-parse", "--short", "HEAD"], root, timeout=5).strip()
    dirty = run(["git", "status", "--porcelain"], root, timeout=10).splitlines()
    return {
        "branch": branch or None,
        "head": head or None,
        "dirty_paths": len(dirty),
        "is_repo": bool(head),
    }


def git_trailers(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Every commit carrying a `Manna:` trailer, indexed by the ids it names.

    One log call over the whole local history; the trailer is the receipt the
    board doctrine requires on any commit advancing an item, so this is the
    evidence column without a receipt config.
    """
    fmt = f"%h{_FS}%cI{_FS}%s{_FS}%(trailers:key=Manna,valueonly,separator={_RS})"
    out = run(["git", "log", f"--format={fmt}", "--grep=^Manna:", "--extended-regexp"], root, timeout=20)
    index: dict[str, list[dict[str, Any]]] = {}
    for line in out.splitlines():
        parts = line.split(_FS)
        if len(parts) != 4:
            continue
        short, when, subject, trailers = parts
        ids = set()
        for value in trailers.split(_RS):
            ids.update(_MN_ID.findall(value))
        for issue_id in ids:
            index.setdefault(issue_id, []).append({"sha": short, "at": when, "subject": subject})
    return index


# ---------------------------------------------------------------- coord


def coord_cmd(agent_do: Path) -> list[str]:
    """Invoke the coord tool script directly when it exists beside agent-do.

    The dispatcher spends 1.5-2s per call on registry/creds/telemetry
    interpreter spawns (worse under machine load), and presence refreshes
    pay it on a cadence. coord declares no secrets, so the direct script is
    behaviorally identical at ~0.4s."""
    import sys as _sys

    tool = Path(str(agent_do)).parent / "tools" / "agent-coord"
    if tool.is_file():
        return [_sys.executable, str(tool)]
    return [str(agent_do), "coord"]


def coord_peers(root: Path, agent_do: Path | None) -> list[dict[str, Any]]:
    if agent_do is None or not agent_do.is_file():
        return []
    out = run([*coord_cmd(agent_do), "peers", "--json"], root, timeout=10)
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    peers = data.get("peers") if isinstance(data, dict) else None
    if not isinstance(peers, list):
        return []
    slim = []
    for peer in peers:
        if not isinstance(peer, dict):
            continue
        focus = peer.get("focus") if isinstance(peer.get("focus"), dict) else {}
        slim.append(
            {
                "agent_id": peer.get("agent_id"),
                "alias": peer.get("alias"),
                "status": peer.get("status"),
                "age": peer.get("age"),
                "age_seconds": peer.get("age_seconds"),
                "runtime": peer.get("runtime"),
                "role": peer.get("role"),
                "mode": peer.get("mode"),
                "phase": peer.get("phase"),
                "goal": focus.get("goal"),
                "paths": focus.get("paths") or peer.get("territory") or [],
                "pulse": slim_pulse(peer.get("pulse")),
            }
        )
    for peer in slim:
        peer["attention"] = attention_rank(peer)
    return slim


# Attention-first, the order coord peers itself uses: whoever waits on a
# human outranks whoever failed, outranks whoever is working, outranks the
# merely present; the finished and the gone sink.
ATTENTION_ORDER = ("needs-user", "failed", "working", "present", "idle", "finished", "ended", "gone")


def slim_pulse(pulse: Any) -> dict[str, Any] | None:
    """The telemetry fields the page shows. Pulse is a hint about what a
    session is doing now, never evidence of what the board records."""
    if not isinstance(pulse, dict):
        return None
    out = {
        "status": pulse.get("status"),
        "activity": pulse.get("activity"),
        "latest_prompt": pulse.get("latest_prompt"),
        "updated_at": pulse.get("updated_at"),
        "turns": pulse.get("turns"),
    }
    todo = pulse.get("todo")
    if isinstance(todo, dict):
        out["todo"] = {"done": todo.get("done"), "total": todo.get("total"), "current": todo.get("current")}
    return out


def attention_rank(peer: dict[str, Any]) -> str:
    """Mirror of the Rust core's ranking (state.rs attention_rank), so the
    estate glance and the board page count the same peer the same way."""
    liveness = peer.get("status")
    pulse = peer.get("pulse") or {}
    pstatus = pulse.get("status")
    if liveness in ("dead", "stopped", "stale"):
        return "gone"
    if pstatus in ("needs-user", "failed", "working", "idle", "finished", "ended"):
        return pstatus
    if liveness == "idle":
        return "idle"
    return "present"


def attention_key(peer: dict[str, Any]) -> tuple:
    rank = peer.get("attention") or attention_rank(peer)
    pos = ATTENTION_ORDER.index(rank) if rank in ATTENTION_ORDER else len(ATTENTION_ORDER)
    return (pos, peer.get("age_seconds") if isinstance(peer.get("age_seconds"), (int, float)) else 10**9)


def coord_json(root: Path, agent_do: Path | None, *verb: str, key: str) -> list[dict[str, Any]]:
    if agent_do is None or not agent_do.is_file():
        return []
    out = run([*coord_cmd(agent_do), *verb, "--json"], root, timeout=10)
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    rows = data.get(key) if isinstance(data, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


LIVE_OWNER = frozenset({"active", "idle"})
EMPTY_COORD: dict[str, Any] = {"claims": [], "contention": [], "drops": [], "needs": []}


def _overlaps(a: str, b: str) -> bool:
    a, b = a.rstrip("/"), b.rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/") or a == "." or b == "."


def coord_snapshot(root: Path, agent_do: Path | None, peers: list[dict[str, Any]]) -> dict[str, Any]:
    """Claims, drops, needs, and the contention the page can see for itself:
    two live owners whose claimed paths overlap. coord's own interrupts are
    per-session; the daemon has no session, so it derives the shared view."""
    claims = []
    for c in coord_json(root, agent_do, "claims", key="claims"):
        claims.append(
            {
                "path": c.get("path"),
                "owner": c.get("owner"),
                "owner_alias": c.get("owner_alias"),
                "owner_status": c.get("owner_status"),
                "reason": c.get("reason"),
                "strength": c.get("strength"),
                "updated_at": c.get("updated_at") or c.get("created_at"),
                "stale": c.get("owner_status") not in LIVE_OWNER,
            }
        )
    live = [c for c in claims if not c["stale"] and c.get("path")]
    contention: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(live):
        for b in live[i + 1 :]:
            if a["owner"] == b["owner"] or not _overlaps(str(a["path"]), str(b["path"])):
                continue
            key = tuple(sorted((f"{a['owner']}:{a['path']}", f"{b['owner']}:{b['path']}")))
            if key in seen:
                continue
            seen.add(key)
            contention.append({"paths": sorted({str(a["path"]), str(b["path"])}), "owners": sorted({str(a["owner"]), str(b["owner"])})})
    for c in claims:
        c["contended"] = any(c["owner"] in x["owners"] and c["path"] in x["paths"] for x in contention)
    claims.sort(key=lambda c: (c["stale"], not c["contended"], str(c["path"])))

    drops = []
    for d in coord_json(root, agent_do, "drops", key="drops"):
        drops.append(
            {
                "for": d.get("for"),
                "path": d.get("path") or d.get("paths"),
                "note": d.get("note"),
                "owner": d.get("owner_label") or d.get("owner"),
                "key": d.get("key"),
                "created_at": d.get("created_at"),
            }
        )
    drops.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    needs = [{"key": n.get("key"), "why": n.get("why"), "owner": n.get("owner") or n.get("owner_label")} for n in coord_json(root, agent_do, "need", "list", "--all", key="needs")]
    return {"claims": claims, "contention": contention, "drops": drops, "needs": needs}


def _identity_hex(value: str | None) -> str:
    """The hex tail shared by manna's claimant label and coord's agent id.

    manna: claude-3c15edbd486045ef / codex-01a02afe94d27b52
    coord: session-3c15edbd4860   / codex-01a02afe94d27b52
    Both derive from the same session id; one is a prefix of the other.
    """
    if not value:
        return ""
    tail = value.rsplit("-", 1)[-1].lower()
    return tail if re.fullmatch(r"[0-9a-f]+", tail) else value.lower()


def match_peer(claimed_by: str | None, peers: list[dict[str, Any]]) -> dict[str, Any] | None:
    want = _identity_hex(claimed_by)
    if not want:
        return None
    for peer in peers:
        have = _identity_hex(peer.get("agent_id"))
        if have and (want.startswith(have) or have.startswith(want)):
            return peer
    return None


# ---------------------------------------------------------------- derivation


_LEADING_TAGS = re.compile(r"^\s*((?:\[[^\]]*\]\s*)+)")


def is_decision(issue: dict[str, Any], markers: tuple[str, ...] = DECISION_MARKERS) -> bool:
    """A marker counts only when it leads the title; a mention mid-sentence is prose."""
    match = _LEADING_TAGS.match(str(issue.get("title", "")))
    if not match:
        return False
    tags = {tag.upper() for tag in re.findall(r"\[[^\]]*\]", match.group(1))}
    return any(marker.upper() in tags for marker in markers)


def strip_markers(title: str) -> str:
    return re.sub(r"^(\s*\[[^\]]*\]\s*)+", "", title).strip() or title


def _stale_binary_error(binary: Path, sources: list[Path]) -> str | None:
    """A binary older than the sources the daemon's health hash follows is a
    lie waiting to be served: the daemon restarts "clean" on a source change
    and then renders yesterday's contract. Name the rebuild instead."""
    try:
        built = binary.stat().st_mtime
    except OSError:
        return None
    newest_path: Path | None = None
    newest = built
    for path in sources:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > newest:
            newest, newest_path = mtime, path
    if newest_path is None:
        return None
    return (
        f"manna-core binary is older than {newest_path.name}; rebuild it: "
        f"cargo build --release --manifest-path {MANNA_TOOL_DIR / 'Cargo.toml'}"
    )


def _state_binary() -> Path:
    override = os.environ.get("MANNA_STATE_BINARY")
    if override:
        path = Path(override)
        if path.is_file() and os.access(path, os.X_OK):
            return path
        raise RuntimeError(f"MANNA_STATE_BINARY is not executable: {path}")
    sources = [*sorted((MANNA_TOOL_DIR / "src").glob("*.rs")), MANNA_TOOL_DIR / "Cargo.toml"]
    for candidate in (
        MANNA_TOOL_DIR / "target" / "release" / "manna-core",
        MANNA_TOOL_DIR / "target" / "debug" / "manna-core",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            stale = _stale_binary_error(candidate, sources)
            if stale:
                raise RuntimeError(stale)
            return candidate
    import shutil

    on_path = shutil.which("manna-core")
    if on_path:
        return Path(on_path)
    raise RuntimeError(
        "manna-core binary is unavailable; build it: "
        f"cargo build --release --manifest-path {MANNA_TOOL_DIR / 'Cargo.toml'}"
    )


def derive(
    root: Path,
    agent_do: Path | None = None,
    markers: tuple[str, ...] = DECISION_MARKERS,
    live: bool = False,
    coord: dict[str, Any] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Read the canonical core model. Legacy keyword inputs are accepted so
    callers can migrate without splitting the state contract; they are never
    used to re-derive or overlay the core result.

    `coord` hands the core an already-fetched presence snapshot
    ({"peers": [...], "coord": {...}}) so one observation feeds both the
    caller's cache signature and this payload; the core still folds it (and
    re-ranks attention) itself."""
    command = [str(_state_binary()), "state", "--json"]
    if not live:
        command.append("--cached-drift")
    for marker in markers:
        command.extend(["--decision-marker", marker])
    env = dict(os.environ)
    env["MANNA_STATE_AGENT_DO"] = str(agent_do) if agent_do is not None else "none"
    env.pop("MANNA_STATE_COORD_FILE", None)
    coord_file: Path | None = None
    if coord is not None:
        import tempfile

        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", prefix="manna-coord-", suffix=".json", delete=False
        )
        with handle:
            json.dump(coord, handle)
        coord_file = Path(handle.name)
        env["MANNA_STATE_COORD_FILE"] = str(coord_file)
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"manna state failed: {error}") from error
    finally:
        if coord_file is not None:
            try:
                coord_file.unlink()
            except OSError:
                pass
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        detail = completed.stderr.strip()[:400] or "no JSON response"
        raise RuntimeError(f"manna state failed: {detail}") from error
    if completed.returncode != 0 or not isinstance(payload, dict) or payload.get("success") is not True:
        detail = payload.get("error") if isinstance(payload, dict) else None
        raise RuntimeError(f"manna state failed: {detail or completed.stderr.strip()[:400]}")
    return {key: value for key, value in payload.items() if key != "success"}


# ---------------------------------------------------------------- signature


def signature_paths(root: Path, gitdir: Path | None, include_coord: bool = True) -> list[Path]:
    board_dir = root / ".manna"
    paths = [
        board_dir / "issues.jsonl",
        board_dir / "handoff-order.yaml",
        board_dir / "drift.yaml",
        board_dir / "board.yaml",
        board_dir / "workflow.yaml",
        board_dir / "federation.yaml",
    ]
    if gitdir:
        paths.extend([gitdir / "HEAD", gitdir / "index", gitdir / "logs" / "HEAD"])
        if include_coord:
            coord_root = gitdir / "agent-do" / "coord"
            paths.extend(coord_root / name for name in COORD_SIGNATURE_FILES)
    return paths


def base_signature(root: Path, gitdir: Path | None) -> str:
    """Board + git only. Presence files are excluded on purpose: every tool
    call by any agent in the repo touches them, so a signature that included
    them would never settle. Presence is read on its own cadence."""
    return signature(root, gitdir, include_coord=False)


def coord_signature(root: Path, gitdir: Path | None) -> str:
    """Only the coord presence files: what the estate glance depends on."""
    if not gitdir:
        return "no-git"
    parts = []
    for name in COORD_SIGNATURE_FILES:
        path = gitdir / "agent-do" / "coord" / name
        try:
            st = path.stat()
            parts.append(f"{name}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{name}:missing")
    return "|".join(parts)


def glance(root: Path, agent_do: Path | None) -> dict[str, Any]:
    """Attention counts for one board's coord presence: the index-row view."""
    return glance_from_peers(coord_peers(root, agent_do))


def glance_from_peers(peers: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {rank: sum(1 for p in peers if p.get("attention") == rank) for rank in ATTENTION_ORDER}
    return {
        "attention": counts,
        "needs_you": counts["needs-user"] + counts["failed"],
        "working": counts["working"],
        "here": sum(v for k, v in counts.items() if k != "gone"),
        "gone": counts["gone"],
    }


def signature(root: Path, gitdir: Path | None, include_coord: bool = True) -> str:
    parts = []
    for path in signature_paths(root, gitdir, include_coord):
        try:
            st = path.stat()
            parts.append(f"{path}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{path}:missing")
    return "|".join(parts)


def _track_waits(track: dict[str, Any], issues: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], markers: tuple[str, ...]) -> bool:
    """Mirror of the core's dispatch rule for a paired track: it waits when no
    item in it is claimable now and work remains, or when it has no items; it
    is ready while an item is claimable or every item is done."""
    items = [i for i in issues if i.get("track") == track["id"] and i.get("type", "item") == "item"]
    if not items:
        return True
    open_items = [i for i in items if i.get("status") != "done"]
    if not open_items:
        return False
    for item in open_items:
        if item.get("status") != "open" or item.get("claimed_by"):
            continue
        if any((by_id.get(dep) or {}).get("status") != "done" for dep in item.get("blocked_by") or []):
            continue
        if is_decision(item, markers):
            continue
        return False
    return True


def summary(root: Path, markers: tuple[str, ...] = DECISION_MARKERS) -> dict[str, Any]:
    """Cheap index-row view of a board: counts and freshness, no git walk."""
    board_dir = root / ".manna"
    issues = read_issues(board_dir)
    # Effective rules, the same ones the board page renders with (the blocker
    # graph outranks the status field), so an estate number always matches
    # the section a click on it opens.
    by_id = {i["id"]: i for i in issues}
    status_counts: dict[str, int] = {}
    dreams = 0
    decisions = 0
    for issue in issues:
        track_waits = False
        if issue.get("type") == "track":
            # A track carrying a sealed handoff is a dispatchable assignment
            # and counts under the item lifecycle, as the core derives it; a
            # container track counts nowhere.
            if not (issue.get("prompt") and issue.get("handoff_digest")):
                continue
            track_waits = _track_waits(issue, issues, by_id, markers)
        if issue.get("type") == "dream":
            if issue.get("status") != "done":
                dreams += 1
            continue
        s = issue.get("status", "open")
        blocked = track_waits or any((by_id.get(dep) or {}).get("status") != "done" for dep in issue.get("blocked_by") or [])
        decision = is_decision(issue, markers) and s != "done"
        if s == "done":
            key = "done"
        elif s == "in_progress":
            key = "active"
        elif blocked:
            key = "blocked"
        elif decision:
            key = "decision"
        else:
            key = "ready"
        status_counts[key] = status_counts.get(key, 0) + 1
        if decision:
            decisions += 1
    drift = read_drift(board_dir)
    latest = max((i.get("updated_at") or "" for i in issues), default="") or None
    return {
        "name": root.name,
        "root": str(root),
        "exists": board_dir.is_dir(),
        "total": len(issues),
        "status_counts": status_counts,
        "dreams": dreams,
        "decisions": decisions,
        "drift_count": drift["count"],
        "drift_generated_at": drift["generated_at"],
        "latest_update": latest,
        "issues_modified_at": mtime_iso(board_dir / "issues.jsonl"),
    }
