"""Release management commands."""
from __future__ import annotations

import argparse
from typing import Any

from ..refs import parse_repo
from ..render import print_json, print_table
from ..snapshot import envelope
from ..transport import GhError, gh_json, run_gh


_RELEASE_FIELDS = "tagName,name,isDraft,isPrerelease,createdAt,publishedAt,url,body,assets"


# ── core data functions ────────────────────────────────────────────────────────

def list_releases(repo: str, *, limit: int = 20) -> dict[str, Any]:
    """List releases for a repo, most recent first."""
    r = parse_repo(repo)
    data = gh_json(["release", "list", "--repo", r.slug, "--limit", str(limit),
                    "--json", "tagName,name,isDraft,isPrerelease,createdAt,publishedAt,url"])
    return envelope("release list", ref=r.slug, data={"releases": data or []})


def view_release(repo: str, tag: str) -> dict[str, Any]:
    """Fetch full details for a single release by tag."""
    r = parse_repo(repo)
    data = gh_json(["release", "view", tag, "--repo", r.slug, "--json", _RELEASE_FIELDS])
    return envelope("release view", ref=f"{r.slug}@{tag}", data=data or {})


def latest_release(repo: str) -> dict[str, Any]:
    """Return the most recent release for a repo."""
    r = parse_repo(repo)
    data = gh_json(["release", "list", "--repo", r.slug, "--limit", "1",
                    "--json", "tagName,name,isDraft,isPrerelease,createdAt,publishedAt,url"])
    releases = data or []
    latest = releases[0] if releases else {}
    return envelope("release latest", ref=r.slug, data=latest)


def create_release(repo: str, tag: str, *, title: str | None = None,
                   notes: str | None = None, notes_file: str | None = None,
                   target: str | None = None, draft: bool = False,
                   prerelease: bool = False, generate_notes: bool = False,
                   assets: list[str] | None = None) -> dict[str, Any]:
    """Create a GitHub release for a tag, returning an envelope with the release URL."""
    r = parse_repo(repo)
    args = ["release", "create", tag, "--repo", r.slug]
    if title:
        args += ["--title", title]
    if notes is not None:
        args += ["--notes", notes]
    elif notes_file:
        args += ["--notes-file", notes_file]
    if target:
        args += ["--target", target]
    if draft:
        args.append("--draft")
    if prerelease:
        args.append("--prerelease")
    if generate_notes:
        args.append("--generate-notes")
    for asset in assets or []:
        args.append(asset)
    out = run_gh(args).strip()
    url = out.splitlines()[-1] if out else None
    return envelope("release create", ref=f"{r.slug}@{tag}", data={"url": url, "tag": tag})


def edit_release(repo: str, tag: str, *, title: str | None = None,
                 notes: str | None = None, draft: bool | None = None,
                 prerelease: bool | None = None) -> dict[str, Any]:
    """Edit metadata on an existing release."""
    r = parse_repo(repo)
    args = ["release", "edit", tag, "--repo", r.slug]
    if title is not None:
        args += ["--title", title]
    if notes is not None:
        args += ["--notes", notes]
    if draft is True:
        args.append("--draft")
    elif draft is False:
        args.append("--draft=false")
    if prerelease is True:
        args.append("--prerelease")
    elif prerelease is False:
        args.append("--prerelease=false")
    run_gh(args)
    return envelope("release edit", ref=f"{r.slug}@{tag}", data={"tag": tag})


def publish_release(repo: str, tag: str) -> dict[str, Any]:
    """Publish a draft release by clearing the draft flag."""
    return edit_release(repo, tag, draft=False)


def delete_release(repo: str, tag: str, *, cleanup_tag: bool = False) -> dict[str, Any]:
    """Delete a release; also deletes the git tag when cleanup_tag=True."""
    r = parse_repo(repo)
    args = ["release", "delete", tag, "--repo", r.slug, "--yes"]
    if cleanup_tag:
        args.append("--cleanup-tag")
    run_gh(args)
    return envelope("release delete", ref=f"{r.slug}@{tag}", data={"deleted": True, "tag": tag})


def upload_assets(repo: str, tag: str, files: list[str]) -> dict[str, Any]:
    """Upload binary assets to an existing release."""
    r = parse_repo(repo)
    run_gh(["release", "upload", tag, "--repo", r.slug, *files])
    return envelope("release upload", ref=f"{r.slug}@{tag}", data={"files": files})


def download_assets(repo: str, tag: str, *, pattern: str | None = None,
                    output_dir: str = ".") -> dict[str, Any]:
    """Download release assets, optionally filtered by glob pattern."""
    r = parse_repo(repo)
    args = ["release", "download", tag, "--repo", r.slug, "--dir", output_dir]
    if pattern:
        args += ["--pattern", pattern]
    run_gh(args)
    return envelope("release download", ref=f"{r.slug}@{tag}", data={"output_dir": output_dir})


