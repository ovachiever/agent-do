#!/usr/bin/env python3
"""`agent-do manna serve`: the human window onto every manna board.

One read-only daemon on a fixed local port. `/` indexes every registered
board across the estate; `/<slug>` renders one project. Running `serve`
inside a project registers that board, starts the daemon if it is not up,
and always prints the project's URL, so any agent asked "show me the board"
runs this and hands the link over.

Agents do not read from this server. The page renders the canonical
`manna state --json` contract; the only file it writes is its own registry
under $AGENT_DO_HOME/manna/serve/.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import hashlib
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

SERVE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVE_DIR))
import board as board_lib  # noqa: E402
import digest as digest_lib  # noqa: E402

STATIC_DIR = SERVE_DIR / "static"
AGENT_DO = Path(os.environ.get("MANNA_SERVE_AGENT_DO") or (SERVE_DIR.parents[2] / "agent-do"))

# The port is machine-local configuration, never a shipped constant: one
# machine's memorable number is another machine's occupied port. First run
# asks the OS for a free port (bind to 0), persists the pick in
# $AGENT_DO_HOME/manna/serve/config.json, and every later run reuses it, so
# printed URLs and bookmarks stay stable. --port and MANNA_SERVE_PORT
# override one invocation without rewriting the config.
DEFAULT_HOST = "127.0.0.1"
SERVER_NAME = "manna-serve"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"})

# The page reads as live when a change lands within the flow-of-thought
# limit (Nielsen, Usability Engineering 1993: 1.0s). Polling file mtimes
# once a second is far under that once render time is added, and costs a
# handful of stat calls per client per second.
POLL_INTERVAL_SECONDS = 1.0

# Presence is re-read every ten seconds: Nielsen's limit for keeping a
# person's attention on a dialogue (Usability Engineering, 1993: 10s), so
# a "needs you" reaches the page inside the window in which it still holds
# the human's attention. Presence files themselves churn on every tool call
# in the repo, so they cannot drive a signature; a cadence must.
COORD_REFRESH_SECONDS = 10.0

# A scan walks three directory levels below the root it is given: deep enough
# for <root>/<project>/<sub-project>/.manna, the deepest layout this was built
# against, and shallow enough never to crawl a home directory.
SCAN_DEPTH = 3
SCAN_SKIP = {".git", "node_modules", "target", ".venv", "venv", "__pycache__", ".manna", ".handoff"}


def source_hash() -> str:
    """Identity of the daemon and the core state contract it renders."""
    digest = hashlib.sha256()
    for path in (
        SERVE_DIR / "serve.py",
        SERVE_DIR / "board.py",
        SERVE_DIR / "digest.py",
        SERVE_DIR.parent / "src" / "state.rs",
        SERVE_DIR.parent / "src" / "main.rs",
    ):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


SOURCE_HASH = source_hash()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def serve_home() -> Path:
    home = Path(os.environ.get("AGENT_DO_HOME", str(Path.home() / ".agent-do")))
    path = home / "manna" / "serve"
    path.mkdir(parents=True, exist_ok=True)
    return path


def registry_path() -> Path:
    return serve_home() / "boards.json"


def config_path() -> Path:
    return serve_home() / "config.json"


def resolved_port() -> int:
    """The daemon's stable port: read from config, or pick a free one once."""
    import socket

    try:
        port = int(json.loads(config_path().read_text())["port"])
        if 0 < port < 65536:
            return port
    except (OSError, ValueError, KeyError, TypeError):
        pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((DEFAULT_HOST, 0))
        port = probe.getsockname()[1]
    tmp = config_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"port": port}) + "\n")
    tmp.replace(config_path())
    return port


def identity_path() -> Path:
    return serve_home() / "identity.json"


def serve_identity() -> dict[str, str]:
    """The daemon's own manna identity: a public label plus a private bearer
    token, pinned the way scripted lanes pin theirs (README: MANNA_SESSION_ID
    + MANNA_SESSION_TOKEN). Created once, mode 600, never sent to a page."""
    path = identity_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("session_id") and data.get("token"):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    import secrets
    data = {"session_id": f"serve-{secrets.token_hex(8)}", "token": secrets.token_hex(32), "created_at": utc_now_iso()}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return data


# One token per daemon process, handed to the page inside its state (same
# origin only) and required on every write: a cross-site page cannot read it.
import secrets as _secrets
ACT_TOKEN = _secrets.token_hex(16)

# What a click may run. Every action is a manna verb; nothing edits a file.
ACTIONS = {
    "fix": {"argv": ["manna", "reconcile", "--fix", "--json"], "needs_id": False, "confirm": False},
    "sync": {"argv": ["manna", "sync"], "needs_id": False, "confirm": False},
    "close": {"argv": None, "needs_id": True, "confirm": False},   # claim then done
    "promote": {"argv": ["manna", "update", "{id}", "--type", "item"], "needs_id": True, "confirm": False},
    "delete": {"argv": ["manna", "delete", "{id}"], "needs_id": True, "confirm": True},
}


def run_manna(root: Path, argv: list[str]) -> dict[str, Any]:
    ident = serve_identity()
    env = {**os.environ, "MANNA_SESSION_ID": ident["session_id"], "MANNA_SESSION_TOKEN": ident["token"]}
    try:
        done = subprocess.run([str(AGENT_DO), *argv], cwd=str(root), env=env, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"code": -1, "stdout": "", "stderr": str(error)[:400]}
    return {"code": done.returncode, "stdout": done.stdout[-4000:], "stderr": done.stderr[-4000:]}


