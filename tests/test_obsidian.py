#!/usr/bin/env python3
"""Offline tests for agent-do obsidian.

These tests run without Obsidian or the obsidian CLI installed. They use a
fake `obsidian` shim that records its argv to a file, then assert that
agent-obsidian passes the right parameter grammar (`key=value` / flag) to
the underlying CLI for every supported subcommand. They also verify the
doctor output shape, snapshot JSON, +live gating for the privileged
surface, and the registry entry.
"""

from __future__ import annotations

import json
import os
import importlib.util
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"
AGENT_OBSIDIAN = ROOT / "tools" / "agent-obsidian"
OBSIDIAN_ENGINE = ROOT / "tools" / "obsidian_lib" / "engine.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_obsidian_engine():
    spec = importlib.util.spec_from_file_location("agent_obsidian_engine_for_tests", OBSIDIAN_ENGINE)
    require(spec is not None and spec.loader is not None, "failed to load obsidian engine spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_fake_obsidian(path: Path, log_file: Path) -> None:
    """Create a fake `obsidian` binary that records its argv and exits 0.

    `help` is special-cased to exit 0 silently so the doctor's
    cli-responsive probe (`obsidian help`) returns success. Arguments
    are recorded as a JSON array so values containing newlines or quotes
    survive the round trip — line-delimited records can't represent
    those cleanly.
    """
    path.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            if [[ "${{1:-}}" == "help" ]]; then
                exit 0
            fi
            python3 - "$@" <<'PY' > "{log_file}"
            import json, sys
            print(json.dumps(sys.argv[1:]))
            PY
            exit 0
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def run(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def read_log(log_file: Path) -> list[str]:
    if not log_file.exists():
        return []
    blob = log_file.read_text()
    if not blob.strip():
        return []
    return json.loads(blob)


def base_env(tmp: Path, log_file: Path, *, fake_cli: Path | None) -> dict[str, str]:
    env = os.environ.copy()
    env["AGENT_DO_HOME"] = str(tmp / "agent-do-home")
    env["HOME"] = str(tmp / "fake-home")
    Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
    # Strip any inherited live context so gating tests start clean.
    for key in (
        "AGENT_DO_LIVE",
        "AGENT_DO_LIVE_SPEC",
        "AGENT_DO_LIVE_CONTEXT",
        "AGENT_OBSIDIAN_VAULT",
        "AGENT_OBSIDIAN_VAULT_PATH",
    ):
        env.pop(key, None)
    for key in ("VOYAGE_API_KEY", "OPENAI_API_KEY", "COHERE_API_KEY"):
        env.pop(key, None)
    # Disable the auto-install symlink path during tests; we use OBSIDIAN_BIN.
    env["AGENT_OBSIDIAN_NO_AUTO_INSTALL"] = "1"
    if fake_cli is not None:
        env["OBSIDIAN_BIN"] = str(fake_cli)
        # Shadow any real `obsidian` on PATH so it can't interfere.
        # OBSIDIAN_BIN takes priority in resolution, but this prevents
        # accidental real-CLI usage. Uses a shim instead of removing PATH
        # directories (which could also remove python3 or other needed
        # binaries from the same directory).
        shim_dir = str(tmp / "obsidian-shim")
        Path(shim_dir).mkdir(parents=True, exist_ok=True)
        shim_path = Path(shim_dir) / "obsidian"
        shim_path.write_text("#!/bin/sh\nexit 127\n")
        shim_path.chmod(0o755)
        env["PATH"] = shim_dir + os.pathsep + env.get("PATH", "")
    else:
        # No CLI wanted — point OBSIDIAN_BIN at a nonexistent path so the
        # wrapper's _find_obsidian_cli returns 1 immediately (early exit
        # bypasses PATH lookup AND hardcoded candidate checks like
        # /usr/local/bin/obsidian which exist on machines with Obsidian
        # installed).
        env["OBSIDIAN_BIN"] = str(tmp / "nonexistent-obsidian")
    return env


def assert_argv(actual: list[str], expected: list[str], label: str) -> None:
    require(
        actual == expected,
        f"{label}: argv mismatch\n  expected: {expected}\n  actual:   {actual}",
    )


def test_static_artifacts() -> None:
    """Cheap structural checks that don't need a subprocess."""
    require(AGENT_OBSIDIAN.exists(), "tools/agent-obsidian must exist")
    require(os.access(AGENT_OBSIDIAN, os.X_OK), "tools/agent-obsidian must be executable")

    src = AGENT_OBSIDIAN.read_text()
    # Defensive checks that catch easy regressions.
    require("set -euo pipefail" in src, "agent-obsidian must use set -euo pipefail")
    require("require_live_control" in src, "agent-obsidian must call require_live_control via Python")
    require('cmd_eval' in src and 'cmd_dev' in src and 'cmd_plugin' in src,
            "agent-obsidian must expose eval/dev/plugin commands")
    # The privileged commands must reach the gate function.
    for needle in (
        '_require_live_or_die "obsidian:eval"',
        '_require_live_or_die "obsidian:dev:errors"',
        '_require_live_or_die "obsidian:plugin:reload"',
    ):
        require(needle in src, f"agent-obsidian must call gate for: {needle}")


def test_registry_entry() -> None:
    """The registry.yaml entry must be present and well-formed."""
    import sys

    sys.path.insert(0, str(ROOT / "lib"))
    from registry import load_registry  # type: ignore

    registry = load_registry()
    require("obsidian" in registry["tools"], "registry.yaml must declare tools.obsidian")
    entry = registry["tools"]["obsidian"]
    for key in ("description", "capabilities", "commands", "examples", "routing", "concurrency"):
        require(key in entry, f"obsidian registry entry missing key: {key}")
    require(entry["concurrency"] == "mixed", f"unexpected concurrency: {entry['concurrency']}")
    for cmd in ("doctor", "snapshot", "read", "create", "append", "search",
                "embed", "context", "chat", "connections",
                "daily", "prop", "tasks", "tags", "backlinks",
                "refresh", "save", "save-group", "query", "relate", "summarize",
                "weekly", "period", "graph", "templates", "audit", "move", "delete",
                "eval", "dev", "plugin"):
        require(cmd in entry["commands"], f"obsidian registry missing command: {cmd}")
    # Subcommands we deliberately do NOT ship in v1: `open` (semantics
    # depend on whether `obsidian read` reveals or just prints — unverified)
    # and `prop list` (not documented in the upstream CLI surface).
    for absent in ("open",):
        require(absent not in entry["commands"],
                f"registry should not list unverified command: {absent}")
    routing = entry["routing"]
    require("readiness" in routing, "routing.readiness must be present")
    require(routing["readiness"]["check"] == "agent-do obsidian doctor",
            f"unexpected readiness.check: {routing['readiness']}")
    require(routing["readiness"]["fix"] == "agent-do obsidian doctor --fix",
            f"unexpected readiness.fix: {routing['readiness']}")
    intents = {item["label"] for item in routing.get("intents", [])}
    for label in ("vault_save_intent", "vault_find_intent", "vault_ask_intent",
                  "vault_organize_intent", "vault_refactor_intent"):
        require(label in intents, f"obsidian routing missing intent label: {label}")
    contracts = entry.get("contracts") or {}
    for beat in ("connect", "snapshot", "interact", "verify", "save"):
        require(beat in contracts, f"obsidian contracts missing beat: {beat}")


def test_help_and_unknown(env: dict[str, str]) -> None:
    h = run(str(AGENT_OBSIDIAN), "--help", env=env)
    require(h.returncode == 0, f"--help must exit 0: {h.stderr}")
    require("agent-obsidian" in h.stdout, f"--help should mention tool name: {h.stdout[:80]}")
    require("doctor" in h.stdout and "+live" in h.stdout,
            "--help should mention doctor and +live gating")

    bogus = run(str(AGENT_OBSIDIAN), "totally-bogus-command", env=env)
    require(bogus.returncode == 2, f"unknown command should exit 2, got {bogus.returncode}")


def test_doctor_missing(env_no_cli: dict[str, str]) -> None:
    # Doctor with no working obsidian binary → exit 1, JSON has
    # recommendation, ok=false. env_no_cli already has OBSIDIAN_BIN set to a
    # nonexistent path, which makes _find_obsidian_cli return 1 immediately
    # (skipping PATH lookup and hardcoded-candidate checks that would find a
    # real Obsidian installation on dev machines).
    r = run(str(AGENT_OBSIDIAN), "doctor", "--json", env=env_no_cli)
    require(r.returncode == 1, f"doctor with no CLI should exit 1: {r.stdout} / {r.stderr}")
    payload = json.loads(r.stdout)
    require(payload["ok"] is False, f"doctor.ok should be False: {payload}")
    require(payload["cli_path"] is None, f"doctor.cli_path should be None: {payload}")
    require("recommendation" in payload, f"doctor should suggest a fix: {payload}")


def test_doctor_present(env_with_cli: dict[str, str]) -> None:
    # OBSIDIAN_BIN points at a working fake → doctor reports ok=true.
    r = run(str(AGENT_OBSIDIAN), "doctor", "--json", env=env_with_cli)
    require(r.returncode == 0, f"doctor with CLI present should exit 0: {r.stdout} / {r.stderr}")
    payload = json.loads(r.stdout)
    require(payload["ok"] is True, f"doctor.ok should be True: {payload}")
    require(payload["cli_path"] == env_with_cli["OBSIDIAN_BIN"],
            f"doctor.cli_path mismatch: {payload}")
    require(payload["cli_source"] == "env_override",
            f"doctor.cli_source should reflect OBSIDIAN_BIN: {payload}")
    require(payload["cli_runs"] is True, f"doctor.cli_runs should be True: {payload}")


def test_snapshot(env_with_cli: dict[str, str], env_no_cli: dict[str, str]) -> None:
    # With a working fake CLI, snapshot is JSON, ok=true, exit 0.
    r = run(str(AGENT_OBSIDIAN), "snapshot", env=env_with_cli)
    require(r.returncode == 0, f"snapshot should exit 0 when ok=true: {r.stderr}")
    payload = json.loads(r.stdout)
    require(payload["tool"] == "obsidian", f"snapshot.tool mismatch: {payload}")
    require(payload["ok"] is True, f"snapshot.ok should be True with fake CLI: {payload}")
    require(payload["cli"]["responsive"] is True,
            f"snapshot.cli.responsive should be True: {payload}")

    # Without a CLI, snapshot still emits JSON, but exits 1 — matches
    # agent-linear and agent-notion: snapshot signals missing prerequisites
    # via exit code so orchestrators can react without parsing the body.
    r = run(str(AGENT_OBSIDIAN), "snapshot", env=env_no_cli)
    require(r.returncode == 1,
            f"snapshot should exit 1 when prerequisites missing: {r.returncode}")
    payload = json.loads(r.stdout)
    require(payload["ok"] is False, f"snapshot.ok should be False: {payload}")
    require("recommendation" in payload, f"snapshot should suggest a fix: {payload}")


def test_non_responsive_cli(tmp: Path, log_file: Path) -> None:
    """Doctor and snapshot must exit 1 / ok=false when the CLI exists but
    fails the 'help' responsiveness probe (broken binary, wrong version, etc.).
    """
    broken_cli = tmp / "obsidian-broken"
    broken_cli.write_text("#!/bin/sh\nexit 1\n")  # always fails
    broken_cli.chmod(0o755)
    env = base_env(tmp, log_file, fake_cli=broken_cli)

    # Doctor should report ok=false and exit 1.
    r = run(str(AGENT_OBSIDIAN), "doctor", "--json", env=env)
    require(r.returncode == 1,
            f"doctor should exit 1 for non-responsive CLI: {r.returncode}")
    payload = json.loads(r.stdout)
    require(payload["ok"] is False,
            f"doctor.ok should be False for non-responsive CLI: {payload}")
    require(payload["cli_runs"] is False,
            f"doctor.cli_runs should be False: {payload}")
    require("recommendation" in payload,
            f"doctor should recommend a fix for non-responsive CLI: {payload}")

    # Snapshot should also report ok=false and exit 1.
    r = run(str(AGENT_OBSIDIAN), "snapshot", env=env)
    require(r.returncode == 1,
            f"snapshot should exit 1 for non-responsive CLI: {r.returncode}")
    payload = json.loads(r.stdout)
    require(payload["ok"] is False,
            f"snapshot.ok should be False for non-responsive CLI: {payload}")
    require(payload["cli"]["responsive"] is False,
            f"snapshot.cli.responsive should be False: {payload}")


def test_snapshot_app_not_running(tmp: Path, log_file: Path) -> None:
    """Snapshot must return ok=false when the CLI responds to 'help' but the
    Obsidian app isn't running (simulated by `tags` returning non-zero).
    The Obsidian CLI's `help` is a static dump that works without the app,
    but actual commands like `tags` require the IPC connection to the running
    app.
    """
    # Fake CLI: help succeeds, everything else fails (app not running).
    help_only_cli = tmp / "obsidian-help-only"
    help_only_cli.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            if [[ "${1:-}" == "help" ]]; then
                exit 0
            fi
            exit 1
            """
        ),
        encoding="utf-8",
    )
    help_only_cli.chmod(0o755)
    env = base_env(tmp, log_file, fake_cli=help_only_cli)

    r = run(str(AGENT_OBSIDIAN), "snapshot", env=env)
    require(r.returncode == 1,
            f"snapshot should exit 1 when app not running: {r.returncode}")
    payload = json.loads(r.stdout)
    require(payload["ok"] is False,
            f"snapshot.ok should be False when tags fails: {payload}")
    require(payload["cli"]["responsive"] is True,
            f"snapshot.cli.responsive should be True (help works): {payload}")
    require("recommendation" in payload,
            f"snapshot should recommend opening Obsidian: {payload}")
    require("open Obsidian" in payload["recommendation"],
            f"recommendation should mention opening Obsidian: {payload['recommendation']}")


def test_content_with_flag_literals(env_with_cli: dict[str, str], log_file: Path) -> None:
    """Content containing literal --vault and --json must not be eaten by the
    global parser. Regression guard for the leading-flags-only parsing change.
    """
    # Append with positional body text that includes "--vault" and "--json".
    r = run(str(AGENT_OBSIDIAN), "append", "TestNote",
            "set --vault=secret --json output", env=env_with_cli)
    require(r.returncode == 0,
            f"append with flag-like content should succeed: {r.stderr}")
    argv = json.loads(log_file.read_text())
    # The obsidian CLI should receive the full body as content, not have
    # --vault or --json stripped from it.
    body = " ".join(argv[2:]) if len(argv) > 2 else ""
    require("--vault=secret" in body,
            f"--vault in content body was incorrectly consumed: argv={argv}")
    require("--json" in body,
            f"--json in content body was incorrectly consumed: argv={argv}")


def test_argv_passthrough(env_with_cli: dict[str, str], log_file: Path) -> None:
    """Every subcommand must pass the right key=value grammar to the CLI."""

    cases: list[tuple[list[str], list[str], str]] = [
        # (agent-obsidian argv, expected obsidian argv, label)
        (["read", "Daily/2026-05-10"], ["read", "file=Daily/2026-05-10"],
         "read by name"),
        (["read", "--path", "folder/note.md"], ["read", "path=folder/note.md"],
         "read by path"),
        (["create", "Inbox/Idea", "--content", "Pricing experiment"],
         ["create", "name=Inbox/Idea", "content=Pricing experiment"],
         "create with content (silent by default — no flag needed)"),
        (["create", "Inbox/Idea", "--content", "X", "--open"],
         ["create", "name=Inbox/Idea", "content=X", "open"],
         "create --open reveals note"),
        (["create", "Doc", "--template", "Meeting", "--overwrite"],
         ["create", "name=Doc", "template=Meeting", "overwrite"],
         "create with template + overwrite"),
        (["append", "Note", "Hello", "world"],
         ["append", "file=Note", "content=Hello world"],
         "append concatenates trailing positional words"),
        (["append", "Note", "--content", "line1\nline2"],
         ["append", "file=Note", "content=line1\nline2"],
         "append --content preserves embedded newlines"),
        (["append", "Note", "Hello", "--path"],
         ["append", "path=Note", "content=Hello"],
         "append --path switches target style"),
        (["search", "review", "--limit", "5"],
         ["search", "query=review", "limit=5"],
         "search with limit"),
        (["search", "review", "--total"],
         ["search", "query=review", "total"],
         "search with --total"),
        (["daily", "read", "--copy"], ["daily:read", "--copy"],
         "daily read --copy"),
        (["daily", "append", "- [ ] Ship PR"],
         ["daily:append", "content=- [ ] Ship PR"],
         "daily append"),
        (["prop", "get", "status", "--file", "Note"],
         ["property:read", "name=status", "file=Note"],
         "prop get with --file"),
        (["prop", "set", "status", "done", "--file", "Note"],
         ["property:set", "name=status", "value=done", "file=Note"],
         "prop set with --file"),
        (["tasks", "todo", "--daily"], ["tasks", "daily", "todo"],
         "tasks todo --daily"),
        (["tags", "--counts", "--sort", "count"],
         ["tags", "counts", "sort=count"],
         "tags with counts and sort"),
        (["backlinks", "My Note"], ["backlinks", "file=My Note"],
         "backlinks preserves spaces"),
        # Global flag — vault must be prepended FIRST per obsidian-cli grammar.
        (["--vault", "My Vault", "search", "review"],
         ["vault=My Vault", "search", "query=review"],
         "--vault is injected before subcommand"),
    ]

    for argv, expected, label in cases:
        log_file.write_text("")  # truncate
        r = run(str(AGENT_OBSIDIAN), *argv, env=env_with_cli)
        require(r.returncode == 0, f"{label}: command failed ({r.returncode}): {r.stderr}")
        assert_argv(read_log(log_file), expected, label)


def test_live_gating(env_with_cli: dict[str, str], log_file: Path) -> None:
    """Privileged commands must require +live(...) and emit canonical denial."""

    privileged = [
        (["eval", "console.log(1)"], "obsidian:eval"),
        (["dev", "errors"], "obsidian:dev:errors"),
        (["dev", "screenshot", "/tmp/x.png"], "obsidian:dev:screenshot"),
        (["dev", "dom", ".workspace"], "obsidian:dev:dom"),
        (["dev", "console"], "obsidian:dev:console"),
        (["dev", "css", ".x", "color"], "obsidian:dev:css"),
        (["dev", "mobile", "on"], "obsidian:dev:mobile"),
        (["plugin", "reload", "templater-obsidian"], "obsidian:plugin:reload"),
    ]

    # Denial path: each command exits 1 with the canonical payload.
    for argv, reason in privileged:
        env = dict(env_with_cli)
        # Brand-new AGENT_DO_HOME so leases can't sneak in.
        with tempfile.TemporaryDirectory() as fresh:
            env["AGENT_DO_HOME"] = fresh
            r = run(str(AGENT_OBSIDIAN), *argv, env=env)
            require(r.returncode == 1,
                    f"{argv}: privileged command should be denied (exit 1), got {r.returncode}")
            payload = json.loads(r.stdout)
            require(payload["action_required"] == "LIVE_APPROVAL_REQUIRED",
                    f"{argv}: expected LIVE_APPROVAL_REQUIRED: {payload}")
            require(payload["required_scope"] == "desktop",
                    f"{argv}: expected scope desktop: {payload}")
            require(payload["app"] == "Obsidian",
                    f"{argv}: expected app Obsidian: {payload}")
            require(payload["reason"] == reason,
                    f"{argv}: expected reason '{reason}', got '{payload.get('reason')}'")
            require("+live(" in payload["rerun"] and "obsidian" in payload["rerun"],
                    f"{argv}: rerun hint malformed: {payload['rerun']}")

    # Approval path: a single valid live context lets every privileged command
    # through. We use a per-command fresh home so each invocation activates
    # its own lease cleanly.
    approvals: list[tuple[list[str], list[str]]] = [
        (["eval", "console.log(1)"],
         ["eval", "code=console.log(1)"]),
        (["dev", "errors"],
         ["dev:errors"]),
        (["dev", "screenshot", "/tmp/x.png"],
         ["dev:screenshot", "path=/tmp/x.png"]),
        (["dev", "dom", ".workspace", "--text"],
         ["dev:dom", "selector=.workspace", "text"]),
        (["dev", "console", "--level", "error"],
         ["dev:console", "level=error"]),
        (["dev", "css", ".x", "color"],
         ["dev:css", "selector=.x", "prop=color"]),
        (["dev", "mobile", "on"],
         ["dev:mobile", "on"]),
        (["plugin", "reload", "templater-obsidian"],
         ["plugin:reload", "id=templater-obsidian"]),
    ]
    for argv, expected in approvals:
        env = dict(env_with_cli)
        with tempfile.TemporaryDirectory() as fresh:
            env["AGENT_DO_HOME"] = fresh
            env["AGENT_DO_LIVE"] = "1"
            env["AGENT_DO_LIVE_CONTEXT"] = json.dumps({
                "enabled": True,
                "scope": "desktop",
                "app": "Obsidian",
                "ttl_seconds": 60,
            })
            log_file.write_text("")
            r = run(str(AGENT_OBSIDIAN), *argv, env=env)
            require(r.returncode == 0,
                    f"approved {argv} should exit 0: {r.stdout} / {r.stderr}")
            assert_argv(read_log(log_file), expected, f"approved {argv}")


def make_local_vault(tmp: Path) -> Path:
    vault = tmp / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "Projects").mkdir()
    (vault / "Projects" / "Alpha.md").write_text(
        textwrap.dedent(
            """\
            ---
            tags: [project]
            status: active
            scope: local
            ---
            # Alpha
            This is about Saoshyant and [[Beta]].
            - [ ] Ship thing 📅 2026-05-19 🔼
            """
        ),
        encoding="utf-8",
    )
    (vault / "Beta.md").write_text(
        textwrap.dedent(
            """\
            ---
            tags: [project]
            ---
            # Beta
            Back to [[Alpha]].
            """
        ),
        encoding="utf-8",
    )
    (vault / "Loose.md").write_text("Loose body with no frontmatter.\n", encoding="utf-8")
    return vault


def test_local_vault_v2_surface(tmp: Path, log_file: Path) -> None:
    """The v2 local-vault surface works without Obsidian.app or obsidian-cli."""
    vault = make_local_vault(tmp)
    env = base_env(tmp, log_file, fake_cli=None)
    env["AGENT_OBSIDIAN_VAULT_PATH"] = str(vault)

    r = run(str(AGENT_OBSIDIAN), "doctor", "--json", env=env)
    require(r.returncode == 0, f"local doctor should work without CLI: {r.stdout} / {r.stderr}")
    payload = json.loads(r.stdout)
    require(payload["mode"] == "local-index", f"doctor should report local mode: {payload}")
    require(payload["features"]["read_save_keyword_index"]["ready"] is True,
            f"doctor should mark local read/save/index feature ready: {payload}")
    require("VOYAGE_API_KEY" in payload["credentials"],
            f"doctor should expose semantic credential readiness without values: {payload}")

    r = run(str(AGENT_DO), "--health", "obsidian", env=env)
    require(r.returncode == 0, f"health obsidian should accept local-index mode: {r.stdout} / {r.stderr}")
    require("OK" in r.stdout and "local vault index mode" in r.stdout,
            f"health should report local-index readiness: {r.stdout}")

    r = run(str(AGENT_OBSIDIAN), "refresh", "--full", "--verbose", "--json", env=env)
    require(r.returncode == 0, f"refresh failed: {r.stdout} / {r.stderr}")
    payload = json.loads(r.stdout)
    require(payload["note_count"] == 3, f"expected 3 indexed notes: {payload}")
    require(payload["task_count"] == 1, f"expected 1 indexed task: {payload}")
    require(payload["chunk_count"] >= 3, f"refresh should index markdown chunks: {payload}")
    require(payload["scan"]["markdown_files"] == 3, f"verbose scan should count markdown files: {payload}")
    require(payload["scan"]["walk_errors"] == [], f"temp vault should scan cleanly: {payload}")

    r = run(str(AGENT_OBSIDIAN), "embed", "status", "--json", env=env)
    require(r.returncode == 0, f"embed status failed: {r.stdout} / {r.stderr}")
    payload = json.loads(r.stdout)
    require(payload["embedding"]["model"] == "voyage-4-large",
            f"embed status should expose the current best default: {payload}")
    require(payload["embedding"]["stale_embedding_count"] >= 3,
            f"embed status should show unembedded chunks: {payload}")

    r = run(str(AGENT_OBSIDIAN), "search", "Saoshyant", "--json", env=env)
    require(r.returncode == 0, f"search failed: {r.stdout} / {r.stderr}")
    payload = json.loads(r.stdout)
    require(payload["results"][0]["path"] == "Projects/Alpha.md",
            f"search should find Alpha: {payload}")

    r = run(str(AGENT_OBSIDIAN), "context", "build", "Saoshyant",
            "--mode", "keyword", "--json", env=env)
    require(r.returncode == 0, f"context build keyword failed: {r.stdout} / {r.stderr}")
    payload = json.loads(r.stdout)
    require("Projects/Alpha.md:" in payload["context"] and payload["sources"],
            f"context build should return cited chunks: {payload}")

    r = run(str(AGENT_OBSIDIAN), "read", "Alpha", "--json", env=env)
    require(r.returncode == 0, f"read failed: {r.stdout} / {r.stderr}")
    payload = json.loads(r.stdout)
    require(payload["note"]["backlinks_count"] == 1,
            f"Alpha should have one backlink from Beta: {payload}")

    r = run(str(AGENT_OBSIDIAN), "tasks", "list", "--json", env=env)
    require(r.returncode == 0, f"tasks list failed: {r.stdout} / {r.stderr}")
    payload = json.loads(r.stdout)
    require(payload["tasks"][0]["priority"] == "high",
            f"task priority emoji should parse: {payload}")

    r = run(str(AGENT_OBSIDIAN), "query",
            "FROM #project WHERE status=active SORT title ASC LIMIT 5", "--json", env=env)
    require(r.returncode == 0, f"query failed: {r.stdout} / {r.stderr}")
    payload = json.loads(r.stdout)
    require(payload["count"] == 1 and payload["rows"][0]["title"] == "Alpha",
            f"DQL subset query should return Alpha: {payload}")

    r = run(str(AGENT_OBSIDIAN), "tags", "rename", "project", "active-project", "--json", env=env)
    require(r.returncode == 0, f"tags rename failed: {r.stdout} / {r.stderr}")
    r = run(str(AGENT_OBSIDIAN), "tags", "--counts", "--json", env=env)
    payload = json.loads(r.stdout)
    tags = {item["tag"] for item in payload["tags"]}
    require("active-project" in tags and "project" not in tags,
            f"tags rename should rewrite indexed tags: {payload}")

    r = run(str(AGENT_OBSIDIAN), "save", "--content", "New idea about Alpha",
            "--related", "auto", "--tags", "note", "--json", env=env)
    require(r.returncode == 0, f"save failed: {r.stdout} / {r.stderr}")
    payload = json.loads(r.stdout)
    fm = payload["record"]["frontmatter"]
    require(payload["record"]["path"].startswith("+/"), f"save should use inbox folder: {payload}")
    require(fm["log"] != "[[{today}]]", f"save should expand date tokens: {payload}")

    r = run(str(AGENT_OBSIDIAN), "save-group", "Hub",
            "--child", "Child A:body a", "--child", "Child B:body b",
            "--scope", "team", "--child-scope", "Child B:local", "--json", env=env)
    require(r.returncode == 0, f"save-group failed: {r.stdout} / {r.stderr}")
    payload = json.loads(r.stdout)
    scopes = {item["title"]: item["frontmatter"]["scope"] for item in payload["records"]}
    require(scopes["Hub"] == "team" and scopes["Child A"] == "team" and scopes["Child B"] == "local",
            f"save-group should inherit and override scope: {payload}")

    r = run(str(AGENT_OBSIDIAN), "move", "Alpha", "Projects/Renamed Alpha",
            "--update-links", "--json", env=env)
    require(r.returncode == 0, f"move failed: {r.stdout} / {r.stderr}")
    r = run(str(AGENT_OBSIDIAN), "read", "Beta", "--json", env=env)
    payload = json.loads(r.stdout)
    require("[[Renamed Alpha]]" in payload["note"]["body"],
            f"move --update-links should rewrite Beta backlink: {payload}")

    r = run(str(AGENT_OBSIDIAN), "audit", "--json", env=env)
    require(r.returncode == 0, f"audit failed: {r.stdout} / {r.stderr}")
    payload = json.loads(r.stdout)
    require((vault / ".agent-do" / "context" / "ledger" / "vault-audit.jsonl").exists(),
            f"audit should write ledger: {payload}")
    missing = next(item for item in payload["findings"] if item["kind"] == "missing-frontmatter")
    r = run(str(AGENT_OBSIDIAN), "audit", "fix", missing["id"], "--json", env=env)
    require(r.returncode == 0, f"audit fix missing-frontmatter failed: {r.stdout} / {r.stderr}")
    fixed = json.loads(r.stdout)
    require(fixed["record"]["frontmatter"]["scope"] == "local",
            f"audit fix should add safe frontmatter: {fixed}")


def test_semantic_search_uses_stored_embeddings(tmp: Path) -> None:
    """Semantic search should use the stored chunk embeddings, not keyword
    coincidence. The provider call is monkeypatched so this remains an offline
    engine test while exercising the real chunk/embedding tables.
    """
    engine = load_obsidian_engine()
    vault = make_local_vault(tmp / "semantic")
    rt = engine.Runtime(vault=vault, json_mode=True, repo_root=ROOT)
    engine.refresh(rt, full=True)

    alpha_vec = [1.0] + [0.0] * 1023
    other_vec = [0.0, 1.0] + [0.0] * 1022
    profile = engine.model_profile(rt, "embedding")
    with engine.connect(rt) as conn:
        rows = list(conn.execute("SELECT * FROM chunks ORDER BY note_path, ordinal"))
        for row in rows:
            text = row["text"] or ""
            vector = alpha_vec if "Saoshyant" in text else other_vec
            conn.execute(
                """
                INSERT OR REPLACE INTO embeddings
                (chunk_id,provider,model,dimension,content_hash,embedding_json,embedded_at)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    row["chunk_id"],
                    profile["provider"],
                    profile["model"],
                    profile["dimension"],
                    row["content_hash"],
                    json.dumps(vector),
                    engine.utc_now(),
                ),
            )
        conn.commit()

    original_embed_texts = engine.embed_texts

    def fake_embed_texts(_profile, texts, *, input_type):
        require(input_type == "query", f"semantic search should embed query text: {input_type}")
        return [alpha_vec for _ in texts]

    engine.embed_texts = fake_embed_texts
    try:
        results = engine.search_notes(rt, "messiah pattern", limit=1, mode="semantic")
        require(results and results[0]["path"] == "Projects/Alpha.md",
                f"semantic search should rank by vector similarity: {results}")
        context = engine.build_context_payload(rt, "messiah pattern", limit=1, mode="semantic")
        require("Projects/Alpha.md:" in context["context"],
                f"semantic context should include cited source lines: {context}")
    finally:
        engine.embed_texts = original_embed_texts


