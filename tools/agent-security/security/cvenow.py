"""Optional public-advisory aggregation; never sends repository inventories."""
from __future__ import annotations

import re
import urllib.parse

from .model import cvss_scores, ecosystem, finding, timestamp
from .sources import SourceError

BASE = 'https://cve.now'
ECOSYSTEMS = {'npm': 'npm', 'pip': 'pypi', 'go': 'go', 'maven': 'maven',
              'rust': 'crates.io', 'composer': 'packagist', 'rubygems': 'rubygems',
              'erlang': 'hex', 'nuget': 'nuget'}
# Published feed selectors; reject unknown values rather than risk an unfiltered feed.
TECHNOLOGIES = set('nextjs react node express django flask rails spring log4j kubernetes docker nginx '
                   'apache-httpd openssl postgresql mysql redis php wordpress jenkins gitlab fortinet '
                   'citrix ivanti cisco-ios palo-alto-panos vmware microsoft-exchange chrome linux-kernel'.split())
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{1,199}')


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise SourceError('Unexpected cve.now advisory identifier')
    if value.upper().startswith('CVE-'):
        return value.upper()
    if value.upper().startswith('GHSA-'):
        return 'GHSA-' + value[5:].lower()
    return value


def validate_options(args):
    extra = args.technology or args.feed_filter or args.source_status
    if args.source != 'cve-now':
        if extra:
            raise ValueError('--technology, --feed-filter and --source-status require --source cve-now')
        return
    if args.vendor or args.product or args.query or args.target:
        raise ValueError('cve.now uses --technology, --ecosystem or --cve; NVD/curated selectors are not supported')
    if args.technology and args.technology not in TECHNOLOGIES:
        raise ValueError('Unsupported cve.now --technology; see the documented feed selectors')
    if args.ecosystem and ecosystem(args.ecosystem) not in ECOSYSTEMS:
        raise ValueError('Unsupported cve.now ecosystem')
    if args.cve and (args.technology or args.feed_filter):
        raise ValueError('--cve is a direct lookup; use a separate query for technology/curated feed selection')


def entry_row(entry):
    """Retain aggregator and upstream provenance without treating it as exposure."""
    if (not isinstance(entry, dict) or not isinstance(entry.get('status'), str)
            or entry['status'] not in {'published', 'rejected', 'withdrawn', 'superseded'}):
        raise SourceError('Unexpected cve.now entry schema/status')
    key = identifier(entry.get('id'))
    if entry['status'] != 'published':
        return None
    aliases = entry.get('aliases', [])
    affected = entry.get('affected', [])
    severity = entry.get('severity') if entry.get('severity') is not None else {}
    exploitation = entry.get('exploitation') if entry.get('exploitation') is not None else {}
    if (not isinstance(aliases, list) or not isinstance(affected, list)
            or not isinstance(severity, dict) or not isinstance(exploitation, dict)):
        raise SourceError('Unexpected cve.now entry fields')
    for field in ('publishedAt', 'modifiedAt'):
        try:
            timestamp(entry.get(field))
        except (ValueError, TypeError, AttributeError) as exc:
            raise SourceError('Invalid cve.now advisory date') from exc
    packages = []
    for item in affected:
        if not isinstance(item, dict) or not isinstance(item.get('ranges', []), list):
            raise SourceError('Invalid cve.now affected record')
        package = {'ecosystem': 'erlang' if item['ecosystem'].lower() == 'hex' else ecosystem(item['ecosystem']), 'name': item['package']} if isinstance(item.get('ecosystem'), str) and isinstance(item.get('package'), str) else None
        fixes = [r['fixed'] for r in item.get('ranges', []) if isinstance(r, dict)
                 and isinstance(r.get('fixed'), str) and r['fixed'] and not any(c in r['fixed'] for c in '*?')]
        # Vendor free text can resemble a version (or contain product patterns).
        # Only ecosystem/package records can supply package-specific fix metadata.
        packages.append({'package': package or {}, 'ranges': item.get('ranges', []),
                         'fixed_versions': fixes if package else []})
    url = BASE + '/' + key
    description = entry.get('originalDescription') or entry.get('title')
    if not isinstance(description, str):
        raise SourceError('Missing cve.now advisory description')
    row = finding([key, *[identifier(a) for a in aliases]], description, 'cve.now', url,
                  scores=cvss_scores([{'score': severity.get('cvss'), 'vectorString': severity.get('vector')}],
                                     'cve.now / ' + str(severity.get('source') or 'unspecified upstream')),
                  published=entry.get('publishedAt'), modified=entry.get('modifiedAt'), affected=packages,
                  evidence=[{'source': 'cve.now', 'url': url, 'record': entry,
                             'summary_notice': 'Model summaries, if present, are generated by the named model; CC-BY 4.0. Original description used for display.'}])
    row['aggregator'] = {'name': 'cve.now', 'exploitation': exploitation,
                         'summary': entry.get('summary'), 'summary_license': 'CC-BY-4.0',
                         'upstream_sources': entry.get('sources', []), 'references': entry.get('references', [])}
    if isinstance(exploitation.get('kev'), dict) and exploitation['kev']:
        row['known_exploited'] = True
        row['exploitation_source'] = {'name': 'cve.now (aggregated CISA KEV)', 'url': url,
                                      **exploitation['kev']}
    return row