def perform(slug: str, root: Path, action: str, issue_id: str | None, confirm: bool) -> dict[str, Any]:
    spec = ACTIONS.get(action)
    if not spec:
        return {"ok": False, "error": "unknown action"}
    if spec["needs_id"] and not (issue_id and re.fullmatch(r"mn-[0-9a-f]{6,}", issue_id)):
        return {"ok": False, "error": "an item id is required"}
    if spec["confirm"] and not confirm:
        return {"ok": False, "error": "confirm required", "needs_confirm": True}
    steps = []
    if action == "close":
        for argv in (["manna", "claim", issue_id], ["manna", "done", issue_id]):
            result = run_manna(root, argv)
            steps.append({"argv": argv, **result})
            if result["code"] != 0:
                break
    else:
        argv = [a.replace("{id}", issue_id or "") for a in spec["argv"]]
        steps.append({"argv": argv, **run_manna(root, argv)})
    ok = all(st["code"] == 0 for st in steps)
    with CACHE.lock:  # the next read re-derives; the file signature will move anyway
        CACHE.states.pop(slug, None)
    sys.stdout.write(f"[act] {slug} {action} {issue_id or ''} -> {'ok' if ok else 'refused'}\n"); sys.stdout.flush()
    return {"ok": ok, "action": action, "id": issue_id, "steps": steps}


def daemon_path() -> Path:
    return serve_home() / "daemon.json"


def log_path() -> Path:
    return serve_home() / "daemon.log"


# ---------------------------------------------------------------- registry


def load_registry_file() -> dict[str, Any]:
    path = registry_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_registry() -> dict[str, dict[str, Any]]:
    boards = load_registry_file().get("boards")
    return boards if isinstance(boards, dict) else {}


def decision_markers() -> tuple[str, ...]:
    """Shipped role markers plus whatever this machine added; never a person's name in code."""
    extra = load_registry_file().get("decision_markers")
    extra = [m for m in extra if isinstance(m, str) and m.strip()] if isinstance(extra, list) else []
    return tuple(dict.fromkeys([*board_lib.DECISION_MARKERS, *extra]))


def save_registry(boards: dict[str, dict[str, Any]], markers: list[str] | None = None) -> None:
    current = load_registry_file()
    payload = {"version": 1, "boards": boards, "decision_markers": markers if markers is not None else current.get("decision_markers", [])}
    path = registry_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def add_decision_marker(tag: str) -> list[str]:
    tag = tag.strip()
    if not (tag.startswith("[") and tag.endswith("]") and len(tag) > 2):
        raise ValueError(f"a decision marker is a bracketed tag like [NAME], not {tag!r}")
    current = load_registry_file()
    markers = [m for m in current.get("decision_markers", []) if isinstance(m, str)]
    if tag.upper() not in {m.upper() for m in markers}:
        markers.append(tag)
    save_registry(load_registry(), markers)
    return markers


def slug_for(root: Path, boards: dict[str, dict[str, Any]]) -> str:
    """Directory name, or parent--name when another board already owns it."""
    for slug, entry in boards.items():
        if entry.get("path") == str(root):
            return slug
    base = root.name or "root"
    if base not in boards:
        return base
    return f"{root.parent.name}--{base}"


def register_board(root: Path) -> tuple[str, bool]:
    root = root.resolve()
    boards = load_registry()
    slug = slug_for(root, boards)
    fresh = slug not in boards
    entry = {"path": str(root), "registered_at": boards.get(slug, {}).get("registered_at") or utc_now_iso()}
    board_id = board_lib.read_federation(root / ".manna").get("board_id")
    if board_id:
        entry["board_id"] = board_id
    boards[slug] = entry
    save_registry(boards)
    return slug, fresh


def scan_boards(scan_root: Path) -> list[Path]:
    found: list[Path] = []

    def walk(directory: Path, depth: int) -> None:
        if (directory / ".manna").is_dir():
            found.append(directory)
        if depth >= SCAN_DEPTH:
            return
        try:
            children = sorted(p for p in directory.iterdir() if p.is_dir() and not p.is_symlink())
        except OSError:
            return
        for child in children:
            if child.name in SCAN_SKIP or child.name.startswith("."):
                continue
            walk(child, depth + 1)

    walk(scan_root, 0)
    return found


# ---------------------------------------------------------------- daemon state


def read_daemon() -> dict[str, Any] | None:
    path = daemon_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def health(host: str, port: int) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("server") == SERVER_NAME else {"foreign": True}


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ---------------------------------------------------------------- HTTP


# Digests need a model; the house flag family decides (AGENT_DO_SERVE_AI, then
# AGENT_DO_AI), and a missing credential simply leaves rows on their titles.
def _digests_enabled() -> bool:
    try:
        sys.path.insert(0, str(SERVE_DIR.parents[2] / "lib"))
        from ai_router import ai_requested  # type: ignore
        return ai_requested(digest_lib.FLAG_NAME)
    except Exception:
        return False


DIGESTS_ENABLED = _digests_enabled()


