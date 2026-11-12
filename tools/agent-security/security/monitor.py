"""Portfolio configuration, due runs, comparison journals, digests and cron export."""
from __future__ import annotations

import copy
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from .comparison import CATEGORIES, compare_target, unscanned
from .model import matches, merge_findings, now, timestamp
from .repositories import load_repositories
from .scan import repo_name, scan
from .sources import Client, SourceError, enrich_kev
from .store import atomic_json, digest, finish, home, new_report
from .runtime import RUNTIME_MATCHER_SCHEMA, assess_runtime, cpe_parts, load_inventory

BUILD_OPTIONS = {'maven', 'gradle', 'maven_settings', 'maven_profile', 'gradle_configuration', 'build_property'}
LIST_OPTIONS = {'maven_profile', 'gradle_configuration', 'build_property'}
NETWORK_OPTIONS = ('timeout', 'retries', 'cache_ttl', 'refresh', 'allow_stale', 'max_bytes', 'kev')
COLLECT_OPTIONS = {'image', 'rootfs', 'kube_context', 'namespace', 'selector', 'syft', 'trivy', 'kubectl', 'collect_timeout', 'database_max_age'}


def runtime_target(target):
    return 'runtime_inventory' in target or 'runtime_collect' in target or 'runtime_probe' in target


