#!/usr/bin/env python3
"""Tests for agent-gh cr (code-review responder) command."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"

# ── thread fixtures ────────────────────────────────────────────────────────────

THREADS_2 = [
    {
        "id": "T_aaa",
        "isResolved": False,
        "path": "src/main.py",
        "line": 42,
        "comments": {"nodes": [
            {"id": "C_1", "body": "This function is too long, please split it.",
             "createdAt": "2026-05-20T10:00:00Z",
             "url": "https://github.com/owner/repo/pull/7#r1",
             "author": {"login": "coderabbitai"}},
        ]},
    },
    {
        "id": "T_bbb",
        "isResolved": False,
        "path": "src/utils.py",
        "line": 10,
        "comments": {"nodes": [
            {"id": "C_2", "body": "Missing type annotation here.",
             "createdAt": "2026-05-20T11:00:00Z",
             "url": "https://github.com/owner/repo/pull/7#r2",
             "author": {"login": "erik"}},
        ]},
    },
]

THREADS_1 = [THREADS_2[0]]

GQL_THREADS_2 = {
    "data": {
        "repository": {
            "pullRequest": {
                "reviewThreads": {"nodes": THREADS_2}
            }
        }
    }
}

GQL_THREADS_CLEAN = {
    "data": {
        "repository": {
            "pullRequest": {
                "reviewThreads": {"nodes": []}
            }
        }
    }
}

PR_VIEW_7 = {
    "number": 7,
    "title": "Add new feature",
    "state": "OPEN",
    "isDraft": False,
    "author": {"login": "ovachiever"},
    "baseRefName": "main",
    "headRefName": "feat/new-feature",
    "headRefOid": "abc123def456",
    "mergeable": "MERGEABLE",
    "mergeStateStatus": "CLEAN",
    "reviewDecision": "REVIEW_REQUIRED",
    "changedFiles": 3,
    "additions": 50,
    "deletions": 5,
    "url": "https://github.com/owner/repo/pull/7",
    "updatedAt": "2026-05-20T12:00:00Z",
    "createdAt": "2026-05-19T09:00:00Z",
    "assignees": [],
    "reviewRequests": [],
    "latestReviews": [],
    "labels": [],
    "files": [{"path": "src/main.py", "additions": 30, "deletions": 3}],
    "comments": [],
    "commits": [],
    "statusCheckRollup": [],
}

SEARCH_PR_7 = {
    "number": 7,
    "title": "Add new feature",
    "state": "open",
    "url": "https://github.com/owner/repo/pull/7",
    "headRepositoryOwner": {"login": "owner"},
    "headRepository": {"name": "repo"},
    "headRefName": "feat/new-feature",
    "baseRefName": "main",
}

# ── test helpers ───────────────────────────────────────────────────────────────

def make_exec(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, env=env, text=True, capture_output=True, check=False)


def base_env(fake_bin: Path, fake_home: Path) -> dict[str, str]:
    path = str(fake_bin) + os.pathsep + os.environ.get("PATH", "")
    return {
        **os.environ,
        "PATH": path,
        "AGENT_DO_HOME": str(fake_home),
        "HOME": str(fake_home),
    }


def make_fake_gh(
    fake_bin: Path,
    *,
    threads_payload: dict | None = None,
    pr_view: dict | None = None,
    search_prs: list | None = None,
    user_login: str = "ovachiever",
    comment_log: Path | None = None,
) -> None:
    threads_json = json.dumps(threads_payload or GQL_THREADS_2)
    pr_view_json = json.dumps(pr_view or PR_VIEW_7)
    search_json = json.dumps(search_prs if search_prs is not None else [SEARCH_PR_7])
    user_json = json.dumps({"login": user_login})
    comment_log_str = str(comment_log) if comment_log else ""

    make_exec(
        fake_bin / "gh",
        f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]

# api /user
if args[:2] in [["api", "/user"], ["api", "user"]]:
    print({user_json!r})
    sys.exit(0)

# graphql → review threads
if args[:2] == ["api", "graphql"]:
    print({threads_json!r})
    sys.exit(0)

# pr view
if args[:2] == ["pr", "view"]:
    print({pr_view_json!r})
    sys.exit(0)

# pr diff → return a fake diff
if args[:2] == ["pr", "diff"]:
    print("--- a/src/main.py")
    print("+++ b/src/main.py")
    print("@@ -40,5 +40,6 @@")
    print("+# added line")
    sys.exit(0)

# pr comment (reply after address)
if args[:2] == ["pr", "comment"]:
    log = {comment_log_str!r}
    if log:
        with open(log, "a") as f:
            f.write(json.dumps(args) + "\\n")
    sys.exit(0)

# search prs
if args[:2] == ["search", "prs"]:
    print({search_json!r})
    sys.exit(0)

# repo clone — create the dest directory so git rev-parse can run there
if args[:2] == ["repo", "clone"]:
    # args: repo clone <repo> <dest> -- --branch <branch> --depth 50
    dest = args[3] if len(args) > 3 else args[2]
    os.makedirs(dest, exist_ok=True)
    sys.exit(0)

sys.exit(0)
""",
    )


