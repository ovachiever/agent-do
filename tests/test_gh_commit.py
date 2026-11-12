#!/usr/bin/env python3
"""Offline contract tests for `agent-do gh commit` correlation evidence."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("agent_gh_commit", str(ROOT / "tools" / "agent-gh"))
spec = importlib.util.spec_from_loader(loader.name, loader)
gh = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = gh
loader.exec_module(gh)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


COMMIT = {
    "sha": "a" * 40,
    "html_url": "https://github.example/o/r/commit/aaaa",
    "commit": {
        "message": "Deploy payments",
        "author": {"date": "2026-10-12T20:00:00Z"},
        "committer": {"date": "2026-10-12T20:01:00Z"},
    },
    "author": {"login": "author"},
    "committer": {"login": "committer"},
}
PR = {
    "number": 42,
    "html_url": "https://github.example/o/r/pull/42",
    "title": "Deploy payments",
    "state": "closed",
    "merged_at": "2026-10-12T20:02:00Z",
    "merge_commit_sha": "b" * 40,
    "head": {"sha": "a" * 40},
    "base": {"ref": "main"},
}
ISSUE_DATA = {
    "repository": {
        "pullRequest": {
            "closingIssuesReferences": {
                "totalCount": 1,
                "nodes": [{
                    "number": 7,
                    "title": "Release payments",
                    "url": "https://github.example/o/r/issues/7",
                    "state": "CLOSED",
                    "closedAt": "2026-10-12T20:02:00Z",
                    "repository": {"nameWithOwner": "o/r"},
                }],
            }
        }
    }
}


def test_exact_associations() -> None:
    with patch.object(gh, "gh_json", side_effect=[COMMIT, [PR]]) as api, \
            patch.object(gh, "run_graphql", return_value=ISSUE_DATA):
        result = gh.commit_correlation("o/r", "a" * 40)
    require(result["commit"]["sha"] == "a" * 40, f"commit lost: {result}")
    require(result["pull_requests"]["count"] == 1, f"PR count wrong: {result}")
    pr = result["pull_requests"]["items"][0]
    require(pr["merged_at"] == "2026-10-12T20:02:00Z" and pr["head_sha"] == "a" * 40,
            f"merge evidence wrong: {pr}")
    require(result["issues"]["status"] == "available", f"issues not available: {result}")
    require(result["issues"]["items"][0]["number"] == 7, f"issue missing: {result}")
    calls = api.call_args_list
    require("commits/" + "a" * 40 in calls[0].args[0][-1], f"commit endpoint wrong: {calls}")
    require(calls[1].args[0][-1].endswith("/pulls?per_page=100")
            and "--paginate" in calls[1].args[0] and "--slurp" in calls[1].args[0],
            f"associated PR endpoint is not fully paginated: {calls}")


def test_associated_pr_pages_are_flattened() -> None:
    other = {**PR, "number": 43}
    with patch.object(gh, "gh_json", side_effect=[COMMIT, [[PR], [other]]]), \
            patch.object(gh, "run_graphql", return_value=ISSUE_DATA):
        result = gh.commit_correlation("o/r", "a" * 40)
    require(result["pull_requests"]["count"] == 2,
            f"paginated associated PRs were lost: {result}")


def test_no_associated_pr_is_available_empty_evidence() -> None:
    with patch.object(gh, "gh_json", side_effect=[COMMIT, []]), \
            patch.object(gh, "run_graphql") as graphql:
        result = gh.commit_correlation("o/r", "a" * 40)
    require(result["pull_requests"] == {"status": "available", "items": [], "count": 0},
            f"empty PR association was not explicit: {result}")
    require(result["issues"]["status"] == "available" and result["issues"]["count"] == 0,
            f"empty issues were not explicit: {result}")
    graphql.assert_not_called()


def test_issue_links_degrade_without_hiding_pr_evidence() -> None:
    with patch.object(gh, "gh_json", side_effect=[COMMIT, [PR]]), \
            patch.object(gh, "run_graphql", side_effect=gh.GhError("forbidden")):
        result = gh.commit_correlation("o/r", "a" * 40)
    require(result["pull_requests"]["count"] == 1, f"PR evidence vanished: {result}")
    require(result["issues"]["status"] == "degraded", f"issue access was not degraded: {result}")
    require("forbidden" not in result["issues"].get("reason", ""), f"raw provider error leaked: {result}")


def test_missing_graphql_issue_connection_is_degraded() -> None:
    for payload in ({"repository": None}, {"repository": {"pullRequest": None}},
                    {"repository": {"pullRequest": {"closingIssuesReferences": None}}}):
        with patch.object(gh, "gh_json", side_effect=[COMMIT, [PR]]), \
                patch.object(gh, "run_graphql", return_value=payload):
            result = gh.commit_correlation("o/r", "a" * 40)
        require(result["pull_requests"]["count"] == 1, f"PR evidence vanished: {result}")
        require(result["issues"]["status"] == "degraded", f"missing data reported as empty: {result}")


def test_bad_sha_and_json_error_are_structured() -> None:
    try:
        gh.commit_correlation("o/r", "not-a-sha")
    except gh.GhError as error:
        require("Commit SHA" in str(error), f"wrong SHA error: {error}")
    else:
        raise AssertionError("invalid SHA was accepted")

    stream = StringIO()
    with patch.object(gh, "commit_correlation", side_effect=gh.GhError("GitHub denied access")), redirect_stdout(stream):
        rc = gh.main(["commit", "a" * 40, "--repo", "o/r", "--json"])
    payload = json.loads(stream.getvalue())
    require(rc == 1 and payload == {"success": False, "error": "GitHub denied access", "code": 1},
            f"JSON error shape wrong: rc={rc} {payload}")


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"{len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
