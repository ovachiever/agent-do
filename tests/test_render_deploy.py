#!/usr/bin/env python3
"""agent-render deploy: report only deploys that exist.

Runs the real cmd_deploy with render_request_checked stubbed. Modes follow
Render's create-deploy spec: 201 with a deploy record, 202 Queued with no
body, and an error status (the stub returns 1 and prints to stderr, as the
real helper does).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA = "0123456789abcdef0123456789abcdef01234567"


def run(args: str, mode: str, tmp: Path, kind: str = "web_service", render_json: str = "0"):
    log = tmp / "calls.log"
    log.write_text("")
    svc = json.dumps({"id": "srv-x", "name": "svc", "type": kind})
    deploy = json.dumps({"id": "dep-abc", "status": "created", "commit": {"id": SHA}, "createdAt": "2026-10-06T21:00:00Z"})
    script = f"""
set -euo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
resolve_service() {{ echo "srv-x"; }}
render_request_checked() {{
  printf '%s %s %s\\n' "$1" "$2" "${{3:-}}" >> "{log}"
  case "$1" in
    GET) printf '%s' '{svc}' ;;
    POST)
      case "{mode}" in
        created) printf '%s' '{deploy}' ;;
        created-no-commit) printf '%s' '{{"id": "dep-def", "status": "created"}}' ;;
        queued) printf '' ;;
        bogus) printf '%s' '{{"message": "weird"}}' ;;
        refused) echo "Error: Render API POST /services/srv-x/deploys returned HTTP 400" >&2
                 echo '{{"id":"bad","message":"cannot deploy cron job service by commit reference ID"}}' >&2; return 1 ;;
      esac ;;
  esac
}}
RENDER_JSON={render_json}
cmd_deploy {args}
"""
    r = subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False)
    calls = [l for l in log.read_text().splitlines() if l]
    return r, calls


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)

        r, calls = run(f"svc --commit {SHA}", "created", tmp)
        require(r.returncode == 0 and "dep-abc" in r.stdout and SHA in r.stdout, f"created: {r.stdout} {r.stderr}")
        posts = [c for c in calls if c.startswith("POST")]
        require(len(posts) == 1 and json.loads(posts[0].split(" ", 2)[2]) == {"commitId": SHA}, f"body: {posts}")

        r, calls = run("svc", "created-no-commit", tmp)
        posts = [c for c in calls if c.startswith("POST")]
        require(r.returncode == 0 and "dep-def" in r.stdout and "branch head" in r.stdout, f"no commit: {r.stdout}")
        require(json.loads(posts[0].split(" ", 2)[2]) == {}, f"plain deploy body: {posts}")

        r, calls = run("svc --clear-cache", "created", tmp)
        posts = [c for c in calls if c.startswith("POST")]
        require(r.returncode == 0 and json.loads(posts[0].split(" ", 2)[2]) == {"clearCache": "clear"}, f"clear cache: {posts}")

        # 202 Queued with no body: success, said plainly
        r, _ = run("svc", "queued", tmp)
        require(r.returncode == 0 and "queued" in r.stdout.lower() and "deploys" in r.stdout, f"queued: {r.stdout} {r.stderr}")

        # refusal: Render's reason shown, no fake deploy, exit 1
        r, _ = run("svc", "refused", tmp)
        require(r.returncode == 1 and "HTTP 400" in r.stderr and "no deploy was created" in r.stderr.lower()
                and "Deploy ID" not in r.stdout, f"refused: rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

        # a 2xx reply that is neither a deploy nor empty: error, not success
        r, _ = run("svc", "bogus", tmp)
        require(r.returncode == 1 and "Deploy ID" not in r.stdout and "no deploy is confirmed" in r.stderr
                and "Traceback" not in r.stderr, f"bogus 2xx: rc={r.returncode} {r.stdout!r} {r.stderr!r}")

        # cron + --commit: refused before any POST; cron without --commit is fine
        r, calls = run(f"svc --commit {SHA}", "created", tmp, kind="cron_job")
        require(r.returncode == 2 and not any(c.startswith("POST") for c in calls) and "cron" in r.stderr.lower(),
                f"cron commit: rc={r.returncode} {calls} {r.stderr!r}")
        r, calls = run("svc", "created", tmp, kind="cron_job")
        require(r.returncode == 0 and any(c.startswith("POST") for c in calls), f"cron plain deploy refused: {r.stderr}")

        # bad input: nothing sent
        for bad in ("svc --commit nothex!", "svc --commit", "svc --bogus", "svc other", ""):
            r, calls = run(bad, "created", tmp)
            require(r.returncode == 2 and not calls, f"{bad!r}: rc={r.returncode} calls={calls}")

        # --json
        r, _ = run(f"svc --commit {SHA}", "created", tmp, render_json="1")
        require(r.returncode == 0 and json.loads(r.stdout)["id"] == "dep-abc", f"--json created: {r.stdout}")
        r, _ = run("svc", "queued", tmp, render_json="1")
        require(r.returncode == 0 and json.loads(r.stdout) == {"queued": True, "id": None}, f"--json queued: {r.stdout}")

    print("render deploy tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
