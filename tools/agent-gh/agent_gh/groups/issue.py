"""Issue management commands."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ..refs import IssueRef, parse_issue, parse_repo
from ..render import output, print_json, print_table
from ..snapshot import envelope
from ..transport import GhError, gh_json, run_gh


_ISSUE_LIST_FIELDS = "number,title,state,author,labels,assignees,milestone,createdAt,updatedAt,url"
_ISSUE_VIEW_FIELDS = "number,title,state,author,body,labels,assignees,milestone,createdAt,updatedAt,closedAt,url"


def _read_body(args: argparse.Namespace) -> str | None:
    if getattr(args, "body_file", None):
        p = args.body_file
        return sys.stdin.read() if p == "-" else Path(p).read_text()
    return getattr(args, "body", None)


# ── core data functions ────────────────────────────────────────────────────────

def list_issues(repo: str, *, state: str = "open", labels: list[str] | None = None,
                assignee: str | None = None, author: str | None = None,
                milestone: str | None = None, limit: int = 50) -> dict[str, Any]:
    """List issues in a repo, returning a structured envelope."""
    r = parse_repo(repo)
    args = ["issue", "list", "--repo", r.slug, "--state", state,
            "--limit", str(limit), "--json", _ISSUE_LIST_FIELDS]
    for lbl in labels or []:
        args += ["--label", lbl]
    if assignee:
        args += ["--assignee", assignee]
    if author:
        args += ["--author", author]
    if milestone:
        args += ["--milestone", milestone]
    return envelope("issue list", ref=r.slug, data={"issues": gh_json(args) or []})


def view_issue(ref: str, *, comments: bool = False) -> dict[str, Any]:
    """Fetch full details for a single issue by owner/repo#num reference."""
    i = parse_issue(ref)
    fields = _ISSUE_VIEW_FIELDS + (",comments" if comments else "")
    return envelope("issue view", ref=i.slug, data=gh_json(
        ["issue", "view", str(i.number), "--repo", i.repo_ref.slug, "--json", fields]
    ) or {})


def create_issue(repo: str, *, title: str, body: str | None = None,
                 body_file: str | None = None, labels: list[str] | None = None,
                 assignees: list[str] | None = None, milestone: str | None = None,
                 project: str | None = None) -> dict[str, Any]:
    """Create a new issue in a repo; returns an envelope with the new issue URL."""
    r = parse_repo(repo)
    args = ["issue", "create", "--repo", r.slug, "--title", title]
    if body is not None:
        args += ["--body", body]
    elif body_file is not None:
        btext = sys.stdin.read() if body_file == "-" else Path(body_file).read_text()
        args += ["--body", btext]
    else:
        args += ["--body", ""]
    for lbl in labels or []:
        args += ["--label", lbl]
    for a in assignees or []:
        args += ["--assignee", a]
    if milestone:
        args += ["--milestone", milestone]
    if project:
        args += ["--project", project]
    out = run_gh(args).strip()
    url = out.splitlines()[-1] if out else None
    return envelope("issue create", ref=r.slug, data={"url": url})


def comment_issue(ref: str, *, body: str | None = None, body_file: str | None = None) -> dict[str, Any]:
    """Post a comment on an issue."""
    i = parse_issue(ref)
    if body is None and body_file is None:
        raise GhError("--body or --body-file is required for issue comment")
    args = ["issue", "comment", str(i.number), "--repo", i.repo_ref.slug]
    if body is not None:
        args += ["--body", body]
    else:
        btext = sys.stdin.read() if body_file == "-" else Path(body_file).read_text()  # type: ignore[arg-type]
        args += ["--body", btext]
    run_gh(args)
    return envelope("issue comment", ref=i.slug, data={"commented": True})


def close_issue(ref: str, *, reason: str | None = None, comment: str | None = None) -> dict[str, Any]:
    """Close an issue, optionally with a reason and closing comment."""
    i = parse_issue(ref)
    args = ["issue", "close", str(i.number), "--repo", i.repo_ref.slug]
    if reason:
        args += ["--reason", reason]
    if comment:
        args += ["--comment", comment]
    run_gh(args)
    return envelope("issue close", ref=i.slug, data={"closed": True, "reason": reason})


def reopen_issue(ref: str, *, comment: str | None = None) -> dict[str, Any]:
    """Reopen a closed issue."""
    i = parse_issue(ref)
    args = ["issue", "reopen", str(i.number), "--repo", i.repo_ref.slug]
    if comment:
        args += ["--comment", comment]
    run_gh(args)
    return envelope("issue reopen", ref=i.slug, data={"reopened": True})


def label_issue(ref: str, *, add: list[str] | None = None, remove: list[str] | None = None) -> dict[str, Any]:
    """Add or remove labels on an issue."""
    i = parse_issue(ref)
    args = ["issue", "edit", str(i.number), "--repo", i.repo_ref.slug]
    for lbl in add or []:
        args += ["--add-label", lbl]
    for lbl in remove or []:
        args += ["--remove-label", lbl]
    if not add and not remove:
        raise GhError("--add or --remove is required for issue label")
    run_gh(args)
    return envelope("issue label", ref=i.slug, data={"add": add or [], "remove": remove or []})


