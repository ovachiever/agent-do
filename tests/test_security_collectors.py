#!/usr/bin/env python3
"""Offline vendor, artifact and deployment acceptance tests (no live claims)."""
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
from security.cli import main, parser
from security.collect import execute, java_components
from security.model import now
from security.sources import AdoptiumAssetRedirect, SourceError
from security.temurin import document, relation, version

IMAGE = 'example.invalid/team/bff@sha256:' + 'a' * 64


def vdr():
    return {'bomFormat': 'CycloneDX', 'specVersion': '1.4', 'metadata': {'component': {'name': 'Eclipse Temurin'}},
            'vulnerabilities': [{'id': 'CVE-2026-10001', 'description': 'Synthetic OpenJDK advisory fixture',
                'published': '2026-10-01T00:00:00Z', 'ratings': [{'score': 7.5, 'vector': 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N', 'method': 'CVSSv31'}],
                'affects': [{'ref': 'pkg:github/openjdk/jdk', 'versions': [{'range': 'vers:generic/8u452|17.0.12|21.0.8'}]}]}]}


def sbom(java=False):
    return {'source': {'type': 'image', 'metadata': {'repoDigests': [IMAGE], 'config': 'PRIVATE_CONFIG'}},
            'descriptor': {'version': 'fixture-syft'}, 'artifacts': ([{
                'name': 'jre', 'locations': [{'path': '/opt/java/openjdk/release'}],
                'cpes': ['cpe:2.3:a:oracle:openjdk:21.0.8:*:*:*:*:*:*:*'],
                'metadata': {'release': {'implementor': 'Eclipse Adoptium', 'javaVersion': '21.0.8', 'javaRuntimeVersion': '21.0.8+9-LTS'}}}] if java else [{'name': 'libssl', 'version': '1.2'}])}


def trivy(vulnerable=True):
    return {'SchemaVersion': 2, 'Trivy': {'Version': 'fixture-trivy'},
            'Metadata': {'OS': {'Family': 'debian', 'Name': '12', 'EOSL': False}, 'RepoDigests': [IMAGE], 'ImageConfig': {'Env': ['SECRET=PRIVATE_CONFIG']}},
            'Results': [{'Target': 'fixture rootfs', 'Class': 'os-pkgs', 'Type': 'debian', 'Packages': [{'Name': 'libssl', 'Version': '1.2'}],
                         'Vulnerabilities': ([{'VulnerabilityID': 'CVE-2026-10002', 'PkgName': 'libssl', 'InstalledVersion': '1.2',
                                             'FixedVersion': '1.2+deb12u1', 'Severity': 'HIGH', 'DataSource': {'Name': 'Debian Security Tracker'}}] if vulnerable else [])}]}


def database():
    return {'Version': 'fixture-trivy', 'VulnerabilityDB': {'Version': 2, 'UpdatedAt': now(), 'DownloadedAt': now()}}


class Client:
    def __init__(self, *values):
        self.values = iter(values)
        self.receipts, self.urls = [], []

    def get(self, url):
        self.urls.append(url)
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        self.receipts.append({'url': url, 'fetched_at': now(), 'stale': False})
        return value


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.env = patch.dict(os.environ, {'AGENT_DO_HOME': str(self.root / 'state')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def cli(self, *argv):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main([*argv, '--json'])
        return code, json.loads(stream.getvalue())

    def args(self, *argv):
        return parser().parse_args(['runtime', *argv])

    def file(self, name, body):
        path = self.root / name
        path.write_text(json.dumps(body))
        return str(path)

    def test_temurin_probe_inventory_maps_vendor_without_oracle_or_network(self):
        output = b'java.vendor = Eclipse Adoptium\njava.version = 21.0.8\njava.runtime.version = 21.0.8+9-LTS'
        with patch('security.runtime.shutil.which', return_value='/usr/bin/java'), patch('security.runtime.run', return_value=subprocess.CompletedProcess([], 0, b'', output)), patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--local-java', '--inventory-only')
        self.assertEqual(code, 0)
        component = report['runtime_components'][0]
        self.assertEqual(component['java']['product'], 'temurin')
        self.assertEqual(component['java']['runtime_version'], '21.0.8+9-LTS')
        self.assertNotIn('cpe', component)
        get.assert_not_called()

    def temurin_inventory(self, patch_version='21.0.8'):
        return self.file('inventory.json', {'schema_version': 1, 'components': [{'id': 'temurin-prod',
            'java': {'vendor': 'eclipse_adoptium', 'product': 'temurin', 'version': patch_version},
            'evidence': {'kind': 'deployment_inventory', 'source': 'fixture', 'observed_at': '2026-10-01T00:00:00Z'}}]})

    def test_temurin_exact_vendor_listing_and_fixed_version_not_invented(self):
        with patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--inventory', self.temurin_inventory(), '--temurin-vdr', self.file('vdr.json', vdr()))
        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['total'], 1)
        row = report['findings'][0]
        self.assertEqual(row['runtime_match']['relation'], 'inventory_match')
        self.assertEqual(row['cvss'], 7.5)
        self.assertIsNotNone(row['scores'][0]['vector'])
        self.assertEqual(row['affected'][0]['fixed_versions'], [])
        self.assertEqual(row['evidence'][0]['vendor_document']['verification'], 'user_supplied_not_independently_verified')
        get.assert_not_called()

    def test_temurin_version_boundaries_and_unsupported_versions_stay_explicit(self):
        affects = vdr()['vulnerabilities'][0]['affects']
        self.assertIs(relation(affects, version('21.0.8+9-LTS')), True)
        self.assertIs(relation(affects, version('21.0.9+10-LTS')), False)
        self.assertIs(relation(affects, version('21.0.7')), None)
        self.assertIs(relation(affects, version('21-ea')), None)
        self.assertIs(relation(affects, version('1.8.0_452')), True)
        self.assertIs(relation(affects, version('17.0.12')), True)

    def test_temurin_fetch_failure_is_not_clean_and_oracle_is_not_queried(self):
        client = Client(SourceError('TimeoutError: advisory fetch failed'))
        with patch('security.cli.Client', return_value=client):
            code, report = self.cli('runtime', '--inventory', self.temurin_inventory())
        self.assertEqual(code, 1)
        self.assertEqual(report['coverage'][0]['status'], 'error')
        self.assertEqual(len(client.urls), 1)
        self.assertIn('adoptium/temurin-vdr-generator', client.urls[0])

    def test_vendor_report_without_requested_major_or_cve_is_not_clean(self):
        local = self.file('vdr.json', vdr())
        for version_text, extra in [('99.0.1', []), ('21.0.8', ['--cve', 'CVE-2026-99999'])]:
            code, report = self.cli('runtime', '--inventory', self.temurin_inventory(version_text), '--temurin-vdr', local, *extra)
            self.assertEqual(code, 1)
            self.assertEqual(report['coverage'][0]['status'], 'missing')

    def test_vendor_asset_integrity_required(self):
        url = 'https://github.com/adoptium/temurin-vdr-generator/releases/download/fixture/vdr.json'
        release = {'tag_name': 'fixture', 'assets': [{'name': 'vdr.json', 'browser_download_url': url, 'digest': 'sha256:' + 'a' * 64}]}
        for actual, succeeds in [('b' * 64, False), ('a' * 64, True)]:
            client = Client((release, {}), (vdr(), {'sha256': actual}))
            if succeeds:
                _, provenance = document(self.args(), client)
                self.assertEqual(provenance['verification'], 'official_release_digest_checked')
            else:
                with self.assertRaisesRegex(SourceError, 'digest'):
                    document(self.args(), client)

    def test_asset_redirect_rejects_other_authorities_and_drops_auth(self):
        import urllib.request
        request = urllib.request.Request('https://github.com/adoptium/temurin-vdr-generator/releases/download/fixture/vdr.json', headers={'Authorization': 'Bearer private', 'apiKey': 'private'})
        handler = AdoptiumAssetRedirect()
        redirected = handler.redirect_request(request, None, 302, '', {}, 'https://release-assets.githubusercontent.com/fixture?signature=private')
        self.assertNotIn('Authorization', redirected.headers)
        self.assertNotIn('Apikey', redirected.headers)
        for url in ('https://evil.invalid/a', 'http://release-assets.githubusercontent.com/a', 'https://private@release-assets.githubusercontent.com/a'):
            with self.assertRaises(SourceError):
                handler.redirect_request(request, None, 302, '', {}, url)

    def test_image_is_pinned_and_no_private_config_is_saved(self):
        with patch('security.collect.execute', side_effect=[(sbom(), False), (trivy(), False), (database(), False)]) as helper:
            code, report = self.cli('runtime', '--image', 'example.invalid/team/bff:latest')
        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['total'], 1)
        self.assertEqual(report['artifact_inventory'][0]['image'], IMAGE)
        self.assertEqual(helper.call_args_list[1].args[0][-1], IMAGE)
        self.assertIn('--image-src', helper.call_args_list[1].args[0])
        self.assertEqual(report['findings'][0]['affected'][0]['fixed_versions'], ['1.2+deb12u1'])
        self.assertNotIn('PRIVATE_CONFIG', json.dumps(report))

    def test_package_and_fix_filters_keep_fixable_trivy_findings_on_scan_and_report(self):
        with patch('security.collect.execute', side_effect=[(sbom(), False), (trivy(), False), (database(), False)]):
            code, report = self.cli('runtime', '--image', IMAGE, '--package', 'debian:libssl', '--fix-available')
        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['shown'], 1)
        code, saved = self.cli('report', '--file', report['saved_report'], '--package', 'debian:libssl', '--fix-available')
        self.assertEqual(code, 0)
        self.assertEqual(saved['summary']['shown'], 1)

    def test_image_inventory_only_never_runs_vulnerability_scan(self):
        with patch('security.collect.execute', return_value=(sbom(java=True), False)) as helper, patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--image', IMAGE, '--inventory-only')
        self.assertEqual(code, 0)
        self.assertEqual(helper.call_count, 1)
        self.assertEqual(report['runtime_components'][0]['java']['vendor'], 'eclipse_adoptium')
        self.assertNotIn('cpe', report['runtime_components'][0])
        get.assert_not_called()

    def test_changed_or_missing_digest_cannot_assess_wrong_image(self):
        for changed in ([], [IMAGE.replace('a' * 64, 'b' * 64)]):
            body = sbom()
            body['source']['metadata']['repoDigests'] = changed
            with patch('security.collect.execute', return_value=(body, False)) as helper:
                code, report = self.cli('runtime', '--image', IMAGE)
            self.assertEqual(code, 1)
            self.assertEqual(helper.call_count, 1)
            self.assertEqual(report['summary']['total'], 0)

    def test_unknown_stale_or_eol_database_cannot_clear(self):
        for db, eol in [({}, False), ({'VulnerabilityDB': {'UpdatedAt': '2020-01-01T00:00:00Z'}}, False), (database(), True)]:
            body = trivy(False)
            body['Metadata']['OS']['EOSL'] = eol
            with patch('security.collect.execute', side_effect=[(sbom(), False), (body, False), (db, False)]):
                code, report = self.cli('runtime', '--image', IMAGE)
            self.assertEqual(code, 1)
            self.assertNotEqual(report['coverage'][-1]['status'], 'ok')

    def test_rootfs_is_explicit_and_does_not_execute_its_java(self):
        with patch('security.collect.execute', return_value=(sbom(java=True), False)) as helper:
            code, report = self.cli('runtime', '--rootfs', str(self.root), '--inventory-only')
        self.assertEqual(code, 0)
        self.assertEqual(helper.call_args.args[0][2], 'dir:' + str(self.root))
        self.assertNotIn('java', helper.call_args.args[0])

    def test_helper_errors_are_bounded_and_stderr_private(self):
        with patch('security.collect.run', return_value=subprocess.CompletedProcess([], 1, b'', b'SECRET=private-token')):
            code, report = self.cli('runtime', '--image', IMAGE)
        self.assertEqual(code, 1)
        self.assertNotIn('private-token', json.dumps(report))
        self.assertIn('collection failed', report['coverage'][0]['error'])

    def test_ambient_filters_and_output_settings_cannot_hide_findings_or_write_files(self):
        with patch.dict(os.environ, {'TRIVY_IGNORE_UNFIXED': 'true', 'TRIVY_SEVERITY': 'CRITICAL', 'SYFT_OUTPUT': '/tmp/unwanted.json', 'TRIVY_PASSWORD': 'private'}), patch('security.collect.run', return_value=subprocess.CompletedProcess([], 0, b'{}', b'')) as helper:
            execute(['fixture'], self.args())
        environment = helper.call_args.kwargs['environment']
        self.assertNotIn('TRIVY_IGNORE_UNFIXED', environment)
        self.assertNotIn('TRIVY_SEVERITY', environment)
        self.assertNotIn('SYFT_OUTPUT', environment)
        self.assertEqual(environment['TRIVY_PASSWORD'], 'private')

    def test_private_yaml_config_exists_during_run_and_is_cleaned_on_every_exit(self):
        for outcome in ('success', 'failure', 'timeout'):
            observed = []
            command = ['fixture', 'scan', 'dir:/fixture']
            def helper(argv, args, **kwargs):
                config = Path(argv[argv.index('--config') + 1])
                observed.append(config)
                self.assertEqual(config.suffix, '.yaml')
                self.assertEqual(config.read_text(), '{}\n')
                self.assertEqual(config.stat().st_mode & 0o777, 0o600)
                self.assertEqual(config.parent, Path(kwargs['cwd']))
                self.assertEqual(argv[3:], command[1:])
                if outcome == 'timeout':
                    raise ValueError('fixture: unavailable or timed out')
                return subprocess.CompletedProcess([], 1 if outcome == 'failure' else 0, b'{}', b'')
            with self.subTest(outcome=outcome), patch('security.collect.run', side_effect=helper):
                if outcome == 'success':
                    self.assertEqual(execute(command, self.args(), empty_config=True), ({}, False))
                else:
                    with self.assertRaises(ValueError):
                        execute(command, self.args(), empty_config=True)
            self.assertEqual(command, ['fixture', 'scan', 'dir:/fixture'])
            self.assertEqual(len(observed), 1)
            self.assertFalse(observed[0].exists())
            self.assertFalse(observed[0].parent.exists())

    def test_extension_sensitive_helper_runs_through_runtime_without_wrapper(self):
        helper = self.root / 'syft-extension-check'
        helper.write_text('#!' + sys.executable + '\n'
                          'import json,sys\nfrom pathlib import Path\n'
                          'config=Path(sys.argv[sys.argv.index("--config")+1])\n'
                          'if config.suffix != ".yaml" or json.loads(config.read_text()) != {}: sys.exit(64)\n'
                          'print(' + repr(json.dumps(sbom())) + ')\n')
        helper.chmod(0o755)
        with patch('security.sources.Client.get') as get:
            code, report = self.cli('runtime', '--rootfs', str(self.root), '--syft', str(helper), '--inventory-only')
        self.assertEqual(code, 0)
        self.assertEqual(report['coverage'][0]['status'], 'ok')
        self.assertEqual(report['artifact_inventory'][0]['syft_version'], 'fixture-syft')
        get.assert_not_called()

    def test_relative_collector_paths_and_path_entries_resolve_before_chdir(self):
        helper = self.root / 'bin' / 'syft'
        helper.parent.mkdir()
        implementation = self.root / 'real-helper'
        implementation.write_text('#!' + sys.executable + '\nimport sys\nfrom pathlib import Path\n'
                                  'if Path(sys.argv[0]).name != "syft": sys.exit(64)\n'
                                  'print(' + repr(json.dumps(sbom())) + ')\n')
        implementation.chmod(0o755)
        helper.symlink_to(implementation)
        original = Path.cwd()
        try:
            os.chdir(self.root)
            for selected in ('./bin/syft', 'bin/syft', 'syft'):
                with self.subTest(selected=selected), patch.dict(os.environ, {'PATH': 'bin' + os.pathsep + os.environ.get('PATH', '')}):
                    code, report = self.cli('runtime', '--rootfs', str(self.root), '--syft', selected, '--inventory-only')
                self.assertEqual(code, 0)
                self.assertEqual(report['artifact_inventory'][0]['syft_version'], 'fixture-syft')
        finally:
            os.chdir(original)

    def test_collector_output_overflow_is_an_incomplete_assessment(self):
        helper = self.root / 'oversized-syft'
        helper.write_text('#!' + sys.executable + '\nimport os\nos.write(1,b"x"*2048)\n')
        helper.chmod(0o755)
        code, report = self.cli('runtime', '--rootfs', str(self.root), '--syft', str(helper), '--max-bytes', '1024', '--inventory-only')
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'incomplete')
        self.assertTrue(any('output exceeds --max-bytes' in item.get('error', '') for item in report['coverage']))

    def test_invalid_runtime_inputs_fail_before_helpers(self):
        for argv in (['--image', 'https://user:password@example.com/image'], ['--kube-context', 'fixture'], ['--namespace', 'default'], ['--selector', 'app=bff'], ['--rootfs', '/does-not-exist']):
            with patch('security.collect.execute') as helper:
                code, report = self.cli('runtime', *argv)
            self.assertEqual(code, 2)
            helper.assert_not_called()

    def pod(self, image=IMAGE):
        return {'name': 'bff-abc', 'uid': 'fixture-uid', 'expectedContainers': 1, 'expectedInit': 0, 'expectedEphemeral': 0,
                'containers': [{'name': 'app', 'image': 'bff:latest', 'imageID': 'docker-pullable://' + image}], 'init': [], 'ephemeral': []}

    def test_kubernetes_context_namespace_and_digest_are_explicit(self):
        def collected(args, report, **kwargs):
            report.setdefault('artifact_inventory', []).append({'image': kwargs['image']})
        with patch('security.collect.execute', return_value=({'pods': [self.pod()]}, False)) as helper, patch('security.collect.artifact', side_effect=collected) as collect:
            code, report = self.cli('runtime', '--kube-context', 'team-aks', '--namespace', 'services', '--selector', 'app=bff', '--inventory-only')
        self.assertEqual(code, 0)
        command = helper.call_args.args[0]
        self.assertEqual(command[:5], ['kubectl', '--context', 'team-aks', '--namespace', 'services'])
        self.assertNotIn('exec', command)
        self.assertNotIn('.spec.containers.env', ' '.join(command))
        self.assertEqual(collect.call_args.kwargs['image'], IMAGE)
        self.assertEqual(collect.call_args.kwargs['deployment']['namespace'], 'services')

    def test_pending_pod_empty_discovery_and_nonpullable_ids_are_incomplete(self):
        pending = self.pod()
        pending['containers'] = []
        for pods in ([], [pending], [self.pod('containerd://sha256:' + 'a' * 64)]):
            with patch('security.collect.execute', return_value=({'pods': pods}, False)), patch('security.collect.artifact') as collect:
                code, report = self.cli('runtime', '--kube-context', 'team', '--namespace', 'services', '--inventory-only')
            self.assertEqual(code, 1)
            collect.assert_not_called()

    def test_same_jvm_in_two_deployments_keeps_distinct_evidence(self):
        left = java_components(sbom(True), IMAGE, {'namespace': 'production', 'workload': 'bff/app'})[0]
        right = java_components(sbom(True), IMAGE, {'namespace': 'staging', 'workload': 'bff/app'})[0]
        self.assertNotEqual(left['id'], right['id'])

    def test_collector_monitor_optin_lifecycle_and_failure_retention(self):
        config = str(self.root / 'monitor.json')
        code, initialized = self.cli('monitor', 'init', '--config', config, '--image', IMAGE)
        self.assertEqual(code, 0)
        with patch('security.collect.execute') as helper:
            code, denied = self.cli('monitor', 'run', '--config', config)
        self.assertEqual(code, 1)
        self.assertIn('--allow-collectors', denied['assessment_summary']['coverage_issues'][0]['message'])
        helper.assert_not_called()
        for expected in ('new', 'ongoing'):
            with patch('security.collect.execute', side_effect=[(sbom(), False), (trivy(), False), (database(), False)]):
                code, report = self.cli('monitor', 'run', '--config', config, '--allow-collectors')
            self.assertEqual(code, 0)
            self.assertEqual(report['counts'][expected], 1)
        with patch('security.collect.execute', side_effect=ValueError('registry timeout')):
            code, failed = self.cli('monitor', 'run', '--config', config, '--allow-collectors')
        self.assertEqual(code, 1)
        self.assertEqual(failed['counts']['unverified'], 1)
        self.assertEqual(failed['counts']['resolved'], 0)
        self.assertIn('registry timeout', failed['assessment_summary']['coverage_issues'][0]['message'])

    def test_schedule_requires_and_exports_collector_authorization(self):
        config = str(self.root / 'monitor.json')
        self.cli('monitor', 'init', '--config', config, '--image', IMAGE)
        code, _ = self.cli('monitor', 'schedule', '--config', config)
        self.assertEqual(code, 2)
        code, report = self.cli('monitor', 'schedule', '--config', config, '--allow-collectors')
        self.assertEqual(code, 0)
        self.assertFalse(report['installed'])
        self.assertIn('--allow-collectors', report['cron'])

    def test_complete_artifact_scan_can_resolve_but_helper_revision_cannot(self):
        config = str(self.root / 'resolved-monitor.json')
        self.cli('monitor', 'init', '--config', config, '--image', IMAGE)
        for body, expected in ((trivy(True), 'new'), (trivy(False), 'resolved')):
            with patch('security.collect.execute', side_effect=[(sbom(), False), (body, False), (database(), False)]):
                code, report = self.cli('monitor', 'run', '--config', config, '--allow-collectors')
            self.assertEqual(code, 0)
            self.assertEqual(report['counts'][expected], 1)
        with patch('security.collect.execute', side_effect=[(sbom(), False), (trivy(True), False), (database(), False)]):
            self.cli('monitor', 'run', '--config', config, '--allow-collectors')
        changed = sbom()
        changed['descriptor']['version'] = 'new-helper-version'
        with patch('security.collect.execute', side_effect=[(changed, False), (trivy(False), False), (database(), False)]):
            code, report = self.cli('monitor', 'run', '--config', config, '--allow-collectors')
        self.assertEqual(code, 0)
        self.assertEqual(report['counts']['unverified'], 1)
        self.assertEqual(report['counts']['resolved'], 0)

    def test_missing_monitored_rootfs_is_saved_as_target_failure(self):
        directory = self.root / 'mounted-root'
        directory.mkdir()
        config = str(self.root / 'rootfs-monitor.json')
        self.cli('monitor', 'init', '--config', config, '--rootfs', str(directory))
        with patch('security.collect.execute', side_effect=[(sbom(), False), (trivy(), False), (database(), False)]):
            code, baseline = self.cli('monitor', 'run', '--config', config, '--allow-collectors')
        self.assertEqual(code, 0)
        directory.rmdir()
        with patch('security.collect.execute') as helper:
            code, failed = self.cli('monitor', 'run', '--config', config, '--allow-collectors')
        self.assertEqual(code, 1)
        self.assertEqual(failed['counts']['unverified'], 1)
        self.assertIn('rootfs directory', failed['assessment_summary']['coverage_issues'][0]['message'])
        helper.assert_not_called()


if __name__ == '__main__':
    unittest.main()
