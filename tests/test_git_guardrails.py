#!/usr/bin/env python3
"""Fixture-repo acceptance coverage for guarded agent-git operations."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_GIT = ROOT / "tools" / "agent-git"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def command(cwd: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = command(cwd, "git", *args)
    if check:
        require(result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result


def agent(cwd: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return command(cwd, str(AGENT_GIT), *args, env=env)


def init_repo(root: Path, name: str = "repo") -> Path:
    repo = root / name
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "agent-git-test@example.invalid")
    git(repo, "config", "user.name", "Agent Git Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-qm", "chore: initial")
    return repo


def json_payload(result: subprocess.CompletedProcess[str]) -> dict:
    require(result.stdout.strip(), f"expected JSON output: {result.stderr}")
    return json.loads(result.stdout)


def digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix().encode()
        digest.update(rel)
        if path.is_symlink():
            digest.update(os.readlink(path).encode())
        elif path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def test_commit_guards(root: Path, env: dict[str, str]) -> None:
    repo = init_repo(root, "commit-repo")
    (repo / "unstaged.txt").write_text("must remain unstaged\n", encoding="utf-8")
    empty = agent(repo, "commit", "fix: should refuse", env=env)
    require(empty.returncode != 0, "commit accepted an empty index")
    require("git add <paths>" in empty.stderr, f"commit refusal omitted ownership guidance: {empty.stderr}")
    require(git(repo, "diff", "--cached", "--quiet", check=False).returncode == 0, "commit staged files implicitly")

    planted = "sk-" + "fixture-only-abcdefghijklmnopqrstuvwxyz"
    assignment_name = "SERVICE_" + "TOKEN"
    (repo / "config.env").write_text(f"{assignment_name}={planted}\n", encoding="utf-8")
    git(repo, "add", "config.env")
    blocked = agent(repo, "commit", "fix: blocked fake secret", "--json", env=env)
    require(blocked.returncode != 0, "secret scan allowed a planted provider-shaped key")
    payload = json_payload(blocked)
    require(payload["blocked"] is True and payload["findings"], f"missing structured findings: {payload}")
    require(payload["findings"][0]["detector"] in {"token", "provider-key-shape"}, f"unnamed detector: {payload}")
    require(planted not in blocked.stdout + blocked.stderr, "secret scan printed the matched value")

    bypass = agent(repo, "commit", "fix: explicit fixture bypass", "--no-scan", env=env)
    require(bypass.returncode == 0, f"explicit scan bypass failed: {bypass.stderr or bypass.stdout}")
    require("WARNING" in bypass.stderr and "secret scan bypassed" in bypass.stderr, "bypass warning was not loud")
    events = Path(env["AGENT_DO_HOME"]) / "telemetry" / "events.jsonl"
    require(events.is_file() and "git_secret_scan_bypass" in events.read_text(encoding="utf-8"), "bypass was not logged")


def test_worktrees(root: Path, env: dict[str, str]) -> None:
    repo = init_repo(root, "worktree-repo")
    (repo / ".gitignore").write_text(".env*\nCLAUDE.local.md\ncustom.local\n", encoding="utf-8")
    (repo / ".agent-do").mkdir()
    (repo / ".agent-do" / "worktree-seed").write_text("custom.local\nREADME.md\n", encoding="utf-8")
    git(repo, "add", ".gitignore", ".agent-do/worktree-seed")
    git(repo, "commit", "-qm", "chore: seed policy")
    (repo / ".env.local").write_text("FIXTURE_ENV=present\n", encoding="utf-8")
    (repo / "CLAUDE.local.md").write_text("local instructions\n", encoding="utf-8")
    (repo / "custom.local").write_text("custom seed\n", encoding="utf-8")

    destination = root / "seeded-worktree"
    added = agent(repo, "worktree", "add", "seed-branch", "--path", str(destination), "--json", env=env)
    require(added.returncode == 0, f"worktree add failed: {added.stderr or added.stdout}")
    payload = json_payload(added)
    require({".env.local", "CLAUDE.local.md", "custom.local"} <= set(payload["seeded"]), f"seed report incomplete: {payload}")
    require((destination / ".env.local").read_text() == "FIXTURE_ENV=present\n", "env file was not seeded")
    require((destination / "README.md").read_text() == "base\n", "tracked target was overwritten by seed policy")

    (destination / ".env.local").write_text("do not overwrite\n", encoding="utf-8")
    duplicate = agent(repo, "worktree", "add", "seed-branch", "--path", str(destination), env=env)
    require(duplicate.returncode != 0, "worktree add accepted an existing destination")
    require((destination / ".env.local").read_text() == "do not overwrite\n", "existing seed target was overwritten")

    listed = json_payload(agent(repo, "worktree", "list", "--json", env=env))
    require(
        any(Path(item["path"]).resolve() == destination.resolve() for item in listed["worktrees"]),
        f"worktree list missed destination: {listed}",
    )
    removed = agent(repo, "worktree", "remove", str(destination), "--json", env=env)
    require(removed.returncode == 0 and not destination.exists(), f"worktree remove failed: {removed.stderr or removed.stdout}")

    no_seed_destination = root / "unseeded-worktree"
    no_seed = agent(
        repo,
        "worktree",
        "add",
        "unseeded-branch",
        "--path",
        str(no_seed_destination),
        "--no-seed",
        "--json",
        env=env,
    )
    require(no_seed.returncode == 0 and not (no_seed_destination / ".env.local").exists(), "--no-seed was ignored")
    require(agent(repo, "worktree", "remove", str(no_seed_destination), env=env).returncode == 0, "cleanup remove failed")


def test_snapshots_and_conflicts(root: Path, env: dict[str, str]) -> None:
    repo = init_repo(root, "snapshot-repo")
    (repo / "recover.txt").write_text("working copy\n", encoding="utf-8")
    git(repo, "add", "recover.txt")
    git(repo, "commit", "-qm", "feat: working version")

    absent = json_payload(agent(repo, "snap", "diff", "--json", env=env))
    require(absent["available"] is False, f"missing snapshot did not fail gracefully: {absent}")

    # Build an unreferenced snapshot commit without mutating the working tree.
    blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=repo,
        input="snapshot copy\n",
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    tree_input = f"100644 blob {blob}\trecover.txt\n"
    tree = subprocess.run(
        ["git", "mktree"], cwd=repo, input=tree_input, text=True, capture_output=True, check=True
    ).stdout.strip()
    snapshot_commit = subprocess.run(
        ["git", "commit-tree", tree, "-m", "snapshot"], cwd=repo, text=True, capture_output=True, check=True
    ).stdout.strip()
    git(repo, "update-ref", "refs/auto/main", snapshot_commit)

    listed = json_payload(agent(repo, "snap", "list", "--json", env=env))
    require(any(item["branch"] == "main" for item in listed["snapshots"]), f"snapshot list missed ref: {listed}")
    diffed = json_payload(agent(repo, "snap", "diff", "--json", env=env))
    require("recover.txt" in diffed["diff"], f"snapshot diff missed changed file: {diffed}")
    restored = json_payload(agent(repo, "snap", "restore", "recover.txt", "--json", env=env))
    recovered_path = Path(restored["path"])
    require(recovered_path.name == "recover.txt.recovered", f"restore default overwrote source: {restored}")
    require(recovered_path.read_text() == "snapshot copy\n", "snapshot restore wrote wrong content")
    require((repo / "recover.txt").read_text() == "working copy\n", "default snapshot restore changed working file")
    in_place = agent(repo, "snap", "restore", "recover.txt", "--in-place", "--json", env=env)
    require(in_place.returncode == 0, f"explicit in-place restore failed: {in_place.stderr or in_place.stdout}")
    require((repo / "recover.txt").read_text() == "snapshot copy\n", "--in-place did not restore the snapshot")

    conflict_repo = init_repo(root, "conflict-repo")
    (conflict_repo / "README.md").write_text("main\n", encoding="utf-8")
    git(conflict_repo, "add", "README.md")
    git(conflict_repo, "commit", "-qm", "feat: main change")
    git(conflict_repo, "checkout", "-qb", "other", "HEAD~1")
    (conflict_repo / "README.md").write_text("other\n", encoding="utf-8")
    git(conflict_repo, "add", "README.md")
    git(conflict_repo, "commit", "-qm", "feat: other change")
    git(conflict_repo, "checkout", "-q", "main")
    require(git(conflict_repo, "merge", "other", check=False).returncode != 0, "fixture merge did not conflict")
    conflicts = json_payload(agent(conflict_repo, "conflicts", "--json", env=env))
    require(conflicts["count"] == 1 and conflicts["files"][0]["markers"] >= 3, f"conflicts output wrong: {conflicts}")


def test_recover_read_only(root: Path, env: dict[str, str]) -> None:
    repo = init_repo(root, "recover-repo")
    tree = git(repo, "write-tree").stdout.strip()
    subprocess.run(
        ["git", "commit-tree", tree, "-m", "unreachable fixture"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )
    git_dir = repo / ".git"
    before = digest_tree(git_dir)
    recovered = agent(repo, "recover", "--json", env=env)
    require(recovered.returncode == 0, f"recover failed: {recovered.stderr or recovered.stdout}")
    payload = json_payload(recovered)
    require(payload["reflog"] and payload["unreachable_commits"], f"recover report incomplete: {payload}")
    require(not (git_dir / "lost-found").exists(), "recover used writing fsck mode")
    require(digest_tree(git_dir) == before, "recover changed .git contents")


def test_recover_outside_repo(root: Path, env: dict[str, str]) -> None:
    """Verify-beat contract: a refusal carries a clear reason.

    Regression for the nightly contracts audit, which probes verbs from a
    throwaway cwd: outside any repository `recover` used to print an empty
    but success-shaped report and exit 1 with no explanation.
    """
    outside = root / "not-a-repo"
    outside.mkdir()
    require(git(outside, "rev-parse", "--git-dir", check=False).returncode != 0, "fixture dir is unexpectedly inside a repo")

    bare = agent(outside, "recover", env=env)
    require(bare.returncode != 0, f"recover outside a repo exited 0: {bare.stdout}")
    require("not a git repository" in (bare.stderr + bare.stdout).lower(), f"recover outside a repo gave no reason: {bare.stderr!r} {bare.stdout!r}")
    require("Unreachable commits" not in bare.stdout, f"recover outside a repo printed a success-shaped report: {bare.stdout!r}")

    structured = agent(outside, "recover", "--json", env=env)
    require(structured.returncode != 0, f"recover --json outside a repo exited 0: {structured.stdout}")
    payload = json_payload(structured)
    require(payload.get("ok") is False and "not a git repository" in payload.get("error", ""), f"recover --json outside a repo lacks structured error: {payload}")


def test_sweep(root: Path, env: dict[str, str]) -> None:
    remote = root / "remote.git"
    git(root, "init", "-q", "--bare", str(remote))
    repo = init_repo(root, "sweep-repo")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-qu", "origin", "main")
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")

    for branch in ("merged-delete", "worktree-live", "unpushed", "unmerged-pushed"):
        git(repo, "branch", branch)
        git(repo, "push", "-qu", "-u", "origin", branch)
    git(repo, "branch", "no-upstream")

    git(repo, "checkout", "-q", "unpushed")
    (repo / "unpushed.txt").write_text("ahead\n", encoding="utf-8")
    git(repo, "add", "unpushed.txt")
    git(repo, "commit", "-qm", "feat: local only")
    git(repo, "checkout", "-q", "unmerged-pushed")
    (repo / "unmerged.txt").write_text("remote feature\n", encoding="utf-8")
    git(repo, "add", "unmerged.txt")
    git(repo, "commit", "-qm", "feat: pushed but unmerged")
    git(repo, "push", "-q")
    git(repo, "checkout", "-q", "main")

    worktree_path = root / "live-worktree"
    git(repo, "worktree", "add", "-q", str(worktree_path), "worktree-live")

    dry = json_payload(agent(repo, "sweep", "--json", env=env))
    require(dry["dry_run"] is True and "merged-delete" in dry["candidates"], f"dry-run missed candidate: {dry}")
    reasons = {item["branch"]: item["reason"] for item in dry["excluded"]}
    require(reasons.get("main") == "protected", f"main was not protected: {dry}")
    require(reasons.get("worktree-live") == "checked-out-worktree", f"worktree branch not protected: {dry}")
    require(reasons.get("no-upstream") == "no-upstream", f"no-upstream branch not protected: {dry}")
    require(reasons.get("unpushed") == "unpushed-commits", f"unpushed branch not protected: {dry}")
    require(reasons.get("unmerged-pushed") == "not-merged", f"unmerged branch not protected: {dry}")
    require(git(repo, "show-ref", "--verify", "refs/heads/merged-delete", check=False).returncode == 0, "dry-run deleted branch")

    applied = json_payload(agent(repo, "sweep", "--apply", "--json", env=env))
    require(applied["deleted"] == ["merged-delete"], f"sweep deleted wrong branches: {applied}")
    for branch in ("main", "worktree-live", "no-upstream", "unpushed", "unmerged-pushed"):
        require(git(repo, "show-ref", "--verify", f"refs/heads/{branch}", check=False).returncode == 0, f"sweep deleted protected {branch}")



def test_sweep_keeps_long_lived_branches(root: Path, env: dict[str, str]) -> None:
    """A fully pushed integration branch that main contains is 'merged' by ancestry,
    but it is a base branch, not finished work: sweep must never offer it."""
    remote = root / "remote-long-lived.git"
    git(root, "init", "-q", "--bare", str(remote))
    repo = init_repo(root, "sweep-long-lived")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-qu", "origin", "main")
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")

    built_in = ("staging", "develop", "development", "production", "trunk")
    configured = ("qa", "release/2026.10")
    # Look-alikes must stay sweepable: protection is exact names and full-name globs.
    look_alikes = ("staging-fix", "develop-docs", "hotfix-release")
    for branch in (*built_in, *configured, *look_alikes, "feature-done"):
        git(repo, "branch", branch)
        git(repo, "push", "-qu", "-u", "origin", branch)
    git(repo, "config", "--add", "agent-do.sweep.protect", "qa")
    git(repo, "config", "--add", "agent-do.sweep.protect", "release/*")

    dry = json_payload(agent(repo, "sweep", "--json", env=env))
    expected = sorted(["feature-done", *look_alikes])
    require(dry["candidates"] == expected, f"sweep candidates wrong (long-lived offered or look-alike over-protected): {dry}")
    reasons = {item["branch"]: item["reason"] for item in dry["excluded"]}
    for branch in (*built_in, *configured):
        require(reasons.get(branch) == "protected", f"{branch} not protected: {dry}")

    # Plain-text mode is what most agents read.
    text = agent(repo, "sweep", env=env)
    require(text.returncode == 0, f"text sweep failed: {text.stderr}")
    would = next((line for line in text.stdout.splitlines() if line.startswith("Would delete:")), "")
    offered = {item.strip() for item in would.split(":", 1)[-1].split(",")}
    require(offered == set(expected), f"text-mode candidates wrong: {text.stdout!r}")

    # The remote default is protected even when it is not a built-in name.
    git(repo, "branch", "integration")
    git(repo, "push", "-qu", "-u", "origin", "integration")
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/integration")
    by_default = json_payload(agent(repo, "sweep", "--json", env=env))
    default_reasons = {item["branch"]: item["reason"] for item in by_default["excluded"]}
    require(default_reasons.get("integration") == "protected", f"remote default not protected: {by_default}")
    require("integration" not in by_default["candidates"], f"remote default offered: {by_default}")
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")

    applied = json_payload(agent(repo, "sweep", "--apply", "--json", env=env))
    require(applied["deleted"] == sorted(["feature-done", "integration", *look_alikes]),
            f"sweep deleted wrong branches: {applied}")
    for branch in (*built_in, *configured):
        require(git(repo, "show-ref", "--verify", f"refs/heads/{branch}", check=False).returncode == 0,
                f"sweep deleted long-lived {branch}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_str:
        root = Path(tmp_str)
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(root / "agent-do-home")
        test_commit_guards(root, env)
        test_worktrees(root, env)
        test_snapshots_and_conflicts(root, env)
        test_recover_read_only(root, env)
        test_recover_outside_repo(root, env)
        test_sweep(root, env)
        test_sweep_keeps_long_lived_branches(root, env)

    print("git guardrail tests passed")


if __name__ == "__main__":
    main()
