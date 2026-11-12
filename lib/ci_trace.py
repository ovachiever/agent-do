#!/usr/bin/env python3
"""Normalize GitHub Actions evidence for deployment tracing.

This module deliberately has no network code. ``agent-ci`` obtains data with
the GitHub CLI, then calls these helpers to create a small, stable, safe JSON
surface for callers such as an incident tracker.

GitHub Actions logs are untrusted input. Before an excerpt is returned, common
credential forms and terminal control characters are removed. The caller also
gets machine-readable caps and truncation facts, so a short excerpt can never
be mistaken for a complete log.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import BinaryIO
from typing import Any


DEFAULT_LOG_LINES = 200
DEFAULT_LOG_BYTES = 65_536
MAX_LOG_LINES = 1_000
MAX_LOG_BYTES = 262_144


REDACT_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"rnd_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)\b(authorization)([=:]\s*(?:(?:bearer|basic)\s+)?)\S+"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)([=:]\s*)\S+"),
]
ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def redact(text: str) -> str:
    """Remove common secrets and terminal control characters from log text."""
    # Normalize control sequences first so they cannot split a credential and
    # make it recognizable only after redaction has already run.
    text = ANSI_ESCAPE.sub("", text)
    text = "".join(char for char in text if char in "\n\t" or ord(char) >= 32)
    for pattern in REDACT_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(lambda match: match.group(1) + match.group(2) + "[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def normalize_run(raw: dict[str, Any], repository: str, deployments: list[dict[str, Any]] | None,
                  deployment_error: str | None = None) -> dict[str, Any]:
    """Return only trace-relevant GitHub Actions run and job facts."""
    run = {
        "id": raw.get("databaseId"),
        "url": raw.get("url"),
        "repository": repository,
        "workflow": {
            "name": raw.get("workflowName"),
            "id": raw.get("workflowDatabaseId"),
        },
        "display_title": raw.get("displayTitle"),
        "head_sha": raw.get("headSha"),
        "head_branch": raw.get("headBranch"),
        "event": raw.get("event"),
        "status": raw.get("status"),
        "conclusion": raw.get("conclusion"),
        "timestamps": {
            "created_at": raw.get("createdAt"),
            "started_at": raw.get("startedAt"),
            "updated_at": raw.get("updatedAt"),
        },
    }
    jobs = []
    for job in raw.get("jobs") or []:
        jobs.append({
            "id": job.get("databaseId"),
            "name": job.get("name"),
            "status": job.get("status"),
            "conclusion": job.get("conclusion"),
            "started_at": job.get("startedAt"),
            "completed_at": job.get("completedAt"),
            "url": job.get("url"),
            "steps": [{
                "number": step.get("number"),
                "name": step.get("name"),
                "status": step.get("status"),
                "conclusion": step.get("conclusion"),
                "started_at": step.get("startedAt"),
                "completed_at": step.get("completedAt"),
            } for step in job.get("steps") or []],
        })
    if deployments is None:
        deployment_evidence = {
            "status": "degraded",
            "deployments": [],
            "reason": deployment_error or "GitHub deployment records were unavailable",
        }
    else:
        deployment_evidence = {
            "status": "available",
            "deployments": [{
                "id": deployment.get("id"),
                "environment": deployment.get("environment"),
                "original_environment": deployment.get("original_environment"),
                "ref": deployment.get("ref"),
                "sha": deployment.get("sha"),
                "task": deployment.get("task"),
                "created_at": deployment.get("created_at"),
                "updated_at": deployment.get("updated_at"),
                "url": deployment.get("url"),
                "creator": (deployment.get("creator") or {}).get("login"),
            } for deployment in deployments],
        }
    return {"success": True, "provider": "github-actions", "run": run, "jobs": jobs,
            "deployment_evidence": deployment_evidence}


def bounded_log(raw: str, run_id: str, failed_only: bool, tail: int, max_bytes: int,
                *, total_lines: int | None = None, source_truncated: bool = False) -> dict[str, Any]:
    """Redact and bound a log tail, preserving enough metadata for safe use."""
    if tail < 1 or tail > MAX_LOG_LINES:
        raise ValueError(f"--tail must be between 1 and {MAX_LOG_LINES}")
    if max_bytes < 1 or max_bytes > MAX_LOG_BYTES:
        raise ValueError(f"--max-bytes must be between 1 and {MAX_LOG_BYTES}")

    lines = raw.splitlines()
    selected = lines[-tail:]
    truncated_lines = (total_lines > tail if total_lines is not None else len(lines) > len(selected))
    excerpt = redact("\n".join(selected))
    encoded = excerpt.encode("utf-8")
    truncated_bytes = source_truncated or len(encoded) > max_bytes
    if len(encoded) > max_bytes:
        # Preserve valid UTF-8 and retain the newest portion of a tail.
        excerpt = encoded[-max_bytes:].decode("utf-8", errors="ignore")
        newline = excerpt.find("\n")
        if newline >= 0:
            excerpt = excerpt[newline + 1:]

    return {
        "success": True,
        "provider": "github-actions",
        "run_id": str(run_id),
        "failed_only": failed_only,
        "log": excerpt,
        "limits": {"tail_lines": tail, "max_bytes": max_bytes},
        "truncated": {
            "lines": truncated_lines,
            "bytes": truncated_bytes,
            "any": truncated_lines or truncated_bytes,
        },
        "redaction": {"applied": True},
    }


def bounded_log_stream(stream: BinaryIO, run_id: str, failed_only: bool, tail: int,
                       max_bytes: int) -> dict[str, Any]:
    """Build an excerpt while retaining at most the requested byte cap in memory.

    ``gh run view --log`` has no server-side byte limit. The ring retains one
    extra byte to identify a partial first line, which must be discarded before
    redaction: otherwise a cut can remove a credential's recognizable prefix.
    """
    if tail < 1 or tail > MAX_LOG_LINES:
        raise ValueError(f"--tail must be between 1 and {MAX_LOG_LINES}")
    if max_bytes < 1 or max_bytes > MAX_LOG_BYTES:
        raise ValueError(f"--max-bytes must be between 1 and {MAX_LOG_BYTES}")

    retained = bytearray()
    total_bytes = 0
    newline_count = 0
    ends_in_newline = False
    while chunk := stream.read(65_536):
        total_bytes += len(chunk)
        newline_count += chunk.count(b"\n")
        ends_in_newline = chunk.endswith(b"\n")
        retained.extend(chunk)
        if len(retained) > max_bytes + 1:
            del retained[:-(max_bytes + 1)]

    total_lines = newline_count + int(total_bytes > 0 and not ends_in_newline)
    source_truncated = total_bytes > max_bytes
    if source_truncated:
        preceding = retained[0]
        del retained[0]
        if preceding != ord("\n"):
            newline = retained.find(b"\n")
            retained = retained[newline + 1:] if newline >= 0 else bytearray()
    raw = retained.decode("utf-8", errors="ignore")
    return bounded_log(raw, run_id, failed_only, tail, max_bytes,
                       total_lines=total_lines, source_truncated=source_truncated)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    normalize = subcommands.add_parser("normalize-run")
    normalize.add_argument("repository")
    normalize.add_argument("--deployments-file")
    normalize.add_argument("--deployment-error")
    logs = subcommands.add_parser("bounded-log")
    logs.add_argument("run_id")
    logs.add_argument("--failed-only", action="store_true")
    logs.add_argument("--tail", type=int, default=DEFAULT_LOG_LINES)
    logs.add_argument("--max-bytes", type=int, default=DEFAULT_LOG_BYTES)
    stream_logs = subcommands.add_parser("bounded-log-stream")
    stream_logs.add_argument("run_id")
    stream_logs.add_argument("--failed-only", action="store_true")
    stream_logs.add_argument("--tail", type=int, default=DEFAULT_LOG_LINES)
    stream_logs.add_argument("--max-bytes", type=int, default=DEFAULT_LOG_BYTES)
    args = parser.parse_args()

    try:
        if args.command == "normalize-run":
            raw = json.load(sys.stdin)
            deployments = None
            if args.deployments_file:
                with open(args.deployments_file, encoding="utf-8") as deployment_file:
                    deployments = json.load(deployment_file)
                if isinstance(deployments, list) and all(isinstance(page, list) for page in deployments):
                    deployments = [deployment for page in deployments for deployment in page]
                if not isinstance(deployments, list):
                    raise ValueError("GitHub deployments response was not a JSON list")
            result = normalize_run(raw, args.repository, deployments, args.deployment_error)
        elif args.command == "bounded-log":
            result = bounded_log(sys.stdin.read(), args.run_id, args.failed_only, args.tail, args.max_bytes)
        else:
            result = bounded_log_stream(sys.stdin.buffer, args.run_id, args.failed_only, args.tail, args.max_bytes)
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"success": False, "error": str(error), "code": 2}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
