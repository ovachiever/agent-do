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
import subprocess
import tempfile
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"
AGENT_OBSIDIAN = ROOT / "tools" / "agent-obsidian"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


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
    for key in ("AGENT_DO_LIVE", "AGENT_DO_LIVE_SPEC", "AGENT_DO_LIVE_CONTEXT"):
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
    import yaml  # type: ignore

    registry = yaml.safe_load((ROOT / "registry.yaml").read_text())
    require("obsidian" in registry["tools"], "registry.yaml must declare tools.obsidian")
    entry = registry["tools"]["obsidian"]
    for key in ("description", "capabilities", "commands", "examples", "routing", "concurrency"):
        require(key in entry, f"obsidian registry entry missing key: {key}")
    require(entry["concurrency"] == "mixed", f"unexpected concurrency: {entry['concurrency']}")
    for cmd in ("doctor", "snapshot", "read", "create", "append", "search",
                "daily", "prop", "tasks", "tags", "backlinks",
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

    print("obsidian tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
