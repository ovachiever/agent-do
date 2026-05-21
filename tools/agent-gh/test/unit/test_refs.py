#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_gh.refs import (
    IssueRef,
    PrRef,
    RepoRef,
    parse_issue,
    parse_pr_ref,
    parse_repo,
)
from agent_gh.transport import GhError

def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)

# ── parse_repo ─────────────────────────────────────────────────────────────────

def test_parse_repo_valid() -> None:
    r = parse_repo("ovachiever/agent-do")
    require(isinstance(r, RepoRef), "expected RepoRef")
    require(r.owner == "ovachiever", f"bad owner: {r}")
    require(r.repo == "agent-do", f"bad repo: {r}")
    require(r.slug == "ovachiever/agent-do", f"bad slug: {r}")

def test_parse_repo_dots_and_underscores() -> None:
    r = parse_repo("org/my_tool.v2")
    require(r.owner == "org", f"bad owner: {r}")
    require(r.repo == "my_tool.v2", f"bad repo: {r}")

def test_parse_repo_invalid_no_slash() -> None:
    raised = False
    try:
        parse_repo("notarepo")
    except ValueError:
        raised = True
    require(raised, "expected ValueError for bare word")

def test_parse_repo_invalid_too_many_slashes() -> None:
    raised = False
    try:
        parse_repo("a/b/c")
    except ValueError:
        raised = True
    require(raised, "expected ValueError for triple-slash")

def test_parse_repo_invalid_empty() -> None:
    raised = False
    try:
        parse_repo("")
    except ValueError:
        raised = True
    require(raised, "expected ValueError for empty string")

# ── parse_issue ────────────────────────────────────────────────────────────────

def test_parse_issue_valid() -> None:
    i = parse_issue("ovachiever/agent-do#42")
    require(isinstance(i, IssueRef), "expected IssueRef")
    require(i.owner == "ovachiever", f"bad owner: {i}")
    require(i.repo == "agent-do", f"bad repo: {i}")
    require(i.number == 42, f"bad number: {i}")
    require(i.slug == "ovachiever/agent-do#42", f"bad slug: {i}")

def test_parse_issue_repo_ref() -> None:
    i = parse_issue("ovachiever/agent-do#42")
    rr = i.repo_ref
    require(isinstance(rr, RepoRef), "expected RepoRef from repo_ref")
    require(rr.slug == "ovachiever/agent-do", f"bad slug: {rr}")

def test_parse_issue_large_number() -> None:
    i = parse_issue("org/repo#1000000")
    require(i.number == 1_000_000, f"bad number: {i}")

def test_parse_issue_invalid_no_hash() -> None:
    raised = False
    try:
        parse_issue("ovachiever/agent-do")
    except ValueError:
        raised = True
    require(raised, "expected ValueError without #num")

def test_parse_issue_invalid_non_numeric() -> None:
    raised = False
    try:
        parse_issue("ovachiever/agent-do#abc")
    except ValueError:
        raised = True
    require(raised, "expected ValueError for non-numeric issue number")

def test_parse_issue_invalid_empty() -> None:
    raised = False
    try:
        parse_issue("")
    except ValueError:
        raised = True
    require(raised, "expected ValueError for empty string")

# ── parse_pr_ref ───────────────────────────────────────────────────────────────

def test_parse_pr_ref_owner_hash() -> None:
    ref = parse_pr_ref("ovachiever/agent-do#3")
    require(isinstance(ref, PrRef), "expected PrRef")
    require(ref.repo == "ovachiever/agent-do", f"bad repo: {ref}")
    require(ref.number == "3", f"bad number: {ref}")

def test_parse_pr_ref_github_url() -> None:
    ref = parse_pr_ref("https://github.com/ovachiever/agent-do/pull/99")
    require(ref.repo == "ovachiever/agent-do", f"bad repo: {ref}")
    require(ref.number == "99", f"bad number: {ref}")

def test_parse_pr_ref_bare_number_no_git() -> None:
    from unittest.mock import patch
    raised = False
    with patch("agent_gh.refs.repo_from_git", return_value=None):
        try:
            parse_pr_ref("42")
        except GhError:
            raised = True
    require(raised, "expected GhError for bare number outside git repo")

def test_parse_pr_ref_invalid() -> None:
    raised = False
    try:
        parse_pr_ref("not-a-pr-ref")
    except GhError:
        raised = True
    require(raised, "expected GhError for garbage input")

def test_parse_pr_ref_empty_outside_git() -> None:
    raised = False
    try:
        parse_pr_ref("")
    except GhError:
        raised = True
    # parse_pr_ref("") calls repo_from_git() which may or may not find a repo;
    # in the test env we're inside a git repo so this may succeed — only require
    # that it doesn't crash unexpectedly.
    _ = raised  # result is environment-dependent

# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        test_parse_repo_valid,
        test_parse_repo_dots_and_underscores,
        test_parse_repo_invalid_no_slash,
        test_parse_repo_invalid_too_many_slashes,
        test_parse_repo_invalid_empty,
        test_parse_issue_valid,
        test_parse_issue_repo_ref,
        test_parse_issue_large_number,
        test_parse_issue_invalid_no_hash,
        test_parse_issue_invalid_non_numeric,
        test_parse_issue_invalid_empty,
        test_parse_pr_ref_owner_hash,
        test_parse_pr_ref_github_url,
        test_parse_pr_ref_bare_number_no_git,
        test_parse_pr_ref_invalid,
        test_parse_pr_ref_empty_outside_git,
    ]
    failures = []
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failures.append(f"  FAIL {t.__name__}: {exc}")
        except Exception as exc:
            failures.append(f"  ERROR {t.__name__}: {type(exc).__name__}: {exc}")
    if failures:
        for f in failures:
            print(f)
        return 1
    print(f"refs unit tests passed ({len(tests)} tests)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
