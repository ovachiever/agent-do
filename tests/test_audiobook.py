#!/usr/bin/env python3
"""Offline safety and local-read contract tests; no Audible account required."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/agent-audiobook/agent-audiobook"


class AudiobookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = self.root / "Libation with spaces"
        self.export = self.root / "Library 日本語 ; $(touch nope).json"
        self.env = {**os.environ, "AGENT_LIBATION_BIN": str(self.engine),
                    "AGENT_DO_HOME": str(self.root / "state")}
        self.env.pop("LIBATION_MASTER_KEY", None)

    def fake_engine(self, output="LibationCli v14.2.2", code=0):
        # Doctor may invoke ONLY parser help; the version verb initializes state.
        self.engine.write_text("#!/usr/bin/env python3\nimport sys\n"
                               "assert sys.argv[1:] == ['--help']\n"
                               f"print({output!r}, file=sys.stderr)\n"
                               f"sys.exit({code})\n")
        self.engine.chmod(0o755)

    def call(self, *args):
        result = subprocess.run([str(TOOL), *args, "--json"], env=self.env,
                                capture_output=True, text=True)
        payload = json.loads(result.stdout)  # rejects extra JSON/progress
        self.assertEqual(result.returncode, 0 if payload["success"] else 1)
        self.assertEqual(result.stderr, "")
        return payload

    def rows(self):
        return [{"Account": "home", "Locale": "us", "AudibleProductId": "B012345678",
                 "Title": "A book 日本語", "BookStatus": "Liberated",
                 "IdentityTokens": "DO_NOT_ECHO", "LengthInMinutes": 10}]

    def write_export(self, rows):
        self.export.write_text(json.dumps(rows), encoding="utf-8")

    def test_missing_engine(self):
        self.assertEqual(self.call("doctor")["status"], "missing_engine")

    def test_supported_engine_without_state_access(self):
        self.fake_engine()
        result = self.call("doctor")
        self.assertEqual(result["version"], "14.2.2")
        self.assertEqual(result["credentials"]["session_readiness"], "not_checked")
        self.assertTrue(result["features"]["download"])
        self.assertFalse((self.root / "state").exists())

    def test_unsupported_and_prerelease_versions(self):
        for version in ("13.0.0", "14.2.20", "14.2.2.1", "14.2.2-beta"):
            with self.subTest(version=version):
                self.fake_engine("LibationCli v" + version)
                self.assertFalse(self.call("doctor")["success"])

    def test_failed_engine_cannot_claim_readiness(self):
        self.fake_engine("LibationCli v14.2.2", 3)
        self.assertEqual(self.call("doctor")["status"], "engine_probe_failed")

    def test_engine_output_and_secrets_are_not_forwarded(self):
        self.fake_engine("LIBATION_MASTER_KEY=DO_NOT_ECHO refresh_token=DO_NOT_ECHO", 3)
        self.env["LIBATION_MASTER_KEY"] = "DO_NOT_ECHO"
        result = self.call("doctor")
        self.assertNotIn("DO_NOT_ECHO", json.dumps(result))
        self.assertTrue(result["credentials"]["master_key_present"])
        self.assertFalse(result["credentials"]["master_key_validated"])

    def test_unknown_engine(self):
        self.fake_engine("Some other program")
        self.assertEqual(self.call("doctor")["status"], "unrecognized_engine")

    def test_unavailable_is_not_empty(self):
        self.assertEqual(self.call("snapshot")["error"], "library_unavailable")
        self.assertEqual(self.call("snapshot", "--export", str(self.export))["error"],
                         "library_unavailable")

    def test_empty_library(self):
        self.write_export([])
        result = self.call("snapshot", "--export", str(self.export))
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["total"], 0)

    def test_native_status_is_not_verification(self):
        self.write_export(self.rows())
        result = self.call("snapshot", "--export", str(self.export))
        self.assertEqual(result["entries"][0]["archive_state"], "unverified")
        self.assertNotIn("DO_NOT_ECHO", json.dumps(result))
        self.assertEqual(result["freshness"], "unknown")

    def test_account_marketplace_isolation(self):
        rows = self.rows()
        rows += [{**rows[0], "Account": "work"}, {**rows[0], "Locale": "uk"}]
        self.write_export(rows)
        result = self.call("snapshot", "--export", str(self.export),
                           "--account", "home", "--marketplace", "uk")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["entries"][0]["marketplace"], "uk")

    def test_invalid_exports(self):
        for data in ("not json", "{}", "[null]", '[{"Title": "incomplete"}]'):
            with self.subTest(data=data):
                self.export.write_text(data)
                self.assertEqual(self.call("snapshot", "--export", str(self.export))["error"],
                                 "invalid_export")

    def test_duplicate_identity_fails_closed(self):
        self.write_export(self.rows() * 2)
        self.assertEqual(self.call("snapshot", "--export", str(self.export))["error"],
                         "ambiguous_identity")

    def test_snapshot_does_not_run_engine_or_write(self):
        self.engine.write_text("#!/bin/sh\ntouch SHOULD_NOT_EXIST\nexit 99\n")
        self.engine.chmod(0o755)
        self.write_export(self.rows())
        before = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        self.call("snapshot", "--export", str(self.export))
        after = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((ROOT / "SHOULD_NOT_EXIST").exists())

    def test_json_flag_before_command(self):
        self.fake_engine()
        self.assertTrue(self.call("--json", "doctor")["success"])

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        import base64
        from fixtures_libation import ENGINE, PROBE, DECODE
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.native = self.root / 'native'
        self.native.mkdir()
        (self.native / 'Settings.json').write_text('{}')
        self.output = self.root / 'Archives 日本語 ; $(no)'
        self.home = self.root / 'agent-home'
        self.engine = self.root / 'LibationCli'
        self.probe = self.root / 'ffprobe'
        self.decode = self.root / 'ffmpeg'
        for path, source in ((self.engine, ENGINE), (self.probe, PROBE), (self.decode, DECODE)):
            path.write_text(source.replace('INTERPRETER', sys.executable))
            path.chmod(0o755)
        self.env = {**os.environ, 'AGENT_DO_HOME': str(self.home), 'AGENT_LIBATION_BIN': str(self.engine),
                    'AGENT_FFPROBE_BIN': str(self.probe), 'AGENT_FFMPEG_BIN': str(self.decode),
                    'LIBATION_MASTER_KEY': base64.b64encode(b'\0' * 32).decode()}
        self.mode()

    def mode(self, **values):
        path = self.native / 'fake.json'
        current = json.loads(path.read_text()) if path.exists() else {}
        current.update(values)
        path.write_text(json.dumps(current))

    def call(self, *args, success=None):
        result = subprocess.run([sys.executable, str(TOOL), *args, '--json'],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.stderr, '', result.stderr)
        self.assertNotIn('SECRET_TOKEN', result.stdout)
        self.assertNotIn('SECRET_RESPONSE', result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0 if payload['success'] else 2 if payload.get('error') == 'invalid_arguments' else 1)
        if success is not None:
            self.assertEqual(payload['success'], success, payload)
        return payload

    def connect(self, **extra):
        args = ['connect', '--account', 'home', '--marketplace', 'us',
                '--libation-files', str(self.native), '--output', str(self.output)]
        for key, value in extra.items():
            args.extend(['--' + key.replace('_','-'), value])
        return self.call(*args)

    def sync(self):
        self.assertTrue(self.connect()['success'])
        return self.call('sync', '--account', 'home')

    def calls(self):
        path = self.native / 'calls.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_end_to_end_archive_and_local_reads(self):
        self.assertTrue(self.sync()['success'])
        self.assertEqual(self.call('reconcile')['entries'][0]['archive_state'], 'missing')
        result = self.call('download', 'B123', success=True)['results'][0]
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['receipt']['chapter_count'], 2)
        before = self.calls()
        self.assertEqual(self.call('download', 'B123')['results'][0]['status'], 'already_verified')
        self.assertEqual(before, self.calls())
        self.env['AGENT_LIBATION_BIN'] = '/missing-engine'
        self.env.pop('LIBATION_MASTER_KEY')
        self.assertTrue(self.call('verify', 'B123')['success'])
        self.assertEqual(self.call('snapshot')['entries'][0]['archive_state'], 'verified')
        self.assertEqual(self.call('reconcile')['total'], 0)
        self.assertEqual(self.call('accounts')['accounts'][0]['account'], 'home')
        self.assertEqual(before, self.calls())

    def test_missing_and_invalid_credentials(self):
        self.env.pop('LIBATION_MASTER_KEY')
        self.assertEqual(self.connect()['error'], 'missing_credentials')
        self.env['LIBATION_MASTER_KEY'] = 'SECRET_TOKEN'
        self.assertEqual(self.connect()['error'], 'invalid_master_key')

    def test_expired_and_mfa_failures_redacted(self):
        self.assertTrue(self.sync()['success'])
        for failure, expected in [('Authentication failed: expired session', 'authentication_required'),
                                  ('MFA required', 'authentication_action_required')]:
            self.mode(failure=failure)
            self.assertEqual(self.call('sync')['error'], expected)
            self.assertTrue(self.call('snapshot')['partial_failure'])
            self.assertEqual(self.call('snapshot')['total'], 1)

    def test_empty_vs_failed_scan(self):
        self.mode(rows=[])
        self.assertEqual(self.sync()['total'], 0)
        self.mode(partial=True)
        self.assertEqual(self.call('sync')['error'], 'engine_failed')
        self.assertEqual(self.call('snapshot')['total'], 0)

    def test_scan_requires_fresh_log_evidence(self):
        self.assertTrue(self.sync()['success'])
        self.mode(no_logs=True)
        self.assertEqual(self.call('sync')['error'], 'sync_unverifiable')
        self.assertEqual(self.call('snapshot')['total'], 1)

    def test_multiple_accounts_and_marketplaces_rejected(self):
        self.mode(multiple_accounts=True)
        self.assertEqual(self.connect()['error'], 'dedicated_account_state_required')
        self.mode(multiple_accounts=False, also_scans='uk')
        self.assertEqual(self.connect()['error'], 'dedicated_account_state_required')
        self.mode(also_scans='', marketplace='uk')
        self.assertEqual(self.connect()['error'], 'marketplace_mismatch')

    def test_export_scope_fails_closed(self):
        self.mode(export_rows=[{'Account': 'other', 'Locale': 'us', 'AudibleProductId': 'B123', 'Title': 'Other'}])
        self.assertEqual(self.sync()['error'], 'export_account_mismatch')

    def test_missing_and_invalid_audio_exit_zero(self):
        for mode, expected in [('no_audio', 'missing_or_ambiguous_audio'), ('bad_audio', 'invalid_audio')]:
            with self.subTest(mode=mode):
                self.mode(**{mode: True})
                self.assertTrue(self.sync()['success'])
                result = self.call('download', 'B123')['results'][0]
                self.assertEqual(result['error'], expected)
                self.assertFalse((self.home / 'audiobook/accounts/home/receipts/B123.json').exists())
                self.assertFalse((self.output / 'B123').exists())
                if mode == 'no_audio':
                    self.mode(no_audio=False)
                    import shutil
                    shutil.rmtree(self.output / '.staging')

    def test_completed_unverified_resume(self):
        self.assertTrue(self.sync()['success'])
        self.mode(failed_after_output=True)
        self.assertFalse(self.call('download', 'B123')['success'])
        self.assertEqual(self.call('reconcile')['entries'][0]['archive_state'], 'completed_unverified')
        self.assertEqual(self.call('download', 'B123')['results'][0]['error'], 'resume_required')
        before = self.calls()
        self.assertTrue(self.call('download', 'B123', '--resume')['success'])
        self.assertEqual(before, self.calls())

    def test_timeout_marks_interrupted_and_can_resume(self):
        self.assertTrue(self.sync()['success'])
        self.mode(sleep=True)
        result = self.call('download', 'B123', '--timeout', '0.5')
        self.assertEqual(result['error'], 'operation_timeout')
        self.assertEqual(self.call('reconcile')['entries'][0]['archive_state'], 'interrupted')
        self.mode(sleep=False)
        self.assertTrue(self.call('download', 'B123', '--resume')['success'])

    def test_changed_archive_never_overwritten(self):
        self.assertTrue(self.sync()['success'])
        result = self.call('download', 'B123')['results'][0]
        path = Path(result['receipt']['path'])
        path.write_bytes(b'bad modified audio')
        before = self.calls()
        self.assertEqual(self.call('download', 'B123')['results'][0]['error'], 'archive_conflict')
        self.assertEqual(before, self.calls())
        self.assertEqual(self.call('reconcile')['entries'][0]['archive_state'], 'unverifiable')

    def test_audio_checks_and_optional_deep_decode(self):
        self.assertTrue(self.sync()['success'])
        self.assertTrue(self.call('download', 'B123')['success'])
        for mode, expected in [('zero', 'invalid_audio'), ('short', 'duration_mismatch'),
                               ('no_audio', 'invalid_audio'), ('invalid_json', 'invalid_audio'),
                               ('no_chapters', 'missing_chapters')]:
            with self.subTest(mode=mode):
                self.env['PROBE_MODE'] = mode
                self.assertEqual(self.call('verify', 'B123')['error'], expected)
        self.env['PROBE_MODE'] = 'no_chapters'
        self.assertIn('source_chapters', self.call('verify', 'B123', '--allow-no-chapters')['verification']['unavailable_checks'])
        self.env.pop('PROBE_MODE')
        self.assertTrue(self.call('verify', 'B123', '--deep')['verification']['deep_decode'])
        self.env['DECODE_CODE'] = '1'
        self.assertEqual(self.call('verify', 'B123', '--deep')['error'], 'decode_failed')

    def test_verify_default_does_not_save(self):
        self.assertTrue(self.sync()['success'])
        self.assertTrue(self.call('download', 'B123')['success'])
        receipt = self.home / 'audiobook/accounts/home/receipts/B123.json'
        before = receipt.read_bytes()
        self.call('verify', 'B123', success=True)
        self.assertEqual(before, receipt.read_bytes())
        self.call('verify', 'B123', '--save-receipt', success=True)
        self.assertNotEqual(before, receipt.read_bytes())

    def test_explicit_batch_reports_each_result(self):
        self.assertTrue(self.sync()['success'])
        result = self.call('download', 'B123', 'NOTINLIBRARY')
        self.assertFalse(result['success'])
        self.assertTrue(result['partial_failure'])
        self.assertEqual(len(result['results']), 2)
        self.assertEqual(result['results'][1]['error'], 'book_not_found')

    def test_lock_conflicts_fail_closed(self):
        import fcntl
        self.assertTrue(self.sync()['success'])
        with (self.home / 'audiobook/operation.lock').open('r+') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.call('sync')['error'], 'operation_in_progress')
            self.assertEqual(self.call('download', 'B123')['results'][0]['error'], 'operation_in_progress')

    def test_symlink_and_path_traversal_rejected(self):
        self.assertTrue(self.sync()['success'])
        (self.output / 'evil').symlink_to(self.native, target_is_directory=True)
        self.assertEqual(self.call('download', 'B123')['results'][0]['error'], 'unsafe_symlink')
        self.assertEqual(self.call('download', '../escape')['results'][0]['error'], 'invalid_book_id')

    def test_mp3_is_explicit(self):
        self.assertTrue(self.connect(format='mp3')['success'])
        self.assertTrue(self.call('sync')['success'])
        result = self.call('download', 'B123', success=True)['results'][0]
        self.assertEqual(result['receipt']['format'], 'mp3')

    def test_json_syntax_failure_is_one_document(self):
        self.assertEqual(self.call('download')['error'], 'invalid_arguments')

    def test_native_permissions_restricted(self):
        import stat
        self.assertTrue(self.sync()['success'])
        for path in self.native.rglob('*'):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600)

    def test_login_response_uses_private_pty(self):
        import io
        from unittest.mock import patch
        sys.path.insert(0, str(TOOL.parent))
        from service import Adapter
        adapter = Adapter(str(self.engine))
        profile = {'libation_files': str(self.native), 'marketplace': 'us'}
        actual_open = open
        terminal = io.StringIO()
        # Keep the in-memory transcript available after the adapter closes it.
        terminal.close = lambda: None
        def fake_open(path, *args, **kwargs):
            return terminal if str(path) == '/dev/tty' else actual_open(path, *args, **kwargs)
        with patch.dict(os.environ, self.env), patch('builtins.open', side_effect=fake_open), patch('getpass.getpass', return_value='https://www.amazon.com/ap/maplanding?code=SECRET_RESPONSE'):
            adapter.interactive_login(profile, 'owner@example.test')
        self.assertIn('https://www.amazon.com/ap/signin', terminal.getvalue())
        self.assertNotIn('SECRET_RESPONSE', terminal.getvalue())
        self.assertNotIn('SECRET_RESPONSE', json.dumps(self.calls()))
        self.assertNotIn('--response-url', json.dumps(self.calls()))

    def test_mismatched_staging_manifest_is_not_adopted(self):
        self.assertTrue(self.sync()['success'])
        stage = self.output / '.staging/B123'
        stage.mkdir(parents=True)
        (stage / 'identity.json').write_text(json.dumps({'account': 'other', 'book_id': 'B123', 'marketplace': 'us'}))
        self.assertEqual(self.call('download', 'B123', '--resume')['results'][0]['error'], 'archive_conflict')

    def test_native_encryption_failure_fails_closed(self):
        self.assertTrue(self.sync()['success'])
        self.mode(failure='Failed to encrypt identity field. Saving as plaintext')
        self.assertEqual(self.call('sync')['error'], 'native_encryption_failed')

    def test_missing_dependency_leaves_no_completed_archive(self):
        self.assertTrue(self.sync()['success'])
        self.env['AGENT_FFPROBE_BIN'] = '/missing-probe'
        self.assertFalse(self.call('download', 'B123')['success'])
        self.assertFalse((self.output / 'B123').exists())

    def test_source_duration_unavailable_is_recorded(self):
        self.mode(rows=[{'Account': 'home', 'Locale': 'us', 'AudibleProductId': 'B123', 'Title': 'Book'}])
        self.assertTrue(self.sync()['success'])
        result = self.call('download', 'B123', success=True)['results'][0]
        self.assertIn('source_duration', result['receipt']['verification']['unavailable_checks'])

    def test_batch_interruption_preserves_results(self):
        self.assertTrue(self.sync()['success'])
        self.mode(sleep=True)
        result = self.call('download', 'B123', 'NOTINLIBRARY', '--timeout', '0.5')
        self.assertEqual(result['results'][0]['error'], 'operation_timeout')
        self.assertEqual(result['results'][1]['error'], 'not_attempted')

    def test_native_identity_change_invalidates_profile(self):
        self.assertTrue(self.sync()['success'])
        text = self.engine.read_text().replace('owner@example.test', 'different@example.test')
        self.engine.write_text(text)
        self.assertEqual(self.call('sync')['error'], 'account_identity_changed')

    def test_empty_conflicting_archive_is_not_replaced(self):
        self.assertTrue(self.sync()['success'])
        (self.output / 'B123').mkdir()
        self.assertEqual(self.call('download', 'B123')['results'][0]['error'], 'archive_conflict')
        self.assertEqual(list((self.output / 'B123').iterdir()), [])

    def test_multiple_profile_isolation(self):
        self.assertTrue(self.sync()['success'])
        native = self.root / 'work-native'
        native.mkdir()
        (native / 'Settings.json').write_text('{}')
        (native / 'fake.json').write_text(json.dumps({'marketplace': 'uk', 'rows': []}))
        self.call('connect', '--account', 'work', '--marketplace', 'uk', '--libation-files', str(native),
                  '--output', str(self.root / 'work-output'), success=True)
        self.call('sync', '--account', 'work', success=True)
        self.assertEqual(self.call('snapshot', '--account', 'work')['total'], 0)
        self.assertEqual(self.call('snapshot', '--account', 'home')['total'], 1)
        self.assertEqual(self.call('snapshot')['error'], 'account_required')


if __name__ == "__main__":
    unittest.main()
