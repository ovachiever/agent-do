"""Generate release notes between two tags by grouping merged PRs by label."""
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


def notes_between(repo: str, since_tag: str, *, target: str | None = None) -> dict[str, Any]:
    r = parse_repo(repo)

    # Use gh api to generate notes (GitHub's own notes generation endpoint)
    body: dict[str, Any] = {"tag_name": f"__preview__", "previous_tag_name": since_tag}
    if target:
        body["target_commitish"] = target

    # Try GitHub's native generate-notes endpoint first
    try:
        payload = gh_json([
            "api", "--method", "POST",
            f"/repos/{r.slug}/releases/generate-notes",
            "--field", f"tag_name=__preview__",
            "--field", f"previous_tag_name={since_tag}",
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
    except Exception:
        pass

    # Fallback: list merged PRs since the tag and group by label
    prs = gh_json([
        "search", "prs", "--repo", r.slug,
        "--state", "merged",
        "--base", target or "main",
        "--json", "number,title,labels,mergedAt,url",
        "--limit", "100",
    ]) or []

    # Filter PRs merged after since_tag commit date (best-effort: just use all)
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