def make_fake_git(
    fake_bin: Path,
    *,
    sha_counter_path: Path,
    push_ok: bool = True,
) -> None:
    make_exec(
        fake_bin / "git",
        f"""#!/usr/bin/env python3
import sys
from pathlib import Path

args = sys.argv[1:]
counter_path = Path({str(sha_counter_path)!r})
push_ok = {push_ok!r}

if args[:2] == ["rev-parse", "HEAD"]:
    count = int(counter_path.read_text().strip()) if counter_path.exists() else 0
    counter_path.write_text(str(count + 1))
    # Return different SHAs on first vs subsequent calls so pre != post
    if count == 0:
        print("aaaaabbbbbccccc1111111111")
    else:
        print("dddddeeeeeffffff22222222")
    sys.exit(0)

if args[0] == "push":
    if not push_ok:
        print("error: push failed", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)

sys.exit(0)
""",
    )


def make_fake_claude(fake_bin: Path, *, exit_code: int = 0) -> None:
    make_exec(
        fake_bin / "claude",
        f"""#!/usr/bin/env python3
import sys
args = sys.argv[1:]
# --print mode used by cr
if args and args[0] == "--print":
    print("Addressed all review comments.")
    sys.exit({exit_code})
sys.exit({exit_code})
""",
    )


# ── tests ──────────────────────────────────────────────────────────────────────

def test_cr_list_shows_threads() -> None:
    """cr <pr> without --address prints unresolved thread table."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        make_fake_gh(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run([str(AGENT_DO), "gh", "cr", "owner/repo#7"], env=env)

        assert result.returncode == 0, result.stderr
        assert "unresolved thread" in result.stdout
        assert "src/main.py" in result.stdout
        assert "coderabbitai" in result.stdout


def test_cr_list_clean_pr() -> None:
    """cr <pr> on a PR with no unresolved threads reports clean."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        make_fake_gh(fake_bin, threads_payload=GQL_THREADS_CLEAN)

        env = base_env(fake_bin, fake_home)
        result = run([str(AGENT_DO), "gh", "cr", "owner/repo#7"], env=env)

        assert result.returncode == 0, result.stderr
        assert "No unresolved" in result.stdout


def test_cr_list_json() -> None:
    """cr <pr> --json returns structured thread data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        make_fake_gh(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run([str(AGENT_DO), "gh", "cr", "owner/repo#7", "--json"], env=env)

        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["unresolved"] == 2
        assert "threads" in data
        assert data["pr"] == "owner/repo#7"


def test_cr_list_json_clean() -> None:
    """cr <pr> --json on clean PR returns status clean."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        make_fake_gh(fake_bin, threads_payload=GQL_THREADS_CLEAN)

        env = base_env(fake_bin, fake_home)
        result = run([str(AGENT_DO), "gh", "cr", "owner/repo#7", "--json"], env=env)

        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["status"] == "clean"
        assert data["unresolved"] == 0


