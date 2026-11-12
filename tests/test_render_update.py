#!/usr/bin/env python3
"""agent-render update: new fields, type checks, read-back, buildFilter restore.

Runs the real cmd_update against a stubbed Render API that applies PATCH
bodies the way Render does — including the recorded quirk where a PATCH that
carries serviceDetails nulls buildFilter (Chat staging and prod, 2026-09-30).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILTER = {"paths": [], "ignoredPaths": ["backup/**"]}


def svc(kind: str, runtime: str = "node") -> dict:
    details: dict = {"runtime": runtime, "plan": "starter", "region": "oregon"}
    if runtime == "docker":
        details["envSpecificDetails"] = {"dockerCommand": "", "dockerContext": ".", "dockerfilePath": "./Dockerfile"}
    else:
        details["envSpecificDetails"] = {"buildCommand": "npm ci", "startCommand": "npm start"}
    if kind == "web_service":
        details["healthCheckPath"] = ""
    if kind == "cron_job":
        details["schedule"] = "0 9 * * *"
        details["lastSuccessfulRunAt"] = "2026-10-06T09:00:00Z"
    return {"id": "srv-test", "name": "test-svc", "type": kind, "branch": "main", "rootDir": "",
            "autoDeploy": "yes", "buildFilter": FILTER, "updatedAt": "2026-10-06T00:00:00Z", "serviceDetails": details}


STUB = r'''
import json, sys
mode, state_path, body = sys.argv[1], sys.argv[2], sys.argv[3]
s = json.load(open(state_path))
patch = json.loads(body)
def merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            merge(dst[k], v)
        else:
            dst[k] = v
if mode == "ignore-schedule" and "serviceDetails" in patch:
    patch["serviceDetails"].pop("schedule", None)
merge(s, patch)
if "serviceDetails" in patch and "buildFilter" not in patch:
    s["buildFilter"] = None          # the recorded Render quirk
if mode == "foreign-change":
    s["branch"] = "someone-else"
s["updatedAt"] = "2026-10-06T12:00:00Z"   # volatile: must not count as unexpected
json.dump(s, open(state_path, "w"))
'''


def run(args: str, state: Path, log: Path, mode: str = "ok", render_json: str = "0") -> subprocess.CompletedProcess[str]:
    stub = state.parent / "stub.py"
    stub.write_text(STUB)
    script = f"""
