#!/usr/bin/env python3
"""Repository-file validation, snapshot isolation, failure coverage and saved views."""
import base64
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
import test_security as fixtures
from security.cli import main
from security.repositories import load_repositories
from security.sources import SourceError
from security.store import latest_report


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.env = patch.dict(os.environ, {'AGENT_DO_HOME': str(self.root / 'state')})
        self.env.start()
        self.file = self.root / 'repos.txt'
        self.file.write_text('acme/one\nacme/two\n')
        self.scanner = fixtures.SecurityTests.scanner(self)
        self.requests = []

    def tearDown(self):
        self.env.stop()
        self.temporary.cleanup()

    def github(self, args, endpoint):
        self.requests.append((args.repo, endpoint))
        if args.repo.endswith('/private'):
            raise ValueError('GitHub read failed; check repository access')
        if '/commits/' in endpoint:
            return {'sha': ('b' if 'release' in endpoint else 'a') * 40}
        if '/git/trees/' in endpoint:
            return {'tree': [{'type': 'blob', 'mode': '100644', 'path': 'requirements.txt', 'sha': 'c' * 40}]}
        if '/git/blobs/' in endpoint:
            return {'encoding': 'base64', 'content': base64.b64encode(b'example-python==1.0\n').decode()}
        return {'default_branch': 'main'}

    def cli(self, *options, client=None):
        output = io.StringIO()
        argv = ['scan', '--repos-file', str(self.file), '--scanner', str(self.scanner), *options, '--json']
        with patch('security.scan.github', side_effect=self.github), contextlib.redirect_stdout(output):
            if client:
                with patch('security.cli.Client', return_value=client):
                    code = main(argv)
            else:
                code = main(argv)
        return code, json.loads(output.getvalue())

    def test_plain_list_comments_urls_and_case_insensitive_duplicates(self):
        self.file.write_text('\ufeff# team repos\n\nhttps://github.com/Acme/One.git/\nacme/one\n  acme/two  \n')
        target = load_repositories(self.file, 4096)
        self.assertEqual([x['repository'] for x in target['repositories']], ['Acme/One', 'acme/two'])
        self.assertEqual(target['duplicates_skipped'], 1)
        self.assertEqual(len(target['sha256']), 64)

    def test_json_refs_override_shared_default_and_deduplicate(self):
        self.file.write_text(json.dumps(['acme/one', {'repo': 'https://github.com/acme/one', 'ref': 'main'},
                                         {'repo': 'acme/one', 'ref': 'release/1'}]))
        target = load_repositories(self.file, 4096, 'main')
        self.assertEqual([x['requested_ref'] for x in target['repositories']], ['main', 'release/1'])
        self.assertEqual(target['duplicates_skipped'], 1)

    def test_invalid_entries_reject_entire_file_before_scanning(self):
        cases = ['', '# nothing\n', '{}', '[42]', '[null]', '["acme/one", {"repo":"acme/two","resolve":"maven"}]',
                 '[{"repo":"acme/one","ref":""}]',
                 '[{"repo":"acme/one","ref":"x\\n"}]', 'acme/one\nhttps://token@github.com/acme/two',
                 'acme/one\nhttps://github.com/acme/two?token=secret', 'https://gitlab.com/acme/one',
                 '../repo', 'acme/*', 'acme/one # inline comments unsupported']
        for value in cases:
            with self.subTest(value=value):
                self.file.write_text(value)
                code, report = self.cli()
                self.assertEqual(code, 2, report)
                self.assertNotIn('token@', report['error'])
                self.assertNotIn('secret', report['error'])
        self.assertEqual(self.requests, [])
        self.assertFalse((self.root / 'state/security/reports').exists())

    def test_file_bounds_encoding_and_nonregular_files(self):
        self.file.write_bytes(b'\xff')
        with self.assertRaisesRegex(ValueError, 'UTF-8'):
            load_repositories(self.file, 4096)
        self.file.write_text('acme/one')
        with self.assertRaisesRegex(ValueError, 'max-bytes'):
            load_repositories(self.file, 3)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            load_repositories(self.root, 4096)
        fifo = self.root / 'fifo'
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            load_repositories(fifo, 4096)

    def test_same_cve_and_version_remain_attributable_to_both_repos(self):
        code, report = self.cli()
        self.assertEqual(code, 0, report)
        self.assertEqual(report['summary']['total'], 2)
        self.assertEqual({row['repository_target']['repository'] for row in report['findings']}, {'acme/one', 'acme/two'})
        self.assertTrue(all(row['repository_target']['commit'] == 'a' * 40 for row in report['findings']))
        self.assertEqual([x['total'] for x in report['repository_summaries']], [1, 1])
        self.assertTrue(all(x['status'] == 'complete' for x in report['repository_summaries']))
        self.assertTrue(all(x.get('repository_target') for x in report['coverage']))
        for child in report['repositories']:
            self.assertTrue(child['inventory'])
            self.assertTrue(child['packages'])
            self.assertTrue(child['scanner']['raw_output'])
        self.assertEqual(len(list((self.root / 'state/security/reports').glob('*.json'))), 1)
        self.assertEqual(latest_report()['target']['kind'], 'github_batch')

    def test_failed_middle_repository_does_not_stop_remaining_scans(self):
        self.file.write_text('acme/one\nacme/private\nacme/two\n')
        code, report = self.cli()
        self.assertEqual(code, 1)
        self.assertEqual(report['summary']['total'], 2)
        self.assertEqual([x['status'] for x in report['repository_summaries']], ['complete', 'incomplete', 'complete'])
        failed = [x for x in report['coverage'] if x['status'] == 'error']
        self.assertEqual(failed[0]['repository_target']['repository'], 'acme/private')
        self.assertIsNone(failed[0]['repository_target']['commit'])

    def test_fifteen_repositories_and_duplicate_are_all_accounted_for(self):
        self.file.write_text('\n'.join(f'acme/service-{index}' for index in range(15)) + '\nhttps://github.com/acme/service-0.git\n')
        code, report = self.cli()
        self.assertEqual(code, 0)
        self.assertEqual(len(report['repositories']), 15)
        self.assertEqual(report['summary']['total'], 15)
        self.assertEqual(len(self.requests), 15 * 4)
        self.assertEqual(report['target']['duplicates_skipped'], 1)

    def test_missing_file_and_malformed_json_are_usage_errors(self):
        self.file.unlink()
        code, report = self.cli()
        self.assertEqual(code, 2)
        self.file = self.root / 'repos.json'
        self.file.write_text('acme/one')
        code, report = self.cli()
        self.assertEqual(code, 2)
        self.assertEqual(self.requests, [])

    def test_distinct_refs_are_independent_and_encoded_before_github_request(self):
        self.file.write_text(json.dumps(['acme/one', {'repo': 'acme/one', 'ref': 'release/1'}]))
        code, report = self.cli('--ref', 'main')
        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['total'], 2)
        self.assertEqual({x['repository_target']['commit'] for x in report['findings']}, {'a' * 40, 'b' * 40})
        self.assertTrue(any(endpoint.endswith('/commits/release%2F1') for _, endpoint in self.requests))

    def test_filters_preserve_saved_evidence_and_refilter_per_repo_counts(self):
        code, view = self.cli('--cvss-min', '9')
        self.assertEqual(code, 0)
        self.assertEqual(view['summary']['shown'], 0)
        self.assertEqual(view['summary']['total'], 2)
        self.assertEqual([x['shown'] for x in view['repository_summaries']], [0, 0])
        self.assertEqual(len(latest_report()['findings']), 2)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(['report', '--latest', '--cvss-min', '9', '--include-unscored', '--json'])
        self.assertEqual(code, 0)
        self.assertEqual([x['shown'] for x in json.loads(output.getvalue())['repository_summaries']], [1, 1])

    def test_missing_scanner_is_incomplete_for_every_repository(self):
        code, report = self.cli('--scanner', str(self.root / 'missing-scanner'))
        self.assertEqual(code, 1)
        self.assertEqual([x['status'] for x in report['repository_summaries']], ['incomplete', 'incomplete'])

    def test_opt_in_diagnostics_remain_separate_for_each_repository(self):
        directory = self.root / 'diagnostics'
        code, report = self.cli('--scanner-diagnostics', str(directory))
        self.assertEqual(code, 0)
        paths = [entry['scanner']['diagnostics']['stderr_file'] for entry in report['repositories']]
        self.assertEqual(len(set(paths)), 2)
        self.assertTrue(all(Path(path).is_file() for path in paths))

    def test_kev_enrichment_runs_once_across_repos_and_failure_affects_all(self):
        client = fixtures.FakeClient([({'vulnerabilities': [{'cveID': 'CVE-2026-10001'}]}, {})])
        code, report = self.cli('--known-exploited', client=client)
        self.assertEqual(code, 0)
        self.assertEqual(len(client.urls), 1)
        self.assertTrue(all(row['known_exploited'] for row in report['findings']))
        code, report = self.cli('--known-exploited', client=fixtures.FakeClient([SourceError('offline')]))
        self.assertEqual(code, 1)
        self.assertEqual([x['status'] for x in report['repository_summaries']], ['incomplete', 'incomplete'])

    def test_dependabot_failure_preserves_scanner_results_and_continues(self):
        with patch('security.repositories.dependabot', side_effect=ValueError('alerts unavailable')) as alerts:
            code, report = self.cli('--dependabot')
        self.assertEqual(code, 1)
        self.assertEqual(alerts.call_count, 2)
        self.assertEqual(report['summary']['total'], 2)
        self.assertEqual([x['status'] for x in report['repository_summaries']], ['incomplete', 'incomplete'])

    def test_batch_never_executes_build_resolution_and_targets_are_exclusive(self):
        for options in [('--resolve', 'maven'), ('--resolve', 'gradle'), ('--repo', 'acme/other'), ('--path', '.')]:
            with self.subTest(options=options):
                code, _ = self.cli(*options)
                self.assertEqual(code, 2)
        self.assertEqual(self.requests, [])


if __name__ == '__main__':
    unittest.main()
