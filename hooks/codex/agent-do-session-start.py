#!/usr/bin/env python3
"""Codex SessionStart hook: inject compact agent-do project context."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ZPC_INJECT_TIMEOUT = 3
ZPC_AUTOINIT_TIMEOUT = 3

# Wall-clock bound on one JSON read from agent-do. The coord pair spends it
# once between them rather than twice in turn, because they run at the same
# time; every other read here spends it alone.
JSON_READ_TIMEOUT = 4

# No size bound lives here any more, and its absence is the fix. `zpc inject`
# fits its own blob to a budget read from the quantity authority and marks any
# cut with both numbers; a second cut applied here could only land at a byte
# offset, because this file holds none of the sections and cannot weigh them.
# It used to cut at 6000 characters, which against a real store meant the
# session got the protocol header, no claims at all, and four words admitting
# something had gone missing. What a hook owes a session is promptness, and
# ZPC_INJECT_TIMEOUT above is the whole of that obligation.


def read_payload() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def resolve_agent_do() -> str | None:
    direct = shutil.which("agent-do")
    if direct:
        return direct

    local = Path.home() / ".local" / "bin" / "agent-do"
    if local.exists():
        return str(local)

    breadcrumb = Path.home() / ".agent-do" / "install-path"
    if breadcrumb.exists():
        candidate = Path(breadcrumb.read_text().strip()) / "agent-do"
        if candidate.exists():
            return str(candidate)

    return None


def run_json(cmd: list[str], cwd: str | None = None) -> dict:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=JSON_READ_TIMEOUT,
            check=False,
        )
    except Exception:
        return {}
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {}


def run_capture(cmd: list[str], cwd: str | None = None, timeout: int = 10) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return (1, "", "")
    return (proc.returncode, proc.stdout, proc.stderr)


def native_bootstrap(agent_do: str, cwd: str | None, ask: str, root: str) -> bool:
    mode = os.environ.get("AGENT_DO_BOOTSTRAP_PROMPT_MODE", "").strip().lower()
    if not mode:
        mode = "native" if sys.platform == "darwin" and shutil.which("osascript") else "context"

    if mode == "disabled":
        return True
    if mode != "native":
        return False

    auto_response = os.environ.get("AGENT_DO_BOOTSTRAP_AUTO_RESPONSE", "").strip().lower()
    # Only a person who answered the dialog may be shown a second, blocking
    # failure dialog; an auto-response is a script with nobody at the screen.
    answered_by_person = auto_response not in ("bootstrap", "not_now")
    if auto_response == "bootstrap":
        response = "Bootstrap"
    elif auto_response == "not_now":
        response = "Not now"
    else:
        if not shutil.which("osascript"):
            return False
        code, stdout, _ = run_capture(
            [
                "osascript",
                "-e",
                (
                    f'display dialog {json.dumps(ask)} '
                    'with title "agent-do Bootstrap" '
                    'buttons {"Not now", "Bootstrap"} default button "Bootstrap"\n'
                    "button returned of result"
                ),
            ],
            timeout=15,
        )
        if code != 0:
            return False
        response = stdout.strip()

    if response == "Bootstrap":
        # Capture output to a log; emit a macOS notification with status; on
        # failure also surface a follow-up dialog with the option to view the
        # log. Without this the user clicks Bootstrap and sees nothing.
        log_dir = Path.home() / ".agent-do" / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            log_dir = Path("/tmp")
        timestamp = subprocess.run(
            ["date", "+%Y%m%d-%H%M%S"], capture_output=True, text=True, check=False
        ).stdout.strip() or "now"
        log_file = log_dir / f"bootstrap-{timestamp}-{os.getpid()}.log"
        project_label = Path(root).name or root

        try:
            with log_file.open("w") as fh:
                fh.write(f"agent-do bootstrap --yes\nproject: {root}\nstarted: {timestamp}\n---\n")
                fh.flush()
                completed = subprocess.run(
                    [agent_do, "bootstrap", "--yes"],
                    cwd=root,
                    stdout=fh,
                    stderr=subprocess.STDOUT,
                    timeout=60,
                    check=False,
                )
            run_exit = completed.returncode
        except subprocess.TimeoutExpired:
            run_exit = 124
        except Exception:
            run_exit = 1

        if shutil.which("osascript"):
            if run_exit == 0:
                subprocess.run(
                    [
                        "osascript",
                        "-e",
                        f'display notification "Bootstrap completed for {project_label}. Log: {log_file}" '
                        f'with title "agent-do Bootstrap" sound name "Glass"',
                    ],
                    check=False,
                )
            else:
                subprocess.run(
                    [
                        "osascript",
                        "-e",
                        f'display notification "Bootstrap FAILED for {project_label} (exit {run_exit}). Log: {log_file}" '
                        f'with title "agent-do Bootstrap" sound name "Basso"',
                    ],
                    check=False,
                )
                print(
                    f"[agent-do bootstrap] FAILED for {project_label} (exit {run_exit}). Log: {log_file}",
                    file=sys.stderr,
                )
            if run_exit != 0 and answered_by_person:
                # Failure dialog with "Open log" option.
                failure_message = (
                    f"agent-do bootstrap failed (exit {run_exit}) for {project_label}."
                    + "\n\n"
                    + f"Log: {log_file}"
                )
                code, choice, _ = run_capture(
                    [
                        "osascript",
                        "-e",
                        (
                            f'display dialog {json.dumps(failure_message)} '
                            'with title "agent-do Bootstrap failed" '
                            'buttons {"Dismiss", "Open log"} default button "Open log"\n'
                            "button returned of result"
                        ),
                    ],
                    timeout=15,
                )
                if code == 0 and choice.strip() == "Open log" and shutil.which("open"):
                    subprocess.run(["open", str(log_file)], check=False)
        else:
            status = "completed" if run_exit == 0 else f"FAILED (exit {run_exit})"
            print(f"[agent-do bootstrap] {status} for {project_label}. Log: {log_file}", file=sys.stderr)
    return True


def is_frontend_project(cwd: str | None) -> bool:
    if not cwd:
        return False
    root = Path(cwd)
    package = root / "package.json"
    frontend_tokens = (
        "react",
        "next",
        "vue",
        "nuxt",
        "svelte",
        "astro",
        "angular",
        "remix",
        "gatsby",
        "solid-js",
    )
    if package.exists():
        text = package.read_text(errors="ignore").lower()
        if any(f'"{token}"' in text for token in frontend_tokens):
            return True
    for rel in ("src", "app", "apps", "components", "pages"):
        directory = root / rel
        if not directory.exists():
            continue
        for ext in ("*.tsx", "*.jsx", "*.vue", "*.svelte", "*.astro"):
            if next(directory.glob(f"**/{ext}"), None):
                return True
    pubspec = root / "pubspec.yaml"
    return pubspec.exists() and "flutter" in pubspec.read_text(errors="ignore").lower()


# There is no project-tooling section here, and its absence is deliberate.
# `agent-do suggest --project` needs ~10.5s against a real repo and a session
# hook can afford single digits, so the block it fed was killed before it could
# render. What it would have said reaches the session by other roads anyway —
# the routing table in the repo's agent instructions, the just-in-time nudge
# when a raw command is typed, and zpc's project profile. `agent-do suggest
# --project` remains on demand, where the caller chose to wait for it.


def bootstrap(agent_do: str, cwd: str | None) -> str:
    if not cwd:
        return ""
    data = run_json([agent_do, "bootstrap", "--recommend", "--json", "--cwd", cwd])
    if not data.get("needs_bootstrap"):
        return ""
    ask = data.get("ask_prompt") or "Run agent-do bootstrap for this project?"
    root = data.get("project_root") or cwd
    commands = "\n".join(data.get("commands") or [])
    if native_bootstrap(agent_do, cwd, ask, root):
        return ""
    return (
        "## Bootstrap Opportunity\n\n"
        "At the start of your first reply in this session, ask exactly one short yes/no question:\n"
        f"`{ask}`\n\n"
        "If the user says yes, run `agent-do bootstrap --yes` from:\n"
        f"`{root}`\n\n"
        f"Planned bootstrap:\n```text\n{commands}\n```\n"
    )


def coord_command(agent_do: str) -> list[str]:
    """How to reach coord: the tool itself when it is there, else the dispatcher.

    `agent-do <tool>` spends most of a second before the tool starts — a
    registry parse to resolve declared credentials, then a telemetry write —
    and coord declares no credentials to resolve. The dispatched form stays as
    the fallback, for an install whose resolved agent-do has no tools/ beside
    it.
    """
    try:
        direct = Path(agent_do).resolve().parent / "tools" / "agent-coord"
    except OSError:
        return [agent_do, "coord"]
    if direct.is_file() and os.access(direct, os.X_OK):
        return [str(direct)]
    return [agent_do, "coord"]


def coord_reads(agent_do: str, cwd: str) -> tuple[dict, dict]:
    """Presence and interrupts, read at the same time.

    No single verb answers both questions and minting one is not a hook's call:
    `touch` renews the presence lease and is the only read carrying
    peer_counts, `interrupts --mark-seen` is the only read that consumes what
    it shows, and `coord status` marks nothing seen, so it substitutes for
    neither. So the two stay two and overlap, for one read's wall clock instead
    of two. Overlapping is safe: coord takes its own lock around every
    read-modify-write, and both spawns resolve one identity, anchored to the
    runtime process rather than to either spawn.
    """
    base = coord_command(agent_do)
    wanted = {
        "touch": [*base, "touch", "--json"],
        "interrupts": [*base, "interrupts", "--json", "--mark-seen", "--limit", "5"],
    }
    running: dict[str, subprocess.Popen | None] = {}
    for name, cmd in wanted.items():
        try:
            running[name] = subprocess.Popen(
                cmd,
                cwd=cwd,
                text=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            running[name] = None

    deadline = time.monotonic() + JSON_READ_TIMEOUT
    parsed: dict[str, dict] = {"touch": {}, "interrupts": {}}
    for name, proc in running.items():
        if proc is None:
            continue
        try:
            stdout, _ = proc.communicate(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            continue
        except Exception:
            continue
        if proc.returncode != 0 or not stdout.strip():
            continue
        try:
            loaded = json.loads(stdout)
        except Exception:
            continue
        if isinstance(loaded, dict):
            parsed[name] = loaded
    return parsed["touch"], parsed["interrupts"]


def coord(agent_do: str, cwd: str | None) -> str:
    if not cwd:
        return ""
    touch, interrupts_payload = coord_reads(agent_do, cwd)
    if not touch:
        return ""

    interrupts = interrupts_payload.get("interrupts") or []
    if interrupts:
        lines = [
            f"- {'[new] ' if item.get('new') else ''}{item.get('kind')}: {item.get('summary')}"
            for item in interrupts
        ]
        return (
            "## Coord Interrupts\n\n"
            "Relevant coordination interrupts are active in this repo:\n"
            + "\n".join(lines)
            + "\n\nUse `agent-do coord status`, `agent-do coord interrupts`, or `agent-do coord focus show`.\n"
        )

    active = touch.get("active_peers") or []
    focus_goal = ((touch.get("focus") or {}).get("goal")) or ""
    if active and not focus_goal:
        lines = []
        for peer in active:
            label = peer.get("alias") or peer.get("agent_id")
            goal = ((peer.get("focus") or {}).get("goal")) or ""
            lines.append(f"- {label}{f' goal: {goal}' if goal else ''}")
        return (
            "## Coord Focus Reminder\n\n"
            "Other active peers exist in this repo, and you have not declared focus yet.\n"
            + "\n".join(lines)
            + "\n\nSet focus before overlapping work starts:\n"
            "`agent-do coord focus set \"<goal>\" --path <path> [--path <path> ...]`\n"
        )
    return ""


def git_toplevel(cwd: str | None) -> Path | None:
    """The git worktree containing cwd, for auto-init to know where a store
    belongs. Asked of git rather than walked, because placement wants git's own
    answer — GIT_DIR, linked worktrees and all. The store walk does not use
    this: it carries its own ceiling from zpc_worktree_root, matching the rule
    zpc resolves by, and the two must not be allowed to drift into each other.
    """
    if not cwd:
        return None
    code, out, _ = run_capture(
        ["git", "rev-parse", "--show-toplevel"], cwd=cwd, timeout=ZPC_AUTOINIT_TIMEOUT
    )
    out = out.strip()
    if code != 0 or not out:
        return None
    root = Path(out)
    return root if root.is_dir() else None


def zpc_worktree_root(cwd: Path) -> Path | None:
    """The worktree holding a directory: nearest ancestor-or-self carrying .git.

    Tested for existence rather than directory-ness, because a submodule or a
    linked worktree keeps .git as a file. Walked rather than asked of git: this
    runs before the store walk on every session, and a subprocess to learn what
    a few stat calls already know is a tax.
    """
    probe = cwd
    while True:
        if (probe / ".git").exists():
            return probe
        if probe.parent == probe:
            return None
        probe = probe.parent


def zpc_store_is_ours(store: Path) -> bool:
    """A store is ours only when we own both the name and what it resolves to.

    A link owned by somebody else can be re-aimed whenever they like, and a link
    we own can still land in a directory we do not. zpc applies the identical
    pair (tools/agent-zpc/lib/common.sh:_zpc_store_is_ours).
    """
    me = os.getuid()
    try:
        if store.lstat().st_uid != me:
            return False
        return store.stat().st_uid == me
    except OSError:
        return False


def zpc_binding_for(directory: Path) -> Path | None:
    """The store a directory is bound to, or None when there is none to trust.

    `agent-git worktree add` binds every linked worktree it creates, because
    .zpc/ is gitignored and an unbound worktree would record its lessons into a
    store that dies with `worktree remove`.

    The binding lives in this user's config, never in the repository, and that
    location is the whole security property: a pointer file inside the tree
    would let repository content decide where this hook reads memory from and
    where the session writes it, and this hook injects what it finds as the
    project's recorded truth without anyone asking. A clone cannot write
    $AGENT_DO_HOME. Trust rules identical to zpc's
    (tools/agent-zpc/lib/common.sh:_zpc_binding_for).
    """
    home = os.environ.get("AGENT_DO_HOME") or os.path.join(
        os.environ.get("HOME", ""), ".agent-do"
    )
    bindings = Path(home) / "zpc" / "worktree-bindings.tsv"
    if not bindings.is_file() or not zpc_store_is_ours(bindings):
        return None

    key = str(directory).rstrip("/")
    try:
        raw = bindings.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        worktree, _, store = line.partition("\t")
        if worktree.rstrip("/") != key:
            continue
        path = Path(store.rstrip("/"))
        if not store.startswith("/") or path.name != ".zpc" or not path.is_dir():
            return None
        return path if zpc_store_is_ours(path) else None
    return None


def zpc_store_root(cwd: str) -> Path | None:
    """Where zpc would resolve a store from here — the upward walk
    resolve_zpc_dir does (tools/agent-zpc/lib/common.sh) — but bounded and
    ownership-checked, because this walk runs unattended at session start and
    whatever it finds gets read to the agent as trusted memory.

    The ceiling: a git worktree stops at its toplevel; otherwise a cwd under
    $HOME stops at $HOME; a cwd outside both walks nowhere at all and only ever
    probes itself. Unbounded, a session opened anywhere under /tmp would find a
    world-writable store planted above it and inject a stranger's lessons under
    a heading that tells the agent to trust them.

    The ownership check is the second lock: a store is used only when the
    current uid owns it. One we do not own is stepped over, not treated as
    fatal, and the walk carries on above it. Stopping there looks like the
    careful choice and is not one: the foreign store is refused either way, by
    this same check, so stopping guards nothing — it only hands anyone who can
    write a directory on your path a silent way to black out the real store
    above it.
    """
    probe = Path(str(cwd).rstrip("/") or "/")

    home = (os.environ.get("HOME") or "").rstrip("/")
    under_home = bool(home) and (
        str(probe) == home or str(probe).startswith(home + "/")
    )

    toplevel = zpc_worktree_root(probe)
    if toplevel is not None:
        ceiling = toplevel
        # A repo that contains $HOME must not lift the floor back off.
        if under_home and len(str(toplevel)) < len(home):
            ceiling = Path(home)
    elif under_home:
        ceiling = Path(home)
    else:
        # No worktree and outside $HOME: probe this directory and stop.
        ceiling = probe

    while True:
        store = probe / ".zpc"
        # Not ours: fall through and keep climbing. A real store at a rung
        # answers before that rung's binding does — memory sitting in front of
        # you outranks a note about memory elsewhere.
        if store.is_dir() and zpc_store_is_ours(store):
            return probe
        bound = zpc_binding_for(probe)
        if bound is not None:
            return bound.parent
        if probe == ceiling or probe.parent == probe:
            break
        probe = probe.parent
    return None


def zpc_has_records(cwd: str) -> bool:
    """At least one recorded line under .zpc/memory/. An initialized-but-empty
    store has nothing worth embedding, so it keeps the advisory."""
    for path in (Path(cwd) / ".zpc" / "memory").glob("*.jsonl"):
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line.strip():
                        return True
        except OSError:
            continue
    return False


def zpc_autoinit(agent_do: str | None, cwd: str | None, toplevel: Path | None) -> None:
    """Give every project a store, without the hook ever writing a tracked file.

    Two limits make that true. A git worktree is the unit of "project", so a
    bare directory never gets one. And `zpc init` does more than create the
    store: it appends to .gitignore and writes (or appends to) the repo's agent
    instruction file, which is not something a silent session-start hook may do
    to a repo it does not own. So auto-init rides a store-only mode and stays
    home without it.
    """
    if os.environ.get("AGENT_DO_ZPC_AUTOINIT", "1") == "0":
        return
    if not agent_do or not cwd:
        return

    if toplevel is None:
        return
    root = toplevel

    # zpc resolves a store by walking up from cwd, so a store anywhere between
    # cwd and the toplevel means this project already has one.
    probe = Path(cwd)
    while True:
        if (probe / ".zpc").exists():
            return
        if probe == root or probe.parent == probe:
            break
        probe = probe.parent
    if (root / ".zpc").exists():
        return

    # A bound worktree already has memory — someone else's directory holds it.
    # Creating a store here would shadow that binding on the very next session
    # and put this tree back on the path where its lessons die with it.
    if zpc_binding_for(root) is not None:
        return

    # init's argument loop swallows flags it does not know, so asking an older
    # zpc for --store-only gets a full invasive init that reports success. The
    # gate has to be positive: no such flag in the help text, no auto-init.
    code, help_text, _ = run_capture(
        [agent_do, "zpc", "init", "--help"], cwd=str(root), timeout=ZPC_AUTOINIT_TIMEOUT
    )
    if code != 0 or "--store-only" not in help_text:
        return

    run_capture(
        [agent_do, "zpc", "init", "--store-only"],
        cwd=str(root),
        timeout=ZPC_AUTOINIT_TIMEOUT,
    )


def run_zpc_inject(agent_do: str, cwd: str, preferences: bool = False) -> str:
    """Inject stdout, or "" on any failure.

    Output lands in a temp file rather than a pipe: inject detaches a harvest,
    and any background writer holding the read end open would outlast the
    timeout that exists to bound this call. start_new_session isolates the
    process group so a timeout kill takes the whole spawn without reaching the
    deliberately detached harvest, which carries its own group.
    """
    # AGENT_DO_ZPC_SOURCE tags the access log; the copy keeps it out of the
    # rest of the hook's environment.
    env = dict(os.environ)
    env["AGENT_DO_ZPC_SOURCE"] = "hook"
    try:
        with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as out:
            # cwd must be inside the project: inject resolves the store from there.
            proc = subprocess.Popen(
                [agent_do, "zpc", "inject"] + (["--preferences"] if preferences else []),
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                code = proc.wait(timeout=ZPC_INJECT_TIMEOUT)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except OSError:
                    proc.kill()
                proc.wait()
                return ""
            if code != 0:
                return ""
            out.seek(0)
            return out.read()
    except Exception:
        return ""


def zpc_preferences_section(agent_do: str | None, cwd: str) -> str:
    """Preferences are the user's, not the project's, so they travel: an empty
    store and a directory that will never have one both get them. Returns ""
    unless there is real content, which keeps every caller's fallback intact."""
    if not agent_do:
        return ""
    preferences = run_zpc_inject(agent_do, cwd, preferences=True).rstrip("\n")
    if not preferences.strip():
        return ""
    return (
        "## ZPC Preferences (global memory)\n\n"
        "Preferences recorded across earlier sessions, loaded below. They are "
        "user-level, not project-level: they hold here regardless of what this "
        "directory contains.\n\n"
        f"{preferences}\n\n"
        "Log new ones where they happen: `agent-do zpc learn` and "
        "`agent-do zpc decide`.\n"
    )