def test_cr_dry_run_no_address() -> None:
    """cr <pr> --address --dry-run prints dry-run message without git/claude."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        make_fake_gh(fake_bin)
        # Also need pr view for dry-run path
        sha_counter = tmp / "sha_counter.txt"
        make_fake_git(fake_bin, sha_counter_path=sha_counter)

        # Provide a fake claude too (but it shouldn't be called in dry-run)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address", "--dry-run"],
            env=env,
        )

        assert result.returncode == 0, result.stderr
        assert "dry-run" in result.stdout
        assert "2 thread" in result.stdout


def test_cr_dry_run_json() -> None:
    """cr <pr> --address --dry-run --json returns structured dry-run payload."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        make_fake_gh(fake_bin)
        sha_counter = tmp / "sha_counter.txt"
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address", "--dry-run", "--json"],
            env=env,
        )

        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["dry_run"] is True
        assert data["unresolved"] == 2
        assert len(data["would_address"]) == 2
        paths = [item["path"] for item in data["would_address"]]
        assert "src/main.py" in paths
        assert "src/utils.py" in paths


def test_cr_address_success() -> None:
    """cr <pr> --address clones, invokes claude, pushes, posts comment."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        comment_log = tmp / "comments.jsonl"
        sha_counter = tmp / "sha_counter.txt"

        make_fake_gh(fake_bin, comment_log=comment_log)
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address"],
            env=env,
        )

        assert result.returncode == 0, result.stderr
        assert "addressed" in result.stdout
        assert "pushed" in result.stdout
        # Comment was posted
        assert comment_log.exists()
        comment_calls = [json.loads(line) for line in comment_log.read_text().strip().splitlines()]
        assert any("pr" in call and "comment" in call for call in comment_calls)


def test_cr_address_json_output() -> None:
    """cr <pr> --address --json returns structured result with sha and count."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"

        make_fake_gh(fake_bin)
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address", "--json"],
            env=env,
        )

        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["status"] == "addressed"
        assert data["threads_addressed"] == 2
        assert "sha" in data
        assert len(data["sha"]) > 0


def test_cr_address_no_claude() -> None:
    """cr <pr> --address with no claude binary exits with error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"

        make_fake_gh(fake_bin)
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        # Point AGENT_CLAUDE_BIN to a nonexistent path — clone will succeed, claude will fail
        env = {
            **base_env(fake_bin, fake_home),
            "AGENT_CLAUDE_BIN": str(tmp / "no-such-claude"),
        }
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address"],
            env=env,
        )

        assert result.returncode != 0
        combined = (result.stderr + result.stdout).lower()
        assert "claude" in combined or "failed" in combined


def test_cr_address_clone_failure() -> None:
    """cr <pr> --address exits with error when gh repo clone fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"

        # Override gh to fail on repo clone
        pr_view_j = json.dumps(PR_VIEW_7)
        threads_j = json.dumps(GQL_THREADS_2)
        make_exec(
            fake_bin / "gh",
            f"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if args[:2] in [["api", "/user"], ["api", "user"]]:
    print('{{"login": "ovachiever"}}')
    sys.exit(0)
if args[:2] == ["api", "graphql"]:
    print({threads_j!r})
    sys.exit(0)
if args[:2] == ["pr", "view"]:
    print({pr_view_j!r})
    sys.exit(0)
if args[:2] == ["pr", "diff"]:
    print("diff --git")
    sys.exit(0)
if args[:2] == ["repo", "clone"]:
    print("fatal: repository not found", file=sys.stderr)
    sys.exit(128)
sys.exit(0)
""",
        )
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address"],
            env=env,
        )

        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "clone" in combined.lower() or "failed" in combined.lower()


def test_cr_address_push_failure() -> None:
    """cr <pr> --address exits with error when git push fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"

        make_fake_gh(fake_bin)
        make_fake_git(fake_bin, sha_counter_path=sha_counter, push_ok=False)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address"],
            env=env,
        )

        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "push" in combined.lower() or "failed" in combined.lower()


def test_cr_address_claude_failure() -> None:
    """cr <pr> --address exits with error when claude exits non-zero."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"

        make_fake_gh(fake_bin)
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin, exit_code=1)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address"],
            env=env,
        )

        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "claude" in combined.lower() or "failed" in combined.lower()


def test_cr_address_no_changes() -> None:
    """cr <pr> --address reports no_changes when claude makes no commit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        make_fake_gh(fake_bin)
        make_fake_claude(fake_bin)

        # Git always returns the same SHA → pre == post → "no changes"
        # gh handles the clone; git only needs rev-parse
        make_exec(
            fake_bin / "git",
            """#!/usr/bin/env python3
import sys
args = sys.argv[1:]
if args[:2] == ["rev-parse", "HEAD"]:
    print("samesamesamesame1234567890")
    sys.exit(0)
sys.exit(0)
""",
        )

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address"],
            env=env,
        )

        assert result.returncode == 0, result.stderr
        assert "no changes" in result.stdout.lower()


