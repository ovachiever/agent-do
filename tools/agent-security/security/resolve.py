"""Opt-in JVM build resolution and conversion to a scanner-readable inventory.

Resolution executes trusted local project code. File-only scans never import a
build script or invoke either build tool. This module does not claim to inventory
what is packaged or deployed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

from .model import now

MAVEN_GOAL = 'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree'
SBOM_NAME = 'agent-do-resolved.cdx.json'
GRADLE_SCRIPT = Path(__file__).with_name('gradle-resolution.init.gradle')
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def execute(argv, args, cwd):
    """Build execution is opt-in; isolate process lifetime and bound captured logs."""
    env = {**os.environ, 'CI': 'true', 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'}
    # A build can start children. Kill its process group on timeout, not only its launcher.
    import signal
    import time
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=err, start_new_session=True)
        except OSError as exc:
            raise ValueError('Build tool could not start; check executable, Java, and permissions') from exc
        deadline = time.monotonic() + args.scan_timeout
        failure = None
        try:
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    failure = 'Build resolution timed out (--scan-timeout)'
                elif os.fstat(out.fileno()).st_size > args.max_bytes or os.fstat(err.fileno()).st_size > args.max_bytes:
                    failure = 'Build output exceeds --max-bytes'
                if failure:
                    raise ValueError(failure)
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        out.seek(0)
        err.seek(0)
        stdout, stderr = out.read(args.max_bytes + 1), err.read(args.max_bytes + 1)
        if len(stdout) > args.max_bytes or len(stderr) > args.max_bytes:
            raise ValueError('Build output exceeds --max-bytes')
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def launcher(args, root):
    configured = args.maven if args.resolve == 'maven' else args.gradle
    if configured:
        binary = shutil.which(configured)
        if not binary:
            raise ValueError('Selected build executable is unavailable')
        return str(Path(binary).resolve())
    wrapper = root / ('mvnw' if args.resolve == 'maven' else 'gradlew')
    if wrapper.is_file() and os.access(wrapper, os.X_OK):
        return str(wrapper)
    installed = shutil.which('mvn' if args.resolve == 'maven' else 'gradle')
    if installed:
        return str(Path(installed).resolve())
    raise ValueError('No executable project wrapper or installed ' + args.resolve + ' found; use --maven/--gradle PATH')


def coordinate(group, artifact, version):
    if not all(isinstance(x, str) and x.strip() for x in (group, artifact, version)):
        raise ValueError('Resolved dependency has missing coordinates/version')
    if '${' in version or any(x in version for x in ('[', ']', '(', ')', '+')) or version in {'LATEST', 'RELEASE', '*'}:
        raise ValueError('Build tool returned an unresolved dependency version')
    return {'name': group + ':' + artifact, 'version': version, 'ecosystem': 'Maven'}


def read_json_trees(stdout):
    """Read JSON dependency trees interleaved with Maven reactor log lines."""
    text = ANSI.sub('', stdout.decode('utf-8', errors='replace'))
    text = re.sub(r'^\[(?:INFO|WARNING|DEBUG)\]\s?', '', text, flags=re.MULTILINE)
    trees, cursor = [], 0
    decoder = json.JSONDecoder()
    for match in re.finditer(r'^\{', text, re.MULTILINE):
        start = match.start()
        if start < cursor:
            continue
        start += len(text[start:]) - len(text[start:].lstrip())
        try:
            tree, consumed = decoder.raw_decode(text[start:])
        except ValueError:
            continue
        if isinstance(tree, dict) and {'groupId', 'artifactId', 'version'} <= tree.keys():
            trees.append(tree)
            cursor = start + consumed
    goals = len(re.findall(r'^.*---\s+(?:[^\s]*dependency[^\s]*):[^\s]*:tree\b', text, re.MULTILINE))
    if not trees or (goals and goals != len(trees)):
        raise ValueError('Maven did not return a complete JSON tree for every reactor goal; no clean result inferred')
    return trees


def maven_manifest(tree, inventory, stage):
    matches = []
    for entry in inventory:
        if Path(entry['path']).name != 'pom.xml':
            continue
        try:
            xml = ET.fromstring((stage / entry['path']).read_bytes())
            ns = {'m': 'http://maven.apache.org/POM/4.0.0'} if xml.tag.startswith('{') else {}
            prefix = 'm:' if ns else ''
            artifact = xml.findtext(prefix + 'artifactId', namespaces=ns)
            group = xml.findtext(prefix + 'groupId', namespaces=ns) or xml.findtext(prefix + 'parent/' + prefix + 'groupId', namespaces=ns)
            if artifact == tree['artifactId'] and (not group or '${' in group or group == tree['groupId']):
                matches.append(entry['path'])
        except (ET.ParseError, OSError):
            continue
    return matches[0] if len(matches) == 1 else None


def maven_trees(trees, inventory, stage, resolution):
    occurrences, covered = [], set()
    for tree in trees:
        root_package = coordinate(tree['groupId'], tree['artifactId'], tree['version'])
        manifest = maven_manifest(tree, inventory, stage)
        module = root_package['name']
        entry = {'module': module, 'manifest': manifest, 'root': root_package, 'status': 'ok'}
        if manifest:
            covered.add(manifest)
        else:
            entry['status'] = 'unmapped'
            resolution['gaps'].append({'module': module, 'reason': 'Resolved Maven module could not be mapped uniquely to a source POM'})
        resolution['modules'].append(entry)
        queue = deque((child, [root_package['name'] + '@' + root_package['version']]) for child in tree.get('children', []))
        while queue:
            node, parents = queue.popleft()
            package = coordinate(node.get('groupId'), node.get('artifactId'), node.get('version'))
            path = parents + [package['name'] + '@' + package['version']]
            occurrence = {'package': package, 'module': module, 'path': manifest or 'pom.xml',
                          'dependency_scope': node.get('scope') or 'unknown', 'dependency_path': path,
                          'artifact_type': node.get('type'), 'classifier': node.get('classifier'),
                          'optional': str(node.get('optional', False)).lower() == 'true',
                          'basis': 'maven_resolved_tree'}
            occurrences.append(occurrence)
            queue.extend((child, path) for child in node.get('children', []))
    return occurrences, covered


def gradle_graphs(body, root, resolution):
    root = Path(root).resolve()
    if body.get('schema_version') != 1 or not isinstance(body.get('projects'), list):
        raise ValueError('Unsupported Gradle resolution output schema')
    occurrences, covered = [], set()
    if body.get('included_builds'):
        resolution['gaps'].append({'reason': 'Composite included builds require separate scans', 'builds': body['included_builds']})
    selected_count = 0
    for project in body['projects']:
        manifest = Path(project['manifest']).resolve()
        try:
            path = str(manifest.relative_to(root))
        except ValueError:
            resolution['gaps'].append({'module': project['project'], 'reason': 'Gradle project is outside selected source root'})
            continue
        graphs = project.get('configurations', [])
        if project.get('has_resolvable_configurations') and project.get('missing_configurations'):
            resolution['gaps'].append({'module': project['project'], 'reason': 'Requested Gradle configurations unavailable', 'configurations': project['missing_configurations']})
        for graph in graphs:
            selected_count += 1
            module = {'module': project['project'], 'manifest': path, 'configuration': graph['configuration'], 'status': 'ok'}
            if graph.get('unresolved') or graph.get('file_dependencies'):
                module['status'] = 'incomplete'
                resolution['gaps'].append({'module': project['project'], 'configuration': graph['configuration'],
                                            'reason': 'Unresolved or local file dependencies have no reliable external coordinates',
                                            'unresolved': graph.get('unresolved', []), 'file_dependencies': graph.get('file_dependencies', [])})
            resolution['modules'].append(module)
            if not graph.get('root'):
                continue
            covered.add(path)
            components = {x['id']: x for x in graph['components']}
            edges = {}
            for edge in graph['edges']:
                if not edge.get('constraint'):
                    edges.setdefault(edge['from'], []).append(edge)
            # One canonical shortest path for each node; keep every direct requesting edge.
            paths, queue = {graph['root']: [graph['root']]}, deque([graph['root']])
            while queue:
                parent = queue.popleft()
                for edge in edges.get(parent, []):
                    selected = components.get(edge['to'])
                    if selected is None:
                        raise ValueError('Gradle graph references a missing selected component')
                    dependency_path = paths[parent] + [edge['to']]
                    if selected.get('external'):
                        package = coordinate(selected.get('group'), selected.get('name'), selected.get('version'))
                        occurrences.append({'package': package, 'module': project['project'], 'path': path,
                            'configuration': graph['configuration'], 'dependency_scope': graph['configuration'],
                            'dependency_path': dependency_path, 'requested': edge.get('requested'),
                            'selection_reasons': selected.get('selection_reasons', []), 'basis': 'gradle_resolved_graph'})
                    if edge['to'] not in paths:
                        paths[edge['to']] = dependency_path
                        queue.append(edge['to'])
    if not selected_count:
        resolution['gaps'].append({'reason': 'No requested Gradle configurations were resolved'})
    return occurrences, covered


def sbom(occurrences):
    components = {}
    for item in occurrences:
        package = item['package']
        group, artifact = package['name'].split(':', 1)
        purl = 'pkg:maven/' + urllib.parse.quote(group, safe='') + '/' + urllib.parse.quote(artifact, safe='') + '@' + urllib.parse.quote(package['version'], safe='')
        components[purl] = {'type': 'library', 'bom-ref': purl, 'group': group, 'name': artifact,
                            'version': package['version'], 'purl': purl}
    return {'bomFormat': 'CycloneDX', 'specVersion': '1.5', 'serialNumber': 'urn:uuid:' + str(uuid.uuid4()),
            'version': 1, 'metadata': {'timestamp': now()}, 'components': [components[k] for k in sorted(components)]}


def resolve(args, report, stage, inventory):
    root = Path(args.path).expanduser().resolve(strict=True)
    resolution = {'tool': args.resolve, 'status': 'incomplete', 'started_at': now(), 'modules': [], 'gaps': [],
                  'execution': 'explicit opt-in; local project code and build cache writes allowed',
                  'requested_profiles': args.maven_profile,
                  'configurations': (args.gradle_configuration or ['runtimeClasspath']) if args.resolve == 'gradle' else [],
                  'property_names': [x.split('=', 1)[0] for x in args.build_property],
                  'settings': str(Path(args.maven_settings).expanduser().resolve()) if args.maven_settings else None,
                  'scope': 'selected Maven reactor or Gradle configurations; not installed/deployed inventory'}
    report['resolution'] = resolution
    report['scope'] = 'source_and_resolved_dependencies'
    binary = launcher(args, root)
    resolution['executable'] = binary
    probe = execute([binary, '--version'], args, root)
    if probe.returncode:
        raise ValueError('Build tool version probe failed')
    version_output = ANSI.sub('', probe.stdout.decode(errors='replace'))
    pattern = r'\bApache Maven ([0-9][A-Za-z0-9_.-]*)' if args.resolve == 'maven' else r'(?m)^Gradle ([0-9][A-Za-z0-9_.-]*)\s*$'
    version_match = re.search(pattern, version_output)
    if not version_match:
        raise ValueError('Build version probe did not identify Maven/Gradle')
    if args.resolve == 'gradle' and int(version_match[1].split('.')[0]) < 7:
        raise ValueError('Gradle resolution requires Gradle 7 or newer')
    resolution['version'] = version_match[1]
    if args.resolve == 'maven':
        resolution['goal'] = MAVEN_GOAL
    else:
        resolution['init_script_sha256'] = hashlib.sha256(GRADLE_SCRIPT.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='agent-security-resolution-') as temporary:
        if args.resolve == 'maven':
            if not (root / 'pom.xml').is_file():
                raise ValueError('Maven resolution requires pom.xml at --path')
            argv = [binary, '--batch-mode', '--no-transfer-progress', '-Dstyle.color=never', MAVEN_GOAL, '-DoutputType=json', '-Dverbose=false']
            if args.maven_profile:
                argv += ['-P' + ','.join(args.maven_profile)]
            if args.maven_settings:
                argv += ['--settings', resolution['settings']]
            argv += ['-D' + value for value in args.build_property]
        else:
            output = Path(temporary) / 'gradle.json'
            argv = [binary, '--no-daemon', '--console=plain', '--no-configuration-cache', '--init-script', str(GRADLE_SCRIPT),
                    '-Dagentdo.security.output=' + str(output),
                    '-Dagentdo.security.configurations=' + ','.join(resolution['configurations'])]
            argv += ['-P' + value for value in args.build_property]
            argv += [':agentDoSecurityInventory']
        result = execute(argv, args, root)
        resolution['output_sha256'] = hashlib.sha256(result.stdout).hexdigest()
        resolution['exit_code'] = result.returncode
        if result.returncode:
            guidance = (' Maven uses its normal ~/.m2/settings.xml; select another file with --maven-settings PATH (alias --settings) and ensure its server IDs match the repository/mirror IDs.' if args.resolve == 'maven' else '')
            raise ValueError('Build dependency resolution failed; check the selected profiles/configurations and repository access.' + guidance + ' Build logs are not persisted because they may contain credentials.')
        if args.resolve == 'maven':
            trees = read_json_trees(result.stdout)
            resolution['raw_inventory'] = trees
            occurrences, covered = maven_trees(trees, inventory, stage, resolution)
        else:
            if not output.is_file() or output.stat().st_size > args.max_bytes:
                raise ValueError('Gradle did not produce a bounded inventory file')
            body = json.loads(output.read_text())
            resolution['raw_inventory'] = body
            occurrences, covered = gradle_graphs(body, root, resolution)
    occurrences.sort(key=lambda item: json.dumps(item, sort_keys=True))
    resolution['occurrences'] = occurrences
    resolution['finished_at'] = now()
    resolution['status'] = 'incomplete' if resolution['gaps'] else 'ok'
    resolution['inventory_sha256'] = hashlib.sha256(json.dumps(occurrences, sort_keys=True).encode()).hexdigest()
    # Replace resolved JVM manifests/locks in the file scan; do not mix stale lock
    # versions or unexpanded parent/BOM declarations into the resolved result.
    covered_dirs = {str(Path(p).parent) for p in covered}
    retained = []
    for entry in inventory:
        path = Path(entry['path'])
        replace = entry['path'] in covered or (str(path.parent) in covered_dirs and path.name in {'gradle.lockfile', 'buildscript-gradle.lockfile'})
        if replace:
            (stage / entry['path']).unlink(missing_ok=True)
        else:
            retained.append(entry)
    for module in resolution['modules']:
        report['coverage'].append({'source': args.resolve + ':' + module['module'], 'status': 'ok' if module['status'] == 'ok' else 'unresolved',
                                   'scope': module.get('configuration', 'Maven effective dependency scopes'), 'manifest': module['manifest']})
    for gap in resolution['gaps']:
        report['coverage'].append({'source': args.resolve, 'status': 'unresolved', **gap})
    if occurrences:
        document = sbom(occurrences)
        data = json.dumps(document, sort_keys=True).encode()
        if len(data) > args.max_bytes:
            raise ValueError('Resolved SBOM exceeds --max-bytes')
        (stage / SBOM_NAME).write_bytes(data)
        report['resolved_sbom'] = document
        retained.append({'path': SBOM_NAME, 'ecosystem': 'maven', 'sha256': hashlib.sha256(data).hexdigest(), 'status': 'candidate'})
    report['notes'].append('Build resolution ran explicitly in the selected local project. Dependency graphs reflect this run; build code may write files/caches. Build plugins and buildscript classpaths are outside the resolved application dependency scope.')
    return retained


def attach_evidence(rows, report):
    occurrences = report.get('resolution', {}).get('occurrences', [])
    for row in rows:
        if not any(x['path'] == SBOM_NAME for x in row['evidence']):
            continue
        matched = [item for item in occurrences if item['package']['name'] == row['package']['name'] and item['package']['version'] == row['package']['version']]
        row['evidence'] = [{k: v for k, v in item.items() if k != 'package'} for item in matched] or row['evidence']
