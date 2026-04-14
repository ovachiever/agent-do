from __future__ import annotations

import json
import os
import shlex
from typing import Any

from .errors import LiveApprovalRequiredError
from .lease import activate_lease, find_matching_lease
from .parser import build_live_modifier, parse_live_modifier


def _context_from_env() -> dict[str, Any] | None:
    raw_json = os.environ.get("AGENT_DO_LIVE_CONTEXT", "").strip()
    if raw_json:
        try:
            data = json.loads(raw_json)
            if isinstance(data, dict) and data.get("enabled"):
                return data
        except Exception:
            pass

    raw_spec = os.environ.get("AGENT_DO_LIVE_SPEC", "").strip()
    if raw_spec:
        return parse_live_modifier(raw_spec)
    return None


def build_rerun_hint(
    *,
    tool: str,
    argv: list[str],
    scope: str,
    app: str | None = None,
    reason: str | None = None,
) -> str:
    modifier = build_live_modifier(scope=scope, app=app, reason=reason)
    tool_parts = [tool, *argv]
    return "agent-do " + " ".join(
        [shlex.quote(modifier), *[shlex.quote(part) for part in tool_parts]]
    )


def require_live_control(
    *,
    scope: str,
    tool: str,
    argv: list[str],
    app: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    context = _context_from_env()
    if context and context.get("enabled"):
        resolved = dict(context)
        resolved["scope"] = str(resolved.get("scope") or scope)
        if app and not resolved.get("app"):
            resolved["app"] = app
        if reason and not resolved.get("reason"):
            resolved["reason"] = reason
        lease = activate_lease(resolved)
        payload: dict[str, Any] = {
            "approved": True,
            "source": "modifier",
            "scope": resolved["scope"],
            "app": resolved.get("app"),
            "reason": resolved.get("reason"),
        }
        if lease:
            payload["lease"] = lease
        return payload

    lease = find_matching_lease(scope, app=app)
    if lease:
        return {
            "approved": True,
            "source": "lease",
            "scope": lease.get("scope"),
            "app": lease.get("app"),
            "reason": lease.get("reason"),
            "lease": lease,
        }

    raise LiveApprovalRequiredError(
        required_scope=scope,
        app=app,
        reason=reason,
        tool=tool,
        rerun=build_rerun_hint(tool=tool, argv=argv, scope=scope, app=app, reason=reason),
    )
