#!/usr/bin/env python3
"""manna serve: derivation, registry, HTTP surface, and CLI lifecycle.

The board on disk is the only input; every section on the page must fall out
of it. These tests build a small strict-shaped board in a throwaway git
repository and check what the page would show.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVE_DIR = REPO / "tools" / "agent-manna" / "serve"
sys.path.insert(0, str(SERVE_DIR))

import board as board_lib  # noqa: E402
import digest as digest_lib  # noqa: E402
import serve as serve_lib  # noqa: E402

ISSUES = [
    {"id": "mn-track1", "title": "TRACK: Program", "status": "open", "type": "track", "blocked_by": [], "created_at": "2026-08-01T00:00:00Z", "updated_at": "2026-08-01T00:00:00Z"},
    {"id": "mn-aaaaaa", "title": "First ready thing", "description": "Build the first ready thing.", "status": "open", "blocked_by": [], "track": "mn-track1", "prompt": ".handoff/01-mn-aaaaaa-first.md", "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-10T00:00:00Z"},
    {"id": "mn-bbbbbb", "title": "Second ready thing", "status": "open", "blocked_by": [], "track": "mn-track1", "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-11T00:00:00Z"},
    {"id": "mn-cccccc", "title": "Claimed thing", "status": "in_progress", "blocked_by": [], "track": "mn-track1", "claimed_by": "claude-deadbeefdead0000", "claimed_at": "2026-08-12T00:00:00Z", "claim_token_hash": "sha256:" + "0" * 64, "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-12T00:00:00Z"},
    {"id": "mn-cccc22", "title": "Second claimed thing", "status": "in_progress", "blocked_by": [], "track": "mn-track1", "claimed_by": "claude-0000aaaa1111ffff", "claimed_at": "2026-08-12T00:00:00Z", "claim_token_hash": "sha256:" + "1" * 64, "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-13T00:00:00Z"},
    {"id": "mn-dddddd", "title": "Waits on aaaaaa", "status": "blocked", "blocked_by": ["mn-aaaaaa"], "track": "mn-track1", "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-03T00:00:00Z"},
    {"id": "mn-eeeeee", "title": "Waits on dddddd", "status": "blocked", "blocked_by": ["mn-dddddd"], "track": "mn-track1", "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-03T00:00:00Z"},
    {"id": "mn-ffffff", "title": "[DECISION] Ratify the thing", "status": "open", "blocked_by": [], "track": "mn-track1", "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-04T00:00:00Z"},
    {"id": "mn-999999", "title": "Open but graph says blocked", "status": "open", "blocked_by": ["mn-bbbbbb"], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-04T00:00:00Z"},
    {"id": "mn-mentio", "title": "Retire the [DECISION] title convention", "status": "open", "blocked_by": [], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-04T00:00:00Z"},
    {"id": "mn-second", "title": "[P1-K] [human] Rule on the second thing", "status": "open", "blocked_by": [], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-04T00:00:00Z"},
    {"id": "mn-dream1", "title": "A spark", "status": "open", "type": "dream", "blocked_by": [], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-05T00:00:00Z"},
    {"id": "mn-done00", "title": "Shipped thing", "description": "Document claim_token_hash and legacy_migration redaction.", "status": "done", "blocked_by": [], "track": "mn-track1", "legacy_migration": {"version": 1, "disposition": "history", "migrated_at": "2026-08-21T00:00:00Z"}, "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-06T00:00:00Z"},
    {"id": "mn-cycle1", "title": "Cycle A", "status": "blocked", "blocked_by": ["mn-cycle2"], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-03T00:00:00Z"},
    {"id": "mn-cycle2", "title": "Cycle B", "status": "blocked", "blocked_by": ["mn-cycle1"], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-03T00:00:00Z"},
]


STUB_PEERS = {
    "success": True,
    "peers": [
        {"agent_id": "session-deadbeefdead", "status": "active", "age": "3s ago", "age_seconds": 3, "runtime": "claude", "focus": {"goal": "building the thing"},
         "pulse": {"status": "needs-user", "activity": "Bash", "latest_prompt": "please fix it", "updated_at": "2026-08-24T00:00:00Z", "turns": 4, "todo": {"done": 1, "total": 3, "current": "fix unicode"}}},
        {"agent_id": "session-0000aaaa1111", "status": "active", "age": "9s ago", "age_seconds": 9, "runtime": "claude", "focus": {"goal": "reading"},
         "pulse": {"status": "working", "activity": "Read", "latest_prompt": "look around", "updated_at": "2026-08-24T00:00:00Z", "turns": 1}},
        {"agent_id": "codex-feedfacefeedface", "status": "idle", "age": "40m ago", "age_seconds": 2400, "runtime": "codex", "focus": {}},
        {"agent_id": "session-dead00000000", "status": "dead", "age": "3h ago", "age_seconds": 10800, "runtime": "claude", "focus": {}},
    ],
}
STUB_CLAIMS = {"success": True, "claims": [
    {"path": "tools/x", "owner": "session-deadbeefdead", "owner_status": "active", "reason": "building", "strength": "soft", "updated_at": "2026-08-24T00:00:00Z"},
    {"path": "tools/x/sub.py", "owner": "session-0000aaaa1111", "owner_status": "active", "reason": "also here", "strength": "soft", "updated_at": "2026-08-24T00:00:00Z"},
    {"path": "docs", "owner": "session-dead00000000", "owner_status": "dead", "reason": "old", "strength": "soft", "updated_at": "2026-08-01T00:00:00Z"},
    {"path": "README.md", "owner": "codex-feedfacefeedface", "owner_status": "idle", "reason": "docs", "strength": "soft", "updated_at": "2026-08-24T00:00:00Z"},
]}
STUB_DROPS = {"success": True, "drops": [
    {"for": "session-deadbeefdead", "path": "notes.md", "note": "read this", "owner_label": "session-0000aaaa1111", "created_at": "2026-08-24T00:00:00Z"},
]}
STUB_RECONCILE = {"success": True, "findings": [
    {"kind": "landed_open", "issue_id": "mn-aaaaaa", "detail": "live finding", "evidence": "abc123", "proposed_fix": "claim and done"},
    {"kind": "stale_dream", "issue_id": "mn-dream1", "detail": "old dream", "evidence": "created 2026-08-02", "proposed_fix": "convert or close"},
]}


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(nested_keys(child) for child in value.values()))
    if isinstance(value, list):
        return set().union(*(nested_keys(child) for child in value))
    return set()


def make_stub_agent_do(directory: Path) -> Path:
    """A stand-in `agent-do` that answers the two verbs serve consumes."""
    import shlex
    script = directory / "agent-do"
    script.write_text(
        "#!/usr/bin/env python3\nimport json, os, sys\n"
        f"PEERS = {STUB_PEERS!r}\nRECON = {STUB_RECONCILE!r}\nCLAIMS = {STUB_CLAIMS!r}\nDROPS = {STUB_DROPS!r}\n"
        "a = sys.argv[1:]\n"
        "if a[:3] == ['coord', 'peers', '--json']: print(json.dumps(PEERS)); sys.exit(0)\n"
        "if a[:3] == ['coord', 'claims', '--json']: print(json.dumps(CLAIMS)); sys.exit(0)\n"
        "if a[:3] == ['coord', 'drops', '--json']: print(json.dumps(DROPS)); sys.exit(0)\n"
        "if a[:2] == ['coord', 'need']: print(json.dumps({'success': True, 'needs': []})); sys.exit(0)\n"

        "if a[:3] == ['manna', 'reconcile', '--json']: print(json.dumps(RECON)); sys.exit(1)\n"
        "if a[:1] == ['manna'] and os.environ.get('STUB_LOG'):\n"
        "    import pathlib\n"
        "    log = pathlib.Path(os.environ['STUB_LOG']); log.write_text((log.read_text() if log.exists() else '') + ' '.join(a) + '|' + os.environ.get('MANNA_SESSION_ID','') + '\\n')\n"
        "    if a[1:3] == ['done', 'mn-10c4ed']: print('Refusing: claimed by another session', file=sys.stderr); sys.exit(2)\n"
        "    print('ok'); sys.exit(0)\n"
        "sys.exit(2)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout.strip()


def make_board(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    board = root / ".manna"
    board.mkdir()
    (board / "issues.jsonl").write_text("".join(json.dumps(i) + "\n" for i in ISSUES), encoding="utf-8")
    (board / "sessions.jsonl").write_text("", encoding="utf-8")
    (board / "handoff-order.yaml").write_text("version: 1\nitems:\n- mn-bbbbbb\n- mn-aaaaaa\n- mn-dddddd\n", encoding="utf-8")
    (board / "workflow.yaml").write_text("version: 2\nhandoff_dir: .handoff\n", encoding="utf-8")
    (board / "board.yaml").write_text("version: 1\nworkflow: strict\n", encoding="utf-8")
    (board / "drift.yaml").write_text(
        "generated_at: \"2026-08-20T00:00:00Z\"\nfindings:\n- kind: landed_open\n  issue_id: mn-aaaaaa\n  detail: referenced by landed commit trailer but status is open\n  evidence: abc123\n  proposed_fix: claim and done it\n",
        encoding="utf-8",
    )
    handoff = root / ".handoff"
    handoff.mkdir()
    (handoff / "01-mn-aaaaaa-first.md").write_text("# First\n\nwork order body\n", encoding="utf-8")
    (root / "secret.md").write_text("not a handoff\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "feat: advance the first thing\n\nManna: mn-aaaaaa\nCo-Authored-By: t <t@example.com>")
    git(root, "commit", "-q", "--allow-empty", "-m", "chore: unrelated")
    return root


class DerivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = make_board(Path(cls.tmp.name) / "proj")
        cls.state = board_lib.derive(cls.root, agent_do=None)
        cls.by_id = {r["id"]: r for r in cls.state["all"]}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_private_fields_never_leave_the_board(self) -> None:
        self.assertFalse({"claim_token_hash", "legacy_migration"} & nested_keys(self.state))

    def test_state_cli_is_the_full_public_contract(self) -> None:
        env = {**os.environ, "MANNA_STATE_AGENT_DO": "none"}
        completed = subprocess.run(
            [str(board_lib._state_binary()), "state", "--json", "--cached-drift"],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["total"], len(ISSUES))
        ready = next(row for row in payload["all"] if row["id"] == "mn-aaaaaa")
        self.assertEqual(ready["description"], "Build the first ready thing.")
        self.assertIn("blocked_by", ready)
        self.assertEqual(ready["prompt"], ".handoff/01-mn-aaaaaa-first.md")
        private = {"claim_token_hash", "legacy_migration", "act_token", "actor"}
        self.assertFalse(private & nested_keys(payload))

    def test_state_cli_attaches_hash_current_presentation_cache_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_board(Path(tmp) / "project").resolve()
            issue_path = root / ".manna" / "issues.jsonl"
            issues = [json.loads(line) for line in issue_path.read_text(encoding="utf-8").splitlines()]
            cached_issue = next(issue for issue in issues if issue["id"] == "mn-aaaaaa")
            cached_issue.update({
                "title": "Ship “Résumé” — compass 🧭",
                "description": "Line one\nLine two\x7f",
                "type": "item",
            })
            issue_path.write_text(
                "".join(json.dumps(issue) + "\n" for issue in issues),
                encoding="utf-8",
            )

            home = Path(tmp) / "home"
            serve_home = home / "manna" / "serve"
            digest_home = serve_home / "digests"
            digest_home.mkdir(parents=True)
            (serve_home / "boards.json").write_text(json.dumps({
                "version": 1,
                "boards": {"Project Board": {"path": str(root)}},
            }), encoding="utf-8")
            content_hash = digest_lib.content_hash(cached_issue)
            self.assertEqual(content_hash, "6843e053b291818f")
            cache_path = digest_home / "Project_Board.json"
            cache_path.write_text(json.dumps({
                "version": 1,
                "digests": {
                    "mn-aaaaaa": {
                        "hash": content_hash,
                        "digest": "Render one shared line everywhere",
                        "summary": "Every human-facing client reads this same cached explanation.",
                        "summary_hash": f"{content_hash}:{digest_lib.SUMMARY_MAX_CHARS}:{digest_lib.SUMMARY_MAX_WORDS}",
                    },
                    "mn-bbbbbb": {
                        "hash": "stale-content-hash",
                        "digest": "Never attach stale presentation",
                    },
                },
            }, sort_keys=True), encoding="utf-8")
            before = cache_path.read_bytes()
            env = {
                **os.environ,
                "AGENT_DO_HOME": str(home),
                "MANNA_STATE_AGENT_DO": "none",
            }
            completed = subprocess.run(
                [str(board_lib._state_binary()), "state", "--json", "--cached-drift"],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            attached = next(row for row in payload["all"] if row["id"] == "mn-aaaaaa")
            self.assertEqual(attached["digest"], "Render one shared line everywhere")
            self.assertEqual(
                attached["summary"],
                "Every human-facing client reads this same cached explanation.",
            )
            next_copy = next(row for row in payload["next"] if row["id"] == "mn-aaaaaa")
            self.assertEqual(next_copy["digest"], attached["digest"])
            miss = next(row for row in payload["all"] if row["id"] == "mn-bbbbbb")
            self.assertNotIn("digest", miss)
            self.assertNotIn("summary", miss)
            self.assertEqual(cache_path.read_bytes(), before, "state is attach-only")

    def test_serve_adapter_returns_the_core_model_without_a_second_derivation(self) -> None:
        env = {**os.environ, "MANNA_STATE_AGENT_DO": "none"}
        direct = subprocess.run(
            [str(board_lib._state_binary()), "state", "--json", "--cached-drift"],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        expected = json.loads(direct.stdout)
        expected.pop("success")
        actual = board_lib.derive(self.root, agent_do=None)
        expected.pop("generated_at")
        actual.pop("generated_at")
        self.assertEqual(actual, expected)

    def test_port_is_picked_free_once_and_kept(self) -> None:
        # No shipped default port: first resolution asks the OS for a free
        # one and persists it; every later resolution returns the same.
        import importlib
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("AGENT_DO_HOME")
            os.environ["AGENT_DO_HOME"] = tmp
            try:
                importlib.reload(serve_lib)
                first = serve_lib.resolved_port()
                second = serve_lib.resolved_port()
                self.assertEqual(first, second)
                self.assertTrue(0 < first < 65536)
                on_disk = json.loads((Path(tmp) / "manna" / "serve" / "config.json").read_text())
                self.assertEqual(on_disk["port"], first)
            finally:
                if old is None:
                    os.environ.pop("AGENT_DO_HOME", None)
                else:
                    os.environ["AGENT_DO_HOME"] = old
                importlib.reload(serve_lib)

    def test_rows_carry_both_timestamps_for_the_recent_view(self) -> None:
        # The recent chip sorts on updated_at and the inspector shows
        # filed (created_at) beside touched (updated_at); both must ship.
        for row in self.state["all"]:
            self.assertIn("created_at", row, row["id"])
            self.assertIn("updated_at", row, row["id"])

    def test_next_follows_handoff_order_then_unordered(self) -> None:
        self.assertEqual([r["id"] for r in self.state["next"]], ["mn-bbbbbb", "mn-aaaaaa", "mn-mentio"])

    def test_now_carries_claimant_with_unseen_liveness_without_coord(self) -> None:
        now = self.state["now"]
        self.assertEqual(sorted(r["id"] for r in now), ["mn-cccc22", "mn-cccccc"])
        first = next(r for r in now if r["id"] == "mn-cccccc")
        self.assertEqual(first["claimant"]["label"], "claude-deadbeefdead0000")
        self.assertEqual(first["claimant"]["liveness"], "unseen")
        self.assertIsNone(first["claimant"]["pulse"])
        self.assertEqual(self.state["drift"]["source"], "file")

    def test_decisions_come_from_title_markers(self) -> None:
        self.assertEqual(sorted(r["id"] for r in self.state["decisions"]), ["mn-ffffff", "mn-second"])
        self.assertEqual(self.by_id["mn-mentio"]["effective"], "ready")
        self.assertEqual(self.by_id["mn-ffffff"]["effective"], "decision")
        self.assertEqual(self.by_id["mn-ffffff"]["title_plain"], "Ratify the thing")

    def test_graph_outranks_status_field(self) -> None:
        self.assertEqual(self.by_id["mn-999999"]["effective"], "waiting")
        self.assertEqual(self.by_id["mn-999999"]["blockers"][0]["id"], "mn-bbbbbb")

    def test_waves_are_topological_layers(self) -> None:
        waves = {w["wave"]: [r["id"] for r in w["items"]] for w in self.state["waves"]}
        self.assertEqual(waves[1], ["mn-dddddd", "mn-999999"])
        self.assertEqual(waves[2], ["mn-eeeeee"])
        self.assertEqual(sorted(r["id"] for r in self.state["unlayered"]), ["mn-cycle1", "mn-cycle2"])

    def test_handoff_existence_is_reported_per_row(self) -> None:
        self.assertTrue(self.by_id["mn-aaaaaa"]["handoff_exists"])
        self.assertIsNone(self.by_id["mn-bbbbbb"]["handoff_exists"])

    def test_dependents_are_reverse_edges(self) -> None:
        self.assertEqual(self.by_id["mn-aaaaaa"]["dependents"], ["mn-dddddd"])

    def test_trailer_commits_index_by_id(self) -> None:
        commits = self.by_id["mn-aaaaaa"]["commits"]
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]["subject"], "feat: advance the first thing")
        self.assertEqual(self.by_id["mn-bbbbbb"]["commits"], [])

    def test_dreams_tracks_drift_counts(self) -> None:
        self.assertEqual([r["id"] for r in self.state["dreams"]], ["mn-dream1"])
        self.assertEqual(self.state["tracks"][0]["id"], "mn-track1")
        self.assertEqual(self.state["tracks"][-1]["title"], "(no track)")
        self.assertEqual(self.state["drift"]["count"], 1)
        self.assertEqual(self.state["drift"]["kinds"], {"landed_open": 1})
        self.assertEqual(self.state["counts"]["ready"], 3)
        self.assertEqual(self.state["git"]["branch"], "main")

    def test_summary_matches_derivation(self) -> None:
        summary = board_lib.summary(self.root)
        self.assertEqual(summary["decisions"], 2)
        self.assertEqual(summary["dreams"], 1)
        self.assertEqual(summary["status_counts"]["done"], 1)
        self.assertEqual(summary["drift_count"], 1)

    def test_signature_moves_when_the_board_moves(self) -> None:
        gitdir = board_lib.git_dir(self.root)
        before = board_lib.signature(self.root, gitdir)
        path = self.root / ".manna" / "issues.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        os.utime(path, (1, 1))
        self.assertNotEqual(before, board_lib.signature(self.root, gitdir))

    def test_federation_declarations_are_attached_without_changing_local_waves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_board(Path(tmp) / "federated")
            (root / ".manna" / "federation.yaml").write_text(
                "version: 1\n"
                "board_id: mb-11111111111111111111111111111111\n"
                "relations:\n"
                "- from: mn-aaaaaa\n"
                "  kind: informed_by\n"
                "  to: manna://mb-22222222222222222222222222222222/mn-bbbbbb\n"
                "  hint: target-board\n",
                encoding="utf-8",
            )
            state = board_lib.derive(root, agent_do=None)
            by_id = {row["id"]: row for row in state["all"]}
            self.assertEqual(state["board"]["board_id"], "mb-11111111111111111111111111111111")
            self.assertEqual(by_id["mn-aaaaaa"]["relations"][0]["kind"], "informed_by")
            self.assertEqual(by_id["mn-aaaaaa"]["effective"], "ready")
            self.assertEqual([row["id"] for row in state["next"]][:2], ["mn-bbbbbb", "mn-aaaaaa"])

    def test_resolved_relation_payload_enriches_the_same_issue_rows(self) -> None:
        state = {"all": [{"id": "mn-aaaaaa", "relations": []}], "federation": {"relations": []}}
        payload = {
            "success": True,
            "relations": [
                {
                    "from": "mn-aaaaaa",
                    "kind": "counterpart",
                    "to": "manna://mb-22222222222222222222222222222222/mn-bbbbbb",
                    "resolution": {"state": "resolved", "replicas": 1, "issue": {"title": "Target", "status": "done"}},
                    "reciprocity": "confirmed",
                }
            ],
        }
        serve_lib.attach_resolved_relations(state, payload)
        self.assertEqual(state["all"][0]["relations"][0]["resolution"]["state"], "resolved")
        self.assertEqual(state["federation"]["relations"][0]["reciprocity"], "confirmed")

    def test_peer_matching_across_identity_forms(self) -> None:
        peers = [{"agent_id": "session-3c15edbd4860", "status": "active"}, {"agent_id": "codex-01a02afe94d27b52", "status": "idle"}]
        self.assertEqual(board_lib.match_peer("claude-3c15edbd486045ef", peers)["status"], "active")
        self.assertEqual(board_lib.match_peer("codex-01a02afe94d27b52", peers)["status"], "idle")
        self.assertIsNone(board_lib.match_peer("claude-ffffffffffffffff", peers))
        self.assertIsNone(board_lib.match_peer(None, peers))


class LiveDerivationTests(unittest.TestCase):
    """With coord and reconcile answering (stubbed), pulse rides the rows and drift is live."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = make_board(Path(cls.tmp.name) / "proj")
        cls.stub = make_stub_agent_do(Path(cls.tmp.name))
        # The caller owns drift now: reconcile serializes on the board lock
        # (measured 40s+ under contention), so derive never recomputes it
        # silently; serve hands in a background-computed value the same way.
        cls.state = board_lib.derive(
            cls.root, agent_do=cls.stub, live=True,
            drift_live=board_lib.live_drift(cls.root, cls.stub),
        )
        cls.by_id = {r["id"]: r for r in cls.state["all"]}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_now_sorts_needs_user_first_and_carries_pulse(self) -> None:
        now = self.state["now"]
        self.assertEqual([r["id"] for r in now], ["mn-cccccc", "mn-cccc22"])
        c = now[0]["claimant"]
        self.assertEqual(c["attention"], "needs-user")
        self.assertEqual(c["pulse"]["activity"], "Bash")
        self.assertEqual(c["pulse"]["todo"], {"done": 1, "total": 3, "current": "fix unicode"})
        self.assertEqual(now[1]["claimant"]["attention"], "working")

    def test_peers_attention_first_and_counted(self) -> None:
        self.assertEqual([p["attention"] for p in self.state["peers"]], ["needs-user", "working", "idle", "gone"])
        self.assertEqual(self.state["attention"]["needs-user"], 1)
        self.assertEqual(self.state["attention"]["gone"], 1)

    def test_drift_is_live_with_file_age_beside_it(self) -> None:
        d = self.state["drift"]
        self.assertEqual(d["source"], "reconcile")
        self.assertEqual(d["count"], 2)
        self.assertEqual(d["kinds"], {"landed_open": 1, "stale_dream": 1})
        self.assertEqual(d["file"]["count"], 1)
        self.assertEqual(d["file"]["generated_at"], "2026-08-20T00:00:00Z")
        self.assertFalse((self.root / ".manna" / "drift.yaml").read_text().count("live finding"), "the page never writes drift")

    def test_coord_snapshot_contention_stale_and_holdings(self) -> None:
        c = self.state["coord"]
        self.assertEqual(len(c["contention"]), 1)
        self.assertEqual(c["contention"][0]["paths"], ["tools/x", "tools/x/sub.py"])
        by_path = {x["path"]: x for x in c["claims"]}
        self.assertTrue(by_path["tools/x"]["contended"] and by_path["tools/x/sub.py"]["contended"])
        self.assertFalse(by_path["README.md"]["contended"])
        self.assertTrue(by_path["docs"]["stale"])
        self.assertEqual([x["path"] for x in c["claims"]][:2], ["tools/x", "tools/x/sub.py"], "contended first, stale last")
        self.assertEqual(c["claims"][-1]["path"], "docs")
        self.assertEqual(len(c["drops"]), 1)
        peers = {p["agent_id"]: p for p in self.state["peers"]}
        self.assertEqual([h["id"] for h in peers["session-deadbeefdead"]["holding"]], ["mn-cccccc"])
        self.assertEqual(peers["codex-feedfacefeedface"]["holding"], [])

    def test_nonzero_exit_reconcile_still_counts(self) -> None:
        # the stub exits 1 with findings, as reconcile does
        self.assertIsNotNone(board_lib.live_drift(self.root, self.stub))