def test_cr_address_no_changes_json() -> None:
    """cr <pr> --address --json no_changes returns status no_changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        make_fake_gh(fake_bin)
        make_fake_claude(fake_bin)

        make_exec(
            fake_bin / "git",
            """#!/usr/bin/env python3
import sys
args = sys.argv[1:]
if args[:2] == ["rev-parse", "HEAD"]:
    print("samesamesamesame1234567890")
    sys.exit(0)
sys.exit(0)
""",
        )

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address", "--json"],
            env=env,
        )

        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["status"] == "no_changes"


def test_cr_sweep_no_prs() -> None:
    """cr with no open PRs reports empty sweep."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        make_fake_gh(fake_bin, search_prs=[])

        env = base_env(fake_bin, fake_home)
        result = run([str(AGENT_DO), "gh", "cr"], env=env)

        assert result.returncode == 0, result.stderr
        assert "No open PRs" in result.stdout


def test_cr_sweep_no_prs_json() -> None:
    """cr --json with no PRs returns count 0."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        make_fake_gh(fake_bin, search_prs=[])

        env = base_env(fake_bin, fake_home)
        result = run([str(AGENT_DO), "gh", "cr", "--json"], env=env)

        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["count"] == 0
        assert data["items"] == []


def test_cr_sweep_mixed() -> None:
    """cr sweep shows per-PR thread counts; clean and dirty PRs both reported."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        # Two PRs: #7 has threads, #8 is clean
        search_two = [
            SEARCH_PR_7,
            {
                "number": 8,
                "title": "Hotfix",
                "state": "open",
                "url": "https://github.com/owner/repo/pull/8",
                "headRepositoryOwner": {"login": "owner"},
                "headRepository": {"name": "repo"},
                "headRefName": "hotfix/typo",
                "baseRefName": "main",
            },
        ]

        # First graphql call → threads for #7; second → clean for #8
        call_counter = tmp / "gql_calls.txt"
        threads_2_json = json.dumps(GQL_THREADS_2)
        threads_clean_json = json.dumps(GQL_THREADS_CLEAN)
        search_two_json = json.dumps(search_two)

        make_exec(
            fake_bin / "gh",
            f"""#!/usr/bin/env python3
import json, sys
from pathlib import Path

args = sys.argv[1:]
counter = Path({str(call_counter)!r})

if args[:2] in [["api", "/user"], ["api", "user"]]:
    print('{{"login": "ovachiever"}}')
    sys.exit(0)

if args[:2] == ["api", "graphql"]:
    count = int(counter.read_text().strip()) if counter.exists() else 0
    counter.write_text(str(count + 1))
    if count == 0:
        print({threads_2_json!r})
    else:
        print({threads_clean_json!r})
    sys.exit(0)

if args[:2] == ["search", "prs"]:
    print({search_two_json!r})
    sys.exit(0)

if args[:2] == ["pr", "diff"]:
    print("--- /dev/null")
    sys.exit(0)

sys.exit(0)
""",
        )

        env = base_env(fake_bin, fake_home)
        result = run([str(AGENT_DO), "gh", "cr"], env=env)

        assert result.returncode == 0, result.stderr
        assert "2 unresolved thread" in result.stdout
        assert "clean" in result.stdout


def test_cr_sweep_json() -> None:
    """cr --json sweep returns author, count, and per-PR items."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        make_fake_gh(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run([str(AGENT_DO), "gh", "cr", "--json"], env=env)

        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert "author" in data
        assert "count" in data
        assert "items" in data
        assert data["count"] == 1
        item = data["items"][0]
        assert item["pr"] == 7
        assert item["unresolved"] == 2
        assert item["status"] == "pending"


def test_cr_sweep_address_dry_run() -> None:
    """cr --address --dry-run sweeps and shows dry-run per PR."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"

        make_fake_gh(fake_bin)
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "--address", "--dry-run"],
            env=env,
        )

        assert result.returncode == 0, result.stderr
        assert "dry-run" in result.stdout


