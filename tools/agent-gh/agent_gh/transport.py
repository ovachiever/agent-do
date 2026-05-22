from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

class GhError(RuntimeError):
    pass

def gh_bin() -> str:
    configured = os.environ.get("AGENT_GH_BIN")
    if configured:
        return configured
    found = shutil.which("gh")
    if not found:
        raise GhError("gh CLI not found. Install GitHub CLI and run `gh auth login`.")
    return found

def run_gh(args: list[str], *, input_text: str | None = None, timeout: int = 60) -> str:
    cmd = [gh_bin(), *args]
    try:
        result = subprocess.run(
            cmd,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise GhError(f"gh {' '.join(args)} timed out after {timeout}s") from exc
    except OSError as exc:
        raise GhError(f"gh {' '.join(args)} failed to start: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown gh error"
        raise GhError(f"gh {' '.join(args)} failed: {detail}")
    return result.stdout

def gh_json(args: list[str], *, input_text: str | None = None) -> Any:
    output = run_gh(args, input_text=input_text).strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise GhError(f"gh returned invalid JSON for {' '.join(args)}: {exc}") from exc

def command_available(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def run_optional(cmd: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