def test_chunker_splits_oversized_unbroken_text() -> None:
    engine = load_obsidian_engine()
    max_tokens = 100
    text = "x" * (max_tokens * 10)
    parts = engine.split_text_for_model(text, max_tokens)
    require(len(parts) > 1, f"oversized unbroken text should split: {len(parts)}")
    require("".join(parts) == text, "splitter must preserve content")
    require(
        all(engine.estimate_tokens(part) <= max_tokens for part in parts),
        f"all split parts should fit the requested token estimate: {[engine.estimate_tokens(part) for part in parts]}",
    )


def test_local_vault_refresh_reports_walk_errors(tmp: Path) -> None:
    """Vault scan errors must fail closed instead of returning success with
    parsed=0. This catches macOS privacy / filesystem denial paths where
    os.walk would otherwise silently produce an empty scan.
    """
    engine = load_obsidian_engine()
    vault = tmp / "blocked-vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "Visible.md").write_text("# Visible\n", encoding="utf-8")
    rt = engine.Runtime(vault=vault, json_mode=True, repo_root=ROOT)

    original_walk = engine.os.walk

    def blocked_walk(path, onerror=None):
        if onerror is not None:
            onerror(PermissionError(1, "Operation not permitted", str(path)))
        if False:
            yield None

    engine.os.walk = blocked_walk
    try:
        try:
            engine.refresh(rt, full=True, verbose=True)
        except engine.AgentObsidianError as exc:
            require(exc.message == "vault scan failed", f"unexpected error: {exc.message}")
            require(exc.payload["walk_errors"][0]["type"] == "PermissionError",
                    f"walk error should be surfaced: {exc.payload}")
            require("recommendation" in exc.payload,
                    f"permission failure should include remediation: {exc.payload}")
        else:
            raise AssertionError("refresh should fail when the vault walk reports an error")
    finally:
        engine.os.walk = original_walk


def main() -> int:
    test_static_artifacts()
    test_registry_entry()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_cli = tmp / "obsidian"
        log_file = tmp / "obsidian.log"
        write_fake_obsidian(fake_cli, log_file)

        env_with_cli = base_env(tmp, log_file, fake_cli=fake_cli)
        env_no_cli = base_env(tmp, log_file, fake_cli=None)

        test_help_and_unknown(env_with_cli)
        test_doctor_missing(env_no_cli)
        test_doctor_present(env_with_cli)
        test_snapshot(env_with_cli, env_no_cli)
        test_non_responsive_cli(tmp, log_file)
        test_snapshot_app_not_running(tmp, log_file)
        test_content_with_flag_literals(env_with_cli, log_file)
        test_argv_passthrough(env_with_cli, log_file)
        test_live_gating(env_with_cli, log_file)
        test_local_vault_v2_surface(tmp, log_file)
        test_semantic_search_uses_stored_embeddings(tmp)
        test_chunker_splits_oversized_unbroken_text()
        test_local_vault_refresh_reports_walk_errors(tmp)

    print("obsidian tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
