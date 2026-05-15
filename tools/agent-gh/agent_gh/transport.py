"""gh CLI subprocess transport."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any


class GhError(RuntimeError):
    """Raised when a gh CLI call fails or the binary is unavailable."""


def gh_bin() -> str:
    """Return the path to the gh binary, raising GhError if not found."""
    configured = os.environ.get("AGENT_GH_BIN")
    if configured:
        return configured
    found = shutil.which("gh")
    if not found:
        raise GhError("gh CLI not found. Install GitHub CLI and run `gh auth login`.")
    return found


def run_gh(args: list[str], *, input_text: str | None = None, timeout: int = 60) -> str:
    """Run a gh CLI command and return stdout, raising GhError on failure or timeout."""
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
    """Run a gh CLI command and parse the JSON output, raising GhError on bad JSON."""
    output = run_gh(args, input_text=input_text).strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise GhError(f"gh returned invalid JSON for {' '.join(args)}: {exc}") from exc


def command_available(cmd: str) -> bool:
    """Return True if the given command exists on PATH."""
    return shutil.which(cmd) is not None


def run_optional(cmd: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str] | None:
    """Run a command, returning None on failure or timeout instead of raising."""
    try:
        return subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
