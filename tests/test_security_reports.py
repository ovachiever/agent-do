#!/usr/bin/env python3
"""Saved-report selection must expose failures without hiding older evidence."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/agent-security'))
from security.cli import main
from security.store import finish, home, new_report
from test_security import advisory


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'AGENT_DO_HOME': self.directory.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def save(self, date, *, incomplete=False, project='service', unscored=False):
        report = new_report('scan', {'kind': 'local', 'path': '/projects/' + project})
        report['created_at'] = '2026-10-22T' + date + ':00:00Z'
        report['findings'] = [advisory(score=None if unscored else 9)] if not incomplete else []
        report['coverage'] = [{'source': 'scan', 'status': 'error', 'reason': 'fixture build failure'}] if incomplete else []
        return finish(report)

    def cli(self, *arguments, text=False):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(['report', *arguments, *([] if text else ['--json'])])
        return code, output.getvalue() if text else json.loads(output.getvalue())

    def test_latest_flags_failed_scan_instead_of_silently_substituting_old_results(self):
        self.save('10')
        failed = self.save('11', incomplete=True)
        original = Path(failed['saved_report']).read_bytes()
        for option in [[], ['--latest']]:
            code, report = self.cli(*option)
            self.assertEqual(code, 1)
            self.assertEqual(report['report_id'], failed['report_id'])
            self.assertTrue(report['selection_notes'])
            self.assertIn('--list', report['selection_notes'][0])
        self.assertEqual(Path(failed['saved_report']).read_bytes(), original)

    def test_explicit_latest_complete_can_select_older_different_project(self):
        complete = self.save('10', project='other-service')
        self.save('11', incomplete=True)
        code, report = self.cli('--latest-complete', '--severity', 'critical')
        self.assertEqual(code, 0)
        self.assertEqual(report['report_id'], complete['report_id'])
        self.assertEqual(report['target']['path'], '/projects/other-service')
        self.assertIn('all projects', report['selection_notes'][0])

    def test_list_includes_failed_and_successful_reports_with_counts_and_paths(self):
        first = self.save('10', unscored=True)
        last = self.save('11', incomplete=True)
        code, report = self.cli('--list')
        self.assertEqual(code, 0)
        self.assertEqual([row['status'] for row in report['reports']], ['incomplete', 'complete'])
        self.assertEqual([row['findings'] for row in report['reports']], [0, 1])
        self.assertEqual(report['reports'][1]['unscored'], 1)
        self.assertEqual(report['reports'][0]['file'], last['saved_report'])
        self.assertEqual(report['reports'][1]['file'], first['saved_report'])
        self.assertEqual(report['reports'][0]['coverage_gaps'][0]['reason'], 'fixture build failure')

    def test_text_output_surfaces_selection_target_timestamp_and_recovery_commands(self):
        self.save('10')
        self.save('11', incomplete=True)
        code, text = self.cli('--latest', text=True)
        self.assertEqual(code, 1)
        for value in ['incomplete', '--list', '--latest-complete', '/projects/service', '2026-10-22T11:00:00Z']:
            self.assertIn(value, text)
        _, text = self.cli('--list', text=True)
        self.assertIn('fixture build failure', text)
        self.assertIn('File:', text)

    def test_empty_store_list_is_valid_but_selection_is_error(self):
        code, report = self.cli('--list')
        self.assertEqual(code, 0)
        self.assertEqual(report['reports'], [])
        for option in ['--latest', '--latest-complete']:
            code, _ = self.cli(option)
            self.assertEqual(code, 2)

    def test_no_complete_report_does_not_fall_back_to_incomplete(self):
        self.save('10', incomplete=True)
        code, report = self.cli('--latest-complete')
        self.assertEqual(code, 2)
        self.assertIn('No complete', report['error'])

    def test_corrupt_report_is_visible_and_does_not_hide_valid_reports(self):
        complete = self.save('10')
        corrupt = home() / 'reports/2026-10-22T12-00-00Z-broken.json'
        corrupt.write_text('[]')
        code, report = self.cli('--list')
        self.assertEqual(code, 1)
        self.assertEqual([row['status'] for row in report['reports']], ['unreadable', 'complete'])
        code, report = self.cli('--latest')
        self.assertEqual(code, 2)
        code, report = self.cli('--latest-complete')
        self.assertEqual(code, 0)
        self.assertEqual(report['report_id'], complete['report_id'])
        self.assertIn('could not be read', ' '.join(report['selection_notes']))

    def test_list_rejects_finding_filters_and_selectors_are_exclusive(self):
        for extra in [('--severity', 'critical'), ('--cvss-min', '0'), ('--known-exploited',), ('--target', 'java'),
                      ('--latest',), ('--file', '/tmp/report.json'), ('--latest-complete',)]:
            with self.subTest(extra=extra):
                code, _ = self.cli('--list', *extra)
                self.assertEqual(code, 2)

    def test_file_selects_old_assessment_without_changing_latest(self):
        complete = self.save('10')
        failed = self.save('11', incomplete=True)
        code, report = self.cli('--file', complete['saved_report'])
        self.assertEqual(code, 0)
        self.assertEqual(report['report_id'], complete['report_id'])
        _, report = self.cli('--latest')
        self.assertEqual(report['report_id'], failed['report_id'])

    def test_unscored_findings_alone_do_not_make_assessment_incomplete(self):
        self.save('10', unscored=True)
        code, report = self.cli('--latest', '--cvss-min', '7')
        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['shown'], 0)
        code, report = self.cli('--latest', '--cvss-min', '7', '--include-unscored')
        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['shown'], 1)


if __name__ == '__main__':
    unittest.main()
