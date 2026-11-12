#!/usr/bin/env python3
"""Multi-target discovery: isolation, provenance, dates, deduplication, and caps."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/agent-security'))
from security.cli import main, parser
from security.model import finding, matches, merge_findings, present
from security.sources import Client, SourceError
from security.store import latest_report, new_report
from security.targets import PROFILES, canonical_target


class AdvisoryClient:
    def __init__(self, *, fail=None, total=1, stale=False):
        self.receipts, self.urls = [], []
        self.fail, self.total, self.stale = fail, total, stale

    def get(self, url):
        self.urls.append(url)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if self.fail and self.fail(url):
            raise SourceError('fixture source unavailable')
        self.receipts.append({'url': url, 'fetched_at': '2026-10-22T00:00:00Z', 'stale': self.stale})
        if 'cisa.gov' in url:
            return {'vulnerabilities': [{'cveID': 'CVE-2026-10001'}]}, {}
        if 'api.github.com' in url:
            name = query.get('affects', ['fixture'])[0]
            return [{'ghsa_id': 'GHSA-aaaa-bbbb-cccc', 'cve_id': 'CVE-2026-10001',
                     'summary': 'Shared fixture advisory', 'published_at': '2026-10-19T00:00:00Z',
                     'updated_at': '2026-10-20T00:00:00Z', 'cvss': {'score': 9.1},
                     'vulnerabilities': [{'package': {'name': name, 'ecosystem': query.get('ecosystem', ['npm'])[0]},
                                          'first_patched_version': '2.0', 'vulnerable_version_range': '< 2.0'}]}], {}
        return {'totalResults': self.total, 'vulnerabilities': [{'cve': {
            'id': 'CVE-2026-10001', 'published': '2026-10-18T00:00:00Z', 'lastModified': '2026-10-20T00:00:00Z',
            'metrics': {'cvssMetricV31': [{'source': 'NVD', 'cvssData': {'version': '3.1', 'baseScore': 8.2}}]},
            'descriptions': [{'lang': 'en', 'value': 'Shared fixture advisory'}]}}]}, {}


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.env = patch.dict(os.environ, {'AGENT_DO_HOME': str(self.root / 'state')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temporary.cleanup()

    def cli(self, *argv, client=None):
        stream = io.StringIO()
        with patch('security.cli.Client', return_value=client or AdvisoryClient()), contextlib.redirect_stdout(stream):
            code = main([*argv, '--json'])
        return code, json.loads(stream.getvalue())

    def test_all_five_targets_union_deduplicate_and_preserve_match_reasons(self):
        client = AdvisoryClient()
        code, report = self.cli('find', '--target', 'java', '--target', 'spring-boot', '--target', 'angular',
                                '--target', 'nodejs', '--target', 'aks', client=client)
        self.assertEqual(code, 0, report)
        self.assertEqual(report['summary']['total'], 1)
        self.assertEqual(set(report['findings'][0]['matched_targets']), set(PROFILES))
        query_count = sum(len(profile['queries']) for profile in PROFILES.values())
        self.assertEqual(len(client.urls), query_count)
        self.assertEqual(len(report['coverage']), query_count)
        self.assertEqual(len(report['findings'][0]['target_matches']), query_count)
        self.assertEqual(report['findings'][0]['cvss'], 9.1)
        self.assertEqual(len(report['target_summaries']), 5)
        self.assertNotIn('summary', latest_report())
        self.assertEqual(len(latest_report()['findings']), 1)

    def test_known_source_criteria_are_explicit(self):
        client = AdvisoryClient()
        _, report = self.cli('find', '--target', 'java', '--target', 'spring-boot', '--target', 'angular',
                              '--target', 'nodejs', '--target', 'aks', client=client)
        queries = [urllib.parse.parse_qs(urllib.parse.urlsplit(url).query) for url in client.urls]
        self.assertTrue(any(q.get('affects') == ['org.springframework.boot:spring-boot'] and q.get('ecosystem') == ['maven'] for q in queries))
        self.assertTrue(any(q.get('affects') == ['@angular/core'] and q.get('ecosystem') == ['npm'] for q in queries))
        self.assertTrue(any('nodejs:node.js' in q.get('virtualMatchString', [''])[0] for q in queries))
        self.assertTrue(any('oracle:java_se' in q.get('virtualMatchString', [''])[0] for q in queries))
        self.assertTrue(any('microsoft:azure_kubernetes_service' in q.get('virtualMatchString', [''])[0] for q in queries))
        self.assertTrue(any('kubernetes:kubernetes' in q.get('virtualMatchString', [''])[0] for q in queries))
        aks_matches = [x for x in report['findings'][0]['target_matches'] if x['target'] == 'aks']
        self.assertIn('upstream_dependency_candidate', {x['relation'] for x in aks_matches})
        self.assertEqual(report['findings'][0]['exploitability'], 'not_assessed')

    def test_aliases_and_repeated_targets_do_not_repeat_queries(self):
        client = AdvisoryClient()
        code, report = self.cli('find', '--target', 'node', '--target', 'nodejs', '--target', 'NODE', client=client)
        self.assertEqual(code, 0)
        self.assertEqual(report['target']['targets'], ['nodejs'])
        self.assertEqual(len(client.urls), len(PROFILES['nodejs']['queries']))
        self.assertEqual(canonical_target('springboot'), 'spring-boot')

    def test_failure_does_not_stop_other_queries_or_targets(self):
        client = AdvisoryClient(fail=lambda url: 'api.github.com' in url)
        code, report = self.cli('find', '--target', 'angular', '--target', 'java', client=client)
        self.assertEqual(code, 1)
        summaries = {row['target']: row for row in report['target_summaries']}
        self.assertEqual(summaries['angular']['status'], 'incomplete')
        self.assertEqual(summaries['angular']['total'], 0)
        self.assertEqual(summaries['java']['status'], 'complete')
        self.assertEqual(summaries['java']['total'], 1)
        self.assertEqual(report['findings'][0]['matched_targets'], ['java'])

    def test_partial_page_failure_retains_rows_and_provenance(self):
        client = AdvisoryClient(total=2)
        original = client.get
        def get(url):
            if 'startIndex=1' in url:
                raise SourceError('page two failed')
            return original(url)
        client.get = get
        code, report = self.cli('find', '--target', 'nodejs', client=client)
        self.assertEqual(code, 1)
        self.assertEqual(report['summary']['total'], 1)
        self.assertTrue(all(row['status']=='error' for row in report['coverage']))
        self.assertEqual(len(report['findings'][0]['target_matches']), 2)

    def test_limit_and_truncation_are_per_component_query(self):
        client = AdvisoryClient(total=5)
        code, report = self.cli('find','--target','java','--target','nodejs','--limit','1',client=client)
        self.assertEqual(code, 1)
        self.assertTrue(all(row['limit']==1 and row['truncated'] is True for row in report['coverage']))
        self.assertEqual(len(client.urls), len(PROFILES['java']['queries']) + len(PROFILES['nodejs']['queries']))

    def test_query_receipts_do_not_include_other_targets(self):
        client = AdvisoryClient()
        _, report = self.cli('find','--target','java','--target','nodejs',client=client)
        for row in report['coverage']:
            self.assertEqual(len(row['receipts']), 1)
        self.assertEqual(len({row['receipts'][0]['url'] for row in report['coverage']}), len(report['coverage']))

    def test_shared_filters_saved_evidence_and_report_refilter(self):
        code, report = self.cli('find','--target','java','--target','angular','--cvss-gt','9.5')
        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['shown'], 0)
        self.assertEqual(len(latest_report()['findings']), 1)
        code, report = self.cli('report','--latest','--target','angular','--cvss-min','9')
        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['shown'], 1)
        self.assertEqual(report['filters']['targets'], ['angular'])

    def test_report_refuses_unsearched_targets_and_legacy_reports(self):
        self.cli('find','--target','java')
        code, report = self.cli('report','--target','aks')
        self.assertEqual(code, 2)
        self.assertIn('not searched', report['error'])
        self.cli('find','--product','jdk')
        code, _ = self.cli('report','--target','java')
        self.assertEqual(code, 2)

    def test_saved_target_filter_does_not_query_sources(self):
        self.cli('find','--target','java')
        client = AdvisoryClient()
        code, report = self.cli('report','--target','java',client=client)
        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['shown'], 1)
        self.assertFalse(client.urls)

    def test_successful_empty_queries_are_complete_zero_results(self):
        class EmptyClient(AdvisoryClient):
            def get(self, url):
                body, headers = super().get(url)
                if isinstance(body, list):
                    return [], headers
                return {'totalResults':0,'vulnerabilities':[]}, headers
        code, report = self.cli('find','--target','java','--target','angular',client=EmptyClient())
        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['total'], 0)
        self.assertTrue(all(item['status']=='complete' and item['total']==0 for item in report['target_summaries']))

    def test_incompatible_manual_selectors_fail_before_requests(self):
        for option in [('--vendor','oracle'),('--product','jdk'),('--query','java'),('--ecosystem','maven'),
                       ('--source','nvd'),('--ecosystem','maven','--package','x')]:
            client = AdvisoryClient()
            code, _ = self.cli('find','--target','java',*option,client=client)
            self.assertEqual(code, 2, option)
            self.assertFalse(client.urls)
        code, _ = self.cli('find','--target','unknown')
        self.assertEqual(code, 2)

    def test_stale_query_is_incomplete_and_summary_marks_it(self):
        code, report = self.cli('find','--target','nodejs',client=AdvisoryClient(stale=True))
        self.assertEqual(code, 1)
        self.assertEqual(report['target_summaries'][0]['status'], 'incomplete')
        self.assertEqual(report['target_summaries'][0]['query_statuses'], {'stale': 2})

    def test_stale_earlier_page_does_not_hide_a_later_query_error(self):
        client = AdvisoryClient(total=2, stale=True)
        original = client.get
        def get(url):
            if 'startIndex=1' in url:
                raise SourceError('later page failed')
            return original(url)
        client.get = get
        code, report = self.cli('find','--target','nodejs',client=client)
        self.assertEqual(code, 1)
        self.assertTrue(all(row['status']=='error' and row['stale'] is True for row in report['coverage']))
        self.assertEqual(report['target_summaries'][0]['query_statuses'], {'error':2})

    def test_kev_enrichment_runs_once_after_target_merge(self):
        client = AdvisoryClient()
        code, report = self.cli('find','--target','java','--target','angular','--known-exploited',client=client)
        self.assertEqual(code, 0)
        self.assertEqual(sum('cisa.gov' in url for url in client.urls), 1)
        self.assertTrue(report['findings'][0]['known_exploited'])
        self.assertEqual(set(report['findings'][0]['matched_targets']), {'java','angular'})

    def test_dates_are_source_specific_after_alias_merge(self):
        old = finding(['CVE-2026-10001'],'old','NVD','https://example.invalid/nvd',published='2026-01-01',modified='2026-10-20')
        recent = finding(['CVE-2026-10001','GHSA-aaaa-bbbb-cccc'],'new','GitHub','https://example.invalid/gh',published='2026-10-19',modified='2026-10-20')
        for row, target in ((old,'java'),(recent,'angular')):
            row['matched_targets'] = [target]
            row['target_matches'] = [{'target':target,'published':row['published'],'modified':row['modified']}]
        row = merge_findings([old,recent])[0]
        self.assertEqual(row['published'], '2026-01-01')
        self.assertTrue(matches(row,parser().parse_args(['report','--published-after','2026-10-01'])))
        self.assertFalse(matches(row,parser().parse_args(['report','--target','java','--published-after','2026-10-01'])))
        self.assertTrue(matches(row,parser().parse_args(['report','--target','angular','--published-after','2026-10-01'])))
        report = new_report('find', {'kind':'multi_advisory_query','targets':['java','angular']})
        report['findings'] = [row]
        report['coverage'] = [{'target':name,'source':'fixture','status':'ok'} for name in ('java','angular')]
        shown = present(report,parser().parse_args(['report','--published-after','2026-10-01']))
        counts = {item['target']:item['shown'] for item in shown['target_summaries']}
        self.assertEqual(counts, {'java':0,'angular':1})

    def test_date_constraints_must_match_one_source_event(self):
        a = finding(['CVE-2026-10001'],'a','NVD','https://example.invalid/a',published='2026-10-19',modified='2026-10-19')
        b = finding(['CVE-2026-10001'],'b','GH','https://example.invalid/b',published='2026-01-01',modified='2026-10-22')
        row = merge_findings([a,b])[0]
        args = parser().parse_args(['report','--published-after','2026-10-01','--updated-after','2026-10-21'])
        self.assertFalse(matches(row,args))

    def test_nvd_pacing_shares_successful_transport_and_skips_cache(self):
        args = parser().parse_args(['find'])
        class Response(io.BytesIO):
            headers = {}
        with patch.dict(os.environ,{'NVD_API_KEY':''}), patch('security.sources.time.monotonic',return_value=100.0), patch('security.sources.time.sleep') as sleep:
            client = Client(args)
            client.open = lambda *a,**k: Response(b'{"vulnerabilities":[],"totalResults":0}')
            client.get('https://services.nvd.nist.gov/rest/json/cves/2.0?fixture=1')
            client.get('https://services.nvd.nist.gov/rest/json/cves/2.0?fixture=2')
            sleep.assert_called_once_with(6.0)
            client.get('https://services.nvd.nist.gov/rest/json/cves/2.0?fixture=2')
            self.assertEqual(sleep.call_count, 1)

    def test_nvd_api_key_uses_keyed_pacing(self):
        args = parser().parse_args(['find'])
        class Response(io.BytesIO):
            headers = {}
        with patch.dict(os.environ,{'NVD_API_KEY':'fixture-not-a-real-key'}), patch('security.sources.time.monotonic',return_value=100.0), patch('security.sources.time.sleep') as sleep:
            client = Client(args)
            client.open = lambda *a,**k: Response(b'{"vulnerabilities":[],"totalResults":0}')
            client.get('https://services.nvd.nist.gov/rest/json/cves/2.0?fixture=1')
            client.get('https://services.nvd.nist.gov/rest/json/cves/2.0?fixture=2')
            sleep.assert_called_once_with(0.6)


if __name__ == '__main__':
    unittest.main()
