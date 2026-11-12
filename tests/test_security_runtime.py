#!/usr/bin/env python3
"""Offline runtime evidence, NVD applicability and false-confirmation regressions."""
import contextlib
import copy
import io
import json
import os
import sys
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'agent-security'))
from security.cli import main, parser
from security.runtime import (applicability, declared_settings,
                              load_inventory, match_component, probe_java)
from security.sources import SourceError
from security.store import read_report

JAVA = 'cpe:2.3:a:oracle:jdk:17.0.12:*:*:*:*:*:*:*'
PATTERN = 'cpe:2.3:a:oracle:jdk:*:*:*:*:*:*:*:*'
WINDOWS = 'cpe:2.3:o:microsoft:windows_11:23h2:*:*:*:*:*:*:*'


def component(identity='jdk', cpe=JAVA, deployment=None):
    value = {'id': identity, 'cpe': cpe, 'evidence': {'kind': 'manual', 'source': 'fixture java -version', 'observed_at': '2026-10-01T00:00:00Z'}}
    if deployment:
        value['deployment'] = deployment
    return value


def match(cpe=PATTERN, **bounds):
    return {'vulnerable': True, 'criteria': cpe, **bounds}


def advisory(*nodes):
    return {'id': 'CVE-2026-10001', 'descriptions': [{'lang': 'en', 'value': 'Runtime fixture'}],
            'published': '2026-10-01T00:00:00Z', 'lastModified': '2026-10-02T00:00:00Z',
            'configurations': [{'operator': 'OR', 'nodes': list(nodes or [{'operator': 'OR', 'cpeMatch': [match(versionEndExcluding='17.0.13')]}])}]}


class Client:
    def __init__(self, *pages):
        self.pages, self.receipts, self.urls = iter(pages), [], []

    def get(self, url):
        self.urls.append(url)
        self.receipts.append({'url': url, 'fetched_at': '2026-10-22T00:00:00Z', 'stale': False})
        value = next(self.pages)
        if isinstance(value, Exception):
            raise value
        return value, {}


