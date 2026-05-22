from __future__ import annotations

from typing import Any

from ..refs import parse_repo
from ..snapshot import envelope
from ..transport import gh_json

_SECTION_LABELS: list[tuple[str, list[str]]] = [
    ("Features", ["enhancement", "feature", "feat"]),
    ("Bug Fixes", ["bug", "fix", "bugfix"]),
    ("Documentation", ["documentation", "docs"]),
    ("Maintenance", ["chore", "maintenance", "refactor", "deps", "dependencies"]),
]

def _tag_date(repo_slug: str, tag: str) -> str | None:
    try:
        ref_obj = gh_json(["api", f"/repos/{repo_slug}/git/ref/tags/{tag}"]) or {}
        obj = ref_obj.get("object") or {}
        obj_type = obj.get("type")
        sha = obj.get("sha", "")
        if not sha:
            return None
        if obj_type == "tag":
            tag_obj = gh_json(["api", f"/repos/{repo_slug}/git/tags/{sha}"]) or {}
            return (tag_obj.get("tagger") or {}).get("date")
        # lightweight tag — points directly to a commit
        commit_obj = gh_json(["api", f"/repos/{repo_slug}/git/commits/{sha}"]) or {}
        return (commit_obj.get("committer") or {}).get("date")
    except Exception:
        return None

def notes_between(repo: str, since_tag: str, *, target: str | None = None) -> dict[str, Any]:
    r = parse_repo(repo)

    # Use gh api to generate notes (GitHub's own notes generation endpoint)
    body: dict[str, Any] = {"tag_name": "__preview__", "previous_tag_name": since_tag}
    if target:
        body["target_commitish"] = target

    # Try GitHub's native generate-notes endpoint first
    try:
        payload = gh_json([
            "api", "--method", "POST",
            f"/repos/{r.slug}/releases/generate-notes",
            "--field", "tag_name=__preview__",
            "--field", f"previous_tag_name={since_tag}",  # since_tag is a variable
            *(["--field", f"target_commitish={target}"] if target else []),
        ])
        raw_body = (payload or {}).get("body", "")
        return envelope("release notes", ref=r.slug, data={
            "since": since_tag,
            "source": "github-generate-notes",
            "markdown": raw_body,
            "sections": {},
            "uncategorized": [],
        })
    except Exception as exc:
        # Fall back to PR label grouping below. generate-notes can fail legitimately
        # (repo too new for a tag, auth scope, network); we intentionally continue.
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).debug("generate-notes endpoint failed, using fallback: %s", exc)

    # Fallback: list merged PRs since the tag and group by label
    prs = gh_json([
        "search", "prs", "--repo", r.slug,
        "--state", "merged",
        "--base", target or "main",
        "--json", "number,title,labels,mergedAt,url",
        "--limit", "100",
    ]) or []

    tag_date = _tag_date(r.slug, since_tag)
    if tag_date:
        prs = [pr for pr in prs if (pr.get("mergedAt") or "") > tag_date]

    sections: dict[str, list[str]] = {name: [] for name, _ in _SECTION_LABELS}
    uncategorized: list[str] = []

    for pr in prs:
        labels = {(lbl.get("name") or "").lower() for lbl in pr.get("labels") or []}
        title = pr.get("title") or ""
        number = pr.get("number")
        url = pr.get("url") or ""
        entry = f"{title} (#{number})"

        matched = False
        for section_name, section_labels in _SECTION_LABELS:
            if labels & set(section_labels):
                sections[section_name].append(entry)
                matched = True
                break
        if not matched:
            uncategorized.append(entry)

    return envelope("release notes", ref=r.slug, data={
        "since": since_tag,
        "source": "pr-label-grouping",
        "sections": {k: v for k, v in sections.items() if v},
        "uncategorized": uncategorized,
    })
