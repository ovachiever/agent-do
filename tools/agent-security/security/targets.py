"""Versioned, explicit discovery profiles and isolated multi-target queries."""
from __future__ import annotations

import copy

from .model import merge_findings
from .sources import SourceError, discover
from .store import new_report

PROFILE_VERSION = 1
ALIASES = {'springboot': 'spring-boot', 'node': 'nodejs'}


def cpe(vendor, product, *, relation='product_advisory'):
    return {'source': 'nvd', 'vendor': vendor, 'product': product,
            'match_basis': 'NVD CPE query', 'relation': relation}


def keyword(value):
    return {'source': 'nvd', 'query': value, 'match_basis': 'NVD keyword query',
            'relation': 'keyword_candidate'}


def packages(ecosystem, names):
    return [{'source': 'github', 'ecosystem': ecosystem, 'package': name,
             'match_basis': 'GitHub package query', 'relation': 'package_advisory'} for name in names]


PROFILES = {
    'java': {
        'description': 'Java SE, JDK/JRE, and OpenJDK discovery',
        'scope': 'Oracle Java SE/JDK/JRE/OpenJDK CPE identities plus Java SE/OpenJDK keyword candidates; not every Java distribution or Maven dependency.',
        'queries': [cpe('oracle', 'java_se'), cpe('oracle', 'jdk'), cpe('oracle', 'jre'), cpe('oracle', 'openjdk'),
                    keyword('Java SE'), keyword('OpenJDK')],
    },
    'spring-boot': {
        'description': 'Selected Spring Boot, Framework, and Security Maven packages',
        'scope': 'A curated package list, not every Boot starter, Spring Cloud component, plugin, or application transitive dependency.',
        'queries': packages('maven', [
            'org.springframework.boot:spring-boot', 'org.springframework.boot:spring-boot-autoconfigure',
            'org.springframework.boot:spring-boot-actuator', 'org.springframework.boot:spring-boot-actuator-autoconfigure',
            'org.springframework.boot:spring-boot-starter-actuator', 'org.springframework.boot:spring-boot-devtools',
            'org.springframework.boot:spring-boot-loader', 'org.springframework.boot:spring-boot-loader-tools',
            'org.springframework:spring-core', 'org.springframework:spring-beans', 'org.springframework:spring-context',
            'org.springframework:spring-expression', 'org.springframework:spring-web', 'org.springframework:spring-webmvc',
            'org.springframework:spring-webflux', 'org.springframework:spring-messaging', 'org.springframework:spring-websocket',
            'org.springframework.security:spring-security-core', 'org.springframework.security:spring-security-web',
            'org.springframework.security:spring-security-config',
        ]),
    },
    'angular': {
        'description': 'Selected modern Angular runtime, SSR, and build packages',
        'scope': 'A curated npm package list; excludes AngularJS, third-party components, and unrelated npm dependencies.',
        'queries': packages('npm', ['@angular/core', '@angular/common', '@angular/compiler', '@angular/compiler-cli',
            '@angular/platform-browser', '@angular/platform-server', '@angular/router', '@angular/forms',
            '@angular/animations', '@angular/ssr', '@angular/cli', '@angular-devkit/build-angular']),
    },
    'nodejs': {
        'description': 'Node.js runtime discovery',
        'scope': 'Node.js CPE identity and Node.js keyword candidates; not every npm package or installed Node version.',
        'queries': [cpe('nodejs', 'node.js'), keyword('Node.js')],
    },
    'aks': {
        'description': 'NVD-indexed AKS service records and upstream Kubernetes candidates',
        'scope': 'NVD-indexed AKS CPE/keyword records and upstream Kubernetes CPE records. No direct MSRC bulletin feed, cluster inspection, node-image, add-on, or workload inventory.',
        'queries': [cpe('microsoft', 'azure_kubernetes_service'), keyword('Azure Kubernetes Service'),
                    cpe('kubernetes', 'kubernetes', relation='upstream_dependency_candidate')],
    },
}


def canonical_target(value):
    normalized = ALIASES.get(value.lower(), value.lower())
    if normalized not in PROFILES:
        raise ValueError('Unknown target; choose ' + ', '.join(PROFILES))
    return normalized


class QueryClient:
    """Keep receipts local to one query while sharing transport/cache/rate pacing."""
    def __init__(self, parent):
        self.parent = parent
        self.receipts = []

    def get(self, url):
        start = len(self.parent.receipts)
        try:
            return self.parent.get(url)
        finally:
            self.receipts.extend(self.parent.receipts[start:])


def discover_targets(args, client, report):
    selected = list(dict.fromkeys(canonical_target(x) for x in args.target))
    report['target'] = {'kind': 'multi_advisory_query', 'targets': selected, 'profile_version': PROFILE_VERSION,
                        'profiles': [{'target': name, 'description': PROFILES[name]['description'],
                                      'scope': PROFILES[name]['scope'], 'query_count': len(PROFILES[name]['queries'])}
                                     for name in selected]}
    report['limitations'] += ['Target profiles are curated discovery queries, not exhaustive ecosystem inventories.',
                              'A target match identifies advisory relevance, not repository or deployment exposure.']
    report['searches'] = []
    report['source_filters'] = {key: getattr(args, key) for key in ('cve', 'published_after', 'published_before', 'updated_after')
                                if getattr(args, key) is not None}
    rows = []
    for target in selected:
        for index, specification in enumerate(PROFILES[target]['queries'], start=1):
            query_id = target + ':' + str(index)
            criteria = {key: specification.get(key) for key in ('source', 'vendor', 'product', 'query', 'ecosystem', 'package')}
            report['searches'].append({'query_id': query_id, 'target': target, 'criteria': criteria,
                                       'match_basis': specification['match_basis'], 'relation': specification['relation']})
            query_args = copy.copy(args)
            query_args.target = []
            for key, value in criteria.items():
                setattr(query_args, key, value)
            scoped = QueryClient(client)
            partial = new_report('find', {})
            try:
                discover(query_args, scoped, partial)
            except (SourceError, OSError, ValueError, KeyError, TypeError) as exc:
                # A failed page must not discard rows already collected or stop other targets.
                partial['coverage'].append({'source': criteria['source'], 'status': 'error', 'error': str(exc),
                                             'records_examined': None, 'records_returned': len(partial['findings']),
                                             'limit': args.limit, 'truncated': None, 'receipts': scoped.receipts[:]})
            for row in partial['findings']:
                row.setdefault('matched_targets', []).append(target)
                row.setdefault('target_matches', []).append({
                    'target': target, 'query_id': query_id, 'source': criteria['source'], 'criteria': criteria,
                    'match_basis': specification['match_basis'], 'relation': specification['relation'],
                    'published': row.get('published'), 'modified': row.get('modified'),
                })
                rows.append(row)
            for coverage in partial['coverage']:
                coverage.update({'target': target, 'query_id': query_id})
                if any(item.get('stale') for item in coverage.get('receipts', [])) and coverage['status'] == 'ok':
                    coverage['status'] = 'stale'
                report['coverage'].append(coverage)
            report['findings'] = rows
    report['notes'].append('--limit applies independently to each component query before presentation filters. Query counts and all criteria are recorded under searches.')
    report['findings'] = merge_findings(rows)
    return report['findings']
