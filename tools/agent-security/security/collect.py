"""Explicit read-only artifact/deployment collection through maintained helpers.

Only whitelisted evidence is retained. Images are read, never started. OS package
backports are assessed by Trivy's vendor adapters, not this module's comparator.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from .model import cvss_scores, finding, now, timestamp
from .scan import run
from .store import digest

DIGEST = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}$')


def image_ref(value, immutable=False):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/@-]*', value) or '://' in value or '..' in value:
        raise ValueError('Image must be a registry image reference without credentials or a transport prefix')
    if immutable and not DIGEST.fullmatch(value):
        raise ValueError('Deployed image needs an immutable repository@sha256 digest; a tag or image config ID is insufficient')
    return value


def execute(argv, args, *, empty_config=False):
    # An empty working directory avoids checkout-local helper configuration and
    # ignore files. Commands are argument arrays, never shell fragments.
    # Prevent ambient scanner filters, output-file settings, remote servers and
    # ignore policies from silently narrowing an assessment. Retain only registry
    # authentication/cache settings from these helpers' environment namespaces.
    # Resolve before entering the temporary cwd, including relative PATH entries.
    executable = shutil.which(argv[0])
    argv = [str(Path(executable).absolute()) if executable else argv[0], *argv[1:]]
    allowed = {'TRIVY_USERNAME', 'TRIVY_PASSWORD', 'TRIVY_REGISTRY_TOKEN', 'TRIVY_CACHE_DIR'}
    environment = {key: value for key, value in os.environ.items() if not key.startswith(('TRIVY_', 'SYFT_')) or
                   key in allowed or re.fullmatch(r'SYFT_REGISTRY_AUTH_(?:\d+_)?(?:USERNAME|PASSWORD|TOKEN|AUTHORITY)', key)}
    environment['SYFT_CHECK_FOR_APP_UPDATE'] = 'false'
    if environment.get('TRIVY_CACHE_DIR'):
        environment['TRIVY_CACHE_DIR'] = str(Path(environment['TRIVY_CACHE_DIR']).expanduser().resolve())
    with tempfile.TemporaryDirectory(prefix='agent-security-collect-') as directory:
        if empty_config:
            # Syft/Viper detects the format from the extension; /dev/null is
            # not a valid config path on current Syft releases. Keep this file
            # private and alive for the subprocess, then remove it on all exits.
            config = Path(directory) / 'empty.yaml'
            with config.open('x', encoding='utf-8') as stream:
                config.chmod(0o600)
                stream.write('{}\n')
            argv = [argv[0], '--config', str(config), *argv[1:]]
        result = run(argv, SimpleNamespace(scan_timeout=args.collect_timeout, max_bytes=args.max_bytes), cwd=directory, environment=environment)
    if result.returncode:
        raise ValueError(Path(argv[0]).name + ' collection failed; check tool version, registry/RBAC access and credentials. Raw output is not persisted.')
    try:
        body = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise ValueError(Path(argv[0]).name + ' returned invalid JSON; raw output is not persisted') from exc
    return body, bool(result.stderr.strip())


def java_components(sbom, source, deployment):
    from .temurin import identity
    components = []
    for package in sbom.get('artifacts', []):
        release = package.get('metadata', {}).get('release')
        if not isinstance(release, dict):
            continue
        # Ignore Syft's generated Oracle CPEs. Implementor is the distribution
        # evidence; runtimeVersion preserves the installed build separately.
        vendor, version = release.get('implementor'), release.get('javaVersion')
        if not isinstance(vendor, str) or not isinstance(version, str) or not version:
            continue
        locations = [item.get('path') for item in package.get('locations', []) if isinstance(item.get('path'), str)]
        scope = {key: value for key, value in deployment.items() if key not in {'image', 'image_digest'}}
        identity_key = digest(json.dumps([source if not scope else scope, locations, package.get('name')], sort_keys=True).encode())[:16]
        component = {'id': 'jvm-' + identity_key, 'deployment': copy.deepcopy(deployment),
                     'properties': {'java.vendor': vendor, 'java.version': version,
                                    'java.runtime.version': release.get('javaRuntimeVersion', version)},
                     'evidence': {'kind': 'artifact_release_file', 'source': source, 'observed_at': now(),
                                  'verification': 'observed_artifact_metadata'}, 'locations': locations}
        java = identity(vendor, version, release.get('javaRuntimeVersion'))
        if java:
            component['java'] = java
            component['identity_source'] = 'adoptium_release_file'
        elif vendor == 'Oracle Corporation' and release.get('imageType') in {'JDK', 'JRE'}:
            from .runtime import canonical_java_cpe
            parts = ['cpe', '2.3', 'a', 'oracle', release['imageType'].lower(), version] + ['*'] * 7
            component['cpe'] = ':'.join(canonical_java_cpe(parts))
            component['identity_source'] = 'oracle_release_file'
        else:
            component['identity_source'] = 'unmapped_vendor'
        components.append(component)
    return components


def trivy_findings(body, component_id, evidence):
    rows = []
    for result in body.get('Results', []):
        if result.get('Class') not in {'os-pkgs', 'lang-pkgs'}:
            continue
        for item in result.get('Vulnerabilities', []):
            if not all(isinstance(item.get(key), str) and item[key] for key in ('VulnerabilityID', 'PkgName', 'InstalledVersion')):
                raise ValueError('Trivy vulnerability is missing identity/package/version')
            scores = []
            for source, rating in item.get('CVSS', {}).items():
                for prefix in ('V2', 'V3', 'V4'):
                    scores += cvss_scores([{'baseScore': rating.get(prefix + 'Score'), 'vectorString': rating.get(prefix + 'Vector')}], source)
            fixed = [value.strip() for value in item.get('FixedVersion', '').split(',') if value.strip()]
            row = finding([item['VulnerabilityID']] + item.get('VendorIDs', []), item.get('Title') or item.get('Description'),
                          'Trivy vendor/package advisory', item.get('PrimaryURL'), scores=scores, severity=item.get('Severity'),
                          published=item.get('PublishedDate'), modified=item.get('LastModifiedDate'),
                          package={'ecosystem': 'runtime', 'name': result.get('Type', 'unknown') + ':' + item['PkgName'],
                                   'version': item['InstalledVersion'], 'runtime_id': component_id},
                          affected=[{'fixed_versions': fixed, 'ranges': [], 'status': item.get('Status')}],
                          evidence=[{'artifact': evidence, 'advisory_source': item.get('DataSource'),
                                     'package_path': item.get('PkgPath'), 'target': result.get('Target'),
                                     'package_identifier': item.get('PkgIdentifier')}])
            row['runtime_match'] = {'component_id': component_id, 'relation': 'inventory_match',
                                    'basis': 'Trivy vendor/package adapter; exploitability not assessed', 'exploitability': 'not_assessed'}
            rows.append(row)
    return rows


def artifact(args, report, *, image=None, rootfs=None, deployment=None):
    label = image or str(Path(rootfs).expanduser().resolve())
    source = 'artifact:' + label
    deployment = copy.deepcopy(deployment or {})
    inventory = {'source': label, 'observed_at': now(), 'deployment': deployment}
    try:
        if rootfs and not Path(label).is_dir():
            raise ValueError('Selected rootfs directory is missing or inaccessible')
        sbom, diagnostics = execute([args.syft, 'scan', 'registry:' + image if image else 'dir:' + label,
                                     '--output', 'syft-json', '--quiet'], args, empty_config=True)
        if not isinstance(sbom, dict) or not isinstance(sbom.get('artifacts'), list) or not isinstance(sbom.get('source'), dict):
            raise ValueError('Unsupported Syft JSON inventory schema')
        if image:
            metadata = sbom['source'].get('metadata', {})
            refs = metadata.get('repoDigests', [])
            if DIGEST.fullmatch(image):
                if image not in refs:
                    raise ValueError('Syft did not confirm the requested immutable image digest')
            else:
                pinned = [ref for ref in refs if DIGEST.fullmatch(ref)]
                if len(pinned) != 1:
                    raise ValueError('Image tag did not resolve to one immutable repository digest')
                image = pinned[0]
            inventory['image'] = image
            deployment['image_digest'] = image
        inventory['syft_version'] = sbom.get('descriptor', {}).get('version')
        inventory['packages_observed'] = len(sbom['artifacts'])
        report['runtime_components'].extend(java_components(sbom, label, deployment))
        report['coverage'].append({'source': source + ':inventory', 'status': 'warning' if diagnostics else 'ok',
                                   'packages_examined': len(sbom['artifacts']), 'reason': 'Syft emitted diagnostics; raw text omitted' if diagnostics else ''})
        if args.inventory_only:
            report.setdefault('artifact_inventory', []).append(inventory)
            return
        argv = [args.trivy, 'image' if image else 'rootfs', '--quiet', '--scanners', 'vuln',
                '--format', 'json', '--list-all-pkgs', '--exit-code', '0', '--ignorefile', '/dev/null',
                '--ignore-unfixed=false', '--severity', 'UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL']
        if image:
            argv += ['--image-src', 'remote']
        body, warnings = execute(argv + [image or label], args, empty_config=True)
        if not isinstance(body, dict) or body.get('SchemaVersion') != 2 or not isinstance(body.get('Results', []), list):
            raise ValueError('Unsupported Trivy JSON report schema')
        metadata = body.get('Metadata', {})
        if image and image not in metadata.get('RepoDigests', []):
            raise ValueError('Trivy report does not confirm the pinned image digest')
        os = metadata.get('OS', {})
        inventory['os'] = {key: os[key] for key in ('Family', 'Name', 'EOSL') if key in os}
        inventory['trivy_version'] = body.get('Trivy', {}).get('Version')
        # Version JSON carries database receipt independently of finding count.
        tool, version_warning = execute([args.trivy, 'version', '--format', 'json'], args, empty_config=True)
        db = tool.get('VulnerabilityDB', {})
        inventory['vulnerability_database'] = {key: db[key] for key in ('Version', 'UpdatedAt', 'NextUpdate', 'DownloadedAt') if key in db}
        at = timestamp(db.get('UpdatedAt')) if db.get('UpdatedAt') else None
        fresh = at is not None and 0 <= (timestamp(now()) - at).total_seconds() <= args.database_max_age
        inventory['deployment'] = deployment
        # Persist no ImageConfig.Env, SBOM secrets, helper stderr or pod spec.
        report.setdefault('artifact_inventory', []).append(inventory)
        scope = {key: value for key, value in deployment.items() if key not in {'image', 'image_digest'}}
        component_id = 'artifact-' + digest(json.dumps(scope or {'source': label}, sort_keys=True).encode())[:16]
        report['findings'].extend(trivy_findings(body, component_id, inventory))
        packages = sum(len(result.get('Packages', [])) for result in body.get('Results', []))
        status = 'warning' if warnings or version_warning else 'stale' if not fresh else 'limited' if os.get('EOSL') or packages == 0 else 'ok'
        report['coverage'].append({'source': source + ':Trivy', 'status': status, 'packages_examined': packages,
            'reason': 'Vendor/package advisory scope only; unsupported/unidentified packages are not assessed. Missing/stale database metadata, end-of-life OS, zero packages or helper diagnostics prevent complete coverage.'})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report['coverage'].append({'source': source, 'status': 'error', 'error': str(exc)})


def kubernetes(args, report):
    try:
        # Go template emits only the metadata needed for image assessment. Pod
        # environment variables and arbitrary annotations never leave kubectl.
        template = '{"pods":[{{range $i,$p := .items}}{{if $i}},{{end}}{"name":{{printf "%q" $p.metadata.name}},"uid":{{printf "%q" $p.metadata.uid}},"expectedContainers":{{len $p.spec.containers}},"expectedInit":{{if $p.spec.initContainers}}{{len $p.spec.initContainers}}{{else}}0{{end}},"expectedEphemeral":{{if $p.spec.ephemeralContainers}}{{len $p.spec.ephemeralContainers}}{{else}}0{{end}},"containers":[{{range $j,$c := $p.status.containerStatuses}}{{if $j}},{{end}}{"name":{{printf "%q" $c.name}},"image":{{printf "%q" $c.image}},"imageID":{{printf "%q" $c.imageID}}}{{end}}],"init":[{{range $j,$c := $p.status.initContainerStatuses}}{{if $j}},{{end}}{"name":{{printf "%q" $c.name}},"image":{{printf "%q" $c.image}},"imageID":{{printf "%q" $c.imageID}}}{{end}}],"ephemeral":[{{range $j,$c := $p.status.ephemeralContainerStatuses}}{{if $j}},{{end}}{"name":{{printf "%q" $c.name}},"image":{{printf "%q" $c.image}},"imageID":{{printf "%q" $c.imageID}}}{{end}}]}{{end}}]}'
        argv = [args.kubectl, '--context', args.kube_context, '--namespace', args.namespace,
                '--request-timeout', str(args.collect_timeout) + 's', 'get', 'pods', '-o', 'go-template=' + template]
        if args.selector:
            argv += ['--selector', args.selector]
        body, diagnostics = execute(argv, args)
        pods = body.get('pods')
        if not isinstance(pods, list) or not pods:
            raise ValueError('No selected pods; empty discovery does not establish a clean deployment')
        for pod in pods:
            for field, expected in (('containers', 'expectedContainers'), ('init', 'expectedInit'), ('ephemeral', 'expectedEphemeral')):
                if len(pod.get(field, [])) != pod.get(expected):
                    report['coverage'].append({'source': 'Kubernetes pod:' + pod['name'], 'status': 'missing', 'reason': 'Declared containers lack corresponding observed statuses: ' + field})
            entries = pod.get('containers', []) + pod.get('init', []) + pod.get('ephemeral', [])
            if not entries:
                report['coverage'].append({'source': 'Kubernetes pod:' + pod['name'], 'status': 'missing', 'reason': 'No observed container statuses/image IDs'})
            for container in entries:
                deployment = {'cluster': args.kube_context, 'namespace': args.namespace,
                              'workload': pod['name'] + '/' + container['name']}
                image = container.get('imageID', '').removeprefix('docker-pullable://')
                try:
                    image_ref(image, immutable=True)
                    artifact(args, report, image=image, deployment=deployment)
                except ValueError as exc:
                    report['coverage'].append({'source': 'Kubernetes container:' + deployment['workload'], 'status': 'missing', 'reason': str(exc)})
        report['coverage'].append({'source': 'Kubernetes discovery', 'status': 'warning' if diagnostics else 'ok',
                                   'pods_observed': len(pods), 'context': args.kube_context, 'namespace': args.namespace})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report['coverage'].append({'source': 'Kubernetes discovery', 'status': 'error', 'error': str(exc)})


def collect(args, report):
    for image in getattr(args, 'image', []):
        artifact(args, report, image=image)
    if getattr(args, 'rootfs', None):
        artifact(args, report, rootfs=args.rootfs)
    if getattr(args, 'kube_context', None):
        kubernetes(args, report)
