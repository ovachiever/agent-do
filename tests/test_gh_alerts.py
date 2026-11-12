#!/usr/bin/env python3
"""agent-gh alerts: Dependabot alert census per repository.

A fake gh (AGENT_GH_BIN) serves multi-page results, a repo with alerts turned
off (403), a repo that errors (404), and an org listing with an archived repo.
The census must never report a repo it could not read as "0 alerts".
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_GH = ROOT / "tools" / "agent-gh"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def alert(n: int, sev: str, scope: str, pkg: str = "lodash", state: str = "open") -> dict:
    return {
        "number": n, "state": state,
        "dependency": {"package": {"ecosystem": "npm", "name": pkg}, "manifest_path": "package-lock.json", "scope": scope},
        "security_advisory": {"ghsa_id": f"GHSA-{n:04d}-aaaa-bbbb", "severity": sev, "summary": f"issue {n}"},
        "security_vulnerability": {"severity": sev, "first_patched_version": {"identifier": "9.9.9"}},
        "html_url": f"https://github.com/acme/x/security/dependabot/{n}",
        "created_at": "2026-10-01T00:00:00Z",
    }


PAGES = {
    "acme/paged": [[alert(1, "critical", "runtime"), alert(2, "high", "development")], [alert(3, "high", "runtime")]],
    "acme/clean": [[]],
}
ORG_REPOS = [[
    {"full_name": "acme/paged", "archived": False},
    {"full_name": "acme/clean", "archived": False},
    {"full_name": "acme/off", "archived": False},
    {"full_name": "acme/attic", "archived": True},
]]

FAKE = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["GH_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
pages = json.loads(os.environ["GH_PAGES"])
path = args[-1]
if args[:1] != ["api"] or "--paginate" not in args or "--slurp" not in args:
    sys.stderr.write("unexpected gh args: " + " ".join(args) + "\n"); sys.exit(2)
if path.startswith("orgs/acme/repos"):
    print(os.environ["GH_ORG"]); sys.exit(0)
repo = "/".join(path.split("/")[1:3])
if repo == "acme/off":
    sys.stderr.write("gh: Dependabot alerts are disabled for this repository. (HTTP 403)\n"); sys.exit(1)
if repo == "acme/broken":
    sys.stderr.write("gh: Not Found (HTTP 404)\n"); sys.exit(1)
if repo in pages:
    print(json.dumps(pages[repo])); sys.exit(0)
sys.stderr.write("unknown repo " + repo + "\n"); sys.exit(1)
'''


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = tmp / "gh"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        log = tmp / "calls.jsonl"
        env = dict(os.environ, AGENT_GH_BIN=str(fake), GH_LOG=str(log), GH_PAGES=json.dumps(PAGES),
                   GH_ORG=json.dumps(ORG_REPOS), AGENT_DO_HOME=str(tmp / "home"))

        def run(*args: str) -> subprocess.CompletedProcess[str]:
            log.write_text("")
            return subprocess.run([str(AGENT_GH), "alerts", *args], cwd=ROOT, env=env, text=True,
                                  capture_output=True, check=False)

        def calls() -> list[list[str]]:
            return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]

        # every page is counted; severity and scope tallied
        r = run("acme/paged", "--json")
        require(r.returncode == 0, f"alerts failed: {r.stderr}")
        data = json.loads(r.stdout)
        row = data["repos"][0]
        require(row["status"] == "ok" and row["count"] == 3, f"multi-page result undercounted: {row}")
        require(row["by_severity"] == {"critical": 1, "high": 2} and row["by_scope"] == {"runtime": 2, "development": 1},
                f"tallies wrong: {row}")
        require(data["totals"]["count"] == 3, f"totals wrong: {data['totals']}")
        sent = calls()[0]
        require("--paginate" in sent and "--slurp" in sent, f"not paginated: {sent}")
        require("state=open" in sent[-1] and "per_page=100" in sent[-1], f"default query wrong: {sent[-1]}")

        # three distinct outcomes: zero, off, error — and an error sets exit 1 without stopping the rest
        r = run("acme/clean", "acme/off", "acme/broken", "acme/paged", "--json")
        require(r.returncode == 1, f"a repo error must exit 1, got {r.returncode}")
        try:
            rows = {x["repo"]: x for x in json.loads(r.stdout)["repos"]}
        except (ValueError, KeyError):
            raise AssertionError(f"an error on one repo aborted the census (no report): {r.stdout!r} {r.stderr!r}")
        require(len(rows) == 4, f"census did not report every repo: {sorted(rows)}")
        require(rows["acme/clean"]["status"] == "ok" and rows["acme/clean"]["count"] == 0, f"clean: {rows['acme/clean']}")
        require(rows["acme/off"]["status"] == "disabled" and rows["acme/off"]["count"] is None,
                f"alerts-off repo must not read as 0: {rows['acme/off']}")
        require(rows["acme/broken"]["status"] == "error" and rows["acme/broken"]["count"] is None
                and "404" in rows["acme/broken"]["error"], f"error repo: {rows['acme/broken']}")
        require(rows["acme/paged"]["count"] == 3, "an error on one repo stopped the others")

        # disabled-only is not an error
        r = run("acme/off", "--json")
        require(r.returncode == 0, f"alerts off is a status, not a failure: rc={r.returncode}")

        # filters reach the API; --state all sends no state filter
        r = run("acme/paged", "--state", "fixed", "--severity", "critical,high", "--scope", "runtime", "--json")
        q = calls()[0][-1]
        require("state=fixed" in q and "severity=critical%2Chigh" in q.replace(",", "%2C") and "scope=runtime" in q,
                f"filters not sent: {q}")
        r = run("acme/paged", "--state", "all", "--json")
        require("state=" not in calls()[0][-1], f"--state all still filtered: {calls()[0][-1]}")

        # --org walks the org, skips archived unless asked
        r = run("--org", "acme", "--json")
        names = [x["repo"] for x in json.loads(r.stdout)["repos"]]
        require(names == ["acme/clean", "acme/off", "acme/paged"], f"--org repos wrong: {names}")
        r = run("--org", "acme", "--include-archived", "--json")
        names = [x["repo"] for x in json.loads(r.stdout)["repos"]]
        require("acme/attic" in names, f"--include-archived ignored: {names}")

        # --details lists each alert
        r = run("acme/paged", "--details", "--json")
        det = json.loads(r.stdout)["repos"][0]["alerts"]
        require(len(det) == 3 and det[0]["package"] == "lodash" and det[0]["fixed_in"] == "9.9.9"
                and det[0]["advisory"].startswith("GHSA-"), f"details wrong: {det}")

        # text mode: off shows as off, never as 0
        r = run("acme/clean", "acme/off")
        line = next(l for l in r.stdout.splitlines() if "acme/off" in l)
        require("off" in line.lower() and " 0 " not in f" {line} ", f"text mode shows off repo as 0: {r.stdout!r}")

        # bad input
        r = run("not-a-repo", "--json")
        require(r.returncode == 2, f"malformed repo accepted: rc={r.returncode}")
        r = run("--json")
        require(r.returncode == 2, f"no repos and no --org accepted: rc={r.returncode}")
        r = run("acme/paged", "--severity", "hihg", "--json")
        require(r.returncode == 2 and not calls(), f"severity typo accepted or sent: rc={r.returncode}")

    print("gh alerts tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
