"""Adoptium's OpenJDK-derived VDR; never substitute an Oracle identity."""
from __future__ import annotations

import copy
import json
import re

from .model import cvss_scores, finding
from .sources import SourceError, re_asset_path

RELEASE = 'https://api.github.com/repos/adoptium/temurin-vdr-generator/releases/latest'


def identity(vendor, version, runtime_version=None):
    if vendor != 'Eclipse Adoptium':
        return None
    return {'vendor': 'eclipse_adoptium', 'product': 'temurin', 'version': version,
            'runtime_version': runtime_version or version}


def version(value):
    from .runtime import numeric_version
    # Temurin's LTS designation/build number does not change the OpenJDK patch.
    return numeric_version(re.sub(r'(?:\+\d+(?:\.\d+)*(?:-LTS)?|-LTS)$', '', value), java=True)


def document(args, client):
    if getattr(args, 'temurin_vdr', None):
        from .runtime import read_bounded
        from .store import digest
        raw = read_bounded(args.temurin_vdr, args.max_bytes)
        return json.loads(raw), {'source': str(args.temurin_vdr), 'sha256': digest(raw),
                                 'verification': 'user_supplied_not_independently_verified'}
    release, _ = client.get(RELEASE)
    assets = [asset for asset in release.get('assets', []) if asset.get('name', '').endswith('.json')]
    if release.get('draft') or release.get('prerelease') or len(assets) != 1:
        raise SourceError('Unexpected Adoptium VDR release metadata')
    asset = assets[0]
    url = asset.get('browser_download_url', '')
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != 'github.com' or not re_asset_path(parsed.path):
        raise SourceError('Unexpected Adoptium VDR asset URL')
    body, meta = client.get(url)
    checksum = asset.get('digest', '')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', checksum) or checksum[7:] != meta.get('sha256'):
        raise SourceError('Adoptium VDR asset digest absent or mismatched')
    return body, {'source': url, 'release': release['tag_name'], 'sha256': meta['sha256'],
                  'published_at': release.get('published_at'), 'verification': 'official_release_digest_checked'}


def listed_versions(affects):
    """Yield status and parsed patch listings using one VDR interpretation."""
    for target in affects:
        if target.get('ref') != 'pkg:github/openjdk/jdk':
            continue
        for entry in target.get('versions', []):
            values = [entry['version']] if entry.get('version') else entry.get('range', '').removeprefix('vers:generic/').split('|')
            for value in values:
                yield entry.get('status', 'affected'), version(value)


def relation(affects, current):
    """Exact VDR listings match; earlier releases stay candidates, not guesses.

    The generator derives per-major affected patch listings from OJVG tables.
    Its generic enumeration is not an introduction/fix range or build/OS proof.
    """
    from .runtime import compare
    known, unknown = [], False
    for status, parsed in listed_versions(affects):
        if status != 'affected' or parsed is None:
            unknown = True
        elif current and parsed[0] == current[0]:
            known.append(parsed)
    if current is None:
        return None
    if any(compare(current, item) == 0 for item in known):
        return True
    if unknown or any(compare(current, item) < 0 for item in known):
        return None
    return False


def assess(component, args, client, report):
    start = len(client.receipts)
    source = 'Adoptium VDR runtime:' + component['id']
    try:
        body, provenance = document(args, client)
        if not isinstance(body, dict) or body.get('bomFormat') != 'CycloneDX' or body.get('metadata', {}).get('component', {}).get('name') != 'Eclipse Temurin' or not isinstance(body.get('vulnerabilities'), list) or not body['vulnerabilities']:
            raise SourceError('Unsupported or empty Eclipse Temurin VDR document')
        current = version(component['java']['version'])
        branches = {parsed[0] for item in body['vulnerabilities']
                    for _, parsed in listed_versions(item.get('affects', [])) if parsed}
        unknown, examined = current is None, 0
        for item in body['vulnerabilities']:
            if not re.fullmatch(r'CVE-\d{4}-\d{4,}', str(item.get('id', ''))):
                raise SourceError('Invalid advisory identity in Temurin VDR')
            if args.cve and args.cve.upper() != item['id']:
                continue
            examined += 1
            result = relation(item.get('affects', []), current)
            if not item.get('affects'):
                result = None
            if result is False:
                continue
            unknown |= result is None
            scores = []
            for rating in item.get('ratings', []):
                scores += cvss_scores([{'score': rating.get('score'), 'vectorString': rating.get('vector'),
                                       'version': rating.get('method')}], rating.get('source', {}).get('name', 'Adoptium VDR'))
            row = finding([item['id']], item.get('description'), 'Adoptium Temurin VDR', provenance['source'],
                          scores=scores, published=item.get('published'), modified=item.get('updated'),
                          package={'ecosystem': 'runtime', 'name': 'eclipse_adoptium:temurin', 'version': component['java']['version'], 'runtime_id': component['id']},
                          affected=[{'ranges': item.get('affects', []), 'fixed_versions': []}],
                          evidence=[{'runtime_component': copy.deepcopy(component), 'vendor_document': provenance,
                                     'vendor_affects': item.get('affects', []), 'advisory_source': item.get('source', {})}])
            row['runtime_match'] = {'component_id': component['id'], 'relation': 'inventory_match' if result is True else 'candidate',
                                    'basis': 'Adoptium VDR OpenJDK patch listing; build/OS exploitability not assessed', 'exploitability': 'not_assessed'}
            report['findings'].append(row)
        absent = (current and current[0] not in branches) or (args.cve and not examined)
        report['coverage'].append({'source': source, 'status': 'missing' if absent else 'uncertain' if unknown else 'ok', 'records_examined': examined,
            'vendor_document': provenance, 'receipts': client.receipts[start:],
            'reason': ('Requested Java major/CVE absent from this VDR; no negative exposure conclusion. ' if absent else '') + 'Adoptium VDR scope only. Older unlisted or unsupported versions remain candidates; no fixed release is inferred. The upstream generator derives per-major listings from OJVG tables.'})
    except (OSError, SourceError, ValueError, KeyError, TypeError) as exc:
        report['coverage'].append({'source': source, 'status': 'error', 'error': str(exc), 'receipts': client.receipts[start:]})