def test_cr_sweep_address_json() -> None:
    """cr --address --json sweep returns addressed status with sha."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"

        make_fake_gh(fake_bin)
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "--address", "--json"],
            env=env,
        )

        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["count"] == 1
        item = data["items"][0]
        assert item["status"] == "addressed"


def test_cr_author_flag() -> None:
    """cr --author <login> uses the given author instead of authenticated user."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        args_log = tmp / "gh-args.jsonl"

        # Custom fake gh that logs the search args
        threads_clean_author = json.dumps(GQL_THREADS_CLEAN)
        make_exec(
            fake_bin / "gh",
            f"""#!/usr/bin/env python3
import json, sys
from pathlib import Path

args = sys.argv[1:]
log = Path({str(args_log)!r})

if args[:2] in [["api", "/user"], ["api", "user"]]:
    print('{{"login": "ovachiever"}}')
    sys.exit(0)

if args[:2] == ["api", "graphql"]:
    print({threads_clean_author!r})
    sys.exit(0)

if args[:2] == ["search", "prs"]:
    with log.open("a") as f:
        f.write(json.dumps(args) + "\\n")
    print("[]")
    sys.exit(0)

sys.exit(0)
""",
        )

        env = base_env(fake_bin, fake_home)
        result = run([str(AGENT_DO), "gh", "cr", "--author", "other-dev"], env=env)

        assert result.returncode == 0, result.stderr
        calls = [json.loads(l) for l in args_log.read_text().strip().splitlines()]
        assert any("other-dev" in call for call in calls)


def test_cr_limit_flag() -> None:
    """cr --limit passes through to search."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        args_log = tmp / "gh-args.jsonl"

        threads_clean_limit = json.dumps(GQL_THREADS_CLEAN)
        make_exec(
            fake_bin / "gh",
            f"""#!/usr/bin/env python3
import json, sys
from pathlib import Path

args = sys.argv[1:]
log = Path({str(args_log)!r})

if args[:2] in [["api", "/user"], ["api", "user"]]:
    print('{{"login": "ovachiever"}}')
    sys.exit(0)

if args[:2] == ["api", "graphql"]:
    print({threads_clean_limit!r})
    sys.exit(0)

if args[:2] == ["search", "prs"]:
    with log.open("a") as f:
        f.write(json.dumps(args) + "\\n")
    print("[]")
    sys.exit(0)

sys.exit(0)
""",
        )

        env = base_env(fake_bin, fake_home)
        result = run([str(AGENT_DO), "gh", "cr", "--limit", "5"], env=env)

        assert result.returncode == 0, result.stderr
        calls = [json.loads(l) for l in args_log.read_text().strip().splitlines()]
        assert any("5" in call for call in calls)


def test_cr_verbose_flag() -> None:
    """cr --address --verbose shows claude invocation message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"

        make_fake_gh(fake_bin)
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address", "--verbose"],
            env=env,
        )

        assert result.returncode == 0, result.stderr
        assert "claude" in (result.stdout + result.stderr).lower()


def test_cr_url_ref() -> None:
    """cr accepts a full GitHub PR URL as reference."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        make_fake_gh(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "https://github.com/owner/repo/pull/7"],
            env=env,
        )

        assert result.returncode == 0, result.stderr
        assert "unresolved thread" in result.stdout


def test_cr_help() -> None:
    """cr --help exits cleanly and mentions key flags."""
    result = subprocess.run(
        [str(AGENT_DO), "gh", "cr", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "--address" in combined
    assert "--dry-run" in combined


def test_cr_comment_body_contains_sha_and_threads() -> None:
    """The PR comment posted after address contains the short SHA and thread summaries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        comment_log = tmp / "comments.jsonl"
        sha_counter = tmp / "sha_counter.txt"

        make_fake_gh(fake_bin, comment_log=comment_log)
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address"],
            env=env,
        )

        assert result.returncode == 0, result.stderr
        calls = [json.loads(l) for l in comment_log.read_text().strip().splitlines()]
        comment_call = next((c for c in calls if c[:2] == ["pr", "comment"]), None)
        assert comment_call is not None, "No pr comment call logged"
        # Body is the last element (--body <body>)
        body_idx = comment_call.index("--body")
        body = comment_call[body_idx + 1]
        assert "addressed" in body.lower() or "review" in body.lower()
        assert "coderabbitai" in body or "erik" in body


