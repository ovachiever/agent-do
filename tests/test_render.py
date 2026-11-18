#!/usr/bin/env python3
"""Focused coverage for agent-render logs."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    help_result = subprocess.run(
        ["./agent-do", "render", "logs", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    require(help_result.returncode == 0, f"render logs --help failed: {help_result.stderr}")
    require("Usage: agent-render logs <resource> [options]" in help_result.stdout, f"unexpected render logs help: {help_result.stdout}")
    require("--since <time>" in help_result.stdout, f"expected logs help flags: {help_result.stdout}")

    temp_dir = tempfile.TemporaryDirectory()
    query_path = Path(temp_dir.name) / "render-queries.txt"
    render_script = f"""
set -euo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
resolve_service() {{
  echo "srv-test"
}}
normalize_log_time() {{
  if [[ "$1" == "60" ]]; then
    echo "2026-04-19T12:00:00Z"
  else
    echo "$1"
  fi
}}
render_request_checked() {{
  local method="$1"
  local endpoint="$2"
  if [[ "$endpoint" == "/services/srv-test" ]]; then
    printf '%s\\n' '{{"id":"srv-test","ownerId":"tea-test-owner"}}'
    return 0
  fi
  if [[ "$endpoint" == /logs\\?* ]]; then
    printf '%s\\n' "$endpoint" >> "{query_path}"
    printf '%s\\n' '{{"hasMore":true,"nextStartTime":"2026-04-19T11:00:00Z","nextEndTime":"2026-04-19T12:00:00Z","logs":[{{"timestamp":"2026-04-19T12:30:00Z","labels":[{{"name":"type","value":"app"}},{{"name":"level","value":"info"}}],"message":"\\u001b[0;32mhello\\u001b[0m"}}]}}'
    return 0
  fi
  echo "unexpected endpoint: $endpoint" >&2
  return 1
}}
render_request() {{
  render_request_checked "$@"
}}
cmd_logs my-render-service --since 60 --limit 5 --type app --level info --text error --host api.example.com --method GET --status 500 --path /billing
cmd_logs my-render-service --limit 5
"""

    result = run_bash(render_script)
    require(result.returncode == 0, f"render logs command failed: {result.stderr}")
    require(query_path.exists(), "expected query capture file to exist")
    queries = query_path.read_text().splitlines()
    require(len(queries) == 2, f"expected filtered and unfiltered queries, got: {queries}")
    query = queries[0]
    require(query.startswith("/logs?"), f"expected /logs endpoint, got: {query}")
    require("ownerId=tea-test-owner" in query, f"missing ownerId in query: {query}")
    require("resource=srv-test" in query, f"missing resource filter in query: {query}")
    require("startTime=2026-04-19T12%3A00%3A00Z" in query, f"missing startTime in query: {query}")
    require("limit=5" in query, f"missing limit in query: {query}")
    require("type=app" in query, f"missing type filter in query: {query}")
    require("level=info" in query, f"missing level filter in query: {query}")
    require("text=error" in query, f"missing text filter in query: {query}")
    require("host=api.example.com" in query, f"missing host filter in query: {query}")
    require("method=GET" in query, f"missing method filter in query: {query}")
    require("statusCode=500" in query, f"missing status code filter in query: {query}")
    require("path=%2Fbilling" in query, f"missing path filter in query: {query}")
    unfiltered_query = queries[1]
    require("ownerId=tea-test-owner" in unfiltered_query, f"missing ownerId: {unfiltered_query}")
    require("resource=srv-test" in unfiltered_query, f"missing resource: {unfiltered_query}")
    for unexpected in ("type=", "level=", "text=", "host=", "method=", "statusCode=", "path="):
        require(unexpected not in unfiltered_query, f"unexpected filter {unexpected}: {unfiltered_query}")

    require(result.stdout.count("[app/info] hello") == 2, f"unexpected render log output: {result.stdout}")
    require(result.stderr.count("More logs available.") == 2, f"expected pagination hints: {result.stderr}")
    temp_dir.cleanup()

    # Resources beyond srv-: crons by id, Postgres / Key Value ids (owner from
    # owner.id), one-off jobs via --job on their service, and the HTTP limit.
    temp_dir = tempfile.TemporaryDirectory()
    calls_path = Path(temp_dir.name) / "calls.txt"
    resources_script = f"""
