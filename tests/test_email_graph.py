#!/usr/bin/env python3
"""Fixture-only coverage, Graph pagination, authentication and CLI regressions."""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import email_query as email
from email_graph import GraphError, GraphMailbox, GRAPH_SEARCH_CEILING
from test_email import write_envelope_index_fixture


def args(command="search", **overrides):
    parsed = email.build_parser().parse_args([command, *(["--id", "db:100"] if command in {"get", "export"} else [])])
    parsed.query_text = ""
    for key, value in overrides.items():
        setattr(parsed, key, value)
    return parsed


def row(remote_id="one", **overrides):
    result = {
        "id": remote_id, "parentFolderId": "inbox-id", "subject": "SutiProcure sandbox",
        "receivedDateTime": "2026-10-22T10:00:00Z", "isRead": False,
        "from": {"emailAddress": {"name": "Support", "address": "support@example.test"}},
        "body": {"contentType": "text", "content": "Your code is 731902. Open https://example.test/login?token=fixture"},
    }
    result.update(overrides)
    return result


class FixtureGraph(GraphMailbox):
    """Fake only the HTTP boundary; production provider/routing code executes."""
    def __init__(self, responses=None):
        super().__init__()
        self.target = "work@example.test"
        self.missing = []
        self.sdk_available = True
        self.calls = []
        self.responses = responses
        self.rows = [row()]
        self.roles = ["Mail.Read"]

    def _get(self, url, *, params=None, raw=False):
        self.calls.append((url, params, raw))
        if self.responses is not None:
            result = self.responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        if raw:
            return "From: support@example.test\r\nSubject: SutiProcure sandbox\r\n\r\nYour code is 731902.\r\n"
        if url.endswith("/mailFolders/inbox"):
            return {"id": "inbox-id", "displayName": "Inbox"}
        if params and "$count" in params:
            return {"@odata.count": len(self.rows), "value": []}
        if "/messages/" in url:
            return dict(self.rows[0])
        return {"value": [dict(item) for item in self.rows]}


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "Envelope Index"
        write_envelope_index_fixture(self.path)
        self.env = patch.dict(os.environ, {"AGENT_EMAIL_ENVELOPE_INDEX": str(self.path)}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(email.QUERY_CONTEXT.clear)
        now = int(time.time())
        day = 24 * 60 * 60  # Unit conversion, not a configured freshness bound.
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE messages SET date_received=? WHERE ROWID=100", (now - day,))
            conn.execute("UPDATE messages SET date_received=? WHERE ROWID=101", (now,))
            conn.execute("INSERT INTO mailboxes (ROWID,url) VALUES (2,'ews://work/Inbox')")
            for mid, stamp in [(200, now - 100 * day), (201, now - 99 * day)]:
                conn.execute("INSERT INTO messages (ROWID,subject,sender,date_received,mailbox) VALUES (?,30,10,?,2)", (mid, stamp))

    def source(self, graph=None):
        source = email.MailboxSource(email.MacMailSource(), graph)
        self.addCleanup(source.close)
        return source

    def test_measured_cadence_is_per_account_and_month_counts_preserved(self):
        source = self.source()
        coverage = {item["name"]: item for item in source.coverage()}
        self.assertEqual(coverage["imap://primary"]["freshness"], "fresh")
        self.assertEqual(coverage["ews://work"]["freshness"], "stale")
        self.assertEqual(coverage["ews://work"]["cadence_seconds"], 24 * 60 * 60)
        self.assertEqual(sum(coverage["ews://work"]["monthly_counts"].values()), 2)

    def test_unknown_cadence_never_claims_freshness(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM messages WHERE ROWID=200")
        work = next(item for item in self.source().coverage() if item["name"] == "ews://work")
        self.assertEqual(work["freshness"], "unknown")
        self.assertIsNone(work["cadence_seconds"])

    def test_snapshot_includes_committed_wal_without_writing_original(self):
        writer = sqlite3.connect(self.path)
        self.addCleanup(writer.close)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("UPDATE messages SET date_received=? WHERE ROWID=201", (int(time.time()),))
        writer.commit()
        paths = [Path(str(self.path) + suffix) for suffix in ("", "-wal", "-shm")]
        before = {p: p.read_bytes() for p in paths}
        source = self.source()
        work = next(item for item in source.coverage() if item["name"] == "ews://work")
        self.assertEqual(work["freshness"], "fresh")
        self.assertEqual(before, {p: p.read_bytes() for p in paths})
        self.assertNotEqual(source.local.conn.execute("PRAGMA database_list").fetchone()[2], str(self.path))

    def test_stale_zero_is_structured_failure_and_text_warning(self):
        source = self.source()
        out, err = io.StringIO(), io.StringIO()
        with patch.object(email, "OUTPUT_JSON", False), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit):
                source.query_messages(args(account="ews://work", query_text="no such mail"))
        self.assertIn("coverage warning", err.getvalue())
        self.assertFalse(email.QUERY_CONTEXT["coverage_complete"])
        self.assertEqual(email.QUERY_CONTEXT["stale_accounts"][0]["name"], "ews://work")

    def test_fresh_scope_is_not_poisoned_by_other_stale_account(self):
        source = self.source()
        _, messages, _ = source.query_messages(args(account="imap://primary", query_text="absent"))
        self.assertEqual(messages, [])
        self.assertEqual(email.QUERY_CONTEXT["stale_accounts"], [])
        self.assertTrue(email.QUERY_CONTEXT["coverage_complete"])

    def test_stale_account_without_requested_local_folder_is_still_a_gap(self):
        source = self.source()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            source.query_messages(args(account="ews://work", mailbox="Missing local folder"))
        self.assertEqual(email.QUERY_CONTEXT["stale_accounts"][0]["name"], "ews://work")

    def test_graph_routing_uses_account_alias_and_postfilters_attachment_hits(self):
        graph = FixtureGraph()
        graph.rows.append(row("attachment-only", subject="Unrelated", body={"contentType": "text", "content": "nothing relevant"}))
        source = self.source(graph)
        _, messages, counts = source.query_messages(args(account=graph.target, query_text="sutiprocure"))
        self.assertEqual([m["id"] for m in messages], [graph.message_id("one")])
        self.assertEqual(email.project_message(messages[0])["source"], "graph")
        self.assertEqual(counts, (2, 2))
        self.assertTrue(email.QUERY_CONTEXT["coverage_complete"])
        self.assertTrue(email.QUERY_CONTEXT["stale_accounts"][0]["served_live"])

    def test_graph_failure_does_not_fall_back_to_local_rows(self):
        source = self.source(FixtureGraph([GraphError("graph_request_failed", status=403)]))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            source.query_messages(args(account="ews://work"))
        self.assertEqual(email.QUERY_CONTEXT["provider_errors"][0]["http_status"], 403)

    def test_missing_graph_creds_remain_an_explicit_gap(self):
        graph = FixtureGraph()
        graph.missing = ["AZURE_CLIENT_SECRET"]
        source = self.source(graph)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            source.query_messages(args(account=graph.target, query_text="sutiprocure"))
        self.assertEqual(email.QUERY_CONTEXT["provider_errors"][0]["error"], "graph_credentials_missing")

    def test_multi_account_results_keep_partial_coverage(self):
        source = self.source()
        with contextlib.redirect_stderr(io.StringIO()):
            _, messages, _ = source.query_messages(args(query_text="invoice"))
        self.assertTrue(messages)
        self.assertFalse(email.QUERY_CONTEXT["coverage_complete"])

    def test_snapshot_does_not_hide_stale_archive_after_inbox_count(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE mailboxes SET url='imap://archive/Archive' WHERE ROWID=2")
        source = self.source()
        with patch.object(email, "OUTPUT_JSON", True), contextlib.redirect_stdout(io.StringIO()) as out:
            email.handle_snapshot(source, args("snapshot", all_mailboxes=True))
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["coverage_complete"])
        self.assertEqual(payload["stale_accounts"][0]["name"], "imap://archive")

    def test_multiple_exchange_accounts_are_not_guessed(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT INTO mailboxes (url) VALUES ('ews://another/Inbox')")
        source = self.source(FixtureGraph())
        self.assertEqual(source.graph_account, "work@example.test")
        self.assertEqual(source.binding, "separate_live_account")

    def test_explicit_binding_and_remote_folder_not_in_index(self):
        graph = FixtureGraph()
        graph.local_account = "ews://work"
        source = self.source(graph)
        selected = source.selected_mailboxes(args(account=graph.target, mailbox="New remote folder"))
        self.assertEqual(selected, [{"account": "ews://work", "mailbox": "New remote folder"}])
        self.assertEqual(source.binding, "explicit")

    def test_unknown_account_refuses_instead_of_empty_success(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.source().query_messages(args(account="missing"))

    def test_status_reports_all_accounts_and_verified_graph_readiness(self):
        source = self.source(FixtureGraph())
        with patch.object(email, "OUTPUT_JSON", True), contextlib.redirect_stdout(io.StringIO()) as out:
            email.handle_status(source, args("status"))
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["accounts"]["count"], 2)
        self.assertTrue(payload["graph"]["live_search_ready"])
        self.assertEqual(payload["graph"]["roles"], ["Mail.Read"])

    def test_latest_wait_code_link_and_get_export_execute_graph_path(self):
        for command in ("latest", "wait", "code", "link", "get", "export"):
            with self.subTest(command=command):
                source = self.source(FixtureGraph())
                options = args(command, account="work@example.test", message_id=source.graph.message_id("one"))
                if command == "export":
                    options.format = "eml"
                with patch.object(email, "OUTPUT_JSON", True), contextlib.redirect_stdout(io.StringIO()) as out:
                    email.dispatch(source, options)
                payload = json.loads(out.getvalue())
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["message"]["source"], "graph")
                if command == "code":
                    self.assertEqual(payload["code"], "731902")
                if command == "link":
                    self.assertEqual(payload["link"], "https://example.test/login?token=fixture")
                if command == "get":
                    self.assertIn("From: support", payload["message"]["raw_source"])
                if command == "export":
                    self.assertIn("From: support", payload["content"])

    def test_get_does_not_cross_account_scope(self):
        source = self.source(FixtureGraph())
        options = args("get", account="imap://primary", message_id=source.graph.message_id("one"))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            email.handle_get(source, options)
        self.assertEqual(source.graph.calls, [])

    def test_indexed_work_message_resolves_exact_header_through_graph(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE messages SET global_message_id=9002 WHERE ROWID=201")
        graph = FixtureGraph()
        source = self.source(graph)
        options = args("get", account=graph.target, message_id="db:201")
        with patch.object(email, "OUTPUT_JSON", True), contextlib.redirect_stdout(io.StringIO()) as out:
            email.handle_get(source, options)
        self.assertEqual(json.loads(out.getvalue())["message"]["source"], "graph")
        query = next(params for _, params, _ in graph.calls if params and "$filter" in params)
        self.assertEqual(query["$filter"], "internetMessageId eq '<remote-hydrate@example.test>'")

    def test_wait_refreshes_the_index_snapshot(self):
        source = self.source()
        options = args("wait", account="imap://primary", subject_filter="Arrived after snapshot", timeout=1, interval=1)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE subjects SET subject='Arrived after snapshot' WHERE ROWID=31")
        _, message, _ = email.wait_for_message(source, options)
        self.assertEqual(message["id"], "db:101")

    def test_real_cli_reports_missing_credentials_with_json_coverage(self):
        env = dict(os.environ, PATH=os.defpath, AGENT_DO_CREDS_PLATFORM="unknown")
        result = subprocess.run(
            [sys.executable, str(ROOT / "lib/email_query.py"), "search", "sutiprocure", "--account", "ews://work"],
            env={**env, "AGENT_EMAIL_OUTPUT_JSON": "1"}, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["error"], "incomplete_coverage")
        self.assertEqual(payload["stale_accounts"][0]["name"], "ews://work")
        self.assertIn("AZURE_CLIENT_ID", payload["stale_accounts"][0]["provider_status"]["missing"])


class GraphTransportTests(unittest.TestCase):
    def test_o365_credentials_flow_observes_roles_without_persisting_tokens(self):
        graph = GraphMailbox()
        graph.missing = []
        graph.sdk_available = True
        claims = base64.urlsafe_b64encode(json.dumps({"roles": ["Mail.Read"]}).encode()).decode().rstrip("=")
        backend = unittest.mock.Mock()
        backend.get_access_token.return_value = {"secret": "fixture." + claims + ".signature"}
        account = unittest.mock.Mock()
        account.authenticate.return_value = True
        factory = unittest.mock.Mock(return_value=account)
        sdk = types.ModuleType("O365")
        sdk.Account = factory
        token = types.ModuleType("O365.utils.token")
        token.MemoryTokenBackend = lambda: backend
        with patch.dict(sys.modules, {"O365": sdk, "O365.utils.token": token}), patch.dict(os.environ, {
            "AZURE_CLIENT_ID": "fixture-client", "AZURE_CLIENT_SECRET": "fixture-secret", "AZURE_TENANT_ID": "fixture-tenant",
        }):
            graph._authenticate()
        self.assertEqual(factory.call_args.args[0], ("fixture-client", "fixture-secret"))
        self.assertEqual(factory.call_args.kwargs["auth_flow_type"], "credentials")
        self.assertEqual(factory.call_args.kwargs["tenant_id"], "fixture-tenant")
        self.assertIs(factory.call_args.kwargs["token_backend"], backend)
        self.assertEqual(graph.roles, ["Mail.Read"])
        self.assertNotIn("secret", json.dumps(graph.status()))

    def test_pagination_uses_whole_next_link_and_no_repeated_params(self):
        graph = FixtureGraph([
            {"value": [row()], "@odata.nextLink": "https://graph.microsoft.com/v1.0/users/work%40example.test/messages?$skiptoken=opaque"},
            {"value": [row("second")]},
        ])
        self.assertEqual(len(list(graph._pages(graph.root + "/messages", params={"$search": '"SutiProcure"'}))), 2)
        self.assertIsNone(graph.calls[1][1])
        self.assertIn("$skiptoken=opaque", graph.calls[1][0])

    def test_later_page_error_cannot_be_returned_as_partial_success(self):
        graph = FixtureGraph([
            {"value": [row()], "@odata.nextLink": "next"}, GraphError("graph_request_failed", status=429),
        ])
        with self.assertRaises(GraphError):
            list(graph._pages(graph.root + "/messages"))

    def test_pagination_loop_fails_closed(self):
        graph = FixtureGraph()
        graph.responses = [{"value": [], "@odata.nextLink": graph.root + "/messages"}]
        with self.assertRaisesRegex(GraphError, "pagination_loop"):
            list(graph._pages(graph.root + "/messages"))

    def test_malformed_page_is_a_typed_failure(self):
        graph = FixtureGraph([{"value": [None]}])
        with self.assertRaisesRegex(GraphError, "invalid_response"):
            list(graph._pages(graph.root + "/messages"))

    def test_untrusted_next_link_never_receives_auth(self):
        graph = GraphMailbox()
        graph.target = "work@example.test"
        for url in ("https://evil.test/v1.0/users/work@example.test/messages", "http://graph.microsoft.com/v1.0/users/work@example.test/messages", "https://graph.microsoft.com/v1.0/users/other@example.test/messages"):
            with patch.object(graph, "_authenticate") as authenticate, self.assertRaisesRegex(GraphError, "invalid_next_link"):
                graph._get(url)
            authenticate.assert_not_called()

    def test_count_failure_is_not_reported_as_zero(self):
        graph = FixtureGraph([{"value": [row()]}, {"value": []}])
        with self.assertRaisesRegex(GraphError, "count_unavailable"):
            graph.query(args(all_mailboxes=True))

    def test_search_provider_ceiling_is_reported_without_client_truncation(self):
        graph = FixtureGraph()
        graph.rows = [row(str(n)) for n in range(GRAPH_SEARCH_CEILING)]
        rows, _ = graph.query(args(query_text="SutiProcure", all_mailboxes=True, limit=1))
        self.assertEqual(len(rows), GRAPH_SEARCH_CEILING)
        self.assertTrue(graph.last_search["possibly_truncated"])
        self.assertIn("learn.microsoft.com", graph.last_search["authority"])

    def test_caller_limit_is_applied_after_filtering(self):
        graph = FixtureGraph()
        graph.rows = [row("unrelated", isRead=True), row("match", isRead=False), row("older", isRead=False)]
        rows, _ = graph.query(args(all_mailboxes=True, limit=1), matches=lambda r: not r["isRead"])
        self.assertEqual([r["id"] for r in rows], ["unrelated", "match"])

    def test_status_does_not_equate_configured_with_ready(self):
        graph = FixtureGraph([GraphError("graph_request_failed", status=401)])
        self.assertFalse(graph.status()["live_search_ready"])
        status = graph.status(probe=True)
        self.assertFalse(status["live_search_ready"])
        self.assertEqual(status["readiness"], "failed")

    def test_get_scope_is_checked_before_fetching_mime(self):
        graph = FixtureGraph()
        graph.rows = [row(parentFolderId="archive-id")]
        with self.assertRaisesRegex(GraphError, "outside_scope"):
            graph.get(graph.message_id("one"))
        self.assertFalse(any(call[2] for call in graph.calls))

    def test_http_error_text_is_not_exposed(self):
        graph = GraphMailbox()
        graph.target = "work@example.test"
        account = unittest.mock.Mock()
        account.con.get.side_effect = RuntimeError("SECRET should never escape")
        graph.account = account
        with self.assertRaises(GraphError) as caught:
            graph._get(graph.root + "/messages")
        self.assertNotIn("SECRET", str(caught.exception))


def run_tests():
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("Graph/coverage email tests failed")


if __name__ == "__main__":
    run_tests()
