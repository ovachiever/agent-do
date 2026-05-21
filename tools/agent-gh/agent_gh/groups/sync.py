"""PR sync: keep your open PRs up to date with their base branch.

Clean PRs (no conflicts) are updated via the GitHub API (no local checkout).
Conflicted PRs are resolved locally using `claude --print` with full context,
then committed and pushed — using your existing Pro/Max subscription, no API
key required.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from ..transport import GhError, gh_json, run_gh


# ── helpers ────────────────────────────────────────────────────────────────────

def _run(cmd: list[str], *, cwd: str | None = None, input_text: str | None = None,
         timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, input=input_text,
        text=True, capture_output=True, check=False, timeout=timeout,
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
    """Return open PRs authored by the given GitHub login across all repos."""
    fields = "number,title,headRefName,baseRefName,url,headRepositoryOwner,headRepository,mergeStateStatus"
    try:
        results = gh_json([
            "search", "prs",
            "--author", author,
            "--state", "open",
            "--limit", str(limit),
            "--json", fields,
        ])
        return results or []
    except GhError:
        # Fall back: search without mergeStateStatus (older gh versions)
        try:
            fields_basic = "number,title,headRefName,baseRefName,url,headRepositoryOwner,headRepository"
            results = gh_json([
                "search", "prs",
                "--author", author,
                "--state", "open",
                "--limit", str(limit),
                "--json", fields_basic,
            ])
            return results or []
        except GhError:
            return []


def _pr_repo_slug(pr: dict[str, Any]) -> str | None:
    owner = (pr.get("headRepositoryOwner") or {}).get("login", "")
    repo = (pr.get("headRepository") or {}).get("name", "")
    if owner and repo:
        return f"{owner}/{repo}"
    # Parse from URL as fallback: https://github.com/owner/repo/pull/N
    url = pr.get("url", "")
    parts = url.rstrip("/").split("/")
    if len(parts) >= 5 and parts[-2] == "pull":
        return f"{parts[-4]}/{parts[-3]}"
    return None


def _try_api_update(repo_slug: str, pr_number: int, rebase: bool) -> bool:
    """Try GitHub API branch update. Returns True on success, False on conflict."""
    args = ["pr", "update-branch", str(pr_number), "--repo", repo_slug]
    if rebase:
        args.append("--rebase")
    try:
        run_gh(args)
        return True
    except GhError as exc:
        msg = str(exc).lower()
        if any(w in msg for w in ("conflict", "merge conflict", "cannot be merged", "not mergeable")):
            return False
        # Other errors (permissions, not behind base, already up to date) — not a conflict
        if any(w in msg for w in ("already up to date", "already up-to-date", "not behind")):
            return True
        # Re-raise unexpected errors
        raise


def _conflicted_files(repo_dir: str) -> list[str]:
    result = _run([_git_bin(), "diff", "--name-only", "--diff-filter=U"], cwd=repo_dir)
    return [f for f in result.stdout.splitlines() if f.strip()]


def _read_conflict_block(path: str) -> str:
    """Return the raw conflict markers section of a file (truncated for context)."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        # Find first conflict marker
        start = next((i for i, l in enumerate(lines) if l.startswith("<<<<<<<")), 0)
        chunk = lines[max(0, start - 5): start + 80]
        return "\n".join(chunk)
    except OSError:
        return "(could not read file)"