def fingerprint(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def load_config(filename, max_bytes):
    path = Path(filename).expanduser().resolve()
    if not path.is_file():
        raise ValueError('Monitor configuration must be a regular file')
    with path.open('rb') as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError('Monitor configuration exceeds --max-bytes')
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) - {'schema_version', 'monitor_id', 'interval_hours', 'targets'}:
        raise ValueError('Invalid monitor configuration fields')
    if value.get('schema_version') != 1 or not re.fullmatch(r'[a-f0-9]{32}', str(value.get('monitor_id', ''))):
        raise ValueError('Unsupported monitor configuration: schema_version must be 1 and monitor_id must be 32 lowercase hexadecimal characters. Create with monitor init, then preserve those fields when editing targets; mixed source/runtime targets are supported.')
    interval = value.get('interval_hours')
    if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
        raise ValueError('interval_hours must be a positive whole number of hours')
    if not isinstance(value.get('targets'), list) or not value['targets']:
        raise ValueError('Monitor targets must be a nonempty array')
    seen = set()
    for target in value['targets']:
        if not isinstance(target, dict) or set(target) - {'repo', 'ref', 'path', 'resolve', 'options', 'runtime_inventory', 'runtime_collect', 'runtime_probe'}:
            raise ValueError('Invalid monitor target fields')
        if sum(key in target for key in ('repo', 'path', 'runtime_inventory', 'runtime_collect', 'runtime_probe')) != 1:
            raise ValueError('Each monitor target needs exactly one repo, path, runtime_inventory, runtime_collect or runtime_probe')
        if 'runtime_probe' in target:
            options = target['runtime_probe']
            if (set(target) != {'runtime_probe'} or not isinstance(options, dict)
                    or set(options) != {'python', 'python_upstream', 'probe_timeout'}
                    or not isinstance(options['python'], str) or not options['python']
                    or not isinstance(options['python_upstream'], bool)
                    or isinstance(options['probe_timeout'], bool) or not isinstance(options['probe_timeout'], (int, float))
                    or not math.isfinite(options['probe_timeout']) or options['probe_timeout'] <= 0):
                raise ValueError('Invalid runtime_probe target; create it with monitor init --local-python')
            if '/' in options['python']:
                options['python'] = str((path.parent / Path(options['python']).expanduser()).absolute())
            target['_key'] = fingerprint({'runtime_probe': options})
            if target['_key'] in seen:
                raise ValueError('Duplicate Python probe target in monitor configuration')
            seen.add(target['_key'])
            continue
        if 'runtime_collect' in target:
            options = target['runtime_collect']
            if set(target) != {'runtime_collect'} or not isinstance(options, dict) or set(options) - COLLECT_OPTIONS or not any(options.get(key) for key in ('image', 'rootfs', 'kube_context')):
                raise ValueError('Invalid runtime_collect target; use monitor init collector flags')
            for key, setting in options.items():
                if key == 'image':
                    if not isinstance(setting, list) or not setting or not all(isinstance(item, str) for item in setting):
                        raise ValueError('runtime_collect image must be an array of image references')
                elif key in {'collect_timeout', 'database_max_age'}:
                    if isinstance(setting, bool) or not isinstance(setting, (int, float)) or not math.isfinite(setting) or setting <= 0:
                        raise ValueError('Collector time/age limits must be finite positive numbers')
                elif not isinstance(setting, str) or not setting:
                    raise ValueError('Runtime collector options must be nonempty strings')
            for key in ('rootfs', 'syft', 'trivy', 'kubectl'):
                if key in options and (key == 'rootfs' or '/' in options[key]):
                    options[key] = str((path.parent / Path(options[key]).expanduser()).resolve())
            target['_key'] = fingerprint({'runtime_collect': options})
            if target['_key'] in seen:
                raise ValueError('Duplicate collector target in monitor configuration')
            seen.add(target['_key'])
            continue
        if 'runtime_inventory' in target:
            if set(target) != {'runtime_inventory'} or not isinstance(target['runtime_inventory'], str) or not target['runtime_inventory']:
                raise ValueError('Runtime monitor target accepts only a nonempty runtime_inventory path')
            target['runtime_inventory'] = str((path.parent / Path(target['runtime_inventory']).expanduser()).resolve())
            target['_key'] = fingerprint({'runtime_inventory': target['runtime_inventory']})
            if target['_key'] in seen:
                raise ValueError('Duplicate runtime inventory in monitor configuration')
            seen.add(target['_key'])
            continue
        if 'repo' in target:
            if not isinstance(target['repo'], str):
                raise ValueError('Monitor repo must be a GitHub repository string')
            target['repo'] = repo_name(target['repo'])
            ref = target.get('ref')
            if ref is not None and (not isinstance(ref, str) or not ref.strip() or any(ord(c) < 32 or ord(c) == 127 for c in ref)):
                raise ValueError('Invalid monitor repository ref')
            if target.get('resolve') or target.get('options'):
                raise ValueError('Build resolution/options require a trusted local path')
        else:
            if not isinstance(target['path'], str) or not target['path']:
                raise ValueError('Monitor path must be a directory path string')
            if 'ref' in target:
                raise ValueError('ref is only supported on GitHub monitor targets')
            local = Path(target['path']).expanduser()
            target['path'] = str((path.parent / local).resolve())
        if target.get('resolve') not in (None, 'maven', 'gradle'):
            raise ValueError('Monitor resolve must be maven or gradle')
        options = target.get('options', {})
        if not isinstance(options, dict) or set(options) - BUILD_OPTIONS:
            raise ValueError('Invalid monitor build options')
        for key, setting in options.items():
            if key in LIST_OPTIONS:
                if not isinstance(setting, list) or not all(isinstance(item, str) for item in setting):
                    raise ValueError('Monitor repeated build options must be arrays of strings')
            elif not isinstance(setting, str) or not setting:
                raise ValueError('Monitor executable/settings options must be nonempty strings')
        for key in ('maven', 'gradle', 'maven_settings'):
            if key in options and (key == 'maven_settings' or '/' in options[key]):
                options[key] = str((path.parent / Path(options[key]).expanduser()).resolve())
        identity = {key: target[key] for key in ('repo', 'ref', 'path') if key in target}
        if 'repo' in identity:
            identity['repo'] = identity['repo'].lower()
            identity.setdefault('ref', None)
        target['_key'] = fingerprint(identity)
        if target['_key'] in seen:
            raise ValueError('Duplicate repository/ref or local path in monitor configuration')
        seen.add(target['_key'])
    value['_file'], value['_sha256'] = str(path), digest(raw)
    return value