set -euo pipefail
source <(awk '/^# --- Main ---/{{exit}} {{print}}' "{ROOT / 'tools/agent-render'}")
resolve_service() {{ echo "srv-test"; }}
render_request_checked() {{
  echo "$1 $2 ${{3:-}}" >> "{log}"
  case "$1 $2" in
    "GET /services/srv-test") cat "{state}" ;;
    "PATCH /services/srv-test") python3 "{stub}" "{mode}" "{state}" "$3"; cat "{state}" ;;
    *) echo "unexpected: $1 $2" >&2; return 1 ;;
  esac
}}
RENDER_JSON={render_json}
cmd_update {args}
"""
    return subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        state, log = tmp / "state.json", tmp / "calls.log"

        def fresh(kind: str, runtime: str = "node") -> None:
            state.write_text(json.dumps(svc(kind, runtime)))
            log.write_text("")

        def cur() -> dict:
            return json.loads(state.read_text())

        def patches() -> list[str]:
            return [l for l in log.read_text().splitlines() if l.startswith("PATCH")]

        # cron schedule: applied, read back, buildFilter wiped by Render and restored
        fresh("cron_job")
        r = run('test-svc --schedule "0 11 * * *"', state, log)
        require(r.returncode == 0, f"schedule update failed: {r.stdout} {r.stderr}")
        require(cur()["serviceDetails"]["schedule"] == "0 11 * * *", "schedule not applied")
        require(cur()["buildFilter"] == FILTER, f"buildFilter not restored after Render wiped it: {cur()['buildFilter']}")
        require(len(patches()) == 2 and '"buildFilter"' in patches()[1], f"expected update + restore PATCH: {patches()}")
        require("restored" in r.stdout.lower() and "buildFilter" in r.stdout, f"restore not reported: {r.stdout}")
        require("not deployed" in r.stdout.lower(), f"deploy reminder missing: {r.stdout}")

        # start/build (native) go under envSpecificDetails; health check on a web service
        fresh("web_service")
        r = run('test-svc --start "node server.js" --build "npm ci --omit=dev" --health-check /health --pre-deploy "npm run migrate"', state, log)
        d = cur()["serviceDetails"]
        require(r.returncode == 0 and d["envSpecificDetails"]["startCommand"] == "node server.js"
                and d["envSpecificDetails"]["buildCommand"] == "npm ci --omit=dev" and d["healthCheckPath"] == "/health"
                and d.get("preDeployCommand") == "npm run migrate", f"web update wrong: {r.stdout} {r.stderr} {d}")

        # top-level only fields: no serviceDetails sent, so no quirk, no restore
        fresh("web_service")
        r = run("test-svc --branch staging", state, log)
        require(r.returncode == 0 and cur()["branch"] == "staging" and len(patches()) == 1, f"branch update: {r.stdout} {patches()}")

        # docker: --docker-command allowed, --start refused
        fresh("web_service", runtime="docker")
        r = run('test-svc --docker-command "uvicorn app:app"', state, log)
        require(r.returncode == 0 and cur()["serviceDetails"]["envSpecificDetails"]["dockerCommand"] == "uvicorn app:app",
                f"docker command: {r.stdout} {r.stderr}")
        fresh("web_service", runtime="docker")
        r = run('test-svc --start "x"', state, log)
        require(r.returncode == 2 and not patches(), f"--start on docker accepted: {r.stdout}")

        # wrong service type: refused before any write
        for kind, opt in (("web_service", '--schedule "0 1 * * *"'), ("cron_job", "--health-check /h"), ("cron_job", '--pre-deploy "x"')):
            fresh(kind)
            r = run(f"test-svc {opt}", state, log)
            require(r.returncode == 2 and not patches(), f"{opt} on {kind} accepted: rc={r.returncode} {r.stdout}")

        # Render silently ignores a requested field: verification fails
        fresh("cron_job")
        r = run('test-svc --schedule "0 12 * * *"', state, log, mode="ignore-schedule")
        require(r.returncode != 0 and "schedule" in (r.stdout + r.stderr), f"ignored field not caught: {r.stdout}")

        # an unexpected change other than buildFilter: reported, exit 1, not auto-reverted
        fresh("cron_job")
        r = run('test-svc --schedule "0 13 * * *"', state, log, mode="foreign-change")
        require(r.returncode == 1 and "branch" in (r.stdout + r.stderr) and cur()["branch"] == "someone-else",
                f"foreign change not reported or wrongly reverted: rc={r.returncode} {r.stdout} {r.stderr}")

        # dry-run: shows the change, sends nothing
        fresh("cron_job")
        r = run('test-svc --schedule "0 14 * * *" --dry-run', state, log)
        require(r.returncode == 0 and not patches() and cur()["serviceDetails"]["schedule"] == "0 9 * * *"
                and "0 14 * * *" in r.stdout, f"dry-run: {r.stdout} {patches()}")

        # --json
        fresh("cron_job")
        r = run('test-svc --schedule "0 15 * * *"', state, log, render_json="1")
        out = json.loads(r.stdout)
        require(out["changed"]["serviceDetails.schedule"] == {"before": "0 9 * * *", "after": "0 15 * * *"}
                and out["restored"] == ["buildFilter"] and out["deployed"] is False, f"--json: {out}")

        # nothing / unknown option
        fresh("cron_job")
        r = run("test-svc", state, log)
        require(r.returncode == 2 and not patches(), f"empty update accepted: rc={r.returncode}")
        r = run("test-svc --bogus x", state, log)
        require(r.returncode == 2 and not patches(), f"unknown option accepted: rc={r.returncode}")

    print("render update tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
