"""CLI entry point: argument parser and main dispatcher."""
from __future__ import annotations

import argparse
import sys
from typing import Any

from .groups import audit as audit_group
from .groups import pr as pr_group
from .transport import GhError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="agent-gh - GitHub work-state for agent-do")
    parser.set_defaults(func=None)
    sub = parser.add_subparsers(dest="command")

    # ── existing: identity + repo inventory ────────────────────────────────────
    whoami = sub.add_parser("whoami", help="Show authenticated GitHub user")
    whoami.add_argument("--json", action="store_true")
    whoami.add_argument("--refresh", action="store_true")
    whoami.set_defaults(func=pr_group.cmd_whoami)

    repos = sub.add_parser("repos", help="List or sync accessible repositories")
    repos.add_argument("repos_command", nargs="?", choices=["sync"], default="list")
    repos.add_argument("--json", action="store_true")
    repos.add_argument("--refresh", action="store_true")
    repos.add_argument("--limit", type=int)
    repos.set_defaults(func=pr_group.cmd_repos)

    # ── existing: PR search + inbox ────────────────────────────────────────────
    prs = sub.add_parser("prs", help="Search pull requests")
    prs.add_argument("query", nargs="?")
    prs.add_argument("--json", action="store_true")
    prs.add_argument("--limit", type=int, default=30)
    prs.add_argument("--state", choices=["open", "closed", "all"], default="open")
    prs.add_argument("--repo", action="append")
    prs.add_argument("--owner", action="append")
    prs.add_argument("--author")
    prs.add_argument("--review-requested", nargs="?", const="me")
    prs.add_argument("--review", choices=["none", "required", "approved", "changes_requested"])
    prs.add_argument("--checks", choices=["pending", "success", "failure"])
    prs.set_defaults(func=pr_group.cmd_prs)

    inbox = sub.add_parser("inbox", help="Show actionable PR work across repositories")
    inbox.add_argument("--json", action="store_true")
    inbox.add_argument("--limit", type=int, default=30)
    inbox.set_defaults(func=pr_group.cmd_inbox)

    awaiting = sub.add_parser("awaiting", help="Show open PRs likely awaiting your review")
    awaiting.add_argument("query", nargs="?")
    awaiting.add_argument("--json", action="store_true")
    awaiting.add_argument("--limit", type=int, default=50)
    awaiting.add_argument("--repo", action="append")
    awaiting.add_argument("--owner", action="append")
    awaiting.add_argument("--author", action="append")
    awaiting.add_argument("--include-bots", action="store_true")
    awaiting.add_argument("--include-drafts", action="store_true")
    awaiting.add_argument("--include-reviewed", action="store_true")
    awaiting.add_argument("--audit", action="store_true")
    awaiting.add_argument("--replies", action="store_true")
    awaiting.add_argument("--probe-deploys", action="store_true")
    awaiting.set_defaults(func=pr_group.cmd_awaiting)

    # ── existing: PR detail ────────────────────────────────────────────────────
    pr = sub.add_parser("pr", help="Show PR detail")
    pr.add_argument("pr", nargs="?")
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(func=pr_group.cmd_pr)

    diff = sub.add_parser("diff", help="Show PR diff")
    diff.add_argument("pr")
    diff.set_defaults(func=pr_group.cmd_diff)

    threads = sub.add_parser("threads", help="Show PR review threads")
    threads.add_argument("pr")
    threads.add_argument("--all", action="store_true")
    threads.add_argument("--json", action="store_true")
    threads.set_defaults(func=pr_group.cmd_threads)

    checks = sub.add_parser("checks", help="Show PR checks")
    checks.add_argument("pr")
    checks.add_argument("--json", action="store_true")
    checks.set_defaults(func=pr_group.cmd_checks)

    review = sub.add_parser("review", help="Summarize a PR for review")
    review.add_argument("pr")
    review.add_argument("--summary", action="store_true", default=True)
    review.add_argument("--json", action="store_true")
    review.set_defaults(func=pr_group.cmd_review_summary)

    audit = sub.add_parser("audit", help="Audit a PR for review risks")
    audit.add_argument("pr")
    audit.add_argument("--json", action="store_true")
    audit.add_argument("--reply", action="store_true")
    audit.add_argument("--probe-deploys", action="store_true")
    audit.set_defaults(func=audit_group.cmd_audit)

    # ── existing: PR actions ───────────────────────────────────────────────────
    for name, action, help_text, _body_required in [
        ("approve", "--approve", "Approve a pull request", False),
        ("request-changes", "--request-changes", "Request changes on a pull request", True),
        ("comment", "--comment", "Comment on a pull request", False),
    ]:
        ap = sub.add_parser(name, help=help_text)
        ap.add_argument("pr")
        ap.add_argument("--body")
        ap.add_argument("--body-file")
        ap.set_defaults(func=lambda ns, a=action: pr_group.cmd_review_action(ns, a))

    merge = sub.add_parser("merge", help="Merge a pull request")
    merge.add_argument("pr")
    strategy = merge.add_mutually_exclusive_group()
    strategy.add_argument("--squash", action="store_true")
    strategy.add_argument("--merge", action="store_true")
    strategy.add_argument("--rebase", action="store_true")
    merge.add_argument("--auto", action="store_true")
    merge.add_argument("--delete-branch", action="store_true")
    merge.add_argument("--match-head-commit")
    merge.add_argument("--subject")
    merge.add_argument("--body")
    merge.set_defaults(func=pr_group.cmd_merge)

    ready = sub.add_parser("ready", help="Mark a pull request ready for review")
    ready.add_argument("pr")
    ready.set_defaults(func=lambda ns: pr_group.cmd_ready(ns, draft=False))

    draft = sub.add_parser("draft", help="Convert a pull request to draft")
    draft.add_argument("pr")
    draft.set_defaults(func=lambda ns: pr_group.cmd_ready(ns, draft=True))

    # ── v1.2 PR actions (ported from flat script) ──────────────────────────────
    close = sub.add_parser("close", help="Close a pull request")
    close.add_argument("pr")
    close.add_argument("--delete-branch", action="store_true")
    close.add_argument("--comment")
    close.add_argument("--comment-file")
    close.set_defaults(func=pr_group.cmd_close)

    reopen = sub.add_parser("reopen", help="Reopen a pull request")
    reopen.add_argument("pr")
    reopen.add_argument("--comment")
    reopen.add_argument("--comment-file")
    reopen.set_defaults(func=pr_group.cmd_reopen)

    checkout = sub.add_parser("checkout", aliases=["co"], help="Check out a pull request locally")
    checkout.add_argument("pr")
    checkout.add_argument("--branch")
    checkout.add_argument("--detach", action="store_true")
    checkout.add_argument("--force", action="store_true")
    checkout.add_argument("--recurse-submodules", action="store_true")
    checkout.set_defaults(func=pr_group.cmd_checkout)

    edit = sub.add_parser("edit", help="Edit pull request metadata")
    edit.add_argument("pr")
    edit.add_argument("--title")
    edit.add_argument("--body")
    edit.add_argument("--body-file")
    edit.add_argument("--base")
    edit.add_argument("--milestone")
    edit.add_argument("--remove-milestone", action="store_true")
    edit.add_argument("--add-label", action="append")
    edit.add_argument("--remove-label", action="append")
    edit.add_argument("--add-assignee", action="append")
    edit.add_argument("--remove-assignee", action="append")
    edit.add_argument("--add-reviewer", action="append")
    edit.add_argument("--remove-reviewer", action="append")
    edit.add_argument("--add-project", action="append")
    edit.add_argument("--remove-project", action="append")
    edit.set_defaults(func=pr_group.cmd_edit)

    update_branch = sub.add_parser("update-branch", help="Update a PR branch from its base branch")
    update_branch.add_argument("pr")
    update_branch.add_argument("--rebase", action="store_true")
    update_branch.set_defaults(func=pr_group.cmd_update_branch)

    # ── Phase 1: issue ─────────────────────────────────────────────────────────
    _build_issue_parser(sub)

    # ── Phase 1: release ───────────────────────────────────────────────────────
    _build_release_parser(sub)

    # ── Phase 1: api / graphql ─────────────────────────────────────────────────
    _build_api_parser(sub)

    return parser


