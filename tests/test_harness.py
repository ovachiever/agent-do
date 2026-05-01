#!/usr/bin/env python3
"""Harness inventory regression tests."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(*args: str, cwd: Path = ROOT, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("AGENT_DO_HOME", str(ROOT / ".dev" / "test-home"))
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def run_agent_do(*args: str, cwd: Path = ROOT, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return run(str(ROOT / "agent-do"), *args, cwd=cwd, extra_env=extra_env)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def main() -> int:
    help_result = run_agent_do("harness", "--help")
    require(help_result.returncode == 0, f"harness help failed: {help_result.stderr}")
    require("agent-harness" in help_result.stdout, f"unexpected help output: {help_result.stdout}")

    text_result = run_agent_do("harness", "inspect")
    require(text_result.returncode == 0, f"harness inspect failed: {text_result.stderr}")
    require("agent-do harness" in text_result.stdout, f"unexpected text output: {text_result.stdout}")
    require("Tools: 89" in text_result.stdout, f"expected current tool count in text output: {text_result.stdout}")

    json_result = run_agent_do("harness", "inspect", "--json")
    require(json_result.returncode == 0, f"harness inspect --json failed: {json_result.stderr}")
    payload = json.loads(json_result.stdout)
    require(payload["ok"] is True, f"expected ok payload: {payload}")
    require(payload["summary"]["tools"] == 89, f"expected 89 tools: {payload['summary']}")
    require(payload["summary"]["by_type"]["tool"] == 89, f"expected tool component count: {payload['summary']}")

    global_json_result = run_agent_do("harness", "--json", "inspect")
    require(global_json_result.returncode == 0, f"harness global --json failed: {global_json_result.stderr}")
    require(json.loads(global_json_result.stdout)["ok"] is True, "global --json should emit JSON")

    components = {component["id"]: component for component in payload["components"]}
    for component_id in [
        "registry:agent-do",
        "hook:user-prompt-submit",
        "hook:pretooluse-codex",
        "tool:harness",
        "tool:context",
        "tool:zpc",
    ]:
        require(component_id in components, f"missing harness component {component_id}")

    harness_tool = components["tool:harness"]
    require("tools/agent-harness" in harness_tool["files"], f"missing harness tool file: {harness_tool}")
    for command in ["inspect", "nudges", "evidence", "manifest"]:
        require(command in harness_tool["commands"], f"missing {command} command: {harness_tool}")
    require(harness_tool["concurrency"] == "read", f"harness should be read-only: {harness_tool}")

    prompt_hook = components["hook:user-prompt-submit"]
    require("tests/test_prompt_hook_ai.py" in prompt_hook["tests"], f"missing hook tests: {prompt_hook}")
    require("~/.agent-do/telemetry/nudges.jsonl" in prompt_hook["state"], f"missing hook state ref: {prompt_hook}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        agent_home = tmp_path / "agent-home"
        telemetry_path = agent_home / "telemetry" / "nudges.jsonl"
        telemetry_path.parent.mkdir(parents=True)
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        telemetry_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "timestamp": timestamp,
                            "event_type": "prompt_suggestion",
                            "source": "UserPromptSubmit",
                            "tools": ["context", "harness"],
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": timestamp,
                            "event_type": "suggestion_suppressed",
                            "source": "UserPromptSubmit",
                            "tool": "coord",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        env = {"AGENT_DO_HOME": str(agent_home)}

        nudges_result = run_agent_do("harness", "nudges", "effectiveness", "--json", extra_env=env)
        require(nudges_result.returncode == 0, f"harness nudges failed: {nudges_result.stderr}")
        nudges_payload = json.loads(nudges_result.stdout)
        require(nudges_payload["summary"]["events"] == 2, f"unexpected nudge summary: {nudges_payload}")
        require(nudges_payload["summary"]["suppressed"] == 1, f"expected suppressed count: {nudges_payload}")
        require(nudges_payload["summary"]["by_tool"]["harness"] == 1, f"expected harness tool count: {nudges_payload}")

        evidence_dir = tmp_path / "evidence"
        evidence_result = run_agent_do(
            "harness",
            "evidence",
            "build",
            "demo-session",
            "--out",
            str(evidence_dir),
            "--json",
            cwd=tmp_path,
            extra_env=env,
        )
        require(evidence_result.returncode == 0, f"harness evidence build failed: {evidence_result.stderr}")
        evidence_payload = json.loads(evidence_result.stdout)
        require(evidence_payload["ok"] is True, f"expected evidence ok payload: {evidence_payload}")
        for filename in [
            "overview.md",
            "timeline.jsonl",
            "session_context.json",
            "nudges.jsonl",
            "coord.json",
            "git_status.txt",
            "diff.patch",
            "root_cause.md",
        ]:
            require((evidence_dir / filename).exists(), f"missing evidence artifact {filename}")

        manifest_result = run_agent_do(
            "harness",
            "manifest",
            "new",
            "demo-change",
            "--component-type",
            "tool",
            "--file",
            "tools/agent-demo",
            "--predicted-fix",
            "case-a",
            "--risk-regression",
            "case-b",
            "--json",
            cwd=tmp_path,
            extra_env=env,
        )
        require(manifest_result.returncode == 0, f"harness manifest new failed: {manifest_result.stderr}")
        manifest_payload = json.loads(manifest_result.stdout)
        manifest_path = Path(manifest_payload["path"])
        require(manifest_path.exists(), f"manifest was not written: {manifest_payload}")

        before_path = tmp_path / "before.json"
        after_path = tmp_path / "after.json"
        write_json(before_path, {"cases": [{"id": "case-a", "passed": False}, {"id": "case-b", "passed": True}]})
        write_json(after_path, {"cases": [{"id": "case-a", "passed": True}, {"id": "case-b", "passed": True}]})
        verify_result = run_agent_do(
            "harness",
            "manifest",
            "verify",
            "demo-change",
            "--before",
            str(before_path),
            "--after",
            str(after_path),
            "--json",
            cwd=tmp_path,
            extra_env=env,
        )
        require(verify_result.returncode == 0, f"harness manifest verify failed: {verify_result.stderr}")
        verify_payload = json.loads(verify_result.stdout)
        require(verify_payload["verdict"] == "keep", f"expected keep verdict: {verify_payload}")
        require(verify_payload["comparison"]["landed_predicted_fixes"] == ["case-a"], f"missing landed fix: {verify_payload}")

    print("harness tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
