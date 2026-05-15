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
    if "--review-requested" in args and "--owner" in args:
        emit([])
        sys.exit(0)
    if "--owner" in args:
        emit([{{
            "number": 9,
            "title": "PR 9",
            "state": "open",
            "url": "https://github.com/Versova-Intelligence-Division/vms.io/pull/9",
            "repository": {{"nameWithOwner": "Versova-Intelligence-Division/vms.io"}},
            "author": {{"login": "ctyrrell-versova"}},
            "isDraft": False,
            "updatedAt": "2026-04-29T12:00:00Z",
            "commentsCount": 2,
            "labels": [{{"name": "bug"}}],
        }}])
        sys.exit(0)
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
    number = args[2]
    repo = args[args.index("--repo") + 1] if "--repo" in args else "ovachiever/agent-do"
    if number == "9":
        emit({{
            "number": 9,
            "title": "PR 9",
            "state": "OPEN",
            "isDraft": False,
            "author": {{"login": "ctyrrell-versova"}},
            "baseRefName": "main",
            "headRefName": "fix/rls",
            "headRefOid": "cafe",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
            "reviewDecision": "",
            "changedFiles": 1,
            "additions": 99,
            "deletions": 0,
            "reviewRequests": [],
            "latestReviews": [],
            "files": [{{"path": "db/migrations/001.sql", "additions": 99, "deletions": 0}}],
            "statusCheckRollup": [],
            "createdAt": "2026-04-27T20:37:55Z",
            "updatedAt": "2026-04-29T12:00:00Z",
            "url": f"https://github.com/{{repo}}/pull/9",
        }})
        sys.exit(0)
    emit({{
        "number": int(number),
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
        "changedFiles": 5,
        "additions": 2029,
        "deletions": 201,
        "reviewRequests": [{{"__typename": "User", "login": "ovachiever"}}],
        "latestReviews": [{{"author": {{"login": "ovachiever"}}, "state": "CHANGES_REQUESTED", "submittedAt": "2026-04-29T12:01:00Z"}}],
        "files": [
            {{"path": "presentation/next.config.ts", "additions": 5, "deletions": 1}},
            {{"path": "presentation/sentry.client.config.ts", "additions": 15, "deletions": 0}},
            {{"path": "presentation/__tests__/sentry-config.test.ts", "additions": 50, "deletions": 0}},
            {{"path": "presentation/package.json", "additions": 1, "deletions": 0}},
            {{"path": "presentation/package-lock.json", "additions": 1958, "deletions": 200}},
        ],
        "statusCheckRollup": [{{"name": "test", "state": "SUCCESS", "conclusion": "SUCCESS"}}],
        "createdAt": "2026-04-27T20:37:55Z",
        "updatedAt": "2026-04-29T12:00:00Z",
        "url": f"https://github.com/{{repo}}/pull/{{number}}",
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
    print('''
diff --git a/presentation/next.config.ts b/presentation/next.config.ts
+  org: process.env.SENTRY_ORG,
+  project: process.env.SENTRY_PROJECT,
diff --git a/presentation/sentry.client.config.ts b/presentation/sentry.client.config.ts
+Sentry.init({{ tracesSampleRate: 1.0, enabled: !!dsn }});
diff --git a/presentation/__tests__/sentry-config.test.ts b/presentation/__tests__/sentry-config.test.ts
+import {{ describe, it, expect }} from 'vitest';
''')
elif args[:2] == ["pr", "review"]:
    print("reviewed")
elif args[:2] == ["pr", "merge"]:
    print("merged")
elif args[:2] == ["pr", "close"]:
    print("closed")
elif args[:2] == ["pr", "reopen"]:
    print("reopened")
elif args[:2] == ["pr", "checkout"]:
    print("checked out")
elif args[:2] == ["pr", "edit"]:
    print("edited")
elif args[:2] == ["pr", "update-branch"]:
    print("updated")
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
        require(pr_payload["pr"]["review_requests"] == ["ovachiever"], f"unexpected review request normalization: {pr_payload}")

        inbox = run([str(AGENT_DO), "gh", "inbox", "--json"], cwd=ROOT, env=env)
        require(inbox.returncode == 0, f"inbox failed: {inbox.stderr}")
        inbox_payload = json.loads(inbox.stdout)
        refs = {item["ref"]: item["reasons"] for item in inbox_payload["items"]}
        require("review_requested" in refs["ovachiever/agent-do#3"], f"missing review inbox reason: {inbox_payload}")
        require("authored_failed_checks" in refs["ovachiever/agent-do#4"], f"missing failed checks reason: {inbox_payload}")

        awaiting = run(
            [
                str(AGENT_DO),
                "gh",
                "awaiting",
                "--owner",
                "Versova-Intelligence-Division",
                "--author",
                "ctyrrell-versova",
                "--json",
            ],
            cwd=ROOT,
            env=env,
        )
        require(awaiting.returncode == 0, f"awaiting failed: {awaiting.stderr}")
        awaiting_payload = json.loads(awaiting.stdout)
        require(awaiting_payload["items"][0]["ref"] == "Versova-Intelligence-Division/vms.io#9", f"unexpected awaiting refs: {awaiting_payload}")
        require("not_reviewed_by_me" in awaiting_payload["items"][0]["reasons"], f"missing awaiting reason: {awaiting_payload}")

        awaiting_replies = run(
            [
                str(AGENT_DO),
                "gh",
                "awaiting",
                "--owner",
                "Versova-Intelligence-Division",
                "--author",
                "ctyrrell-versova",
                "--audit",
                "--replies",
            ],
            cwd=ROOT,
            env=env,
        )
        require(awaiting_replies.returncode == 0, f"awaiting replies failed: {awaiting_replies.stderr}")
        require("## Versova-Intelligence-Division/vms.io#9" in awaiting_replies.stdout, f"missing awaiting reply header: {awaiting_replies.stdout}")
        require("How to address:" in awaiting_replies.stdout, f"missing awaiting fix guidance: {awaiting_replies.stdout}")

        threads = run([str(AGENT_DO), "gh", "threads", "ovachiever/agent-do#3", "--json"], cwd=ROOT, env=env)
        require(threads.returncode == 0, f"threads failed: {threads.stderr}")
        threads_payload = json.loads(threads.stdout)
        require(threads_payload["count"] == 1, f"expected unresolved-only thread list: {threads_payload}")

        audit = run([str(AGENT_DO), "gh", "audit", "ovachiever/agent-do#3", "--json"], cwd=ROOT, env=env)
        require(audit.returncode == 0, f"audit failed: {audit.stderr}")
        audit_payload = json.loads(audit.stdout)
        titles = {finding["title"] for finding in audit_payload["findings"]}
        require(audit_payload["verdict"] == "request_changes", f"expected request_changes audit: {audit_payload}")
        require("Lockfile blast radius is large" in titles, f"missing lockfile finding: {audit_payload}")
        require("Production trace sampling appears too high" in titles, f"missing sampling finding: {audit_payload}")
        require("Source-map upload looks partially wired" in titles, f"missing source-map finding: {audit_payload}")
        require("Added Vitest test may not be runnable" in titles, f"missing test wiring finding: {audit_payload}")

        audit_reply = run([str(AGENT_DO), "gh", "audit", "ovachiever/agent-do#3", "--reply"], cwd=ROOT, env=env)
        require(audit_reply.returncode == 0, f"audit reply failed: {audit_reply.stderr}")
        require("Do not merge as-is." in audit_reply.stdout, f"missing review stance: {audit_reply.stdout}")
        require("How to address:" in audit_reply.stdout, f"missing fix guidance: {audit_reply.stdout}")

        approve = run([str(AGENT_DO), "gh", "approve", "ovachiever/agent-do#3", "--body", "LGTM"], cwd=ROOT, env=env)
        require(approve.returncode == 0, f"approve failed: {approve.stderr}")

        merge = run([str(AGENT_DO), "gh", "merge", "ovachiever/agent-do#3", "--squash", "--match-head-commit", "b352"], cwd=ROOT, env=env)
        require(merge.returncode == 0, f"merge failed: {merge.stderr}")

        close = run(
            [
                str(AGENT_DO),
                "gh",
                "close",
                "ovachiever/agent-do#4",
                "--delete-branch",
                "--comment",
                "Closing accidental PR",
            ],
            cwd=ROOT,
            env=env,
        )
        require(close.returncode == 0, f"close failed: {close.stderr}")

        reopen = run(
            [
                str(AGENT_DO),
                "gh",
                "reopen",
                "ovachiever/agent-do#4",
                "--comment",
                "Reopening after correction",
            ],
            cwd=ROOT,
            env=env,
        )
        require(reopen.returncode == 0, f"reopen failed: {reopen.stderr}")

        checkout = run(
            [
                str(AGENT_DO),
                "gh",
                "checkout",
                "ovachiever/agent-do#3",
                "--branch",
                "review/pr-3",
                "--force",
            ],
            cwd=ROOT,
            env=env,
        )
        require(checkout.returncode == 0, f"checkout failed: {checkout.stderr}")

        edit = run(
            [
                str(AGENT_DO),
                "gh",
                "edit",
                "ovachiever/agent-do#3",
                "--title",
                "Updated title",
                "--base",
                "main",
                "--add-label",
                "review-needed",
                "--add-reviewer",
                "@me",
            ],
            cwd=ROOT,
            env=env,
        )
        require(edit.returncode == 0, f"edit failed: {edit.stderr}")

        update_branch = run(
            [
                str(AGENT_DO),
                "gh",
                "update-branch",
                "ovachiever/agent-do#3",
                "--rebase",
            ],
            cwd=ROOT,
            env=env,
        )
        require(update_branch.returncode == 0, f"update-branch failed: {update_branch.stderr}")

        calls = [json.loads(line) for line in log_path.read_text().splitlines()]
        require(
            ["search", "prs", "--json", "number,title,state,url,repository,author,isDraft,updatedAt,commentsCount,labels", "--limit", "30", "--state", "open", "--author", "@me"] in calls,
            f"missing safe default prs scope: {calls}",
        )
        require(["pr", "review", "3", "--repo", "ovachiever/agent-do", "--approve", "--body", "LGTM"] in calls, f"missing approve call: {calls}")
        require(["pr", "merge", "3", "--repo", "ovachiever/agent-do", "--squash", "--match-head-commit", "b352"] in calls, f"missing merge call: {calls}")
        require(
            ["pr", "close", "4", "--repo", "ovachiever/agent-do", "--delete-branch", "--comment", "Closing accidental PR"] in calls,
            f"missing close call: {calls}",
        )
        require(
            ["pr", "reopen", "4", "--repo", "ovachiever/agent-do", "--comment", "Reopening after correction"] in calls,
            f"missing reopen call: {calls}",
        )
        require(
            ["pr", "checkout", "3", "--repo", "ovachiever/agent-do", "--branch", "review/pr-3", "--force"] in calls,
            f"missing checkout call: {calls}",
        )
        require(
            ["pr", "edit", "3", "--repo", "ovachiever/agent-do", "--title", "Updated title", "--base", "main", "--add-label", "review-needed", "--add-reviewer", "@me"] in calls,
            f"missing edit call: {calls}",
        )
        require(
            ["pr", "update-branch", "3", "--repo", "ovachiever/agent-do", "--rebase"] in calls,
            f"missing update-branch call: {calls}",
        )

    print("gh tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