def _build_issue_parser(sub: Any) -> None:
    from .groups import issue as issue_group

    issue_p = sub.add_parser("issue", help="Issue management")
    issue_sub = issue_p.add_subparsers(dest="issue_command")
    issue_p.set_defaults(func=lambda ns: _subcommand_help(issue_p, ns.issue_command))

    il = issue_sub.add_parser("list", help="List issues")
    il.add_argument("repo", help="owner/repo")
    il.add_argument("--state", choices=["open", "closed", "all"], default="open")
    il.add_argument("--label", action="append", dest="labels")
    il.add_argument("--assignee")
    il.add_argument("--author")
    il.add_argument("--milestone")
    il.add_argument("--limit", type=int, default=50)
    il.add_argument("--json", action="store_true")
    il.set_defaults(func=issue_group.cmd_issue_list)

    iv = issue_sub.add_parser("view", help="View an issue")
    iv.add_argument("issue_ref", help="owner/repo#num")
    iv.add_argument("--comments", action="store_true")
    iv.add_argument("--json", action="store_true")
    iv.set_defaults(func=issue_group.cmd_issue_view)

    ic = issue_sub.add_parser("create", help="Create an issue")
    ic.add_argument("repo", help="owner/repo")
    ic.add_argument("--title", required=True)
    ic.add_argument("--body")
    ic.add_argument("--body-file")
    ic.add_argument("--label", action="append", dest="labels")
    ic.add_argument("--assignee", action="append", dest="assignees")
    ic.add_argument("--milestone")
    ic.add_argument("--project")
    ic.add_argument("--dry-run", action="store_true")
    ic.add_argument("--json", action="store_true")
    ic.set_defaults(func=issue_group.cmd_issue_create)

    ico = issue_sub.add_parser("comment", help="Comment on an issue")
    ico.add_argument("issue_ref", help="owner/repo#num")
    ico.add_argument("--body")
    ico.add_argument("--body-file")
    ico.add_argument("--dry-run", action="store_true")
    ico.add_argument("--json", action="store_true")
    ico.set_defaults(func=issue_group.cmd_issue_comment)

    icl = issue_sub.add_parser("close", help="Close an issue")
    icl.add_argument("issue_ref", help="owner/repo#num")
    icl.add_argument("--reason", choices=["completed", "not_planned"])
    icl.add_argument("--comment")
    icl.add_argument("--dry-run", action="store_true")
    icl.add_argument("--json", action="store_true")
    icl.set_defaults(func=issue_group.cmd_issue_close)

    iro = issue_sub.add_parser("reopen", help="Reopen a closed issue")
    iro.add_argument("issue_ref", help="owner/repo#num")
    iro.add_argument("--comment")
    iro.add_argument("--dry-run", action="store_true")
    iro.add_argument("--json", action="store_true")
    iro.set_defaults(func=issue_group.cmd_issue_reopen)

    ilb = issue_sub.add_parser("label", help="Add or remove labels")
    ilb.add_argument("issue_ref", help="owner/repo#num")
    ilb.add_argument("--add", action="append", dest="add_labels")
    ilb.add_argument("--remove", action="append", dest="remove_labels")
    ilb.add_argument("--dry-run", action="store_true")
    ilb.add_argument("--json", action="store_true")
    ilb.set_defaults(func=issue_group.cmd_issue_label)

    iasn = issue_sub.add_parser("assign", help="Add or remove assignees")
    iasn.add_argument("issue_ref", help="owner/repo#num")
    iasn.add_argument("--add", action="append", dest="add_assignees")
    iasn.add_argument("--remove", action="append", dest="remove_assignees")
    iasn.add_argument("--dry-run", action="store_true")
    iasn.add_argument("--json", action="store_true")
    iasn.set_defaults(func=issue_group.cmd_issue_assign)

    isnap = issue_sub.add_parser("snapshot", help="Bulk structured snapshot of open issues")
    isnap.add_argument("repo", help="owner/repo")
    isnap.add_argument("--state", choices=["open", "closed", "all"], default="open")
    isnap.add_argument("--limit", type=int, default=100)
    isnap.add_argument("--json", action="store_true")
    isnap.set_defaults(func=issue_group.cmd_issue_snapshot)

    itr = issue_sub.add_parser("triage", help="Deterministic issue triage with classification and suggested labels")
    itr.add_argument("issue_ref", help="owner/repo#num")
    itr.add_argument("--json", action="store_true")
    itr.set_defaults(func=issue_group.cmd_issue_triage)


