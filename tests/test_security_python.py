#!/usr/bin/env python3
"""CPython observation, CPE history, provenance and monitoring regressions."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'agent-security'))
from security.cli import main, parser, validate
from security.model import now
from security.monitor import load_config
from security.python_runtime import probe
from security.runtime import applicability, match_component
from security.sources import SourceError
from test_security_runtime import Client


def observation(version='3.12.4', upstream=True):
    return {'id': 'local-python', 'cpe': 'cpe:2.3:a:python:cpython:' + version + ':*:*:*:*:*:*:*',
            'python': {'implementation': 'cpython', 'version': version, 'releaselevel': 'final',
                       'serial': 0, 'executable': sys.executable, 'platform': sys.platform},
            'build_provenance': 'caller_verified_upstream' if upstream else 'vendor_patches_unknown',
            'identity_source': 'cpython_implementation_mapping',
            'evidence': {'kind': 'local_python_probe', 'source': sys.executable,
                         'observed_at': now(), 'verification': 'observed_local_process'}}


def advisory(product='python', **bounds):
    return {'id': 'CVE-2024-7592', 'published': '2024-08-19T19:15:08Z', 'lastModified': '2026-06-17T08:20:30Z',
            'descriptions': [{'lang': 'en', 'value': 'CPython cookie parsing fixture'}],
            'configurations': [{'nodes': [{'operator': 'OR', 'cpeMatch': [
                {'vulnerable': True, 'criteria': 'cpe:2.3:a:python:' + product + ':*:*:*:*:*:*:*:*',
                 **(bounds or {'versionStartIncluding': '3.12.0', 'versionEndExcluding': '3.12.6'})}]}]}]}


def page(cve=None):
    return {'totalResults': 1, 'vulnerabilities': [{'cve': cve or advisory()}]}


class PythonRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / 'monitor.json'
        self.env = patch.dict(os.environ, {'AGENT_DO_HOME': str(self.root / 'state')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def cli(self, *argv):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([*argv, '--json'])
        return code, json.loads(output.getvalue())

    def assess(self, component, client=None, *options):
        client = client or Client(page())
        with patch('security.runtime.probe_python', return_value=component), patch('security.cli.Client', return_value=client):
            code, report = self.cli('runtime', '--local-python', *options)
        return code, report, client

    def monitor_init(self, *extra):
        with patch('security.python_runtime.run') as run:
            code, payload = self.cli('monitor', 'init', '--config', str(self.config), '--local-python', '--python-upstream', '--interval-hours', '4', *extra)
        self.assertEqual(code, 0)
        run.assert_not_called()
        return payload

    def monitor_run(self, observed=None, client=None, allow=True):
        client = client or Client(page())
        with patch('security.runtime.probe_python', return_value=observed or observation()) as probe_run, patch('security.monitor.Client', return_value=client):
            code, report = self.cli('monitor', 'run', '--config', str(self.config), *(['--allow-collectors'] if allow else []))
        return code, report, probe_run

    def test_observes_real_interpreter_without_site_or_checkout_imports(self):
        marker = self.root / 'should-not-execute'
        (self.root / 'sitecustomize.py').write_text('from pathlib import Path;Path(' + repr(str(marker)) + ').touch()')
        (self.root / 'json.py').write_text('raise RuntimeError("checkout module imported")')
        args = parser().parse_args(['runtime', '--local-python', '--python', sys.executable, '--inventory-only'])
        with patch.dict(os.environ, {'PYTHONPATH': str(self.root)}):
            component = probe(args)
        self.assertEqual(component['python']['implementation'], sys.implementation.name)
        self.assertEqual(component['python']['version'], '.'.join(map(str, sys.version_info[:3])))
        self.assertEqual(component['build_provenance'], 'vendor_patches_unknown')
        self.assertFalse(marker.exists())

    def test_inventory_only_does_not_query_advisories(self):
        with patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--local-python', '--inventory-only')
        self.assertEqual(code, 0)
        self.assertEqual(report['scope'], 'runtime_inventory_only')
        self.assertEqual(report['runtime_components'][0]['evidence']['kind'], 'local_python_probe')
        get.assert_not_called()

    def test_invalid_python_selection_is_rejected_before_probe(self):
        for argv in (['runtime', '--python', sys.executable], ['runtime', '--python-upstream'],
                     ['monitor', 'init', '--config', str(self.config), '--path', str(self.root), '--python-upstream']):
            with self.subTest(argv=argv), patch('security.python_runtime.run') as run:
                code, payload = self.cli(*argv)
                self.assertEqual(code, 2)
                self.assertEqual(payload['status'], 'error')
                run.assert_not_called()

    def test_failed_probe_remains_incomplete_without_raw_diagnostics(self):
        result = subprocess.CompletedProcess([], 1, b'PRIVATE', b'SECRET')
        with patch('security.python_runtime.run', return_value=result), patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--local-python')
        self.assertEqual(code, 1)
        self.assertEqual(report['findings'], [])
        self.assertNotIn('PRIVATE', json.dumps(report))
        self.assertNotIn('SECRET', json.dumps(report))
        get.assert_not_called()

    def test_alternate_implementation_and_prerelease_are_not_mapped(self):
        for key, value in [('implementation', 'pypy'), ('releaselevel', 'candidate')]:
            data = observation()['python'];data[key] = value
            result = subprocess.CompletedProcess([], 0, json.dumps(data).encode(), b'')
            with self.subTest(key=key), patch('security.python_runtime.run', return_value=result), patch('security.sources.Client.get') as get:
                code, report = self.cli('runtime', '--local-python')
            self.assertEqual(code, 1)
            self.assertNotIn('cpe', report['runtime_components'][0])
            get.assert_not_called()

    def test_malformed_probe_data_never_establishes_runtime_identity(self):
        for body in (b'not-json', b'{}', b'[]', json.dumps({**observation()['python'], 'serial': True}).encode()):
            with self.subTest(body=body), patch('security.python_runtime.run', return_value=subprocess.CompletedProcess([], 0, body, b'')):
                code, report = self.cli('runtime', '--local-python', '--inventory-only')
            self.assertEqual(code, 1)
            self.assertEqual(report['runtime_components'], [])

    def test_historical_and_current_cpe_products_match_same_runtime(self):
        for product in ('python', 'cpython'):
            cve = advisory(product)
            target = observation()
            self.assertIs(applicability(cve, [target], target), True)
            self.assertIs(applicability(cve, [observation('3.12.6')], observation('3.12.6')), False)
        other = advisory('pypy')
        self.assertIs(applicability(other, [observation()], observation()), False)

    def test_version_boundaries_environment_and_unrelated_vendor(self):
        target = observation()
        cve = advisory(versionEndIncluding='3.12.4')
        self.assertIs(applicability(cve, [target], target), True)
        cve = advisory(versionEndExcluding='3.12.4')
        self.assertIs(applicability(cve, [target], target), False)
        cve = advisory();cve['configurations'][0]['nodes'][0]['cpeMatch'][0]['criteria'] = 'cpe:2.3:a:other:python:*:*:*:*:*:*:*:*'
        self.assertIs(applicability(cve, [target], target), False)
        cve = advisory();node=cve['configurations'][0]['nodes'][0];node['operator']='AND'
        node['cpeMatch'].append({'vulnerable': False, 'criteria': 'cpe:2.3:o:microsoft:windows_11:23h2:*:*:*:*:*:*:*'})
        self.assertIsNone(applicability(cve, [target], target))

    def test_unknown_vendor_backports_keep_matches_as_candidates(self):
        code, r, client = self.assess(observation(upstream=False))
        self.assertEqual(code, 1)
        self.assertEqual(r['findings'][0]['runtime_match']['relation'], 'candidate')
        self.assertTrue(any(x['source'].startswith('Python build provenance:') and x['status']=='limited' for x in r['coverage']))
        self.assertIn('python%3A%2A', client.urls[0])
        self.assertNotIn('3.12.4', client.urls[0])

    def test_verified_upstream_version_match_and_patched_exclusion(self):
        code, r, _ = self.assess(observation())
        self.assertEqual(code, 0)
        self.assertEqual(r['findings'][0]['runtime_match']['relation'], 'inventory_match')
        code, r, _ = self.assess(observation('3.12.6'))
        self.assertEqual(code, 0)
        self.assertEqual(r['findings'], [])

    def test_zero_matches_without_build_provenance_still_has_coverage_gap(self):
        code, r, _ = self.assess(observation('3.12.6', upstream=False))
        self.assertEqual(code, 1)
        self.assertEqual(r['findings'], [])
        self.assertTrue(any(x['status'] == 'limited' for x in r['coverage']))

    def test_nvd_failure_and_truncation_remain_incomplete(self):
        code, r, _ = self.assess(observation(), Client(SourceError('timeout')))
        self.assertEqual(code, 1)
        self.assertIn('timeout', r['coverage'][-1]['error'])
        body = page();body['totalResults'] = 2
        code, r, _ = self.assess(observation(), Client(body), '--limit', '1')
        self.assertEqual(code, 1)
        self.assertEqual(r['coverage'][-1]['status'], 'truncated')
        self.assertEqual(len(r['findings']), 1)

    def test_python_and_java_can_be_observed_together(self):
        java = {'id':'local-java','cpe':'cpe:2.3:a:oracle:jdk:21.0.1:*:*:*:*:*:*:*',
                'evidence': {'kind':'local_java_probe','source':'fixture','observed_at':now(),'verification':'observed_local_process'}}
        with patch('security.runtime.probe_java',return_value=java), patch('security.runtime.probe_python',return_value=observation()):
            code, report = self.cli('runtime','--local-java','--local-python','--inventory-only')
        self.assertEqual(code,0)
        self.assertEqual({c['id'] for c in report['runtime_components']},{'local-java','local-python'})

    def test_monitor_init_saves_probe_and_four_hour_interval_without_execution(self):
        payload = self.monitor_init('--path', str(self.root))
        self.assertEqual(payload['targets'], 2)
        config = load_config(self.config, 1000000)
        self.assertEqual(config['interval_hours'], 4)
        probe = config['targets'][1]['runtime_probe']
        self.assertTrue(Path(probe['python']).is_absolute())
        self.assertTrue(probe['python_upstream'])
        self.assertNotIn('version', probe)

    def test_monitor_reprobes_versions_then_resolves_only_complete_assessments(self):
        self.monitor_init()
        code, first, probe_run = self.monitor_run()
        self.assertEqual(code, 0)
        self.assertEqual(first['counts']['new'], 1)
        probe_run.assert_called_once()
        code, second, _ = self.monitor_run()
        self.assertEqual(second['counts']['ongoing'], 1)
        code, patched, _ = self.monitor_run(observation('3.12.6'))
        self.assertEqual(code, 0)
        self.assertEqual(patched['counts']['resolved'], 1)

    def test_monitor_requires_explicit_probe_permission_and_retains_findings(self):
        self.monitor_init();self.monitor_run()
        code, report, probe_run = self.monitor_run(allow=False)
        self.assertEqual(code, 1)
        self.assertEqual(report['counts']['unverified'], 1)
        self.assertEqual(report['counts']['resolved'], 0)
        probe_run.assert_not_called()

    def test_monitor_timeout_after_positive_retains_unverified(self):
        self.monitor_init();self.monitor_run()
        code, report, _ = self.monitor_run(client=Client(SourceError('NVD timeout')))
        self.assertEqual(code, 1)
        self.assertEqual(report['counts']['unverified'], 1)
        self.assertEqual(report['counts']['resolved'], 0)
        self.assertTrue(any('NVD timeout' in x['message'] for x in report['assessment_summary']['coverage_issues']))

    def test_schedule_requires_permission_and_exports_due_without_installing(self):
        self.monitor_init()
        code, _ = self.cli('monitor','schedule','--config',str(self.config))
        self.assertEqual(code,2)
        code, report = self.cli('monitor','schedule','--config',str(self.config),'--allow-collectors')
        self.assertEqual(code,0)
        self.assertFalse(report['installed'])
        self.assertIn('--allow-collectors',report['cron'])
        self.assertIn('--due',report['cron'])
        self.assertEqual(report['interval_hours'],4)

    def test_invalid_probe_config_rejected(self):
        self.monitor_init()
        original=json.loads(self.config.read_text())
        for key,value in [('python_upstream','yes'),('probe_timeout',False),('python','')]:
            value_config=copy.deepcopy(original);value_config['targets'][0]['runtime_probe'][key]=value
            self.config.write_text(json.dumps(value_config))
            with self.subTest(key=key),self.assertRaises(ValueError):load_config(self.config,1000000)


if __name__ == '__main__':
    unittest.main()