def page(cve=None, total=1):
    return {'totalResults': total, 'vulnerabilities': [{'cve': cve or advisory()}]}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'AGENT_DO_HOME': str(self.root / 'state')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def inventory(self, *entries):
        path = self.root / 'runtimes.json'
        path.write_text(json.dumps({'schema_version': 1, 'components': list(entries or [component()])}))
        return path

    def args(self, *argv):
        return parser().parse_args(['runtime', *argv])

    def cli(self, *argv):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(list(argv) + ['--json'])
        return code, json.loads(stream.getvalue())

    def test_declarations_never_become_runtime_or_trigger_build(self):
        (self.root / 'pom.xml').write_text('<project><properties><java.version>17</java.version><maven.compiler.release>${java.version}</maven.compiler.release></properties></project>')
        (self.root / 'build.gradle.kts').write_text("java { toolchain { languageVersion.set(JavaLanguageVersion.of(21)) } }; password = 'secret-value'")
        (self.root / 'Dockerfile').write_text('FROM eclipse-temurin:17-jre')
        with patch('security.runtime.run') as run, patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--path', str(self.root))
        self.assertEqual(code, 1)
        self.assertEqual(len(report['declared_settings']), 4)
        self.assertNotIn('secret-value', json.dumps(report))
        self.assertEqual(report['runtime_components'], [])
        self.assertTrue(all(not hint['establishes_installed_runtime'] for hint in report['declared_settings']))
        run.assert_not_called()
        get.assert_not_called()

    def test_inventory_only_offline_and_does_not_claim_cve_assessment(self):
        with patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--inventory', str(self.inventory()), '--inventory-only')
        self.assertEqual(code, 0)
        self.assertEqual(report['scope'], 'runtime_inventory_only')
        self.assertEqual(report['runtime_components'][0]['evidence']['verification'], 'user_supplied_not_independently_verified')
        get.assert_not_called()

    def test_version_boundaries_and_exact_version(self):
        for key, boundary, expected in [('versionStartIncluding', '17.0.12', True), ('versionStartExcluding', '17.0.12', False), ('versionEndIncluding', '17.0.12', True), ('versionEndExcluding', '17.0.12', False), ('versionEndExcluding', '17.0.13', True)]:
            with self.subTest(key=key):
                self.assertIs(match_component(match(**{key: boundary}), component()), expected)
        self.assertIs(match_component(match(cpe=JAVA), component()), True)
        self.assertIs(match_component(match(cpe=JAVA.replace('17.0.12', '17.0.13')), component()), False)

    def test_java_build_metadata_and_legacy_update_bounds(self):
        self.assertIs(match_component(match(versionEndExcluding='17.0.13'), component(cpe=JAVA.replace('17.0.12', '17.0.12+7'))), True)
        old = component(cpe=JAVA.replace('17.0.12:*', '1.8.0:update_422'))
        self.assertIs(match_component(match(versionEndExcluding='1.8.0_431'), old), True)
        self.assertIs(match_component(match(versionEndExcluding='1.8.0_421'), old), False)
        self.assertIs(match_component(match(cpe=PATTERN.replace('*:*:*:*:*:*:*:*', '1.8.0:update_421:*:*:*:*:*:*')), old), False)

    def test_non_numeric_ranges_and_specific_platform_fields_are_uncertain(self):
        self.assertIsNone(match_component(match(versionEndExcluding='17.0.13-ea'), component()))
        self.assertIsNone(match_component(match(cpe=PATTERN.replace(':*:*:*:*:*:*:*:*', ':*:*:*:*:*:linux:*:*')), component()))
        self.assertIs(match_component(match(cpe=PATTERN.replace('oracle', 'other_vendor')), component()), False)

    def test_environment_prerequisite_preserved(self):
        java = component()
        windows = component('os', WINDOWS)
        cve = advisory({'operator': 'AND', 'cpeMatch': [match(), {'vulnerable': False, 'criteria': WINDOWS}]})
        self.assertIsNone(applicability(cve, [java], java))
        self.assertIs(applicability(cve, [java, windows], java), True)
        self.assertIs(applicability(cve, [java, component('os', WINDOWS.replace('23h2', '22h2'))], java), None)  # version label ordering unsupported

    def test_unrelated_or_branch_cannot_confirm_candidate_target(self):
        java, windows = component(), component('os', WINDOWS)
        cve = advisory({'operator': 'AND', 'cpeMatch': [match(), {'vulnerable': False, 'criteria': WINDOWS.replace('23h2', '24h2')}]},
                       {'operator': 'OR', 'cpeMatch': [match(WINDOWS)]})
        self.assertIsNone(applicability(cve, [java, windows], java))

    def test_negated_and_non_vulnerable_match_never_confirms_target(self):
        self.assertIs(applicability(advisory({'negate': True, 'cpeMatch': [match()]}), [component()], component()), False)
        self.assertIs(applicability(advisory({'cpeMatch': [{'criteria': PATTERN, 'vulnerable': False}]}), [component()], component()), False)

    def test_missing_configs_and_unsupported_cpe_remain_candidates(self):
        cve = advisory()
        cve['configurations'] = []
        self.assertIsNone(applicability(cve, [component()], component()))
        cve = advisory({'cpeMatch': [match(PATTERN.replace('oracle', r'oracle\!'))]})
        self.assertIsNone(applicability(cve, [component()], component()))

    def test_exact_probe_values_are_observed_not_project_inferred(self):
        args = self.args('--local-java')
        output = '    java.vendor = Oracle Corporation\n    java.vm.name = Java HotSpot(TM) 64-Bit Server VM\n    java.version = 17.0.12\n    java.runtime.version = 17.0.12+7\n    user.home = /secret\n'
        with patch('security.runtime.shutil.which', return_value='/usr/bin/java'), patch('security.runtime.run', return_value=subprocess.CompletedProcess([], 0, b'', output.encode())) as run:
            result = probe_java(args)
        self.assertEqual(result['cpe'], JAVA)
        self.assertNotIn('secret', json.dumps(result))
        self.assertEqual(result['evidence']['verification'], 'observed_local_process')
        self.assertIn('-XshowSettings:properties', run.call_args.args[0])

    @unittest.skipUnless(shutil.which('java'), 'installed Java unavailable')
    def test_installed_java_probe_returns_observed_properties_offline(self):
        with patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--local-java', '--inventory-only')
        self.assertEqual(code, 0)
        self.assertIn('java.version', report['runtime_components'][0]['properties'])
        self.assertEqual(report['runtime_components'][0]['evidence']['verification'], 'observed_local_process')
        get.assert_not_called()

    def test_legacy_oracle_probe_requires_explicit_jdk_or_jre_identity(self):
        output = b'java.vendor = Oracle Corporation\njava.vm.name = Java HotSpot(TM) 64-Bit Server VM\njava.version = 1.8.0_421'
        with patch('security.runtime.shutil.which', return_value='/usr/bin/java'), patch('security.runtime.run', return_value=subprocess.CompletedProcess([], 0, b'', output)):
            self.assertNotIn('cpe', probe_java(self.args('--local-java')))
            selected = probe_java(self.args('--local-java', '--java-cpe', PATTERN))
        self.assertIn(':oracle:jdk:1.8.0:update_421:', selected['cpe'])

    def test_non_oracle_vendor_needs_explicit_mapping(self):
        with patch('security.runtime.shutil.which', return_value='/usr/bin/java'), patch('security.runtime.run', return_value=subprocess.CompletedProcess([], 0, b'', b'java.vendor = Eclipse Adoptium\njava.version = 17.0.12')):
            self.assertNotIn('cpe', probe_java(self.args('--local-java')))
            result = probe_java(self.args('--local-java', '--java-cpe', PATTERN.replace('oracle:jdk', 'fixture:fixture_jdk')))
        self.assertEqual(result['identity_source'], 'caller_selected')

    def test_oracle_identity_on_adoptium_is_incomplete_without_nvd_lookup(self):
        output = b'java.vendor = Eclipse Adoptium\njava.version = 21.0.8\njava.runtime.version = 21.0.8+9-LTS'
        with patch('security.runtime.shutil.which', return_value='/usr/bin/java'), patch('security.runtime.run', return_value=subprocess.CompletedProcess([], 0, b'', output)), patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--local-java', '--java-cpe', PATTERN)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['findings'], [])
        self.assertIn('non-Oracle vendor', report['coverage'][0]['error'])
        get.assert_not_called()

    def test_cpe_errors_include_format_example_and_offline_inspection_command(self):
        for value in ('not-a-cpe', PATTERN.replace(':*:*:*:*:*:*:*:*', ':21.*:*:*:*:*:*:*:*'), JAVA):
            with self.subTest(value=value):
                code, report = self.cli('runtime', '--local-java', '--java-cpe', value)
                self.assertEqual(code, 2)
                self.assertIn('format example:', report['error'])
                self.assertIn('--java-cpe "' + PATTERN + '"', report['error'])
                self.assertIn('--inventory-only', report['error'])

    def xstream_fixture(self):
        return json.loads((ROOT / 'tests/fixtures/security/CVE-2021-21349.json').read_text())['cve']

    def test_public_xstream_configuration_excludes_modern_jdk(self):
        cve = self.xstream_fixture()
        target = component(cpe=JAVA.replace('oracle:jdk', 'oracle:java_se').replace('17.0.12', '21.0.8'))
        self.assertIs(applicability(cve, [target], target), False)
        with patch('security.cli.Client', return_value=Client(page(cve))):
            code, report = self.cli('runtime', '--inventory', str(self.inventory(target)))
        self.assertEqual(code, 1)  # legacy java_se is explicitly limited JDK coverage
        self.assertEqual(report['findings'], [])
        self.assertEqual(report['coverage'][0]['status'], 'limited')
        self.assertEqual(report['coverage'][-1]['records_examined'], 1)

    def test_public_xstream_configuration_retains_affected_historical_jdk(self):
        cve = self.xstream_fixture()
        for version in ('8u311:*', '1.8.0:update_311', '1.8.0_311:*', '7u321:*', '1.7.0:update_321', '1.7.0_321:*'):
            with self.subTest(version=version):
                target = component(cpe=JAVA.replace('oracle:jdk', 'oracle:java_se').replace('17.0.12:*', version))
                self.assertIs(applicability(cve, [target], target), True)
        target = component(cpe=JAVA.replace('oracle:jdk', 'oracle:java_se').replace('17.0.12:*', '8u312:*'))
        self.assertIs(applicability(cve, [target], target), False)

    def test_legacy_short_version_numeric_range_boundaries(self):
        old = component(cpe=JAVA.replace('17.0.12:*', '1.8.0:update_422'))
        self.assertIs(match_component(match(versionEndExcluding='8u431'), old), True)
        self.assertIs(match_component(match(versionEndExcluding='8u421'), old), False)
        self.assertIs(match_component(match(cpe=PATTERN.replace(':*:*:*:*:*:*:*:*', ':8u422:*:*:*:*:*:*:*')), old), True)
        self.assertIs(match_component(match(cpe=PATTERN.replace(':*:*:*:*:*:*:*:*', ':7u321:*:*:*:*:*:*:*')), component()), False)

    def test_project_java17_is_separate_from_observed_java21(self):
        (self.root / 'pom.xml').write_text('<project><properties><java.version>17</java.version></properties></project>')
        output = b'java.vendor = Oracle Corporation\njava.vm.name = Java HotSpot(TM) 64-Bit Server VM\njava.version = 21.0.8\njava.runtime.version = 21.0.8+9-LTS'
        cve = advisory({'cpeMatch': [match(versionStartIncluding='21', versionEndExcluding='21.0.9')]})
        with patch('security.runtime.shutil.which', return_value='/usr/bin/java'), patch('security.runtime.run', return_value=subprocess.CompletedProcess([], 0, b'', output)), patch('security.cli.Client', return_value=Client(page(cve))):
            code, report = self.cli('runtime', '--path', str(self.root), '--local-java')
        self.assertEqual(code, 0)
        self.assertEqual(report['declared_settings'][0]['value'], '17')
        self.assertEqual(report['findings'][0]['package']['version'], '21.0.8')
        self.assertIn('21.0.8', report['runtime_components'][0]['cpe'])

    def test_probe_failure_cannot_appear_as_clean_scan(self):
        with patch('security.runtime.shutil.which', return_value=None):
            code, report = self.cli('runtime', '--local-java')
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'incomplete')

    def test_invalid_inventory_rejected_before_any_lookup(self):
        invalid = [component(cpe=PATTERN), component(cpe='not cpe'), {**component(), 'evidence': {'kind': 'verified'}}, {**component(), 'deployment': {'unknown': 'x'}}]
        for entry in invalid:
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                load_inventory(self.inventory(entry), 10000)
        with self.assertRaises(ValueError):
            load_inventory(self.inventory(component(), component()), 10000)
        with self.assertRaises(ValueError):
            load_inventory(self.inventory(), 10)

    def test_xml_entities_and_byte_limits_rejected(self):
        (self.root / 'pom.xml').write_text('<!DOCTYPE x [<!ENTITY x "bad">]><project/>')
        with self.assertRaises(ValueError):
            declared_settings(self.root, 1000)
        with self.assertRaises(ValueError):
            declared_settings(self.root, 2)

    def test_invalid_flag_combinations(self):
        for argv in [[], ['--java', '/usr/bin/java'], ['--local-java', '--ecosystem', 'java'], ['--local-java', '--java-cpe', JAVA], ['--local-java', '--inventory-only', '--kev']]:
            with self.subTest(argv=argv):
                code, _ = self.cli('runtime', *argv)
                self.assertEqual(code, 2)

    def test_complete_findings_saved_and_refilterable_exit_zero(self):
        path = self.inventory()
        client = Client(page())
        with patch('security.cli.Client', return_value=client):
            code, report = self.cli('runtime', '--inventory', str(path))
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['findings'][0]['runtime_match']['relation'], 'inventory_match')
        saved = read_report(report['saved_report'])
        self.assertEqual(len(saved['findings']), 1)
        code, view = self.cli('report', '--file', report['saved_report'], '--severity', 'critical')
        self.assertEqual(code, 0)
        self.assertEqual(view['summary']['total'], 1)
        self.assertEqual(view['summary']['shown'], 0)
        self.assertNotIn('maven', json.dumps(saved['findings'][0]['package']))

    def test_truncation_and_failed_second_page_preserve_evidence(self):
        for pages, limit, status in [([page(total=2)], '1', 'truncated'), ([page(total=2), SourceError('fixture failure')], '2', 'error')]:
            with self.subTest(status=status), patch('security.cli.Client', return_value=Client(*pages)):
                code, report = self.cli('runtime', '--inventory', str(self.inventory()), '--limit', limit)
            self.assertEqual(code, 1)
            self.assertEqual(report['coverage'][-1]['status'], status)
            self.assertEqual(len(report['findings']), 1)

    def test_rejected_and_unaffected_advisories_excluded(self):
        rejected = advisory()
        rejected['vulnStatus'] = 'Rejected'
        fixed = advisory({'cpeMatch': [match(versionEndExcluding='17.0.12')]})
        client = Client({'totalResults': 2, 'vulnerabilities': [{'cve': rejected}, {'cve': fixed}]})
        with patch('security.cli.Client', return_value=client):
            code, report = self.cli('runtime', '--inventory', str(self.inventory()))
        self.assertEqual(code, 0)
        self.assertEqual(report['findings'], [])

    def test_cross_host_inventory_cannot_satisfy_environment(self):
        java = component(deployment={'host': 'a'})
        windows = component('os', WINDOWS, {'host': 'b'})
        cve = advisory({'operator': 'AND', 'cpeMatch': [match(), {'vulnerable': False, 'criteria': WINDOWS}]})
        # Second query concerns OS; no Java vulnerable witness for that target.
        for same_host in (False, True):
            windows['deployment']['host'] = 'a' if same_host else 'b'
            with patch('security.cli.Client', return_value=Client(page(cve), page(cve))):
                code, report = self.cli('runtime', '--inventory', str(self.inventory(java, windows)))
            self.assertEqual(code, 0 if same_host else 1)
            self.assertEqual(report['findings'][0]['runtime_match']['relation'], 'inventory_match' if same_host else 'candidate')

    def monitor_init(self, inventory):
        config = self.root / 'monitor.json'
        code, result = self.cli('monitor', 'init', '--config', str(config), '--runtime-inventory', str(inventory))
        self.assertEqual(code, 0)
        return config

    def monitor_run(self, config, *pages):
        with patch('security.monitor.Client', return_value=Client(*pages)):
            return self.cli('monitor', 'run', '--config', str(config))

    def test_runtime_monitor_new_ongoing_and_version_update_resolves(self):
        inventory = self.inventory()
        config = self.monitor_init(inventory)
        code, first = self.monitor_run(config, page())
        self.assertEqual(code, 0)
        self.assertEqual(first['counts']['new'], 1)
        _, second = self.monitor_run(config, page())
        self.assertEqual(second['counts']['ongoing'], 1)
        self.inventory(component(cpe=JAVA.replace('17.0.12', '17.0.13')))
        _, fixed = self.monitor_run(config, page())
        self.assertEqual(fixed['counts']['resolved'], 1)
        self.assertEqual(fixed['counts']['unverified'], 0)

    def test_runtime_monitor_missing_component_scope_stays_unverified(self):
        inventory = self.inventory(component(), component('jdk-other'))
        config = self.monitor_init(inventory)
        _, first = self.monitor_run(config, page(), page())
        self.assertEqual(first['counts']['new'], 2)
        self.inventory(component())
        _, second = self.monitor_run(config, page())
        self.assertEqual(second['counts']['unverified'], 2)
        self.assertEqual(second['counts']['resolved'], 0)

    def test_runtime_monitor_failure_and_deployment_change_never_resolve(self):
        inventory = self.inventory(component(deployment={'host': 'a'}))
        config = self.monitor_init(inventory)
        self.monitor_run(config, page())
        code, failed = self.monitor_run(config, SourceError('fixture offline'))
        self.assertEqual(code, 1)
        self.assertEqual(failed['counts']['unverified'], 1)
        self.inventory(component(cpe=JAVA.replace('17.0.12', '17.0.13'), deployment={'host': 'b'}))
        code, moved = self.monitor_run(config, page())
        self.assertEqual(code, 0)
        self.assertEqual(moved['counts']['unverified'], 1)
        self.assertEqual(moved['counts']['resolved'], 0)

    def test_runtime_monitor_missing_file_preserves_history(self):
        inventory = self.inventory()
        config = self.monitor_init(inventory)
        self.monitor_run(config, page())
        inventory.unlink()
        code, failed = self.monitor_run(config)
        self.assertEqual(code, 1)
        self.assertEqual(failed['counts']['unverified'], 1)
        self.assertEqual(failed['counts']['resolved'], 0)

    def test_mixed_source_and_runtime_portfolio_keeps_independent_transitions(self):
        from security.model import finding
        inventory = self.inventory()
        config = self.root / 'mixed-monitor.json'
        code, created = self.cli('monitor', 'init', '--config', str(config), '--runtime-inventory', str(inventory), '--path', str(self.root))
        self.assertEqual(code, 0)
        self.assertEqual(created['targets'], 2)
        row = finding(['CVE-2026-22222'], 'Library fixture', 'fixture', 'https://example.invalid', package={'ecosystem': 'Maven', 'name': 'example:library', 'version': '1.0'})
        def scan(args, report):
            report['findings'] = [copy.deepcopy(row)]
            report['coverage'] = [{'source': 'source fixture', 'status': 'ok'}]
            report['scanner'] = {'version': 'fixture-v2'}
        with patch('security.monitor.scan', side_effect=scan):
            code, first = self.monitor_run(config, page())
            self.assertEqual(code, 0)
            self.assertEqual(first['counts']['new'], 2)
            code, partial = self.monitor_run(config, SourceError('fixture runtime lookup failure'))
            self.assertEqual(code, 1)
            self.assertEqual(partial['counts']['ongoing'], 1)
            self.assertEqual(partial['counts']['unverified'], 1)
            self.assertEqual(partial['counts']['resolved'], 0)
            self.inventory(component(cpe=JAVA.replace('17.0.12', '17.0.13')))
            code, second = self.monitor_run(config, page())
            self.assertEqual(code, 0)
            self.assertEqual(second['counts']['ongoing'], 1)
            self.assertEqual(second['counts']['resolved'], 1)
            self.assertEqual(second['counts']['unverified'], 0)
            code, failed = self.monitor_run(config, SourceError('fixture runtime lookup failure'))
            self.assertEqual(code, 1)
            self.assertEqual(failed['counts']['ongoing'], 1)
            self.assertEqual(failed['counts']['resolved'], 0)
        source_report = read_report(second['source_report'])
        self.assertEqual(source_report['scope'], 'portfolio_source_and_explicit_runtime_inventory')
        self.assertEqual({child['command'] for child in source_report['repositories']}, {'scan', 'runtime'})

    def test_runtime_schedule_exports_same_limit_without_installation_or_scan(self):
        config = self.monitor_init(self.inventory())
        with patch('security.monitor.subprocess.run') as process, patch('security.sources.Client.get') as get:
            code, result = self.cli('monitor', 'schedule', '--config', str(config), '--runtime-limit', '2500')
        self.assertEqual(code, 0)
        self.assertFalse(result['installed'])
        self.assertIn('--runtime-limit 2500', result['cron'])
        self.assertIn('--due', result['cron'])
        process.assert_not_called()
        get.assert_not_called()

    def test_public_modern_jdk_advisory_is_detected_for_17_0_12(self):
        cve = json.loads((ROOT / 'tests/fixtures/security/CVE-2024-21235.json').read_text())['cve']
        target = component()
        self.assertIs(applicability(cve, [target], target), True)
        client = Client(page(cve))
        with patch('security.cli.Client', return_value=client):
            code, report = self.cli('runtime', '--inventory', str(self.inventory(target)))
        self.assertEqual(code, 0)
        self.assertEqual(report['findings'][0]['id'], 'CVE-2024-21235')
        self.assertEqual(report['findings'][0]['runtime_match']['relation'], 'inventory_match')
        self.assertIn('oracle%3Ajdk%3A', client.urls[0])
        changed = component(cpe=JAVA.replace('17.0.12', '17.0.13'))
        self.assertIs(applicability(cve, [changed], changed), False)

    def test_legacy_java_se_empty_query_cannot_claim_complete_jdk_coverage(self):
        legacy = component(cpe=JAVA.replace('oracle:jdk', 'oracle:java_se'))
        with patch('security.cli.Client', return_value=Client({'totalResults': 0, 'vulnerabilities': []})):
            code, report = self.cli('runtime', '--inventory', str(self.inventory(legacy)))
        self.assertEqual(code, 1)
        self.assertEqual(report['coverage'][0]['status'], 'limited')
        self.assertIn('modern oracle:jdk/jre', report['coverage'][0]['reason'])

    def test_nvd_update_without_underscore_matches_observed_java8_update(self):
        criterion = PATTERN.replace(':*:*:*:*:*:*:*:*', ':1.8.0:update421:*:*:*:*:*:*')
        target = component(cpe=JAVA.replace('17.0.12:*', '1.8.0:update_421'))
        self.assertIs(match_component(match(criterion), target), True)
        self.assertIs(match_component(match(criterion), component(cpe=JAVA.replace('17.0.12:*', '1.8.0:update_422'))), False)

    def test_mixed_github_list_and_runtime_init_does_not_scan(self):
        repos = self.root / 'repos.txt'
        repos.write_text('example/one\nexample/two\n')
        config = self.root / 'mixed-github.json'
        with patch('security.monitor.scan') as scan, patch('security.sources.Client.get') as get:
            code, result = self.cli('monitor', 'init', '--config', str(config), '--repos-file', str(repos), '--runtime-inventory', str(self.inventory()))
        self.assertEqual(code, 0)
        self.assertEqual(result['targets'], 3)
        self.assertEqual(len(json.loads(config.read_text())['targets']), 3)
        scan.assert_not_called()
        get.assert_not_called()

    def test_mixed_maven_runtime_init_preserves_build_opt_in(self):
        config = self.root / 'mixed-maven.json'
        code, created = self.cli('monitor', 'init', '--config', str(config), '--path', str(self.root), '--resolve', 'maven', '--runtime-inventory', str(self.inventory()))
        self.assertEqual(code, 0)
        self.assertEqual(created['targets'], 2)
        with patch('security.monitor.scan') as scan:
            code, result = self.monitor_run(config, page())
        self.assertEqual(code, 1)
        self.assertEqual(result['counts']['new'], 1)  # runtime proceeds independently
        scan.assert_not_called()
        self.assertEqual(result['targets'][0]['status'], 'incomplete')
        self.assertEqual(result['targets'][1]['status'], 'complete')

    def test_incomplete_candidates_are_committed_and_timeout_is_top_level(self):
        config = self.monitor_init(self.inventory())
        candidate = advisory({'operator': 'AND', 'cpeMatch': [match(), {'vulnerable': False, 'criteria': WINDOWS}]})
        code, first = self.monitor_run(config, page(candidate))
        self.assertEqual(code, 1)
        self.assertEqual(first['counts']['new'], 1)
        self.assertEqual(first['assessment_summary']['findings_observed'], 1)
        self.assertEqual(first['assessment_summary']['runtime_candidates'], 1)
        self.assertEqual(first['assessment_summary']['coverage_issues'][0]['status'], 'uncertain')
        source = read_report(first['source_report'])
        self.assertEqual(source['findings'][0]['runtime_match']['relation'], 'candidate')
        code, repeated = self.monitor_run(config, page(candidate))
        self.assertEqual(code, 1)
        self.assertEqual(repeated['counts']['ongoing'], 1)
        code, failed = self.monitor_run(config, SourceError('TimeoutError: advisory fetch failed'))
        self.assertEqual(code, 1)
        self.assertEqual(failed['counts']['unverified'], 1)
        self.assertEqual(failed['counts']['resolved'], 0)
        summary = failed['assessment_summary']
        self.assertEqual(summary['findings_observed'], 0)
        self.assertEqual(summary['runtime_candidates'], 0)
        self.assertEqual(summary['targets_incomplete'], 1)
        self.assertEqual(summary['coverage_issues'][0]['status'], 'error')
        self.assertIn('TimeoutError', summary['coverage_issues'][0]['message'])
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            code = main(['monitor', 'report', '--config', str(config)])
        self.assertEqual(code, 1)
        rendered = text.getvalue()
        self.assertIn('ERROR: NVD runtime:jdk', rendered)
        self.assertIn('TimeoutError: advisory fetch failed', rendered)
        self.assertIn('zero findings or zero changes do not establish absence', rendered)
        self.assertLess(rendered.index('TimeoutError'), rendered.index('  new:'))

    def test_first_runtime_timeout_has_no_false_clean_zero_summary(self):
        config = self.monitor_init(self.inventory())
        code, failed = self.monitor_run(config, SourceError('TimeoutError: advisory fetch failed'))
        self.assertEqual(code, 1)
        self.assertTrue(all(count == 0 for count in failed['counts'].values()))
        self.assertEqual(failed['comparison_status'], 'complete')
        self.assertEqual(failed['assessment_summary']['status'], 'incomplete')
        self.assertIn('TimeoutError', failed['assessment_summary']['coverage_issues'][0]['message'])

    def historical_fixture(self, identifier):
        return json.loads((ROOT / 'tests/fixtures/security' / (identifier + '.json')).read_text())['cve']

    def test_public_2012_bounds_exclude_modern_java_without_candidates(self):
        cves = [self.historical_fixture(identifier) for identifier in ('CVE-2012-1723', 'CVE-2012-1531')]
        for version in ('17.0.12', '21.0.8'):
            target = component(cpe=JAVA.replace('17.0.12', version))
            for cve in cves:
                self.assertIs(applicability(cve, [target], target), False)
        body = {'totalResults': 2, 'vulnerabilities': [{'cve': cve} for cve in cves]}
        with patch('security.cli.Client', return_value=Client(body)):
            code, report = self.cli('runtime', '--inventory', str(self.inventory()))
        self.assertEqual(code, 0)
        self.assertEqual(report['findings'], [])
        self.assertEqual(report['coverage'][0]['records_examined'], 2)

    def test_public_2012_bounds_preserve_affected_java14_and_patch_boundary(self):
        for identifier, last in [('CVE-2012-1723', 37), ('CVE-2012-1531', 38)]:
            cve = self.historical_fixture(identifier)
            for form in ('1.4.2_{}:*', '1.4.2:update{}', '1.4.2:update_{}'):
                with self.subTest(identifier=identifier, form=form):
                    target = component(cpe=JAVA.replace('17.0.12:*', form.format(last)))
                    self.assertIs(applicability(cve, [target], target), True)
                    patched = component(cpe=JAVA.replace('17.0.12:*', form.format(last + 1)))
                    self.assertIs(applicability(cve, [patched], patched), False)

    def test_pre_java5_range_bounds_and_unknown_suffixes(self):
        old = component(cpe=JAVA.replace('17.0.12:*', '1.4.2:update_37'))
        for key, expected in [('versionEndIncluding', True), ('versionEndExcluding', False), ('versionStartIncluding', True), ('versionStartExcluding', False)]:
            self.assertIs(match_component(match(**{key: '1.4.2_37'}), old), expected)
        self.assertIsNone(match_component(match(versionEndIncluding='1.4.2_37-b03'), old))
        ancient = component(cpe=JAVA.replace('17.0.12:*', '1.3.1_05:*'))
        self.assertIs(match_component(match(versionEndIncluding='1.3.1_05'), ancient), True)
        criterion = PATTERN.replace(':*:*:*:*:*:*:*:*', ':1.3.1:update5:*:*:*:*:*:*')
        self.assertIs(match_component(match(criterion), ancient), True)

    def test_legacy_base_boundary_and_separate_update_criterion(self):
        criterion = PATTERN.replace(':*:*:*:*:*:*:*:*', ':*:update36:*:*:*:*:*:*')
        old = component(cpe=JAVA.replace('17.0.12:*', '1.5.0:update_36'))
        self.assertIs(match_component(match(criterion, versionEndIncluding='1.5.0'), old), True)
        self.assertIs(match_component(match(criterion, versionEndExcluding='1.5.0'), old), False)
        different_update = component(cpe=JAVA.replace('17.0.12:*', '1.5.0:update_37'))
        self.assertIs(match_component(match(criterion, versionEndIncluding='1.5.0'), different_update), False)

    def test_unbounded_wildcard_and_nonvulnerable_platform_have_distinct_meanings(self):
        target = component()
        self.assertIs(applicability(advisory({'cpeMatch': [match()]}), [target], target), True)
        fx = component('javafx', JAVA.replace('oracle:jdk:17.0.12', 'oracle:javafx:2.0'))
        cve = advisory({'operator': 'AND', 'cpeMatch': [match(PATTERN.replace('oracle:jdk', 'oracle:javafx')),
                                                    {'criteria': PATTERN, 'vulnerable': False}]})
        self.assertIs(applicability(cve, [target, fx], target), False)
        self.assertIs(applicability(cve, [target, fx], fx), True)

    def test_changed_runtime_matcher_baseline_preserves_old_evidence(self):
        config = self.monitor_init(self.inventory())
        with patch('security.runtime.RUNTIME_MATCHER_SCHEMA', 1):
            code, first = self.monitor_run(config, page())
        self.assertEqual(code, 0)
        self.assertEqual(first['counts']['new'], 1)
        code, current = self.monitor_run(config, page())
        self.assertEqual(code, 0)
        self.assertEqual(current['comparison_status'], 'partial')
        self.assertEqual(current['counts']['new'], 1)
        self.assertEqual(current['counts']['unverified'], 1)
        self.assertEqual(current['counts']['resolved'], 0)
        self.assertNotEqual(first['targets'][0]['scope'], current['targets'][0]['scope'])
        self.assertEqual(first['targets'][0]['runtime_matcher_schema'], 1)
        self.assertEqual(current['targets'][0]['runtime_matcher_schema'], 4)

    def test_unrelated_complex_cpe_does_not_poison_target_branch(self):
        target = component()
        unrelated = match('cpe:2.3:a:webkitgtk:webkitgtk\\+:*:*:*:*:*:*:*:*')
        old_java = match(versionEndIncluding='1.8.0_452')
        cve = advisory({'operator': 'OR', 'cpeMatch': [unrelated, old_java]})
        self.assertIs(applicability(cve, [target], target), False)
        cve = advisory({'operator': 'OR', 'cpeMatch': [unrelated, match()]})
        self.assertIs(applicability(cve, [target], target), True)

    def test_related_unsupported_and_missing_and_environment_stay_unknown(self):
        target = component()
        unsupported = match(PATTERN.replace('jdk', 'j?k'))
        self.assertIsNone(applicability(advisory({'cpeMatch': [unsupported]}), [target], target))
        prerequisite = {'vulnerable': False, 'criteria': 'cpe:2.3:o:fixture:escaped\\+os:*:*:*:*:*:*:*:*'}
        cve = advisory({'operator': 'AND', 'cpeMatch': [match(), prerequisite]})
        self.assertIsNone(applicability(cve, [target], target))

    def test_four_v11_candidates_are_excluded_for_java17_without_hiding_positive_branch(self):
        target = component()
        for identifier in ('CVE-2023-41993', 'CVE-2022-21449', 'CVE-2022-21426', 'CVE-2022-21434'):
            with self.subTest(identifier=identifier):
                cve = self.historical_fixture(identifier)
                self.assertIs(applicability(cve, [target], target), False)
                affected = component(cpe=JAVA.replace('17.0.12:*', '1.8.0:update401' if identifier == 'CVE-2023-41993' else '17.0.2:*'))
                self.assertIs(applicability(cve, [affected], affected), True)
                positive = copy.deepcopy(cve)
                positive['configurations'].append({'cpeMatch': [match(JAVA)]})
                self.assertIs(applicability(positive, [target], target), True)

    def test_stale_receipts_never_appear_complete(self):
        client = Client(page())
        original = client.get
        def get(url):
            value = original(url)
            client.receipts[-1]['stale'] = True
            return value
        client.get = get
        with patch('security.cli.Client', return_value=client):
            code, report = self.cli('runtime', '--inventory', str(self.inventory()))
        self.assertEqual(code, 1)
        self.assertEqual(report['coverage'][0]['status'], 'stale')


if __name__ == '__main__':
    unittest.main()
