from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from ..refs import PrRef, parse_pr_ref
from ..render import print_json, print_table
from ..transport import GhError, gh_json, run_gh
from .pr import pr_detail, pr_diff_text, pr_threads


def _run(
    cmd: list[str], *, cwd: str | None = None, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, text=True, capture_output=True, check=False, timeout=timeout
    )


def _claude_bin() -> str | None:
    configured = os.environ.get("AGENT_CLAUDE_BIN")
    if configured:
        return configured
    return shutil.which("claude")


def _git_bin() -> str:
    found = shutil.which("git")
    if not found:
        raise GhError("git not found in PATH")
    return found


def _current_github_user() -> str:
    try:
        data = gh_json(["api", "/user"])
        return (data or {}).get("login", "")
    except GhError:
        return ""


def _open_prs_for_author(author: str, limit: int) -> list[dict[str, Any]]:
    fields = "number,title,headRefName,baseRefName,url,headRepositoryOwner,headRepository"
    try:
        return gh_json([
            "search", "prs",
            "--author", author,
            "--state", "open",
            "--limit", str(limit),
            "--json", fields,
        ]) or []
    except GhError:
        return []


def _pr_repo_slug(pr: dict[str, Any]) -> str | None:
    owner = (pr.get("headRepositoryOwner") or {}).get("login", "")
    repo = (pr.get("headRepository") or {}).get("name", "")
    if owner and repo:
        return f"{owner}/{repo}"
    url = pr.get("url", "")
    parts = url.rstrip("/").split("/")
    if len(parts) >= 5 and parts[-2] == "pull":
        return f"{parts[-4]}/{parts[-3]}"
    return None


def _clone_branch(repo_slug: str, head_branch: str, workdir: str) -> str | None:
    clone_url = f"https://github.com/{repo_slug}.git"
    dest = os.path.join(workdir, repo_slug.replace("/", "_"))
    result = _run(
        [_git_bin(), "clone", "--depth", "50", "--branch", head_branch, clone_url, dest],
        timeout=120,
    )
    if result.returncode != 0:
        print(f"    clone failed: {result.stderr.strip()[:200]}", file=sys.stderr)
        return None
    return dest


def _get_head_sha(repo_dir: str) -> str:
    result = _run([_git_bin(), "rev-parse", "HEAD"], cwd=repo_dir)
    return result.stdout.strip() if result.returncode == 0 else ""


