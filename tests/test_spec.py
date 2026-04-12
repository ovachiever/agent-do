#!/usr/bin/env python3
"""Focused tests for the minimal agent-do spec surface."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"
sys.path.insert(0, str(ROOT / "lib"))

from registry import load_registry, match_prompt_tools  # noqa: E402


def run(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    registry = load_registry()
    spec_matches = match_prompt_tools(registry, "write a spec and change proposal for this feature", limit=3)
    require(spec_matches, "expected routing matches for spec")
    require(spec_matches[0]["tool"] == "spec", f"unexpected top spec match: {spec_matches}")

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        env = os.environ.copy()

        init = run(str(AGENT_DO), "spec", "init", "--json", cwd=repo, env=env)
        require(init.returncode == 0, f"spec init failed: {init.stderr}")
        init_payload = json.loads(init.stdout)
        require(init_payload["ok"] is True, f"unexpected init payload: {init_payload}")
        require((repo / "agent-do-spec" / "config.yaml").exists(), "expected config.yaml after init")

        list_empty = run(str(AGENT_DO), "spec", "list", "--json", cwd=repo, env=env)
        require(list_empty.returncode == 0, f"spec list failed: {list_empty.stderr}")
        list_empty_payload = json.loads(list_empty.stdout)
        require(list_empty_payload["specs"] == [], f"expected no specs initially: {list_empty_payload}")
        require(list_empty_payload["changes"] == [], f"expected no changes initially: {list_empty_payload}")

        auth_spec = repo / "agent-do-spec" / "specs" / "auth.md"
        auth_spec.write_text(
            "---\nname: auth\ntitle: Authentication\n---\n\n# Authentication\n\n## Requirements\n",
            encoding="utf-8",
        )

        new_change = run(
            str(AGENT_DO),
            "spec",
            "new",
            "add-oauth-device-flow",
            "--title",
            "Add OAuth device flow",
            "--spec",
            "auth",
            "--json",
            cwd=repo,
            env=env,
        )
        require(new_change.returncode == 0, f"spec new failed: {new_change.stderr}")
        new_payload = json.loads(new_change.stdout)
        require(new_payload["change"] == "add-oauth-device-flow", f"unexpected new payload: {new_payload}")
        require(new_payload["status"] == "planned", f"unexpected new status: {new_payload}")

        list_full = run(str(AGENT_DO), "spec", "list", "--json", cwd=repo, env=env)
        require(list_full.returncode == 0, f"spec list after new failed: {list_full.stderr}")
        list_full_payload = json.loads(list_full.stdout)
        require(list_full_payload["specs"][0]["name"] == "auth", f"unexpected spec list payload: {list_full_payload}")
        require(list_full_payload["changes"][0]["id"] == "add-oauth-device-flow", f"unexpected change list payload: {list_full_payload}")

        show_spec = run(str(AGENT_DO), "spec", "show", "auth", "--json", cwd=repo, env=env)
        require(show_spec.returncode == 0, f"show spec failed: {show_spec.stderr}")
        show_spec_payload = json.loads(show_spec.stdout)
        require(show_spec_payload["type"] == "spec", f"unexpected show spec payload: {show_spec_payload}")
        require("Authentication" in show_spec_payload["content"], f"unexpected spec content: {show_spec_payload}")

        show_change = run(
            str(AGENT_DO),
            "spec",
            "show",
            "add-oauth-device-flow",
            "--type",
            "change",
            "--json",
            cwd=repo,
            env=env,
        )
        require(show_change.returncode == 0, f"show change failed: {show_change.stderr}")
        show_change_payload = json.loads(show_change.stdout)
        require(show_change_payload["type"] == "change", f"unexpected show change payload: {show_change_payload}")
        require(show_change_payload["status"] == "planned", f"unexpected change status: {show_change_payload}")
        require(show_change_payload["artifacts"]["deltas"][0]["name"] == "auth", f"unexpected change deltas: {show_change_payload}")

        status_change = run(
            str(AGENT_DO),
            "spec",
            "status",
            "--change",
            "add-oauth-device-flow",
            "--json",
            cwd=repo,
            env=env,
        )
        require(status_change.returncode == 0, f"status --change failed: {status_change.stderr}")
        status_change_payload = json.loads(status_change.stdout)
        require(status_change_payload["status"] == "planned", f"unexpected status payload: {status_change_payload}")
        require(status_change_payload["tasks"]["total"] == 3, f"unexpected task counts: {status_change_payload}")
        require(status_change_payload["missing"] == [], f"unexpected missing artifacts: {status_change_payload}")

        nested = repo / "nested" / "deeper"
        nested.mkdir(parents=True, exist_ok=True)
        nested_status = run(str(AGENT_DO), "spec", "status", "--json", cwd=nested, env=env)
        require(nested_status.returncode == 0, f"nested status failed: {nested_status.stderr}")
        nested_payload = json.loads(nested_status.stdout)
        require(nested_payload["counts"]["changes"] == 1, f"nested root detection failed: {nested_payload}")

        invalid = run(str(AGENT_DO), "spec", "new", "Bad_ID", cwd=repo, env=env)
        require(invalid.returncode != 0, "expected invalid change id to fail")

    print("spec tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