def _build_release_parser(sub: Any) -> None:
    from .groups import release as release_group

    rel_p = sub.add_parser("release", help="Release management")
    rel_sub = rel_p.add_subparsers(dest="release_command")
    rel_p.set_defaults(func=lambda ns: _subcommand_help(rel_p, ns.release_command))

    rlist = rel_sub.add_parser("list", help="List releases")
    rlist.add_argument("repo", help="owner/repo")
    rlist.add_argument("--limit", type=int, default=20)
    rlist.add_argument("--json", action="store_true")
    rlist.set_defaults(func=release_group.cmd_release_list)

    rview = rel_sub.add_parser("view", help="View a release")
    rview.add_argument("repo", help="owner/repo")
    rview.add_argument("tag")
    rview.add_argument("--json", action="store_true")
    rview.set_defaults(func=release_group.cmd_release_view)

    rlatest = rel_sub.add_parser("latest", help="Show the latest release")
    rlatest.add_argument("repo", help="owner/repo")
    rlatest.add_argument("--json", action="store_true")
    rlatest.set_defaults(func=release_group.cmd_release_latest)

    rcreate = rel_sub.add_parser("create", help="Create a release")
    rcreate.add_argument("repo", help="owner/repo")
    rcreate.add_argument("tag")
    rcreate.add_argument("--title")
    rcreate.add_argument("--notes")
    rcreate.add_argument("--notes-file")
    rcreate.add_argument("--target")
    rcreate.add_argument("--draft", action="store_true")
    rcreate.add_argument("--prerelease", action="store_true")
    rcreate.add_argument("--generate-notes", action="store_true")
    rcreate.add_argument("--asset", action="append", dest="assets")
    rcreate.add_argument("--dry-run", action="store_true")
    rcreate.add_argument("--json", action="store_true")
    rcreate.set_defaults(func=release_group.cmd_release_create)

    redit = rel_sub.add_parser("edit", help="Edit a release")
    redit.add_argument("repo", help="owner/repo")
    redit.add_argument("tag")
    redit.add_argument("--title")
    redit.add_argument("--notes")
    redit.add_argument("--draft", action="store_true", default=None)
    redit.add_argument("--no-draft", dest="draft", action="store_false")
    redit.add_argument("--prerelease", action="store_true", default=None)
    redit.add_argument("--no-prerelease", dest="prerelease", action="store_false")
    redit.add_argument("--dry-run", action="store_true")
    redit.add_argument("--json", action="store_true")
    redit.set_defaults(func=release_group.cmd_release_edit)

    rpub = rel_sub.add_parser("publish", help="Publish a draft release")
    rpub.add_argument("repo", help="owner/repo")
    rpub.add_argument("tag")
    rpub.add_argument("--dry-run", action="store_true")
    rpub.add_argument("--json", action="store_true")
    rpub.set_defaults(func=release_group.cmd_release_publish)

    rdel = rel_sub.add_parser("delete", help="Delete a release")
    rdel.add_argument("repo", help="owner/repo")
    rdel.add_argument("tag")
    rdel.add_argument("--cleanup-tag", action="store_true")
    rdel.add_argument("--confirm", action="store_true")
    rdel.add_argument("--dry-run", action="store_true")
    rdel.add_argument("--json", action="store_true")
    rdel.set_defaults(func=release_group.cmd_release_delete)

    rup = rel_sub.add_parser("upload", help="Upload release assets")
    rup.add_argument("repo", help="owner/repo")
    rup.add_argument("tag")
    rup.add_argument("files", nargs="+")
    rup.add_argument("--dry-run", action="store_true")
    rup.add_argument("--json", action="store_true")
    rup.set_defaults(func=release_group.cmd_release_upload)

    rdl = rel_sub.add_parser("download", help="Download release assets")
    rdl.add_argument("repo", help="owner/repo")
    rdl.add_argument("tag")
    rdl.add_argument("--pattern")
    rdl.add_argument("--output-dir", default=".")
    rdl.add_argument("--dry-run", action="store_true")
    rdl.add_argument("--json", action="store_true")
    rdl.set_defaults(func=release_group.cmd_release_download)

    rnotes = rel_sub.add_parser("notes", help="Generate release notes between tags")
    rnotes.add_argument("repo", help="owner/repo")
    rnotes.add_argument("--since", required=True, help="Previous tag to compare from")
    rnotes.add_argument("--target", help="Branch or SHA (default: default branch)")
    rnotes.add_argument("--json", action="store_true")
    rnotes.set_defaults(func=release_group.cmd_release_notes)


