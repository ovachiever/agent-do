#!/usr/bin/env python3
"""agent-gh pr: description and merge details.

A fake gh (AGENT_GH_BIN) records the --json field list and answers for an
open PR and a merged PR. Existing keys must keep their values.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_GH = ROOT / "tools" / "agent-gh"

BASE = {
    "title": "fix: thing", "isDraft": False, "author": {"login": "ctyrrell-versova"},
    "baseRefName": "main", "headRefName": "fix/thing", "headRefOid": "abc123",
    "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN", "reviewDecision": "",
    "changedFiles": 1, "additions": 3, "deletions": 1, "reviewRequests": [], "latestReviews": [],
    "files": [{"path": "a.py", "additions": 3, "deletions": 1}], "statusCheckRollup": [],
    "createdAt": "2026-10-01T00:00:00Z", "updatedAt": "2026-10-02T00:00:00Z",
}
OPEN = {**BASE, "number": 7, "state": "OPEN", "url": "https://github.com/acme/x/pull/7",
        "body": "## Why\nBecause.\n", "mergedAt": None, "mergedBy": None, "closedAt": None, "mergeCommit": None}
MERGED = {**BASE, "number": 8, "state": "MERGED", "url": "https://github.com/acme/x/pull/8",
          "body": "Merged one.", "mergedAt": "2026-10-03T10:00:00Z", "mergedBy": {"login": "ovachiever"},
          "closedAt": "2026-10-03T10:00:00Z", "mergeCommit": {"oid": "deadbeef"}}

FAKE = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
open(os.environ["GH_LOG"], "a").write(json.dumps(args) + "\n")
if args[:2] == ["pr", "view"]:
    print(os.environ["GH_PR_" + args[2]]); sys.exit(0)
sys.stderr.write("unexpected gh args: " + " ".join(args) + "\n"); sys.exit(2)
'''


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fake = tmp / "gh"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        log = tmp / "calls.jsonl"
        env = dict(os.environ, AGENT_GH_BIN=str(fake), GH_LOG=str(log), AGENT_DO_HOME=str(tmp / "home"),
                   GH_PR_7=json.dumps(OPEN), GH_PR_8=json.dumps(MERGED))

        def pr(ref: str, *extra: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([str(AGENT_GH), "pr", ref, *extra], cwd=ROOT, env=env, text=True,
                                  capture_output=True, check=False)

        r = pr("acme/x#8", "--json")
        require(r.returncode == 0, f"pr failed: {r.stderr}")
        d = json.loads(r.stdout)["pr"]
        require(d.get("merged_at") == "2026-10-03T10:00:00Z" and d.get("merged_by") == "ovachiever"
                and d.get("closed_at") == "2026-10-03T10:00:00Z" and d.get("merge_commit") == "deadbeef",
                f"merge details missing: {d}")
        require(d.get("body") == "Merged one.", f"description missing: {d.get('body')!r}")
        fields = json.loads(log.read_text().splitlines()[-1])
        requested = set(fields[fields.index("--json") + 1].split(","))
        for f in ("body", "mergedAt", "mergedBy", "closedAt", "mergeCommit"):
            require(f in requested, f"{f} not requested from gh: {sorted(requested)}")

        # open PR: merge fields present and null, description kept verbatim
        d = json.loads(pr("acme/x#7", "--json").stdout)["pr"]
        require(d["merged_at"] is None and d["merged_by"] is None and d["merge_commit"] is None and d["closed_at"] is None,
                f"open PR merge fields not null: {d}")
        require(d["body"] == "## Why\nBecause.\n", f"description altered: {d['body']!r}")

        # existing keys unchanged (merge gate and audit read these)
        for key, want in (("state", "OPEN"), ("merge_state", "CLEAN"), ("mergeable", "MERGEABLE"),
                          ("head_sha", "abc123"), ("base", "main"), ("author", "ctyrrell-versova"),
                          ("url", "https://github.com/acme/x/pull/7"), ("created_at", "2026-10-01T00:00:00Z")):
            require(d.get(key) == want, f"existing key {key} changed: {d.get(key)!r}")

        # text mode ends with the description
        out = pr("acme/x#7").stdout.rstrip("\n").splitlines()
        require(out[-2:] == ["body: ## Why", "Because."], f"text mode should end with the description: {out[-3:]}")

    print("gh pr detail tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
