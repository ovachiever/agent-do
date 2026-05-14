"""Cache helpers for ~/.agent-do/gh/."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .snapshot import now_iso
from .transport import GhError, gh_json


AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))
STATE_DIR = AGENT_DO_HOME / "gh"
REPOS_CACHE = STATE_DIR / "repos.json"
USER_CACHE = STATE_DIR / "user.json"


def _state_dir() -> Path:
    """Return the resolved state directory, re-reading env in case it changed."""
    home = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))
    return home / "gh"


def ensure_state_dir() -> Path:
    d = _state_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _repos_cache() -> Path:
    return _state_dir() / "repos.json"


def _user_cache() -> Path:
    return _state_dir() / "user.json"


def normalize_repo(item: dict[str, Any]) -> dict[str, Any]:
    owner = item.get("owner") or {}
    owner_login = owner.get("login") if isinstance(owner, dict) else None
    full_name = item.get("full_name") or item.get("nameWithOwner")
    if not full_name and owner_login and item.get("name"):
        full_name = f"{owner_login}/{item['name']}"
    return {
        "name": item.get("name"),
        "full_name": full_name,
        "owner": owner_login,
        "visibility": item.get("visibility") or ("private" if item.get("private") else "public"),
        "private": bool(item.get("private") or item.get("isPrivate")),
        "archived": bool(item.get("archived") or item.get("isArchived")),
        "default_branch": item.get("default_branch") or (item.get("defaultBranchRef") or {}).get("name"),
        "url": item.get("html_url") or item.get("url"),
        "pushed_at": item.get("pushed_at") or item.get("pushedAt"),
        "updated_at": item.get("updated_at") or item.get("updatedAt"),
    }


def fetch_repos(limit: int | None = None) -> list[dict[str, Any]]:
    args = [
        "api",
        "--paginate",
        "--slurp",
        "/user/repos?affiliation=owner,collaborator,organization_member&sort=updated&per_page=100",
    ]
    raw = gh_json(args)
    items: list[dict[str, Any]] = []
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        for page in raw:
            items.extend(page)
    elif isinstance(raw, list):
        items = raw
    repos = [normalize_repo(item) for item in items if isinstance(item, dict)]
    repos = [repo for repo in repos if repo.get("full_name")]
    if limit is not None:
        repos = repos[:limit]
    return repos


def write_repos_cache(repos: list[dict[str, Any]]) -> None:
    ensure_state_dir()
    _repos_cache().write_text(
        json.dumps({"synced_at": now_iso(), "count": len(repos), "repos": repos}, indent=2) + "\n"
    )


def read_repos_cache() -> dict[str, Any] | None:
    path = _repos_cache()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def current_user(*, refresh: bool = False) -> dict[str, Any]:
    ensure_state_dir()
    cache = _user_cache()
    if not refresh and cache.exists():
        try:
            return json.loads(cache.read_text())
        except json.JSONDecodeError:
            pass
    payload = gh_json(["api", "user"])
    user = {
        "login": payload.get("login", ""),
        "id": payload.get("id"),
        "name": payload.get("name"),
        "url": payload.get("html_url"),
        "synced_at": now_iso(),
    }
    cache.write_text(json.dumps(user, indent=2) + "\n")
    return user
