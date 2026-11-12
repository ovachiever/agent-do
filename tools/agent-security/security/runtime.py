"""Explicit runtime evidence and conservative NVD applicability evaluation.

Declarations never become installed runtime evidence. NVD configuration logic is
preserved; absent environmental prerequisites remain unknown rather than true.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from .python_runtime import canonical_cpe as canonical_python_cpe, is_cpython, probe as probe_python
from .model import now, timestamp
from .scan import run
from .sources import NVD, SourceError, nvd_row
from .store import digest


class UnsupportedCPE(ValueError):
    pass


def cpe_parts(value):
    # Deliberately exclude escaped/pattern CPE components until a full CPE matcher
    # is available. Never compare them as ordinary product/version strings.
    if not isinstance(value, str):
        raise UnsupportedCPE('CPE must be a string')
    parts = value.split(':')
    if len(parts) != 13 or parts[:2] != ['cpe', '2.3'] or parts[2] not in {'a', 'o', 'h', '*'}:
        raise UnsupportedCPE('Expected a CPE 2.3 formatted string with 11 components')
    if any(not re.fullmatch(r'[A-Za-z0-9_.+*-]+', part) for part in parts[2:]):
        raise UnsupportedCPE('Escaped or complex CPE components are not supported')
    if any(('?' in part or ('*' in part and part != '*')) for part in parts[2:]):
        raise UnsupportedCPE('Embedded CPE wildcards are not supported')
    return parts


RUNTIME_MATCHER_SCHEMA = 4

JAVA_CPE_EXAMPLE = 'cpe:2.3:a:oracle:jdk:*:*:*:*:*:*:*:*'


def java_identity(value):
    try:
        parts = cpe_parts(value)
        if parts[5] != '*' or parts[6] != '*' or any(parts[i] in {'*', '-'} for i in (2, 3, 4)):
            raise UnsupportedCPE('--java-cpe must specify part/vendor/product with wildcard version/update')
        return parts
    except UnsupportedCPE as exc:
        raise ValueError(str(exc) + '; format example: --java-cpe "' + JAVA_CPE_EXAMPLE +
                         '" (Oracle Java only; choose the verified identity for the observed vendor). '
                         'Inspect first with runtime --local-java --inventory-only.') from exc


def canonical_java_cpe(parts):
    parts = parts[:]
    short = re.fullmatch(r'([5-8])u(\d+)', parts[5])
    legacy = re.fullmatch(r'1\.([2-8])\.(\d+)[._](\d+)', parts[5])
    compact = re.fullmatch(r'([5-8])\.0[._](\d+)', parts[5])
    if legacy:
        parts[5], parts[6] = '1.' + legacy[1] + '.' + legacy[2], 'update_' + legacy[3]
    elif short or compact:
        old = short or compact
        parts[5], parts[6] = '1.' + old[1] + '.0', 'update_' + old[2]
    update = re.fullmatch(r'update_?(\d+)', parts[6])
    if update:
        parts[6] = 'update_' + str(int(update[1]))
    return parts


def numeric_version(value, java=False):
    # Build metadata does not affect JDK security patch ordering. EA/vendor suffixes
    # and Linux distribution revisions need dedicated semantics and stay unknown.
    if java:
        value = re.sub(r'\+\d+(?:\.\d+)*$', '', value)
        legacy = re.fullmatch(r'1\.([2-8])\.(\d+)(?:[._](\d+))?', value)
        if legacy:
            return (int(legacy[1]), int(legacy[2]), int(legacy[3] or 0))
        short = re.fullmatch(r'([5-8])u(\d+)', value)
        compact = re.fullmatch(r'([5-8])\.0[._](\d+)', value)
        if short or compact:
            old = short or compact
            return (int(old[1]), 0, int(old[2]))
    if not re.fullmatch(r'\d+(?:\.\d+)*', value):
        return None
    return tuple(int(part) for part in value.split('.'))


def compare(left, right):
    size = max(len(left), len(right))
    return (left + (0,) * (size - len(left)) > right + (0,) * (size - len(right))) - (left + (0,) * (size - len(left)) < right + (0,) * (size - len(right)))


def match_component(match, component):
    try:
        pattern, actual = canonical_python_cpe(cpe_parts(match.get('criteria'))), canonical_python_cpe(cpe_parts(component['cpe']))
    except (UnsupportedCPE, KeyError):
        return None
    java = actual[4].lower() in {'java_se', 'jdk', 'jre', 'openjdk'}
    if java:
        pattern, actual = canonical_java_cpe(pattern), canonical_java_cpe(actual)
    uncertain = False
    for index in (2, 3, 4, 6, 7, 8, 9, 10, 11, 12):
        if pattern[index] == '*':
            continue
        if actual[index] == '*':
            uncertain = True
        elif pattern[index].lower() != actual[index].lower():
            return False
    current_value = actual[5]
    if java and re.fullmatch(r'1\.[2-8]\.\d+', actual[5]) and re.fullmatch(r'update_\d+', actual[6]):
        current_value += '_' + actual[6].removeprefix('update_')
    current = numeric_version(current_value, java)
    if pattern[5] != '*':
        expected = numeric_version(pattern[5], java)
        if actual[5] == pattern[5]:
            pass
        elif current is None or expected is None:
            uncertain = True
        elif compare(current, expected) != 0:
            return False
    bounds = {'versionStartIncluding': lambda c: c >= 0, 'versionStartExcluding': lambda c: c > 0,
              'versionEndIncluding': lambda c: c <= 0, 'versionEndExcluding': lambda c: c < 0}
    for key, accepts in bounds.items():
        if key not in match:
            continue
        bound = numeric_version(match[key], java)
        # A legacy base-version boundary constrains the CPE version field;
        # its separate update criterion is evaluated above. Embedded update
        # boundaries (1.4.2_37, 8u431) compare the full Java security version.
        selected_current = numeric_version(actual[5], java) if java and re.fullmatch(r'1\.[2-8]\.\d+', match[key]) else current
        if bound is None or selected_current is None:
            uncertain = True
        elif not accepts(compare(selected_current, bound)):
            return False
    return None if uncertain else True


def same_product(match, component):
    """Compare identity before parsing unsupported version/environment fields.

    A complex NetApp/WebKit predicate cannot make an unrelated JDK branch
    uncertain. An unparseable identity remains potentially relevant, however.
    """
    try:
        value = match.get('criteria')
        # Unlike strict inventory cpe_parts(), preserve escaped colons when
        # splitting upstream predicates so complex syntax does not prevent
        # ruling out an unrelated vendor/product. Relevant unsupported syntax
        # still remains uncertain in the full matcher.
        pattern = re.split(r'(?<!\\):', value)
        actual = canonical_python_cpe(cpe_parts(component['cpe']))
        pattern = canonical_python_cpe(pattern) if len(pattern) == 13 else pattern
        if len(pattern) != 13 or pattern[:2] != ['cpe', '2.3']:
            return None
        uncertain = False
        for index in (2, 3, 4):
            field = pattern[index]
            if field == '*':
                continue
            if not re.fullmatch(r'[A-Za-z0-9_.+*-]+', field) or '*' in field:
                uncertain = True
            elif field.lower() != actual[index].lower():
                return False
        return None if uncertain else True
    except (UnsupportedCPE, TypeError, KeyError):
        return None


def combine(values, operator):
    if not values or operator not in {'AND', 'OR'}:
        return None
    if operator == 'AND':
        return False if False in values else None if None in values else True
    return True if True in values else None if None in values else False


def evaluate(node, components, target):
    """Return applicability and a vulnerable-target witness for this branch.

    A true OR branch for another product must not turn a target's uncertain
    branch into a confirmed match. Negated branches cannot prove vulnerability.
    """
    if node.get('operator', 'OR') not in {'AND', 'OR'} or not isinstance(node.get('negate', False), bool):
        return None, None
    results = []
    for match in node.get('cpeMatch', []):
        relevant = [component for component in components if same_product(match, component) is not False]
        values = [match_component(match, component) for component in relevant]
        truth = combine(values, 'OR') if relevant else None
        target_value = match_component(match, target) if same_product(match, target) is not False else False
        witness = target_value if match.get('vulnerable') is True else False
        results.append((truth, witness))
    for child in node.get('nodes', []) + node.get('children', []):
        results.append(evaluate(child, components, target))
    operator = node.get('operator', 'OR')
    truth = combine([value for value, _ in results], operator)
    witnesses = []
    for index, (value, witness) in enumerate(results):
        if witness is False or value is False:
            continue
        prerequisites = [v for i, (v, _) in enumerate(results) if i != index] if operator == 'AND' else []
        witnesses.append(combine([value, witness] + prerequisites, 'AND'))
    witness = combine(witnesses, 'OR') if witnesses else False
    if node.get('negate'):
        return (None if truth is None else not truth), False
    return truth, witness


def applicability(cve, components, target):
    values = [evaluate(config, components, target)[1] for config in cve.get('configurations', [])]
    return combine(values, 'OR') if values else None


def read_bounded(path, maximum):
    path = Path(path).expanduser()
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('Runtime input exceeds --max-bytes: ' + str(path))
    return data


def declared_settings(path, maximum):
    """Static root-project hints only: no POM inheritance/build evaluation."""
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('--path must name a project directory')
    hints = []
    names = ('java.version', 'maven.compiler.release', 'maven.compiler.source', 'maven.compiler.target')
    pom = root / 'pom.xml'
    if pom.is_file():
        raw = read_bounded(pom, maximum)
        # Do not expand DTDs or XML entities from an untrusted checkout.
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise ValueError('POM contains unsupported XML DTD/entity declarations')
        tree = ET.fromstring(raw)
        local = lambda tag: tag.rsplit('}', 1)[-1]
        for element in tree.iter():
            if local(element.tag) == 'properties':
                for child in element:
                    if local(child.tag) in names:
                        hints.append({'file': 'pom.xml', 'setting': local(child.tag), 'value': (child.text or '').strip()})
            # Compiler-plugin release settings are declarations too, including
            # property expressions; never pretend static parsing resolves them.
            if local(element.tag) == 'plugin' and any(local(c.tag) == 'artifactId' and c.text == 'maven-compiler-plugin' for c in element):
                for child in element.iter():
                    if local(child.tag) in {'release', 'source', 'target'}:
                        hints.append({'file': 'pom.xml', 'setting': 'maven-compiler-plugin.' + local(child.tag), 'value': (child.text or '').strip()})
    for name in ('build.gradle', 'build.gradle.kts', '.java-version', '.tool-versions', 'Dockerfile'):
        file = root / name
        if not file.is_file():
            continue
        text = read_bounded(file, maximum).decode('utf-8')
        for index, line in enumerate(text.splitlines(), 1):
            setting, value = None, None
            if name == '.java-version' and line.strip() and not line.lstrip().startswith('#'):
                setting, value = 'java-version', line.split()[0]
            elif name == '.tool-versions' and re.match(r'^java\s+', line):
                setting, value = 'java-tool-version', line.split()[1]
            elif name.startswith('build.gradle'):
                # Capture only the version expression, never an entire build
                # line that might also contain credentials or private settings.
                literal = re.search(r'JavaLanguageVersion\.of\(\s*(\d+)\s*\)', line)
                compat = re.search(r'(sourceCompatibility|targetCompatibility)\s*=?\s*(JavaVersion\.VERSION_[0-9_]+|[\'"][0-9_.]+[\'"]|[0-9]+)', line)
                if literal:
                    setting, value = 'languageVersion', literal[1]
                elif compat:
                    setting, value = compat[1], compat[2]
                elif re.search(r'languageVersion|sourceCompatibility|targetCompatibility', line):
                    setting, value = 'java-setting', 'unresolved static expression'
            elif name == 'Dockerfile':
                image = re.match(r'^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)', line, re.I)
                if image:
                    setting, value = 'base-image-reference', image[1]
            if setting:
                hints.append({'file': name, 'line': index, 'setting': setting, 'value': value})
    for hint in hints:
        hint['evidence_kind'] = 'declaration_only'
        hint['establishes_installed_runtime'] = False
    return hints


def load_inventory(path, maximum):
    raw = read_bounded(path, maximum)
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get('schema_version') != 1 or not isinstance(value.get('components'), list) or not value['components']:
        raise ValueError('Runtime inventory requires schema_version: 1 and a nonempty components array')
    components, ids = [], set()
    for entry in value['components']:
        if not isinstance(entry, dict) or set(entry) - {'id', 'cpe', 'java', 'evidence', 'deployment'}:
            raise ValueError('Runtime component fields: id, cpe or java, evidence, optional deployment')
        identity = entry.get('id')
        if not isinstance(identity, str) or not identity.strip() or identity in ids:
            raise ValueError('Every runtime component needs a unique nonempty string id')
        ids.add(identity)
        if ('cpe' in entry) == ('java' in entry):
            raise ValueError('Runtime component needs exactly one cpe or java identity')
        if 'java' in entry:
            java = entry['java']
            if not isinstance(java, dict) or set(java) - {'vendor', 'product', 'version', 'runtime_version'} or java.get('vendor') != 'eclipse_adoptium' or java.get('product') != 'temurin' or not isinstance(java.get('version'), str) or not java['version'].strip() or any(not isinstance(v, str) for v in java.values()):
                raise ValueError('Java identity requires vendor eclipse_adoptium, product temurin, version, optional runtime_version')
        else:
            parts = cpe_parts(entry.get('cpe'))
            if any(parts[i] in {'*', '-'} for i in (2, 3, 4, 5)):
                raise ValueError('Inventory CPE must specify exact part, vendor, product and version')
        evidence = entry.get('evidence')
        if not isinstance(evidence, dict) or set(evidence) != {'kind', 'source', 'observed_at'} or evidence.get('kind') not in {'manual', 'deployment_inventory', 'image_inventory'}:
            raise ValueError('Imported evidence requires kind (manual/deployment_inventory/image_inventory), source and observed_at')
        if not isinstance(evidence['source'], str) or not evidence['source'].strip() or not isinstance(evidence['observed_at'], str) or not timestamp(evidence['observed_at']):
            raise ValueError('Imported evidence requires nonempty source and ISO observed_at')
        if timestamp(evidence['observed_at']) > timestamp(now()):
            raise ValueError('Inventory observed_at cannot be in the future')
        deployment = entry.get('deployment', {})
        if not isinstance(deployment, dict) or set(deployment) - {'environment', 'cluster', 'namespace', 'workload', 'image', 'image_digest', 'host'} or any(not isinstance(item, str) for item in deployment.values()):
            raise ValueError('Deployment labels must be strings: environment, cluster, namespace, workload, image, image_digest, host')
        components.append({**entry, 'evidence': {**evidence, 'verification': 'user_supplied_not_independently_verified'}, 'inventory_sha256': digest(raw)})
    return components


def probe_java(args):
    executable = shutil.which(args.java or 'java')
    if not executable:
        raise ValueError('Java executable not found; choose --java PATH with --local-java')
    result = run([executable, '-XshowSettings:properties', '-version'], SimpleNamespace(scan_timeout=args.probe_timeout, max_bytes=args.max_bytes))
    if result.returncode != 0:
        raise ValueError('Java version probe failed; raw output is not persisted')
    properties = {}
    for line in (result.stdout + b'\n' + result.stderr).decode('utf-8', errors='replace').splitlines():
        match = re.fullmatch(r'\s*(java\.(?:vendor|version|runtime.version|vm.name))\s*=\s*(.*?)\s*', line)
        if match:
            properties[match[1]] = match[2]
    version = properties.get('java.version')
    if not version:
        raise ValueError('Java probe did not return java.version; raw output is not persisted')
    # A caller-selected identity is explicit attribution, not vendor inference.
    identity = args.java_cpe
    identity_source = 'caller_selected' if identity else 'unmapped_vendor'
    parsed_version = numeric_version(version, java=True)
    # Older Oracle releases had separate JDK/JRE artifacts; VM vendor/name
    # alone cannot select which product was installed.
    if not identity and parsed_version and parsed_version[0] >= 11 and properties.get('java.vendor') == 'Oracle Corporation' and 'HotSpot' in properties.get('java.vm.name', '') and 'Graal' not in properties.get('java.vm.name', ''):
        identity = 'cpe:2.3:a:oracle:jdk:*:*:*:*:*:*:*:*'
        identity_source = 'oracle_vendor_mapping'
    component = {'id': 'local-java', 'properties': properties,
                 'evidence': {'kind': 'local_java_probe', 'source': str(Path(executable).resolve()), 'observed_at': now(), 'verification': 'observed_local_process'},
                 'identity_source': identity_source}
    if not identity:
        from .temurin import identity as temurin_identity
        mapped = temurin_identity(properties.get('java.vendor'), version, properties.get('java.runtime.version'))
        if mapped:
            component['java'] = mapped
            component['identity_source'] = 'adoptium_vendor_mapping'
    if identity:
        parts = java_identity(identity)
        if parts[3].lower() == 'oracle' and parts[4].lower() in {'java_se', 'jdk', 'jre', 'openjdk'} and properties.get('java.vendor') != 'Oracle Corporation':
            raise ValueError('Selected Oracle Java CPE conflicts with the observed non-Oracle vendor. '
                             'Use runtime --local-java --inventory-only to inspect vendor/version, then verify that distribution identity. '
                             'Oracle Java advisories cannot establish exposure for an Adoptium/Temurin or other non-Oracle JDK.')
        # Preserve old JDK update versions in the equivalent CPE fields.
        parts[5], parts[6] = version, '*'
        component['cpe'] = ':'.join(canonical_java_cpe(parts))
    return component


def assess_component(component, components, args, client, report):
    parts = cpe_parts(component['cpe'])
    params = {'virtualMatchString': ':'.join(parts[:5] + ['*'] * 8), 'startIndex': 0, 'resultsPerPage': min(args.limit, 2000)}
    if is_cpython(parts):
        # One bounded namespace query includes both current and historical CPE
        # product names; the matcher excludes unrelated products independently.
        params['virtualMatchString'] = 'cpe:2.3:a:python:*:*:*:*:*:*:*:*:*'
        params['resultsPerPage'] = min(args.limit, 100)
    if args.cve:
        params['cveId'] = args.cve.upper()
    count, unknown, start = 0, False, len(client.receipts)
    total = None
    try:
        while count < args.limit:
            body, _ = client.get(NVD + '?' + urllib.parse.urlencode(params))
            if not isinstance(body, dict) or not isinstance(body.get('vulnerabilities'), list) or not isinstance(body.get('totalResults'), int) or body['totalResults'] < 0:
                raise SourceError('Unexpected NVD runtime response schema')
            batch, total = body['vulnerabilities'], body['totalResults']
            if not batch and params['startIndex'] < total:
                raise SourceError('NVD runtime pagination stalled')
            for item in batch[:args.limit - count]:
                cve = item['cve']
                if cve.get('vulnStatus') == 'Rejected':
                    continue
                relation = applicability(cve, components, component)
                if relation is False:
                    continue
                # No configurations means no proof of applicability, but still
                # retain the source's product-query candidate visibly.
                if component.get('python') and component.get('build_provenance') != 'caller_verified_upstream':
                    relation = None  # Version alone cannot establish vendor backport status.
                row = nvd_row(cve)
                row['package'] = {'ecosystem': 'cpe', 'name': parts[3] + ':' + parts[4], 'version': parts[5], 'runtime_id': component['id']}
                row['runtime_match'] = {'component_id': component['id'], 'relation': 'inventory_match' if relation is True else 'candidate',
                                        'cpe': component['cpe'], 'exploitability': 'not_assessed'}
                row['evidence'].append({'runtime_component': copy.deepcopy(component), 'nvd_configurations': cve.get('configurations', [])})
                report['findings'].append(row)
                unknown |= relation is None
            count += min(len(batch), args.limit - count)
            params['startIndex'] += len(batch)
            if params['startIndex'] >= total:
                break
        truncated = total is not None and count < total
        report['coverage'].append({'source': 'NVD runtime:' + component['id'], 'status': 'truncated' if truncated else 'uncertain' if unknown else 'ok',
            'records_examined': count, 'total_records': total, 'limit': args.limit, 'receipts': client.receipts[start:],
            'reason': 'Product query truncated; increase --limit' if truncated else 'Candidate applicability requires unsupported version/CPE semantics or missing environment evidence' if unknown else ''})
    except (SourceError, ValueError, KeyError, TypeError) as exc:
        report['coverage'].append({'source': 'NVD runtime:' + component['id'], 'status': 'error', 'error': str(exc), 'receipts': client.receipts[start:]})


def assess_runtime(args, client, report):
    report['scope'] = 'explicit_runtime_inventory'
    report['runtime_matcher_schema'] = RUNTIME_MATCHER_SCHEMA
    report['limitations'] = [
        'Declared compiler targets, toolchains and Docker image tags do not establish an installed or deployed runtime version.',
        'Local Java/Python are the selected executables on this host, not proof of a project, container or deployment runtime.',
        'Python assessment covers upstream CPython interpreter/stdlib versions, not PyPI packages, bundled OpenSSL or vendor backports. Unknown build provenance retains candidates; --python-upstream is explicit caller verification, not automatic attestation.',
        'Imported runtime/deployment inventory is user supplied; its age and accuracy are not independently verified.',
        'NVD CPE matches assess only supplied components and configuration prerequisites; exploitability and deployment reachability are not assessed.',
        'Image/rootfs collection uses Syft and Trivy only when explicitly requested. Kubernetes reads pod image IDs, not running processes, writable container layers, host nodes or managed control-plane vulnerabilities. OS backports use Trivy vendor adapters. No remediation is performed.',
        'Publication/date/score options filter findings after full product/version assessment; --limit bounds NVD records per component. No fix is inferred from version-range boundaries.'
    ]
    report['runtime_components'] = components = []
    report['declared_settings'] = []
    if args.path:
        try:
            report['declared_settings'] = declared_settings(args.path, args.max_bytes)
            report['coverage'].append({'source': 'project declarations', 'status': 'ok', 'reason': 'Static root-file hints only; parent POMs, submodules and conditional build logic are not evaluated'})
        except (OSError, ValueError, ET.ParseError) as exc:
            report['coverage'].append({'source': 'project declarations', 'status': 'error', 'error': str(exc)})
    if args.inventory:
        components.extend(load_inventory(args.inventory, args.max_bytes))
    if args.local_java:
        try:
            component = probe_java(args)
            if any(c['id'] == component['id'] for c in components):
                raise ValueError('Inventory id local-java is reserved when --local-java is selected')
            components.append(component)
            report['coverage'].append({'source': 'local Java probe', 'status': 'ok'})
        except (OSError, ValueError) as exc:
            report['coverage'].append({'source': 'local Java probe', 'status': 'error', 'error': str(exc)})
    if args.local_python:
        try:
            component = probe_python(args)
            if any(c['id'] == component['id'] for c in components):
                raise ValueError('Inventory id local-python is reserved when --local-python is selected')
            components.append(component)
            report['coverage'].append({'source': 'local Python probe', 'status': 'ok'})
        except (OSError, ValueError) as exc:
            report['coverage'].append({'source': 'local Python probe', 'status': 'error', 'error': str(exc)})
    from .collect import collect
    collect(args, report)
    if len({component['id'] for component in components}) != len(components):
        raise ValueError('Collected and imported runtime component IDs collide')
    if args.inventory_only:
        report['notes'].append('Inventory only: no advisory service contacted and no CVEs assessed. Explicit image/cluster collectors may contact registries and Kubernetes APIs.')
        report['scope'] = 'runtime_inventory_only'
        if not components and not args.path and not report.get('artifact_inventory'):
            report['coverage'].append({'source': 'runtime inventory', 'status': 'missing', 'reason': 'No runtime evidence supplied'})
        return
    if not components and not report.get('artifact_inventory'):
        report['coverage'].append({'source': 'runtime inventory', 'status': 'missing', 'reason': 'Project declarations cannot identify an installed runtime. Supply --local-java, --local-python or --inventory PATH.'})
    for component in components:
        if component.get('java', {}).get('product') == 'temurin':
            from .temurin import assess
            assess(component, args, client, report)
        elif component.get('python') and not component.get('cpe'):
            report['coverage'].append({'source': 'runtime:' + component['id'], 'status': 'missing',
                'reason': 'Only final CPython releases are mapped. Other implementations and prerelease interpreters need dedicated matching; no CPython inference was made.'})
        elif not component.get('cpe'):
            report['coverage'].append({'source': 'runtime:' + component['id'], 'status': 'missing', 'reason': 'Vendor-specific CPE identity is not mapped. Rerun with an explicitly verified --java-cpe identity; no cross-vendor JDK inference was made.'})
        else:
            identity = cpe_parts(component['cpe'])
            if [part.lower() for part in identity[3:5]] == ['oracle', 'java_se']:
                report['coverage'].append({'source': 'runtime identity:' + component['id'], 'status': 'limited',
                    'reason': 'Legacy oracle:java_se identity does not cover modern oracle:jdk/jre advisories. Verify the actual artifact identity; use oracle:jdk for a verified Oracle JDK. Zero results here do not establish full JDK coverage.'})
            # Environment prerequisites may be satisfied only by explicitly
            # co-located evidence. Portfolio-wide components are not one host.
            deployment = component.get('deployment', {})
            colocated = bool(deployment.get('host') or deployment.get('image_digest') or
                             all(deployment.get(key) for key in ('cluster', 'namespace', 'workload')))
            environment = [other for other in components if other is component or
                           (colocated and other.get('deployment') == deployment)]
            if component.get('python') and component.get('build_provenance') != 'caller_verified_upstream':
                report['coverage'].append({'source': 'Python build provenance:' + component['id'], 'status': 'limited',
                    'reason': 'Vendor backport status is unknown; upstream version matches remain candidates. Use a vendor OS/image scan, or --python-upstream only after verifying the selected build follows upstream CPython releases.'})
            assess_component(component, environment, args, client, report)
