#!/usr/bin/env python3
"""Offline privacy, coverage and protocol regressions for optional aggregation."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.parse
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'agent-security'))
from security.cli import main, output, parser, validate
from security.cvenow import BASE, discover, entry_row
from security.model import merge_findings, now
from security.sources import Client, NoRedirect, SourceError
from security.store import new_report, read_report


def entry(key='CVE-2026-10001'):
    return {'id': key, 'status': 'published', 'aliases': ['GHSA-AAAA-BBBB-CCCC'],
            'originalDescription': 'Original advisory description', 'title': 'Fixture title',
            'summary': {'text': 'Generated interpretation', 'model': 'fixture-model'},
            'publishedAt': '2026-10-01T00:00:00Z', 'modifiedAt': '2026-10-02T00:00:00Z',
            'severity': {'cvss': 8.1, 'vector': 'CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N', 'source': 'nvd'},
            'exploitation': {'kev': {'dateAdded': '2026-10-02'}, 'epssReached': {'date': '2026-10-01'}, 'exploitDb': None},
            'affected': [{'ecosystem': 'Maven', 'package': 'example:library', 'ranges': [{'introduced': '0', 'fixed': '2.0'}]},
                         {'vendor': 'Example', 'product': 'Library', 'ranges': [{'fixed': 'library*'}]}],
            'sources': [{'name': 'nvd', 'url': 'https://nvd.nist.gov/vuln/detail/' + key}],
            'references': [{'url': 'https://example.invalid/advisory'}]}


def health(ok=True):
    return {'polling': {'checkedAt': now(), 'sources': {'nvd': {'ok': ok}}},
            'history': {'source': 'fixture'}, 'backfill': {'state': 'complete'}}


class FakeClient:
    def __init__(self, *values):
        self.values = iter(values)
        self.urls, self.receipts = [], []

    def get(self, url):
        self.urls.append(url)
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        self.receipts.append({'url': url, 'fetched_at': now(), 'stale': False})
        return copy.deepcopy(value), {}


class CveNowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'AGENT_DO_HOME': self.temp.name,
                                          'GH_TOKEN': 'SECRET_GITHUB', 'NVD_API_KEY': 'SECRET_NVD'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def args(self, *argv):
        args = parser().parse_args(['find', '--source', 'cve-now', *argv])
        validate(args)
        return args

    def run_discovery(self, client, *argv):
        report = new_report('find', {})
        discover(self.args(*argv), client, report)
        return report

    def cli(self, client, *argv):
        output = io.StringIO()
        with patch('security.cli.Client', return_value=client), contextlib.redirect_stdout(output):
            code = main(['find', '--source', 'cve-now', *argv, '--json'])
        return code, json.loads(output.getvalue())

    def test_direct_lookup_preserves_provenance_dates_aliases_and_fixes(self):
        client = FakeClient(entry())
        code, report = self.cli(client, '--cve', 'cve-2026-10001', '--ecosystem', 'java', '--package', 'example:library', '--fix-available')
        self.assertEqual(code, 0)
        row = report['findings'][0]
        self.assertEqual(row['aliases'], ['CVE-2026-10001', 'GHSA-aaaa-bbbb-cccc'])
        self.assertEqual(row['cvss'], 8.1)
        self.assertEqual(row['summary'], 'Original advisory description')
        self.assertTrue(row['known_exploited'])
        self.assertEqual(row['affected'][0]['fixed_versions'], ['2.0'])
        self.assertEqual(row['affected'][1]['fixed_versions'], [])
        self.assertEqual(row['aggregator']['summary']['model'], 'fixture-model')
        self.assertEqual(row['evidence'][0]['record'], entry())
        self.assertEqual(client.urls, [BASE + '/api/v1/entries/CVE-2026-10001'])
        self.assertEqual(read_report(report['saved_report'])['findings'], report['findings'])

    def test_detail_dates_and_filters_are_local_not_inventory_uploads(self):
        client = FakeClient(entry())
        code, report = self.cli(client, '--cve', 'CVE-2026-10001', '--published-after', '2026-10-03')
        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['total'], 1)
        self.assertEqual(report['summary']['shown'], 0)
        self.assertNotIn('published', client.urls[0])

    def test_listing_hydrates_and_follows_opaque_cursor(self):
        other = entry('CVE-2026-10002');other['aliases'] = []
        client = FakeClient({'entries': [{'id': 'CVE-2026-10001'}], 'nextCursor': 'opaque/+?='}, entry(),
                            {'entries': [{'id': 'CVE-2026-10002'}], 'nextCursor': None}, other)
        r = self.run_discovery(client)
        self.assertEqual(r['coverage'][0]['status'], 'ok')
        self.assertEqual(r['coverage'][0]['records_examined'], 2)
        self.assertIn('cursor=opaque%2F%2B%3F%3D', client.urls[2])
        self.assertEqual(len(r['findings']), 2)

    def test_strict_cap_even_when_server_ignores_requested_page_size(self):
        client = FakeClient({'entries': [{'id': 'CVE-2026-10001'}, {'id': 'CVE-2026-10002'}], 'nextCursor': None}, entry())
        code, r = self.cli(client, '--limit', '1')
        self.assertEqual(code, 1)
        self.assertEqual(r['coverage'][0]['status'], 'truncated')
        self.assertEqual(r['coverage'][0]['records_examined'], 1)
        self.assertEqual(len(client.urls), 2)

    def test_repeated_cursor_and_empty_page_are_errors(self):
        for page in ({'entries': [], 'nextCursor': 'next'},
                     {'entries': [{'id': 'CVE-2026-10002'}], 'nextCursor': 'next'}):
            with self.subTest(page=page):
                c = FakeClient({'entries': [{'id': 'CVE-2026-10001'}], 'nextCursor': 'next'}, entry(), page)
                r = self.run_discovery(c)
                self.assertEqual(r['coverage'][0]['status'], 'error')
                self.assertIn('stalled', r['coverage'][0]['error'])
                self.assertEqual(len(r['findings']), 1)

    def test_duplicate_ids_do_not_consume_unbounded_pages(self):
        c = FakeClient({'entries': [{'id': 'CVE-2026-10001'}], 'nextCursor': 'a'}, entry(),
                       {'entries': [{'id': 'CVE-2026-10001'}], 'nextCursor': 'b'})
        r = self.run_discovery(c)
        self.assertIn('repeated', r['coverage'][0]['error'])
        self.assertEqual(len(c.urls), 3)

    def test_fetch_failure_keeps_partial_findings_and_saved_error(self):
        c = FakeClient({'entries': [{'id': 'CVE-2026-10001'}, {'id': 'CVE-2026-10002'}], 'nextCursor': None},
                       entry(), SourceError('advisory timeout'))
        code, r = self.cli(c)
        self.assertEqual(code, 1)
        self.assertEqual(len(r['findings']), 1)
        self.assertEqual(read_report(r['saved_report'])['coverage'][0]['error'], 'advisory timeout')

    def test_unknown_schema_and_wrong_identity_are_not_clean(self):
        for body in ({}, [], {'entries': [], 'nextCursor': []}, {'entries': [{'id': '../stack'}], 'nextCursor': None}):
            with self.subTest(body=body):
                code, r = self.cli(FakeClient(body))
                self.assertEqual(code, 1)
                self.assertEqual(r['coverage'][0]['status'], 'error')
        code, r = self.cli(FakeClient(entry('CVE-2026-10002')), '--cve', 'CVE-2026-10001')
        self.assertEqual(code, 1)
        self.assertEqual(r['findings'], [])

    def test_feed_scopes_are_always_limited_and_preserve_selection(self):
        c = FakeClient({'items': [{'id': 'CVE-2026-10001'}]}, entry())
        code, r = self.cli(c, '--technology', 'spring', '--ecosystem', 'maven', '--feed-filter', 'critical')
        self.assertEqual(code, 1)
        self.assertEqual(r['coverage'][0]['status'], 'limited')
        self.assertIn('not an exhaustive', r['coverage'][0]['reason'])
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(c.urls[0]).query),
                         {'format': ['json'], 'tech': ['spring'], 'ecosystem': ['maven'], 'filter': ['critical']})
        self.assertIn('not CVSS critical', r['notes'][0])

    def test_hex_ecosystem_matches_the_existing_erlang_filter(self):
        e = entry();e['affected'][0]['ecosystem'] = 'Hex'
        c = FakeClient({'items': [{'id': e['id']}]}, e)
        code, r = self.cli(c, '--ecosystem', 'erlang')
        self.assertEqual(code, 1)
        self.assertEqual(r['summary']['shown'], 1)
        self.assertIn('ecosystem=hex', c.urls[0])

    def test_status_success_does_not_mask_advisory_acquisition_failure(self):
        code, r = self.cli(FakeClient(SourceError('lookup failed'), health()),
                           '--cve', 'CVE-2026-10001', '--source-status')
        self.assertEqual(code, 1)
        self.assertEqual([x['status'] for x in r['coverage']], ['error', 'ok'])
        self.assertEqual(r['findings'], [])

    def test_empty_feed_does_not_claim_exhaustive_absence(self):
        code, r = self.cli(FakeClient({'items': []}), '--ecosystem', 'python')
        self.assertEqual(code, 1)
        self.assertEqual(r['coverage'][0]['status'], 'limited')

    def test_source_health_is_opt_in_and_separate_from_findings(self):
        c = FakeClient(entry(), health())
        code, r = self.cli(c, '--cve', 'CVE-2026-10001', '--source-status')
        self.assertEqual(code, 0)
        self.assertIn('history', r['source_status']['data'])
        self.assertEqual(c.urls[-1], BASE + '/api/v1/status')
        self.assertEqual(r['coverage'][-1]['status'], 'ok')

    def test_status_failure_or_unhealthy_polling_does_not_erase_findings(self):
        for status in (SourceError('status unavailable'), health(False), {}):
            with self.subTest(status=status):
                code, r = self.cli(FakeClient(entry(), status), '--cve', 'CVE-2026-10001', '--source-status')
                self.assertEqual(code, 1)
                self.assertEqual(len(r['findings']), 1)
                self.assertNotEqual(r['coverage'][-1]['status'], 'ok')

    def test_unknown_kev_is_not_false_and_epss_event_is_not_a_probability(self):
        e = entry();e['exploitation']['kev'] = None
        row = entry_row(e)
        self.assertIsNone(row['known_exploited'])
        self.assertEqual(row['aggregator']['exploitation']['epssReached'], {'date': '2026-10-01'})
        self.assertNotIn('epss', row)

    def test_rejected_entries_and_invalid_fields(self):
        for status in ('rejected', 'withdrawn', 'superseded'):
            e = entry();e['status'] = status
            self.assertIsNone(entry_row(e))
        for field, value in [('status', []), ('affected', {}), ('aliases', {}), ('publishedAt', 'bad-date'), ('severity', [])]:
            e = entry();e[field] = value
            with self.subTest(field=field), self.assertRaises(SourceError):
                entry_row(e)

    def test_alias_union_retains_source_conflicts_in_evidence(self):
        first, second = entry_row(entry()), entry_row(entry('CVE-2026-10002'))
        second['evidence'][0]['record']['severity']['cvss'] = 7.0
        rows = merge_findings([first, second])
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]['evidence']), 2)
        self.assertEqual(rows[0]['cvss'], 8.1)

    def test_invalid_or_cross_source_selectors_fail_before_network(self):
        invalid = [('--vendor', 'oracle'), ('--query', 'java'), ('--target', 'java'),
                   ('--technology', 'unknown-tech'), ('--ecosystem', 'swift'),
                   ('--cve', 'CVE-2026-10001', '--feed-filter', 'kev')]
        for options in invalid:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.args(*options)
        for option in (['--technology', 'spring'], ['--source-status'], ['--feed-filter', 'kev']):
            with self.assertRaises(ValueError):
                validate(parser().parse_args(['find', *option]))

    def test_explicit_nvd_discovery_never_contacts_cvenow(self):
        c = FakeClient({'vulnerabilities': [], 'totalResults': 0})
        out = io.StringIO()
        with patch('security.cli.Client', return_value=c), contextlib.redirect_stdout(out):
            self.assertEqual(main(['find', '--source', 'nvd', '--cve', 'CVE-2026-10001', '--json']), 0)
        self.assertEqual(urllib.parse.urlsplit(c.urls[0]).hostname, 'services.nvd.nist.gov')

    def auto_cli(self, client, *argv):
        output = io.StringIO()
        with patch('security.cli.Client', return_value=client), contextlib.redirect_stdout(output):
            code = main(['find', *argv, '--json'])
        return code, json.loads(output.getvalue())

    def test_auto_prefers_aggregator_when_direct_lookup_succeeds(self):
        c = FakeClient(entry())
        code, r = self.auto_cli(c, '--cve', 'CVE-2026-10001')
        self.assertEqual(code, 0)
        self.assertEqual(c.urls, [BASE + '/api/v1/entries/CVE-2026-10001'])
        self.assertEqual(r['target']['source'], 'cve-now')
        self.assertTrue(r['source_attempts'][0]['selected'])

    def test_auto_lookup_outage_falls_back_to_nvd_with_visible_attempt(self):
        c = FakeClient(SourceError('Advisory HTTP 503'), {'vulnerabilities': [], 'totalResults': 0})
        code, r = self.auto_cli(c, '--cve', 'CVE-2026-10001')
        self.assertEqual(code, 0)
        self.assertEqual(urllib.parse.urlsplit(c.urls[1]).hostname, 'services.nvd.nist.gov')
        self.assertIn('cveId=CVE-2026-10001', c.urls[1])
        self.assertEqual(r['target']['source'], 'nvd')
        self.assertEqual(r['source_attempts'][0]['coverage'][0]['error'], 'Advisory HTTP 503')
        self.assertFalse(r['source_attempts'][0]['selected'])
        self.assertEqual(r['coverage'][0]['source'], 'nvd')
        self.assertIn('cve.now failed', r['notes'][0])

    def test_auto_ecosystem_outage_preserves_github_query_and_filters(self):
        c = FakeClient(SourceError('offline'), [])
        code, r = self.auto_cli(c, '--ecosystem', 'python', '--package', 'example', '--published-after', '2026-10-01')
        self.assertEqual(code, 0)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(c.urls[1]).query)
        self.assertEqual(query['ecosystem'], ['pip'])
        self.assertEqual(query['affects'], ['example'])
        self.assertEqual(query['published'], ['2026-10-01..*'])
        self.assertEqual(r['target']['source'], 'github')

    def test_auto_healthy_limited_feed_does_not_become_complete_or_retry(self):
        c = FakeClient({'items': [{'id': 'CVE-2026-10001'}]}, entry())
        code, r = self.auto_cli(c, '--ecosystem', 'maven')
        self.assertEqual(code, 1)
        self.assertEqual(r['coverage'][0]['status'], 'limited')
        self.assertEqual(len(c.urls), 2)
        self.assertEqual(len(r['source_attempts']), 1)

    def test_auto_partial_aggregator_findings_survive_failed_fallback(self):
        c = FakeClient({'entries': [{'id': 'CVE-2026-10001'}, {'id': 'CVE-2026-10002'}], 'nextCursor': None},
                       entry(), SourceError('detail timeout'), SourceError('NVD timeout'))
        code, r = self.auto_cli(c)
        self.assertEqual(code, 1)
        self.assertEqual(len(r['findings']), 1)
        self.assertEqual(r['findings'][0]['discovery_attempt']['status'], 'unverified_preferred_source')
        self.assertEqual(r['coverage'][0]['error'], 'NVD timeout')
        self.assertEqual(len(read_report(r['saved_report'])['source_attempts']), 2)
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            output(r, False)
        self.assertIn('unverified partial cve.now', text.getvalue())

    def test_auto_fallback_keeps_partial_rows_and_alias_deduplicates(self):
        nvd = {'id': 'CVE-2026-10001', 'descriptions': [{'lang':'en','value':'NVD fixture'}],
               'published':'2026-10-01T00:00:00Z','configurations':[]}
        c = FakeClient({'entries': [{'id': 'CVE-2026-10001'}, {'id': 'CVE-2026-10002'}], 'nextCursor': None},
                       entry(), SourceError('detail timeout'), {'totalResults':1,'vulnerabilities':[{'cve':nvd}]})
        code, r = self.auto_cli(c)
        self.assertEqual(code, 0)
        self.assertEqual(len(r['findings']), 1)
        self.assertEqual({x['name'] for x in r['findings'][0]['sources']}, {'cve.now','NVD'})

    def test_auto_stale_attempt_does_not_contaminate_fresh_fallback_receipts(self):
        class StaleClient(FakeClient):
            def get(self, url):
                result = super().get(url)
                self.receipts[-1]['stale'] = url.startswith(BASE)
                return result
        c = StaleClient(entry(), {'vulnerabilities': [], 'totalResults': 0})
        code, r = self.auto_cli(c, '--cve','CVE-2026-10001','--allow-stale')
        self.assertEqual(code, 0)
        self.assertEqual(r['source_attempts'][0]['status'], 'stale')
        self.assertTrue(all(not x['stale'] for x in r['coverage'][0]['receipts']))

    def test_auto_fallback_truncation_still_returns_incomplete(self):
        nvd = {'id': 'CVE-2026-10001', 'descriptions': [{'lang':'en','value':'fixture'}], 'configurations':[]}
        c = FakeClient(SourceError('offline'), {'vulnerabilities': [{'cve':nvd}], 'totalResults': 2})
        code, r = self.auto_cli(c, '--limit','1')
        self.assertEqual(code, 1)
        self.assertEqual(r['coverage'][0]['status'], 'truncated')

    def test_auto_unsupported_aggregator_ecosystem_keeps_github_route(self):
        c = FakeClient([])
        code, r = self.auto_cli(c, '--ecosystem', 'swift')
        self.assertEqual(code, 0)
        self.assertEqual(urllib.parse.urlsplit(c.urls[0]).hostname, 'api.github.com')
        self.assertNotIn('source_attempts', r)

    def test_explicit_aggregator_outage_does_not_fall_back(self):
        c = FakeClient(SourceError('offline'))
        code, r = self.cli(c, '--cve','CVE-2026-10001')
        self.assertEqual(code,1)
        self.assertEqual(len(c.urls),1)
        self.assertEqual(r['coverage'][0]['source'],'cve.now')

    def test_auto_nvd_only_criteria_skip_aggregator(self):
        for options in (['--vendor','oracle'], ['--product','jdk'], ['--query','python interpreter']):
            with self.subTest(options=options):
                c = FakeClient({'vulnerabilities': [], 'totalResults': 0})
                code, r = self.auto_cli(c,*options)
                self.assertEqual(code,0)
                self.assertEqual(urllib.parse.urlsplit(c.urls[0]).hostname,'services.nvd.nist.gov')
                self.assertNotIn('source_attempts',r)

    def test_http_allowlist_blocks_upload_stack_mcp_arbitrary_hosts_and_queries(self):
        client = Client(self.args())
        for suffix in ['/stack', '/mcp', '/api/v1/upload', '/feed?format=json&p=private:package@1',
                       '/api/v1/entries?repository=secret', '/api/v1/entries/..%2Fstack',
                       '/api/v1/status?token=secret', '/api/v1/entries#stack']:
            with self.subTest(suffix=suffix), patch.object(client, 'open') as opener:
                with self.assertRaises(SourceError):client.get(BASE + suffix)
                opener.assert_not_called()
        with self.assertRaises(SourceError):client.get('https://cve.now.evil.invalid/api/v1/entries')

    def test_public_http_requests_are_get_only_and_never_forward_credentials(self):
        client = Client(self.args())
        response = io.BytesIO(json.dumps(entry()).encode());response.headers = {}
        with patch.object(client, 'open', return_value=response) as opener:
            client.get(BASE + '/api/v1/entries/CVE-2026-10001')
        request = opener.call_args.args[0]
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(request.data)
        self.assertNotIn('Authorization', request.headers)
        self.assertNotIn('Apikey', request.headers)
        self.assertNotIn('SECRET_', json.dumps(request.headers))
        self.assertNotIn('SECRET_', ''.join(p.read_text() for p in Path(self.temp.name).rglob('*.json')))
        with self.assertRaises(SourceError):NoRedirect().redirect_request(request, None, 302, '', {}, 'https://elsewhere.invalid')

    def test_cached_stale_data_and_byte_limits_keep_existing_http_contracts(self):
        args = self.args('--cache-ttl', '1', '--allow-stale')
        client = Client(args)
        response = io.BytesIO(json.dumps(entry()).encode());response.headers = {}
        with patch.object(client, 'open', return_value=response):client.get(BASE + '/api/v1/entries/CVE-2026-10001')
        with patch('security.sources.now', return_value='2099-01-01T00:00:00Z'), patch.object(client, 'open', side_effect=OSError('private error')):
            client.get(BASE + '/api/v1/entries/CVE-2026-10001')
        self.assertTrue(client.receipts[-1]['stale'])
        args = self.args('--max-bytes', '5')
        response = io.BytesIO(b'123456');response.headers = {}
        client = Client(args)
        with patch.object(client, 'open', return_value=response), self.assertRaises(SourceError):
            client.get(BASE + '/api/v1/entries/CVE-2026-10002')


if __name__ == '__main__':
    unittest.main()
