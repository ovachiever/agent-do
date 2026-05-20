#!/usr/bin/env python3
"""Regression tests for hook outcome telemetry correlation."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(*args: str, input_text: str | None = None, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=ROOT,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def event_types(home: Path) -> list[str]:
    return [event["event_type"] for event in read_jsonl(home / "telemetry" / "events.jsonl")]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir) / "agent-home"
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(home)
        env["AGENT_DO_HOOK_AI"] = "0"
        env["AGENT_DO_HOOK_RUNTIME"] = "claude"
        env["AGENT_DO_TELEMETRY_PENDING_ACTIONS"] = "2"

        clear = run(str(ROOT / "agent-do"), "nudges", "clear", "--json", env=env)
        require(clear.returncode == 0, f"nudges clear failed: {clear.stderr}")

        pretool = run(
            "python3",
            "hooks/claude/agent-do-pretooluse-check.py",
            input_text='{"tool_name":"Bash","tool_input":{"command":"npx playwright test"}}',
            env=env,
        )
        require(pretool.returncode == 0, f"pretool hook failed: {pretool.stderr}")
        require("agent-do browse" in pretool.stdout, f"expected browse nudge: {pretool.stdout}")
        require("hook_emitted" in event_types(home), f"expected hook_emitted event: {event_types(home)}")
        require(list((home / "telemetry" / "pending").glob("*.json")), "expected pending nudge")

        followed = run(str(ROOT / "agent-do"), "browse", "--help", env=env)
        require(followed.returncode == 0, f"browse help failed: {followed.stderr}")
        types_after_follow = event_types(home)
        require("agent_tool_call" in types_after_follow, f"missing tool call event: {types_after_follow}")
        require("agent_tool_result" in types_after_follow, f"missing tool result event: {types_after_follow}")
        require("hook_followed" in types_after_follow, f"missing hook_followed event: {types_after_follow}")
        require(not list((home / "telemetry" / "pending").glob("*.json")), "followed nudge should be resolved")

        second_pretool = run(
            "python3",
            "hooks/claude/agent-do-pretooluse-check.py",
            input_text='{"tool_name":"Bash","tool_input":{"command":"npx playwright test"}}',
            env=env,
        )
        require(second_pretool.returncode == 0, f"second pretool hook failed: {second_pretool.stderr}")

        for _ in range(2):
            unrelated = run(str(ROOT / "agent-do"), "coord", "status", env=env)
            require(unrelated.returncode == 0, f"coord status failed: {unrelated.stderr}")

        types_after_ignore = event_types(home)
        require("hook_ignored" in types_after_ignore, f"missing hook_ignored event: {types_after_ignore}")

        prompt = run(
            "python3",
            "hooks/claude/agent-do-prompt-router.py",
            input_text='{"prompt":"maybe look around"}',
            env=env,
        )
        require(prompt.returncode == 0, f"prompt hook failed: {prompt.stderr}")
        require(prompt.stdout.strip() == "", f"expected prompt hook silence: {prompt.stdout}")
        decision_events = [
            event for event in read_jsonl(home / "telemetry" / "events.jsonl")
            if event["event_type"] == "hook_decision" and event.get("hook") == "UserPromptSubmit"
        ]
        require(decision_events, "expected UserPromptSubmit decision telemetry")
        require(decision_events[-1]["decision"] == "suppress", f"expected suppress decision: {decision_events[-1]}")

        harness = run(str(ROOT / "agent-do"), "harness", "nudges", "effectiveness", "--json", env=env)
        require(harness.returncode == 0, f"harness effectiveness failed: {harness.stderr}")
        payload = json.loads(harness.stdout)
        summary = payload["summary"]
        require(payload["compliance"]["status"] == "available", f"expected available compliance: {payload}")
        require(summary["followed"] >= 1, f"expected followed count: {payload}")
        require(summary["ignored"] >= 1, f"expected ignored count: {payload}")
        require(summary["resolved"] >= 2, f"expected resolved count: {payload}")
        require(summary["follow_through_rate"] is not None, f"expected follow-through rate: {payload}")

    print("hook outcome telemetry tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
