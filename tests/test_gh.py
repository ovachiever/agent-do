#!/usr/bin/env python3
"""Focused tests for agent-gh GitHub work-state commands."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_exec(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        log_path = tmp / "gh-calls.jsonl"

        make_exec(
            fake_bin / "gh",
            f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

log = Path({str(log_path)!r})
args = sys.argv[1:]
with log.open("a") as f:
    f.write(json.dumps(args) + "\\n")

def emit(payload):
    print(json.dumps(payload))

if args[:2] == ["api", "user"]:
    emit({{"login": "ovachiever", "id": 1, "name": "Erik", "html_url": "https://github.com/ovachiever"}})
elif args[:3] == ["api", "--paginate", "--slurp"]:
    emit([[{{"name": "agent-do", "full_name": "ovachiever/agent-do", "owner": {{"login": "ovachiever"}}, "private": False, "visibility": "public", "archived": False, "default_branch": "main", "html_url": "https://github.com/ovachiever/agent-do"}}]])
elif args[:2] == ["search", "prs"]:
    reason = "generic"
    if "--review-requested" in args:
        reason = "review"
    elif "--checks" in args:
        reason = "failed"
    elif "--review" in args:
        reason = "changes"
    elif "--author" in args:
        reason = "mine"
    number = {{"review": 3, "mine": 4, "failed": 4, "changes": 5}}.get(reason, 9)
    emit([{{
        "number": number,
        "title": f"PR {{number}}",
        "state": "open",
        "url": f"https://github.com/ovachiever/agent-do/pull/{{number}}",
        "repository": {{"nameWithOwner": "ovachiever/agent-do"}},
        "author": {{"login": "ctyrrell-versova"}},
        "isDraft": False,
        "updatedAt": "2026-04-29T12:00:00Z",
        "commentsCount": 2,
        "labels": [{{"name": "bug"}}],
    }}])
elif args[:2] == ["pr", "view"]:
    emit({{
        "number": 3,
        "title": "Escape JSON control chars",
        "state": "OPEN",
        "isDraft": False,
        "author": {{"login": "ctyrrell-versova"}},
        "baseRefName": "main",
        "headRefName": "feat/snapshot-control-char-escaping",
        "headRefOid": "b352",
        "mergeable": "CONFLICTING",
        "mergeStateStatus": "DIRTY",
        "reviewDecision": "CHANGES_REQUESTED",
        "changedFiles": 3,
        "additions": 29,
        "deletions": 1,
        "reviewRequests": [{{"requestedReviewer": {{"login": "ovachiever"}}}}],
        "latestReviews": [{{"author": {{"login": "ovachiever"}}, "state": "CHANGES_REQUESTED", "submittedAt": "2026-04-29T12:01:00Z"}}],
        "files": [{{"path": "lib/snapshot.sh", "additions": 5, "deletions": 1}}],
        "statusCheckRollup": [{{"name": "test", "state": "SUCCESS", "conclusion": "SUCCESS"}}],
        "createdAt": "2026-04-27T20:37:55Z",
        "updatedAt": "2026-04-29T12:00:00Z",
        "url": "https://github.com/ovachiever/agent-do/pull/3",
    }})
elif args[:2] == ["pr", "checks"]:
    emit([{{"name": "test", "state": "SUCCESS", "conclusion": "SUCCESS", "bucket": "pass", "link": "https://example.com", "description": ""}}])
elif args[:3] == ["api", "graphql", "-f"]:
    emit({{"data": {{"repository": {{"pullRequest": {{"reviewThreads": {{"nodes": [
        {{"id": "thread1", "isResolved": False, "path": "lib/snapshot.sh", "line": 34, "comments": {{"nodes": [
            {{"id": "comment1", "body": "escape all controls", "createdAt": "2026-04-29T12:00:00Z", "url": "https://github.com/x", "author": {{"login": "ovachiever"}}}}
        ]}}}},
        {{"id": "thread2", "isResolved": True, "path": "README.md", "line": 1, "comments": {{"nodes": []}}}}
    ]}}}}}}}}}})
elif args[:2] == ["pr", "diff"]:
    print("diff --git a/lib/snapshot.sh b/lib/snapshot.sh")
elif args[:2] == ["pr", "review"]:
    print("reviewed")
elif args[:2] == ["pr", "merge"]:
    print("merged")
elif args[:2] == ["pr", "ready"]:
    print("ready")
else:
    print("unexpected gh args: " + " ".join(args), file=sys.stderr)
    sys.exit(2)
""",
        )

        env = dict(os.environ)
        env["AGENT_DO_HOME"] = str(fake_home)
        env["PATH"] = f"{fake_bin}:{env['PATH']}"

        whoami = run([str(AGENT_DO), "gh", "whoami", "--json"], cwd=ROOT, env=env)
        require(whoami.returncode == 0, f"whoami failed: {whoami.stderr}")
        require(json.loads(whoami.stdout)["user"]["login"] == "ovachiever", f"unexpected whoami: {whoami.stdout}")

        repos = run([str(AGENT_DO), "gh", "repos", "sync", "--json"], cwd=ROOT, env=env)
        require(repos.returncode == 0, f"repos sync failed: {repos.stderr}")
        repos_payload = json.loads(repos.stdout)
        require(repos_payload["repos"][0]["full_name"] == "ovachiever/agent-do", f"unexpected repos: {repos_payload}")

        prs = run([str(AGENT_DO), "gh", "prs", "--review-requested", "--json"], cwd=ROOT, env=env)
        require(prs.returncode == 0, f"prs failed: {prs.stderr}")
        prs_payload = json.loads(prs.stdout)
        require(prs_payload["prs"][0]["ref"] == "ovachiever/agent-do#3", f"unexpected prs: {prs_payload}")

        my_prs = run([str(AGENT_DO), "gh", "prs", "--json"], cwd=ROOT, env=env)
        require(my_prs.returncode == 0, f"default prs failed: {my_prs.stderr}")
        my_prs_payload = json.loads(my_prs.stdout)
        require(my_prs_payload["prs"][0]["ref"] == "ovachiever/agent-do#4", f"unexpected default prs: {my_prs_payload}")

        pr = run([str(AGENT_DO), "gh", "pr", "ovachiever/agent-do#3", "--json"], cwd=ROOT, env=env)
        require(pr.returncode == 0, f"pr failed: {pr.stderr}")
        pr_payload = json.loads(pr.stdout)
        require(pr_payload["pr"]["merge_state"] == "DIRTY", f"unexpected pr detail: {pr_payload}")

        inbox = run([str(AGENT_DO), "gh", "inbox", "--json"], cwd=ROOT, env=env)
        require(inbox.returncode == 0, f"inbox failed: {inbox.stderr}")
        inbox_payload = json.loads(inbox.stdout)
        refs = {item["ref"]: item["reasons"] for item in inbox_payload["items"]}
        require("review_requested" in refs["ovachiever/agent-do#3"], f"missing review inbox reason: {inbox_payload}")
        require("authored_failed_checks" in refs["ovachiever/agent-do#4"], f"missing failed checks reason: {inbox_payload}")

        threads = run([str(AGENT_DO), "gh", "threads", "ovachiever/agent-do#3", "--json"], cwd=ROOT, env=env)
        require(threads.returncode == 0, f"threads failed: {threads.stderr}")
        threads_payload = json.loads(threads.stdout)
        require(threads_payload["count"] == 1, f"expected unresolved-only thread list: {threads_payload}")

        approve = run([str(AGENT_DO), "gh", "approve", "ovachiever/agent-do#3", "--body", "LGTM"], cwd=ROOT, env=env)
        require(approve.returncode == 0, f"approve failed: {approve.stderr}")

        merge = run([str(AGENT_DO), "gh", "merge", "ovachiever/agent-do#3", "--squash", "--match-head-commit", "b352"], cwd=ROOT, env=env)
        require(merge.returncode == 0, f"merge failed: {merge.stderr}")

        calls = [json.loads(line) for line in log_path.read_text().splitlines()]
        require(
            ["search", "prs", "--json", "number,title,state,url,repository,author,isDraft,updatedAt,commentsCount,labels", "--limit", "30", "--state", "open", "--author", "@me"] in calls,
            f"missing safe default prs scope: {calls}",
        )
        require(["pr", "review", "3", "--repo", "ovachiever/agent-do", "--approve", "--body", "LGTM"] in calls, f"missing approve call: {calls}")
        require(["pr", "merge", "3", "--repo", "ovachiever/agent-do", "--squash", "--match-head-commit", "b352"] in calls, f"missing merge call: {calls}")

    print("gh tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
