#!/usr/bin/env python3
"""Portfolio transition safety, scheduling, transaction and notification contracts."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/agent-security'))
from security.cli import main
from security.comparison import compare_target
from security.monitor import load_config, locked
from security.store import home
from test_security import FakeClient, advisory
from security.sources import SourceError


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.env = patch.dict(os.environ, {'AGENT_DO_HOME': str(self.root / 'state')})
        self.env.start()
        self.config = self.root / 'portfolio.json'
        self.config.write_text(json.dumps({'schema_version': 1, 'monitor_id': 'a' * 32,
            'interval_hours': 24, 'targets': [{'repo': 'acme/one'}, {'repo': 'acme/two'}]}))
        self.rows = {'acme/one': [advisory()], 'acme/two': []}
        self.failed_targets = set()
        self.version = 'osv-scanner version: 2.7.0'
        self.calls = []

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def scanner(self, args, report):
        key = args.repo or args.path
        self.calls.append(key)
        report['scanner'] = {'version': self.version, 'raw_output': {'fixture': True}}
        report['target'].update({'commit': 'b' * 40, 'requested_ref': args.ref or ('main' if args.repo else None)})
        report['findings'] = [json.loads(json.dumps(row)) for row in self.rows.get(key, [])]
        if key in self.failed_targets:
            report['coverage'].append({'source': 'fixture scanner', 'status': 'error', 'reason': 'partial lookup'})
        else:
            report['coverage'].append({'source': 'fixture scanner', 'status': 'ok'})

    def cli(self, action='run', *options, text=False):
        out = io.StringIO()
        with patch('security.monitor.scan', side_effect=self.scanner), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = main(['monitor', action, '--config', str(self.config), *options, *([] if text else ['--json'])])
        return code, out.getvalue() if text else json.loads(out.getvalue())

    def state(self):
        return json.loads((home() / 'monitors' / ('a' * 32) / 'state.json').read_text())

    def test_new_ongoing_resolved_and_reopened_keep_first_detection(self):
        code, first = self.cli()
        self.assertEqual(code, 0)
        self.assertEqual(first['counts'], {'new': 1, 'ongoing': 0, 'resolved': 0, 'unverified': 0})
        issue = first['changes']['new'][0]
        self.assertNotEqual(issue['first_detected_at'], issue['findings'][0]['published'])
        _, second = self.cli()
        self.assertEqual(second['counts']['ongoing'], 1)
        self.rows['acme/one'] = []
        _, third = self.cli()
        self.assertEqual(third['counts']['resolved'], 1)
        self.rows['acme/one'] = [advisory()]
        _, fourth = self.cli()
        reopened = fourth['changes']['new'][0]
        self.assertTrue(reopened['reopened'])
        self.assertEqual(reopened['first_detected_at'], issue['first_detected_at'])
        self.assertEqual(reopened['issue_id'], issue['issue_id'])

    def test_partial_failure_never_resolves_prior_findings_and_other_repo_continues(self):
        self.cli()
        self.rows['acme/one'] = []
        self.rows['acme/two'] = [advisory('CVE-2026-20000')]
        self.failed_targets.add('acme/one')
        code, digest = self.cli()
        self.assertEqual(code, 1)
        self.assertEqual(digest['counts']['resolved'], 0)
        self.assertEqual(digest['counts']['unverified'], 1)
        self.assertEqual(digest['counts']['new'], 1)
        self.assertEqual(digest['comparison_status'], 'partial')
        self.failed_targets.clear()
        _, digest = self.cli()
        self.assertEqual(digest['counts']['resolved'], 1)

    def test_positive_evidence_from_partial_scan_is_tracked(self):
        self.failed_targets.add('acme/one')
        code, first = self.cli()
        self.assertEqual(code, 1)
        self.assertEqual(first['counts']['new'], 1)
        self.rows['acme/one'] = []
        _, second = self.cli()
        self.assertEqual(second['counts']['unverified'], 1)
        self.assertEqual(second['counts']['resolved'], 0)

    def test_package_version_change_is_ongoing_not_a_false_resolution(self):
        self.cli()
        self.rows['acme/one'] = [advisory(version='1.1')]
        _, digest = self.cli()
        self.assertEqual(digest['counts']['ongoing'], 1)
        self.assertEqual(digest['counts']['new'], 0)
        self.assertEqual(digest['counts']['resolved'], 0)

    def test_same_advisory_in_two_repositories_has_independent_lifecycle(self):
        self.rows['acme/two'] = [advisory()]
        _, first = self.cli()
        self.assertEqual(first['counts']['new'], 2)
        source = json.loads(Path(first['source_report']).read_text())
        self.assertEqual(len(source['findings']), 2)
        self.rows['acme/one'] = []
        _, second = self.cli()
        self.assertEqual(second['counts']['resolved'], 1)
        self.assertEqual(second['counts']['ongoing'], 1)
        self.assertEqual(second['changes']['resolved'][0]['target']['repo'], 'acme/one')

    def test_alias_evolution_and_bridge_merge_keep_identity(self):
        history = {}
        first = advisory('GHSA-aaaa-bbbb-cccc')
        initial = compare_target(history, 'same-scope', [first], True, '2026-10-21T00:00:00Z', 'one')
        second = advisory('CVE-2026-10001'); second['aliases'].append(first['id'])
        result = compare_target(history, 'same-scope', [second], True, '2026-10-22T00:00:00Z', 'two')
        self.assertEqual(result['ongoing'][0]['issue_id'], initial['new'][0]['issue_id'])
        self.assertFalse(result['resolved'])
        # Two previously separate aliases learned to be the same issue.
        other = advisory('GHSA-dddd-eeee-ffff')
        compare_target(history, 'same-scope', [second, other], True, '2026-10-22T01:00:00Z', 'three')
        second['aliases'].append(other['id'])
        result = compare_target(history, 'same-scope', [second], True, '2026-10-22T02:00:00Z', 'four')
        self.assertEqual(len(result['ongoing']), 1)
        self.assertFalse(result['resolved'])

    def test_scanner_version_change_preserves_old_issues_as_unverified(self):
        self.cli()
        self.rows['acme/one'] = []
        self.version = 'osv-scanner version: 2.8.0'
        _, digest = self.cli()
        self.assertEqual(digest['counts']['resolved'], 0)
        self.assertEqual(digest['counts']['unverified'], 1)
        self.assertIn('different scan scope', digest['changes']['unverified'][0]['reason'])

    def test_removing_target_does_not_resolve_its_issues(self):
        self.cli()
        config = json.loads(self.config.read_text()); config['targets'] = [{'repo': 'acme/two'}]
        self.config.write_text(json.dumps(config))
        _, digest = self.cli()
        self.assertEqual(digest['counts']['resolved'], 0)
        self.assertEqual(digest['counts']['unverified'], 1)
        self.assertIn('no longer configured', digest['changes']['unverified'][0]['reason'])

    def test_local_builds_require_explicit_run_opt_in_and_scope_changes_are_separate(self):
        config = json.loads(self.config.read_text())
        config['targets'] = [{'path': str(self.root), 'resolve': 'maven', 'options': {'build_property': ['example=PRIVATE_VALUE']}}]
        self.config.write_text(json.dumps(config))
        self.rows[str(self.root)] = [advisory()]
        code, blocked = self.cli()
        self.assertEqual(code, 1)
        self.assertFalse(self.calls)
        code, allowed = self.cli('run', '--allow-builds')
        self.assertEqual(code, 0)
        self.assertEqual(allowed['counts']['new'], 1)
        self.assertNotIn('PRIVATE_VALUE', json.dumps(self.state()))
        config['targets'][0]['options']['build_property'] = ['example=OTHER_PRIVATE_VALUE']
        self.config.write_text(json.dumps(config))
        self.rows[str(self.root)] = []
        _, digest = self.cli('run', '--allow-builds')
        self.assertEqual(digest['counts']['resolved'], 0)
        self.assertEqual(digest['counts']['unverified'], 1)

    def test_due_skips_without_scan_state_advance_or_notification(self):
        self.cli()
        before = self.state()
        self.calls.clear()
        with patch('security.monitor.subprocess.run') as notify:
            code, result = self.cli('run', '--due', '--notify-recipient', 'team')
        self.assertEqual(code, 0)
        self.assertTrue(result['skipped'])
        self.assertEqual(self.state(), before)
        self.assertFalse(self.calls)
        notify.assert_not_called()

    def test_due_interval_elapses_and_failed_attempt_is_also_throttled(self):
        self.failed_targets.add('acme/one')
        with patch('security.monitor.now', return_value='2026-10-21T00:00:00Z'):
            self.cli()
        self.calls.clear()
        with patch('security.monitor.now', return_value='2026-10-22T00:00:00Z'):
            code, result = self.cli('run', '--due')
        self.assertEqual(code, 1)
        self.assertFalse(result.get('skipped', False))
        self.assertEqual(len(self.calls), 2)

    def test_lock_rejects_overlapping_runs(self):
        directory = home() / 'monitors' / ('a' * 32)
        with locked(directory):
            code, result = self.cli()
        self.assertEqual(code, 2)
        self.assertIn('active', result['error'])
        self.assertFalse(self.calls)

    def test_config_rejects_bad_fields_duplicates_or_nonregular_files_before_scan(self):
        original = json.loads(self.config.read_text())
        for targets in [[{'repo': 'acme/one', 'command': 'sh'}], [{'repo': 'acme/one'}, {'repo': 'ACME/one'}],
                        [{'repo': 'acme/one', 'resolve': 'maven'}], [{'path': '.' ,'ref': 'main'}],
                        [{'path': '.', 'options': {'shell': 'true'}}]]:
            value = {**original, 'targets': targets}; self.config.write_text(json.dumps(value))
            code, _ = self.cli()
            self.assertEqual(code, 2, targets)
        self.assertFalse(self.calls)
        self.config.unlink(); os.mkfifo(self.config)
        code, _ = self.cli(); self.assertEqual(code, 2)

    def test_digest_filters_do_not_modify_history_and_report_is_offline(self):
        code, view = self.cli('run', '--cvss-min', '9')
        self.assertEqual(code, 0)
        self.assertEqual(view['counts']['new'], 1)
        self.assertEqual(view['shown_counts']['new'], 0)
        saved = json.loads(Path(view['saved_digest']).read_text())
        self.assertEqual(len(saved['changes']['new']), 1)
        self.calls.clear()
        code, result = self.cli('report')
        self.assertEqual(code, 0)
        self.assertEqual(result['shown_counts']['new'], 1)
        self.assertFalse(self.calls)
        code, other = self.cli('report', '--file', view['saved_digest'])
        self.assertEqual(other['run_id'], result['run_id'])

    def test_failed_state_write_cannot_advance_baseline(self):
        from security.store import atomic_json
        self.cli(); before = self.state()
        def fail_state(path, value):
            if Path(path).name == 'state.json': raise OSError('fixture state write failure')
            return atomic_json(path, value)
        self.rows['acme/one'] = []
        with patch('security.monitor.atomic_json', side_effect=fail_state):
            code, _ = self.cli()
        self.assertEqual(code, 2)
        self.assertEqual(self.state(), before)

    def test_notification_is_opt_in_and_failure_does_not_erase_scan_evidence(self):
        with patch('security.monitor.subprocess.run') as notify:
            self.cli()
            notify.assert_not_called()
            notify.return_value = subprocess.CompletedProcess([], 1, b'', b'PRIVATE_ERROR')
            code, result = self.cli('run', '--notify-recipient', 'team', '--notify-via', 'slack')
        self.assertEqual(code, 1)
        self.assertEqual(result['notification']['status'], 'error')
        self.assertTrue(Path(result['source_report']).exists())
        self.assertNotIn('PRIVATE_ERROR', json.dumps(result))
        self.assertIn('--via', notify.call_args.args[0])

    def test_schedule_export_has_no_install_or_execution_side_effects(self):
        with patch('security.monitor.subprocess.run') as executed:
            code, result = self.cli('schedule')
        self.assertEqual(code, 0)
        self.assertFalse(result['installed'])
        self.assertTrue(result['cron'].startswith('0 * * * * '))
        self.assertIn('--due', result['cron'])
        self.assertIn(str(self.config), result['cron'])
        executed.assert_not_called()
        self.assertFalse(self.calls)
        self.assertFalse((home() / 'monitors').exists())

    def test_actual_local_maven_pipeline_runs_and_compares_without_target_mocks(self):
        import test_security_resolution as resolution_fixtures
        fixture = resolution_fixtures.ResolutionTests()
        fixture.setUp()
        try:
            fixture.pom()
            config = json.loads(self.config.read_text())
            config['targets'] = [{'path': str(fixture.project), 'resolve': 'maven', 'options': {'maven': fixture.maven()}}]
            self.config.write_text(json.dumps(config))
            for category in ['new', 'ongoing']:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(['monitor', 'run', '--config', str(self.config), '--allow-builds', '--scanner', fixture.scanner(), '--json'])
                digest = json.loads(output.getvalue())
                self.assertEqual(code, 0, digest)
                self.assertEqual(digest['counts'][category], 1)
                assessment = json.loads(Path(digest['source_report']).read_text())
                self.assertEqual(assessment['repositories'][0]['resolution']['status'], 'ok')
                self.assertTrue(assessment['findings'][0]['evidence'][0]['dependency_path'])
        finally:
            fixture.tearDown()

    def test_corrupt_state_fails_closed_before_scanning(self):
        self.cli(); self.calls.clear()
        state_file = home() / 'monitors' / ('a' * 32) / 'state.json'
        state_file.write_text('{"schema_version":1,"targets":{"bad":{"scopes":[]}}}')
        before = state_file.read_bytes()
        code, result = self.cli()
        self.assertEqual(code, 2)
        self.assertIn('monitor', result['error'])
        self.assertFalse(self.calls)
        self.assertEqual(state_file.read_bytes(), before)

    def test_default_branch_switch_starts_separate_scope_and_cron_quotes_percent(self):
        self.cli()
        def switched(args, report):
            self.scanner(args, report)
            report['target']['requested_ref'] = 'develop'
        self.rows['acme/one'] = []
        output = io.StringIO()
        with patch('security.monitor.scan', side_effect=switched), contextlib.redirect_stdout(output):
            code = main(['monitor', 'run', '--config', str(self.config), '--json'])
        digest = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(digest['counts']['resolved'], 0)
        self.assertEqual(digest['counts']['unverified'], 1)
        renamed = self.config.with_name('portfolio 100%.json')
        self.config.rename(renamed); self.config = renamed
        code, result = self.cli('schedule', '--notify-recipient', 'security-team')
        self.assertEqual(code, 0)
        self.assertIn(r'100\%', result['cron'])
        self.assertIn('--notify-recipient security-team', result['cron'])

    def test_shared_kev_failure_cannot_resolve_prior_findings(self):
        client = FakeClient([({'vulnerabilities': [{'cveID': 'CVE-2026-10001'}]}, {})])
        with patch('security.monitor.Client', return_value=client):
            code, result = self.cli('run', '--kev')
        self.assertEqual(code, 0)
        self.assertTrue(result['changes']['new'][0]['findings'][0]['known_exploited'])
        self.rows['acme/one'] = []
        with patch('security.monitor.Client', return_value=FakeClient([SourceError('fixture unavailable')])):
            code, result = self.cli('run', '--kev')
        self.assertEqual(code, 1)
        self.assertEqual(result['counts']['resolved'], 0)
        self.assertEqual(result['counts']['unverified'], 1)
        self.assertTrue(all(target['status'] == 'incomplete' for target in result['targets']))
        self.rows['acme/one'] = [advisory()]
        with patch('security.monitor.Client', return_value=FakeClient([SourceError('fixture unavailable')])):
            code, result = self.cli('run', '--known-exploited')
        self.assertEqual(code, 1)
        self.assertEqual(result['shown_counts']['ongoing'], 0)
        code, _ = self.cli('report', '--known-exploited')
        self.assertEqual(code, 2)

    def test_symlinked_local_target_uses_the_same_canonical_scope(self):
        alias = self.root / 'root-alias'
        alias.symlink_to(self.root, target_is_directory=True)
        value = json.loads(self.config.read_text())
        value['targets'] = [{'path': str(alias)}]
        self.config.write_text(json.dumps(value))
        self.rows[str(self.root)] = [advisory()]
        code, first = self.cli()
        self.assertEqual(code, 0)
        self.assertEqual(first['counts']['new'], 1)
        value['targets'] = [{'path': str(self.root)}]
        self.config.write_text(json.dumps(value))
        code, second = self.cli()
        self.assertEqual(code, 0)
        self.assertEqual(second['counts']['ongoing'], 1)
        self.assertEqual(second['counts']['unverified'], 0)

    def test_historical_digest_summary_preserves_unknown_observations_and_saved_bytes(self):
        code, first = self.cli()
        self.assertEqual(code, 0)
        state = self.state()
        state['latest_digest'].pop('assessment_summary')
        path = home() / 'monitors' / ('a' * 32) / 'state.json'
        path.write_text(json.dumps(state))
        before = path.read_bytes()
        code, report = self.cli('report')
        self.assertEqual(code, 0)
        self.assertIsNone(report['assessment_summary']['findings_observed'])
        self.assertIsNone(report['assessment_summary']['runtime_candidates'])
        self.assertEqual(report['counts'], first['counts'])
        code, text = self.cli('report', text=True)
        self.assertEqual(code, 0)
        self.assertIn('unknown (historical digest)', text)
        self.assertEqual(path.read_bytes(), before)

    def test_changed_settings_content_is_not_a_compatible_baseline(self):
        settings = self.root / 'settings.xml'; settings.write_text('<settings>FIRST_PRIVATE_VALUE</settings>')
        config = json.loads(self.config.read_text())
        config['targets'] = [{'path': str(self.root), 'resolve': 'maven', 'options': {'maven_settings': str(settings)}}]
        self.config.write_text(json.dumps(config))
        self.rows[str(self.root)] = [advisory()]
        self.cli('run', '--allow-builds')
        settings.write_text('<settings>SECOND_PRIVATE_VALUE</settings>')
        self.rows[str(self.root)] = []
        _, result = self.cli('run', '--allow-builds')
        self.assertEqual(result['counts']['resolved'], 0)
        self.assertEqual(result['counts']['unverified'], 1)
        self.assertNotIn('PRIVATE_VALUE', json.dumps(self.state()))

    def test_package_identity_preserves_maven_case_and_normalizes_python_names(self):
        upper, lower = advisory(), advisory()
        upper['package'].update({'ecosystem': 'Maven', 'name': 'org.example:Foo'})
        lower['package'].update({'ecosystem': 'Maven', 'name': 'org.example:foo'})
        result = compare_target({}, 'scope', [upper, lower], True, '2026-10-22T00:00:00Z', 'one')
        self.assertEqual(len(result['new']), 2)
        upper['package'].update({'ecosystem': 'PyPI', 'name': 'Example_Package'})
        lower['package'].update({'ecosystem': 'pip', 'name': 'example-package'})
        result = compare_target({}, 'scope', [upper, lower], True, '2026-10-22T00:00:00Z', 'two')
        self.assertEqual(len(result['new']), 1)

    def test_init_existing_config_is_friendly_and_byte_preserving(self):
        before = self.config.read_bytes()
        code, result = self.cli('init', '--path', str(self.root))
        self.assertEqual(code, 2)
        self.assertIn('Monitor config already exists:', result['error'])
        self.assertIn('Nothing was overwritten', result['error'])
        self.assertNotIn('Errno', result['error'])
        self.assertEqual(self.config.read_bytes(), before)

    def test_init_from_repo_file_or_local_root_does_not_overwrite_config(self):
        self.config.unlink()
        repos = self.root / 'repos.txt'; repos.write_text('acme/one\nhttps://github.com/acme/two\n')
        code, _ = self.cli('init', '--repos-file', str(repos))
        self.assertEqual(code, 0)
        self.assertEqual(len(load_config(self.config, 4096)['targets']), 2)
        before = self.config.read_bytes()
        code, _ = self.cli('init', '--path', str(self.root))
        self.assertEqual(code, 2)
        self.assertEqual(self.config.read_bytes(), before)
        self.config.unlink()
        code, _ = self.cli('init', '--path', str(self.root), '--resolve', 'maven')
        self.assertEqual(code, 0)
        self.assertEqual(load_config(self.config, 4096)['targets'][0]['resolve'], 'maven')
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        code, _ = self.cli('schedule'); self.assertEqual(code, 2)
        code, result = self.cli('schedule', '--allow-builds')
        self.assertEqual(code, 0)
        self.assertIn('--allow-builds', result['cron'])


if __name__ == '__main__': unittest.main()