def assign_issue(ref: str, *, add: list[str] | None = None, remove: list[str] | None = None) -> dict[str, Any]:
    """Add or remove assignees on an issue."""
    i = parse_issue(ref)
    args = ["issue", "edit", str(i.number), "--repo", i.repo_ref.slug]
    for a in add or []:
        args += ["--add-assignee", a]
    for a in remove or []:
        args += ["--remove-assignee", a]
    if not add and not remove:
        raise GhError("--add or --remove is required for issue assign")
    run_gh(args)
    return envelope("issue assign", ref=i.slug, data={"add": add or [], "remove": remove or []})


def snapshot_issues(repo: str, *, state: str = "open", limit: int = 100) -> dict[str, Any]:
    return list_issues(repo, state=state, limit=limit)


# ── command handlers ───────────────────────────────────────────────────────────

def cmd_issue_list(args: argparse.Namespace) -> None:
    result = list_issues(
        args.repo,
        state=args.state,
        labels=args.labels,
        assignee=args.assignee,
        author=args.author,
        milestone=args.milestone,
        limit=args.limit,
    )
    if args.json:
        print_json(result)
    else:
        print_table(result["data"]["issues"], ["number", "state", "title", "author", "updatedAt"])


def cmd_issue_view(args: argparse.Namespace) -> None:
    result = view_issue(args.issue_ref, comments=args.comments)
    if args.json:
        print_json(result)
    else:
        d = result["data"]
        print(f"#{d.get('number')} {d.get('title')}")
        print(f"State: {d.get('state')}  Author: {(d.get('author') or {}).get('login')}")
        print(f"Labels: {', '.join(l.get('name','') for l in d.get('labels') or [])}")
        if d.get("body"):
            print()
            print(d["body"])


def cmd_issue_create(args: argparse.Namespace) -> None:
    if args.dry_run:
        print(f"[dry-run] would create issue in {args.repo}: {args.title!r}")
        return
    result = create_issue(
        args.repo,
        title=args.title,
        body=args.body,
        body_file=args.body_file,
        labels=args.labels,
        assignees=args.assignees,
        milestone=args.milestone,
        project=args.project,
    )
    if args.json:
        print_json(result)
    else:
        print(f"Created: {result['data'].get('url')}")


def cmd_issue_comment(args: argparse.Namespace) -> None:
    if args.dry_run:
        print(f"[dry-run] would comment on {args.issue_ref}")
        return
    body = _read_body(args)
    result = comment_issue(args.issue_ref, body=body)
    if args.json:
        print_json(result)
    else:
        print(f"Commented on {args.issue_ref}")


def cmd_issue_close(args: argparse.Namespace) -> None:
    if args.dry_run:
        print(f"[dry-run] would close {args.issue_ref}")
        return
    result = close_issue(args.issue_ref, reason=args.reason, comment=args.comment)
    if args.json:
        print_json(result)
    else:
        print(f"Closed {args.issue_ref}")


def cmd_issue_reopen(args: argparse.Namespace) -> None:
    if args.dry_run:
        print(f"[dry-run] would reopen {args.issue_ref}")
        return
    result = reopen_issue(args.issue_ref, comment=args.comment)
    if args.json:
        print_json(result)
    else:
        print(f"Reopened {args.issue_ref}")


def cmd_issue_label(args: argparse.Namespace) -> None:
    if args.dry_run:
        print(f"[dry-run] would update labels on {args.issue_ref}")
        return
    result = label_issue(args.issue_ref, add=args.add_labels, remove=args.remove_labels)
    if args.json:
        print_json(result)
    else:
        print(f"Updated labels on {args.issue_ref}")


def cmd_issue_assign(args: argparse.Namespace) -> None:
    if args.dry_run:
        print(f"[dry-run] would update assignees on {args.issue_ref}")
        return
    result = assign_issue(args.issue_ref, add=args.add_assignees, remove=args.remove_assignees)
    if args.json:
        print_json(result)
    else:
        print(f"Updated assignees on {args.issue_ref}")


def cmd_issue_snapshot(args: argparse.Namespace) -> None:
    result = snapshot_issues(args.repo, state=args.state, limit=args.limit)
    if args.json:
        print_json(result)
    else:
        print_table(result["data"]["issues"], ["number", "state", "title", "updatedAt"])


def cmd_issue_triage(args: argparse.Namespace) -> None:
    from ..triage.issue_triage import triage
    result = triage(args.issue_ref)
    if args.json:
        print_json(result)
    else:
        d = result["data"]
        print(f"Classification : {d.get('classification')} (confidence {d.get('confidence', 0):.0%})")
        print(f"Suggested labels: {', '.join(d.get('suggested_labels') or [])}")
        if d.get("needs_repro"):
            print("  → Needs repro steps")
        if d.get("needs_version"):
            print("  → Needs version info")
        if d.get("related_issues"):
            print(f"Related ({len(d['related_issues'])}):")
            for ri in d["related_issues"]:
                print(f"  #{ri.get('number')} [{ri.get('state')}] {ri.get('title')}")
        print()
        print("Suggested first response:")
        print(d.get("first_response_draft", ""))