def test_cr_sweep_error_fetching_threads() -> None:
    """cr sweep continues to next PR if thread fetch fails on one PR."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        search_two = [
            SEARCH_PR_7,
            {
                "number": 8,
                "title": "Another PR",
                "state": "open",
                "url": "https://github.com/owner/repo/pull/8",
                "headRepositoryOwner": {"login": "owner"},
                "headRepository": {"name": "repo"},
                "headRefName": "feat/other",
                "baseRefName": "main",
            },
        ]

        call_counter = tmp / "gql_calls.txt"
        threads_clean_j = json.dumps(GQL_THREADS_CLEAN)
        search_two_j = json.dumps(search_two)
        make_exec(
            fake_bin / "gh",
            f"""#!/usr/bin/env python3
import json, sys
from pathlib import Path

args = sys.argv[1:]
counter = Path({str(call_counter)!r})

if args[:2] in [["api", "/user"], ["api", "user"]]:
    print('{{"login": "ovachiever"}}')
    sys.exit(0)

if args[:2] == ["api", "graphql"]:
    count = int(counter.read_text().strip()) if counter.exists() else 0
    counter.write_text(str(count + 1))
    if count == 0:
        print("graphql error: something went wrong", file=sys.stderr)
        sys.exit(1)
    else:
        print({threads_clean_j!r})
    sys.exit(0)

if args[:2] == ["search", "prs"]:
    print({search_two_j!r})
    sys.exit(0)

sys.exit(0)
""",
        )

        env = base_env(fake_bin, fake_home)
        result = run([str(AGENT_DO), "gh", "cr"], env=env)

        # Should not crash — continues to second PR
        assert result.returncode == 0, result.stderr


def test_cr_address_closed_pr() -> None:
    """cr <pr> --address on a closed PR raises an error without cloning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"

        closed_view = {**PR_VIEW_7, "state": "CLOSED"}
        make_fake_gh(fake_bin, pr_view=closed_view)
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address"],
            env=env,
        )

        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "closed" in combined.lower() or "open" in combined.lower()


def test_cr_address_merged_pr() -> None:
    """cr <pr> --address on a merged PR raises an error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"

        merged_view = {**PR_VIEW_7, "state": "MERGED"}
        make_fake_gh(fake_bin, pr_view=merged_view)
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address"],
            env=env,
        )

        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "merged" in combined.lower() or "open" in combined.lower()


def test_cr_address_empty_head_branch() -> None:
    """cr <pr> --address on PR with no head branch raises a clean error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"

        no_head_view = {**PR_VIEW_7, "headRefName": ""}
        make_fake_gh(fake_bin, pr_view=no_head_view)
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address"],
            env=env,
        )

        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "head branch" in combined.lower() or "branch" in combined.lower()


def test_cr_comment_failure_does_not_fail_overall() -> None:
    """cr <pr> --address succeeds even if the reply comment post fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"

        # pr comment fails with permission error
        pr_view_j = json.dumps(PR_VIEW_7)
        threads_j = json.dumps(GQL_THREADS_2)
        make_exec(
            fake_bin / "gh",
            f"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if args[:2] in [["api", "/user"], ["api", "user"]]:
    print('{{"login": "ovachiever"}}')
    sys.exit(0)
if args[:2] == ["api", "graphql"]:
    print({threads_j!r})
    sys.exit(0)
if args[:2] == ["pr", "view"]:
    print({pr_view_j!r})
    sys.exit(0)
if args[:2] == ["pr", "diff"]:
    print("diff --git")
    sys.exit(0)
if args[:2] == ["pr", "comment"]:
    print("Error: permission denied", file=sys.stderr)
    sys.exit(1)
if args[:2] == ["repo", "clone"]:
    dest = args[3] if len(args) > 3 else args[2]
    os.makedirs(dest, exist_ok=True)
    sys.exit(0)
sys.exit(0)
""",
        )
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address"],
            env=env,
        )

        # Should succeed overall despite comment failure
        assert result.returncode == 0, result.stderr
        assert "addressed" in result.stdout
        # Warning about comment failure goes to stderr
        assert "warning" in (result.stdout + result.stderr).lower()