def _build_api_parser(sub: Any) -> None:
    from .groups import api as api_group

    api_p = sub.add_parser("api", help="Raw GitHub REST API call")
    api_p.add_argument("method", choices=["GET", "POST", "PATCH", "PUT", "DELETE"])
    api_p.add_argument("path", help="API path, e.g. /rate_limit")
    api_p.add_argument("--field", action="append", dest="fields", metavar="K=V")
    api_p.add_argument("--raw-field", action="append", dest="raw_fields", metavar="K=V")
    api_p.add_argument("--header", action="append", dest="headers", metavar="K:V")
    api_p.add_argument("--paginate", action="store_true")
    api_p.add_argument("--jq", metavar="EXPR")
    api_p.add_argument("--json", action="store_true")
    api_p.set_defaults(func=api_group.cmd_api)

    gql_p = sub.add_parser("graphql", help="Raw GitHub GraphQL call")
    gql_p.add_argument("query", help="GraphQL query string or @file path")
    gql_p.add_argument("--field", action="append", dest="fields", metavar="K=V")
    gql_p.add_argument("--paginate", action="store_true")
    gql_p.add_argument("--jq", metavar="EXPR")
    gql_p.add_argument("--json", action="store_true")
    gql_p.set_defaults(func=api_group.cmd_graphql)


