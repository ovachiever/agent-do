#!/usr/bin/env python3
"""Offline contract tests for vulnerability evidence and false-clean regressions."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "agent-security"))
from security.cli import main, parser
from security.model import cvss_scores, finding, matches, merge_findings, present
from security.scan import acquire, assess_inventory, dependabot, run as run_process
from security.sources import Client, SourceError, discover, enrich_kev, nvd_row
from security.store import finish, latest_report, new_report, read_report

# Exact OSV 2.7.0 diagnostic captured during laptop testing (not a synthetic
# approximation containing just the words "source" and "warning").
OSV_SOURCE_NOTICE = (
    'Warning: `source` exists as both a subcommand of OSV-Scanner and as a file on the filesystem. '
    '`source` is assumed to be a subcommand here. If you intended for `source` to be an argument '
    'to `source`, you must specify `source source` in your command line.'
)


def advisory(identifier="CVE-2026-10001", score=7.0, version="1.0"):
    return finding([identifier], "A fixture vulnerability", "fixture", "https://example.invalid/advisory",
                   scores=[{"score": score, "version": "3.1", "vector": None, "source": "fixture"}] if score is not None else [],
                   published="2026-10-01T00:00:00Z", modified="2026-10-03T00:00:00Z",
                   package={"name": "fixture", "ecosystem": "PyPI", "version": version})


class FakeClient:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.receipts = []
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        self.receipts.append({"url": url, "fetched_at": "2026-10-22T00:00:00Z", "stale": False})
        value = next(self.pages)
        if isinstance(value, Exception):
            raise value
        return value


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.env = patch.dict(os.environ, {"AGENT_DO_HOME": str(self.root / "state")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temporary.cleanup()

    def args(self, *argv):
        return parser().parse_args(argv)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, json.loads(out.getvalue())

    def test_dispatch_does_not_hide_programming_errors(self):
        cases = [
            ('security.cli.discover', ['find', '--source', 'nvd', '--vendor', 'oracle', '--product', 'jdk']),
            ('security.cli.assess_runtime', ['runtime', '--local-java', '--inventory-only']),
        ]
        for target, argv in cases:
            for error in (KeyError, TypeError):
                with self.subTest(target=target, error=error.__name__):
                    with patch(target, side_effect=error('internal defect')):
                        with self.assertRaises(error):
                            self.cli(*argv, '--json')

    def test_dispatch_keeps_expected_failures_as_incomplete_reports(self):
        cases = [
            ('security.cli.discover', ['find', '--source', 'nvd', '--vendor', 'oracle', '--product', 'jdk']),
            ('security.cli.assess_runtime', ['runtime', '--local-java', '--inventory-only']),
        ]
        for target, argv in cases:
            for error in (SourceError, OSError, ValueError):
                with self.subTest(target=target, error=error.__name__):
                    with patch(target, side_effect=error('expected failure')):
                        code, payload = self.cli(*argv, '--json')
                    self.assertEqual(code, 1)
                    self.assertEqual(payload['status'], 'incomplete')
                    self.assertEqual(payload['coverage'][-1]['error'], 'expected failure')

    def test_score_boundaries_and_unscored(self):
        row = advisory()
        self.assertTrue(matches(row, self.args("report", "--cvss-min", "7")))
        self.assertFalse(matches(row, self.args("report", "--cvss-gt", "7")))
        self.assertFalse(matches(advisory(score=None), self.args("report", "--cvss-min", "7")))
        self.assertTrue(matches(advisory(score=None), self.args("report", "--cvss-min", "7", "--include-unscored")))
        report = new_report("scan", {})
        report["findings"] = [row, advisory(score=None)]
        view = present(report, self.args("report", "--cvss-gt", "7"))
        self.assertEqual(view["summary"], {"total": 2, "shown": 0, "excluded": 2, "unscored": 1})
        self.assertEqual(len(report["findings"]), 2)

    def test_numeric_score_survives_missing_vector_library(self):
        with patch.dict(sys.modules, {"cvss": None}):
            scores = cvss_scores([{"score": 8.1, "vector_string": "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N"}], "GitHub")
        self.assertEqual(scores[0]["score"], 8.1)
        self.assertEqual(scores[0]["version"], "3.1")

    def test_dates_and_alias_filter(self):
        row = advisory()
        self.assertTrue(matches(row, self.args("report", "--published-after", "2026-10-01")))
        self.assertFalse(matches(row, self.args("report", "--published-before", "2026-10-01")))
        self.assertTrue(matches(row, self.args("report", "--updated-after", "2026-10-02")))
        row["aliases"].append("CVE-2026-12345")
        self.assertTrue(matches(row, self.args("report", "--cve", "CVE-2026-12345")))

    def test_php_ecosystem_aliases_and_fix_filter(self):
        row = advisory()
        row["package"]["ecosystem"] = "Packagist"
        self.assertTrue(matches(row, self.args("report", "--ecosystem", "composer")))
        self.assertFalse(matches(row, self.args("report", "--fix-available")))
        row["affected"] = [{"fixed_versions": ["2.0"]}]
        self.assertTrue(matches(row, self.args("report", "--fix-available")))

    def test_fix_filter_does_not_borrow_another_packages_fix(self):
        row = advisory()
        row["package"] = None
        row["affected"] = [{"package": {"name": "a", "ecosystem": "pip"}, "fixed_versions": []},
                           {"package": {"name": "b", "ecosystem": "pip"}, "fixed_versions": ["2.0"]}]
        self.assertFalse(matches(row, self.args("report", "--package", "a", "--fix-available")))
        self.assertTrue(matches(row, self.args("report", "--package", "b", "--fix-available")))
        row['package'] = {'name': 'a', 'ecosystem': 'pip', 'version': '1.0'}
        self.assertFalse(matches(row, self.args('report', '--package', 'a', '--fix-available')))

    def test_combined_fix_filters_fall_back_to_finding_package(self):
        row = advisory()
        row['package'] = {'name': 'debian:libssl', 'ecosystem': 'runtime', 'version': '1.2'}
        row['affected'] = [{'fixed_versions': ['1.2+deb12u1']}]
        for flags in (['--package', 'debian:libssl'], ['--fix-available'], ['--package', 'debian:libssl', '--fix-available']):
            self.assertTrue(matches(row, self.args('report', *flags)))
        row['package'] = {'name': 'vendor/package', 'ecosystem': 'Packagist', 'version': '1.0'}
        self.assertTrue(matches(row, self.args('report', '--package', 'vendor/package', '--ecosystem', 'composer', '--fix-available')))
        row['affected'][0]['fixed_versions'] = []
        self.assertFalse(matches(row, self.args('report', '--package', 'vendor/package', '--fix-available')))

    def test_subprocess_preserves_each_stream_at_limit_and_nonzero_status(self):
        args = self.args('scan', '--path', str(self.root), '--max-bytes', '1024')
        result = run_process([sys.executable, '-c', "import os,sys;os.write(1,b'x'*1024);os.write(2,b'y'*1024);sys.exit(7)"], args)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, b'x' * 1024)
        self.assertEqual(result.stderr, b'y' * 1024)

    def test_subprocess_stops_oversized_stdout_or_stderr_before_completion(self):
        args = self.args('scan', '--path', str(self.root), '--max-bytes', '1024')
        for stream in (1, 2):
            marker = self.root / ('completed-' + str(stream))
            script = 'import os,sys,time;from pathlib import Path;os.write(' + str(stream) + ",b'x'*2048);time.sleep(.3);Path(sys.argv[1]).write_text('completed')"
            with self.subTest(stream=stream), self.assertRaisesRegex(ValueError, 'output exceeds --max-bytes'):
                run_process([sys.executable, '-c', script, str(marker)], args)
            self.assertFalse(marker.exists(), 'The producer completed before its output limit was enforced')

    @unittest.skipUnless(hasattr(os, 'fork'), 'POSIX process groups required')
    def test_subprocess_timeout_kills_children_holding_output_pipes(self):
        args = self.args('scan', '--path', str(self.root), '--scan-timeout', '.5')
        marker, ready = self.root / 'child-completed', self.root / 'child-started'
        script = ('import os,sys,time\nfrom pathlib import Path\n'
                  'if os.fork()==0:\n'
                  ' Path(sys.argv[2]).write_text("started")\n'
                  ' time.sleep(.8)\n'
                  ' Path(sys.argv[1]).write_text("completed")\n'
                  ' os._exit(0)\n'
                  'os._exit(0)\n')
        with self.assertRaisesRegex(ValueError, 'timed out'):
            run_process([sys.executable, '-c', script, str(marker), str(ready)], args)
        self.assertTrue(ready.exists(), 'Child did not start; timeout cleanup was not exercised')
        time.sleep(.4)
        self.assertFalse(marker.exists(), 'The descendant survived the command timeout')

    def test_alias_union_preserves_versions_and_occurrences(self):
        a = advisory("GHSA-aaaa-bbbb-cccc")
        b = advisory()
        bridge = copy.deepcopy(a)
        bridge["aliases"] += b["aliases"]
        b["evidence"] = [{"path": "sub/requirements.txt"}]
        c = advisory(version="2.0")
        rows = merge_findings([a, b, bridge, c])
        self.assertEqual(len(rows), 2)
        same = next(x for x in rows if x["package"]["version"] == "1.0")
        self.assertEqual(same["id"], "CVE-2026-10001")
        self.assertIn({"path": "sub/requirements.txt"}, same["evidence"])

    def test_nvd_scoring_and_cpe(self):
        row = nvd_row({"id": "CVE-2026-10001", "descriptions": [{"lang": "en", "value": "test"}],
                       "metrics": {"cvssMetricV31": [{"source": "nvd@nist.gov", "cvssData": {"version": "3.1", "baseScore": 9.8}}]},
                       "configurations": [{"nodes": [{"cpeMatch": [{"criteria": "cpe:2.3:a:oracle:jdk:*:*:*:*:*:*:*:*", "vulnerable": True}]}]}]})
        self.assertEqual(row["cvss"], 9.8)
        self.assertEqual(row["severity"], "critical")
        self.assertEqual(len(row["affected"]), 1)

    def test_nvd_pagination_and_truncation(self):
        def cve(i):
            return {"cve": {"id": "CVE-2026-" + str(10000+i)}}
        client = FakeClient([({"vulnerabilities": [cve(1), cve(2)], "totalResults": 3}, {}),
                             ({"vulnerabilities": [cve(3)], "totalResults": 3}, {})])
        report = new_report("find", {})
        discover(self.args("find", "--vendor", "oracle", "--limit", "4"), client, report)
        self.assertEqual(len(report["findings"]), 3)
        self.assertIn("startIndex=2", client.urls[1])
        self.assertEqual(report["coverage"][0]["status"], "ok")
        client = FakeClient([({"vulnerabilities": [cve(1), cve(2)], "totalResults": 3}, {})])
        report = new_report("find", {})
        discover(self.args("find", "--limit", "2"), client, report)
        self.assertTrue(report["coverage"][0]["truncated"])

    def test_partial_page_failure_retains_findings(self):
        client = FakeClient([({"vulnerabilities": [{"cve": {"id": "CVE-2026-10001"}}], "totalResults": 2}, {}), SourceError("rate limit")])
        report = new_report("find", {})
        with self.assertRaises(SourceError):
            discover(self.args("find"), client, report)
        self.assertEqual(len(report["findings"]), 1)

    def test_github_pagination_and_package_identity(self):
        row = {"ghsa_id": "GHSA-aaaa-bbbb-cccc", "cve_id": "CVE-2026-10001", "severity": "high",
               "vulnerabilities": [{"package": {"ecosystem": "pip", "name": "litellm"}, "first_patched_version": "2.0", "vulnerable_version_range": "< 2.0"}]}
        client = FakeClient([([row], {"link": '<next>; rel="next"'}), ([], {})])
        report = new_report("find", {})
        discover(self.args("find", "--ecosystem", "pypi", "--package", "litellm"), client, report)
        self.assertIn("ecosystem=pip", client.urls[0])
        self.assertIn("page=2", client.urls[1])
        self.assertEqual(report["findings"][0]["affected"][0]["fixed_versions"], ["2.0"])

    def test_kev_unknown_failure_and_membership(self):
        report = new_report("scan", {})
        report["findings"] = [advisory(), advisory("CVE-2026-20002")]
        enrich_kev(FakeClient([SourceError("offline")]), report)
        self.assertIsNone(report["findings"][0]["known_exploited"])
        enrich_kev(FakeClient([({"vulnerabilities": [{"cveID": "CVE-2026-10001"}]}, {})]), report)
        self.assertTrue(report["findings"][0]["known_exploited"])
        self.assertFalse(report["findings"][1]["known_exploited"])

    def test_cache_refresh_stale_and_rate_limit(self):
        args = self.args("find", "--retries", "0")
        client = Client(args)
        class Response(io.BytesIO):
            headers = {}
        client.open = lambda *a, **k: Response(b'{"vulnerabilities": []}')
        url = "https://api.github.com/advisories?fixture=cache"
        client.get(url)
        client.open = lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("offline"))
        client.get(url)
        self.assertTrue(client.receipts[-1]["cache"])
        args.refresh = True
        with self.assertRaises(SourceError):
            client.get(url)
        args.allow_stale = True
        client.get(url)
        self.assertTrue(client.receipts[-1]["stale"])
        args.allow_stale = False
        args.retries = 1
        client.open = lambda *a, **k: (_ for _ in ()).throw(urllib.error.HTTPError(url, 429, "limit", {"Retry-After": "60"}, None))
        with self.assertRaisesRegex(SourceError, "Retry-After"):
            client.get(url)

    def test_http_size_bound_and_endpoint_validation(self):
        args = self.args("find", "--max-bytes", "2")
        client = Client(args)
        class Response(io.BytesIO):
            headers = {}
        client.open = lambda *a, **k: Response(b'{}x')
        with self.assertRaises(SourceError):
            client.get("https://api.github.com/advisories")
        with self.assertRaises(SourceError):
            client.get("https://attacker.invalid/advisories")

    def test_local_manifest_snapshot_unresolved_and_symlinks(self):
        target = self.root / "repo"
        target.mkdir()
        (target / "requirements.txt").write_text("litellm>=1\n")
        (target / "package.json").write_text('{"scripts":{"install":"touch PWNED"}}')
        outside = self.root / "private"
        outside.write_text("secret")
        (target / "composer.lock").symlink_to(outside)
        stage = self.root / "stage"
        stage.mkdir()
        report = new_report("scan", {})
        entries = acquire(self.args("scan", "--path", str(target)), report, stage)
        assess_inventory(entries, stage, report)
        self.assertFalse((stage / "composer.lock").exists())
        self.assertFalse((target / "PWNED").exists())
        self.assertTrue(any(x["status"] == "unresolved" for x in report["coverage"]))
        self.assertTrue(any(x["status"] == "unsupported" for x in report["coverage"]))
        self.assertIsNotNone(report["target"]["inventory_sha256"])

    def scanner(self, exit_code=1):
        script = self.root / "osv-scanner"
        script.write_text('''#!/usr/bin/env python3
import json, sys
from pathlib import Path
if '--version' in sys.argv:
    print('osv-scanner version: 2.7.0')
    raise SystemExit(0)
stage = Path(sys.argv[-1])
assert stage.name != 'source'
assert not (Path.cwd() / 'source').exists(), 'staging must not collide with OSV subcommands'
assert '--all-packages' in sys.argv
assert '--verbosity=warn' in sys.argv
assert not list(stage.rglob('osv-scanner.toml'))
results=[]
for filename, name, eco in [('package-lock.json','example-npm','npm'),('composer.lock','example/php','Packagist'),('requirements.txt','example-python','PyPI'),('gradle.lockfile','org.example:java','Maven')]:
    for path in stage.rglob(filename):
        results.append({'source': {'path': str(path), 'type':'lockfile'}, 'packages': [{'package':{'name':name,'version':'1.0','ecosystem':eco}, 'vulnerabilities':[{'id':'CVE-2026-10001','summary':'Fixture advisory','published':'2026-10-01T00:00:00Z','affected':[{'package':{'name':name,'ecosystem':eco},'ranges':[{'type':'ECOSYSTEM','events':[{'introduced':'0'},{'fixed':'2.0'}]}]}]}]}]})
print(json.dumps({'results':results}))
raise SystemExit(EXIT_CODE)
'''.replace("EXIT_CODE", str(exit_code)))
        script.chmod(0o755)
        return script

    def test_cli_scan_four_ecosystems_and_saved_refilter(self):
        target = self.root / "repo"
        target.mkdir()
        for filename, content in (("package-lock.json", '{}'), ("composer.lock", '{}'), ("requirements.txt", 'example-python==1.0\n'), ("gradle.lockfile", 'org.example:java:1.0=runtimeClasspath\n')):
            (target / filename).write_text(content)
        (target / "osv-scanner.toml").write_text('[[IgnoredVulns]]\nid="CVE-2026-10001"\n')
        before = {p.name: p.read_bytes() for p in target.iterdir()}
        code, data = self.cli("scan", "--path", str(target), "--scanner", str(self.scanner()), "--json")
        self.assertEqual(code, 0, data)
        self.assertEqual(data["summary"]["total"], 4)
        self.assertEqual(len(data["packages"]), 4)
        self.assertTrue(all(x["affected"][0]["fixed_versions"] == ["2.0"] for x in data["findings"]))
        self.assertEqual(before, {p.name: p.read_bytes() for p in target.iterdir()})
        saved = read_report(data["saved_report"])
        code, view = self.cli("report", "--latest", "--cvss-min", "7", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(view["summary"]["shown"], 0)
        self.assertEqual(len(saved["findings"]), 4)
        code, view = self.cli("report", "--latest", "--cvss-min", "7", "--include-unscored", "--json")
        self.assertEqual(view["summary"]["shown"], 4)
        self.assertEqual(os.stat(data["saved_report"]).st_mode & 0o777, 0o600)

    def test_failed_scanner_and_missing_scanner_never_report_clean(self):
        target = self.root / "repo"
        target.mkdir()
        (target / "package-lock.json").write_text('{}')
        for scanner in (str(self.root / "absent"), str(self.scanner(exit_code=128))):
            code, data = self.cli("scan", "--path", str(target), "--scanner", scanner, "--json")
            self.assertEqual(code, 1)
            self.assertEqual(data["status"], "incomplete")
            self.assertEqual(latest_report()["status"], "incomplete")

    def test_unknown_upstream_freshness_and_unscored_vectors_alone_are_not_warnings(self):
        target = self.root / 'freshness-project'
        target.mkdir()
        (target / 'requirements.txt').write_text('example-python==1.0\n')
        code, report = self.cli('scan', '--path', str(target), '--scanner', str(self.scanner()), '--json')
        self.assertEqual(code, 0)
        coverage = next(item for item in report['coverage'] if item['source'] == 'OSV-Scanner')
        self.assertEqual(coverage['status'], 'ok')
        self.assertFalse(coverage['warnings'])
        self.assertIn('publication time unavailable', coverage['advisory_data_freshness'])
        self.assertEqual(report['summary']['unscored'], 1)

    def test_scanner_warning_reason_explains_detection_without_leaking_diagnostics(self):
        target = self.root / 'warning-project'
        target.mkdir()
        (target / 'requirements.txt').write_text('example-python==1.0\n')
        scanner = self.scanner()
        scanner.write_text(scanner.read_text().replace('import json, sys', "import json, sys\nprint('WARNING private diagnostic SECRET', file=sys.stderr)"))
        code, report = self.cli('scan', '--path', str(target), '--scanner', str(scanner), '--json')
        self.assertEqual(code, 1)
        coverage = next(item for item in report['coverage'] if item['source'] == 'OSV-Scanner')
        self.assertEqual(coverage['status'], 'warning')
        self.assertEqual(coverage['diagnostic_detection'], 'unclassified_stderr_after_known_notices')
        self.assertIn('--verbosity=warn', coverage['reason'])
        self.assertEqual(coverage['diagnostic_lines'], 1)
        self.assertEqual(len(coverage['stderr_sha256']), 64)
        self.assertNotIn('SECRET', json.dumps(report))

    def test_info_logs_containing_warning_words_are_suppressed_by_scanner_verbosity(self):
        target = self.root / 'info-project'
        target.mkdir()
        (target / 'requirements.txt').write_text('example-python==1.0\n')
        scanner = self.scanner()
        # Emulate OSV's native level filtering: INFO has no prefix in JSON mode.
        scanner.write_text(scanner.read_text().replace('import json, sys', "import json, sys\nif '--verbosity=warn' not in sys.argv:\n    print('INFO: 0 error records; failed lookups: 0; warning summary', file=sys.stderr)"))
        code, report = self.cli('scan', '--path', str(target), '--scanner', str(scanner), '--json')
        self.assertEqual(code, 0)
        self.assertEqual(report['scanner']['verbosity'], 'warn')
        self.assertEqual(report['coverage'][-1]['status'], 'ok')
        # The same scan can now be selected as complete.
        code, selected = self.cli('report', '--latest-complete', '--json')
        self.assertEqual(code, 0)
        self.assertEqual(selected['report_id'], report['report_id'])

    def test_diagnostic_without_warning_keywords_still_marks_coverage_incomplete(self):
        target = self.root / 'skipped-project'
        target.mkdir()
        (target / 'requirements.txt').write_text('example-python==1.0\n')
        scanner = self.scanner()
        scanner.write_text(scanner.read_text().replace('import json, sys', "import json, sys\nprint('Skipping some package lookups', file=sys.stderr)"))
        code, report = self.cli('scan', '--path', str(target), '--scanner', str(scanner), '--json')
        self.assertEqual(code, 1)
        self.assertTrue(any(item['status'] == 'warning' for item in report['coverage']))
        self.assertEqual(report['summary']['total'], 1)

    def test_diagnostic_capture_is_opt_in_private_and_does_not_overwrite_prior_logs(self):
        target = self.root / 'diagnostic-project'
        target.mkdir()
        (target / 'requirements.txt').write_text('example-python==1.0\n')
        scanner = self.scanner()
        scanner.write_text(scanner.read_text().replace('import json, sys', "import json, sys\nprint('PRIVATE_SCANNER_MESSAGE', file=sys.stderr)"))
        directory = self.root / 'private diagnostics'
        for index in range(2):
            code, report = self.cli('scan', '--path', str(target), '--scanner', str(scanner),
                '--scanner-diagnostics', str(directory), '--json')
            self.assertEqual(code, 1)
            metadata = report['scanner']['diagnostics']
            captured = Path(metadata['stderr_file'])
            self.assertEqual(captured.read_text(), 'PRIVATE_SCANNER_MESSAGE\n')
            self.assertEqual(captured.stat().st_mode & 0o777, 0o600)
            self.assertTrue(metadata['sensitive'])
            self.assertNotIn('PRIVATE_SCANNER_MESSAGE', json.dumps(report))
            self.assertEqual(len(list(directory.glob('*.log'))), index + 1)
            self.assertTrue(any(item.get('coverage_impact') == 'unclassified' for item in report['coverage']))
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        _, default = self.cli('scan', '--path', str(target), '--scanner', str(scanner), '--json')
        self.assertNotIn('diagnostics', default['scanner'])
        self.assertEqual(len(list(directory.glob('*.log'))), 2)

    def test_diagnostic_capture_preserves_nonzero_scanner_error_stderr(self):
        target = self.root / 'failed-project'
        target.mkdir()
        (target / 'requirements.txt').write_text('example-python==1.0\n')
        scanner = self.scanner(exit_code=128)
        scanner.write_text(scanner.read_text().replace('import json, sys', "import json, sys\nprint('PRIVATE_FAILURE_DETAILS', file=sys.stderr)"))
        code, report = self.cli('scan', '--path', str(target), '--scanner', str(scanner),
            '--scanner-diagnostics', str(self.root / 'diagnostics'), '--json')
        self.assertEqual(code, 1)
        self.assertEqual(Path(report['scanner']['diagnostics']['stderr_file']).read_text(), 'PRIVATE_FAILURE_DETAILS\n')
        self.assertNotIn('PRIVATE_FAILURE_DETAILS', json.dumps(report))

    def test_diagnostic_destination_cannot_be_an_existing_file(self):
        destination = self.root / 'do-not-overwrite.log'
        destination.write_text('existing')
        code, report = self.cli('scan', '--path', '.', '--scanner-diagnostics', str(destination), '--json')
        self.assertEqual(code, 2)
        self.assertEqual(destination.read_text(), 'existing')

    def test_verified_source_notice_is_non_blocking_and_latest_complete_selects_scan(self):
        target = self.root / 'source-notice-project'
        target.mkdir()
        (target / 'requirements.txt').write_text('example-python==1.0\n')
        for notice in [OSV_SOURCE_NOTICE, OSV_SOURCE_NOTICE.replace('on the filesystem.', 'on\n  the filesystem.')]:
            with self.subTest(notice=notice):
                scanner = self.scanner()
                scanner.write_text(scanner.read_text().replace('import json, sys', 'import json, sys\nprint(' + repr(notice) + ', file=sys.stderr)'))
                code, report = self.cli('scan', '--path', str(target), '--scanner', str(scanner),
                    '--scanner-diagnostics', str(self.root / 'diagnostics'), '--json')
                self.assertEqual(code, 0, report)
                self.assertEqual(report['summary']['total'], 1)
                coverage = next(item for item in report['coverage'] if item['source'] == 'OSV-Scanner')
                self.assertEqual(coverage['status'], 'ok')
                self.assertFalse(coverage['warnings'])
                self.assertEqual(coverage['non_blocking_diagnostics'][0]['code'], 'osv_source_subcommand_name_collision')
                self.assertEqual(coverage['coverage_impact'], 'none')
                self.assertEqual(Path(report['scanner']['diagnostics']['stderr_file']).read_text(), notice + '\n')
                code, selected = self.cli('report', '--latest-complete', '--json')
                self.assertEqual(code, 0)
                self.assertEqual(selected['report_id'], report['report_id'])

    def test_known_notice_does_not_hide_mixed_or_modified_diagnostics(self):
        target = self.root / 'mixed-notice-project'
        target.mkdir()
        (target / 'requirements.txt').write_text('example-python==1.0\n')
        for diagnostic in [OSV_SOURCE_NOTICE + '\nQuery failed: PRIVATE_LOOKUP',
                           'Query failed: PRIVATE_LOOKUP\n' + OSV_SOURCE_NOTICE,
                           OSV_SOURCE_NOTICE + ' Additional unclassified detail.',
                           OSV_SOURCE_NOTICE.replace('`source`', '`scan`')]:
            with self.subTest(diagnostic=diagnostic):
                scanner = self.scanner()
                scanner.write_text(scanner.read_text().replace('import json, sys', 'import json, sys\nprint(' + repr(diagnostic) + ', file=sys.stderr)'))
                code, report = self.cli('scan', '--path', str(target), '--scanner', str(scanner), '--json')
                self.assertEqual(code, 1)
                self.assertTrue(any(item['status'] == 'warning' for item in report['coverage']))
                self.assertNotIn('PRIVATE_LOOKUP', json.dumps(report))

    def test_recognized_notice_does_not_override_scanner_failure(self):
        target = self.root / 'failed-source-notice-project'
        target.mkdir()
        (target / 'requirements.txt').write_text('example-python==1.0\n')
        scanner = self.scanner(exit_code=128)
        scanner.write_text(scanner.read_text().replace('import json, sys', 'import json, sys\nprint(' + repr(OSV_SOURCE_NOTICE) + ', file=sys.stderr)'))
        code, report = self.cli('scan', '--path', str(target), '--scanner', str(scanner), '--json')
        self.assertEqual(code, 1)
        self.assertTrue(any(item['status'] == 'error' for item in report['coverage']))

    def test_invalid_cli_inputs_are_json_and_make_no_reports(self):
        for argv in (("find", "--cvss-min", "nan"), ("find", "--severity", "hihg"),
                     ("find", "--published-after", "yesterday"), ("find", "--package", "litellm"),
                     ("scan", "--repo", "https://evil.invalid/owner/repo"), ("scan", "--path", ".", "--ref", "main")):
            code, data = self.cli(*argv, "--json")
            self.assertEqual(code, 2, argv)
            self.assertEqual(data["status"], "error")

    def test_report_rejects_unknown_schema_and_unknown_kev(self):
        path = self.root / "report.json"
        path.write_text('{"schema_version":999,"findings":[]}')
        code, _ = self.cli("report", "--file", str(path), "--json")
        self.assertEqual(code, 2)
        report = new_report("scan", {})
        report["findings"] = [advisory()]
        finish(report)
        code, _ = self.cli("report", "--known-exploited", "--json")
        self.assertEqual(code, 2)

    def test_github_immutable_acquisition_and_truncated_tree(self):
        stage = self.root / "stage"
        stage.mkdir()
        sha = "a" * 40
        args = self.args("scan", "--repo", "https://github.com/acme/project", "--ref", "feature/x")
        report = new_report("scan", {})
        calls = []
        def api(args, endpoint):
            calls.append(endpoint)
            if endpoint == "repos/acme/project": return {"default_branch": "main"}
            if "/commits/" in endpoint: return {"sha": sha}
            return {"truncated": True, "tree": []}
        with patch("security.scan.github", api):
            with self.assertRaisesRegex(ValueError, "truncated"):
                acquire(args, report, stage)
        self.assertEqual(report["target"]["commit"], sha)
        self.assertIn("feature%2Fx", calls[1])
        self.assertIn(sha, calls[2])

    def test_github_snapshot_fetches_only_selected_commit_manifests(self):
        import base64
        stage = self.root / "stage"
        stage.mkdir()
        sha = "b" * 40
        calls = []
        content = b'{"packages":{},"lockfileVersion":3}'
        def api(args, endpoint):
            calls.append(endpoint)
            if endpoint == "repos/acme/project": return {"default_branch": "main"}
            if "/commits/" in endpoint: return {"sha": sha}
            if "/git/trees/" in endpoint:
                return {"truncated": False, "tree": [
                    {"path": "app/package-lock.json", "type": "blob", "mode": "100644", "sha": "c"*40},
                    {"path": "app/install.sh", "type": "blob", "mode": "100755", "sha": "d"*40}]}
            return {"encoding": "base64", "content": base64.b64encode(content).decode()}
        report = new_report("scan", {})
        with patch("security.scan.github", api):
            acquire(self.args("scan", "--repo", "acme/project"), report, stage)
        self.assertEqual((stage / "app/package-lock.json").read_bytes(), content)
        self.assertFalse((stage / "app/install.sh").exists())
        self.assertEqual(report["target"]["commit"], sha)
        self.assertEqual(len(calls), 4)

    def test_nonregular_local_manifest_is_not_opened_as_a_stream(self):
        target = self.root / "repo"
        target.mkdir()
        os.mkfifo(target / "requirements.txt")
        stage = self.root / "stage"
        stage.mkdir()
        report = new_report("scan", {})
        entries = acquire(self.args("scan", "--path", str(target)), report, stage)
        self.assertEqual(entries, [])
        self.assertEqual(report["coverage"][0]["status"], "unsupported")

    def test_local_git_status_cannot_execute_repo_fsmonitor(self):
        target = self.root / "repo"
        target.mkdir()
        subprocess.run(["git", "init", "-q", str(target)], check=True)
        watcher = self.root / "watcher"
        watcher.write_text('#!/bin/sh\ntouch "' + str(target / "PWNED") + '"\n')
        watcher.chmod(0o755)
        subprocess.run(["git", "-C", str(target), "config", "core.fsmonitor", str(watcher)], check=True)
        (target / "requirements.txt").write_text('example==1.0\n')
        subprocess.run(["git", "-C", str(target), "-c", "core.fsmonitor=false", "add", "requirements.txt"], check=True)
        subprocess.run(["git", "-C", str(target), "-c", "core.fsmonitor=false", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
        # Test the scan path after setup, including protection from optional index writes.
        marker = target / "PWNED"
        marker.unlink(missing_ok=True)
        index = target / ".git/index"
        before = index.read_bytes()
        stage = self.root / "stage"
        stage.mkdir()
        acquire(self.args("scan", "--path", str(target)), new_report("scan", {}), stage)
        self.assertFalse(marker.exists())
        self.assertEqual(index.read_bytes(), before)

    def test_stale_source_data_cannot_produce_complete_cli_report(self):
        def discovery(args, client, report):
            report["findings"] = [advisory()]
            report["coverage"] = [{"source": "NVD", "status": "ok", "receipts": [{"stale": True}]}]
        with patch("security.cli.discover", discovery):
            code, data = self.cli("find", "--source", "nvd", "--json")
        self.assertEqual(code, 1)
        self.assertEqual(data["coverage"][0]["status"], "stale")
        self.assertEqual(data["summary"]["total"], 1)

    def test_network_failure_publishes_incomplete_report_with_existing_findings(self):
        def discovery(args, client, report):
            report["findings"] = [advisory()]
            raise SourceError("rate limited on page 2")
        with patch("security.cli.discover", discovery):
            code, data = self.cli("find", "--source", "nvd", "--json")
        self.assertEqual(code, 1)
        self.assertEqual(data["summary"]["total"], 1)
        self.assertEqual(read_report(data["saved_report"])["status"], "incomplete")

    def test_dependabot_disabled_and_error_are_not_zero(self):
        args = self.args("scan", "--repo", "acme/project")
        report = new_report("scan", {"kind": "github", "repository": "acme/project"})
        rows = [{"repo": "acme/project", "status": "disabled", "count": None}]
        result = subprocess.CompletedProcess([], 0, json.dumps({"repos": rows}).encode(), b"")
        with patch("security.scan.run", return_value=result):
            dependabot(args, report, ROOT / "tools" / "agent-gh")
        self.assertEqual(report["coverage"][0]["status"], "disabled")
        self.assertIsNone(report["dependabot"]["repos"][0]["count"])
        finish(report)
        self.assertEqual(report["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
