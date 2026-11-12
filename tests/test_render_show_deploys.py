#!/usr/bin/env python3
"""agent-render show / deploys: honour --json, show the deploy-gating fields,
put the service URL before the repo link, print full commit ids."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SVC = json.dumps({
    "id": "srv-test", "name": "svc", "type": "web_service",
    "repo": "https://github.com/org/repo", "branch": "main",
    "rootDir": "apps/api", "autoDeploy": "yes", "autoDeployTrigger": "commit",
    "buildFilter": {"paths": ["apps/api/**", "package.json"], "ignoredPaths": ["docs/**"]},
    "suspended": "not_suspended", "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-02T00:00:00Z",
    "serviceDetails": {"url": "https://svc.onrender.com", "region": "oregon", "plan": "starter"},
})
DEPLOYS = json.dumps([
    {"deploy": {"id": "dep-1", "status": "live", "createdAt": "2026-01-02T00:00:00Z",
                "commit": {"id": "0123456789abcdef0123456789abcdef01234567", "message": "m"}}},
    {"deploy": {"id": "dep-0", "status": "deactivated", "createdAt": "2026-01-01T00:00:00Z", "commit": None}},
])


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(cmd: str, render_json: str = "0") -> subprocess.CompletedProcess[str]:
    script = f"""
set -uo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
resolve_service() {{ echo "srv-test"; }}
render_request() {{
  case "$2" in
    /services/srv-test) printf '%s' '{SVC}' ;;
    "/services/srv-test/deploys?limit=10") printf '%s' '{DEPLOYS}' ;;
    *) echo "unexpected endpoint: $2" >&2; return 1 ;;
  esac
}}
RENDER_JSON={render_json}
{cmd}
"""
    return subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    r = run("cmd_show svc")
    require(r.returncode == 0, f"show failed: {r.stderr}")
    out = r.stdout
    for needle in ("Root dir: apps/api", "Auto-deploy: yes (trigger: commit)",
                   "Build filter paths:   apps/api/**, package.json", "Build filter ignored: docs/**"):
        require(needle in out, f"show missing {needle!r}: {out}")
    require(out.index("https://svc.onrender.com") < out.index("https://github.com/org/repo"),
            f"service URL must precede repo URL: {out}")

    r = run("cmd_show svc", render_json="1")
    require(r.returncode == 0, f"show --json failed: {r.stderr}")
    require(json.loads(r.stdout)["id"] == "srv-test", f"show --json not raw JSON: {r.stdout}")

    r = run("cmd_deploys svc")
    require(r.returncode == 0, f"deploys failed: {r.stderr}")
    require("commit:0123456789abcdef0123456789abcdef01234567" in r.stdout, f"full commit id missing: {r.stdout}")
    require("dep-0  deactivated  commit:?" in r.stdout, f"null commit not handled: {r.stdout}")

    r = run("cmd_deploys svc", render_json="1")
    require(r.returncode == 0, f"deploys --json failed: {r.stderr}")
    require(len(json.loads(r.stdout)) == 2, f"deploys --json not raw list: {r.stdout}")

    print("render show/deploys tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
