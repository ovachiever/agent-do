#!/usr/bin/env python3
"""Codex-compatible PreToolUse wrapper.

Claude accepts PreToolUse `additionalContext`; Codex currently rejects that
field for PreToolUse. This wrapper still runs the shared hook for telemetry and
compatibility checks, but suppresses stdout so Codex never receives an
unsupported payload.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    payload = sys.stdin.read()
    hook = Path(__file__).with_name("agent-do-pretooluse-check.py")
    if not hook.exists():
        return 0

    try:
        subprocess.run(
            [sys.executable, str(hook)],
            input=payload,
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
    except Exception:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
