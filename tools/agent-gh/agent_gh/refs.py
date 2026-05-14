"""Reference parsing: PrRef, RepoRef, IssueRef."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from .transport import GhError


@dataclass(frozen=True)
class PrRef:
    repo: str | None
    number: str
    original: str


@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass(frozen=True)
class IssueRef:
    owner: str
    repo: str
    number: int

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}#{self.number}"

    @property
    def repo_ref(self) -> RepoRef:
        return RepoRef(self.owner, self.repo)


_REPO_RE = re.compile(r"^([A-Za-z0-9](?:[A-Za-z0-9-]{0,38})?)/([A-Za-z0-9._-]+)$")
_NUM_RE = re.compile(r"^([A-Za-z0-9](?:[A-Za-z0-9-]{0,38})?)/([A-Za-z0-9._-]+)#(\d+)$")


def repo_from_git() -> str | None:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    remote = result.stdout.strip()
    match = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?$", remote)
    if not match:
        return None
    return match.group(1)


def parse_pr_ref(raw: str | None) -> PrRef:
    value = (raw or "").strip()
    if not value:
        repo = repo_from_git()
        if not repo:
            raise GhError("PR reference required outside a GitHub-backed repo")
        return PrRef(repo=repo, number="", original="")

    url = re.search(r"github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)", value)
    if url:
        return PrRef(repo=url.group(1), number=url.group(2), original=value)

    owner_repo = re.fullmatch(r"([^/\s]+/[^#\s]+)#(\d+)", value)
    if owner_repo:
        return PrRef(repo=owner_repo.group(1), number=owner_repo.group(2), original=value)

    if re.fullmatch(r"\d+", value):
        repo = repo_from_git()
        if not repo:
            raise GhError("Bare PR number requires a GitHub-backed repo")
        return PrRef(repo=repo, number=value, original=value)

    raise GhError(f"Invalid PR reference: {value}")


def pr_gh_args(ref: PrRef) -> list[str]:
    args: list[str] = []
    if ref.number:
        args.append(ref.number)
    if ref.repo:
        args.extend(["--repo", ref.repo])
    return args


def parse_repo(s: str) -> RepoRef:
    m = _REPO_RE.match(s.strip())
    if not m:
        raise ValueError(f"Not a valid owner/repo: {s!r}")
    return RepoRef(m.group(1), m.group(2))


def parse_issue(s: str) -> IssueRef:
    m = _NUM_RE.match(s.strip())
    if not m:
        raise ValueError(f"Not a valid owner/repo#num: {s!r}")
    return IssueRef(m.group(1), m.group(2), int(m.group(3)))