def _push_branch(repo_dir: str, head_branch: str) -> bool:
    result = _run([_git_bin(), "push", "origin", head_branch], cwd=repo_dir)
    if result.returncode != 0:
        print(f"    push failed: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def _post_pr_comment(repo_slug: str, pr_number: int, body: str) -> None:
    run_gh(["pr", "comment", str(pr_number), "--repo", repo_slug, "--body", body])


def _format_thread_summary(threads: list[dict[str, Any]]) -> str:
    lines = []
    for i, thread in enumerate(threads, 1):
        path = thread.get("path") or ""
        line = thread.get("line")
        first = (thread.get("comments") or [{}])[0]
        author = first.get("author") or "reviewer"
        body = (first.get("body") or "").replace("\n", " ")[:120]
        loc = f"{path}:{line}" if line else path
        lines.append(f"{i}. [{author}] {loc}: {body}")
    return "\n".join(lines)


def _format_threads_for_prompt(threads: list[dict[str, Any]]) -> str:
    parts = []
    for i, thread in enumerate(threads, 1):
        path = thread.get("path") or ""
        line = thread.get("line")
        loc = f"{path} line {line}" if line else path
        comment_lines = []
        for c in thread.get("comments") or []:
            author = c.get("author") or "reviewer"
            body = c.get("body") or ""
            comment_lines.append(f"  [{author}]: {body}")
        parts.append(f"Thread {i} — {loc}:\n" + "\n".join(comment_lines))
    return "\n\n".join(parts)


def _address_with_claude(
    repo_dir: str,
    threads: list[dict[str, Any]],
    pr: dict[str, Any],
    repo_slug: str,
    diff_text: str,
    claude_bin: str,
    verbose: bool,
    *,
    silent: bool = False,
) -> bool:
    pr_title = pr.get("title", "")
    head_branch = pr.get("headRefName", "")
    base_branch = pr.get("baseRefName", "main")
    pr_url = pr.get("url", "")
    thread_text = _format_threads_for_prompt(threads)
    diff_excerpt = diff_text[:4000] if diff_text else "(diff unavailable)"

    prompt = f"""You are addressing unresolved review comments on a pull request.

PR: {pr_title}
URL: {pr_url}
Branch: {head_branch}
Base branch: {base_branch}
Repository: {repo_slug}
Working directory: {repo_dir}

The following review threads are unresolved and need to be addressed:

{thread_text}

PR diff (first 4000 chars for context):
```diff
{diff_excerpt}
```

Instructions:
1. Read each file mentioned in the review threads using its full path in {repo_dir}
2. Understand what each reviewer is asking for
3. Make the changes needed to address each review comment
4. Stage all changed files with `git add`
5. Commit with message: "Address review feedback\\n\\n{_format_thread_summary(threads)}"
6. Do not push — the orchestrator will push after you finish

Address every thread. Work through them one at a time.
"""

    if verbose:
        print(f"    Invoking claude to address {len(threads)} thread(s)...")

    try:
        result = subprocess.run(
            [claude_bin, "--print", prompt],
            cwd=repo_dir,
            text=True,
            capture_output=silent,
            check=False,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"    claude invocation failed: {exc}", file=sys.stderr)
        return False

    if result.returncode != 0:
        print(f"    claude exited {result.returncode}", file=sys.stderr)
        return False

    return True


def _address_pr(ref: PrRef, threads: list[dict[str, Any]], args: Any, *, emit_json: bool = True) -> None:
    claude_bin = _claude_bin()
    if not claude_bin:
        raise GhError("claude CLI not found. Install Claude Code or set AGENT_CLAUDE_BIN.")

    detail = pr_detail(ref)
    head_branch = detail.get("head") or ""
    base_branch = detail.get("base") or "main"
    repo_slug = ref.repo or ""
    verbose = getattr(args, "verbose", False)
    json_mode = getattr(args, "json", False)

    if args.dry_run:
        if json_mode and emit_json:
            print_json({
                "pr": f"{repo_slug}#{ref.number}",
                "unresolved": len(threads),
                "dry_run": True,
                "would_address": [
                    {"path": t.get("path"), "line": t.get("line")}
                    for t in threads
                ],
            })
        elif not json_mode:
            print(f"[dry-run] would address {len(threads)} thread(s) on {repo_slug}#{ref.number}")
            print(f"[dry-run] would clone {head_branch}, invoke claude, push, post comment")
        return

    pr_dict = {
        "title": detail.get("title", ""),
        "headRefName": head_branch,
        "baseRefName": base_branch,
        "url": detail.get("url", ""),
    }

    try:
        diff_text = pr_diff_text(ref)
    except GhError:
        diff_text = ""

    with tempfile.TemporaryDirectory(prefix="agent-gh-cr-") as workdir:
        if not json_mode:
            print(f"  Cloning {repo_slug} branch {head_branch}...")
        repo_dir = _clone_branch(repo_slug, head_branch, workdir)
        if not repo_dir:
            raise GhError(f"Failed to clone {repo_slug} branch {head_branch}")

        pre_sha = _get_head_sha(repo_dir)

        ok = _address_with_claude(
            repo_dir, threads, pr_dict, repo_slug, diff_text, claude_bin, verbose,
            silent=json_mode,
        )
        if not ok:
            raise GhError("claude failed to address review comments")

        post_sha = _get_head_sha(repo_dir)

        if post_sha == pre_sha:
            if json_mode and emit_json:
                print_json({"pr": f"{repo_slug}#{ref.number}", "status": "no_changes", "sha": post_sha})
            elif not json_mode:
                print("  No changes committed by claude — threads may already be addressed")
            return

        if not json_mode:
            print(f"  Pushing branch {head_branch}...")
        if not _push_branch(repo_dir, head_branch):
            raise GhError("push failed after addressing review comments")

        comment_body = f"Review feedback addressed in {post_sha[:8]}.\n\n"
        comment_body += _format_thread_summary(threads)
        _post_pr_comment(repo_slug, int(ref.number), comment_body)

        if json_mode and emit_json:
            print_json({
                "pr": f"{repo_slug}#{ref.number}",
                "status": "addressed",
                "sha": post_sha,
                "threads_addressed": len(threads),
            })
        elif not json_mode:
            print(f"  ✓ addressed {len(threads)} thread(s), pushed, commented ({post_sha[:8]})")


# ── command handlers ───────────────────────────────────────────────────────────

def cmd_cr(args: Any) -> None:
    if args.pr:
        _cr_single(args)
    else:
        _cr_sweep(args)


def _cr_single(args: Any) -> None:
    ref = parse_pr_ref(args.pr)
    threads = pr_threads(ref, all_threads=False)
    json_mode = getattr(args, "json", False)

    if not threads:
        if json_mode:
            print_json({"pr": f"{ref.repo}#{ref.number}", "unresolved": 0, "status": "clean"})
        else:
            print(f"No unresolved threads on {ref.repo}#{ref.number}")
        return

    if not args.address:
        if json_mode:
            print_json({
                "pr": f"{ref.repo}#{ref.number}",
                "unresolved": len(threads),
                "threads": threads,
            })
        else:
            print(f"{len(threads)} unresolved thread(s) on {ref.repo}#{ref.number}:")
            rows = []
            for thread in threads:
                first = (thread.get("comments") or [{}])[0]
                rows.append({
                    "path": thread.get("path"),
                    "line": thread.get("line"),
                    "author": first.get("author"),
                    "body": (first.get("body") or "").replace("\n", " ")[:100],
                })
            print_table(rows, ["path", "line", "author", "body"])
        return

    _address_pr(ref, threads, args)


def _cr_sweep(args: Any) -> None:
    author = getattr(args, "author", None) or _current_github_user()
    if not author:
        print("Error: could not determine GitHub user. Use --author.", file=sys.stderr)
        sys.exit(1)

    limit = getattr(args, "limit", 50)
    prs = _open_prs_for_author(author, limit)

    json_mode = getattr(args, "json", False)

    if not prs:
        if json_mode:
            print_json({"author": author, "count": 0, "items": []})
        else:
            print(f"No open PRs for @{author}")
        return

    results: list[dict[str, Any]] = []

    for pr in prs:
        repo_slug = _pr_repo_slug(pr)
        number = pr.get("number")
        title = pr.get("title", "")
        url = pr.get("url", "")
        label = f"#{number} {title[:60]}"

        if not repo_slug:
            results.append({"pr": number, "title": title, "status": "skipped", "reason": "no repo"})
            if not json_mode:
                print(f"  {label}  — skipped (no repo)")
            continue

        ref = PrRef(repo=repo_slug, number=str(number), original=f"{repo_slug}#{number}")
        try:
            threads = pr_threads(ref, all_threads=False)
        except GhError as exc:
            results.append({"pr": number, "title": title, "status": "error", "reason": str(exc)})
            if not json_mode:
                print(f"  {label}  — error fetching threads: {exc}", file=sys.stderr)
            continue

        if not threads:
            results.append({"pr": number, "title": title, "unresolved": 0, "status": "clean"})
            if not json_mode:
                print(f"  {label}  — clean")
            continue

        result: dict[str, Any] = {
            "pr": number,
            "title": title,
            "unresolved": len(threads),
            "url": url,
        }
        if not json_mode:
            print(f"  {label}  — {len(threads)} unresolved thread(s)")

        if args.address:
            if args.dry_run:
                result["status"] = "dry-run"
                if not json_mode:
                    print(f"    [dry-run] would address {len(threads)} thread(s)")
            else:
                try:
                    _address_pr(ref, threads, args, emit_json=False)
                    result["status"] = "addressed"
                except GhError as exc:
                    print(f"    ✗ {exc}", file=sys.stderr)
                    result["status"] = "error"
                    result["reason"] = str(exc)
        else:
            result["status"] = "pending"

        results.append(result)

    if json_mode:
        print_json({"author": author, "count": len(results), "items": results})
    else:
        has_unresolved = sum(1 for r in results if r.get("unresolved", 0) > 0)
        clean = sum(1 for r in results if r.get("status") == "clean")
        print(f"\n{len(results)} PR(s): {has_unresolved} with unresolved threads, {clean} clean")