def initialize(args):
    if args.interval_hours < 1:
        raise ValueError('--interval-hours must be at least 1')
    if args.resolve and not args.path:
        raise ValueError('Monitor build resolution requires local --path')
    targets = []
    if args.repos_file:
        entries = load_repositories(args.repos_file, args.max_bytes)['repositories']
        targets.extend({'repo': entry['repository'], 'ref': entry['requested_ref']} for entry in entries)
    elif args.path:
        targets.append({'path': str(Path(args.path).expanduser().resolve())})
        if args.resolve:
            targets[0]['resolve'] = args.resolve
    if getattr(args, 'runtime_inventory', None):
        load_inventory(args.runtime_inventory, args.max_bytes)
        targets.append({'runtime_inventory': str(Path(args.runtime_inventory).expanduser().resolve())})
    if any(getattr(args, key, None) for key in ('image', 'rootfs', 'kube_context')):
        options = {key: getattr(args, key) for key in COLLECT_OPTIONS if getattr(args, key, None)}
        if options.get('rootfs'):
            options['rootfs'] = str(Path(options['rootfs']).expanduser().resolve())
        for key in ('syft', 'trivy', 'kubectl'):
            if '/' in options.get(key, ''):
                options[key] = str(Path(options[key]).expanduser().resolve())
        targets.append({'runtime_collect': options})
    if args.local_python:
        executable = shutil.which(args.python or sys.executable)
        if not executable:
            raise ValueError('Python executable not found; select --python PATH')
        targets.append({'runtime_probe': {'python': str(Path(executable).absolute()),
            'python_upstream': args.python_upstream, 'probe_timeout': args.probe_timeout}})
    if not targets:
        raise ValueError('Monitor initialization requires a source, runtime inventory, collector or local Python target')
    value = {'schema_version': 1, 'monitor_id': uuid.uuid4().hex, 'interval_hours': args.interval_hours, 'targets': targets}
    path = Path(args.config).expanduser().resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError('Monitor config already exists: ' + str(path) + '; choose a new --config path or use monitor run with the existing config. Nothing was overwritten.') from exc
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    return {'schema_version': 1, 'command': 'monitor init', 'status': 'ok', 'config': str(path), 'monitor_id': value['monitor_id'], 'targets': len(targets)}


def scan_arguments(target, args, parse_scan, validate_scan):
    argv = (['runtime', '--local-python'] if 'runtime_probe' in target else ['runtime'] if 'runtime_collect' in target else ['runtime', '--inventory', target['runtime_inventory']] if 'runtime_inventory' in target else
            ['scan', '--repo', target['repo']] if 'repo' in target else ['scan', '--path', target['path']])
    for key, setting in target.get('runtime_probe', {}).items():
        if key == 'python_upstream':
            if setting:
                argv.append('--python-upstream')
        else:
            argv += ['--' + key.replace('_', '-'), str(setting)]
    for key, value in target.get('runtime_collect', {}).items():
        for item in value if key == 'image' else [value]:
            argv += ['--' + key.replace('_', '-'), str(item)]
    if target.get('ref'):
        argv += ['--ref', target['ref']]
    if target.get('resolve'):
        argv += ['--resolve', target['resolve']]
    for key, setting in target.get('options', {}).items():
        for item in setting if key in LIST_OPTIONS else [setting]:
            argv += ['--' + key.replace('_', '-'), item]
    selected = parse_scan(argv)
    for key in NETWORK_OPTIONS:
        setattr(selected, key, getattr(args, key))
    if runtime_target(target):
        selected.limit = args.runtime_limit
    selected.scanner, selected.scan_timeout = args.scanner, args.scan_timeout
    selected._monitor_planned = True
    validate_scan(selected)
    return selected