def _resolve_with_claude(
    repo_dir: str,
    conflicted: list[str],
    pr: dict[str, Any],
    repo_slug: str,
    claude_bin: str,
    verbose: bool,
) -> bool:
    """Invoke claude --print to resolve conflicts in-place. Returns True on success."""
    pr_title = pr.get("title", "")
    head_branch = pr.get("headRefName", "")
    base_branch = pr.get("baseRefName", "main")
    pr_url = pr.get("url", "")

    # Build conflict context for claude
    conflict_details = []
    for rel_path in conflicted:
        abs_path = os.path.join(repo_dir, rel_path)
        block = _read_conflict_block(abs_path)
        conflict_details.append(f"File: {rel_path}\n```\n{block}\n```")

    conflict_text = "\n\n".join(conflict_details)

    prompt = f"""You are resolving merge conflicts in a git repository.

PR: {pr_title}
URL: {pr_url}
Branch being updated: {head_branch}
Base branch: {base_branch}
Repository: {repo_slug}
Working directory: {repo_dir}

The following files have merge conflicts after merging the base branch:

{conflict_text}

Instructions:
1. Read each conflicted file in full using the path {repo_dir}/<filename>
2. Understand what both sides are trying to do
3. Resolve each conflict correctly — keep both changes when they don't logically conflict, choose the right side when they do
4. Write the resolved content back to each file (no conflict markers remaining)
5. Stage the resolved files with `git add`
6. Commit with message: "Merge origin/{base_branch} — resolve conflicts"
7. Do not push

Work through each file completely. The files are in: {repo_dir}
"""

    if verbose:
        print(f"    Invoking claude to resolve {len(conflicted)} conflict(s)...")

    try:
        result = subprocess.run(
            [claude_bin, "--print", prompt],
            cwd=repo_dir,
            text=True,
            capture_output=False,  # let claude output flow to terminal
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"    claude invocation failed: {exc}", file=sys.stderr)
        return False

    if result.returncode != 0:
        print(f"    claude exited {result.returncode}", file=sys.stderr)
        return False

    # Verify no conflict markers remain
    still_conflicted = _conflicted_files(repo_dir)
    if still_conflicted:
        print(f"    Conflicts still present after claude: {still_conflicted}", file=sys.stderr)
        return False

    return True