def zpc(agent_do: str | None, cwd: str | None) -> str:
    if not cwd:
        return ""

    embedding = bool(agent_do) and os.environ.get("AGENT_DO_ZPC_INJECT", "1") != "0"

    # No store anywhere up the tree, and none coming: auto-init already declined
    # this directory (not a git worktree, or it has no store-only mode to use).
    # Preferences are still his, so they still arrive.
    store_root = zpc_store_root(cwd)
    if store_root is None:
        return zpc_preferences_section(agent_do, cwd) if embedding else ""
    root = str(store_root)

    # The advisory below only *asks* the agent to go read the store, and asking
    # is not a mechanism. When there are records to show, put the memory itself
    # in context. Every failure mode (kill-switch, empty store, missing
    # dispatcher, nonzero exit, timeout) falls through to the advisory, so the
    # section degrades instead of disappearing.
    if embedding:
        if zpc_has_records(root):
            # Run from the store's own root, which is cwd for a session opened
            # at the top and the walked-up answer otherwise.
            memory = run_zpc_inject(agent_do, root).rstrip("\n")
            if memory.strip():
                return (
                    "## ZPC Project Memory\n\n"
                    "This project's recorded memory, loaded below. Read it before coding; "
                    "it is already in context, so do not re-run `agent-do zpc inject`.\n\n"
                    f"{memory}\n\n"
                    "Keep the loop closed: `agent-do zpc learn` and `agent-do zpc decide` as "
                    "you work, `agent-do zpc harvest` after significant work.\n"
                )
        else:
            # A store with nothing in it yet — every project's first session,
            # now that init runs automatically. Preferences beat an advisory
            # nobody reads.
            section = zpc_preferences_section(agent_do, root)
            if section:
                return section

    return (
        "## ZPC Memory Available\n\n"
        "This project has `.zpc/` memory. Start with `agent-do zpc status` and "
        "`agent-do zpc patterns` before coding.\n"
    )