def source_status(client, report):
    start = len(client.receipts)
    try:
        body, _ = client.get(BASE + '/api/v1/status')
        polling = body.get('polling') if isinstance(body, dict) else None
        if not isinstance(polling, dict) or not isinstance(polling.get('sources'), dict) or not polling['sources']:
            raise SourceError('Unexpected cve.now source status schema')
        report['source_status'] = {'source': 'cve.now', 'url': BASE + '/api/v1/status', 'data': body}
        ok = all(isinstance(v, dict) and v.get('ok') is True for v in polling['sources'].values())
        report['coverage'].append({'source': 'cve.now status', 'status': 'ok' if ok else 'warning',
                                   'reason': 'Self-reported polling health, not independent freshness verification',
                                   'receipts': client.receipts[start:]})
    except SourceError as exc:
        report['coverage'].append({'source': 'cve.now status', 'status': 'error', 'error': str(exc),
                                   'receipts': client.receipts[start:]})


def discover(args, client, report):
    report['target'] = {'kind': 'advisory_query', 'source': 'cve-now', 'technology': args.technology,
                        'ecosystem': args.ecosystem, 'feed_filter': args.feed_filter, 'cve': args.cve}
    report['limitations'] += ['Published advisory discovery only; no repository/runtime exposure is established.',
                              'cve.now is replaceable; explicit NVD/GitHub discovery and OSV/vendor scans remain available.',
                              'Only public advisory selectors/IDs are sent; no lockfiles or repository inventories are uploaded.',
                              'Date/package/score filters apply locally to examined records; capped results are not exhaustive.']
    feed = bool(args.technology or args.ecosystem or args.feed_filter)
    start, count, seen_ids, cursors = len(client.receipts), 0, set(), set()
    coverage = {'source': 'cve.now', 'status': 'error', 'records_examined': 0, 'limit': args.limit}
    report['coverage'].append(coverage)
    try:
        if args.cve:
            batch, more = [{'id': args.cve.upper()}], False
        else:
            params = {}
            if feed:
                params['format'] = 'json'
                if args.technology:
                    params['tech'] = args.technology
                if args.ecosystem:
                    params['ecosystem'] = ECOSYSTEMS[ecosystem(args.ecosystem)]
                if args.feed_filter:
                    params['filter'] = args.feed_filter
            cursor = None
        while True:
            if not args.cve:
                if cursor:
                    params['cursor'] = cursor
                path = '/feed' if feed else '/api/v1/entries'
                body, _ = client.get(BASE + path + ('?' + urllib.parse.urlencode(params) if params else ''))
                field = 'items' if feed else 'entries'
                if not isinstance(body, dict) or not isinstance(body.get(field), list) or (not feed and 'nextCursor' not in body):
                    raise SourceError('Unexpected cve.now listing schema')
                batch = body[field]
                next_cursor = None if feed else body['nextCursor']
                if next_cursor is not None and (not isinstance(next_cursor, str) or not next_cursor or len(next_cursor) > 4096):
                    raise SourceError('Invalid cve.now cursor')
                more = bool(next_cursor)
                if more and (next_cursor in cursors or not batch):
                    raise SourceError('cve.now pagination stalled')
                if next_cursor:
                    cursors.add(next_cursor)
            consumed = 0
            for item in batch[:args.limit - count]:
                if not isinstance(item, dict):
                    raise SourceError('Invalid cve.now listing record')
                key = identifier(item.get('id'))
                if key in seen_ids:
                    raise SourceError('cve.now pagination repeated an advisory')
                seen_ids.add(key)
                body, _ = client.get(BASE + '/api/v1/entries/' + key)
                row = entry_row(body)
                if key not in {identifier(body['id']), *[identifier(a) for a in body.get('aliases', [])]}:
                    raise SourceError('cve.now detail identity differs from the requested advisory')
                if row:
                    report['findings'].append(row)
                count += 1
                consumed += 1
                coverage['records_examined'] = count
            truncated = more or consumed < len(batch)
            if args.cve or feed or count >= args.limit or not more:
                break
            cursor = next_cursor
        limited = feed and not args.cve
        coverage.update(status='truncated' if truncated else 'limited' if limited else 'ok',
                        truncated=truncated,
                        reason='Recent feed only (up to 200 entries); not an exhaustive technology/ecosystem/date search' if limited
                        else 'Record cap reached before catalog exhaustion' if truncated else 'Selected lookup/catalog traversal completed')
        if args.feed_filter == 'critical':
            report['notes'].append('cve.now curated critical includes exploitation/technology rules; it is not CVSS critical severity.')
        return report['findings']
    except SourceError as exc:
        coverage['error'] = str(exc)
        return report['findings']
    finally:
        coverage['receipts'] = client.receipts[start:]
        if args.source_status:
            source_status(client, report)
