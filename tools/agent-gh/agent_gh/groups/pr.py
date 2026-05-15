"""PR inspection and action commands."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ..cache import current_user, ensure_state_dir, fetch_repos, read_repos_cache, write_repos_cache
from ..refs import PrRef, parse_pr_ref, pr_gh_args
from ..render import output, print_json, print_table
from ..snapshot import now_iso, parse_github_time
from ..transport import GhError, gh_json, run_gh


PR_VIEW_FIELDS = ",".join(
    [
        "additions",
        "assignees",
        "author",
        "baseRefName",
        "changedFiles",
        "comments",
        "commits",
        "createdAt",
        "deletions",
        "files",
        "headRefName",
        "headRefOid",
        "isDraft",
        "labels",
        "latestReviews",
        "maintainerCanModify",
        "mergeStateStatus",
        "mergeable",
        "number",
        "reviewDecision",
        "reviewRequests",
        "state",
        "statusCheckRollup",
        "title",
        "updatedAt",
        "url",
    ]
)

PR_SEARCH_FIELDS = "number,title,state,url,repository,author,isDraft,updatedAt,commentsCount,labels"


def normalize_pr(item: dict[str, Any]) -> dict[str, Any]:
    repo = item.get("repository") or {}
    author = item.get("author") or {}
    labels = item.get("labels") or []
    return {
        "ref": f"{repo.get('nameWithOwner') or repo.get('fullName') or repo.get('full_name')}#{item.get('number')}",
        "repo": repo.get("nameWithOwner") or repo.get("fullName") or repo.get("full_name"),
        "number": item.get("number"),
        "title": item.get("title"),
        "state": item.get("state"),
        "draft": bool(item.get("isDraft")),
        "author": author.get("login") if isinstance(author, dict) else author,
        "updated_at": item.get("updatedAt"),
        "url": item.get("url"),
        "comments": item.get("commentsCount"),
        "labels": [label.get("name") for label in labels if isinstance(label, dict)],
    }


def review_request_label(request: dict[str, Any]) -> str | None:
    reviewer = request.get("requestedReviewer")
    if not isinstance(reviewer, dict):
        reviewer = request
    return reviewer.get("login") or reviewer.get("slug") or reviewer.get("name")


def search_prs(args: argparse.Namespace) -> list[dict[str, Any]]:
    gh_args = ["search", "prs", "--json", PR_SEARCH_FIELDS, "--limit", str(args.limit)]
    has_explicit_scope = bool(
        args.repo
        or args.owner
        or args.author
        or args.review_requested
        or args.review
        or args.checks
        or args.query
    )
    if args.state != "all":
        gh_args.extend(["--state", args.state])
    for repo in args.repo or []:
        gh_args.extend(["--repo", repo])
    for owner in args.owner or []:
        gh_args.extend(["--owner", owner])
    if args.author:
        gh_args.extend(["--author", args.author])
    if args.review_requested:
        gh_args.extend(["--review-requested", "@me" if args.review_requested == "me" else args.review_requested])
    if args.review:
        gh_args.extend(["--review", args.review])
    if args.checks:
        gh_args.extend(["--checks", args.checks])
    if not has_explicit_scope:
        gh_args.extend(["--author", "@me"])
    if args.query:
        gh_args.append(args.query)
    payload = gh_json(gh_args) or []
    return [normalize_pr(item) for item in payload]


def pr_detail(ref: PrRef) -> dict[str, Any]:
    payload = gh_json(["pr", "view", *pr_gh_args(ref), "--json", PR_VIEW_FIELDS])
    return normalize_pr_detail(ref, payload or {})


def normalize_pr_detail(ref: PrRef, payload: dict[str, Any]) -> dict[str, Any]:
    review_requests = payload.get("reviewRequests") or []
    latest_reviews = payload.get("latestReviews") or []
    files = payload.get("files") or []
    status_rollup = payload.get("statusCheckRollup") or []
    return {
        "ref": f"{ref.repo}#{payload.get('number') or ref.number}",
        "repo": ref.repo,
        "number": payload.get("number") or int(ref.number or 0),
        "title": payload.get("title"),
        "state": payload.get("state"),
        "draft": bool(payload.get("isDraft")),
        "author": (payload.get("author") or {}).get("login"),
        "base": payload.get("baseRefName"),
        "head": payload.get("headRefName"),
        "head_sha": payload.get("headRefOid"),
        "mergeable": payload.get("mergeable"),
        "merge_state": payload.get("mergeStateStatus"),
        "review_decision": payload.get("reviewDecision"),
        "changed_files": payload.get("changedFiles"),
        "additions": payload.get("additions"),
        "deletions": payload.get("deletions"),
        "review_requests": [
            label
            for request in review_requests
            if isinstance(request, dict)
            for label in [review_request_label(request)]
            if label
        ],
        "latest_reviews": [
            {
                "author": (review.get("author") or {}).get("login"),
                "state": review.get("state"),
                "submitted_at": review.get("submittedAt"),
            }
            for review in latest_reviews
            if isinstance(review, dict)
        ],
        "files": [
            {
                "path": file.get("path"),
                "additions": file.get("additions"),
                "deletions": file.get("deletions"),
            }
            for file in files
            if isinstance(file, dict)
        ],
        "checks": summarize_checks(status_rollup),
        "updated_at": payload.get("updatedAt"),
        "created_at": payload.get("createdAt"),
        "url": payload.get("url"),
    }


def summarize_checks(checks: list[Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"total": 0, "passed": 0, "failed": 0, "pending": 0, "items": []}
    for check in checks:
        if not isinstance(check, dict):
            continue
        state = check.get("state") or check.get("status")
        conclusion = check.get("conclusion")
        name = check.get("name") or check.get("workflowName")
        bucket = "pending"
        if conclusion in {"SUCCESS", "success"} or state in {"SUCCESS", "success"}:
            bucket = "passed"
        elif conclusion in {"FAILURE", "failure", "ERROR", "error", "CANCELLED", "cancelled"}:
            bucket = "failed"
        summary["total"] += 1
        summary[bucket] += 1
        summary["items"].append({"name": name, "state": state, "conclusion": conclusion, "bucket": bucket})
    return summary


def pr_checks(ref: PrRef) -> list[dict[str, Any]]:
    payload = gh_json(["pr", "checks", *pr_gh_args(ref), "--json", "name,state,bucket,link,description,workflow,startedAt,completedAt"])
    return payload or []


def pr_diff_text(ref: PrRef) -> str:
    return run_gh(["pr", "diff", *pr_gh_args(ref)])


def pr_threads(ref: PrRef, *, all_threads: bool = False) -> list[dict[str, Any]]:
    if not ref.repo or not ref.number:
        raise GhError("threads requires an explicit PR reference")
    owner, repo = ref.repo.split("/", 1)
    query = """
