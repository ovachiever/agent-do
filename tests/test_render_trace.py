#!/usr/bin/env python3
"""Offline tests for Render's read-only incident evidence command."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = json.dumps({"id": "srv-trace", "ownerId": "tea-1", "name": "api", "type": "web_service", "repo": "https://github.com/acme/api", "branch": "main", "rootDir": "apps/api", "autoDeploy": "yes", "autoDeployTrigger": "commit", "serviceDetails": {"url": "https://api.onrender.com"}})
DEPLOYS = json.dumps([{ "deploy": {"id": f"dep-{index}", "status": "live", "commit": {"id": "a" * 40}, "createdAt": "2026-10-12T00:00:00Z"}} for index in range(11)])
EVENTS = json.dumps([{ "event": {"timestamp": "2026-10-12T00:01:00Z", "type": "deploy_ended", "details": {"reason": "token=secret-value"}}} for _ in range(101)])
LOGS = json.dumps({"logs": [{"timestamp": "2026-10-12T00:02:00Z", "message": "password" + "=hunter2 Authorization: Bearer bearer-secret-value", "labels": [{"name": "level", "value": "token" + "=label-secret"}]}], "hasMore": True})


def run(*args: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as temp:
        fake = Path(temp) / "curl"
        fake.write_text(f'''#!/usr/bin/env python3
import pathlib, sys
a = sys.argv[1:]
out = pathlib.Path(a[a.index("-o") + 1])
url = next(value for value in a if value.startswith("https://api.render.com/"))
if url.endswith("/services/srv-trace"): body = {SERVICE!r}
elif "/deploys?limit=11" in url: body = {DEPLOYS!r}
elif "/events?limit=101" in url: body = {EVENTS!r}
elif "/logs?" in url: body = {LOGS!r}
else: raise SystemExit("unexpected URL: " + url)
out.write_text(body)
print("200", end="")
''')
        fake.chmod(0o755)
        env = os.environ | {"PATH": f"{temp}:{os.environ['PATH']}", "RENDER_API_KEY": "test"}
        return subprocess.run([str(ROOT / "tools/agent-render"), "trace", *args], cwd=ROOT, text=True, capture_output=True, env=env, check=False)


def main() -> int:
    result = run("srv-trace", "--since", "30m", "--max-log-bytes", "65536", "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["service"]["id"] == "srv-trace"
    assert payload["deploys"][0]["commit_sha"] == "a" * 40
    assert len(payload["deploys"]) == 10
    assert len(payload["events"]) == 100
    assert payload["truncated"]["deploys_more_available"] is True
    assert payload["truncated"]["events_more_available"] is True
    assert payload["truncated"]["logs_more_available"] is True
    rendered = json.dumps(payload)
    assert "secret-value" not in rendered and "hunter2" not in rendered and "label-secret" not in rendered
    assert "[REDACTED]" in rendered
    bad = run("srv-trace", "--since", "forever")
    assert bad.returncode == 2
    assert json.loads(bad.stdout)["error"].startswith("--since")
    print("render trace tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
