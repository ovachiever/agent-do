from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def agent_do_home() -> Path:
    return Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))


def live_dir() -> Path:
    path = agent_do_home() / "live"
    path.mkdir(parents=True, exist_ok=True)
    return path


def leases_file() -> Path:
    return live_dir() / "leases.json"


def _scope_allows(lease_scope: str, required_scope: str) -> bool:
    if lease_scope == "any" or lease_scope == required_scope:
        return True
    if lease_scope == "desktop" and required_scope == "browser":
        return True
    return False


def _app_allows(lease_app: str | None, required_app: str | None) -> bool:
    if not required_app:
        return True
    if not lease_app:
        return True
    return lease_app == required_app


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def load_leases() -> list[dict[str, Any]]:
    path = leases_file()
    if not path.exists():
        return []
    try:
        leases = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(leases, list):
        return []
    return [lease for lease in leases if isinstance(lease, dict)]


def save_leases(leases: list[dict[str, Any]]) -> None:
    leases_file().write_text(json.dumps(leases, indent=2), encoding="utf-8")


def prune_expired_leases() -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    changed = False
    current = now_utc()
    for lease in load_leases():
        expires_at = lease.get("expires_at")
        if not expires_at:
            active.append(lease)
            continue
        try:
            expiry = _parse_timestamp(str(expires_at))
        except Exception:
            changed = True
            continue
        if expiry > current:
            active.append(lease)
        else:
            changed = True
    if changed:
        save_leases(active)
    return active


def list_active_leases() -> list[dict[str, Any]]:
    return prune_expired_leases()


def activate_lease(context: dict[str, Any]) -> dict[str, Any] | None:
    ttl_seconds = int(context.get("ttl_seconds") or 0)
    if ttl_seconds <= 0:
        return None

    scope = str(context.get("scope") or "desktop")
    app = context.get("app")
    reason = context.get("reason")
    current = now_utc()
    expires_at = current + timedelta(seconds=ttl_seconds)
    leases = prune_expired_leases()

    existing = None
    for lease in leases:
        if lease.get("scope") == scope and lease.get("app") == app:
            existing = lease
            break

    if existing is None:
        existing = {
            "id": f"live-{uuid.uuid4().hex[:12]}",
            "scope": scope,
            "app": app,
            "reason": reason,
            "created_at": current.isoformat(),
            "source": "modifier",
        }
        leases.append(existing)

    existing["expires_at"] = expires_at.isoformat()
    existing["updated_at"] = current.isoformat()
    existing["ttl_seconds"] = ttl_seconds
    if reason:
        existing["reason"] = reason
    save_leases(leases)
    return existing


def find_matching_lease(required_scope: str, app: str | None = None) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for lease in prune_expired_leases():
        lease_scope = str(lease.get("scope") or "desktop")
        lease_app = lease.get("app")
        if not _scope_allows(lease_scope, required_scope):
            continue
        if not _app_allows(lease_app, app):
            continue
        if best is None:
            best = lease
            continue
        if bool(best.get("app")) and not lease_app:
            best = lease
    return best
