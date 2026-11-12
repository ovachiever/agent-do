"""Explicit local repository lists and isolated, sequential GitHub scans."""
from __future__ import annotations

import copy
import json
import stat
from pathlib import Path

from .model import merge_findings
from .scan import dependabot, repo_name, scan
from .sources import SourceError
from .store import digest, new_report


def load_repositories(filename, max_bytes, default_ref=None):
    path = Path(filename).expanduser().resolve()
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('--repos-file must be a regular file')
    with path.open('rb') as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError('--repos-file exceeds --max-bytes')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('--repos-file must be UTF-8 text') from exc
    if path.suffix.lower() == '.json' or text.lstrip().startswith(('[', '{')):
        try:
            entries = json.loads(text)
        except ValueError as exc:
            raise ValueError('--repos-file contains invalid JSON') from exc
        if not isinstance(entries, list):
            raise ValueError('JSON --repos-file must be an array of repo strings or {"repo": ..., "ref": ...} objects')
        entries = [(f'entry {index}', entry) for index, entry in enumerate(entries, 1)]
    else:
        entries = [(f'line {index}', line.strip()) for index, line in enumerate(text.splitlines(), 1)
                   if line.strip() and not line.lstrip().startswith('#')]
    result, seen = [], set()
    duplicates = 0
    for location, entry in entries:
        ref = default_ref
        if isinstance(entry, dict):
            if set(entry) - {'repo', 'ref'} or 'repo' not in entry:
                raise ValueError(f'Invalid repository fields at {location}; only repo and ref are supported')
            ref = entry.get('ref', default_ref)
            entry = entry['repo']
        if not isinstance(entry, str) or not entry or entry != entry.strip():
            raise ValueError(f'Invalid repository at {location}; use owner/repo or an HTTPS GitHub repository URL')
        try:
            repository = repo_name(entry)
        except ValueError as exc:
            # Never echo a potentially credential-bearing URL from the input file.
            raise ValueError(f'Invalid repository at {location}; use owner/repo or an HTTPS GitHub repository URL') from exc
        if ref is not None and (not isinstance(ref, str) or not ref.strip() or any(ord(c) < 32 or ord(c) == 127 for c in ref)):
            raise ValueError(f'Invalid ref at {location}; use a nonempty branch, tag, or commit')
        key = (repository.lower(), ref)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        result.append({'entry_id': str(len(result) + 1), 'repository': repository, 'requested_ref': ref})
    if not result:
        raise ValueError('--repos-file must contain at least one repository')
    return {'kind': 'github_batch', 'path': str(path), 'sha256': digest(raw),
            'repositories': result, 'duplicates_skipped': duplicates}


def scan_repositories(args, report, gh_tool):
    """Keep one snapshot/evidence record per target and continue after failures."""
    report['repositories'] = []
    for entry in report['target']['repositories']:
        selected = copy.copy(args)
        selected.repo = entry['repository']
        selected.ref = entry['requested_ref']
        selected.repos_file = None
        child = new_report('scan', {'kind': 'github', 'repository': selected.repo,
                                    'requested_ref': selected.ref})
        try:
            scan(selected, child)
        except (SourceError, OSError, ValueError, KeyError, TypeError) as exc:
            child['coverage'].append({'source': 'repository scan', 'status': 'error', 'error': str(exc)})
        if selected.dependabot:
            try:
                dependabot(selected, child, gh_tool)
            except (SourceError, OSError, ValueError, KeyError, TypeError) as exc:
                child['coverage'].append({'source': 'Dependabot', 'status': 'error', 'error': str(exc)})
        identity = {**entry, 'commit': child['target'].get('commit')}
        for row in child['findings']:
            row['repository_target'] = identity.copy()
        report['findings'].extend(merge_findings(child.pop('findings')))
        for coverage in child['coverage']:
            coverage['repository_target'] = identity.copy()
        report['coverage'].extend(child['coverage'])
        child['entry_id'] = entry['entry_id']
        child.pop('status')
        child['source_scan_status'] = 'incomplete' if any(x['status'] != 'ok' for x in child['coverage']) else 'complete'
        # Detailed inventory, packages, raw scanner evidence and optional alerts
        # live here; normalized findings and coverage are stored once at the top.
        child.pop('coverage')
        report['repositories'].append(child)
    report['notes'].append('Repository scans run sequentially. Findings count affected advisory/package/version/repository targets, not unique CVE identifiers across the portfolio.')
    if report['target']['duplicates_skipped']:
        report['notes'].append(f"Skipped {report['target']['duplicates_skipped']} duplicate repository/ref entries.")