def test_cr_sweep_null_number_skipped() -> None:
    """cr sweep skips PRs with no number without crashing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()

        bad_pr = {
            "number": None,
            "title": "Bad PR",
            "state": "open",
            "url": "https://github.com/owner/repo/pull/0",
            "headRepositoryOwner": {"login": "owner"},
            "headRepository": {"name": "repo"},
            "headRefName": "feat/bad",
            "baseRefName": "main",
        }
        make_fake_gh(fake_bin, search_prs=[bad_pr])

        env = base_env(fake_bin, fake_home)
        result = run([str(AGENT_DO), "gh", "cr"], env=env)

        assert result.returncode == 0, result.stderr
        assert "skipped" in (result.stdout + result.stderr).lower()


def test_cr_sweep_address_includes_sha() -> None:
    """cr --address --json sweep result includes sha for each addressed PR."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"

        make_fake_gh(fake_bin)
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "--address", "--json"],
            env=env,
        )

        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        item = data["items"][0]
        assert item["status"] == "addressed"
        assert "sha" in item
        assert len(item["sha"]) > 0


def test_cr_address_uses_gh_clone() -> None:
    """cr --address uses gh repo clone (not git clone) for private-repo auth."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        fake_bin = tmp / "bin"
        fake_bin.mkdir()
        fake_home = tmp / "home"
        fake_home.mkdir()
        sha_counter = tmp / "sha_counter.txt"
        clone_log = tmp / "clone_log.txt"

        pr_view_j = json.dumps(PR_VIEW_7)
        threads_j = json.dumps(GQL_THREADS_2)
        make_exec(
            fake_bin / "gh",
            f"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
log = Path({str(clone_log)!r})
if args[:2] in [["api", "/user"], ["api", "user"]]:
    print('{{"login": "ovachiever"}}')
    sys.exit(0)
if args[:2] == ["api", "graphql"]:
    print({threads_j!r})
    sys.exit(0)
if args[:2] == ["pr", "view"]:
    print({pr_view_j!r})
    sys.exit(0)
if args[:2] == ["pr", "diff"]:
    print("diff --git")
    sys.exit(0)
if args[:2] == ["pr", "comment"]:
    sys.exit(0)
if args[:2] == ["repo", "clone"]:
    log.write_text(json.dumps(args))
    dest = args[3] if len(args) > 3 else args[2]
    os.makedirs(dest, exist_ok=True)
    sys.exit(0)
sys.exit(0)
""",
        )
        make_fake_git(fake_bin, sha_counter_path=sha_counter)
        make_fake_claude(fake_bin)

        env = base_env(fake_bin, fake_home)
        result = run(
            [str(AGENT_DO), "gh", "cr", "owner/repo#7", "--address"],
            env=env,
        )

        assert result.returncode == 0, result.stderr
        assert clone_log.exists(), "gh repo clone was not called"
        clone_args = json.loads(clone_log.read_text())
        assert clone_args[:2] == ["repo", "clone"]
        assert "owner/repo" in clone_args


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        test_cr_list_shows_threads,
        test_cr_list_clean_pr,
        test_cr_list_json,
        test_cr_list_json_clean,
        test_cr_dry_run_no_address,
        test_cr_dry_run_json,
        test_cr_address_success,
        test_cr_address_json_output,
        test_cr_address_no_claude,
        test_cr_address_clone_failure,
        test_cr_address_push_failure,
        test_cr_address_claude_failure,
        test_cr_address_no_changes,
        test_cr_address_no_changes_json,
        test_cr_sweep_no_prs,
        test_cr_sweep_no_prs_json,
        test_cr_sweep_mixed,
        test_cr_sweep_json,
        test_cr_sweep_address_dry_run,
        test_cr_sweep_address_json,
        test_cr_author_flag,
        test_cr_limit_flag,
        test_cr_verbose_flag,
        test_cr_url_ref,
        test_cr_help,
        test_cr_comment_body_contains_sha_and_threads,
        test_cr_sweep_error_fetching_threads,
        # QA edge cases
        test_cr_address_closed_pr,
        test_cr_address_merged_pr,
        test_cr_address_empty_head_branch,
        test_cr_comment_failure_does_not_fail_overall,
        test_cr_sweep_null_number_skipped,
        test_cr_sweep_address_includes_sha,
        test_cr_address_uses_gh_clone,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {test.__name__}: {exc}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
