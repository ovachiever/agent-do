#!/usr/bin/env python3
"""Focused tests for optional AI-backed suggest routing."""

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


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        fake = Path(tmpdir) / "anthropic.py"
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
        assert "deploy this on vercel and check logs" in prompt
        return _Response({
            "tool": "vercel",
            "primary": "agent-do vercel deploy <project>",
            "entrypoints": [
                "agent-do vercel deploy <project>",
                "agent-do vercel logs <deployment>"
            ],
            "confidence": 0.94,
            "reason": "deploy is the action-specific command"
        })


class Anthropic:
    def __init__(self):
        self.messages = _Messages()
""",
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{tmpdir}:{env.get('PYTHONPATH', '')}"
        env["ANTHROPIC_API_KEY"] = "test-key"
        env["AGENT_DO_SUGGEST_AI"] = "1"
        env.pop("AGENT_DO_AI_MODEL", None)
        env.pop("AGENT_DO_AI_MAX_TOKENS", None)
        env.pop("AGENT_DO_AI_EFFORT", None)

        result = subprocess.run(
            [
                str(ROOT / "agent-do"),
                "suggest",
                "deploy this on vercel and check logs",
                "--json",
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        require(result.returncode == 0, f"suggest failed: {result.stderr}\n{result.stdout}")
        payload = json.loads(result.stdout)
        top = payload["results"][0]
        require(top["tool"] == "vercel", f"unexpected top tool: {payload}")
        require(top["source"] == "ai", f"expected ai source: {payload}")
        require(top["primary"] == "agent-do vercel deploy <project>", f"unexpected primary: {payload}")
        require(
            "agent-do vercel logs <deployment>" in top["entrypoints"],
            f"expected log follow-up: {payload}",
        )

    print("suggest AI tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