def _push_branch(repo_dir: str, head_branch: str) -> bool:
    result = _run([_git_bin(), "push", "origin", head_branch], cwd=repo_dir)
    if result.returncode != 0:
        print(f"    push failed: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def _clone_or_update(repo_slug: str, head_branch: str, workdir: str) -> str | None:
    """Clone repo into workdir and checkout head_branch. Returns path or None on failure."""
    clone_url = f"https://github.com/{repo_slug}.git"
    dest = os.path.join(workdir, repo_slug.replace("/", "_"))
    git = _git_bin()

    result = _run([git, "clone", "--depth", "50", "--branch", head_branch, clone_url, dest],
                  timeout=120)
    if result.returncode != 0:
        print(f"    clone failed: {result.stderr.strip()[:200]}", file=sys.stderr)
        return None
    return dest


def _merge_base_into_branch(repo_dir: str, base_branch: str) -> tuple[bool, bool]:
    """Fetch origin and merge base_branch into HEAD. Returns (success, had_conflicts)."""
    git = _git_bin()
    _run([git, "fetch", "origin"], cwd=repo_dir, timeout=60)
    result = _run([git, "merge", f"origin/{base_branch}", "--no-edit"], cwd=repo_dir)
    if result.returncode == 0:
        return True, False
    if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
        return False, True
    return False, False


# ── main command ───────────────────────────────────────────────────────────────

def cmd_sync(args: Any) -> None:
    author = args.author or _current_github_user()
    if not author:
        print("Error: could not determine GitHub user. Use --author.", file=sys.stderr)
        sys.exit(1)

    rebase = args.rebase
    dry_run = args.dry_run
    verbose = args.verbose
    limit = args.limit
    json_mode = args.json

    claude_bin = _claude_bin()
    if not claude_bin:
        print("Warning: claude CLI not found — conflicted PRs will be flagged but not auto-resolved.",
              file=sys.stderr)

    print(f"Syncing open PRs for @{author}...")

    prs = _open_prs_for_author(author, limit)
    if not prs:
        print("No open PRs found.")
        return

    results = []

    for pr in prs:
        number = pr.get("number")
        title = pr.get("title", "")
        head_branch = pr.get("headRefName", "")
        base_branch = pr.get("baseRefName", "main")
        url = pr.get("url", "")
        repo_slug = _pr_repo_slug(pr)

        label = f"#{number} {title[:60]}"
        print(f"\n  {label}")
        print(f"    {head_branch} → {base_branch}  ({repo_slug})")

        if not repo_slug:
            print("    skipped: could not determine repo", file=sys.stderr)
            results.append({"pr": number, "title": title, "status": "skipped", "reason": "no repo"})
            continue

        if dry_run:
            print("    [dry-run] would attempt update-branch via API")
            results.append({"pr": number, "title": title, "status": "dry-run"})
            continue

        # ── try clean API update first ─────────────────────────────────────────
        try:
            clean = _try_api_update(repo_slug, number, rebase)
        except GhError as exc:
            print(f"    API update error: {exc}", file=sys.stderr)
            results.append({"pr": number, "title": title, "status": "error", "reason": str(exc)})
            continue

        if clean:
            print("    ✓ updated via API (no conflicts)")
            results.append({"pr": number, "title": title, "status": "updated"})
            continue

        # ── conflicts — resolve locally with claude ────────────────────────────
        print("    conflicts detected — resolving locally...")

        if not claude_bin:
            print("    ✗ claude not available — manual resolution required")
            results.append({"pr": number, "title": title, "status": "conflict", "url": url})
            continue

        with tempfile.TemporaryDirectory(prefix="agent-gh-sync-") as workdir:
            repo_dir = _clone_or_update(repo_slug, head_branch, workdir)
            if not repo_dir:
                results.append({"pr": number, "title": title, "status": "error",
                                 "reason": "clone failed"})
                continue

            success, had_conflicts = _merge_base_into_branch(repo_dir, base_branch)
            if success:
                # Clean after clone+merge — just push
                if _push_branch(repo_dir, head_branch):
                    print("    ✓ merged and pushed (no conflicts after local merge)")
                    results.append({"pr": number, "title": title, "status": "updated"})
                else:
                    results.append({"pr": number, "title": title, "status": "error",
                                     "reason": "push failed"})
                continue

            if not had_conflicts:
                print("    ✗ merge failed (not a conflict — check branch state)", file=sys.stderr)
                results.append({"pr": number, "title": title, "status": "error",
                                 "reason": "merge failed unexpectedly"})
                continue

            conflicted = _conflicted_files(repo_dir)
            if not conflicted:
                conflicted = ["(unknown — check git status)"]

            print(f"    conflicted files: {', '.join(conflicted)}")

            resolved = _resolve_with_claude(repo_dir, conflicted, pr, repo_slug,
                                            claude_bin, verbose)
            if not resolved:
                print(f"    ✗ auto-resolution failed — resolve manually: {url}")
                results.append({"pr": number, "title": title, "status": "conflict",
                                 "url": url, "files": conflicted})
                continue

            if _push_branch(repo_dir, head_branch):
                print("    ✓ conflicts resolved by claude and pushed")
                results.append({"pr": number, "title": title, "status": "resolved",
                                 "files": conflicted})
            else:
                results.append({"pr": number, "title": title, "status": "error",
                                 "reason": "push after resolution failed"})

    # ── summary ────────────────────────────────────────────────────────────────
    updated  = sum(1 for r in results if r["status"] == "updated")
    resolved = sum(1 for r in results if r["status"] == "resolved")
    conflicts = sum(1 for r in results if r["status"] == "conflict")
    errors   = sum(1 for r in results if r["status"] == "error")
    skipped  = sum(1 for r in results if r["status"] in ("skipped", "dry-run"))

    print(f"\nDone: {updated} updated, {resolved} resolved, "
          f"{conflicts} need manual attention, {errors} errors, {skipped} skipped")

    if conflicts:
        print("\nRequires manual resolution:")
        for r in results:
            if r["status"] == "conflict":
                print(f"  {r['title'][:70]}  {r.get('url', '')}")

    if json_mode:
        import json as _json
        print(_json.dumps({"results": results}, indent=2))

    if conflicts or errors:
        sys.exit(1)
