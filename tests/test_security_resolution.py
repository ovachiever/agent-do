#!/usr/bin/env python3
"""JVM resolution contracts: exact selected versions, opt-in, and incomplete evidence."""
from __future__ import annotations

import contextlib
import copy
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
from security.resolve import (SBOM_NAME, attach_evidence, coordinate, execute,
                              gradle_graphs, launcher, maven_trees, read_json_trees, sbom)
from test_security import OSV_SOURCE_NOTICE


def node(artifact='app', version='1.0', children=None, scope='', group='org.example'):
    return {'groupId': group, 'artifactId': artifact, 'version': version,
            'type': 'jar', 'scope': scope, 'classifier': '', 'optional': 'false', 'children': children or []}


def tree():
    return node(children=[node('spring-web', '6.1.14', [node('spring-core', '6.1.14', scope='compile', group='org.springframework')],
                              scope='compile', group='org.springframework'),
                          node('junit', '4.13.2', scope='test', group='junit')])


def graph(root):
    return {'schema_version': 1, 'gradle_version': '8.10.2', 'included_builds': [], 'projects': [{
        'project': ':app', 'manifest': str(root / 'build.gradle.kts'), 'has_resolvable_configurations': True,
        'missing_configurations': [], 'configurations': [{
            'configuration': 'runtimeClasspath', 'root': 'project :app', 'unresolved': [], 'file_dependencies': [],
            'components': [
                {'id': 'project :app', 'external': False},
                {'id': 'project :shared', 'external': False},
                {'id': 'org.springframework:spring-web:6.1.14', 'external': True, 'group': 'org.springframework',
                 'name': 'spring-web', 'version': '6.1.14', 'selection_reasons': ['conflict resolution']}],
            'edges': [
                {'from': 'project :app', 'to': 'project :shared', 'constraint': False},
                {'from': 'project :shared', 'to': 'org.springframework:spring-web:6.1.14',
                 'requested': 'org.springframework:spring-web:6.0.0', 'constraint': False},
                {'from': 'project :shared', 'to': 'project :app', 'constraint': False}]}]}]}


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.env = patch.dict(os.environ, {'AGENT_DO_HOME': str(self.root / 'state')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def args(self, *args):
        return parser().parse_args(list(args))

    def cli(self, *args):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(list(args) + ['--json'])
        return code, json.loads(stream.getvalue())

    def pom(self, folder=None, artifact='app'):
        folder = folder or self.project
        folder.mkdir(exist_ok=True)
        (folder / 'pom.xml').write_text('<project xmlns="http://maven.apache.org/POM/4.0.0">'
            '<modelVersion>4.0.0</modelVersion><parent><groupId>org.example</groupId>'
            '<artifactId>spring-boot-parent</artifactId><version>3.3.0</version></parent>'
            '<artifactId>' + artifact + '</artifactId><version>1.0</version></project>')

    def binary(self, name, contents):
        path = self.root / name
        path.write_text('#!/usr/bin/env python3\n' + contents)
        path.chmod(0o755)
        return str(path)

    def maven(self, trees=None, exit_code=0, logs=''):
        trees = [tree()] if trees is None else trees
        text = '\n'.join('[INFO] --- dependency:3.8.1:tree (default-cli) @ app ---\n' +
                         '\n'.join('[INFO] ' + line for line in json.dumps(t, indent=2).splitlines()) for t in trees)
        return self.binary('mvn', 'import sys\n'
            "if '--version' in sys.argv:\n print('Apache Maven 3.9.9'); raise SystemExit(0)\n" +
            'print(' + repr(logs + '\n' + text) + ')\nraise SystemExit(' + str(exit_code) + ')\n')

    def scanner(self, omit=False):
        return self.binary('osv-scanner', '''import json, sys
from pathlib import Path
if '--version' in sys.argv:
    print('osv-scanner version: 2.7.0'); raise SystemExit(0)
stage=Path(sys.argv[-1])
assert '--verbosity=warn' in sys.argv
assert not list(stage.rglob('pom.xml')), 'Resolved POM must not be statically rescanned'
document=json.loads((stage/'agent-do-resolved.cdx.json').read_text())
packages=[]
for component in document['components']:
    if OMIT and component['name']=='spring-core': continue
    package={'name':component['group']+':'+component['name'],'version':component['version'],'ecosystem':'Maven'}
    vulnerabilities=[]
    if component['name']=='spring-web':
        vulnerabilities=[{'id':'CVE-2026-10001','summary':'Fixture advisory','affected':[{'package':package,'ranges':[{'type':'ECOSYSTEM','events':[{'introduced':'0'},{'fixed':'6.1.15'}]}]}]}]
    packages.append({'package':package,'vulnerabilities':vulnerabilities})
print(json.dumps({'results':[{'source':{'type':'sbom','path':str(stage/'agent-do-resolved.cdx.json')},'packages':packages}]}))
raise SystemExit(1)
'''.replace('OMIT', repr(omit)))

    def test_maven_log_json_multiple_reactor_modules(self):
        stdout = ('[INFO] --- dependency:3.8.1:tree (default-cli) @ app ---\n' + json.dumps(tree()) +
                  '\n[INFO] --- dependency:3.8.1:tree (default-cli) @ child ---\n' + json.dumps(node('child'))).encode()
        self.assertEqual(len(read_json_trees(stdout)), 2)

    def test_missing_reactor_tree_is_not_complete(self):
        stdout = ('[INFO] --- dependency:3.8.1:tree (default-cli) @ app ---\n' + json.dumps(tree()) +
                  '\n[INFO] --- dependency:3.8.1:tree (default-cli) @ child ---\n').encode()
        with self.assertRaisesRegex(ValueError, 'complete JSON tree'):
            read_json_trees(stdout)

    def test_no_tree_or_invalid_versions_are_not_clean(self):
        with self.assertRaises(ValueError):
            read_json_trees(b'[INFO] BUILD SUCCESS')
        for version in ('', '${spring.version}', '[5,7)', '1.+', 'LATEST'):
            with self.assertRaises(ValueError):
                coordinate('org.springframework', 'spring-web', version)

    def test_truncated_outer_json_cannot_become_a_child_module_tree(self):
        text = json.dumps(tree(), indent=2)[:-2]
        with self.assertRaises(ValueError):
            read_json_trees(text.encode())

    def test_maven_inherited_coordinates_paths_and_scopes(self):
        self.pom()
        stage = self.project
        resolution = {'modules': [], 'gaps': []}
        occurrences, covered = maven_trees([tree()], [{'path': 'pom.xml'}], stage, resolution)
        self.assertEqual(covered, {'pom.xml'})
        core = next(x for x in occurrences if x['package']['name'].endswith(':spring-core'))
        self.assertEqual(core['package']['version'], '6.1.14')
        self.assertEqual(len(core['dependency_path']), 3)
        self.assertEqual(core['dependency_scope'], 'compile')
        self.assertEqual(next(x for x in occurrences if x['package']['name']=='junit:junit')['dependency_scope'], 'test')
        self.assertFalse(resolution['gaps'])

    def test_unmapped_maven_module_is_a_gap(self):
        resolution = {'modules': [], 'gaps': []}
        occurrences, covered = maven_trees([tree()], [], self.project, resolution)
        self.assertEqual(covered, set())
        self.assertTrue(occurrences)
        self.assertTrue(resolution['gaps'])

    def test_gradle_symlinked_root_matches_canonical_manifest(self):
        alias = self.root / 'project-alias'
        alias.symlink_to(self.project, target_is_directory=True)
        resolution = {'modules': [], 'gaps': []}
        occurrences, covered = gradle_graphs(graph(self.project), alias, resolution)
        self.assertEqual(len(occurrences), 1)
        self.assertEqual(covered, {'build.gradle.kts'})
        self.assertFalse(resolution['gaps'])

    def test_gradle_selected_versions_cycles_and_project_components(self):
        resolution = {'modules': [], 'gaps': []}
        occurrences, covered = gradle_graphs(graph(self.project), self.project, resolution)
        self.assertEqual(len(occurrences), 1)
        self.assertEqual(occurrences[0]['package']['version'], '6.1.14')
        self.assertEqual(occurrences[0]['requested'], 'org.springframework:spring-web:6.0.0')
        self.assertEqual(occurrences[0]['dependency_path'][1], 'project :shared')
        self.assertEqual(covered, {'build.gradle.kts'})
        self.assertFalse(resolution['gaps'])

    def test_gradle_unresolved_and_file_dependencies_remain_visible(self):
        body = graph(self.project)
        config = body['projects'][0]['configurations'][0]
        config['unresolved'] = [{'requested': 'private:missing:1.0'}]
        config['file_dependencies'] = [{'kind': 'file_collection'}]
        resolution = {'modules': [], 'gaps': []}
        occurrences, _ = gradle_graphs(body, self.project, resolution)
        self.assertTrue(occurrences)
        self.assertTrue(resolution['gaps'])
        self.assertEqual(resolution['modules'][0]['status'], 'incomplete')

    def test_gradle_constraints_alone_are_not_installed_packages(self):
        body = graph(self.project)
        for edge in body['projects'][0]['configurations'][0]['edges']:
            edge['constraint'] = True
        resolution = {'modules': [], 'gaps': []}
        occurrences, _ = gradle_graphs(body, self.project, resolution)
        self.assertEqual(occurrences, [])

    def test_gradle_projects_outside_root_are_not_silently_assessed(self):
        body = graph(self.project)
        body['projects'][0]['manifest'] = str(self.root / 'outside/build.gradle')
        resolution = {'modules': [], 'gaps': []}
        occurrences, covered = gradle_graphs(body, self.project, resolution)
        self.assertFalse(occurrences)
        self.assertFalse(covered)
        self.assertTrue(resolution['gaps'])

    def test_gradle_empty_or_missing_configurations_and_composite_builds(self):
        body = graph(self.project)
        body['included_builds'] = ['another-build']
        body['projects'][0]['missing_configurations'] = ['testRuntimeClasspath']
        body['projects'][0]['configurations'] = []
        resolution = {'modules': [], 'gaps': []}
        gradle_graphs(body, self.project, resolution)
        self.assertEqual(len(resolution['gaps']), 3)

    def test_gradle_configurations_keep_distinct_selected_versions(self):
        body = graph(self.project)
        test = copy.deepcopy(body['projects'][0]['configurations'][0])
        test['configuration'] = 'testRuntimeClasspath'
        test['components'][-1]['version'] = '5.3.39'
        body['projects'][0]['configurations'].append(test)
        resolution = {'modules': [], 'gaps': []}
        occurrences, _ = gradle_graphs(body, self.project, resolution)
        self.assertEqual({x['package']['version'] for x in occurrences}, {'6.1.14', '5.3.39'})

    def test_sbom_deduplicates_packages_but_evidence_retains_paths(self):
        resolution = {'modules': [], 'gaps': []}
        occurrences, _ = gradle_graphs(graph(self.project), self.project, resolution)
        document = sbom(occurrences + occurrences)
        self.assertEqual(len(document['components']), 1)
        self.assertEqual(document['components'][0]['purl'], 'pkg:maven/org.springframework/spring-web@6.1.14')
        rows = [{'package': occurrences[0]['package'], 'evidence': [{'path': SBOM_NAME}]}]
        attach_evidence(rows, {'resolution': {'occurrences': occurrences}})
        self.assertEqual(rows[0]['evidence'][0]['basis'], 'gradle_resolved_graph')

    def test_cli_resolution_to_scanner_and_findings_end_to_end(self):
        self.pom()
        code, report = self.cli('scan', '--path', str(self.project), '--resolve', 'maven',
                                '--maven', self.maven(), '--scanner', self.scanner())
        self.assertEqual(code, 0, report)
        self.assertEqual(report['resolution']['status'], 'ok')
        self.assertEqual(report['resolution']['configurations'], [])
        self.assertIn('maven-dependency-plugin:3.8.1:tree', report['resolution']['goal'])
        self.assertEqual(report['scope'], 'source_and_resolved_dependencies')
        self.assertEqual(report['summary']['total'], 1)
        evidence = report['findings'][0]['evidence'][0]
        self.assertEqual(evidence['path'], 'pom.xml')
        self.assertEqual(evidence['dependency_scope'], 'compile')
        self.assertEqual(evidence['dependency_path'][-1], 'org.springframework:spring-web@6.1.14')
        self.assertEqual(report['findings'][0]['affected'][0]['fixed_versions'], ['6.1.15'])

    def test_cli_gradle_resolution_and_scanning(self):
        (self.project/'build.gradle.kts').write_text('plugins { java }')
        body = graph(self.project)
        binary = self.binary('gradle', '''import json, sys
from pathlib import Path
if '--version' in sys.argv:
    print('Gradle 8.10.2'); raise SystemExit(0)
assert '--no-configuration-cache' in sys.argv
destination=next(x.split('=',1)[1] for x in sys.argv if x.startswith('-Dagentdo.security.output='))
Path(destination).write_text(json.dumps(BODY))
'''.replace('BODY', repr(body)))
        code, report = self.cli('scan', '--path', str(self.project), '--resolve', 'gradle', '--gradle', binary, '--scanner', self.scanner())
        self.assertEqual(code, 0, report)
        self.assertEqual(report['findings'][0]['evidence'][0]['configuration'], 'runtimeClasspath')

    def test_resolution_never_runs_without_opt_in(self):
        self.pom()
        marker = self.project/'PWNED'
        wrapper = self.project/'mvnw'
        wrapper.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\n')
        wrapper.chmod(0o755)
        code, _ = self.cli('scan', '--path', str(self.project), '--scanner', str(self.root/'absent'))
        self.assertEqual(code, 1)
        self.assertFalse(marker.exists())

    def test_missing_scanner_still_preserves_resolved_inventory(self):
        self.pom()
        code, report = self.cli('scan', '--path', str(self.project), '--resolve', 'maven', '--maven', self.maven(), '--scanner', str(self.root/'absent'))
        self.assertEqual(code, 1)
        self.assertEqual(len(report['resolution']['occurrences']), 3)
        self.assertTrue(any(x['status']=='unavailable' for x in report['coverage']))

    def test_scanner_must_account_for_every_resolved_component(self):
        self.pom()
        scanner = Path(self.scanner(omit=True))
        scanner.write_text(scanner.read_text().replace('import json, sys', 'import json, sys\nprint(' + repr(OSV_SOURCE_NOTICE) + ', file=sys.stderr)'))
        code, report = self.cli('scan', '--path', str(self.project), '--resolve', 'maven', '--maven', self.maven(), '--scanner', str(scanner))
        self.assertEqual(code, 1)
        self.assertEqual(report['summary']['total'], 1)
        self.assertTrue(any(x['source']=='resolved SBOM' for x in report['coverage']))
        self.assertTrue(any(x.get('non_blocking_diagnostics') for x in report['coverage']))

    def test_failed_build_cannot_report_clean_or_leak_logs(self):
        self.pom()
        code, report = self.cli('scan', '--path', str(self.project), '--resolve', 'maven', '--maven', self.maven(exit_code=1, logs='SECRET_CREDENTIAL_VALUE'))
        self.assertEqual(code, 1)
        self.assertEqual(report['resolution']['status'], 'incomplete')
        self.assertNotIn('SECRET_CREDENTIAL_VALUE', json.dumps(report))
        self.assertIn('--maven-settings PATH', json.dumps(report['coverage']))

    def test_version_probe_retains_only_version_number(self):
        self.pom()
        def command(argv,args,cwd):
            value = b'SECRET_BOOTSTRAP_LOG\nApache Maven 3.9.9\n' if '--version' in argv else json.dumps(tree()).encode()
            return subprocess.CompletedProcess(argv,0,value,b'')
        with patch('security.resolve.execute', command):
            code, report = self.cli('scan','--path',str(self.project),'--resolve','maven','--maven',self.maven(),'--scanner',str(self.root/'absent'))
        self.assertEqual(code, 1)
        self.assertEqual(report['resolution']['version'], '3.9.9')
        self.assertNotIn('SECRET_BOOTSTRAP_LOG', json.dumps(report))

    def test_invalid_build_options_rejected_before_execution(self):
        for options in [('--maven', '/bin/false'), ('--resolve','maven','--gradle-configuration','runtimeClasspath'),
                        ('--resolve','gradle','--maven-profile','prod'), ('--resolve','maven','--build-property','outputFile=foo'),
                        ('--resolve','maven','--build-property','missingEquals')]:
            code, _ = self.cli('scan','--path',str(self.project),*options)
            self.assertEqual(code, 2, options)
        code, _ = self.cli('scan','--repo','acme/repo','--resolve','maven')
        self.assertEqual(code, 2)

    def test_profile_settings_properties_forwarded_without_persisting_values(self):
        self.pom()
        settings = self.root/'settings.xml'
        settings.write_text('<settings/>')
        observed = []
        def command(argv, args, cwd):
            observed.append(argv)
            if '--version' in argv:
                return subprocess.CompletedProcess(argv,0,b'Apache Maven 3.9.9',b'')
            return subprocess.CompletedProcess(argv,0,json.dumps(tree()).encode(),b'')
        with patch('security.resolve.execute', command):
            code, report = self.cli('scan','--path',str(self.project),'--resolve','maven','--maven',self.maven(),
                                    '--maven-profile','prod','--maven-profile','cloud','--maven-settings',str(settings),
                                    '--build-property','example=PRIVATE_VALUE','--scanner',str(self.root/'absent'))
        self.assertEqual(code, 1)
        self.assertIn('-Pprod,cloud', observed[-1])
        self.assertIn('--settings', observed[-1])
        self.assertIn('-Dexample=PRIVATE_VALUE', observed[-1])
        self.assertNotIn('PRIVATE_VALUE', json.dumps(report))

    def test_empty_resolved_application_is_not_missing_inventory(self):
        self.pom()
        code, report = self.cli('scan','--path',str(self.project),'--resolve','maven','--maven',self.maven(trees=[node()]),'--scanner',str(self.root/'absent'))
        self.assertEqual(code, 0, report)
        self.assertEqual(report['summary']['total'], 0)
        self.assertEqual(report['resolution']['occurrences'], [])

    def test_settings_alias_reaches_maven_and_preserves_authentication_environment(self):
        self.pom()
        settings = self.root / 'private settings.xml'
        settings.write_text('<settings>PRIVATE_SETTINGS_CONTENT</settings>')
        executable = Path(self.maven())
        executable.write_text(executable.read_text().replace('import sys',
            "import os, sys\nif '--version' not in sys.argv:\n"
            "    assert sys.argv[sys.argv.index('--settings')+1] == " + repr(str(settings)) + "\n"
            "    assert os.environ['ARTIFACTORY_PASSWORD'] == 'PRIVATE_AUTH_VALUE'\n"))
        with patch.dict(os.environ, {'ARTIFACTORY_PASSWORD': 'PRIVATE_AUTH_VALUE'}):
            code, report = self.cli('scan', '--path', str(self.project), '--resolve', 'maven',
                '--settings', str(settings), '--maven', str(executable), '--scanner', self.scanner())
        self.assertEqual(code, 0, report)
        self.assertEqual(report['resolution']['settings'], str(settings))
        self.assertNotIn('PRIVATE_AUTH_VALUE', json.dumps(report))
        self.assertNotIn('PRIVATE_SETTINGS_CONTENT', json.dumps(report))

    def test_build_execution_timeout_and_output_bound(self):
        sleeper = self.binary('sleep-build', 'import time\ntime.sleep(5)\n')
        args = self.args('scan','--path',str(self.project),'--resolve','maven','--scan-timeout','0.1')
        with self.assertRaisesRegex(ValueError, 'timed out'):
            execute([sleeper],args,self.project)
        noisy = self.binary('noisy-build', 'print("x"*1024)\n')
        # Test the output bound independently of the deliberately tiny timeout.
        args = self.args('scan','--path',str(self.project),'--resolve','maven','--max-bytes','32')
        with self.assertRaisesRegex(ValueError, 'max-bytes'):
            execute([noisy],args,self.project)

    def test_default_launcher_prefers_project_wrapper(self):
        wrapper = self.project/'mvnw'
        wrapper.write_text('#!/bin/sh\nexit 0\n')
        wrapper.chmod(0o755)
        args = self.args('scan','--path',str(self.project),'--resolve','maven')
        self.assertEqual(launcher(args,self.project),str(wrapper))


if __name__ == '__main__':
    unittest.main()