def frontend_context(cwd: str | None) -> str:
    if not is_frontend_project(cwd):
        return ""
    return (
        "## Frontend Project Detected\n\n"
        "For visual/UI work, use screenshots as visual truth and `agent-do dpt` for scoring:\n"
        "- `agent-do browse open <dev-url>`\n"
        "- `agent-do browse screenshot /tmp/before.png`\n"
        "- after edits: `agent-do browse reload && agent-do browse screenshot /tmp/after.png`\n"
        "- `agent-do dpt score /tmp/after.png`\n\n"
        "Use Codex UI skills when applicable, especially `building-ui` and `layout-rhythm-repair`.\n"
    )


def main() -> None:
    payload = read_payload()
    cwd = payload.get("cwd") or os.getcwd()
    agent_do = resolve_agent_do()

    # Auto-init first: the memory section below reads the store this may have
    # just created. The toplevel here is auto-init's placement question only;
    # the store walk answers its own.
    toplevel = git_toplevel(cwd)
    zpc_autoinit(agent_do, cwd, toplevel)

    sections = [
        "## TOOLING REMINDER - agent-do\n\n"
        "Before writing raw automation or vendor API glue, check whether `agent-do` already has the path:\n"
        "`agent-do suggest \"task\"`, `agent-do suggest --project`, `agent-do find <keyword>`, "
        "`agent-do --list`, `agent-do <tool> --help`.\n"
    ]

    if agent_do:
        sections.extend(
            part
            for part in (
                bootstrap(agent_do, cwd),
                coord(agent_do, cwd),
            )
            if part
        )
    sections.extend(
        part for part in (frontend_context(cwd), zpc(agent_do, cwd)) if part
    )

    context = "\n---\n\n".join(sections)
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
