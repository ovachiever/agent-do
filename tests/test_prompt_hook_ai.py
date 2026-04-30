#!/usr/bin/env python3
"""Focused tests for AI-backed UserPromptSubmit routing."""

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


def run_hook(prompt: str, *, cwd: Path | None = None, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    payload = {"prompt": prompt}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return subprocess.run(
        ["python3", "hooks/agent-do-prompt-router.py"],
        cwd=ROOT,
        env=env,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake = tmp / "anthropic.py"
        fake.write_text(
            """
import json


class _Chunk:
    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, payload):
        self.content = [_Chunk(json.dumps(payload))]


class _Messages:
    def create(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        assert kwargs["model"] == "claude-sonnet-4-6"
        assert kwargs["max_tokens"] == 64000
        assert kwargs["thinking"] == {"type": "adaptive", "display": "omitted"}
        assert kwargs["output_config"] == {"effort": "max"}
        assert '"tool": "vercel"' in prompt
        assert '"tool": "context"' in prompt
        assert "Candidate tools" not in prompt

        if "deploy this on vercel and check logs" in prompt:
            return _Response({
                "prompt_kind": "work_starting",
                "starts_work": True,
                "coord": {"block": False, "reason": "", "focus_command": ""},
                "emit_tools": True,
                "tool_suggestions": [{
                    "tool": "vercel",
                    "command": "agent-do vercel deploy <project>",
                    "why": "deployment is the requested first action",
                    "confidence": 0.94
                }]
            })

        if "fix the render config in this repo" in prompt:
            return _Response({
                "prompt_kind": "work_starting",
                "starts_work": True,
                "coord": {
                    "block": True,
                    "reason": "active peer exists and repo work is starting",
                    "focus_command": "agent-do coord focus set \\"fix render config\\" --path render.yaml"
                },
                "emit_tools": False,
                "tool_suggestions": []
            })

        if "wait what was pr 6" in prompt:
            return _Response({
                "prompt_kind": "discussion",
                "starts_work": False,
                "coord": {"block": False, "reason": "", "focus_command": ""},
                "emit_tools": False,
                "tool_suggestions": []
            })

        return _Response({
            "prompt_kind": "other",
            "starts_work": False,
            "coord": {"block": False, "reason": "", "focus_command": ""},
            "emit_tools": True,
            "tool_suggestions": [{
                "tool": "context",
                "command": "agent-do context search authentication",
                "why": "weak match",
                "confidence": 0.2
            }]
        })


class Anthropic:
    def __init__(self):
        self.messages = _Messages()
""",
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{tmp}:{env.get('PYTHONPATH', '')}"
        env["ANTHROPIC_API_KEY"] = "test-key"
        env["AGENT_DO_HOOK_AI"] = "1"
        env.pop("AGENT_DO_AI_MODEL", None)
        env.pop("AGENT_DO_AI_MAX_TOKENS", None)
        env.pop("AGENT_DO_AI_EFFORT", None)

        suggest = run_hook("deploy this on vercel and check logs", env=env)
        require(suggest.returncode == 0, f"AI prompt hook failed: {suggest.stderr}\\n{suggest.stdout}")
        suggest_payload = json.loads(suggest.stdout)
        suggest_context = suggest_payload["hookSpecificOutput"]["additionalContext"]
        require("agent-do vercel deploy <project>" in suggest_context, f"expected exact AI suggestion: {suggest_context}")
        require("agent-do context search" not in suggest_context, f"unexpected weak context suggestion: {suggest_context}")

        weak = run_hook("maybe look around", env=env)
        require(weak.returncode == 0, f"weak AI prompt hook failed: {weak.stderr}")
        require(weak.stdout.strip() == "", f"expected low-confidence suggestion suppression, got: {weak.stdout}")

        project = tmp / "project"
        project.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        coord_home = tmp / "coord-home"
        peer_env = dict(env)
        peer_env["AGENT_DO_HOME"] = str(coord_home)
        peer_env["CODEX_THREAD_ID"] = "peer-one"
        subprocess.run(
            [str(ROOT / "agent-do"), "coord", "touch", "--json"],
            cwd=project,
            env=peer_env,
            text=True,
            capture_output=True,
            check=True,
        )

        current_env = dict(env)
        current_env["AGENT_DO_HOME"] = str(coord_home)
        current_env["CODEX_THREAD_ID"] = "peer-two"

        block = run_hook("fix the render config in this repo", cwd=project, env=current_env)
        require(block.returncode == 0, f"coord AI block failed: {block.stderr}")
        block_payload = json.loads(block.stdout)
        require(block_payload.get("decision") == "block", f"expected coord block: {block_payload}")
        require("agent-do coord focus set" in block_payload.get("reason", ""), f"expected focus command: {block_payload}")
        require("render.yaml" in block_payload.get("reason", ""), f"expected AI focus path: {block_payload}")

        discussion = run_hook("wait what was pr 6?", cwd=project, env=current_env)
        require(discussion.returncode == 0, f"discussion hook failed: {discussion.stderr}")
        require(discussion.stdout.strip() == "", f"expected discussion prompt to pass silently: {discussion.stdout}")

    print("prompt hook AI tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