def generate_notes_between(repo: str, since_tag: str, *, target: str | None = None) -> dict[str, Any]:
    """Generate release notes between since_tag and HEAD (or target branch)."""
    from ..triage.release_notes import notes_between
    return notes_between(repo, since_tag, target=target)


# ── command handlers ───────────────────────────────────────────────────────────

def cmd_release_list(args: argparse.Namespace) -> None:
    result = list_releases(args.repo, limit=args.limit)
    if args.json:
        print_json(result)
    else:
        print_table(result["data"]["releases"],
                    ["tagName", "name", "isDraft", "isPrerelease", "publishedAt"])


def cmd_release_view(args: argparse.Namespace) -> None:
    result = view_release(args.repo, args.tag)
    if args.json:
        print_json(result)
    else:
        d = result["data"]
        print(f"{d.get('tagName')} — {d.get('name') or '(no title)'}")
        print(f"Draft: {d.get('isDraft')}  Pre-release: {d.get('isPrerelease')}  Published: {d.get('publishedAt')}")
        if d.get("body"):
            print()
            print(d["body"])


def cmd_release_latest(args: argparse.Namespace) -> None:
    result = latest_release(args.repo)
    if args.json:
        print_json(result)
    else:
        d = result["data"]
        if not d:
            print("No releases found.")
            return
        print(f"{d.get('tagName')} — {d.get('name') or '(no title)'}  Published: {d.get('publishedAt')}")


def cmd_release_create(args: argparse.Namespace) -> None:
    if args.dry_run:
        print(f"[dry-run] would create release {args.tag} in {args.repo}")
        return
    result = create_release(
        args.repo, args.tag,
        title=args.title,
        notes=args.notes,
        notes_file=args.notes_file,
        target=args.target,
        draft=args.draft,
        prerelease=args.prerelease,
        generate_notes=args.generate_notes,
        assets=args.assets,
    )
    if args.json:
        print_json(result)
    else:
        print(f"Created release {args.tag}: {result['data'].get('url')}")


def cmd_release_edit(args: argparse.Namespace) -> None:
    if args.dry_run:
        print(f"[dry-run] would edit release {args.tag} in {args.repo}")
        return
    result = edit_release(args.repo, args.tag, title=args.title, notes=args.notes,
                          draft=args.draft, prerelease=args.prerelease)
    if args.json:
        print_json(result)
    else:
        print(f"Updated release {args.tag}")


def cmd_release_publish(args: argparse.Namespace) -> None:
    if args.dry_run:
        print(f"[dry-run] would publish (un-draft) release {args.tag} in {args.repo}")
        return
    result = publish_release(args.repo, args.tag)
    if args.json:
        print_json(result)
    else:
        print(f"Published release {args.tag}")


def cmd_release_delete(args: argparse.Namespace) -> None:
    if not args.confirm and not args.dry_run:
        raise GhError("Release delete requires --confirm (or use --dry-run to preview)")
    if args.dry_run:
        print(f"[dry-run] would delete release {args.tag} in {args.repo}")
        return
    result = delete_release(args.repo, args.tag, cleanup_tag=args.cleanup_tag)
    if args.json:
        print_json(result)
    else:
        print(f"Deleted release {args.tag}")


def cmd_release_upload(args: argparse.Namespace) -> None:
    if args.dry_run:
        print(f"[dry-run] would upload {args.files} to {args.repo}@{args.tag}")
        return
    result = upload_assets(args.repo, args.tag, args.files)
    if args.json:
        print_json(result)
    else:
        print(f"Uploaded {len(args.files)} file(s) to {args.tag}")


def cmd_release_download(args: argparse.Namespace) -> None:
    if args.dry_run:
        print(f"[dry-run] would download assets from {args.repo}@{args.tag} to {args.output_dir}")
        return
    result = download_assets(args.repo, args.tag, pattern=args.pattern, output_dir=args.output_dir)
    if args.json:
        print_json(result)
    else:
        print(f"Downloaded assets to {result['data']['output_dir']}")


def cmd_release_notes(args: argparse.Namespace) -> None:
    result = generate_notes_between(args.repo, args.since, target=args.target)
    if args.json:
        print_json(result)
    else:
        d = result["data"]
        print(f"## Release notes: {args.repo} since {args.since}")
        print()
        for section, items in d.get("sections", {}).items():
            if items:
                print(f"### {section}")
                for item in items:
                    print(f"- {item}")
                print()
        if d.get("uncategorized"):
            print("### Other")
            for item in d["uncategorized"]:
                print(f"- {item}")
