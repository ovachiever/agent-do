"""Public agent-do security command surface."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
from quantities import READ_PROBE_TIMEOUT_SECONDS

from .cvenow import discover as discover_cvenow, validate_options as validate_cvenow
from .model import ECOSYSTEMS, merge_findings, present, timestamp
from .scan import dependabot, repo_name, run, scan
from .sources import Client, SourceError, discover, discover_auto, enrich_kev
from .store import finish, latest_report, list_reports, new_report, read_report
from .targets import PROFILES, canonical_target, discover_targets
from .repositories import load_repositories, scan_repositories
from .monitor import initialize, present_digest, read_digest, run_monitor, schedule
from .runtime import assess_runtime, java_identity


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


def score(value):
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 10:
        raise argparse.ArgumentTypeError("CVSS score must be between 0 and 10")
    return number


def date(value):
    try:
        timestamp(value)
        return value
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use an ISO date or timestamp (UTC if timezone omitted)") from exc


def common(parser):
    parser.add_argument("--json", action="store_true", help="emit one versioned JSON document")
    parser.add_argument("--cve", help="match a CVE identifier, including advisory aliases")
    parser.add_argument("--ecosystem", choices=sorted(ECOSYSTEMS), help="package ecosystem; python/pypi normalize to pip")
    parser.add_argument("--package", help="exact package name; discovery requires --ecosystem")
    scores = parser.add_mutually_exclusive_group()
    scores.add_argument("--cvss-min", type=score, help="inclusive minimum CVSS base score")
    scores.add_argument("--cvss-gt", type=score, help="exclusive minimum CVSS base score")
    parser.add_argument("--include-unscored", action="store_true", help="retain unscored records with a score threshold")
    parser.add_argument("--severity", help="comma-separated: critical,high,medium,low,none,unknown")
    parser.add_argument("--published-after", type=date, help="inclusive publication boundary")
    parser.add_argument("--published-before", type=date, help="exclusive publication boundary")
    parser.add_argument("--updated-after", type=date, help="inclusive advisory revision boundary")
    parser.add_argument("--known-exploited", action="store_true", help="only matches in CISA KEV")
    parser.add_argument("--fix-available", action="store_true", help="only records with a published fixed version")


def network(parser):
    parser.add_argument("--timeout", type=positive, default=READ_PROBE_TIMEOUT_SECONDS, help="per HTTP request timeout, seconds")
    parser.add_argument("--retries", type=int, default=2, help="HTTP rate-limit/server-error retries")
    parser.add_argument("--cache-ttl", type=positive, default=3600, help="HTTP cache age, seconds")
    parser.add_argument("--refresh", action="store_true", help="bypass fresh cache entries")
    parser.add_argument("--allow-stale", action="store_true", help="allow explicitly marked stale cache after fetch failure")
    parser.add_argument("--max-bytes", type=int, default=16_777_216, help="maximum bytes per response, manifest, or subprocess stream")
    parser.add_argument("--kev", action="store_true", help="enrich all results using CISA's exploitation catalog")


def collectors(parser):
    parser.add_argument('--image', action='append', default=[], help='explicit registry image to inspect without starting it; repeat for several images')
    parser.add_argument('--rootfs', help='explicit unpacked image or mounted host filesystem directory; never inferred from the current machine')
    parser.add_argument('--kube-context', help='explicit kubectl context for read-only pod image discovery; requires --namespace')
    parser.add_argument('--namespace', help='one explicit Kubernetes namespace (no implicit current context/namespace)')
    parser.add_argument('--selector', help='optional Kubernetes pod label selector; requires --kube-context')
    parser.add_argument('--syft', default='syft', help='trusted installed Syft executable for artifact/JVM release-file inventory')
    parser.add_argument('--trivy', default='trivy', help='trusted installed Trivy executable for vendor/OS/library vulnerability assessment')
    parser.add_argument('--kubectl', default='kubectl', help='trusted installed kubectl executable; pod metadata reads only')
    parser.add_argument('--collect-timeout', type=positive, default=300, help='timeout per collector subprocess, seconds')
    parser.add_argument('--database-max-age', type=positive, default=86400, help='maximum accepted Trivy vulnerability DB age in seconds')


def python_options(parser):
    parser.add_argument('--local-python', action='store_true', help='explicitly probe a trusted Python interpreter in isolated/no-site mode')
    parser.add_argument('--python', help='trusted Python executable; requires --local-python (default this agent-do process interpreter)')
    parser.add_argument('--python-upstream', action='store_true', help='caller verifies this CPython build follows upstream release patch status; otherwise matches remain candidates')


def parser():
    p = ArgumentParser(prog="agent-do security", description="Find advisories, scan dependencies, assess explicit runtimes and monitor portfolios. File scans are read-only; --resolve explicitly executes trusted local Maven/Gradle project code and permits build writes.")
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("find", help="discover published advisories; does not assess repository exposure")
    common(f)
    network(f)
    f.add_argument("--source", choices=["auto", "nvd", "github", "cve-now"], default="auto")
    f.add_argument('--technology', help='cve.now recent-feed technology slug, e.g. spring, log4j, node; requires --source cve-now')
    f.add_argument('--feed-filter', choices=['critical', 'kev'], help='cve.now curated critical/KEV feed; critical is not a CVSS severity')
    f.add_argument('--source-status', action='store_true', help='attach cve.now self-reported polling/coverage health to the assessment')
    f.add_argument("--vendor", help="NVD CPE vendor component, such as oracle")
    f.add_argument("--product", help="NVD CPE product component, such as cpython")
    f.add_argument("--query", help="broad NVD keyword search; not an exact product identity")
    f.add_argument("--limit", type=int, default=100, help="maximum source records examined before presentation filters; truncation is explicit")
    f.add_argument('--target', type=canonical_target, choices=sorted(PROFILES), action='append', default=[],
                   help='repeat to combine curated searches; aliases: springboot, node; --limit applies per component query')
    s = sub.add_parser("scan", help="assess an isolated dependency-file snapshot with OSV-Scanner v2")
    common(s)
    network(s)
    target = s.add_mutually_exclusive_group(required=True)
    target.add_argument("--path", help="local source directory, including uncommitted dependency files")
    target.add_argument("--repo", help="GitHub URL or owner/repo; requires authenticated gh for acquisition")
    target.add_argument('--repos-file', help='local text/JSON list of GitHub repositories; scan all sequentially in one report')
    s.add_argument("--ref", help="branch, tag, or commit; defaults to repository default branch")
    s.add_argument("--scanner", default="osv-scanner", help="trusted OSV-Scanner v2 executable")
    s.add_argument('--scanner-diagnostics', metavar='DIR', help='opt in to saving raw scanner stderr as a private, uniquely named file in DIR; may contain credentials/private paths')
    s.add_argument("--scan-timeout", type=positive, default=300, help="timeout per scanner/GitHub subprocess, seconds")
    s.add_argument("--dependabot", action="store_true", help="attach separately scoped default-branch alerts through gh alerts (PR #51)")
    s.add_argument('--resolve', choices=['maven', 'gradle'], help='opt in to executing local build code to resolve exact JVM dependencies (requires --path)')
    s.add_argument('--maven', help='trusted Maven executable; defaults to executable ./mvnw, then installed mvn')
    s.add_argument('--gradle', help='trusted Gradle executable; defaults to executable ./gradlew, then installed gradle')
    s.add_argument('--maven-profile', action='append', default=[], help='activate a Maven profile; repeat for multiple profiles')
    s.add_argument('--maven-settings', '--settings', help='Maven settings.xml for repository/auth/profile configuration (requires --resolve maven)')
    s.add_argument('--gradle-configuration', action='append', default=[], help='Gradle configuration to resolve in each project; repeat (default runtimeClasspath)')
    s.add_argument('--build-property', action='append', default=[], help='NAME=VALUE; Maven -D or Gradle -P project property (repeat; avoid credentials)')
    runtime = sub.add_parser('runtime', help='assess explicit runtime/deployment CPE inventory; project declarations remain hints')
    common(runtime)
    network(runtime)
    runtime.add_argument('--path', help='read static root POM/Gradle/toolchain/Dockerfile declarations without executing project code')
    runtime.add_argument('--inventory', help='versioned JSON runtime/deployment inventory with exact CPE identities and evidence')
    runtime.add_argument('--temurin-vdr', help='local Adoptium CycloneDX VDR JSON; defaults to digest-verified latest official release')
    collectors(runtime)
    python_options(runtime)
    runtime.add_argument('--local-java', action='store_true', help='explicitly execute the selected local Java binary to observe vendor and version')
    runtime.add_argument('--java', help='trusted Java executable, used only with --local-java (default installed java)')
    runtime.add_argument('--java-cpe', help='verified distribution CPE identity with wildcard version/update; used only with --local-java')
    runtime.add_argument('--probe-timeout', type=positive, default=READ_PROBE_TIMEOUT_SECONDS, help='local Java/Python probe timeout in seconds')
    runtime.add_argument('--inventory-only', action='store_true', help='collect without advisory requests/CVE assessment; explicit image/cluster collectors may contact registries/APIs')
    runtime.add_argument('--limit', type=int, default=1000, help='maximum NVD records examined per runtime component before presentation filters; truncation is explicit')
    r = sub.add_parser("report", help="read a saved unfiltered report and apply presentation filters")
    common(r)
    r.add_argument('--target', type=canonical_target, choices=sorted(PROFILES), action='append', default=[],
                   help='filter saved multi-target findings to searched targets (repeat for OR)')
    selected = r.add_mutually_exclusive_group()
    selected.add_argument("--latest", action="store_true", help="read the newest saved report, including incomplete assessments (default)")
    selected.add_argument('--latest-complete', action='store_true', help='explicitly select the newest complete report across all projects; may be older')
    selected.add_argument('--list', action='store_true', help='list saved report paths, timestamps, targets, status, findings and coverage gaps')
    selected.add_argument("--file", help="read a particular saved JSON report")
    d = sub.add_parser("doctor", help="check local feature prerequisites without network requests")
    d.add_argument("--json", action="store_true")
    d.add_argument("--scanner", default="osv-scanner")
    d.add_argument("--scan-timeout", type=positive, default=READ_PROBE_TIMEOUT_SECONDS)
    d.add_argument("--max-bytes", type=int, default=16_777_216)
    m = sub.add_parser('monitor', help='configure portfolio scans, compare evidence, and export a recurring cron job')
    actions = m.add_subparsers(dest='monitor_command', required=True)
    init = actions.add_parser('init', help='create a new local portfolio configuration without overwriting a file')
    init.add_argument('--config', required=True)
    inputs = init.add_mutually_exclusive_group()
    inputs.add_argument('--repos-file')
    inputs.add_argument('--path')
    init.add_argument('--runtime-inventory', help='monitor runtime/deployment inventory, optionally alongside --path or --repos-file')
    init.add_argument('--resolve', choices=['maven', 'gradle'])
    init.add_argument('--interval-hours', type=int, default=24)
    init.add_argument('--max-bytes', type=int, default=16_777_216)
    init.add_argument('--json', action='store_true')
    collectors(init)
    python_options(init)
    init.add_argument("--probe-timeout", type=positive, default=READ_PROBE_TIMEOUT_SECONDS, help="timeout for the configured local Python probe")
    monitor_run = actions.add_parser('run', help='scan configured targets and save an unfiltered change digest')
    common(monitor_run)
    network(monitor_run)
    monitor_run.add_argument('--config', required=True)
    monitor_run.add_argument('--due', action='store_true', help='skip if the configured interval has not elapsed since the last attempt')
    monitor_run.add_argument('--allow-builds', action='store_true', help='explicitly authorize trusted configured local Maven/Gradle build execution')
    monitor_run.add_argument('--allow-collectors', action='store_true', help='authorize configured Syft/Trivy/kubectl and local Python probe execution for this run')
    monitor_run.add_argument('--runtime-limit', type=int, default=1000, help='maximum NVD records examined per imported runtime component; source dependency scans are unaffected')
    monitor_run.add_argument('--scanner', default='osv-scanner')
    monitor_run.add_argument('--scan-timeout', type=positive, default=300)
    monitor_run.add_argument('--notify-recipient', help='explicitly send digest counts/path to this existing agent-do notify recipient')
    monitor_run.add_argument('--notify-via', help='provider order forwarded to notify; requires --notify-recipient')
    monitor_report = actions.add_parser('report', help='read/refilter a saved monitor digest without scanning')
    common(monitor_report)
    monitor_report.add_argument('--config', required=True)
    monitor_report.add_argument('--file', help='specific digest; defaults to this monitor latest committed digest')
    monitor_report.add_argument('--max-bytes', type=int, default=16_777_216)
    scheduled = actions.add_parser('schedule', help='print a reviewable hourly cron entry; never install it automatically')
    scheduled.add_argument('--config', required=True)
    scheduled.add_argument('--allow-builds', action='store_true')
    scheduled.add_argument('--allow-collectors', action='store_true')
    scheduled.add_argument('--runtime-limit', type=int, default=1000, help='per-component NVD record bound exported into the scheduled runtime assessments')
    scheduled.add_argument('--notify-recipient', help='explicit recipient included in the exported job; nothing is sent during export')
    scheduled.add_argument('--notify-via', help='provider order for the exported job; requires --notify-recipient')
    scheduled.add_argument('--max-bytes', type=int, default=16_777_216)
    scheduled.add_argument('--json', action='store_true')
    return p


def validate(args):
    if hasattr(args, 'image'):
        from .collect import image_ref
        for image in args.image:
            image_ref(image)
        if bool(args.kube_context) != bool(args.namespace):
            raise ValueError('--kube-context and --namespace must be supplied together')
        if args.selector and not args.kube_context:
            raise ValueError('--selector requires --kube-context and --namespace')
        for value in (args.kube_context, args.namespace, args.selector):
            if value and (value.startswith('-') or any(ord(c) < 32 or ord(c) == 127 for c in value)):
                raise ValueError('Invalid Kubernetes context/namespace/selector')
        if args.rootfs and not getattr(args, '_monitor_planned', False) and not Path(args.rootfs).expanduser().is_dir():
            raise ValueError('--rootfs requires an existing explicitly selected directory')
    if args.command == 'monitor' and args.monitor_command == 'init' and not (args.path or args.repos_file or args.runtime_inventory or args.image or args.rootfs or args.kube_context or args.local_python):
        raise ValueError('monitor init requires a source, runtime inventory, --local-python or explicit collector target')
    if args.command == 'monitor' and args.monitor_command in {'run', 'schedule'} and args.notify_via and not args.notify_recipient:
        raise ValueError('--notify-via requires --notify-recipient')
    if args.command == 'report' and args.list:
        filters = ('cve', 'ecosystem', 'package', 'cvss_min', 'cvss_gt', 'include_unscored', 'severity',
                   'published_after', 'published_before', 'updated_after', 'known_exploited', 'fix_available', 'target')
        if any(getattr(args, key) is not None and getattr(args, key) is not False and getattr(args, key) != [] for key in filters):
            raise ValueError('--list lists report metadata; apply finding filters with --file, --latest or --latest-complete')
    if getattr(args, "max_bytes", 1) <= 0 or getattr(args, "limit", 1) <= 0 or getattr(args, "runtime_limit", 1) <= 0 or getattr(args, "retries", 0) < 0:
        raise ValueError("--max-bytes, --limit and --runtime-limit must be positive; --retries must be nonnegative")
    if getattr(args, "cve", None) and not re.fullmatch(r"CVE-\d{4}-\d{4,}", args.cve, re.I):
        raise ValueError("--cve must be a CVE-YYYY-NNNN identifier")
    if getattr(args, "severity", None):
        values = args.severity.lower().split(",")
        if not values or set(values) - {"critical", "high", "medium", "low", "none", "unknown"}:
            raise ValueError("Unknown --severity value")
        args.severity = ",".join(values)
    if getattr(args, "published_after", None) and args.published_before and timestamp(args.published_after) >= timestamp(args.published_before):
        raise ValueError("--published-after must precede --published-before")
    if args.command == 'runtime' or (args.command == 'monitor' and args.monitor_command == 'init'):
        if (args.python or args.python_upstream) and not args.local_python:
            raise ValueError('--python and --python-upstream require explicit --local-python')
    if args.command == 'runtime':
        if not (args.path or args.inventory or args.local_java or args.local_python or args.image or args.rootfs or args.kube_context):
            raise ValueError('runtime requires --path, --inventory, --local-java, --local-python or explicit collectors (may be combined)')
        if (args.java or args.java_cpe) and not args.local_java:
            raise ValueError('--java and --java-cpe require explicit --local-java')
        if args.java_cpe:
            java_identity(args.java_cpe)
        if args.ecosystem:
            raise ValueError('Runtime identities use CPE, not package ecosystems; use --package vendor:product or --cve')
        if args.inventory_only and (args.kev or args.known_exploited or args.cve or args.package or args.cvss_min is not None or args.cvss_gt is not None or args.severity or args.published_after or args.published_before or args.updated_after or args.fix_available or args.include_unscored):
            raise ValueError('--inventory-only does not assess advisories; CVE/score/date/exploitation filters do not apply')
    if args.command == "find":
        validate_cvenow(args)
        if args.target:
            args.target = list(dict.fromkeys(args.target))
            if args.source != 'auto' or any((args.vendor, args.product, args.query, args.ecosystem, args.package)):
                raise ValueError('--target chooses its own source/criteria; use shared CVSS/date/CVE filters or run a separate manual query')
        if args.package and not args.ecosystem:
            raise ValueError("Package discovery requires --ecosystem")
        if (args.vendor or args.product) and (args.ecosystem or args.package):
            raise ValueError("Vendor/product discovery and ecosystem/package discovery use different sources; run separate queries")
        for value in (args.vendor, args.product):
            if value and not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
                raise ValueError("Vendor/product must be one CPE component; use --query for free text")
    if args.command == "scan":
        if args.scanner_diagnostics:
            destination = Path(args.scanner_diagnostics).expanduser()
            if destination.exists() and not destination.is_dir():
                raise ValueError('--scanner-diagnostics must name a directory')
        if args.resolve and not args.path:
            raise ValueError('--resolve executes build code and requires a trusted local --path checkout; clone GitHub projects first')
        if not args.resolve and (args.maven or args.gradle or args.maven_profile or args.maven_settings or args.gradle_configuration or args.build_property):
            raise ValueError('Build options require explicit --resolve maven|gradle')
        if args.resolve == 'maven' and (args.gradle or args.gradle_configuration):
            raise ValueError('Gradle options require --resolve gradle')
        if args.resolve == 'gradle' and (args.maven or args.maven_profile or args.maven_settings):
            raise ValueError('Maven options require --resolve maven')
        for value in args.maven_profile + args.gradle_configuration:
            if not re.fullmatch(r'[A-Za-z0-9_.!-]+', value):
                raise ValueError('Profile/configuration names must be individual names; repeat the option for multiple selections')
        for value in args.build_property:
            name, separator, _ = value.partition('=')
            if not separator or not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
                raise ValueError('--build-property must be NAME=VALUE')
            if name in {'outputFile', 'outputType', 'verbose', 'appendOutput', 'skip', 'mdep.skip'} or name.startswith('agentdo.security.'):
                raise ValueError('This build property is reserved by dependency inventory capture')
        if args.maven_settings and not Path(args.maven_settings).expanduser().is_file():
            raise ValueError('--maven-settings must name an existing settings file')
        if args.ref and not (args.repo or args.repos_file):
            raise ValueError("--ref requires --repo or --repos-file")
        if args.dependabot and not (args.repo or args.repos_file):
            raise ValueError("--dependabot requires --repo or --repos-file")
        if args.repo:
            repo_name(args.repo)


def doctor(args):
    binary = shutil.which(args.scanner)
    scanner = {"available": bool(binary), "version": None, "v2": False}
    if binary:
        result = run([binary, "--version"], args)
        scanner["version"] = result.stdout.decode(errors="replace").strip()
        scanner["v2"] = result.returncode == 0 and bool(re.search(r"(?:version[: ]+|v)2\.", scanner["version"], re.I))
    return {"schema_version": 1, "command": "doctor", "status": "ok" if scanner["v2"] else "incomplete",
            "scanner": scanner, "features": {"advisory_discovery": "available; network not probed",
            "cvenow_discovery": "preferred for compatible auto discovery; NVD/GitHub fallback; network not probed",
            "local_scan": "available" if scanner["v2"] else "requires OSV-Scanner v2",
            "runtime_inventory": "available; explicit CPE/Temurin evidence and vendor advisory assessment",
            "temurin_assessment": "available; official Adoptium VDR, network not probed",
            "artifact_collection": "available" if shutil.which('syft') and shutil.which('trivy') else "requires separately installed syft and trivy",
            "kubernetes_collection": "available" if all(shutil.which(tool) for tool in ('syft', 'trivy', 'kubectl')) else "requires syft, trivy and kubectl; explicit context/namespace and registry/RBAC access",
            "local_python_probe": "available; explicit runtime --local-python, isolated/no-site; CPython upstream version assessment",
            "local_java_probe": "java found; executed only with runtime --local-java" if shutil.which("java") else "requires a trusted Java executable selected with runtime --local-java --java PATH",
            "github_acquisition": "gh found; authentication not probed" if shutil.which("gh") else "requires gh",
            "maven_resolution": "installed mvn found" if shutil.which('mvn') else 'requires executable project mvnw or installed Maven; never probed without opt-in',
            "gradle_resolution": "installed gradle found" if shutil.which('gradle') else 'requires executable project gradlew or installed Gradle; never probed without opt-in',
            "vector_scoring": "available" if importlib.util.find_spec("cvss") else "install optional cvss package; numeric scores and raw vectors remain available",
            "dependabot": "requires gh alerts from PR #51 or successor"},
            "credentials_present": {name: bool(os.environ.get(name)) for name in ("NVD_API_KEY", "GH_TOKEN", "GITHUB_TOKEN")},
            "notes": ["Credential presence does not establish authorization. No network requests made."]}


def output(payload, json_mode):
    if json_mode:
        print(json.dumps(payload, sort_keys=True, indent=2))
        return
    if payload.get("error"):
        print("security: " + payload["error"], file=sys.stderr)
        return
    if payload.get('command', '').startswith('monitor '):
        print('agent-do security ' + payload['command'] + ' — ' + payload['status'])
        if payload.get('config'):
            print('  Config: ' + payload['config'])
        if payload.get('skipped'):
            print('  Not due; next due: ' + payload['next_due'])
        if payload.get('cron'):
            print(payload['cron'])
        if payload.get('changes') is not None:
            assessment = payload.get('assessment_summary')
            if assessment:
                observed = str(assessment['findings_observed']) if assessment['findings_observed'] is not None else 'unknown (historical digest)'
                print(f"  Assessment: {assessment['status']}; {assessment['targets_complete']}/{assessment['targets_total']} targets complete; {observed} observed findings before filters")
                if assessment['runtime_candidates'] is not None:
                    print(f"  Runtime evidence: {assessment['runtime_inventory_matches']} inventory matches; {assessment['runtime_candidates']} candidates")
                if assessment['status'] != 'complete':
                    print('  WARNING: ' + assessment['interpretation'])
                for issue in assessment['coverage_issues']:
                    target = issue['target']
                    label = target.get('repo') or target.get('path') or target.get('runtime_inventory', issue['target_key'])
                    prefix = 'ERROR' if issue['status'] == 'error' else 'COVERAGE'
                    print(f"  {prefix}: {issue['source']} [{label}] — {issue['status']}: {issue['message']}")
            print('  Comparison: ' + payload['comparison_status'])
            for assessed in payload['targets']:
                target = assessed['target']
                print('  Target: ' + (target.get('repo') or target.get('path') or target.get('runtime_inventory', '') or target.get('runtime_probe', {}).get('python', '')) + ' — ' + assessed['status'])
            for category, count in payload['counts'].items():
                print(f"  {category}: {payload.get('shown_counts', payload['counts'])[category]} shown / {count}")
                for issue in payload['changes'][category]:
                    target = issue['target']
                    rows = issue['findings']
                    representative = max(rows, key=lambda row: row['cvss'] if row['cvss'] is not None else -1)
                    package = representative.get('package') or {}
                    versions = sorted({str((row.get('package') or {}).get('version') or '?') for row in rows})
                    print('    ' + (target.get('repo') or target.get('path') or target.get('runtime_inventory', '') or target.get('runtime_probe', {}).get('python', '')) + ': ' + ', '.join(issue['aliases']) + ' — ' + representative['severity'] + ' ' + package.get('name', '') + '@' + ','.join(versions))
                    if representative.get('runtime_match'):
                        print('      Runtime applicability: ' + representative['runtime_match']['component_id'] + ' — ' + representative['runtime_match']['relation'])
                    print('      ' + representative['summary'].replace('\n', ' '))
                    fixes = sorted({version for row in rows for affected in row['affected'] for version in affected.get('fixed_versions', [])})
                    if fixes:
                        print('      Published fixes (compatibility not verified): ' + ', '.join(fixes))
                    print('      First detected: ' + issue['first_detected_at'] + '; last seen: ' + issue['last_seen_at'])
                    if issue.get('reason'):
                        print('      ' + issue['reason'])
            print('  Source assessment: ' + payload['source_report'])
            print('  Digest: ' + payload['saved_digest'])
        for note in payload.get('notes', []):
            print('  ' + note)
        if payload.get('notification'):
            print('  Notification: ' + payload['notification']['status'])
        return
    print("agent-do security " + payload["command"] + " — " + payload["status"])
    if payload["command"] == "doctor":
        for name, state in payload["features"].items():
            print("  " + name + ": " + state)
        return
    if 'reports' in payload:
        for report in payload['reports']:
            target = report.get('target', {})
            label = target.get('repository') or target.get('path') or target.get('inventory') or ', '.join(target.get('targets', [])) or target.get('kind', 'unknown')
            print(f"  {report.get('created_at', '?')}  {report.get('command', '?')}  {label} — {report['status']}; {report.get('findings', '?')} findings; {report.get('unscored', '?')} unscored")
            for gap in report.get('coverage_gaps', []):
                print(f"    Coverage: {gap['source']} — {gap['status']}: {gap.get('reason', gap.get('error', ''))}")
            if report.get('error'):
                print('    ' + report['error'])
            print('    File: ' + report['file'])
        if not payload['reports']:
            print('  No saved security reports; run find or scan first.')
        return
    for note in payload.get('selection_notes', []):
        print('  Report selection: ' + note)
    if payload.get('created_at'):
        print('  Assessed: ' + payload['created_at'])
    target = payload.get('target', {})
    label = target.get('repository') or target.get('path') or target.get('inventory')
    if label:
        print('  Target: ' + label)
    summary = payload["summary"]
    print(f"  {summary['shown']} shown / {summary['total']} findings; {summary['excluded']} filtered; {summary['unscored']} unscored")
    for target in payload.get('target_summaries', []):
        print(f"  Target: {target['target']} — {target['status']}; {target['shown']}/{target['total']} findings shown across {target['queries']} queries")
    for repository in payload.get('repository_summaries', []):
        print(f"  Repository: {repository['repository']} ({repository['requested_ref'] or 'default branch'}) — {repository['status']}; {repository['shown']}/{repository['total']} findings shown; commit {repository['commit'] or 'unavailable'}")
    for repository in payload.get('repositories', []):
        diagnostics = repository.get('scanner', {}).get('diagnostics')
        if diagnostics:
            print('  Private scanner diagnostics (' + repository['target']['repository'] + '): ' + diagnostics['stderr_file'])
    if payload.get('resolution'):
        resolution = payload['resolution']
        print(f"  Resolution: {resolution['tool']} — {resolution['status']}; {len(resolution.get('occurrences', []))} dependency occurrences")
    if payload.get('scanner', {}).get('diagnostics'):
        print('  Private scanner diagnostics: ' + payload['scanner']['diagnostics']['stderr_file'])
    for hint in payload.get('declared_settings', []):
        print('  Declaration only: ' + hint['file'] + ' ' + hint['setting'] + '=' + hint['value'])
    for component in payload.get('runtime_components', []):
        print('  Runtime: ' + component['id'] + ' — ' + component.get('cpe', ':'.join(component.get('java', {}).get(key, '?') for key in ('vendor', 'product', 'version')) if component.get('java') else 'unmapped vendor identity'))
        evidence = component['evidence']
        print('    Evidence: ' + evidence['kind'] + '; observed ' + evidence['observed_at'] + '; ' + evidence['verification'])
        if component.get('python'):
            identity = component['python']
            print('    Python: ' + identity['implementation'] + ' ' + identity['version'] + ' (' + identity['releaselevel'] + '); ' + component['build_provenance'])
        if component.get('properties'):
            print('    Java: ' + component['properties'].get('java.vendor', 'unknown vendor') + ' ' + component['properties'].get('java.runtime.version', component['properties'].get('java.version', '?')))
        if component.get('deployment'):
            print('    Deployment: ' + json.dumps(component['deployment'], sort_keys=True))
    for row in payload["findings"]:
        if row.get('discovery_attempt'):
            print('  Advisory source: unverified partial cve.now result retained after failover')
        if row.get('runtime_match'):
            print('  Runtime applicability: ' + row['runtime_match']['component_id'] + ' — ' + row['runtime_match']['relation'])
        package = row.get("package") or {}
        label = package.get("name", "") + ("@" + package["version"] if package.get("version") else "")
        print(f"  {row['id']}  CVSS {row['cvss'] if row['cvss'] is not None else '?'}  {row['severity']}  {label}")
        if row.get('repository_target'):
            target = row['repository_target']
            print(f"    Repository: {target['repository']} ({target['requested_ref'] or 'default branch'}); commit {target['commit'] or 'unavailable'}")
        if row.get('matched_targets'):
            print('    Matched targets: ' + ', '.join(row['matched_targets']))
            for match in row.get('target_matches', []):
                if match['relation'].endswith('_candidate'):
                    print('    Candidate relevance: ' + match['target'] + ' — ' + match['relation'])
        print("    " + row["summary"].replace("\n", " "))
        fixes = sorted({v for a in row["affected"] for v in a.get("fixed_versions", [])})
        if fixes:
            print("    Published fixes (compatibility not verified): " + ", ".join(fixes))
        for source in row["sources"]:
            print("    " + str(source["url"]))
        for evidence in row['evidence']:
            if evidence.get('dependency_path'):
                print('    ' + evidence.get('dependency_scope', 'unknown') + ': ' + ' -> '.join(evidence['dependency_path']))
    if not payload["findings"] and payload.get("scope") != "runtime_inventory_only":
        print("  No matching records in the assessed inventory/source window; review coverage below.")
    for source in payload["coverage"]:
        identity = source['source'] + (' [' + source['query_id'] + ']' if source.get('query_id') else '')
        if source.get('repository_target'):
            target = source['repository_target']
            identity += f" [{target['repository']} @ {target['requested_ref'] or 'default branch'}]"
        print("  Coverage: " + identity + " — " + source["status"] + (": " + source.get("reason", source.get("error", "")) if source.get("reason") or source.get("error") else ""))
    for profile in payload.get('target', {}).get('profiles', []):
        print('  Target scope (' + profile['target'] + '): ' + profile['scope'])
    for note in payload.get("notes", []) + payload.get("limitations", []):
        print("  " + note)
    if payload.get("saved_report"):
        print("  Saved: " + payload["saved_report"])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    p = parser()
    # Keep parser errors machine-readable when the caller requests JSON.
    try:
        args = p.parse_args(argv)
        validate(args)
        if args.command == "doctor":
            payload = doctor(args)
        elif args.command == 'monitor':
            if args.monitor_command == 'init':
                payload = initialize(args)
            elif args.monitor_command == 'schedule':
                payload = schedule(args, ROOT)
            else:
                result = run_monitor(args, lambda argv: p.parse_args(argv), validate, ROOT) if args.monitor_command == 'run' else read_digest(args)
                payload = present_digest(result, args)
        elif args.command == 'runtime':
            report = new_report('runtime', {'kind': 'runtime_inventory', 'path': str(Path(args.path).expanduser().resolve()) if args.path else None,
                                           'inventory': str(Path(args.inventory).expanduser().resolve()) if args.inventory else None})
            client = Client(args)
            try:
                assess_runtime(args, client, report)
                if not args.inventory_only and (args.kev or args.known_exploited):
                    enrich_kev(client, report)
            except (SourceError, OSError, ValueError) as exc:
                report['coverage'].append({'source': 'runtime', 'status': 'error', 'error': str(exc)})
            for source in report['coverage']:
                if any(item.get('stale') for item in source.get('receipts', [])):
                    source['stale'] = True
                    if source['status'] == 'ok':
                        source['status'] = 'stale'
            report['findings'] = merge_findings(report['findings'])
            payload = present(finish(report), args)
        elif args.command == "report":
            if args.list:
                entries = list_reports()
                payload = {'schema_version': 1, 'command': 'report', 'status': 'incomplete' if any(entry['status'] == 'unreadable' for entry in entries) else 'ok', 'reports': entries}
                output(payload, args.json)
                return 1 if payload['status'] == 'incomplete' else 0
            report = read_report(args.file) if args.file else latest_report(complete_only=args.latest_complete)
            if not args.file and not args.latest_complete and report['status'] != 'complete':
                report.setdefault('selection_notes', []).append('The newest saved assessment is incomplete. No earlier result was substituted. Use report --list to choose --file PATH, or explicitly request --latest-complete (which may concern a different project).')
            if args.target:
                searched = report.get('target', {}).get('targets', [])
                if not set(args.target) <= set(searched):
                    raise ValueError('Requested targets were not searched in this saved report; repeat find with --target')
            if args.known_exploited and any(x["known_exploited"] is None for x in report["findings"]):
                raise ValueError("Saved report has unknown exploitation status; repeat find/scan with --kev")
            payload = present(report, args)
        else:
            batch_target = load_repositories(args.repos_file, args.max_bytes, args.ref) if args.command == 'scan' and args.repos_file else None
            report = new_report(args.command, batch_target or ({"kind": "github", "repository": args.repo} if args.command == "scan" and args.repo else {"kind": "local", "path": args.path} if args.command == "scan" else {"kind": "advisory_query"}))
            client = Client(args)
            try:
                if args.command == "find":
                    if args.source == "cve-now":
                        discover_cvenow(args, client, report)
                    elif args.target:
                        discover_targets(args, client, report)
                    elif args.source == 'auto':
                        discover_auto(args, client, report)
                    else:
                        discover(args, client, report)
                elif batch_target:
                    scan_repositories(args, report, ROOT / 'tools' / 'agent-gh')
                else:
                    scan(args, report)
                    if args.dependabot:
                        dependabot(args, report, ROOT / "tools" / "agent-gh")
                if args.kev or args.known_exploited:
                    enrich_kev(client, report)
            except (SourceError, OSError, ValueError) as exc:
                report["coverage"].append({"source": args.command, "status": "error", "error": str(exc), "receipts": client.receipts[:]})
            report["findings"] = merge_findings(report["findings"])
            for source in report["coverage"]:
                if any(x.get("stale") for x in source.get("receipts", [])):
                    source['stale'] = True
                    if source['status'] == 'ok':
                        source["status"] = "stale"
            payload = present(finish(report), args)
        output(payload, args.json)
        return 1 if payload["status"] != "complete" and payload["status"] != "ok" else 0
    except (ValueError, OSError, SourceError) as exc:
        output({"schema_version": 1, "status": "error", "error": str(exc)}, "--json" in argv)
        return 2