def _subcommand_help(parser: argparse.ArgumentParser, command: str | None) -> None:
    if not command:
        parser.print_help()


def show_help() -> None:
    print(
        """agent-gh - GitHub work-state for agent-do

PR commands (existing):
  whoami                         Show authenticated GitHub user
  repos [sync]                   List or sync accessible repositories
  inbox                          Show actionable PR work across repositories
  awaiting                       Show open PRs likely awaiting your review
  prs [query]                    Search pull requests
  pr <repo#num|url|num>          Show PR details
  diff <pr>                      Show PR diff
  threads <pr>                   Show unresolved PR review threads
  checks <pr>                    Show PR checks
  review <pr>                    Summarize a PR for review
  audit <pr> [--reply]           Audit a PR and generate fix-oriented review text
  approve / request-changes / comment / merge / ready / draft

Issue commands (new):
  issue list <owner/repo>        List issues
  issue view <owner/repo>#<num>  View an issue
  issue create <owner/repo>      Create an issue
  issue comment <owner/repo>#N   Comment on an issue
  issue close / reopen           Close or reopen an issue
  issue label / assign           Manage labels and assignees
  issue snapshot <owner/repo>    Bulk structured snapshot
  issue triage <owner/repo>#N    Deterministic triage with suggested labels

Release commands (new):
  release list <owner/repo>      List releases
  release view <owner/repo> <tag>
  release latest <owner/repo>    Show latest release
  release create / edit / publish / delete / upload / download / notes

API escape hatch (new):
  api GET /rate_limit            Raw REST API call
  graphql '<query>'              Raw GraphQL call

Examples:
  agent-do gh inbox
  agent-do gh issue list ovachiever/agent-do --state open
  agent-do gh issue triage ovachiever/agent-do#42
  agent-do gh release latest ovachiever/agent-do --json
  agent-do gh release create ovachiever/agent-do v1.2 --generate-notes
  agent-do gh api GET /rate_limit
  agent-do gh audit ovachiever/agent-do#3 --reply
"""
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 1 and argv[0] in {"help", "--help", "-h"}:
        show_help()
        return 0
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.func is None:
        parser.print_help()
        return 0
    try:
        args.func(args)
        return 0
    except GhError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
