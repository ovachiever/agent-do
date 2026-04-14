from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LiveApprovalRequiredError(RuntimeError):
    required_scope: str
    rerun: str
    app: str | None = None
    reason: str | None = None
    tool: str | None = None
    source: str = "live"

    def __post_init__(self) -> None:
        message = f"Live local-control approval is required for scope '{self.required_scope}'"
        if self.app:
            message += f" on {self.app}"
        super().__init__(message)

    def payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "action_required": "LIVE_APPROVAL_REQUIRED",
            "required_scope": self.required_scope,
            "rerun": self.rerun,
            "source": self.source,
        }
        if self.app:
            payload["app"] = self.app
        if self.reason:
            payload["reason"] = self.reason
        if self.tool:
            payload["tool"] = self.tool
        return payload
