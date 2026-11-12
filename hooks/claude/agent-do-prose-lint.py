#!/usr/bin/env python3
"""PostToolUse prose feedback through the canonical, offline deai CLI.

Lint the saved document, including after Edit: rates and code-fence masking
need the whole file. This hook never rewrites text or blocks a completed edit.
No cooldown: each revision gets checked, including a fix followed by a new tell.
"""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
from pathlib import Path

AGENT_DO = Path(__file__).resolve().parents[2] / "agent-do"
PROSE_SUFFIXES = {".md", ".markdown", ".txt", ".rst"}
SKIP_PARTS = {".git", ".venv", "venv", "node_modules", "vendor", "dist", "build", "__pycache__"}
REGISTER_PATHS = {
    "drafts": "essay", "essays": "essay",
    "email": "email", "emails": "email",
    "product-answers": "product-answer", "product_answers": "product-answer",
}
# The installer gives this hook five seconds. Leave two for wrapper/dispatcher
# startup, process cleanup, and delivering the advisory before the host cutoff.
DEAI_TIMEOUT_SECONDS = 3
# Match the sibling quantity hook's six-row feedback window. Report omitted
# rule and occurrence counts, and give the command for deai's complete output.
MAX_FINDINGS_REPORTED = 6


def register_for(path: Path) -> str | None:
    if path.suffix.lower() not in PROSE_SUFFIXES:
        return None
    parents = [part.lower() for part in path.parts[:-1]]
    if any(part in SKIP_PARTS for part in parents):
        return None
    # The closest named directory wins for nested writing projects.
    return next((REGISTER_PATHS[part] for part in reversed(parents) if part in REGISTER_PATHS), "default")


def emit(message: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse", "additionalContext": message,
    }}))


def lint(path: Path, register: str) -> dict:
    command = [str(AGENT_DO), "deai", "lint", str(path), "--register", register, "--json"]
    # The dispatcher can have children. Own a process group so a timeout also
    # reaps its linter; never leave work running after the hook reports failure.
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True, start_new_session=True) as process:
        try:
            stdout, _ = process.communicate(timeout=DEAI_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise ValueError("deai exceeded the hook time budget") from None
    if process.returncode not in (0, 1):
        raise ValueError("deai failed to run")
    result = json.loads(stdout)
    if (not isinstance(result, dict) or result.get("schema") != "deai-result-v1"
            or result.get("success") is not True or result.get("command") != "lint"
            or result.get("register") != register):
        raise ValueError("deai returned an invalid result")
    files = result.get("files")
    if not isinstance(files, list) or len(files) != 1 or files[0].get("path") != str(path):
        raise ValueError("deai returned a different file")
    findings = files[0].get("findings")
    if (not isinstance(findings, list) or result.get("clean") is not (not findings)
            or files[0].get("clean") is not (not findings)
            or process.returncode != bool(findings)):
        raise ValueError("deai returned inconsistent findings")
    return files[0]


def render(path: str, register: str, findings: list[dict], command: str) -> str:
    lines = [f"Prose lint: deai flagged {path} (register: {register})."]
    shown = findings[:MAX_FINDINGS_REPORTED]
    for finding in shown:
        hits = finding["occurrences"]
        first = hits[0]
        lines.append(
            f"  {first['line']}:{first['column']} [{finding['rule']}] {finding['label']}"
            + (f" ({len(hits)} occurrences; first location shown)" if len(hits) > 1 else "")
        )
    if len(findings) > len(shown):
        lines.append(f"  {len(findings) - len(shown)} additional rules flagged.")
    lines += [
        "Review these locations and revise the prose before finishing. Preserve the intended meaning; "
        "these are editing signals, not an authorship verdict.",
        f"Complete findings: {command}",
        "AGENT_DO_PROSE_LINT=0 disables this advisory hook.",
    ]
    return "\n".join(lines)


def run(payload: object) -> None:
    if not isinstance(payload, dict) or payload.get("hook_event_name", "PostToolUse") != "PostToolUse":
        return
    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    raw_path = tool_input.get("file_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return
    response = payload.get("tool_response")
    if isinstance(response, dict) and (response.get("is_error") is True or response.get("success") is False):
        return
    cwd = payload.get("cwd")
    root = Path(cwd).resolve() if isinstance(cwd, str) and cwd else Path.cwd()
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    register = register_for(path)
    if register is None:
        return
    command = shlex.join(["agent-do", "deai", "lint", str(path), "--register", register, "--json"])
    try:
        if not path.is_file():
            raise ValueError("the saved file is unavailable")
        result = lint(path, register)
        if result["findings"]:
            emit(render(relative.as_posix(), register, result["findings"], command))
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError):
        # A failed check must never masquerade as a clean lint. Do not echo
        # subprocess output or source text into diagnostics or telemetry.
        emit(f"Prose lint could not check {relative.as_posix()}; the file remains unchecked. "
             f"Run {command} to diagnose and review it before finishing.")


def main() -> None:
    if os.environ.get("AGENT_DO_PROSE_LINT", "").strip() == "0":
        return
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return
    try:
        run(payload)
    except (OSError, ValueError, TypeError, RuntimeError):
        # Malformed host input has no document to diagnose. This is advisory.
        return


if __name__ == "__main__":
    main()
