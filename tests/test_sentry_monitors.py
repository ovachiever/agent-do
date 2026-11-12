#!/usr/bin/env python3
"""agent-sentry monitors: cron monitor check-in health.

Sources the real tool with the API stubbed: sentry_get answers from a file
and records the URL. Field names follow a live response from
GET /organizations/{org}/monitors/ (2026-10-06).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def mon(slug: str, envs: list[dict], *, muted: bool = False, status: str = "active", project: str = "proj-a") -> dict:
    return {"id": slug + "-id", "slug": slug, "name": slug, "status": status, "isMuted": muted,
            "project": {"slug": project}, "config": {"schedule": "0 * * * *", "timezone": "UTC", "schedule_type": "crontab"},
            "environments": envs}


def env(name: str, status: str, last: str | None = "2026-10-06T20:00:00Z", nxt: str | None = "2026-10-06T21:00:00Z",
        muted: bool = False) -> dict:
    return {"name": name, "status": status, "lastCheckIn": last, "nextCheckIn": nxt,
            "nextCheckInLatest": nxt, "isMuted": muted}


MONITORS = [
    mon("tick", [env("production", "ok")], project="vid-watcher"),
    mon("probe", [env("production", "missed_checkin"), env("staging", "error")]),
    mon("fresh", []),
    mon("quiet", [env("production", "timeout", muted=True)], muted=True),
]


def run(args: str, payload: object, tmp: Path) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    data, log = tmp / "resp.json", tmp / "urls.log"
    data.write_text(json.dumps(payload))
    log.write_text("")
    tools = tmp / "tools"
    tools.mkdir(exist_ok=True)
    if not (tmp / "lib").exists():
        (tmp / "lib").symlink_to(ROOT / "lib")
    src = (ROOT / "tools" / "agent-sentry").read_text()
    (tools / "agent-sentry").write_text(src[: src.index('case "${1:-help}" in')])
    script = f"""
set -euo pipefail
source "{tools / 'agent-sentry'}"
sentry_base_url() {{ echo "https://sentry.example/api/0"; }}
sentry_org() {{ echo "acme"; }}
sentry_get() {{ echo "$1" >> "{log}"; cat "{data}"; }}
cmd_monitors {args}
"""
    r = subprocess.run(["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False)
    return r, [l for l in log.read_text().splitlines() if l]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)

        r, urls = run("", MONITORS, tmp)
        require(r.returncode == 0, f"monitors failed: {r.stderr}")
        require(urls == ["https://sentry.example/api/0/organizations/acme/monitors/"], f"wrong URL: {urls}")
        lines = r.stdout.splitlines()
        row = lambda slug, envname: next((l for l in lines if l.split()[:1] == [slug] and envname in l.split()), "")
        require("ok" in row("tick", "production").split() and "vid-watcher" in row("tick", "production"), f"tick row: {r.stdout}")
        require("missed_checkin" in row("probe", "production").split(), f"probe production row: {r.stdout}")
        require("error" in row("probe", "staging").split(), f"probe staging row: {r.stdout}")
        fresh = next((l for l in lines if l.startswith("fresh")), "")
        require("no check-ins yet" in fresh, f"monitor without environments must say so: {fresh!r}")
        quiet = row("quiet", "production")
        require("timeout" in quiet.split() and "yes" in quiet.split(), f"muted row: {quiet!r}")
        footer = lines[-1]
        require("4 monitors" in footer and "3 not ok" in footer, f"footer should count missed, error, timeout: {footer!r}")

        # filters become query parameters, URL-encoded, repeatable
        r, urls = run("--project vid-watcher --project palantir --environment 'prod east'", MONITORS, tmp)
        require(r.returncode == 0 and len(urls) == 1, f"filtered call: {r.stderr} {urls}")
        q = urls[0].split("?", 1)[1] if "?" in urls[0] else ""
        require(sorted(q.split("&")) == sorted(["project=vid-watcher", "project=palantir", "environment=prod+east"])
                or sorted(q.split("&")) == sorted(["project=vid-watcher", "project=palantir", "environment=prod%20east"]),
                f"query params: {q!r}")

        # JSON: the API response, unchanged
        r, _ = run("--json", MONITORS, tmp)
        require(r.returncode == 0 and json.loads(r.stdout) == MONITORS, f"--json: {r.stdout[:200]} {r.stderr}")

        # no monitors: clear message, exit 0
        r, _ = run("", [], tmp)
        require(r.returncode == 0 and "No cron monitors" in r.stdout, f"empty: {r.stdout}")

        # Sentry error: message and exit 1 in both modes, never an empty table
        for extra in ("", "--json"):
            r, _ = run(extra, {"detail": "You do not have permission to perform this action."}, tmp)
            require(r.returncode == 1 and "permission" in r.stderr and "No cron monitors" not in r.stdout,
                    f"error ({extra or 'text'}): rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

        # with --project, the hint also names an unknown slug (Sentry answers 403 for one; seen live)
        r, _ = run("--project nope", {"detail": "You do not have permission to perform this action."}, tmp)
        require(r.returncode == 1 and "--project" in r.stderr, f"unknown-project hint missing: {r.stderr!r}")
        r, _ = run("", {"detail": "You do not have permission to perform this action."}, tmp)
        require("--project" not in r.stderr, f"project hint shown without --project: {r.stderr!r}")

        # truncation warning at a full page
        r, _ = run("", [mon(f"m{i}", [env("production", "ok")]) for i in range(100)], tmp)
        require(r.returncode == 0 and "100" in r.stderr and "more" in r.stderr.lower(), f"no truncation warning: {r.stderr!r}")

        # bad options
        for bad in ("--bogus", "--project"):
            r, urls = run(bad, MONITORS, tmp)
            require(r.returncode == 2 and not urls, f"{bad} accepted: rc={r.returncode}")

    print("sentry monitors tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
