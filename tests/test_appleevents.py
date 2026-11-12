#!/usr/bin/env python3
"""Tests for the AppleEvents tool surface."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL_DIR = ROOT / "tools" / "agent-appleevents"
AGENT_DO = ROOT / "agent-do"
sys.path.insert(0, str(TOOL_DIR))
sys.path.insert(0, str(ROOT / "lib"))

import appleevents_ops as ops  # noqa: E402
import telemetry  # noqa: E402
from registry import find_raw_cli_equivalent, load_registry, match_prompt_tools  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(*args: str, env: dict[str, str] | None = None, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    run_env.setdefault("AGENT_DO_SUGGEST_AI", "0")
    return subprocess.run(
        list(args),
        cwd=ROOT,
        env=run_env,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def test_sdef_parser() -> None:
    fixture = TOOL_DIR / "test" / "fixtures" / "minimal.sdef.xml"
    parsed = ops.parse_sdef(fixture.read_text(encoding="utf-8"))
    require(parsed["counts"] == {"suites": 2, "commands": 2, "classes": 2, "properties": 3}, f"bad counts: {parsed['counts']}")
    standard = parsed["suites"][0]
    require(standard["commands"][0]["name"] == "open", "expected open command")
    require(standard["commands"][0]["parameters"][0]["name"] == "using", "expected command parameter")
    require(standard["classes"][0]["properties"][1]["name"] == "modified", "expected class property")


def test_classifier() -> None:
    cases = {
        "execution error: Not authorized to send Apple events. (-1743)": ("denied", -1743, "errAEEventNotPermitted"),
        "execution error: Application isn't running. (-600)": ("not_running", -600, "procNotFound"),
        "execution error: Can't get window 99. (-1728)": ("object_error", -1728, "errAENoSuchObject"),
        "execution error: Event not handled. (-1708)": ("event_not_handled", -1708, "errAEEventNotHandled"),
    }
    for stderr, expected in cases.items():
        result = ops.classify_appleevent_result(1, stderr)
        require(
            (result["automation"], result["osstatus"], result["name"]) == expected,
            f"bad classification for {stderr}: {result}",
        )
    allowed = ops.classify_appleevent_result(0, "")
    require(allowed["automation"] == "allowed", f"expected allowed result: {allowed}")


def test_registry_routing() -> None:
    registry = load_registry()
    require("appleevents" in registry["tools"], "appleevents missing from registry")
    entry = registry["tools"]["appleevents"]
    for command in ["probe", "dictionary", "terms", "compile", "permissions", "run", "tell"]:
        require(command in entry["commands"], f"missing registry command: {command}")

    equivalent = find_raw_cli_equivalent(registry, "osascript -e 'tell application \"Finder\" to get name'")
    require(equivalent is not None, "expected osascript raw equivalent")
    require(equivalent["tool"] == "appleevents", f"osascript should route to appleevents, got: {equivalent}")

    matches = match_prompt_tools(registry, "use osascript to control Xcode", limit=3)
    require(matches and matches[0]["tool"] == "appleevents", f"expected appleevents top prompt match: {matches}")


def test_telemetry_redacts_inline_scripts() -> None:
    args = ["tell", "Finder", "--script", 'return "secret-token-123"']
    preview = telemetry.command_preview("appleevents", args)
    shape = telemetry.args_shape(args, tool="appleevents")
    require("secret-token-123" not in preview, f"preview leaked script source: {preview}")
    require("secret-token-123" not in json.dumps(shape), f"args shape leaked script source: {shape}")
    require("<script:" in preview, f"preview should include script hash placeholder: {preview}")


def test_cli_help_and_live_gate() -> None:
    help_result = run(str(AGENT_DO), "appleevents", "--help")
    require(help_result.returncode == 0, f"help failed: {help_result.stderr}")
    require("agent-appleevents" in help_result.stdout and "permissions" in help_result.stdout, help_result.stdout)

    with tempfile.TemporaryDirectory() as tmpdir:
        env = {"AGENT_DO_HOME": tmpdir}
        denied = run(str(AGENT_DO), "appleevents", "permissions", "Finder", env=env)
        require(denied.returncode == 1, f"expected live denial: {denied.stdout} {denied.stderr}")
        payload = json.loads(denied.stdout)
        require(payload["action_required"] == "LIVE_APPROVAL_REQUIRED", f"bad live payload: {payload}")
        require("appleevents" in payload["rerun"], f"rerun should mention appleevents: {payload}")


def test_macos_static_commands() -> None:
    if platform.system() != "Darwin":
        result = run(str(AGENT_DO), "appleevents", "apps")
        payload = json.loads(result.stdout)
        require(result.returncode == 6, f"expected unsupported platform: {payload}")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        env = {"AGENT_DO_HOME": tmpdir}
        compile_result = run(
            str(AGENT_DO),
            "appleevents",
            "compile",
            "--language",
            "applescript",
            "--stdin",
            env=env,
            input_text="return 1\n",
        )
        require(compile_result.returncode == 0, f"compile failed: {compile_result.stdout} {compile_result.stderr}")
        compile_payload = json.loads(compile_result.stdout)
        require(compile_payload["compiled"] is True, f"expected compiled payload: {compile_payload}")
        require("return 1" not in compile_result.stdout, "compile output must not echo script source")

        probe_result = run(str(AGENT_DO), "appleevents", "probe", "Finder", "--json", env=env)
        require(probe_result.returncode == 0, f"probe failed: {probe_result.stdout} {probe_result.stderr}")
        probe_payload = json.loads(probe_result.stdout)
        require(probe_payload["bundle_id"] == "com.apple.finder", f"expected Finder bundle id: {probe_payload}")
        require(probe_payload["permissions"]["automation"] == "unknown", f"probe must not claim permission: {probe_payload}")
        require(probe_payload["sent_event"] is False, f"probe must not send event: {probe_payload}")

        dictionary_result = run(str(AGENT_DO), "appleevents", "dictionary", "Finder", "--format", "json", env=env)
        require(dictionary_result.returncode == 0, f"dictionary failed: {dictionary_result.stdout} {dictionary_result.stderr}")
        dictionary_payload = json.loads(dictionary_result.stdout)
        require(dictionary_payload["dictionary"]["counts"]["suites"] >= 1, f"expected suites: {dictionary_payload}")


def test_run_has_no_default_deadline() -> None:
    options = ops.parse_source_options(["--script", "return 1"])
    require(options["timeout"] is None, f"run must not impose a default deadline: {options}")
    options = ops.parse_source_options(["--script", "return 1", "--timeout", "600"])
    require(options["timeout"] == 600.0, f"--timeout must reach the run path: {options}")


def test_timeout_is_classified() -> None:
    if platform.system() != "Darwin":
        return
    # A bare delay sends no AppleEvent to any app, so this runs without a live gate.
    timed_out = ops.execute_script(source="delay 3", language="applescript", target=None, launch=False, timeout=1)
    require(timed_out["automation"] == "timed_out", f"timeout must not read as unknown_error: {timed_out}")
    require(timed_out["timeout_s"] == 1, f"payload must carry the deadline used: {timed_out}")
    require(ops.run_exit_code(timed_out) == ops.EXIT_TIMEOUT, f"timeout must exit {ops.EXIT_TIMEOUT}")

    finished = ops.execute_script(source="delay 1\nreturn 1", language="applescript", target=None, launch=False, timeout=None)
    require(finished["ok"] is True and finished["timeout_s"] is None, f"unbounded run must finish: {finished}")
    require(ops.run_exit_code(finished) == ops.EXIT_SUCCESS, "finished run must exit 0")


def main() -> int:
    test_run_has_no_default_deadline()
    test_timeout_is_classified()
    test_sdef_parser()
    test_classifier()
    test_registry_routing()
    test_telemetry_redacts_inline_scripts()
    test_cli_help_and_live_gate()
    test_macos_static_commands()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