query($owner:String!, $repo:String!, $number:Int!) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$number) {
      reviewThreads(first:100) {
        nodes {
          id
          isResolved
          path
          line
          comments(first:20) {
            nodes {
              id
              body
              createdAt
              url
              author { login }
            }
          }
        }
      }
    }
  }
}
"""
    payload = gh_json(
        [
            "api",
            "graphql",
            "-f",
            f"owner={owner}",
            "-f",
            f"repo={repo}",
            "-F",
            f"number={ref.number}",
            "-f",
            f"query={query}",
        ]
    )
    nodes = (
        ((payload or {}).get("data") or {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )
    threads = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("isResolved") and not all_threads:
            continue
        comments = [
            {
                "author": (comment.get("author") or {}).get("login"),
                "body": comment.get("body"),
                "created_at": comment.get("createdAt"),
                "url": comment.get("url"),
            }
            for comment in ((node.get("comments") or {}).get("nodes") or [])
            if isinstance(comment, dict)
        ]
        threads.append(
            {
                "id": node.get("id"),
                "resolved": bool(node.get("isResolved")),
                "path": node.get("path"),
                "line": node.get("line"),
                "comments": comments,
            }
        )
    return threads


def build_inbox(limit: int) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}

    def add(reason: str, prs: list[dict[str, Any]]) -> None:
        for pr in prs:
            key = pr.get("ref") or pr.get("url")
            if not key:
                continue
            entry = items.setdefault(key, {**pr, "reasons": []})
            if reason not in entry["reasons"]:
                entry["reasons"].append(reason)

    base = argparse.Namespace(
        limit=limit,
        state="open",
        repo=[],
        owner=[],
        author=None,
        review_requested="me",
        review=None,
        checks=None,
        query=None,
    )
    add("review_requested", search_prs(base))

    mine = argparse.Namespace(**{**vars(base), "review_requested": None, "author": "@me"})
    add("authored_open", search_prs(mine))

    failed = argparse.Namespace(**{**vars(base), "review_requested": None, "author": "@me", "checks": "failure"})
    add("authored_failed_checks", search_prs(failed))

    changes = argparse.Namespace(**{**vars(base), "review_requested": None, "author": "@me", "review": "changes_requested"})
    add("authored_changes_requested", search_prs(changes))

    return list(items.values())[:limit]


def is_bot_login(login: str | None) -> bool:
    if not login:
        return False
    lower = login.lower()
    return lower.endswith("[bot]") or lower in {"dependabot", "dependabot-preview"}


def search_candidates_for_awaiting(args: argparse.Namespace) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}

    def add(prs: list[dict[str, Any]]) -> None:
        for pr in prs:
            key = pr.get("ref") or pr.get("url")
            if key:
                items.setdefault(key, pr)

    base = argparse.Namespace(
        limit=args.limit,
        state="open",
        repo=args.repo or [],
        owner=args.owner or [],
        author=None,
        review_requested=None,
        review=None,
        checks=None,
        query=args.query,
    )

    strict = argparse.Namespace(**{**vars(base), "review_requested": "me"})
    add(search_prs(strict))

    has_broad_scope = bool(args.repo or args.owner or args.author or args.query)
    if has_broad_scope:
        authors = args.author or [None]
        for author in authors:
            broad = argparse.Namespace(**{**vars(base), "author": author})
            add(search_prs(broad))

    return list(items.values())


def awaiting_reasons(detail: dict[str, Any], viewer: str, *, include_reviewed: bool) -> list[str]:
    reasons: list[str] = []
    review_requests = set(detail.get("review_requests") or [])
    if viewer in review_requests:
        reasons.append("review_requested")

    viewer_reviews = [
        review
        for review in detail.get("latest_reviews", [])
        if isinstance(review, dict) and review.get("author") == viewer
    ]
    latest_review = max(
        viewer_reviews,
        key=lambda review: review.get("submitted_at") or "",
        default=None,
    )
    if latest_review is None:
        reasons.append("not_reviewed_by_me")
        return reasons

    review_state = latest_review.get("state")
    submitted_at = parse_github_time(latest_review.get("submitted_at"))
    updated_at = parse_github_time(detail.get("updated_at"))
    if submitted_at and updated_at and updated_at > submitted_at:
        reasons.append("updated_after_my_review")
    elif review_state == "COMMENTED":
        reasons.append("commented_not_decisive")
    elif include_reviewed:
        reasons.append(f"reviewed_by_me:{review_state or 'unknown'}")

    return reasons


def build_awaiting(args: argparse.Namespace) -> dict[str, Any]:
    viewer = current_user().get("login") or ""
    candidates = search_candidates_for_awaiting(args)
    details: list[dict[str, Any]] = []
    seen: set[str] = set()

    for candidate in candidates:
        repo = candidate.get("repo")
        number = candidate.get("number")
        if not repo or not number:
            continue
        ref = f"{repo}#{number}"
        if ref in seen:
            continue
        seen.add(ref)
        detail = pr_detail(PrRef(repo=repo, number=str(number), original=ref))
        if str(detail.get("state") or "").upper() != "OPEN":
            continue
        if detail.get("draft") and not args.include_drafts:
            continue
        if detail.get("author") == viewer:
            continue
        if is_bot_login(detail.get("author")) and not args.include_bots:
            continue
        reasons = awaiting_reasons(detail, viewer, include_reviewed=args.include_reviewed)
        if not reasons:
            continue
        details.append({**detail, "reasons": reasons})

    details.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    scope_note = None
    if not (args.repo or args.owner or args.author or args.query):
        scope_note = "Unscoped awaiting uses strict review requests only. Add --owner, --repo, --author, or a query for broader not-yet-reviewed PR discovery."
    return {"viewer": viewer, "count": len(details), "items": details[: args.limit], "scope_note": scope_note}


def read_body(args: argparse.Namespace, *, required: bool = False) -> str | None:
    if args.body_file:
        if args.body_file == "-":
            return sys.stdin.read()
        return Path(args.body_file).read_text()
    if args.body:
        return args.body
    if required:
        raise GhError("--body or --body-file is required")
    return None


# ── command handlers ───────────────────────────────────────────────────────────

def cmd_whoami(args: argparse.Namespace) -> None:
    output({"user": current_user(refresh=args.refresh)}, json_mode=args.json)


def cmd_repos(args: argparse.Namespace) -> None:
    if args.repos_command == "sync" or args.refresh:
        repos = fetch_repos(limit=args.limit)
        write_repos_cache(repos)
        payload: dict[str, Any] = {"synced_at": now_iso(), "count": len(repos), "repos": repos}
    else:
        cache = read_repos_cache()
        if cache is None:
            repos = fetch_repos(limit=args.limit)
            write_repos_cache(repos)
            payload = {"synced_at": now_iso(), "count": len(repos), "repos": repos}
        else:
            repos = cache.get("repos", [])
            if args.limit:
                repos = repos[: args.limit]
            payload = {**cache, "count": len(repos), "repos": repos}
    if args.json:
        print_json(payload)
    else:
        print_table(payload["repos"], ["full_name", "visibility", "default_branch", "updated_at"])


def cmd_prs(args: argparse.Namespace) -> None:
    prs = search_prs(args)
    payload = {"count": len(prs), "prs": prs}
    if args.json:
        print_json(payload)
    else:
        print_table(prs, ["ref", "state", "draft", "author", "updated_at", "title"])


def cmd_inbox(args: argparse.Namespace) -> None:
    entries = build_inbox(args.limit)
    payload = {"count": len(entries), "items": entries}
    if args.json:
        print_json(payload)
    else:
        print_table(entries, ["ref", "reasons", "state", "author", "updated_at", "title"])


def cmd_awaiting(args: argparse.Namespace) -> None:
    from ..groups import audit as audit_group

    payload = build_awaiting(args)
    if args.audit or args.replies:
        audited_items = []
        for item in payload.get("items", []):
            ref = PrRef(repo=item.get("repo"), number=str(item.get("number")), original=item.get("ref") or "")
            audit = audit_group.audit_pr(ref, probe_deploys=args.probe_deploys)
            if args.replies:
                audit["reply"] = audit_group.format_audit_reply(audit)
            audited_items.append({**item, "audit": audit})
        payload = {**payload, "items": audited_items, "audit_enabled": True, "deployment_probe_enabled": args.probe_deploys}
    if args.json:
        print_json(payload)
    else:
        if args.replies:
            for item in payload.get("items", []):
                print(f"## {item.get('ref')}: {item.get('title')}")
                print()
                print((item.get("audit") or {}).get("reply") or "")
                print()
        elif args.audit:
            rows = []
            for item in payload.get("items", []):
                audit = item.get("audit") or {}
                findings = audit.get("findings") or []
                rows.append(
                    {
                        "ref": item.get("ref"),
                        "verdict": audit.get("verdict"),
                        "findings": len(findings),
                        "top_finding": findings[0].get("title") if findings else "",
                    }
                )
            print_table(rows, ["ref", "verdict", "findings", "top_finding"])
        else:
            print_table(payload["items"], ["ref", "reasons", "state", "author", "updated_at", "title"])
        if payload.get("scope_note"):
            print(f"\nNote: {payload['scope_note']}")


def cmd_pr(args: argparse.Namespace) -> None:
    ref = parse_pr_ref(args.pr)
    detail = pr_detail(ref)
    if args.json:
        print_json({"pr": detail})
    else:
        output(detail, json_mode=False)


def cmd_diff(args: argparse.Namespace) -> None:
    ref = parse_pr_ref(args.pr)
    print(run_gh(["pr", "diff", *pr_gh_args(ref)]), end="")


def cmd_threads(args: argparse.Namespace) -> None:
    ref = parse_pr_ref(args.pr)
    threads = pr_threads(ref, all_threads=args.all)
    payload = {"count": len(threads), "threads": threads}
    if args.json:
        print_json(payload)
    else:
        rows = []
        for thread in threads:
            first = (thread.get("comments") or [{}])[0]
            rows.append(
                {
                    "path": thread.get("path"),
                    "line": thread.get("line"),
                    "resolved": thread.get("resolved"),
                    "author": first.get("author"),
                    "body": (first.get("body") or "").replace("\n", " ")[:100],
                }
            )
        print_table(rows, ["path", "line", "resolved", "author", "body"])


def cmd_checks(args: argparse.Namespace) -> None:
    ref = parse_pr_ref(args.pr)
    checks = pr_checks(ref)
    payload = {"count": len(checks), "checks": checks}
    if args.json:
        print_json(payload)
    else:
        print_table(checks, ["name", "state", "bucket", "link"])


def cmd_review_summary(args: argparse.Namespace) -> None:
    ref = parse_pr_ref(args.pr)
    detail = pr_detail(ref)
    checks = pr_checks(ref)
    threads = pr_threads(ref)
    payload = {
        "pr": detail,
        "checks": {"count": len(checks), "items": checks},
        "unresolved_threads": {"count": len(threads), "items": threads},
    }
    if args.json:
        print_json(payload)
    else:
        print(f"{detail.get('ref')}: {detail.get('title')}")
        print(f"State: {detail.get('state')}  Draft: {detail.get('draft')}  Review: {detail.get('review_decision')}")
        print(f"Checks: {len(checks)}  Unresolved threads: {len(threads)}")
        print(f"Files changed: {detail.get('changed_files')}  +{detail.get('additions')} -{detail.get('deletions')}")


def cmd_review_action(args: argparse.Namespace, action: str) -> None:
    ref = parse_pr_ref(args.pr)
    body = read_body(args, required=action == "--request-changes")
    gh_args = ["pr", "review", *pr_gh_args(ref), action]
    if body:
        gh_args.extend(["--body", body])
    run_gh(gh_args)
    print(f"Submitted review for {ref.repo}#{ref.number}")


def cmd_merge(args: argparse.Namespace) -> None:
    ref = parse_pr_ref(args.pr)
    strategy = "--squash"
    if args.merge:
        strategy = "--merge"
    if args.rebase:
        strategy = "--rebase"
    gh_args = ["pr", "merge", *pr_gh_args(ref), strategy]
    if args.auto:
        gh_args.append("--auto")
    if args.delete_branch:
        gh_args.append("--delete-branch")
    if args.match_head_commit:
        gh_args.extend(["--match-head-commit", args.match_head_commit])
    if args.subject:
        gh_args.extend(["--subject", args.subject])
    if args.body:
        gh_args.extend(["--body", args.body])
    run_gh(gh_args)
    print(f"Merged {ref.repo}#{ref.number}")


def cmd_ready(args: argparse.Namespace, *, draft: bool = False) -> None:
    ref = parse_pr_ref(args.pr)
    gh_args = ["pr", "ready", *pr_gh_args(ref)]
    if draft:
        gh_args.append("--undo")
    run_gh(gh_args)
    print(f"{'Converted to draft' if draft else 'Marked ready'}: {ref.repo}#{ref.number}")


def read_comment(args: argparse.Namespace) -> str | None:
    """Read a comment string from --comment or --comment-file (- for stdin)."""
    if args.comment_file:
        if args.comment_file == "-":
            return sys.stdin.read()
        return Path(args.comment_file).read_text()
    if args.comment:
        return args.comment
    return None


def cmd_close(args: argparse.Namespace) -> None:
    ref = parse_pr_ref(args.pr)
    gh_args = ["pr", "close", *pr_gh_args(ref)]
    if args.delete_branch:
        gh_args.append("--delete-branch")
    comment = read_comment(args)
    if comment:
        gh_args.extend(["--comment", comment])
    run_gh(gh_args)
    print(f"Closed {ref.repo}#{ref.number}")


def cmd_reopen(args: argparse.Namespace) -> None:
    ref = parse_pr_ref(args.pr)
    gh_args = ["pr", "reopen", *pr_gh_args(ref)]
    comment = read_comment(args)
    if comment:
        gh_args.extend(["--comment", comment])
    run_gh(gh_args)
    print(f"Reopened {ref.repo}#{ref.number}")


def cmd_checkout(args: argparse.Namespace) -> None:
    ref = parse_pr_ref(args.pr)
    gh_args = ["pr", "checkout", *pr_gh_args(ref)]
    if args.branch:
        gh_args.extend(["--branch", args.branch])
    if args.detach:
        gh_args.append("--detach")
    if args.force:
        gh_args.append("--force")
    if args.recurse_submodules:
        gh_args.append("--recurse-submodules")
    run_gh(gh_args)
    print(f"Checked out {ref.repo}#{ref.number}")


def append_repeated_flag(gh_args: list[str], flag: str, values: list[str] | None) -> None:
    """Append a repeated CLI flag for each value in the list."""
    for value in values or []:
        gh_args.extend([flag, value])


def cmd_edit(args: argparse.Namespace) -> None:
    ref = parse_pr_ref(args.pr)
    gh_args = ["pr", "edit", *pr_gh_args(ref)]
    if args.title:
        gh_args.extend(["--title", args.title])
    if args.body:
        gh_args.extend(["--body", args.body])
    if args.body_file:
        gh_args.extend(["--body-file", args.body_file])
    if args.base:
        gh_args.extend(["--base", args.base])
    if args.milestone:
        gh_args.extend(["--milestone", args.milestone])
    if args.remove_milestone:
        gh_args.append("--remove-milestone")
    append_repeated_flag(gh_args, "--add-label", args.add_label)
    append_repeated_flag(gh_args, "--remove-label", args.remove_label)
    append_repeated_flag(gh_args, "--add-assignee", args.add_assignee)
    append_repeated_flag(gh_args, "--remove-assignee", args.remove_assignee)
    append_repeated_flag(gh_args, "--add-reviewer", args.add_reviewer)
    append_repeated_flag(gh_args, "--remove-reviewer", args.remove_reviewer)
    append_repeated_flag(gh_args, "--add-project", args.add_project)
    append_repeated_flag(gh_args, "--remove-project", args.remove_project)
    run_gh(gh_args)
    print(f"Edited {ref.repo}#{ref.number}")


def cmd_update_branch(args: argparse.Namespace) -> None:
    ref = parse_pr_ref(args.pr)
    gh_args = ["pr", "update-branch", *pr_gh_args(ref)]
    if args.rebase:
        gh_args.append("--rebase")
    run_gh(gh_args)
    print(f"Updated branch for {ref.repo}#{ref.number}")