class DigestTests(unittest.TestCase):
    """One-line digests: validated, cached by content hash, generated in byte-bounded batches, title as fallback."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["AGENT_DO_HOME"] = self.tmp.name
        self.rows = [
            {"id": "mn-aaaaaa", "title": "First ready thing", "description": "Make the first thing.", "kind": "item"},
            {"id": "mn-bbbbbb", "title": "Second ready thing", "description": None, "kind": "item"},
            {"id": "mn-track1", "title": "TRACK: Program", "kind": "track"},
        ]

    def tearDown(self) -> None:
        os.environ.pop("AGENT_DO_HOME", None)
        self.tmp.cleanup()

    def test_validator_holds_the_line(self) -> None:
        row = self.rows[0]
        self.assertEqual(digest_lib.validate("Build the first thing.", row), "Build the first thing")
        self.assertIsNone(digest_lib.validate("x" * (digest_lib.DIGEST_MAX_CHARS + 1), row))
        self.assertIsNone(digest_lib.validate("first ready thing", row), "the title is not a digest")
        self.assertIsNone(digest_lib.validate("Do mn-aaaaaa now", row), "no ids")
        self.assertIsNone(digest_lib.validate("two\nlines", row))
        self.assertIsNone(digest_lib.validate(None, row))

    def test_generate_writes_cache_and_apply_reads_it(self) -> None:
        calls = []
        def caller(prompt):
            calls.append(prompt)
            return {"mn-aaaaaa": "Make the first thing real", "mn-bbbbbb": "y" * 200}, "stub-model"
        out = digest_lib.generate("proj", self.rows[:2], caller=caller)
        self.assertEqual(out["written"], 1)
        self.assertEqual(out["failed"], 1, "the long one fails after its shorten retry")
        self.assertEqual(len(calls), 2, "one batch call plus one strict retry")
        self.assertIn("Previous answers", calls[1])
        report = digest_lib.apply("proj", self.rows)
        self.assertEqual(self.rows[0]["digest"], "Make the first thing real")
        self.assertIsNone(self.rows[1]["digest"])
        self.assertIsNone(self.rows[2]["digest"], "tracks never get digests")
        self.assertEqual(report["ready"], 1)
        self.assertEqual(report["missing"], 0, "a failed row is not retried until its content changes")
        # content change invalidates
        self.rows[0]["description"] = "Changed."
        report = digest_lib.apply("proj", self.rows)
        self.assertIsNone(self.rows[0]["digest"])
        self.assertEqual([r["id"] for r in report["missing_rows"]], ["mn-aaaaaa"])

    def test_plan_reports_gaps_without_reattaching_rows(self) -> None:
        digest_lib.generate(
            "proj",
            self.rows[:1],
            caller=lambda prompt: ({"mn-aaaaaa": "Make the first thing real"}, "stub-model"),
        )
        rows = [dict(row) for row in self.rows]
        rows[0]["digest"] = "Make the first thing real"
        before = json.dumps(rows, sort_keys=True)
        report = digest_lib.plan("proj", rows)
        self.assertEqual(report["ready"], 1)
        self.assertEqual(report["missing"], 1)
        self.assertEqual(json.dumps(rows, sort_keys=True), before)

    def test_chunking_is_byte_bounded(self) -> None:
        many = [{"id": f"mn-{i:06d}", "title": "t" * 40, "description": "d" * 400, "kind": "item"} for i in range(30)]
        one = len(digest_lib._item_block(many[0]).encode("utf-8")) + 2
        chunks = digest_lib.chunk_by_bytes(many, one * 7)
        self.assertTrue(all(len(c) <= 7 for c in chunks))
        self.assertEqual(sum(len(c) for c in chunks), 30)
        # and never more items per call than the measured cap, whatever the bytes allow
        big = digest_lib.chunk_by_bytes(many * 3, 10**9)
        self.assertTrue(all(len(c) <= digest_lib.DIGESTS_PER_CALL for c in big))
        self.assertEqual(sum(len(c) for c in big), 90)

    def test_failed_call_leaves_titles_and_invents_nothing(self) -> None:
        def caller(prompt):
            raise RuntimeError("no credential")
        out = digest_lib.generate("proj", self.rows[:2], caller=caller)
        self.assertEqual(out["written"], 0)
        cache = digest_lib.load_cache("proj")
        self.assertTrue(all(v["digest"] is None and v["failed"] == "no_credential" and v["transient"] for v in cache.values()))
        # transient: inside the cooldown the rows are not asked again; after it they are
        report = digest_lib.apply("proj", self.rows[:2])
        self.assertEqual(report["missing"], 0)
        for v in cache.values():
            v["failed_at"] = "2000-01-01T00:00:00Z"
        digest_lib.save_cache("proj", cache)
        report = digest_lib.apply("proj", self.rows[:2])
        self.assertEqual(report["missing"], 2)


class SummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(); os.environ["AGENT_DO_HOME"] = self.tmp.name
        self.row = {"id": "mn-aaaaaa", "title": "First ready thing", "description": "Make the first thing.", "status": "open", "kind": "item"}
    def tearDown(self) -> None:
        os.environ.pop("AGENT_DO_HOME", None); self.tmp.cleanup()
    def test_summary_generated_once_then_cached_until_content_changes(self) -> None:
        calls = []
        def caller(prompt): calls.append(prompt); return "It is the first thing.\n\nMake it, then it is done.", "stub"
        a = digest_lib.summarize("proj", self.row, caller=caller)
        self.assertFalse(a["cached"]); self.assertEqual(a["summary"].count("\n\n"), 1)
        b = digest_lib.summarize("proj", self.row, caller=caller)
        self.assertTrue(b["cached"]); self.assertEqual(len(calls), 1)
        self.row["description"] = "Changed."
        c = digest_lib.summarize("proj", self.row, caller=caller)
        self.assertFalse(c["cached"]); self.assertEqual(len(calls), 2)
        cache = digest_lib.load_cache("proj"); self.assertIn("summary", cache["mn-aaaaaa"])
    def test_summary_never_exceeds_the_cap(self) -> None:
        long = ("This sentence is here to make the summary far too long for the column. " * 12).strip()
        calls = []
        def caller(prompt): calls.append(prompt); return long, "stub"
        out = digest_lib.summarize("proj", self.row, caller=caller)
        self.assertLessEqual(len(out["summary"]), digest_lib.SUMMARY_MAX_CHARS)
        self.assertTrue(out["summary"].endswith("."), "cut at a sentence end")
        self.assertEqual(len(calls), 2, "one shorten pass before the trim")

    def test_ask_cites_only_known_ids(self) -> None:
        rows = [{"id": "mn-aaaaaa", "title": "First", "kind": "item", "effective": "ready"}, {"id": "mn-bbbbbb", "title": "Second", "kind": "item", "effective": "done"}]
        out = digest_lib.ask(rows, "  which one is done?  ", caller=lambda prompt: ("mn-bbbbbb is done; mn-zzzzzz is not on the board.", "stub"))
        self.assertEqual(out["cited"], ["mn-bbbbbb"])
        self.assertIn("QUESTION: which one is done?", digest_lib.ask_prompt(rows, "which one is done?"))
        def boom(prompt): raise RuntimeError("timed out")
        self.assertEqual(digest_lib.ask(rows, "x", caller=boom)["error"], "timeout")

    def test_summary_failure_invents_nothing(self) -> None:
        def caller(prompt): raise RuntimeError("no credential")
        out = digest_lib.summarize("proj", self.row, caller=caller)
        self.assertIsNone(out["summary"]); self.assertEqual(out["error"], "no_credential", "a code, never the exception text")
        self.assertIsNone(digest_lib.validate_summary("- a bullet list"))


class RegistryAndHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        os.environ["AGENT_DO_HOME"] = str(self.home)
        self.root = make_board(Path(self.tmp.name) / "proj")

    def tearDown(self) -> None:
        os.environ.pop("AGENT_DO_HOME", None)
        self.tmp.cleanup()

    def test_slug_collisions_take_the_parent_name(self) -> None:
        slug, fresh = serve_lib.register_board(self.root)
        self.assertEqual((slug, fresh), ("proj", True))
        other = Path(self.tmp.name) / "elsewhere" / "proj"
        other.mkdir(parents=True)
        slug2, fresh2 = serve_lib.register_board(other)
        self.assertEqual((slug2, fresh2), ("elsewhere--proj", True))
        self.assertEqual(serve_lib.register_board(self.root), ("proj", False))

    def test_registry_caches_public_federation_identity(self) -> None:
        (self.root / ".manna" / "federation.yaml").write_text(
            "version: 1\n"
            "board_id: mb-11111111111111111111111111111111\n"
            "relations: []\n",
            encoding="utf-8",
        )
        slug, _ = serve_lib.register_board(self.root)
        self.assertEqual(
            serve_lib.load_registry()[slug]["board_id"],
            "mb-11111111111111111111111111111111",
        )

    def test_machine_added_marker_is_honored_and_never_in_code(self) -> None:
        self.assertNotIn("[ADA]", board_lib.DECISION_MARKERS)
        with (self.root / ".manna" / "issues.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps({"id": "mn-named1", "title": "[Ada] Rule on the named thing", "status": "open", "blocked_by": [], "created_at": "2026-08-02T00:00:00Z", "updated_at": "2026-08-04T00:00:00Z"}) + "\n"
            )
        before = board_lib.summary(self.root, serve_lib.decision_markers())["decisions"]
        with self.assertRaises(ValueError):
            serve_lib.add_decision_marker("ADA")
        serve_lib.add_decision_marker("[ADA]")
        serve_lib.add_decision_marker("[ada]")
        self.assertEqual(serve_lib.load_registry_file()["decision_markers"], ["[ADA]"])
        self.assertEqual(board_lib.summary(self.root, serve_lib.decision_markers())["decisions"], before + 1)
        serve_lib.register_board(self.root)
        self.assertEqual(serve_lib.load_registry_file()["decision_markers"], ["[ADA]"], "registering a board keeps the markers")

    def test_scan_finds_nested_boards_and_skips_noise(self) -> None:
        base = Path(self.tmp.name) / "estate"
        (base / "a" / ".manna").mkdir(parents=True)
        (base / "a" / "sub" / ".manna").mkdir(parents=True)
        (base / "node_modules" / "x" / ".manna").mkdir(parents=True)
        (base / "deep" / "1" / "2" / "3" / ".manna").mkdir(parents=True)
        found = {p.relative_to(base).as_posix() for p in serve_lib.scan_boards(base)}
        self.assertEqual(found, {"a", "a/sub"})

    def test_index_glance_reads_coord_per_board(self) -> None:
        serve_lib.register_board(self.root)
        stub = make_stub_agent_do(Path(self.tmp.name))
        original, serve_lib.AGENT_DO = serve_lib.AGENT_DO, stub
        try:
            serve_lib.CACHE.bundles.clear()
            fast = serve_lib.boards_index(fast=True)
            self.assertEqual(fast["building"], 1, "cold cache: presence not read yet")
            self.assertIsNone(fast["boards"][0]["coord"], "null, never a fake zero")
            index = serve_lib.boards_index()
            self.assertEqual(index["building"], 0)
            row = index["boards"][0]
            self.assertEqual(row["coord"]["needs_you"], 1)
            self.assertEqual(row["coord"]["working"], 1)
            self.assertEqual(row["coord"]["here"], 3)
            self.assertEqual(row["coord"]["gone"], 1)
            self.assertEqual(index["totals"]["needs_you"], 1)
            # presence runs on a cadence: inside the window the same bundle answers
            root = self.root.resolve()
            first = serve_lib.CACHE.bundle(root)
            self.assertIs(serve_lib.CACHE.bundle(root), first)
            self.assertIn("coord:" + first["digest"], serve_lib.CACHE.signature(root))
            later = serve_lib.CACHE.bundle(root, now=first["fetched_at"] + serve_lib.COORD_REFRESH_SECONDS + 1)
            self.assertIsNot(later, first)
            self.assertEqual(later["digest"], first["digest"], "same presence, same digest: no push")
        finally:
            serve_lib.AGENT_DO = original
            serve_lib.CACHE.bundles.clear()

    def test_act_endpoint_runs_manna_verbs_under_the_daemon_identity(self) -> None:
        serve_lib.register_board(self.root)
        stub = make_stub_agent_do(Path(self.tmp.name))
        log = Path(self.tmp.name) / "stub.log"
        os.environ["STUB_LOG"] = str(log)
        original, serve_lib.AGENT_DO = serve_lib.AGENT_DO, stub
        server = ThreadingHTTPServer(("127.0.0.1", 0), serve_lib.Handler)
        server.daemon_threads = True; server.stopping = False; server.started_at = "test"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def post(path, payload):
            req = urllib.request.Request(base + path, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.status, json.loads(resp.read())
            except urllib.error.HTTPError as err:
                return err.code, json.loads(err.read() or b"{}")

        try:
            token = serve_lib.ACT_TOKEN
            self.assertEqual(post("/proj/api/act", {"action": "fix"})[0], 403, "no token, no write")
            self.assertEqual(post("/proj/api/act", {"action": "nope", "token": token})[0], 409)
            status, d = post("/proj/api/act", {"action": "close", "id": "mn-aaaaaa", "token": token})
            self.assertEqual(status, 200, d); self.assertTrue(d["ok"]); self.assertEqual([st["argv"][1] for st in d["steps"]], ["claim", "done"])
            status, d = post("/proj/api/act", {"action": "delete", "id": "mn-d0ea11", "token": token})
            self.assertEqual(status, 200, d); self.assertTrue(d.get("needs_confirm"), "delete asks first")
            status, d = post("/proj/api/act", {"action": "delete", "id": "mn-d0ea11", "token": token, "confirm": True})
            self.assertTrue(d["ok"], d)
            status, d = post("/proj/api/act", {"action": "close", "id": "mn-10c4ed", "token": token})
            self.assertEqual(status, 409); self.assertFalse(d["ok"]); self.assertIn("another session", d["steps"][-1]["stderr"])
            status, d = post("/proj/api/act", {"action": "sync", "token": token}); self.assertTrue(d["ok"])
            ran = log.read_text()
            ident = serve_lib.serve_identity()["session_id"]
            self.assertTrue(ident.startswith("serve-"))
            self.assertIn(f"manna claim mn-aaaaaa|{ident}", ran)
            self.assertIn(f"manna delete mn-d0ea11|{ident}", ran)
            self.assertIn("manna sync|", ran)
            self.assertEqual(ran.count("manna delete mn-d0ea11"), 1, "delete ran once, after the confirm")
            self.assertEqual(oct(serve_lib.identity_path().stat().st_mode & 0o777), "0o600")
        finally:
            serve_lib.AGENT_DO = original
            os.environ.pop("STUB_LOG", None)
            server.stopping = True; server.shutdown(); server.server_close()

    def test_http_surface(self) -> None:
        serve_lib.register_board(self.root)
        server = ThreadingHTTPServer(("127.0.0.1", 0), serve_lib.Handler)
        server.daemon_threads = True
        server.stopping = False
        server.started_at = "test"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def get(path: str) -> tuple[int, bytes, str]:
            try:
                with urllib.request.urlopen(base + path, timeout=5) as resp:
                    return resp.status, resp.read(), resp.headers.get("Content-Type", "")
            except urllib.error.HTTPError as err:
                return err.code, err.read(), err.headers.get("Content-Type", "")

        try:
            status, body, _ = get("/api/health")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["server"], "manna-serve")

            status, body, _ = get("/api/boards")
            index = json.loads(body)
            self.assertEqual([b["slug"] for b in index["boards"]], ["proj"])
            self.assertEqual(index["boards"][0]["decisions"], 2)

            status, body, ctype = get("/proj")
            self.assertEqual(status, 200)
            self.assertIn("text/html", ctype)
            self.assertIn(b'id="board-list"', body)
            self.assertIn(b'data-sheet="coord"', body)

            status, body, _ = get("/proj/api/state")
            state = json.loads(body)
            self.assertEqual(state["slug"], "proj")
            self.assertFalse({"claim_token_hash", "legacy_migration"} & nested_keys(state))

            # No document viewer: the page hands out the handoff path, never the file.
            status, _, _ = get("/proj/handoff?path=.handoff/01-mn-aaaaaa-first.md")
            self.assertEqual(status, 404)
            self.assertNotIn("work order body", body.decode())

            status, _, _ = get("/nope")
            self.assertEqual(status, 404)

            # DNS rebinding: a foreign Host header is refused everywhere
            for host in ("evil.example", "evil.example:80", "127.0.0.1.evil.example"):
                req = urllib.request.Request(base + "/api/boards", headers={"Host": host})
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        self.fail(f"{host} was served: {resp.status}")
                except urllib.error.HTTPError as err:
                    self.assertEqual(err.code, 403, host)
            req = urllib.request.Request(base + "/api/boards", headers={"Origin": "http://evil.example"})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(caught.exception.code, 403)
            req = urllib.request.Request(base + "/api/health", headers={"Origin": base})
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
            for host in ("localhost", f"localhost:{server.server_address[1]}", "[::1]:1", "127.0.0.1"):
                req = urllib.request.Request(base + "/api/health", headers={"Host": host})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self.assertEqual(resp.status, 200, host)
            status, _, _ = get("/proj/api/summary?id=mn-nope")
            self.assertEqual(status, 404)
            original_flag, original_caller = serve_lib.DIGESTS_ENABLED, digest_lib.default_summary_caller
            serve_lib.DIGESTS_ENABLED = True
            digest_lib.default_summary_caller = lambda prompt: ("A short explanation.", "stub")
            try:
                status, body, _ = get("/proj/api/summary?id=mn-aaaaaa")
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["summary"], "A short explanation.")
            finally:
                serve_lib.DIGESTS_ENABLED, digest_lib.default_summary_caller = original_flag, original_caller
            original_flag, original_ask = serve_lib.DIGESTS_ENABLED, digest_lib.default_ask_caller
            serve_lib.DIGESTS_ENABLED = True
            digest_lib.default_ask_caller = lambda prompt: ("mn-aaaaaa covers it.", "stub")
            try:
                status, body, _ = get("/proj/api/ask?q=does+anything+cover+the+first+thing")
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["cited"], ["mn-aaaaaa"])
            finally:
                serve_lib.DIGESTS_ENABLED, digest_lib.default_ask_caller = original_flag, original_ask

            status, app, ctype = get("/static/app.js")
            self.assertEqual(status, 200)
            self.assertIn("javascript", ctype)
            self.assertIn(b"RELATIONS", app)
            self.assertIn(b"r.summary", app)
        finally:
            server.stopping = True
            server.shutdown()
            server.server_close()


class ServeRegressionTests(unittest.TestCase):
    """The mn-c6e3ad regression set: enrichment must reach every rendered
    bucket, a page must never wait on reconcile, unknown coordination must
    say unknown, one presence snapshot signs and fills a state, concurrent
    requests share one derive, and failure answers instead of disconnecting.
    All six held green through the live regressions; these pin the fixes."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        os.environ["AGENT_DO_HOME"] = str(self.home)
        self.root = make_board(Path(self.tmp.name) / "proj").resolve()
        self.stub = make_stub_agent_do(Path(self.tmp.name))
        self.original_agent_do = serve_lib.AGENT_DO
        serve_lib.AGENT_DO = self.stub
        self.original_cache = serve_lib.CACHE
        self.cache = serve_lib.BoardCache()
        serve_lib.CACHE = self.cache
        serve_lib.register_board(self.root)

    def tearDown(self) -> None:
        serve_lib.AGENT_DO = self.original_agent_do
        serve_lib.CACHE = self.original_cache
        os.environ.pop("AGENT_DO_HOME", None)
        self.tmp.cleanup()

    def seed_digests(self, slug: str = "proj") -> None:
        state = board_lib.derive(self.root, None)
        rows = [r for r in state["all"] if r.get("kind") != "track"]
        lines = {r["id"]: f"One line about item number {i}." for i, r in enumerate(rows)}
        digest_lib.generate(slug, rows, caller=lambda prompt: (lines, "stub-model"))

    def test_digests_reach_every_rendered_bucket(self) -> None:
        self.seed_digests()
        _, state = self.cache.state("proj", self.root)
        buckets = {
            "now": state["now"],
            "next": state["next"],
            "decisions": state["decisions"],
            "dreams": state["dreams"],
            "unlayered": state["unlayered"],
            "waves": [r for wave in state["waves"] for r in wave["items"]],
            "tracks": [r for track in state["tracks"] for r in track["items"] if r.get("kind") != "track"],
        }
        for name, rows in buckets.items():
            self.assertTrue(rows, f"{name} is empty; the fixture no longer exercises it")
            for row in rows:
                self.assertTrue(row.get("digest"), f"{name} row {row['id']} lost its digest")
        # the mechanism, not just the symptom: buckets alias the same objects
        by_id = {r["id"]: r for r in state["all"]}
        self.assertIs(state["now"][0], by_id[state["now"][0]["id"]])
        self.assertIs(state["waves"][0]["items"][0], by_id[state["waves"][0]["items"][0]["id"]])

    def test_full_state_reads_cached_drift_and_reconciles_in_background(self) -> None:
        derive_calls: list[dict] = []
        original_derive = board_lib.derive

        def spy_derive(root, agent_do=None, markers=board_lib.DECISION_MARKERS, live=False, **kw):
            derive_calls.append({"live": live, "agent_do": agent_do, "coord": kw.get("coord")})
            return original_derive(root, agent_do, markers, live=live, **kw)

        gate = threading.Event()
        drift_threads: list[str] = []
        original_live_drift = board_lib.live_drift

        def gated_drift(root, agent_do):
            drift_threads.append(threading.current_thread().name)
            gate.wait(timeout=30)
            return original_live_drift(root, agent_do)

        board_lib.derive = spy_derive
        board_lib.live_drift = gated_drift
        try:
            sig, state = self.cache.state("proj", self.root)
            self.assertEqual(len(derive_calls), 1)
            self.assertFalse(derive_calls[0]["live"], "the full state must take the cached-drift path")
            self.assertIsNone(derive_calls[0]["agent_do"], "coordination comes from the serve bundle, never a second fetch")
            self.assertIsNotNone(derive_calls[0]["coord"], "the signing snapshot feeds the payload")
            self.assertEqual(state["drift"]["source"], "file", "before the background reconcile lands")
            self.assertEqual(len(drift_threads), 1)
            self.assertTrue(drift_threads[0].startswith("drift:"), f"reconcile ran on {drift_threads[0]}, not in background")
            stamp = self.cache.drift_stamps.get(str(self.root), 0)
            gate.set()
            self.cache.drift_jobs[str(self.root)][1].join(timeout=30)
            self.assertGreater(self.cache.drift_stamps.get(str(self.root), 0), stamp)
            sig2, state2 = self.cache.state("proj", self.root)
            self.assertNotEqual(sig, sig2, "the landed drift re-signs the stream")
            self.assertEqual(state2["drift"]["source"], "reconcile")
            self.assertEqual(state2["drift"]["count"], 2)
            self.assertEqual(state2["drift"]["file"]["count"], 1, "the written file's age stays beside the live read")
        finally:
            board_lib.derive = original_derive
            board_lib.live_drift = original_live_drift

    def test_fast_state_ships_unknown_coordination_never_zeros(self) -> None:
        cold = serve_lib.fast_state("proj", self.root)
        self.assertTrue(cold["building"])
        self.assertIsNone(cold["peers"], "unread peers are unknown, not an empty list")
        self.assertIsNone(cold["coord"])
        self.assertIsNone(cold["attention"])
        self.assertIn("digests", cold)
        claimed = next(r for r in cold["all"] if r["id"] == "mn-cccccc")
        self.assertEqual(claimed["claimant"]["liveness"], "unknown")
        self.assertEqual(claimed["claimant"]["attention"], "unknown")
        in_now = next(r for r in cold["now"] if r["id"] == "mn-cccccc")
        self.assertEqual(in_now["claimant"]["attention"], "unknown", "the marking reaches the rendered bucket")
        # a warm bundle folds in whole, through the same canonical core fold
        self.cache.bundle(self.root)
        warm = serve_lib.fast_state("proj", self.root)
        self.assertTrue(warm["building"], "commits and live drift are still on their way")
        self.assertEqual(len(warm["peers"]), 4)
        self.assertEqual(warm["attention"]["needs-user"], 1)
        self.assertTrue(warm["coord"]["claims"])
        claimed = next(r for r in warm["all"] if r["id"] == "mn-cccccc")
        self.assertEqual(claimed["claimant"]["attention"], "needs-user")
        self.assertIsNotNone(warm["coord_refreshed_ago"])

    def test_signature_holds_still_while_only_the_clock_moves(self) -> None:
        coord = dict(board_lib.EMPTY_COORD)
        young = [{"agent_id": "session-deadbeefdead", "status": "active", "age": "3s ago", "age_seconds": 3,
                  "pulse": {"status": "working", "latest_prompt": "fix it", "updated_at": "2026-08-31T00:00:00Z", "turns": 4}}]
        old = [{"agent_id": "session-deadbeefdead", "status": "active", "age": "9m ago", "age_seconds": 540,
                "pulse": {"status": "working", "latest_prompt": "fix it", "updated_at": "2026-08-31T00:09:00Z", "turns": 4}}]
        self.assertEqual(serve_lib.coord_digest(young, coord), serve_lib.coord_digest(old, coord),
                         "unchanged peers must not re-sign as their ages tick")
        changed = [{**young[0], "pulse": {**young[0]["pulse"], "status": "needs-user"}}]
        self.assertNotEqual(serve_lib.coord_digest(young, coord), serve_lib.coord_digest(changed, coord),
                            "a real attention change must re-sign")

    def test_concurrent_state_requests_share_one_derive(self) -> None:
        gate = threading.Event()
        count: list[int] = []
        original = board_lib.derive

        def gated_derive(root, agent_do=None, markers=board_lib.DECISION_MARKERS, live=False, **kw):
            count.append(1)
            gate.wait(timeout=30)
            return original(root, agent_do, markers, live=live, **kw)

        board_lib.derive = gated_derive
        try:
            results: list[tuple] = []
            workers = [threading.Thread(target=lambda: results.append(self.cache.state("proj", self.root))) for _ in range(5)]
            for worker in workers:
                worker.start()
            gate.set()
            for worker in workers:
                worker.join(timeout=60)
            self.assertEqual(len(results), 5)
            self.assertEqual(len(count), 1, "five concurrent requests, one derive")
            self.assertTrue(all(r[0] == results[0][0] for r in results), "every request left with the shared state")
        finally:
            board_lib.derive = original

    def test_overlay_coordination_matches_core_fetched_coordination(self) -> None:
        peers = board_lib.coord_peers(self.root, self.stub)
        coord = board_lib.coord_snapshot(self.root, self.stub, peers)
        via_overlay = board_lib.derive(self.root, None, coord={"peers": peers, "coord": coord})
        via_core = board_lib.derive(self.root, self.stub)
        for key in ("peers", "attention", "coord"):
            self.assertEqual(via_overlay[key], via_core[key], key)
        self.assertEqual([r["id"] for r in via_overlay["now"]], [r["id"] for r in via_core["now"]])
        self.assertEqual(via_overlay["now"][0]["claimant"], via_core["now"][0]["claimant"])

    def test_state_failure_answers_structured_instead_of_disconnecting(self) -> None:
        serve_lib.register_board(self.root)
        with (self.root / ".manna" / "issues.jsonl").open("a", encoding="utf-8") as stream:
            stream.write('{"id":"mn-broken"}\n')
        server = ThreadingHTTPServer(("127.0.0.1", 0), serve_lib.Handler)
        server.daemon_threads = True
        server.stopping = False
        server.started_at = "test"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            for path in ("/proj/api/state", "/proj/api/state?fast=1"):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(base + path, timeout=30)
                self.assertEqual(caught.exception.code, 500, path)
                payload = json.loads(caught.exception.read())
                self.assertIn("malformed", payload["error"], path)
        finally:
            server.stopping = True
            server.shutdown()
            server.server_close()

    def test_stale_binary_is_refused_with_the_rebuild_command(self) -> None:
        scratch = Path(self.tmp.name) / "binaries"
        scratch.mkdir()
        binary = scratch / "manna-core"
        binary.write_text("#!/bin/sh\n", encoding="utf-8")
        source = scratch / "state.rs"
        source.write_text("// src\n", encoding="utf-8")
        os.utime(binary, (1000, 1000))
        os.utime(source, (2000, 2000))
        error = board_lib._stale_binary_error(binary, [source])
        self.assertIsNotNone(error)
        self.assertIn("state.rs", error)
        self.assertIn("cargo build --release", error)
        os.utime(binary, (3000, 3000))
        self.assertIsNone(board_lib._stale_binary_error(binary, [source]), "a fresh binary passes")