set -uo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
resolve_service() {{ echo "srv-test"; }}
render_request_checked() {{
  printf '%s %s\\n' "${{RENDER_HTTP_TIMEOUT:-unset}}" "$2" >> "{calls_path}"
  case "$2" in
    /services/*) printf '%s' '{{"id":"x","ownerId":"tea-svc-owner"}}' ;;
    /postgres/dpg-test|/key-value/red-test) printf '%s' '{{"id":"x","owner":{{"id":"tea-db-owner"}}}}' ;;
    /logs\\?*) printf '%s' '{{"logs":[]}}' ;;
    *) echo "unexpected endpoint: $2" >&2; return 1 ;;
  esac
}}
cmd_logs crn-test --limit 1
cmd_logs dpg-test --limit 1
cmd_logs red-test --limit 1
cmd_logs my-worker --job job-abc123 --timeout 120 --limit 1
cmd_logs job-abc123 || echo "bare-job=$?"
cmd_logs my-worker --job nonsense || echo "bad-job=$?"
"""
    result = run_bash(resources_script)
    calls = calls_path.read_text().splitlines()
    require("90 /services/crn-test" not in calls and any(c.endswith("/services/crn-test") for c in calls),
            f"crn- ids must be looked up directly: {calls}")
    logs_calls = [c for c in calls if " /logs?" in c]
    require(len(logs_calls) == 4, f"expected four /logs calls: {calls}")
    require("ownerId=tea-svc-owner" in logs_calls[0] and "resource=crn-test" in logs_calls[0], logs_calls[0])
    require("ownerId=tea-db-owner" in logs_calls[1] and "resource=dpg-test" in logs_calls[1], logs_calls[1])
    require("ownerId=tea-db-owner" in logs_calls[2] and "resource=red-test" in logs_calls[2], logs_calls[2])
    require("ownerId=tea-svc-owner" in logs_calls[3] and "resource=job-abc123" in logs_calls[3], logs_calls[3])
    require(logs_calls[0].startswith("90 ") and logs_calls[3].startswith("120 "),
            f"logs must use --timeout (default 90): {logs_calls}")
    require(not any(c.startswith("90 /services") or c.startswith("120 /services") for c in calls),
            f"only the /logs call gets the long limit: {calls}")
    require("bare-job=2" in result.stdout and "--job job-abc123" in result.stderr,
            f"a bare job id must point at --job: {result.stdout!r} {result.stderr!r}")
    require("bad-job=2" in result.stdout, f"malformed --job must exit 2: {result.stdout!r}")
    temp_dir.cleanup()

    # No HTTP response (connection refused here) is reported as such, and the
    # helper leaves no RETURN trap behind to abort its caller under set -u.
    unreachable = run_bash(f"""
set -euo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
RENDER_API_KEY=test RENDER_API="http://127.0.0.1:9"
caller() {{ local r; r=$(render_request_checked GET /services/x) || {{ echo "caller-failed"; return 0; }}; }}
caller
render_request_checked GET /services/x >/dev/null 2>&1 || true
later() {{ :; }}
later
echo "caller-returned"
""")
    require("no HTTP response" in unreachable.stderr and "not a 'not found'" in unreachable.stderr,
            f"transport failure must say so: {unreachable.stderr!r}")
    require("caller-failed" in unreachable.stdout and "caller-returned" in unreachable.stdout
            and "unbound variable" not in unreachable.stderr,
            f"caller must survive the failed request: {unreachable.stdout!r} {unreachable.stderr!r}")

    print("render tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