def coord_digest(peers: list[dict[str, Any]], coord: dict[str, Any]) -> str:
    """Content digest of a presence snapshot with the clock taken out.

    age/age_seconds and pulse.updated_at move every time the snapshot is
    read, with zero underlying events; a digest that includes them re-signs
    unchanged peers on every refresh and turns each re-sign into a full
    state rebuild. What remains changes only when something happened."""
    stable_peers = []
    for peer in peers:
        slim = {k: v for k, v in peer.items() if k not in ("age", "age_seconds")}
        if isinstance(slim.get("pulse"), dict):
            slim["pulse"] = {k: v for k, v in slim["pulse"].items() if k != "updated_at"}
        stable_peers.append(slim)
    return hashlib.sha256(json.dumps({"p": stable_peers, "c": coord}, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


# Buckets whose rows the page renders directly. The core serializes each as an
# independent copy; the page applies live coordination overlays once, so every
# bucket must alias the same row objects as all[]. Cached presentation fields
# already arrive on every copy through the canonical state contract.
ROW_BUCKETS = ("now", "next", "decisions", "dreams", "unlayered")


def hydrate_buckets(state: dict[str, Any]) -> None:
    """Re-share row objects: every rendered bucket points at the same dict as
    all[], keyed by id, so per-row enrichment applied once reaches every
    sheet — including waves[].items and tracks[].items."""
    index = {row.get("id"): row for row in state.get("all") or [] if isinstance(row, dict)}

    def swap(rows: list[Any]) -> list[Any]:
        return [index.get(row.get("id"), row) if isinstance(row, dict) else row for row in rows]

    for key in ROW_BUCKETS:
        if isinstance(state.get(key), list):
            state[key] = swap(state[key])
    for wave in state.get("waves") or []:
        if isinstance(wave, dict) and isinstance(wave.get("items"), list):
            wave["items"] = swap(wave["items"])
    for track in state.get("tracks") or []:
        if isinstance(track, dict) and isinstance(track.get("items"), list):
            track["items"] = swap(track["items"])


def mark_coordination_unknown(state: dict[str, Any]) -> None:
    """Coordination not read yet ships as explicitly unknown, never as zero:
    null peers/coord/attention (the page says "still reading"), and a
    claimant whose liveness nobody has observed says "unknown", not
    "unseen" — unseen is a verdict, unknown is the absence of one."""
    state["peers"] = None
    state["coord"] = None
    state["attention"] = None
    for row in state.get("all") or []:
        claimant = row.get("claimant") if isinstance(row, dict) else None
        if isinstance(claimant, dict):
            claimant["liveness"] = "unknown"
            claimant["attention"] = "unknown"


def prepare_digests(slug: str, state: dict[str, Any], schedule_missing: bool) -> None:
    """Plan missing digest generation without decorating canonical rows.

    `manna state` owns cache attachment. Serve only schedules gaps, and the
    cache file's change re-signs the page.
    """
    report = digest_lib.plan(slug, state.get("all") or [])
    state["digests"] = {"ready": report["ready"], "missing": report["missing"], "model": report["model"], "generating": False}
    if schedule_missing and report["missing_rows"] and DIGESTS_ENABLED:
        state["digests"]["generating"] = digest_lib.schedule(slug, report["missing_rows"])


class BoardCache:
    """Two clocks. Board and git state is keyed by a file signature and
    recomputed only when those files move; the drift a reconcile finds is
    computed in the background per durable board signature and stamped into
    the signature when it lands, so a page load never waits on it. Coord
    presence is refreshed on a cadence and carries a content digest, so
    streams push when live attention changes even if no repository file
    moved — and the same snapshot that signs a state is the one folded into
    its payload."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.gitdirs: dict[str, Path | None] = {}
        self.bundles: dict[str, dict[str, Any]] = {}
        self.states: dict[str, tuple[str, dict[str, Any]]] = {}
        self.drifts: dict[str, dict[str, Any]] = {}
        self.drift_jobs: dict[str, tuple[str, threading.Thread]] = {}
        self.drift_done: dict[str, str] = {}
        self.drift_stamps: dict[str, int] = {}
        self.build_locks: dict[str, threading.Lock] = {}

    def gitdir(self, root: Path) -> Path | None:
        key = str(root)
        with self.lock:
            if key in self.gitdirs:
                return self.gitdirs[key]
        value = board_lib.git_dir(root)
        with self.lock:
            self.gitdirs[key] = value
        return value

    def base_signature(self, root: Path) -> str:
        return board_lib.base_signature(root, self.gitdir(root))

    def digest_signature(self, slug: str) -> str:
        path = digest_lib.cache_path(slug)
        try:
            st = path.stat()
            return f"digests:{st.st_mtime_ns}:{st.st_size}"
        except OSError:
            return "digests:none"

    # -- presence clock

    def bundle(self, root: Path, now: float | None = None) -> dict[str, Any]:
        """Peers + claims/drops/needs, at most COORD_REFRESH_SECONDS old."""
        key = str(root)
        now = time.monotonic() if now is None else now
        with self.lock:
            cached = self.bundles.get(key)
            if cached and now - cached["fetched_at"] < COORD_REFRESH_SECONDS:
                return cached
        if self.gitdir(root) is None:
            peers, coord = [], board_lib.EMPTY_COORD
        else:
            peers = board_lib.coord_peers(root, AGENT_DO)
            coord = board_lib.coord_snapshot(root, AGENT_DO, peers) if peers else board_lib.EMPTY_COORD
        value = {"fetched_at": now, "peers": peers, "coord": coord, "digest": coord_digest(peers, coord), "glance": board_lib.glance_from_peers(peers)}
        with self.lock:
            self.bundles[key] = value
        return value

    def refresh_bundles(self, roots: list[Path]) -> None:
        """Bring every stale bundle current in parallel, one worker per core."""
        now = time.monotonic()
        with self.lock:
            stale = [r for r in roots if not (self.bundles.get(str(r)) and now - self.bundles[str(r)]["fetched_at"] < COORD_REFRESH_SECONDS)]
        if not stale:
            return
        workers = max(1, min(len(stale), os.cpu_count() or 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda r: self.bundle(r, now), stale))

    # -- drift clock

    def schedule_drift(self, key: str, root: Path, base_sig: str) -> None:
        """One background reconcile per board at a time, per base signature.

        Live drift is `manna reconcile --json`, and reconcile serializes on
        the board lock with every other consumer (SessionEnd hooks, other
        pages, the daemon's own refresh): measured 41.7s of lock convoy on a
        242-row board. A page load never waits on it — the state ships the
        last finished drift, a background run brings it current, and the
        drift stamp in the stream signature pushes the update when it lands.
        """
        with self.lock:
            job = self.drift_jobs.get(key)
            if job and job[0] == base_sig and job[1].is_alive():
                return
            if self.drift_done.get(key) == base_sig:
                return

            def run() -> None:
                drift = board_lib.live_drift(root, AGENT_DO)
                with self.lock:
                    if drift is not None:
                        self.drifts[key] = drift
                    self.drift_done[key] = base_sig
                    self.drift_stamps[key] = self.drift_stamps.get(key, 0) + 1

            thread = threading.Thread(target=run, name=f"drift:{root.name}", daemon=True)
            self.drift_jobs[key] = (base_sig, thread)
            thread.start()

    def overlay_drift(self, key: str, state: dict[str, Any]) -> None:
        """The last finished background reconcile replaces the file read, in
        the same shape the core emits for a live run; the file part stays
        beside it so the page can still show the written drift's age."""
        with self.lock:
            live = self.drifts.get(key)
        if not live:
            return
        file_part = state["drift"].get("file") if isinstance(state.get("drift"), dict) else None
        state["drift"] = {
            "present": True,
            "generated_at": live.get("generated_at"),
            "findings": live.get("findings") or [],
            "count": live.get("count", 0),
            "kinds": live.get("kinds") or {},
            "source": "reconcile",
            "file": file_part,
        }

    # -- the page

    def signature(self, root: Path, slug: str | None = None, bundle: dict[str, Any] | None = None) -> str:
        """What a board stream watches: board/git files, live presence,
        federation targets, the drift stamp (bumped when a background
        reconcile finishes, so the page updates without having waited), and
        the optional digest cache."""
        bundle = bundle if bundle is not None else self.bundle(root)
        sig = (self.base_signature(root) + "|coord:" + bundle["digest"]
               + "|federation:" + federation_signature()
               + "|drift:" + str(self.drift_stamps.get(str(root), 0)))
        if slug:
            sig += "|" + self.digest_signature(slug)
        return sig

    def build_lock(self, slug: str) -> threading.Lock:
        with self.lock:
            return self.build_locks.setdefault(slug, threading.Lock())

    def state(self, slug: str, root: Path) -> tuple[str, dict[str, Any]]:
        bundle = self.bundle(root)
        sig = self.signature(root, slug, bundle)
        with self.lock:
            cached = self.states.get(slug)
            if cached and cached[0] == sig:
                return cached
        # Singleflight: the first request per signature derives; concurrent
        # requests (initial fetch, SSE, summary, ask, handoff) wait on the
        # same lock and leave with the state that request built.
        with self.build_lock(slug):
            with self.lock:
                cached = self.states.get(slug)
                if cached and cached[0] == sig:
                    return cached
            key = str(root)
            # Cached-drift core read, with the very snapshot that signed this
            # state folded in by the core. A full state never reconciles
            # inline (old serve.py measured the 41.7s lock convoy; the rebase
            # reintroduced it inline at 36-60s per page).
            state = board_lib.derive(
                root, None, decision_markers(), live=False,
                coord={"peers": bundle["peers"], "coord": bundle["coord"]},
            )
            hydrate_buckets(state)
            self.overlay_drift(key, state)
            state["slug"] = slug
            state["coord_refreshed_ago"] = round(time.monotonic() - bundle["fetched_at"], 1)
            state["coord_refresh_seconds"] = COORD_REFRESH_SECONDS
            state["act_token"] = ACT_TOKEN
            state["actor"] = serve_identity()["session_id"]
            prepare_digests(slug, state, schedule_missing=True)
            if self.gitdir(root) is not None:
                self.schedule_drift(key, root, self.base_signature(root))
            with self.lock:
                self.states[slug] = (sig, state)
        return sig, state

    def glance(self, root: Path) -> dict[str, Any]:
        return self.bundle(root)["glance"]

    def glance_if_warm(self, root: Path) -> dict[str, Any] | None:
        """Whatever presence we already hold, however old; None means unread.
        The fast index shows this instantly and the full read replaces it."""
        with self.lock:
            cached = self.bundles.get(str(root))
        return cached["glance"] if cached else None


CACHE = BoardCache()


EMPTY_GLANCE = {"attention": {}, "needs_you": 0, "working": 0, "here": 0, "gone": 0}


def index_row(slug: str, entry: dict[str, Any], markers: tuple[str, ...], fast: bool = False) -> dict[str, Any]:
    root = Path(entry.get("path", ""))
    if root.is_dir() and (root / ".manna").is_dir():
        row = board_lib.summary(root, markers)
        row["coord"] = CACHE.glance_if_warm(root) if fast else CACHE.glance(root)
    else:
        row = {"name": root.name, "root": str(root), "exists": False, "total": 0, "status_counts": {}, "dreams": 0, "decisions": 0, "drift_count": 0, "drift_generated_at": None, "latest_update": None, "issues_modified_at": None, "coord": EMPTY_GLANCE}
    row["slug"] = slug
    row["url"] = f"/{urllib.parse.quote(slug)}"
    return row


def registered_roots(boards: dict[str, dict[str, Any]]) -> list[Path]:
    return [Path(e.get("path", "")) for e in boards.values() if (Path(e.get("path", "")) / ".manna").is_dir()]


def federation_signature() -> str:
    """Every registered identity and target row that can change a derived
    relation read. A target transition must wake the source board stream even
    though it changes zero bytes in the source checkout."""
    parts = []
    try:
        stat = registry_path().stat()
        parts.append(f"registry:{stat.st_mtime_ns}:{stat.st_size}")
    except OSError:
        parts.append("registry:missing")
    for slug, entry in sorted(load_registry().items()):
        root = Path(entry.get("path", ""))
        for relative in (".manna/federation.yaml", ".manna/issues.jsonl"):
            path = root / relative
            try:
                stat = path.stat()
                parts.append(f"{slug}:{relative}:{stat.st_mtime_ns}:{stat.st_size}")
            except OSError:
                parts.append(f"{slug}:{relative}:missing")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def resolved_relations(root: Path) -> dict[str, Any] | None:
    """Ask the Rust read path for the same resolver semantics the CLI exposes.
    The daemon never reimplements replica selection or writes either board."""
    if not board_lib.read_federation(root / ".manna").get("enabled"):
        return None
    out = board_lib.run(
        [str(AGENT_DO), "manna", "relations", "--resolve", "--json"],
        root,
        timeout=30,
    )
    if not out:
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data.get("success") or not isinstance(data.get("relations"), list):
        return None
    return data


def attach_resolved_relations(state: dict[str, Any], payload: dict[str, Any] | None) -> None:
    if not payload:
        return
    reports = [row for row in payload.get("relations", []) if isinstance(row, dict)]
    by_source: dict[str, list[dict[str, Any]]] = {}
    for report in reports:
        source = report.get("from")
        if isinstance(source, str):
            by_source.setdefault(source, []).append(report)
    for row in state.get("all", []):
        if isinstance(row, dict):
            row["relations"] = by_source.get(row.get("id"), [])
    federation = state.get("federation")
    if isinstance(federation, dict):
        federation["relations"] = reports
        federation["resolved"] = True


# A bundle this much older than its cadence is history, not presence: the
# fast path folds it in only while it could still describe the live room.
FAST_BUNDLE_MAX_AGE = COORD_REFRESH_SECONDS * 3


def fast_state(slug: str, root: Path) -> dict[str, Any]:
    """The cached-drift core model, so every sheet paints before live coord
    and reconcile complete. An already-warm coord bundle is folded in whole;
    a cold one ships as explicitly unknown, never as zero peers. `building`
    marks the intentional live-data gap either way."""
    with CACHE.lock:
        bundle = CACHE.bundles.get(str(root))
    warm = bundle is not None and time.monotonic() - bundle["fetched_at"] < FAST_BUNDLE_MAX_AGE
    if not warm:
        threading.Thread(target=lambda: CACHE.bundle(root), name=f"warm:{slug}", daemon=True).start()
    state = board_lib.derive(
        root, None, decision_markers(), live=False,
        coord={"peers": bundle["peers"], "coord": bundle["coord"]} if warm else None,
    )
    hydrate_buckets(state)
    if not warm:
        mark_coordination_unknown(state)
    prepare_digests(slug, state, schedule_missing=False)
    state.update({
        "slug": slug,
        "act_token": ACT_TOKEN,
        "actor": serve_identity()["session_id"],
        "coord_refresh_seconds": COORD_REFRESH_SECONDS,
        "coord_refreshed_ago": round(time.monotonic() - bundle["fetched_at"], 1) if warm else None,
        "building": True,
    })
    return state


def boards_index(fast: bool = False) -> dict[str, Any]:
    """The estate view. `fast` answers from what is already in hand — manna
    counts always, presence only where a bundle is warm — so the page can
    paint immediately and say honestly that coord is still being read."""
    boards = load_registry()
    markers = decision_markers()
    items = sorted(boards.items())
    if not fast:
        CACHE.refresh_bundles(registered_roots(boards))
    # One coord read per board on a cold cache; fan out one worker per core
    # (os.cpu_count() is the authority) so 30+ boards answer in one read's time.
    workers = max(1, min(len(items) or 1, os.cpu_count() or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(lambda kv: index_row(kv[0], kv[1], markers, fast), items))
    # needs-you first, then freshest, missing boards last
    rows.sort(key=lambda r: r.get("latest_update") or "", reverse=True)
    rows.sort(key=lambda r: (not r["exists"], -(r.get("coord") or {}).get("needs_you", 0), -(r.get("coord") or {}).get("working", 0)))
    totals = {
        "needs_you": sum((r.get("coord") or {}).get("needs_you", 0) for r in rows),
        "working": sum((r.get("coord") or {}).get("working", 0) for r in rows),
        "here": sum((r.get("coord") or {}).get("here", 0) for r in rows),
    }
    building = sum(1 for r in rows if r["exists"] and r.get("coord") is None)
    return {"generated_at": utc_now_iso(), "boards": rows, "count": len(rows), "registry": str(registry_path()), "decision_markers": list(markers), "totals": totals, "building": building}


def index_signature() -> str:
    parts = []
    try:
        st = registry_path().stat()
        parts.append(f"registry:{st.st_mtime_ns}:{st.st_size}")
    except OSError:
        parts.append("registry:missing")
    boards = load_registry()
    CACHE.refresh_bundles(registered_roots(boards))
    for slug, entry in sorted(boards.items()):
        root = Path(entry.get("path", ""))
        parts.append(slug + "=" + (CACHE.signature(root) if (root / ".manna").is_dir() else "missing"))
    return "|".join(parts)


class Handler(SimpleHTTPRequestHandler):
    server_version = f"{SERVER_NAME}/1.0"
    protocol_version = "HTTP/1.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write(f"[{self.log_date_time_string()}] {fmt % args}\n")
        sys.stdout.flush()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    # -- helpers

    def send_bytes(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_bytes(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), "application/json; charset=utf-8", status)

    def send_page(self, name: str) -> None:
        path = STATIC_DIR / name
        self.send_bytes(path.read_bytes(), "text/html; charset=utf-8")

    def resolve_board(self, slug: str) -> Path | None:
        entry = load_registry().get(slug)
        if not entry:
            return None
        root = Path(entry.get("path", ""))
        return root if (root / ".manna").is_dir() else None

    # -- routing

    def host_allowed(self) -> bool:
        """Refuse DNS rebinding: a page elsewhere can point its own hostname at
        127.0.0.1, and the browser would then send that hostname here. Only a
        loopback name, or the address this daemon bound, may address it."""
        raw = (self.headers.get("Host") or "").strip().lower()
        if raw.startswith("["):
            host = raw.split("]", 1)[0].lstrip("[")
        else:
            host = raw.rsplit(":", 1)[0] if raw.count(":") == 1 else raw
        bound = str(self.server.server_address[0]).lower()
        if host not in LOOPBACK_HOSTS and host != bound:
            return False
        # Same rule for a browser-sent Origin: absent is fine (navigation,
        # curl); present, it must be a loopback page too.
        origin = (self.headers.get("Origin") or "").strip().lower()
        if origin and origin != "null":
            origin_host = urllib.parse.urlsplit(origin).hostname or ""
            if origin_host not in LOOPBACK_HOSTS and origin_host != bound:
                return False
        return True

    def do_POST(self) -> None:  # noqa: N802
        if not self.host_allowed():
            return self.send_json({"error": "host not allowed"}, HTTPStatus.FORBIDDEN)
        parsed = urllib.parse.urlparse(self.path)
        parts = [urllib.parse.unquote(p) for p in parsed.path.split("/") if p]
        if len(parts) != 3 or parts[1:] != ["api", "act"]:
            return self.send_json({"error": "unknown path"}, HTTPStatus.NOT_FOUND)
        root = self.resolve_board(parts[0])
        if root is None:
            return self.send_json({"error": "no such board"}, HTTPStatus.NOT_FOUND)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, OSError):
            return self.send_json({"error": "bad request body"}, HTTPStatus.BAD_REQUEST)
        if not isinstance(body, dict) or body.get("token") != ACT_TOKEN:
            return self.send_json({"error": "act token missing or stale; reload the page"}, HTTPStatus.FORBIDDEN)
        result = perform(parts[0], root, str(body.get("action") or ""), body.get("id") if isinstance(body.get("id"), str) else None, bool(body.get("confirm")))
        return self.send_json(result, HTTPStatus.OK if result.get("ok") or result.get("needs_confirm") else HTTPStatus.CONFLICT)

    def do_GET(self) -> None:  # noqa: N802
        if not self.host_allowed():
            return self.send_json({"error": "host not allowed; address this daemon by 127.0.0.1 or localhost"}, HTTPStatus.FORBIDDEN)
        parsed = urllib.parse.urlparse(self.path)
        parts = [urllib.parse.unquote(p) for p in parsed.path.split("/") if p]

        if not parts:
            return self.send_page("index.html")
        if parts[0] == "api":
            return self.route_api(parts[1:], parsed.query)
        if parts[0] == "static":
            self.path = "/" + "/".join(parts[1:])
            return super().do_GET()

        slug = parts[0]
        root = self.resolve_board(slug)
        if root is None:
            return self.send_json({"error": f"no registered board named {slug!r}; run `agent-do manna serve` inside the project"}, HTTPStatus.NOT_FOUND)
        rest = parts[1:]
        if not rest:
            return self.send_page("board.html")
        # A derive failure (stale binary, malformed board row, dead core) is
        # an answer, not a dropped connection: the page gets a structured
        # error payload it can show instead of a disconnect.
        try:
            if rest == ["api", "state"]:
                if urllib.parse.parse_qs(parsed.query).get("fast", ["0"])[0] == "1":
                    return self.send_json(fast_state(slug, root))
                _, state = CACHE.state(slug, root)
                return self.send_json(state)
            if rest == ["api", "events"]:
                return self.stream(lambda: CACHE.signature(root, slug), lambda: CACHE.state(slug, root)[1])
            if rest == ["api", "summary"]:
                return self.send_summary(slug, root, parsed.query)
            if rest == ["api", "handoff"]:
                return self.send_handoff(slug, root, parsed.query)
            if rest == ["api", "ask"]:
                question = urllib.parse.parse_qs(parsed.query).get("q", [""])[0]
                if not DIGESTS_ENABLED:
                    return self.send_json({"answer": None, "cited": [], "error": "asking needs a model credential (AGENT_DO_SERVE_AI)"})
                _, state = CACHE.state(slug, root)
                return self.send_json(digest_lib.ask(state.get("all", []), question))
        except RuntimeError as error:
            sys.stdout.write(f"[error] {slug} {'/'.join(rest)}: {error}\n"); sys.stdout.flush()
            return self.send_json({"error": str(error), "slug": slug}, HTTPStatus.INTERNAL_SERVER_ERROR)
        return self.send_json({"error": "unknown path"}, HTTPStatus.NOT_FOUND)

    def route_api(self, parts: list[str], query: str) -> None:
        if parts == ["health"]:
            return self.send_json({"server": SERVER_NAME, "pid": os.getpid(), "port": self.server.server_address[1], "boards": len(load_registry()), "started_at": getattr(self.server, "started_at", None), "source": SOURCE_HASH, "digests": DIGESTS_ENABLED})
        if parts == ["boards"]:
            fast = urllib.parse.parse_qs(query).get("fast", ["0"])[0] == "1"
            return self.send_json(boards_index(fast))
        if parts == ["events"]:
            return self.stream(index_signature, boards_index)
        return self.send_json({"error": "unknown api path"}, HTTPStatus.NOT_FOUND)

    def send_summary(self, slug: str, root: Path, query: str) -> None:
        _send_summary(self, slug, root, query)

    def send_handoff(self, slug: str, root: Path, query: str) -> None:
        """The paired handoff document itself, for the copy button.

        The board row names the file; the daemon still refuses to read outside
        the handoff root — a hand-edited prompt field must not become a file
        oracle for whatever the daemon's user can read.
        """
        issue_id = urllib.parse.parse_qs(query).get("id", [""])[0]
        if not issue_id:
            return self.send_json({"error": "id required"}, HTTPStatus.BAD_REQUEST)
        _, state = CACHE.state(slug, root)
        row = next((r for r in state.get("all", []) if r.get("id") == issue_id), None)
        if row is None:
            return self.send_json({"error": f"no issue {issue_id!r} on this board"}, HTTPStatus.NOT_FOUND)
        prompt = row.get("prompt")
        if not prompt:
            return self.send_json({"error": f"{issue_id} has no paired handoff"}, HTTPStatus.NOT_FOUND)
        handoff_root = (root / ".handoff").resolve()
        local = (root / str(prompt)).resolve()
        if not (local.is_relative_to(handoff_root) and local.suffix == ".md"):
            return self.send_json({"error": "handoff path escapes .handoff/"}, HTTPStatus.FORBIDDEN)
        if not local.is_file():
            return self.send_json({"error": f"handoff file missing: {prompt}"}, HTTPStatus.NOT_FOUND)
        return self.send_json({
            "id": issue_id,
            "path": str(prompt),
            "content": local.read_text(encoding="utf-8", errors="replace"),
        })

    def stream(self, signature_fn, payload_fn) -> None:
        """Server-sent events: a fresh payload whenever the signature moves."""
        self.close_connection = True
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        previous = None
        reported = None
        try:
            while not getattr(self.server, "stopping", False):
                # A derive failure must not tear the stream down: the page
                # keeps its last state, and the next tick retries.
                try:
                    sig = signature_fn()
                    if sig != previous:
                        payload = json.dumps(payload_fn(), ensure_ascii=False, separators=(",", ":"))
                        self.wfile.write(f"event: state\ndata: {payload}\n\n".encode("utf-8"))
                        previous = sig
                    else:
                        self.wfile.write(b": hb\n\n")
                except RuntimeError as error:
                    if str(error) != reported:
                        reported = str(error)
                        sys.stdout.write(f"[stream error] {error}\n"); sys.stdout.flush()
                    self.wfile.write(b": hb\n\n")
                self.wfile.flush()
                time.sleep(POLL_INTERVAL_SECONDS)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


def _send_summary(handler: "Handler", slug: str, root: Path, query: str) -> None:
    issue_id = urllib.parse.parse_qs(query).get("id", [""])[0]
    _, state = CACHE.state(slug, root)
    row = next((r for r in state.get("all", []) if r.get("id") == issue_id), None)
    if row is None:
        return handler.send_json({"error": "no such item on this board"}, HTTPStatus.NOT_FOUND)
    if not DIGESTS_ENABLED:
        return handler.send_json({"id": issue_id, "summary": None, "error": "summaries need a model credential (AGENT_DO_SERVE_AI)"})
    result = digest_lib.summarize(slug, row)
    result["id"] = issue_id
    return handler.send_json(result)


def run_server(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.started_at = utc_now_iso()
    server.stopping = False
    bound_port = server.server_address[1]
    daemon_path().write_text(
        json.dumps({"pid": os.getpid(), "host": host, "port": bound_port, "started_at": server.started_at, "log": str(log_path())}, indent=2) + "\n",
        encoding="utf-8",
    )

    def stop(*_: Any) -> None:
        server.stopping = True
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def watch_source() -> None:
        # The CLI restarts a stale daemon, but a daemon nobody touches via
        # the CLI serves yesterday's code forever (observed: a day-old
        # process behind a day of fixes). The daemon watches its own three
        # files and execs itself in place when they change.
        while not server.stopping:
            time.sleep(POLL_INTERVAL_SECONDS * 5)
            try:
                if source_hash() != SOURCE_HASH:
                    os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), "--foreground", "--host", host, "--port", str(bound_port)])
            except OSError:
                continue

    threading.Thread(target=watch_source, name="source-watch", daemon=True).start()
    print(f"{SERVER_NAME}: http://{host}:{bound_port}/  (read-only; boards register via `agent-do manna serve`)")
    sys.stdout.flush()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            current = read_daemon()
            if current and current.get("pid") == os.getpid():
                daemon_path().unlink()
        except OSError:
            pass


# ---------------------------------------------------------------- CLI


def ensure_daemon(host: str, port: int) -> dict[str, Any]:
    """Return {'status': running|started, 'port': N, 'pid': P} or raise RuntimeError."""
    existing = read_daemon()
    if existing and pid_alive(int(existing.get("pid", 0))):
        live = health(existing.get("host", host), int(existing.get("port", port)))
        if live and not live.get("foreign"):
            if live.get("source") == SOURCE_HASH:
                return {"status": "running", "port": int(existing["port"]), "pid": int(existing["pid"]), "host": existing.get("host", host)}
            # The code on disk moved under the daemon: restart so the page
            # renders the current derivation, not the one it booted with.
            stop_daemon()
            port = int(existing.get("port", port))
    probe = health(host, port)
    if probe and not probe.get("foreign"):
        if probe.get("source") == SOURCE_HASH:
            return {"status": "running", "port": port, "pid": probe.get("pid"), "host": host}
        raise RuntimeError(f"a {SERVER_NAME} on port {port} runs different code and is not this home's daemon; stop it or pick another --port")
    if probe and probe.get("foreign"):
        raise RuntimeError(f"port {port} is held by something that is not {SERVER_NAME}; pick another with --port")

    log = log_path().open("ab")
    child = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--foreground", "--host", host, "--port", str(port)],
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        cwd=str(serve_home()),
    )
    # Wait for the child's own health answer or its exit: no timeout literal,
    # the child's fate is the clock.
    while child.poll() is None:
        current = read_daemon()
        if current and current.get("pid") == child.pid:
            live = health(host, int(current["port"]))
            if live and not live.get("foreign"):
                return {"status": "started", "port": int(current["port"]), "pid": child.pid, "host": host}
        time.sleep(POLL_INTERVAL_SECONDS / 10)
    raise RuntimeError(f"daemon exited with code {child.returncode}; see {log_path()}")