class CliLifecycleTests(unittest.TestCase):
    def test_serve_registers_starts_prints_url_and_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            root = make_board(Path(tmp) / "proj")
            env = {**os.environ, "AGENT_DO_HOME": str(home)}
            wrapper = REPO / "tools" / "agent-manna" / "agent-manna"
            try:
                first = subprocess.run([str(wrapper), "serve", "--json", "--port", "0"], cwd=root, env=env, capture_output=True, text=True, timeout=60)
                self.assertEqual(first.returncode, 0, first.stderr)
                payload = json.loads(first.stdout)
                self.assertEqual(payload["daemon"], "started")
                self.assertEqual(payload["slug"], "proj")
                self.assertTrue(payload["url"].endswith("/proj"))
                port = payload["port"]

                second = subprocess.run([str(wrapper), "serve", "--json", "--port", "0"], cwd=root, env=env, capture_output=True, text=True, timeout=60)
                again = json.loads(second.stdout)
                self.assertEqual(again["daemon"], "running")
                self.assertEqual(again["port"], port)

                with urllib.request.urlopen(f"http://127.0.0.1:{port}/proj/api/state", timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read())["name"], "proj")

                outside = subprocess.run([str(wrapper), "serve", "--json"], cwd=tmp, env=env, capture_output=True, text=True, timeout=60)
                self.assertEqual(outside.returncode, 2)
                self.assertIn("no .manna", json.loads(outside.stdout)["error"])

                status = subprocess.run([str(wrapper), "serve", "--status", "--json"], cwd=root, env=env, capture_output=True, text=True, timeout=60)
                self.assertTrue(json.loads(status.stdout)["running"])

                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read())["source"], serve_lib.SOURCE_HASH)
            finally:
                stopped = subprocess.run([str(wrapper), "serve", "--stop", "--json"], cwd=root, env=env, capture_output=True, text=True, timeout=60)
            self.assertIn(json.loads(stopped.stdout)["status"], {"stopped", "not_running"})
            status = subprocess.run([str(wrapper), "serve", "--status", "--json"], cwd=root, env=env, capture_output=True, text=True, timeout=60)
            self.assertFalse(json.loads(status.stdout)["running"])

    def test_help_lists_serve_for_the_drift_gate(self) -> None:
        wrapper = REPO / "tools" / "agent-manna" / "agent-manna"
        out = subprocess.run([str(wrapper), "--help"], capture_output=True, text=True, timeout=30).stdout
        self.assertRegex(out, r"\n  serve\s{2,}", msg=out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
