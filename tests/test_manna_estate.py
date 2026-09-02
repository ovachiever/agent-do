#!/usr/bin/env python3
"""Manna estate CLI: one registry read, the HTTP model, and no daemon."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SERVE_DIR = REPO / "tools" / "agent-manna" / "serve"
sys.path.insert(0, str(SERVE_DIR))

import estate as estate_lib  # noqa: E402


ISSUES = [
    {
        "id": "mn-track1",
        "title": "TRACK: Program",
        "status": "open",
        "type": "track",
        "blocked_by": [],
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-01T00:00:00Z",
    },
    {
        "id": "mn-ready1",
        "title": "Ready",
        "status": "open",
        "blocked_by": [],
        "created_at": "2026-08-02T00:00:00Z",
        "updated_at": "2026-08-02T00:00:00Z",
    },
    {
        "id": "mn-active",
        "title": "Active",
        "status": "in_progress",
        "blocked_by": [],
        "claimed_by": "session-worker",
        "created_at": "2026-08-03T00:00:00Z",
        "updated_at": "2026-08-03T00:00:00Z",
    },
    {
        "id": "mn-block1",
        "title": "Blocked",
        "status": "blocked",
        "blocked_by": ["mn-ready1"],
        "created_at": "2026-08-04T00:00:00Z",
        "updated_at": "2026-08-04T00:00:00Z",
    },
    {
        "id": "mn-decide",
        "title": "[DECISION] Choose",
        "status": "open",
        "blocked_by": [],
        "created_at": "2026-08-05T00:00:00Z",
        "updated_at": "2026-08-05T00:00:00Z",
    },
    {
        "id": "mn-dream1",
        "title": "Dream",
        "status": "open",
        "type": "dream",
        "blocked_by": [],
        "created_at": "2026-08-06T00:00:00Z",
        "updated_at": "2026-08-06T00:00:00Z",
    },
    {
        "id": "mn-done01",
        "title": "Done",
        "status": "done",
        "blocked_by": [],
        "created_at": "2026-08-07T00:00:00Z",
        "updated_at": "2026-08-07T00:00:00Z",
    },
]

PEERS = {
    "success": True,
    "peers": [
        {"agent_id": "session-needs", "status": "active", "pulse": {"status": "needs-user"}},
        {"agent_id": "session-works", "status": "active", "pulse": {"status": "working"}},
        {"agent_id": "session-idles", "status": "idle"},
        {"agent_id": "session-gone1", "status": "dead"},
    ],
}


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def make_board(root: Path) -> None:
    board = root / ".manna"
    board.mkdir(parents=True)
    (board / "issues.jsonl").write_text(
        "".join(json.dumps(issue) + "\n" for issue in ISSUES), encoding="utf-8"
    )
    (board / "drift.yaml").write_text(
        "generated_at: '2026-08-20T00:00:00Z'\n"
        "findings:\n"
        "- kind: landed_open\n"
        "  issue_id: mn-ready1\n",
        encoding="utf-8",
    )
    git(root, "init", "-q", "-b", "main")


def make_agent_do(path: Path) -> Path:
    script = path / "agent-do-stub"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"PEERS = {PEERS!r}\n"
        "if sys.argv[1:] == ['coord', 'peers', '--json']:\n"
        "    print(json.dumps(PEERS))\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(2)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


class DirectAdapterTests(unittest.TestCase):
    def test_cli_emits_the_http_derivation_unchanged(self) -> None:
        expected = {"generated_at": "now", "boards": [{"slug": "sentinel"}]}
        original = estate_lib.serve_lib.boards_index
        estate_lib.serve_lib.boards_index = lambda: expected
        try:
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                self.assertEqual(estate_lib.main(["--json"]), 0)
            self.assertEqual(json.loads(stream.getvalue()), expected)
        finally:
            estate_lib.serve_lib.boards_index = original

    def test_derivation_failure_is_structured_and_nonzero(self) -> None:
        original = estate_lib.serve_lib.boards_index

        def fail() -> dict:
            raise RuntimeError("registry unreadable")

        estate_lib.serve_lib.boards_index = fail
        try:
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                self.assertEqual(estate_lib.main(["--json"]), 1)
            self.assertEqual(
                json.loads(stream.getvalue()),
                {"success": False, "error": "estate read failed: registry unreadable"},
            )
        finally:
            estate_lib.serve_lib.boards_index = original


class WrapperContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.root = base / "project"
        self.missing = base / "gone"
        make_board(self.root)
        registry = self.home / "manna" / "serve" / "boards.json"
        registry.parent.mkdir(parents=True)
        registry.write_text(
            json.dumps(
                {
                    "version": 1,
                    "decision_markers": [],
                    "boards": {
                        "project": {"path": str(self.root), "registered_at": "2026-08-01T00:00:00Z"},
                        "gone": {"path": str(self.missing), "registered_at": "2026-08-01T00:00:00Z"},
                    },
                }
            ),
            encoding="utf-8",
        )
        (self.home / "python-path").write_text(sys.executable + "\n", encoding="utf-8")
        self.stub_agent_do = make_agent_do(base)
        self.env = {
            **os.environ,
            "AGENT_DO_HOME": str(self.home),
            "MANNA_SERVE_AGENT_DO": str(self.stub_agent_do),
        }
        self.env.pop("AGENT_DO_PYTHON", None)
        self.wrapper = REPO / "tools" / "agent-manna" / "agent-manna"

    def tearDown(self) -> None:
        estate_lib.serve_lib.CACHE.bundles.clear()
        estate_lib.serve_lib.CACHE.gitdirs.clear()
        self.tmp.cleanup()

    def run_estate(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.wrapper), "estate", *args],
            cwd=self.tmp.name,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_json_has_every_registered_board_and_required_rollups(self) -> None:
        result = self.run_estate("--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(
            payload["registry"],
            str(self.home / "manna" / "serve" / "boards.json"),
        )
        self.assertEqual(
            payload["decision_markers"],
            ["[DECISION]", "[HUMAN]", "[OWNER]"],
        )
        self.assertEqual([row["slug"] for row in payload["boards"]], ["project", "gone"])

        project, gone = payload["boards"]
        self.assertEqual(project["root"], str(self.root))
        self.assertTrue(project["exists"])
        self.assertEqual(project["total"], len(ISSUES))
        self.assertEqual(
            project["status_counts"],
            {"ready": 1, "active": 1, "blocked": 1, "decision": 1, "done": 1},
        )
        self.assertEqual(project["dreams"], 1)
        self.assertEqual(project["decisions"], 1)
        self.assertEqual(project["drift_count"], 1)
        self.assertEqual(project["drift_generated_at"], "2026-08-20T00:00:00Z")
        self.assertEqual(project["latest_update"], "2026-08-07T00:00:00Z")
        self.assertEqual(
            {key: project["coord"][key] for key in ("needs_you", "working", "here", "gone")},
            {"needs_you": 1, "working": 1, "here": 3, "gone": 1},
        )
        self.assertFalse(gone["exists"])
        self.assertEqual(gone["total"], 0)
        self.assertEqual(payload["totals"], {"needs_you": 1, "working": 1, "here": 3})
        self.assertEqual(payload["building"], 0)
        self.assertFalse((self.home / "manna" / "serve" / "daemon.json").exists())

    def test_default_is_yaml_and_help_exposes_the_wrapper_verb(self) -> None:
        result = self.run_estate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(yaml.safe_load(result.stdout)["count"], 2)

        command_help = self.run_estate("--help")
        self.assertEqual(command_help.returncode, 0, command_help.stderr)
        self.assertIn("No daemon is started or contacted", command_help.stdout)

        top = subprocess.run(
            [str(self.wrapper), "--help"],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(top.returncode, 0, top.stderr)
        self.assertRegex(top.stdout, r"\n  estate\s{2,}")

    def test_sparse_path_uses_the_pinned_runtime_for_estate_and_serve(self) -> None:
        sparse_env = {
            "PATH": "/usr/bin:/bin",
            "AGENT_DO_HOME": str(self.home),
            "MANNA_SERVE_AGENT_DO": str(self.stub_agent_do),
        }
        estate = subprocess.run(
            [str(self.wrapper), "estate", "--json"],
            cwd=self.tmp.name,
            env=sparse_env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(estate.returncode, 0, estate.stderr)
        self.assertEqual(json.loads(estate.stdout)["count"], 2)

        try:
            serve = subprocess.run(
                [str(self.wrapper), "serve", "--json", "--port", "0"],
                cwd=self.root,
                env=sparse_env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(serve.returncode, 0, serve.stderr)
            self.assertEqual(json.loads(serve.stdout)["daemon"], "started")
        finally:
            subprocess.run(
                [str(self.wrapper), "serve", "--stop", "--json"],
                cwd=self.root,
                env=sparse_env,
                capture_output=True,
                text=True,
                timeout=60,
            )

    def test_invalid_pinned_runtime_fails_closed(self) -> None:
        invalid = Path(self.tmp.name) / "invalid-python"
        invalid.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        invalid.chmod(0o755)
        (self.home / "python-path").write_text(str(invalid) + "\n", encoding="utf-8")
        result = self.run_estate("--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pinned Python runtime is not Python 3.10+ with PyYAML", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