def stop_daemon() -> dict[str, Any]:
    current = read_daemon()
    if not current or not pid_alive(int(current.get("pid", 0))):
        if current:
            try:
                daemon_path().unlink()
            except OSError:
                pass
        return {"status": "not_running"}
    pid = int(current["pid"])
    os.kill(pid, signal.SIGTERM)
    while pid_alive(pid):
        time.sleep(POLL_INTERVAL_SECONDS / 10)
    try:
        daemon_path().unlink()
    except OSError:
        pass
    return {"status": "stopped", "pid": pid}


def emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
        return
    if "url" in payload:
        print(payload["url"])
    for key in ("daemon", "slug", "board", "index"):
        if key in payload and key != "url":
            print(f"  {key}: {payload[key]}")
    if payload.get("note"):
        print(f"  {payload['note']}")


HELP = """Usage: agent-do manna serve [--open] [--json] [--port N] [--host H]
       agent-do manna serve --status | --stop | --scan <dir> | --foreground

Human window onto the board. Read-only. Agents keep `manna context|list|show`.

Running inside a project registers its board with the estate daemon, starts
the daemon if needed, and prints the project URL:
  http://127.0.0.1:<port>/<project>    this board
  http://127.0.0.1:<port>/             every registered board

Options:
  --open           open the project page in the default browser
  --json           machine-readable result
  --port N         daemon port (default: free port picked on first run and
                   kept in $AGENT_DO_HOME/manna/serve/config.json; env
                   override MANNA_SERVE_PORT)
  --host H         bind address (default 127.0.0.1; keep it local)
  --status         is the daemon up, which boards are registered
  --stop           stop the daemon
  --scan <dir>     register every board found up to three levels below <dir>
  --decision-marker "[NAME]"
                   add a leading title tag that means "a human must rule" on this
                   machine (shipped defaults: [DECISION] [HUMAN] [OWNER])
  --foreground     run the daemon in this process (what the daemon itself runs)
"""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="agent-do manna serve", add_help=False)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--json", action="store_true")
    env_port = os.environ.get("MANNA_SERVE_PORT")
    parser.add_argument("--port", type=int, default=int(env_port) if env_port else None)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--scan", metavar="DIR")
    parser.add_argument("--decision-marker", metavar="TAG", action="append", default=[])
    parser.add_argument("--foreground", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    args = parser.parse_args(argv)
    if args.port is None:
        args.port = resolved_port()

    if args.help:
        print(HELP, end="")
        return 0
    if args.foreground:
        run_server(args.host, args.port)
        return 0
    if args.stop:
        emit(stop_daemon(), args.json)
        return 0
    if args.status:
        current = read_daemon()
        live = None
        if current and pid_alive(int(current.get("pid", 0))):
            live = health(current.get("host", args.host), int(current.get("port", args.port)))
        boards = load_registry()
        payload = {
            "running": bool(live and not live.get("foreign")),
            "daemon": current if live else None,
            "index": f"http://{current.get('host', args.host)}:{current.get('port')}/" if live and current else None,
            "boards": {slug: entry.get("path") for slug, entry in sorted(boards.items())},
            "count": len(boards),
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print("running:", payload["running"], "" if not payload["index"] else payload["index"])
            for slug, path in payload["boards"].items():
                print(f"  /{slug}  {path}")
        return 0

    if args.decision_marker:
        try:
            for tag in args.decision_marker:
                markers = add_decision_marker(tag)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        payload = {"decision_markers": list(decision_markers()), "added": markers}
        print(json.dumps(payload, indent=2) if args.json else "decision markers: " + " ".join(payload["decision_markers"]))
        if not args.scan and board_lib.find_board_root(Path.cwd()) is None:
            return 0

    if args.scan:
        found = scan_boards(Path(args.scan))
        added = []
        for root in found:
            slug, fresh = register_board(root)
            added.append({"slug": slug, "path": str(root), "new": fresh})
        payload = {"scanned": str(Path(args.scan).resolve()), "found": len(found), "registered": added}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"found {len(found)} boards under {payload['scanned']}")
            for row in added:
                print(f"  {'+' if row['new'] else '='} /{row['slug']}  {row['path']}")
        if not found:
            return 0

    root = board_lib.find_board_root(Path.cwd())
    if root is None and not args.scan:
        message = "no .manna/ here or above; run inside a project with a board (or `agent-do manna init`)"
        if args.json:
            print(json.dumps({"success": False, "error": message}))
        else:
            print(message, file=sys.stderr)
        return 2

    try:
        daemon = ensure_daemon(args.host, args.port)
    except RuntimeError as error:
        if args.json:
            print(json.dumps({"success": False, "error": str(error)}))
        else:
            print(f"error: {error}", file=sys.stderr)
        return 1

    base = f"http://{daemon['host']}:{daemon['port']}"
    payload: dict[str, Any] = {"success": True, "daemon": daemon["status"], "pid": daemon["pid"], "port": daemon["port"], "index": f"{base}/"}
    if root is not None:
        slug, _ = register_board(root)
        payload.update({"slug": slug, "board": str(root), "url": f"{base}/{urllib.parse.quote(slug)}"})
        if args.open:
            webbrowser.open(payload["url"])
    else:
        payload["url"] = payload["index"]
        if args.open:
            webbrowser.open(payload["index"])
    payload["note"] = "read-only human view; agents use `agent-do manna context`"
    emit(payload, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
