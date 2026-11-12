"""Persistent finding transitions, with conservative scope and failure handling."""
from __future__ import annotations

import copy
import re
import uuid

from .model import ecosystem

CATEGORIES = ('new', 'ongoing', 'resolved', 'unverified')


def package_key(row):
    package = row.get('package') or {}
    eco, name = ecosystem(package.get('ecosystem')), package.get('name', '')
    if eco == 'pip':
        name = re.sub(r'[-_.]+', '-', name).lower()
    elif eco in {'npm', 'nuget'}:
        name = name.lower()
    # Maven coordinates, Go import paths and other case-sensitive names must
    # remain distinct even if their advisories share a CVE alias.
    return [eco, name, package.get('runtime_id')] if eco in {'cpe', 'runtime'} else [eco, name]


def groups(rows):
    """Versions/occurrences of one advisory are one issue; union aliases transitively."""
    result = []
    for row in rows:
        group = {'package_key': package_key(row), 'aliases': set(row['aliases']), 'findings': [copy.deepcopy(row)]}
        changed = True
        while changed:
            changed = False
            for other in result[:]:
                if other['package_key'] == group['package_key'] and other['aliases'] & group['aliases']:
                    group['aliases'].update(other['aliases'])
                    group['findings'].extend(other['findings'])
                    result.remove(other)
                    changed = True
        result.append(group)
    return result


def compare_target(history, scope, rows, complete, at, report_id):
    """Only absence in a complete compatible assessment can resolve an issue."""
    changes = {category: [] for category in CATEGORIES}
    scopes = history.setdefault('scopes', {})
    ledger = scopes.setdefault(scope, {'issues': [], 'created_at': at})
    seen = set()
    for group in groups(rows):
        matches = [issue for issue in ledger['issues'] if issue['package_key'] == group['package_key']
                   and set(issue['aliases']) & group['aliases']]
        if matches:
            matches.sort(key=lambda issue: (issue['first_detected_at'], issue['issue_id']))
            issue = matches[0]
            was_active = any(item['active'] for item in matches)
            for other in matches[1:]:
                group['aliases'].update(other['aliases'])
                ledger['issues'].remove(other)
            group['aliases'].update(issue['aliases'])
            category = 'ongoing' if was_active else 'new'
            reopened = not was_active
        else:
            issue = {'issue_id': uuid.uuid4().hex, 'first_detected_at': at, 'package_key': group['package_key']}
            ledger['issues'].append(issue)
            category, reopened = 'new', False
        issue.update({'aliases': sorted(group['aliases']), 'findings': group['findings'], 'active': True,
                      'last_seen_at': at, 'last_seen_report': report_id, 'resolved_at': None})
        seen.add(issue['issue_id'])
        changes[category].append({**copy.deepcopy(issue), 'reopened': reopened})
    for issue in ledger['issues']:
        if issue['active'] and issue['issue_id'] not in seen:
            if complete:
                issue.update({'active': False, 'resolved_at': at, 'resolved_report': report_id})
                changes['resolved'].append({**copy.deepcopy(issue), 'resolution_basis': 'not detected in complete assessment of the same configured scope'})
            else:
                changes['unverified'].append({**copy.deepcopy(issue), 'reason': 'current assessment incomplete; previous evidence retained'})
    for prior_scope, prior in scopes.items():
        if prior_scope != scope:
            changes['unverified'].extend({**copy.deepcopy(issue), 'reason': 'different scan scope; not compared', 'scope': prior_scope}
                                         for issue in prior['issues'] if issue['active'])
    ledger['last_attempt_at'] = at
    if complete:
        ledger['last_complete_at'] = at
    return changes


def unscanned(history, reason):
    return [{**copy.deepcopy(issue), 'scope': scope, 'reason': reason}
            for scope, ledger in history.get('scopes', {}).items() for issue in ledger['issues'] if issue['active']]