@contextmanager
def locked(directory):
    try:
        import fcntl
    except ImportError as exc:
        raise ValueError('Monitor locking requires POSIX (macOS/Linux)') from exc
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(directory / '.lock', os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Another run of this monitor is active') from exc
        yield
    finally:
        os.close(fd)


def scope_key(target, report, max_bytes):
    descriptor = {'repo': target.get('repo', '').lower(), 'ref': target.get('ref'),
                  'path': target.get('path'), 'resolve': target.get('resolve'),
                  'options': target.get('options', {})}
    settings = target.get('options', {}).get('maven_settings')
    if settings:
        with Path(settings).open('rb') as stream:
            content = stream.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError('Monitor settings fingerprint input exceeds --max-bytes')
        descriptor['settings_sha256'] = digest(content)
    if runtime_target(target):
        descriptor['runtime_inventory'] = target.get('runtime_inventory')
        descriptor['runtime_collect'] = target.get('runtime_collect')
        descriptor['runtime_probe'] = target.get('runtime_probe')
        descriptor['runtime_matcher_schema'] = report.get('runtime_matcher_schema', RUNTIME_MATCHER_SCHEMA)
        descriptor['runtime_scope'] = []
        for component in report.get('runtime_components', []):
            parts = cpe_parts(component['cpe']) if component.get('cpe') else [component.get('python', {}).get('implementation', component.get('java', {}).get('vendor', 'unmapped')), 'python' if component.get('python') else component.get('java', {}).get('product', 'java')]
            if component.get('cpe'):
                parts[5:7] = ['*', '*']
            deployment = component.get('deployment', {}).copy()
            if component['evidence']['kind'] == 'artifact_release_file':
                deployment.pop('image_digest', None)
            descriptor['runtime_scope'].append({'id': component['id'], 'product_identity': ':'.join(parts),
                                               'deployment': deployment,
                                               'evidence_kind': component['evidence']['kind']})
        descriptor['runtime_scope'].sort(key=lambda row: row['id'])
        descriptor['artifact_tools'] = sorted({(item.get('syft_version') or '', item.get('trivy_version') or '') for item in report.get('artifact_inventory', [])})
    descriptor['effective_ref'] = report.get('target', {}).get('requested_ref')
    descriptor['scanner_version'] = report.get('scanner', {}).get('version')
    descriptor['build_version'] = report.get('resolution', {}).get('version')
    descriptor['comparison_schema'] = 1
    return fingerprint(descriptor)


def assessment_summary(targets, rows=None):
    """Keep acquisition failures visible independently of issue transitions.

    Missing row counts on older digests stay unknown, never inferred as zero
    from lifecycle counts which may include historical/unverified evidence.
    """
    issues = []
    for target in targets:
        for coverage in target.get('coverage', []):
            if coverage['status'] != 'ok':
                issues.append({'target_key': target['target_key'], 'target': target['target'],
                               'source': coverage['source'], 'status': coverage['status'],
                               'message': coverage.get('error') or coverage.get('reason') or 'Coverage incomplete'})
    incomplete = sum(target['status'] != 'complete' for target in targets)
    return {'status': 'incomplete' if incomplete or issues else 'complete',
            'targets_total': len(targets), 'targets_complete': len(targets) - incomplete,
            'targets_incomplete': incomplete,
            'findings_observed': len(rows) if rows is not None else None,
            'runtime_inventory_matches': sum(row.get('runtime_match', {}).get('relation') == 'inventory_match' for row in rows) if rows is not None else None,
            'runtime_candidates': sum(row.get('runtime_match', {}).get('relation') == 'candidate' for row in rows) if rows is not None else None,
            'coverage_issues': issues,
            'interpretation': 'Incomplete assessment: zero findings or zero changes do not establish absence of vulnerabilities. Detected findings/candidates are retained. Only a complete compatible assessment of a target can resolve its earlier evidence.' if incomplete or issues else 'Assessment completed for the supplied scope; findings and change counts are not an all-clear signal.'}


def run_monitor(args, parse_scan, validate_scan, root):
    config = load_config(args.config, args.max_bytes)
    # Validate every target before any acquisition or project execution.
    selected = [scan_arguments(target, args, parse_scan, validate_scan) for target in config['targets']]
    directory = home() / 'monitors' / config['monitor_id']
    with locked(directory):
        state_file = directory / 'state.json'
        state = json.loads(state_file.read_text()) if state_file.exists() else {'schema_version': 1, 'targets': {}}
        if not isinstance(state, dict) or state.get('schema_version') != 1 or not isinstance(state.get('targets'), dict):
            raise ValueError('Unsupported monitor state; refusing to discard history')
        try:
            for history in state['targets'].values():
                if not isinstance(history['scopes'], dict) or not isinstance(history['target'], dict):
                    raise ValueError('Invalid monitor history')
                for ledger in history['scopes'].values():
                    if not isinstance(ledger['issues'], list):
                        raise ValueError('Invalid monitor issue history')
                    for issue in ledger['issues']:
                        if not isinstance(issue['active'], bool) or not isinstance(issue['aliases'], list) or not isinstance(issue['findings'], list):
                            raise ValueError('Invalid monitor finding history')
                        for key in ('issue_id', 'package_key', 'first_detected_at'):
                            if key not in issue:
                                raise ValueError('Missing monitor finding identity')
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError('Invalid monitor state; refusing to discard history') from exc
        at = now()
        due = timestamp(state.get('last_attempt_at'))
        if args.due and due and timestamp(at) < due + timedelta(hours=config['interval_hours']):
            return {'schema_version': 1, 'command': 'monitor run', 'status': 'ok', 'skipped': True,
                    'reason': 'not due', 'next_due': (due + timedelta(hours=config['interval_hours'])).isoformat(),
                    'last_digest': state.get('last_digest')}
        report = new_report('scan', {'kind': 'portfolio', 'monitor_id': config['monitor_id'], 'config': config['_file']})
        if any(runtime_target(target) for target in config['targets']):
            report['scope'] = 'portfolio_source_and_explicit_runtime_inventory'
            report['limitations'] = ['Source dependency assessment and explicit runtime inventory are separate scopes. Imported deployment evidence is not independently verified; live deployments, reachability and remediation are not established.']
        report['monitor'] = {'config_sha256': config['_sha256'], 'interval_hours': config['interval_hours']}
        children = []
        client = Client(args)
        for target, scan_args in zip(config['targets'], selected):
            is_runtime = runtime_target(target)
            child = new_report('runtime' if is_runtime else 'scan',
                {'kind': 'runtime_inventory', 'inventory': target.get('runtime_inventory'), 'collection': target.get('runtime_collect'), 'probe': target.get('runtime_probe')} if is_runtime else
                {'kind': 'github', 'repository': target['repo']} if 'repo' in target else {'kind': 'local', 'path': target['path']})
            try:
                if target.get('resolve') and not args.allow_builds:
                    raise ValueError('Local build execution requires monitor run --allow-builds')
                if 'runtime_probe' in target and not getattr(args, 'allow_collectors', False):
                    raise ValueError('Local Python probe execution requires monitor run --allow-collectors')
                if 'runtime_collect' in target and not getattr(args, 'allow_collectors', False):
                    raise ValueError('Runtime collector execution requires monitor run --allow-collectors')
                if is_runtime:
                    assess_runtime(scan_args, client, child)
                else:
                    scan(scan_args, child)
            except (OSError, SourceError, ValueError, KeyError, TypeError) as exc:
                child['coverage'].append({'source': 'monitor target', 'status': 'error', 'error': str(exc)})
            identity = {'entry_id': target['_key'], 'repository': target.get('repo', target.get('path', target.get('runtime_inventory', target.get('runtime_probe', {}).get('python', 'runtime collectors')))),
                        'requested_ref': target.get('ref'), 'commit': child['target'].get('commit')}
            for row in child['findings']:
                row['repository_target'] = identity.copy()
            for coverage in child['coverage']:
                coverage['repository_target'] = identity.copy()
            report['findings'].extend(child['findings'])
            report['coverage'].extend(child['coverage'])
            children.append(child)
        report['findings'] = merge_findings(report['findings'])
        if args.kev or args.known_exploited:
            enrich_kev(client, report)
        for item in report['coverage']:
            if any(receipt.get('stale') for receipt in item.get('receipts', [])):
                item['status'] = 'stale'
        report['repositories'] = []
        for target, child in zip(config['targets'], children):
            metadata = {key: value for key, value in child.items() if key not in {'findings', 'coverage'}}
            metadata['entry_id'] = target['_key']
            metadata['status'] = 'complete' if all(item['status'] == 'ok' for item in child['coverage'] + [item for item in report['coverage'] if not item.get('repository_target')]) else 'incomplete'
            report['repositories'].append(metadata)
        report = finish(report)
        changes = {category: [] for category in CATEGORIES}
        target_summaries = []
        active_keys = set()
        shared = [item for item in report['coverage'] if not item.get('repository_target')]
        for target, child in zip(config['targets'], children):
            key = target['_key']
            active_keys.add(key)
            label = {k: v for k, v in target.items() if k in {'repo', 'ref', 'path', 'resolve', 'runtime_inventory', 'runtime_collect', 'runtime_probe'}}
            history = state['targets'].setdefault(key, {'target': label, 'scopes': {}})
            history['target'] = label
            coverage = shared + [item for item in report['coverage'] if item.get('repository_target', {}).get('entry_id') == key]
            complete = all(item['status'] == 'ok' for item in coverage)
            rows = [row for row in report['findings'] if row['repository_target']['entry_id'] == key]
            scope = scope_key(target, child, args.max_bytes)
            transitions = compare_target(history, scope, rows, complete, at, report['report_id'])
            history['scopes'][scope]['evidence_scope'] = {
                'scanner_version': child.get('scanner', {}).get('version'),
                'build_version': child.get('resolution', {}).get('version'),
                'runtime_matcher_schema': child.get('runtime_matcher_schema'),
                'effective_ref': child['target'].get('requested_ref'),
                'configuration_fingerprint': fingerprint({k: v for k, v in target.items() if not k.startswith('_')})}
            for category, issues in transitions.items():
                changes[category].extend({**issue, 'target_key': key, 'target': history['target']} for issue in issues)
            target_summaries.append({'target_key': key, 'target': history['target'], 'commit': child['target'].get('commit'),
                                     'status': 'complete' if complete else 'incomplete', 'scope': scope,
                                     'coverage': coverage, 'runtime_matcher_schema': child.get('runtime_matcher_schema'),
                                     'counts': {category: len(issues) for category, issues in transitions.items()}})
        for key, history in state['targets'].items():
            if key not in active_keys:
                changes['unverified'].extend({**issue, 'target_key': key, 'target': history['target']}
                    for issue in unscanned(history, 'target no longer configured; not scanned or resolved'))
        result = {'schema_version': 1, 'command': 'monitor run', 'monitor_id': config['monitor_id'],
                  'run_id': report['report_id'], 'created_at': at, 'status': report['status'],
                  'comparison_status': 'partial' if changes['unverified'] else 'complete',
                  'targets': target_summaries, 'changes': changes,
                  'assessment_summary': assessment_summary(target_summaries, report['findings']),
                  'counts': {category: len(issues) for category, issues in changes.items()},
                  'source_report': report['saved_report'],
                  'notes': ['New means first detected in this monitor/scope, not newly published.',
                            'Resolved means no longer detected in a complete compatible source assessment; deployment remediation is not established.',
                            'Different scanner/build versions, runtime matcher revisions or configuration create separate baselines; earlier unresolved issues stay unverified.']}
        result['saved_digest'] = str(directory / 'digests' / (at.replace(':', '-') + '-' + result['run_id'] + '.json'))
        state.update({'last_attempt_at': at, 'last_digest': result['saved_digest']})
        # One state replacement includes the digest for crash recovery. A failed
        # state write cannot advance the baseline; raw assessment is still saved.
        state['latest_digest'] = result
        atomic_json(state_file, state)
        atomic_json(result['saved_digest'], result)
        if args.notify_recipient:
            counts = present_digest(result, args)['shown_counts']
            message = 'Security portfolio (filtered counts): ' + ', '.join(f'{counts[category]} {category}' for category in CATEGORIES) + '; scan ' + result['status'] + '; comparison ' + result['comparison_status'] + '; ' + result['saved_digest']
            command = [str(root / 'bin' / 'notify'), 'send', args.notify_recipient, message, '--json']
            if args.notify_via:
                command += ['--via', args.notify_via]
            try:
                sent = subprocess.run(command, capture_output=True, timeout=args.timeout, check=False)
                result['notification'] = {'status': 'sent' if sent.returncode == 0 else 'error', 'exit_code': sent.returncode, 'counts': counts}
            except (OSError, subprocess.TimeoutExpired):
                result['notification'] = {'status': 'error'}
            if result['notification']['status'] != 'sent':
                result['status'] = 'incomplete'
            state['latest_digest'] = result
            atomic_json(state_file, state)
            atomic_json(result['saved_digest'], result)
        return result


def read_digest(args):
    config = load_config(args.config, args.max_bytes)
    state_file = home() / 'monitors' / config['monitor_id'] / 'state.json'
    if args.file:
        result = json.loads(Path(args.file).expanduser().read_text())
    else:
        if not state_file.exists():
            raise ValueError('No monitor runs yet; use monitor run')
        state = json.loads(state_file.read_text())
        if not isinstance(state, dict) or state.get('schema_version') != 1 or not isinstance(state.get('latest_digest'), dict):
            raise ValueError('Invalid monitor state; no valid latest committed digest')
        result = state['latest_digest']
    if not isinstance(result, dict) or result.get('schema_version') != 1 or result.get('monitor_id') != config['monitor_id'] or not isinstance(result.get('changes'), dict):
        raise ValueError('Digest does not match this monitor/schema')
    return result


def present_digest(result, args):
    payload = copy.deepcopy(result)
    if 'changes' not in payload:
        return payload
    if 'assessment_summary' not in payload:
        payload['assessment_summary'] = assessment_summary(payload.get('targets', []))
    if args.monitor_command == 'report' and args.known_exploited and any(row.get('known_exploited') is None for issues in payload['changes'].values() for issue in issues for row in issue['findings']):
        raise ValueError('Some monitor evidence has unknown exploitation status; repeat monitoring with --kev')
    payload['changes'] = {category: [issue for issue in issues if any(matches(row, args) for row in issue['findings'])]
                          for category, issues in payload['changes'].items()}
    payload['shown_counts'] = {category: len(issues) for category, issues in payload['changes'].items()}
    return payload


def schedule(args, root):
    config = load_config(args.config, args.max_bytes)
    executable = (root / 'tools' / 'agent-security' / 'agent-security').resolve()
    argv = [sys.executable, str(executable), 'monitor', 'run', '--config', config['_file'], '--due', '--max-bytes', str(args.max_bytes), '--runtime-limit', str(args.runtime_limit), '--json']
    if args.allow_builds:
        argv.append('--allow-builds')
    if getattr(args, 'allow_collectors', False):
        argv.append('--allow-collectors')
    if args.notify_recipient:
        argv += ['--notify-recipient', args.notify_recipient]
    if args.notify_via:
        argv += ['--notify-via', args.notify_via]
    if any(target.get('resolve') for target in config['targets']) and not args.allow_builds:
        raise ValueError('Scheduling local build resolution requires explicit --allow-builds')
    if any('runtime_collect' in target or 'runtime_probe' in target for target in config['targets']) and not getattr(args, 'allow_collectors', False):
        raise ValueError('Scheduling runtime collection requires explicit --allow-collectors')
    command = ' '.join(shlex.quote(item) for item in [
        'env', 'PATH=' + os.environ.get('PATH', ''), 'AGENT_DO_HOME=' + str(home().parent), *argv])
    if '\n' in command or '\r' in command:
        raise ValueError('Cron command cannot contain newlines')
    # Cron treats unescaped % specially even inside shell quotes.
    cron = '0 * * * * ' + command.replace('%', r'\%')
    return {'schema_version': 1, 'command': 'monitor schedule', 'status': 'ok', 'cron': cron,
            'interval_hours': config['interval_hours'], 'installed': False,
            'notes': ['Review and install this line with crontab -e on the scan host. Hourly checks run only when due.',
                      'Uses existing host gh/build credentials. No scheduler or notification is installed automatically.',
                      'PATH, Python and checkout paths are specific to this host/session. Regenerate on the scheduling host/account; do not copy a laptop PATH unchanged into CI.']}
