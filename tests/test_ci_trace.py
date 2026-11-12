#!/usr/bin/env python3
"""Offline contract tests for the incident-tracker GitHub Actions read surface.

The test uses a fake ``gh`` executable. It proves the wrapper asks GitHub for
the fields a deployment trace needs, turns them into a stable JSON document,
and never returns an unbounded or unredacted log excerpt.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


RUN = {
    "databaseId": 48201933,
    "workflowName": "deploy-production.yml",
    "workflowDatabaseId": 91,
    "displayTitle": "Deploy payments",
    "status": "completed",
    "conclusion": "success",
    "headBranch": "main",
    "headSha": "abc123def456",
    "event": "push",
    "createdAt": "2026-10-12T20:00:00Z",
    "startedAt": "2026-10-12T20:01:00Z",
    "updatedAt": "2026-10-12T20:03:00Z",
    "url": "https://github.example/owner/repo/actions/runs/48201933",
    "jobs": [{
        "databaseId": 3,
        "name": "deploy",
        "status": "completed",
        "conclusion": "success",
        "startedAt": "2026-10-12T20:01:10Z",
        "completedAt": "2026-10-12T20:02:50Z",
        "url": "https://github.example/job/3",
        "steps": [{
            "number": 1,
            "name": "Deploy",
            "status": "completed",
            "conclusion": "success",
            "startedAt": "2026-10-12T20:01:20Z",
            "completedAt": "2026-10-12T20:02:40Z",
        }],
    }],
}

FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ['GH_CALL_LOG'], 'a') as log:
    log.write(' '.join(args) + '\\n')
if args[:2] == ['run', 'view'] and '--json' in args:
    print(json.dumps(%s))
elif args[:2] == ['run', 'view']:
    print('old line')
    print('Authorization: Bearer super-secret-token')
    print('token=plain-secret')
    print('ghp_' + 'abcdefghijklmnopqrstuvwxyz123456')
    print('newest line')
elif args[0] == 'api':
    print(json.dumps([{
        'id': 88, 'environment': 'production', 'original_environment': 'production',
        'ref': 'main', 'sha': 'abc123def456', 'task': 'deploy',
        'created_at': '2026-10-12T20:02:00Z', 'updated_at': '2026-10-12T20:03:00Z',
        'url': 'https://api.github.example/deployments/88', 'creator': {'login': 'octo'}
    }]))
else:
    print('unexpected gh invocation: ' + ' '.join(args), file=sys.stderr)
    sys.exit(2)
""" % repr(RUN)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        binp = tmp / "bin"; binp.mkdir()
        gh = binp / "gh"; gh.write_text(FAKE_GH); gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        call_log = tmp / "calls.log"
        work = tmp / "not-a-repository"; work.mkdir()
        env = dict(os.environ, PATH=f"{binp}:{os.environ['PATH']}", GH_CALL_LOG=str(call_log),
                   PYTHONDONTWRITEBYTECODE="1")

        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([str(ROOT / "tools" / "agent-ci"), *args], cwd=work, env=env,
                                  text=True, capture_output=True, check=False)

        details = run("details", "48201933", "--repo", "owner/repo", "--json")
        require(details.returncode == 0, f"details failed: {details.stdout} {details.stderr}")
        body = json.loads(details.stdout)
        require(body["provider"] == "github-actions", f"wrong provider: {body}")
        require(body["run"]["head_sha"] == "abc123def456", f"head SHA missing: {body}")
        require(body["run"]["workflow"] == {"name": "deploy-production.yml", "id": 91},
                f"workflow not normalized: {body}")
        require(body["run"]["timestamps"]["started_at"] == "2026-10-12T20:01:00Z"
                and body["run"]["timestamps"]["updated_at"] == "2026-10-12T20:03:00Z",
                f"run timestamps missing: {body}")
        require(body["jobs"][0]["steps"][0]["conclusion"] == "success",
                f"job/step facts missing: {body}")
        require(body["deployment_evidence"]["status"] == "available", f"deployments missing: {body}")
        require(body["deployment_evidence"]["deployments"][0]["environment"] == "production",
                f"deployment facts missing: {body}")
        calls = call_log.read_text().splitlines()
        require("--repo owner/repo" in calls[-2], f"details lost explicit repo: {calls}")
        require("repos/owner/repo/deployments?sha=abc123def456" in calls[-1],
                f"details did not fetch matching deployment records: {calls}")
        for required in ("headSha", "workflowDatabaseId", "startedAt", "updatedAt", "jobs"):
            require(required in calls[-2], f"details did not request {required}: {calls[-2]}")

        logs = run("logs", "48201933", "--failed", "--tail", "2", "--max-bytes", "4096",
                   "--repo", "owner/repo", "--json")
        require(logs.returncode == 0, f"logs failed: {logs.stdout} {logs.stderr}")
        body = json.loads(logs.stdout)
        require(body["failed_only"] is True, f"failed-only fact missing: {body}")
        require(body["limits"] == {"tail_lines": 2, "max_bytes": 4096}, f"limits wrong: {body}")
        require(body["truncated"]["lines"] is True, f"line truncation missing: {body}")
        require(body["redaction"]["applied"] is True, f"redaction fact missing: {body}")
        for secret in ("super-secret-token", "plain-secret", "ghp_"):
            require(secret not in body["log"], f"secret leaked from log: {body}")
        calls = call_log.read_text().splitlines()
        require("--log-failed" in calls[-1], f"--failed did not request failed log: {calls[-1]}")

        byte_limited = run("logs", "48201933", "--tail", "4", "--max-bytes", "20",
                           "--repo", "owner/repo", "--json")
        require(byte_limited.returncode == 0, f"byte limit failed: {byte_limited.stdout} {byte_limited.stderr}")
        body = json.loads(byte_limited.stdout)
        require(body["truncated"]["bytes"] is True, f"byte truncation missing: {body}")
        require(len(body["log"].encode("utf-8")) <= 20, f"byte cap exceeded: {body}")
        calls = call_log.read_text().splitlines()
        require("--log" in calls[-1] and "--log-failed" not in calls[-1],
                f"ordinary logs used wrong GitHub query: {calls[-1]}")

        invalid = run("logs", "48201933", "--tail", "0", "--repo", "owner/repo", "--json")
        require(invalid.returncode == 2, f"invalid tail exit: {invalid.returncode} {invalid.stdout}")
        error = json.loads(invalid.stdout)
        require(error["success"] is False and "--tail must be between" in error["error"],
                f"invalid tail is not structured: {error}")

        missing = run("details", "--repo", "owner/repo", "--json")
        require(missing.returncode == 2 and "Run ID required" in missing.stdout,
                f"missing run id not explained: {missing.stdout} {missing.stderr}")

    print("ci trace tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
