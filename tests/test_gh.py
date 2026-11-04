#!/usr/bin/env python3
"""Focused tests for agent-gh GitHub work-state commands."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_agent_gh():
    """Import the extensionless agent-gh tool as a module for unit tests."""
    loader = importlib.machinery.SourceFileLoader("agent_gh", str(ROOT / "tools" / "agent-gh"))
    spec = importlib.util.spec_from_loader("agent_gh", loader)
    module = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve cls.__module__.
    sys.modules["agent_gh"] = module
    loader.exec_module(module)
    return module


def test_classify_risk() -> None:
    gh = load_agent_gh()

    crit = gh.classify_risk(["apps/web/middleware.ts"])
    require(crit["tier"] == "critical", f"middleware should be critical: {crit}")

    sql = gh.classify_risk(["packages/database/migrations/0001_init.sql"])
    require(sql["tier"] == "critical", f"migration should be critical: {sql}")

    elevated = gh.classify_risk(["render.yaml"])
    require(elevated["tier"] == "elevated", f"render.yaml should be elevated: {elevated}")

    lockfile = gh.classify_risk(["apps/web/package-lock.json"])
    require(lockfile["tier"] == "elevated", f"lockfile should be elevated: {lockfile}")

    standard = gh.classify_risk(["README.md", "apps/web/components/Button.tsx"])
    require(standard["tier"] == "standard", f"docs/components should be standard: {standard}")

    mixed = gh.classify_risk(["apps/web/middleware.ts", "render.yaml", "README.md"])
    require(mixed["tier"] == "critical", f"mixed set tier should be highest: {mixed}")
    require(mixed["counts"] == {"critical": 1, "elevated": 1, "standard": 1},
            f"mixed counts wrong: {mixed}")
    require([s["path"] for s in mixed["signals"]][0] == "apps/web/middleware.ts",
            f"signals should be critical-first: {mixed}")


def test_merge_gate() -> None:
    gh = load_agent_gh()
    ref = gh.parse_pr_ref("owner/repo#1")

    def patch(*, detail, checks, threads):
        gh.pr_detail = lambda r: detail
        gh.pr_checks = lambda r: checks
        gh.pr_threads = lambda r: threads

    clean_detail = {"merge_state": "CLEAN", "review_decision": "APPROVED",
                    "files": [{"path": "src/app.ts"}]}

    # Clean PR — allowed.
    patch(detail=clean_detail, checks=[], threads=[])
    gate = gh.merge_gate(ref)
    require(gate["allowed"], f"clean PR should be allowed: {gate}")

    # Failing check — blocked.
    patch(detail=clean_detail, checks=[{"name": "build", "bucket": "fail"}], threads=[])
    gate = gh.merge_gate(ref)
    require(not gate["allowed"] and any(b["gate"] == "checks" for b in gate["blocks"]),
            f"failing check should block: {gate}")

    # Unresolved thread — blocked.
    patch(detail=clean_detail, checks=[], threads=[{"id": "t1"}])
    gate = gh.merge_gate(ref)
    require(any(b["gate"] == "threads" for b in gate["blocks"]),
            f"unresolved thread should block: {gate}")

    # Dirty merge state — blocked.
    patch(detail={**clean_detail, "merge_state": "DIRTY"}, checks=[], threads=[])
    gate = gh.merge_gate(ref)
    require(any(b["gate"] == "mergeable" for b in gate["blocks"]),
            f"dirty merge state should block: {gate}")

    # Changes requested — blocked.
    patch(detail={**clean_detail, "review_decision": "CHANGES_REQUESTED"}, checks=[], threads=[])
    gate = gh.merge_gate(ref)
    require(any(b["gate"] == "approval" for b in gate["blocks"]),
            f"changes requested should block: {gate}")

    # Branch requires a review and none is recorded — blocked.
    patch(detail={**clean_detail, "review_decision": "REVIEW_REQUIRED"}, checks=[], threads=[])
    gate = gh.merge_gate(ref)
    require(any(b["gate"] == "approval" for b in gate["blocks"]),
            f"required-but-missing review should block: {gate}")

    # Branch requires no review (GitHub reports reviewDecision null) — the
    # repo's own policy allows the merge; the gate notes it, never blocks.
    for empty in (None, ""):
        patch(detail={**clean_detail, "review_decision": empty}, checks=[], threads=[])
        gate = gh.merge_gate(ref)
        require(gate["allowed"], f"no-review-required repo should not block (decision={empty!r}): {gate}")
        require(any(n["gate"] == "approval" for n in gate["notes"]),
                f"unreviewed merge should be noted: {gate}")

    # No decision published, but a latest review requests changes — blocked.
    patch(detail={**clean_detail, "review_decision": None,
                  "latest_reviews": [{"author": "grok", "state": "CHANGES_REQUESTED"}]}, checks=[], threads=[])
    gate = gh.merge_gate(ref)
    require(any(b["gate"] == "approval" and "grok" in b["reason"] for b in gate["blocks"]),
            f"a changes request must block even when the decision is null: {gate}")

    # No decision, an approving review — allowed, and the note names the approver.
    patch(detail={**clean_detail, "review_decision": "",
                  "latest_reviews": [{"author": "grok", "state": "APPROVED"}]}, checks=[], threads=[])
    gate = gh.merge_gate(ref)
    require(gate["allowed"] and "approved by grok" in gate["notes"][0]["reason"], f"approver note: {gate}")

    # Anything the gate does not recognise blocks (fail closed).
    patch(detail={**clean_detail, "review_decision": "SOMETHING_NEW"}, checks=[], threads=[])
    gate = gh.merge_gate(ref)
    require(not gate["allowed"], f"unknown decision must block: {gate}")

    # Critical-risk paths — warning, not block.
    patch(detail={**clean_detail, "files": [{"path": "apps/web/middleware.ts"}]},
          checks=[], threads=[])
    gate = gh.merge_gate(ref)
    require(gate["allowed"], f"critical risk alone should not block: {gate}")
    require(any(w["gate"] == "risk" for w in gate["warnings"]),
            f"critical risk should warn: {gate}")


def test_classify_maintainer_state() -> None:
    gh = load_agent_gh()
    viewer = "ovachiever"

    def review(state: str, commit_id: str, submitted_at: str = "2026-04-28T10:00:00Z", login: str = viewer) -> dict:
        return {"user": {"login": login}, "state": state, "commit_id": commit_id, "submitted_at": submitted_at}

    classify = gh.classify_maintainer_state
    require(classify([], viewer, "head") == "maintainer_unreviewed",
            "no reviews should classify as unreviewed")
    require(classify([review("APPROVED", "head", login="someone")], viewer, "head") == "maintainer_unreviewed",
            "other users' reviews must not count")
    require(classify([review("PENDING", "head")], viewer, "head") == "maintainer_unreviewed",
            "pending drafts are not submitted reviews")
    require(classify([review("APPROVED", "old")], viewer, "head") == "maintainer_review_stale",
            "review behind head is stale")
    require(classify([review("CHANGES_REQUESTED", "old")], viewer, "head") == "maintainer_review_stale",
            "staleness must be checked before state")
    require(classify([review("APPROVED", "head")], viewer, "head") == "maintainer_approved_unmerged",
            "approved at head is approved_unmerged")
    require(classify([review("CHANGES_REQUESTED", "head")], viewer, "head") is None,
            "changes requested at head waits on the author")
    require(classify([review("COMMENTED", "head")], viewer, "head") == "maintainer_unreviewed",
            "commented at head is not a decision")
    latest_wins = [review("APPROVED", "old", "2026-04-01T10:00:00Z"),
                   review("CHANGES_REQUESTED", "head", "2026-04-28T10:00:00Z")]
    require(classify(latest_wins, viewer, "head") is None,
            "latest submitted review must win")


def test_portfolio_patterns() -> None:
    gh = load_agent_gh()
    for good in ("acme/widgets", "acme/*", "a1/b.c-d_e"):
        require(gh.validate_portfolio_pattern(good) == good, f"{good!r} should validate")
    for bad in ("acme", "acme/", "/widgets", "acme/*x", "*/widgets", "acme/widgets/extra", "-acme/x", ""):
        try:
            gh.validate_portfolio_pattern(bad)
            raise AssertionError(f"{bad!r} should be rejected")
        except gh.GhError:
            pass


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

        def rest_repo(name: str, *, permissions: dict, open_issues: int, archived: bool = False) -> dict:
            return {
                "name": name,
                "full_name": f"ovachiever/{name}",
                "owner": {"login": "ovachiever"},
                "private": False,
                "visibility": "public",
                "archived": archived,
                "default_branch": "main",
                "html_url": f"https://github.com/ovachiever/{name}",
                "permissions": permissions,
                "open_issues_count": open_issues,
            }

        admin = {"admin": True, "maintain": False, "push": True, "triage": True, "pull": True}
        push_only = {"admin": False, "maintain": False, "push": True, "triage": True, "pull": True}
        read_only = {"admin": False, "maintain": False, "push": False, "triage": False, "pull": True}
        sweep_repos = [
            rest_repo("agent-do", permissions=admin, open_issues=5),
            rest_repo("bots", permissions=push_only, open_issues=1),
            rest_repo("broken", permissions=push_only, open_issues=2),
            rest_repo("empty", permissions=push_only, open_issues=0),
            rest_repo("readonly", permissions=read_only, open_issues=3),
            rest_repo("attic", permissions=admin, open_issues=4, archived=True),
        ]

        def rest_pull(repo: str, number: int, author: str, head_sha: str) -> dict:
            return {
                "number": number,
                "title": f"PR {number}",
                "state": "open",
                "draft": False,
                "user": {"login": author},
                "updated_at": "2026-04-29T12:00:00Z",
                "html_url": f"https://github.com/ovachiever/{repo}/pull/{number}",
                "head": {"sha": head_sha},
                "labels": [],
            }

        sweep_pulls = {
            "ovachiever/agent-do": [
                rest_pull("agent-do", 3, "ctyrrell-versova", "head3"),
                rest_pull("agent-do", 4, "ovachiever", "head4"),
                rest_pull("agent-do", 6, "christyrrell", "head6"),
                rest_pull("agent-do", 7, "ctyrrell-versova", "head7"),
                rest_pull("agent-do", 8, "ctyrrell-versova", "head8"),
            ],
            "ovachiever/bots": [rest_pull("bots", 2, "dependabot[bot]", "headb2")],
            "acme/widgets": [
                rest_pull("widgets", 1, "someone-else", "headw1"),
                rest_pull("widgets", 2, "someone-else", "headw2"),
            ],
            "solouser/lab": [rest_pull("lab", 9, "ovachiever", "headl9")],
        }

        portfolio_org_repos = {
            "acme": [
                {"full_name": "acme/widgets", "archived": False, "open_issues_count": 3},
                {"full_name": "acme/quiet", "archived": False, "open_issues_count": 0},
                {"full_name": "acme/attic", "archived": True, "open_issues_count": 9},
            ],
        }
        portfolio_user_repos = {
            "solouser": [{"full_name": "solouser/lab", "archived": False, "open_issues_count": 1}],
        }

        def viewer_review(state: str, commit_id: str, submitted_at: str) -> dict:
            return {"user": {"login": "ovachiever"}, "state": state, "commit_id": commit_id, "submitted_at": submitted_at}

        sweep_reviews = {
            "ovachiever/agent-do#3": [],
            "ovachiever/agent-do#6": [viewer_review("APPROVED", "head6", "2026-04-28T10:00:00Z")],
            "ovachiever/agent-do#7": [viewer_review("CHANGES_REQUESTED", "old7", "2026-04-28T10:00:00Z")],
            "ovachiever/agent-do#8": [
                viewer_review("APPROVED", "old8", "2026-04-01T10:00:00Z"),
                viewer_review("CHANGES_REQUESTED", "head8", "2026-04-28T10:00:00Z"),
            ],
            "ovachiever/bots#2": [],
            "acme/widgets#1": [],
            "acme/widgets#2": [viewer_review("CHANGES_REQUESTED", "headw2", "2026-04-28T10:00:00Z")],
        }

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
    path = args[3]
    repos_fixture = json.loads({json.dumps(sweep_repos)!r})
    pulls_fixture = json.loads({json.dumps(sweep_pulls)!r})
    reviews_fixture = json.loads({json.dumps(sweep_reviews)!r})
    if "/user/repos" in path:
        emit([repos_fixture])
    elif "/reviews" in path:
        scoped = path.split("repos/", 1)[1].split("/reviews", 1)[0]
        owner_repo, _, number = scoped.partition("/pulls/")
        emit([reviews_fixture.get(owner_repo + "#" + number, [])])
    elif "/pulls?" in path:
        owner_repo = path.split("repos/", 1)[1].split("/pulls", 1)[0]
        if owner_repo == "ovachiever/broken":
            print("HTTP 500: boom", file=sys.stderr)
            sys.exit(1)
        if owner_repo == "ghost/hidden":
            print("HTTP 404: Not Found", file=sys.stderr)
            sys.exit(1)
        emit([pulls_fixture.get(owner_repo, [])])
    elif path.startswith("orgs/") and "/repos" in path:
        owner = path.split("orgs/", 1)[1].split("/repos", 1)[0]
        org_fixture = json.loads({json.dumps(portfolio_org_repos)!r})
        if owner not in org_fixture:
            print("HTTP 404: Not Found (org)", file=sys.stderr)
            sys.exit(1)
        emit([org_fixture[owner]])
    elif path.startswith("users/") and "/repos" in path:
        owner = path.split("users/", 1)[1].split("/repos", 1)[0]
        user_fixture = json.loads({json.dumps(portfolio_user_repos)!r})
        if owner not in user_fixture:
            print("HTTP 404: Not Found (user)", file=sys.stderr)
            sys.exit(1)
        emit([user_fixture[owner]])
    else:
        print("unexpected api path: " + path, file=sys.stderr)
        sys.exit(2)
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

        # Maintainer sweep (default): role-derived reasons merge with ceremony rows.
        require("maintainer_unreviewed" in refs["ovachiever/agent-do#3"],
                f"sweep should mark unreviewed third-party PR: {inbox_payload}")
        require("maintainer_approved_unmerged" in refs["ovachiever/agent-do#6"],
                f"approved-at-head PR should read approved_unmerged: {inbox_payload}")
        require("maintainer_review_stale" in refs["ovachiever/agent-do#7"],
                f"review behind head should read stale: {inbox_payload}")
        require("ovachiever/agent-do#8" not in refs,
                f"changes-requested-at-head PR must be excluded from rows: {inbox_payload}")
        require(refs.get("ovachiever/bots#2") == ["maintainer_unreviewed", "bot_author"],
                f"bot PR should carry bot_author tag: {inbox_payload}")
        sweep = inbox_payload["sweep"]
        require(sweep["repos_swept"] == 3, f"agent-do + bots + prefiltered empty should be swept: {sweep}")
        require(sweep["prs_classified"] == 5, f"five third-party open PRs should classify: {sweep}")
        require(sweep["waiting_on_author"] == 1, f"PR 8 waits on its author: {sweep}")
        require(len(sweep["unswept"]) == 1 and sweep["unswept"][0]["repo"] == "ovachiever/broken",
                f"failed repo must land in unswept: {sweep}")

        calls_so_far = [" ".join(json.loads(line)) for line in log_path.read_text().splitlines()]
        for skipped in ("empty", "readonly", "attic"):
            require(not any(f"ovachiever/{skipped}/pulls" in call for call in calls_so_far),
                    f"{skipped} must not be swept: {calls_so_far}")

        inbox_table = run([str(AGENT_DO), "gh", "inbox"], cwd=ROOT, env=env)
        require(inbox_table.returncode == 0, f"inbox table failed: {inbox_table.stderr}")
        require("maintainer sweep: 3 repos, 5 PRs; 1 waiting on author; 1 unswept" in inbox_table.stdout,
                f"missing sweep footer: {inbox_table.stdout}")
        require("unswept: ovachiever/broken" in inbox_table.stdout,
                f"unswept repos must be listed loudly: {inbox_table.stdout}")

        # A hit --limit cap is loud, never silent.
        capped = run([str(AGENT_DO), "gh", "inbox", "--limit", "2", "--json"], cwd=ROOT, env=env)
        require(capped.returncode == 0, f"capped inbox failed: {capped.stderr}")
        capped_payload = json.loads(capped.stdout)
        require(capped_payload["count"] == 2 and capped_payload["total"] == 6,
                f"capped JSON must report the uncapped total: {capped_payload['count']}/{capped_payload.get('total')}")
        capped_table = run([str(AGENT_DO), "gh", "inbox", "--limit", "2"], cwd=ROOT, env=env)
        require("showing 2 of 6 items; raise --limit" in capped_table.stdout,
                f"capped table must announce truncation: {capped_table.stdout}")

        # --ceremony-only: no sweep calls, byte-compatible JSON payload, loud notice.
        before_ceremony = len(log_path.read_text().splitlines())
        ceremony = run([str(AGENT_DO), "gh", "inbox", "--ceremony-only", "--json"], cwd=ROOT, env=env)
        require(ceremony.returncode == 0, f"ceremony-only inbox failed: {ceremony.stderr}")
        ceremony_payload = json.loads(ceremony.stdout)
        require(set(ceremony_payload) == {"count", "items"},
                f"ceremony-only JSON must not grow keys: {sorted(ceremony_payload)}")
        require("ceremony-only" in ceremony.stderr, f"missing ceremony-only notice: {ceremony.stderr}")
        ceremony_calls = [" ".join(json.loads(line)) for line in log_path.read_text().splitlines()[before_ceremony:]]
        require(not any("pulls?state=open" in call or "/user/repos" in call for call in ceremony_calls),
                f"ceremony-only must not sweep: {ceremony_calls}")

        ceremony_table = run([str(AGENT_DO), "gh", "inbox", "--ceremony-only"], cwd=ROOT, env=env)
        require(ceremony_table.returncode == 0, f"ceremony-only table failed: {ceremony_table.stderr}")
        require("ceremony-only view" in ceremony_table.stdout, f"missing table notice: {ceremony_table.stdout}")
        require("maintainer sweep:" not in ceremony_table.stdout,
                f"ceremony-only must not print sweep footer: {ceremony_table.stdout}")

        # An old-shape repos cache (no permissions) refreshes compatibly.
        cache_path = fake_home / "gh" / "repos.json"
        cache_path.write_text(json.dumps({"synced_at": "2026-01-01T00:00:00Z", "count": 1,
                                          "repos": [{"full_name": "ovachiever/agent-do"}]}))
        before_refresh = len(log_path.read_text().splitlines())
        refreshed = run([str(AGENT_DO), "gh", "inbox", "--json"], cwd=ROOT, env=env)
        require(refreshed.returncode == 0, f"inbox with old-shape cache failed: {refreshed.stderr}")
        refresh_calls = [" ".join(json.loads(line)) for line in log_path.read_text().splitlines()[before_refresh:]]
        require(any("/user/repos" in call for call in refresh_calls),
                f"permission-less cache should trigger a refresh: {refresh_calls}")
        cached = json.loads(cache_path.read_text())
        require(all("permissions" in repo for repo in cached["repos"]),
                f"refreshed cache must carry permissions: {cached['repos'][:2]}")

        # ── Declared portfolio: CRUD ───────────────────────────────────
        pf_empty = run([str(AGENT_DO), "gh", "portfolio", "list", "--json"], cwd=ROOT, env=env)
        require(pf_empty.returncode == 0, f"portfolio list failed: {pf_empty.stderr}")
        require(json.loads(pf_empty.stdout)["patterns"] == [], f"portfolio should start empty: {pf_empty.stdout}")

        for pattern in ("acme/*", "solouser/*", "ovachiever/agent-do", "ghost/hidden", "ovachiever/solo"):
            added = run([str(AGENT_DO), "gh", "portfolio", "add", pattern], cwd=ROOT, env=env)
            require(added.returncode == 0, f"portfolio add {pattern} failed: {added.stderr}")

        bad = run([str(AGENT_DO), "gh", "portfolio", "add", "not-a-pattern"], cwd=ROOT, env=env)
        require(bad.returncode == 1 and "Invalid portfolio pattern" in bad.stderr,
                f"invalid pattern must be rejected: rc={bad.returncode} {bad.stderr}")
        bad_wild = run([str(AGENT_DO), "gh", "portfolio", "add", "acme/*x"], cwd=ROOT, env=env)
        require(bad_wild.returncode == 1, f"partial wildcard must be rejected: {bad_wild.stdout}")

        removed = run([str(AGENT_DO), "gh", "portfolio", "remove", "ovachiever/solo"], cwd=ROOT, env=env)
        require(removed.returncode == 0, f"portfolio remove failed: {removed.stderr}")
        missing_rm = run([str(AGENT_DO), "gh", "portfolio", "remove", "ovachiever/solo"], cwd=ROOT, env=env)
        require(missing_rm.returncode == 1, f"removing absent pattern must fail: {missing_rm.stdout}")

        pf_list = run([str(AGENT_DO), "gh", "portfolio", "list", "--json"], cwd=ROOT, env=env)
        pf_payload = json.loads(pf_list.stdout)
        require(pf_payload["patterns"] == ["acme/*", "ghost/hidden", "ovachiever/agent-do", "solouser/*"],
                f"unexpected portfolio state: {pf_payload}")
        require((fake_home / "gh" / "portfolio.yaml").exists(), "portfolio file missing")
        require(not (fake_home / "gh" / "portfolio.yaml.tmp").exists(), "atomic temp file left behind")

        # ── Declared portfolio: sweep ──────────────────────────────────
        pf_inbox = run([str(AGENT_DO), "gh", "inbox", "--json"], cwd=ROOT, env=env)
        require(pf_inbox.returncode == 0, f"portfolio inbox failed: {pf_inbox.stderr}")
        pf_inbox_payload = json.loads(pf_inbox.stdout)
        pf_refs = {item["ref"]: item["reasons"] for item in pf_inbox_payload["items"]}
        require(pf_refs.get("acme/widgets#1") == ["portfolio_unreviewed"],
                f"wildcard-expanded repo should carry portfolio_unreviewed: {pf_refs}")
        require("acme/widgets#2" not in pf_refs,
                f"portfolio changes-requested-at-head must be excluded from rows: {pf_refs}")
        require("maintainer_unreviewed" in pf_refs["ovachiever/agent-do#3"]
                and not any(reason.startswith("portfolio_") for reason in pf_refs["ovachiever/agent-do#3"]),
                f"role must win dedupe with no portfolio_* dupes: {pf_refs['ovachiever/agent-do#3']}")
        pf_sweep = pf_inbox_payload["sweep"]["portfolio"]
        require(pf_sweep == {"patterns": 4, "repos_swept": 3, "prs_classified": 2, "waiting_on_author": 1},
                f"unexpected portfolio sweep stats: {pf_sweep}")
        unswept_reasons = {entry["repo"]: entry["reason"] for entry in pf_inbox_payload["sweep"]["unswept"]}
        require(unswept_reasons.get("ghost/hidden") == "no access",
                f"unreadable portfolio repo must report no access: {unswept_reasons}")
        require("ovachiever/broken" in unswept_reasons,
                f"role unswept must survive alongside portfolio unswept: {unswept_reasons}")

        pf_table = run([str(AGENT_DO), "gh", "inbox"], cwd=ROOT, env=env)
        require("maintainer sweep: 3 repos, 5 PRs; 1 waiting on author; 2 unswept" in pf_table.stdout,
                f"maintainer footer should count portfolio unswept: {pf_table.stdout}")
        require("portfolio sweep: 4 patterns, 3 repos, 2 PRs; 1 waiting on author" in pf_table.stdout,
                f"missing portfolio footer: {pf_table.stdout}")
        require("unswept: ghost/hidden: no access" in pf_table.stdout,
                f"no-access repo must be listed loudly: {pf_table.stdout}")

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

        # PR 3 in the mock is DIRTY + CHANGES_REQUESTED with an unresolved
        # thread — the merge gate must block it. --force reaches the merge call.
        merge = run([str(AGENT_DO), "gh", "merge", "ovachiever/agent-do#3", "--squash", "--match-head-commit", "b352", "--force"], cwd=ROOT, env=env)
        require(merge.returncode == 0, f"forced merge failed: {merge.stderr}")

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

        # ── Review doctrine + merge gate (subprocess) ──────────────────

        doctrine = run([str(AGENT_DO), "gh", "doctrine"], cwd=ROOT, env=env)
        require(doctrine.returncode == 0, f"doctrine failed: {doctrine.stderr}")
        require("Pull Request Review Doctrine" in doctrine.stdout,
                f"doctrine missing header: {doctrine.stdout[:200]}")

        review = run([str(AGENT_DO), "gh", "review", "9", "--json"], cwd=ROOT, env=env)
        require(review.returncode == 0, f"review failed: {review.stderr}")
        review_payload = json.loads(review.stdout)
        require("risk" in review_payload and "doctrine" in review_payload,
                f"review --json missing risk/doctrine keys: {list(review_payload)}")
        require(review_payload["risk"]["tier"] == "critical",
                f"PR 9 touches a .sql migration — risk should be critical: {review_payload['risk']}")

        # PR 9 has reviewDecision="" (its branch requires no review) and
        # touches a critical-tier path — merge must stop on the unconfirmed
        # risk warning, and the missing review is a note, not a block.
        merge_blocked = run([str(AGENT_DO), "gh", "merge", "9", "--json"], cwd=ROOT, env=env)
        require(merge_blocked.returncode == 2,
                f"merge with unconfirmed critical risk should exit 2: rc={merge_blocked.returncode}")
        gate_payload = json.loads(merge_blocked.stdout)
        require(any(w["gate"] == "risk" for w in gate_payload["warnings"]),
                f"merge gate should hold on the risk warning: {gate_payload}")
        require(not any(b["gate"] == "approval" for b in gate_payload["blocks"]),
                f"no-review-required PR must not block on approval: {gate_payload}")
        require(any(n["gate"] == "approval" for n in gate_payload.get("notes", [])),
                f"the unreviewed state should be noted: {gate_payload}")

        # --force bypasses the block and reaches the gh merge call.
        merge_forced = run([str(AGENT_DO), "gh", "merge", "9", "--force"], cwd=ROOT, env=env)
        require(merge_forced.returncode == 0, f"forced merge failed: {merge_forced.stderr}")
        require("bypassing merge gates" in merge_forced.stderr,
                f"--force should announce the bypass: {merge_forced.stderr}")

    test_classify_risk()
    test_merge_gate()
    test_classify_maintainer_state()
    test_portfolio_patterns()
    test_graphql_inbox()
    test_next_action_mapping()
    test_stage_fixture()

    print("gh tests passed")
    return 0


def test_stage_fixture() -> None:
    """The pinned live capture (2026-08-13) carries the stage contract and
    at least one row in mapping states 1 (Draft), 5 (Merge), 6 (Review),
    and 7 (Awaiting review) — the work-order verification set."""
    gh = load_agent_gh()
    fixture = json.loads((ROOT / "tests" / "fixtures" / "gh-inbox-stage-1.json").read_text())
    require(fixture["sweep"]["stage_contract"] == 1, "pinned fixture must carry stage_contract 1")
    verbs = {(item.get("next_action") or {}).get("verb") for item in fixture["items"]}
    for required in ("Draft", "Merge", "Review", "Awaiting review"):
        require(required in verbs, f"pinned fixture missing state '{required}': {sorted(v for v in verbs if v)}")
    for item in fixture["items"]:
        for key in ("review_decision", "merge_state", "checks", "review_requests", "next_action"):
            require(key in item, f"fixture row {item['ref']} missing stage key {key}")

    # Derived-reason parity: the two searched-no-more ceremony reasons come
    # from stage fields.
    entry = {"reasons": ["authored_open"], "checks": {"failed": 1, "total": 2, "passed": 1, "pending": 0},
             "review_decision": "CHANGES_REQUESTED"}
    gh.derive_authored_reasons(entry)
    require("authored_failed_checks" in entry["reasons"] and "authored_changes_requested" in entry["reasons"],
            f"derived reasons drifted: {entry['reasons']}")
    untouched = {"reasons": ["review_requested"], "checks": {"failed": 3, "total": 3, "passed": 0, "pending": 0}}
    gh.derive_authored_reasons(untouched)
    require(untouched["reasons"] == ["review_requested"],
            "derivation must only extend authored rows")


def test_next_action_mapping() -> None:
    gh = load_agent_gh()
    base = {"number": 9, "author": "other", "draft": False, "merge_state": None,
            "review_decision": None, "checks": None, "reasons": [], "review_requests": None}

    def item(**kw):
        merged = dict(base)
        merged.update(kw)
        return merged

    # Rule 1, and the draft+approved collision stays Draft.
    na = gh.next_action_for(item(draft=True, review_decision="APPROVED", merge_state="CLEAN", author="me"), "me")
    require(na["verb"] == "Draft" and na["yours"] is False and na["command"] is None,
            f"draft+approved must stay Draft: {na}")
    # Rule 2, and the DIRTY+approved collision stays Resolve conflicts.
    na = gh.next_action_for(item(author="me", merge_state="DIRTY", review_decision="APPROVED"), "me")
    require(na["verb"] == "Resolve conflicts" and na["yours"] is True,
            f"DIRTY+approved must stay Resolve conflicts: {na}")
    na = gh.next_action_for(item(merge_state="DIRTY"), "me")
    require(na["verb"] == "Resolve conflicts" and na["yours"] is False,
            f"a stranger's conflicts are not your move: {na}")
    # Rule 3.
    na = gh.next_action_for(item(author="me", review_decision="CHANGES_REQUESTED"), "me")
    require(na["verb"] == "Address review" and na["command"] == "agent-do gh pr 9",
            f"changes-requested mapping drifted: {na}")
    # Rule 4.
    na = gh.next_action_for(item(author="me", checks={"passed": 1, "failed": 2, "pending": 0, "total": 3}), "me")
    require(na["verb"] == "Fix checks" and na["detail"] == "2 of 3 failing"
            and na["command"] == "agent-do gh checks 9", f"failed-checks mapping drifted: {na}")
    # Rule 5.
    na = gh.next_action_for(item(author="me", review_decision="APPROVED", merge_state="CLEAN"), "me")
    require(na["verb"] == "Merge" and na["yours"] is True and na["command"] == "agent-do gh merge 9",
            f"merge mapping drifted: {na}")
    # Rule 6.
    na = gh.next_action_for(item(reasons=["review_requested"]), "me")
    require(na["verb"] == "Review" and na["yours"] is True and na["command"] == "agent-do gh pr 9",
            f"review-requested mapping drifted: {na}")
    # Rule 7, both details.
    na = gh.next_action_for(item(author="me"), "me")
    require(na["verb"] == "Awaiting review" and na["detail"] == "no review yet" and na["yours"] is False,
            f"awaiting-review mapping drifted: {na}")
    na = gh.next_action_for(item(author="me", review_requests=2), "me")
    require(na["detail"] == "2 reviewer(s) pending", f"pending-reviewer detail drifted: {na}")
    # Rule 8.
    require(gh.next_action_for(item(reasons=["maintainer_unreviewed"]), "me") is None,
            "not-authored without review_requested must map to null")

    # Rollup bucketing: counted outcomes, never invented; no rollup -> null.
    node = {"commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "FAILURE", "contexts": {
        "totalCount": 4, "nodes": [
            {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"},
            {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"},
            {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": None},
            {"__typename": "StatusContext", "state": "SUCCESS"},
        ]}}}}]}}
    counts = gh.checks_from_rollup(node)
    require(counts == {"passed": 2, "failed": 1, "pending": 1, "total": 4},
            f"rollup bucketing drifted: {counts}")
    require(gh.checks_from_rollup({"commits": {"nodes": [{"commit": {"statusCheckRollup": None}}]}}) is None,
            "no rollup must be null, not zeros")
    # Stage keys ride every normalized row, even when GraphQL omits them.
    entry = gh.normalize_graphql_pr({"number": 1, "repository": {"nameWithOwner": "o/r"}})
    for key in ("review_decision", "merge_state", "checks", "review_requests", "next_action"):
        require(key in entry, f"stage key {key} missing from normalized row")


def test_graphql_inbox() -> None:
    gh = load_agent_gh()

    # Generated documents must balance their braces — an unbalanced sweep
    # alias cost a live round trip (RCURLY parse error, 2026-08-11).
    aliases = " ".join(gh._graphql_search_alias(n, q, 30) for n, q in gh.CEREMONY_SEARCHES)
    sweep = gh._graphql_sweep_alias("is:pr is:open user:someone", "CURSOR")
    for doc in (
        f"query {{ viewer {{ login }} {aliases} }} {gh.GRAPHQL_PR_CORE}",
        f"query {{ {sweep} }} {gh.GRAPHQL_PR_CORE}",
    ):
        require(doc.count("{") == doc.count("}"), f"unbalanced braces in document: {doc}")

    node = {
        "number": 7, "title": "t", "state": "OPEN", "isDraft": False,
        "updatedAt": "2026-08-11T00:00:00Z", "url": "https://x",
        "author": {"login": "someone"},
        "repository": {"nameWithOwner": "o/r"},
        "labels": {"nodes": [{"name": "bug"}]},
        "comments": {"totalCount": 2},
        "headRefOid": "headsha",
        "reviews": {"totalCount": 1, "nodes": [
            {"state": "APPROVED", "submittedAt": "2026-08-10T00:00:00Z",
             "author": {"login": "erik"}, "commit": {"oid": "oldsha"}},
        ]},
    }
    entry = gh.normalize_graphql_pr(node)
    require(entry["ref"] == "o/r#7" and entry["state"] == "open" and entry["comments"] == 2
            and entry["labels"] == ["bug"], f"normalize_graphql_pr drifted from REST shape: {entry}")

    added: list[tuple[str, str]] = []

    def add(reason: str, prs: list) -> None:
        added.extend((reason, pr["ref"]) for pr in prs)

    stats = {"repos_swept": 0, "prs_classified": 0, "waiting_on_author": 0,
             "unswept": [], "skipped_no_role": 0}
    # Viewer's review sits on an old sha -> maintainer_review_stale.
    gh._classify_sweep_node(node, "erik", {"o/r"}, add, stats)
    require(("maintainer_review_stale", "o/r#7") in added, f"stale review misclassified: {added}")
    # Changes requested at head -> ball with the author, nothing added.
    node2 = json.loads(json.dumps(node))
    node2["reviews"]["nodes"][0].update({"state": "CHANGES_REQUESTED", "commit": {"oid": "headsha"}})
    before = list(added)
    gh._classify_sweep_node(node2, "erik", {"o/r"}, add, stats)
    require(added == before and stats["waiting_on_author"] == 1,
            f"changes-requested at head must wait on author: {stats}")
    # A repo outside the eligible set is skipped, mirroring the REST sweep.
    gh._classify_sweep_node(node, "erik", {"other/repo"}, add, stats)
    require(stats["skipped_no_role"] == 1, f"non-eligible repo must be skipped: {stats}")
    # Viewer-authored PRs never enter the sweep.
    node3 = json.loads(json.dumps(node))
    node3["author"] = {"login": "erik"}
    before = list(added)
    gh._classify_sweep_node(node3, "erik", {"o/r"}, add, stats)
    require(added == before, "viewer-authored PR must not enter the sweep")
    # Bot author, no viewer review -> maintainer_unreviewed + bot_author.
    node4 = json.loads(json.dumps(node))
    node4["author"] = {"login": "dependabot"}
    node4["reviews"] = {"totalCount": 0, "nodes": []}
    gh._classify_sweep_node(node4, "erik", {"o/r"}, add, stats)
    require(("maintainer_unreviewed", "o/r#7") in added and ("bot_author", "o/r#7") in added,
            f"bot classification drifted: {added}")


if __name__ == "__main__":
    raise SystemExit(main())
