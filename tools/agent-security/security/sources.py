"""Bounded advisory HTTP reads, caching, source adapters, and KEV enrichment."""
from __future__ import annotations

import json
import copy
import hashlib
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from .model import cvss_scores, ecosystem, finding, now, timestamp
from .store import atomic_json, digest, home

NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"
GHSA = "https://api.github.com/advisories"
KEV = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


class SourceError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Endpoints are fixed authorities; do not forward credentials via redirects.
        raise SourceError("Advisory source redirected; update the source adapter")


class AdoptiumAssetRedirect(urllib.request.HTTPRedirectHandler):
    """Public release downloads only; never forward API credentials."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if target.scheme != 'https' or target.username or target.password or target.port not in (None, 443) or target.hostname != 'release-assets.githubusercontent.com':
            raise SourceError('Unapproved Adoptium asset redirect')
        return urllib.request.Request(newurl, headers={'Accept': 'application/json', 'User-Agent': 'agent-do-security/1'})


def cvenow_endpoint(parsed):
    """Allow public advisory reads only; stack/MCP/upload paths are excluded."""
    if parsed.hostname != 'cve.now' or parsed.fragment:
        return False
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    if any(len(values) != 1 for values in query.values()):
        return False
    if parsed.path == '/api/v1/entries':
        return not (set(query) - {'cursor'})
    if re.fullmatch(r'/api/v1/entries/[A-Za-z0-9][A-Za-z0-9_.-]{1,199}', parsed.path):
        return not parsed.query
    if parsed.path == '/api/v1/status':
        return not parsed.query
    if parsed.path == '/feed':
        return not (set(query) - {'format', 'tech', 'ecosystem', 'filter'}) and query.get('format') == ['json']
    return False


class Client:
    def __init__(self, args):
        self.args = args
        self.receipts = []
        self.last_nvd_request = None
        self.open = urllib.request.build_opener(NoRedirect()).open

    def get(self, url):
        parsed = urllib.parse.urlsplit(url)
        asset = parsed.hostname == 'github.com' and re_asset_path(parsed.path) and not parsed.query
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443) or (not asset and not cvenow_endpoint(parsed) and parsed.hostname not in {"services.nvd.nist.gov", "api.github.com", "www.cisa.gov"}):
            raise SourceError("Unapproved advisory endpoint")
        headers = {"Accept": "application/json", "User-Agent": "agent-do-security/1"}
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if parsed.hostname == "api.github.com" and token:
            headers["Authorization"] = "Bearer " + token
        if parsed.hostname == "services.nvd.nist.gov" and os.environ.get("NVD_API_KEY"):
            headers["apiKey"] = os.environ["NVD_API_KEY"]
        # Partition private cache entries by credential identity without persisting credentials.
        identity = digest((headers.get("Authorization", "") + headers.get("apiKey", "")).encode())
        path = home() / "cache" / (digest((url + identity).encode()) + ".json")
        cached = None
        try:
            cached = json.loads(path.read_text())
        except (OSError, ValueError):
            pass
        if cached and not self.args.refresh and (timestamp(now()) - timestamp(cached["fetched_at"])).total_seconds() < self.args.cache_ttl:
            self.receipts.append({"url": url, "fetched_at": cached["fetched_at"], "cache": True, "stale": False})
            return cached["body"], cached.get("headers", {})
        failure = "Network request failed"
        for attempt in range(self.args.retries + 1):
            try:
                if parsed.hostname == 'services.nvd.nist.gov' and self.last_nvd_request is not None:
                    interval = 0.6 if os.environ.get('NVD_API_KEY') else 6.0
                    delay = interval - (time.monotonic() - self.last_nvd_request)
                    if delay > 0:
                        time.sleep(delay)
                requested_at = time.monotonic()
                request = urllib.request.Request(url, headers=headers)
                opener = urllib.request.build_opener(AdoptiumAssetRedirect()).open if asset else self.open
                with opener(request, timeout=self.args.timeout) as response:
                    if parsed.hostname == 'services.nvd.nist.gov':
                        self.last_nvd_request = requested_at
                    body = response.read(self.args.max_bytes + 1)
                    if len(body) > self.args.max_bytes:
                        raise SourceError("Source response exceeds --max-bytes; no records discarded silently")
                    value = json.loads(body)
                    meta = {"link": response.headers.get("Link", ""), "last-modified": response.headers.get("Last-Modified", ""),
                            'sha256': hashlib.sha256(body).hexdigest()}
                fetched = now()
                atomic_json(path, {"fetched_at": fetched, "body": value, "headers": meta})
                self.receipts.append({"url": url, "fetched_at": fetched, "cache": False, "stale": False})
                return value, meta
            except urllib.error.HTTPError as exc:
                if parsed.hostname == 'services.nvd.nist.gov':
                    self.last_nvd_request = requested_at
                failure = "Advisory HTTP " + str(exc.code)  # Do not echo credential-bearing headers or bodies.
                retryable = exc.code in {429, 500, 502, 503, 504}
                if not retryable or attempt == self.args.retries:
                    break
                retry_after = exc.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else 2 ** attempt
                if delay > self.args.timeout:
                    failure += "; Retry-After exceeds --timeout; retry later"
                    break
                time.sleep(delay)
            except SourceError as exc:
                failure = str(exc)
                break
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                failure = type(exc).__name__ + ": advisory fetch failed"
                break
        if cached and self.args.allow_stale:
            self.receipts.append({"url": url, "fetched_at": cached["fetched_at"], "cache": True, "stale": True, "error": failure})
            return cached["body"], cached.get("headers", {})
        raise SourceError(failure)


def re_asset_path(path):
    return bool(re.fullmatch(r'/adoptium/temurin-vdr-generator/releases/download/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.json', path))


def nvd_row(cve):
    scores = []
    for name, metrics in (cve.get("metrics") or {}).items():
        if name.startswith("cvssMetric"):
            for metric in metrics:
                scores += cvss_scores([metric.get("cvssData", {})], metric.get("source", "NVD"))
    summary = next((x["value"] for x in cve.get("descriptions", []) if x.get("lang") == "en"), "")
    affected = []

    def visit(node):
        for match in node.get("cpeMatch", []):
            if match.get("vulnerable"):
                affected.append({"cpe": match.get("criteria"), "ranges": [match], "fixed_versions": []})
        for child in node.get("nodes", []) + node.get("children", []):
            visit(child)

    for config in cve.get("configurations", []):
        visit(config)
    return finding([cve["id"]], summary, "NVD", "https://nvd.nist.gov/vuln/detail/" + cve["id"],
                   scores=scores, published=cve.get("published"), modified=cve.get("lastModified"), affected=affected)


def ghsa_row(item):
    entries = []
    for version, score in (item.get("cvss_severities") or {}).items():
        if score:
            entries.append({**score, "version": version.replace("cvss_v", "").replace("_", ".")})
    if item.get("cvss"):
        entries.append(item["cvss"])
    affected = [{"package": v.get("package", {}), "ranges": [v.get("vulnerable_version_range")],
                 "fixed_versions": [v["first_patched_version"]] if v.get("first_patched_version") else []}
                for v in item.get("vulnerabilities", [])]
    ids = [item.get("ghsa_id"), item.get("cve_id")] + [x.get("value") for x in item.get("identifiers", [])]
    return finding(ids, item.get("summary"), "GitHub Advisory Database", item.get("html_url"),
                   scores=cvss_scores(entries, "GitHub Advisory Database"), severity=item.get("severity"),
                   published=item.get("published_at"), modified=item.get("updated_at"), affected=affected)


def discover(args, client, report):
    source = args.source
    if source == "auto":
        source = "github" if args.ecosystem or args.package else "nvd"
    if source == "nvd" and (args.ecosystem or args.package):
        raise ValueError("Use --source github for ecosystem/package discovery")
    if source == "github" and (args.vendor or args.product):
        raise ValueError("Use --source nvd for vendor/product discovery")
    report["target"] = {"kind": "advisory_query", "source": source,
                        "vendor": args.vendor, "product": args.product, "query": args.query}
    report["limitations"] += ["Discovery returns published advisory records; it does not establish repository exposure.",
                               "Coverage is limited to the selected advisory source."]
    rows, count, total, next_page = [], 0, None, None
    if source == "nvd":
        params = {"resultsPerPage": min(args.limit, 2000), "startIndex": 0}
        if args.cve:
            params["cveId"] = args.cve.upper()
        if args.query:
            params["keywordSearch"] = args.query
        if args.vendor or args.product:
            # CPE component identity is explicit: no guess that "java" means a particular JDK.
            params["virtualMatchString"] = "cpe:2.3:*:" + (args.vendor or "*") + ":" + (args.product or "*") + ":*:*:*:*:*:*:*:*"
            report["notes"].append("Vendor/product match NVD CPE component names. Use --query for broad text discovery; Java distributions have distinct CPE identities.")
        for after, before, prefix in ((args.published_after, args.published_before, "pub"), (args.updated_after, None, "lastMod")):
            if after or before:
                end = timestamp(before) if before else timestamp(now())
                start = timestamp(after) if after else end - timedelta(days=120)
                if end <= start or end - start > timedelta(days=120):
                    raise ValueError("NVD date windows must be positive and at most 120 days; provide both publication bounds")
                params[prefix + "StartDate"] = start.isoformat()
                params[prefix + "EndDate"] = end.isoformat()
        while count < args.limit:
            url = NVD + "?" + urllib.parse.urlencode(params)
            body, _ = client.get(url)
            if not isinstance(body.get("vulnerabilities"), list) or "totalResults" not in body:
                raise SourceError("Unexpected NVD response schema")
            batch = body["vulnerabilities"]
            total = body["totalResults"]
            remaining = args.limit - count
            for item in batch[:remaining]:
                if item["cve"].get("vulnStatus") != "Rejected":
                    rows.append(nvd_row(item["cve"]))
            count += min(len(batch), remaining)
            report["findings"] = rows[:]
            params["startIndex"] += len(batch)
            if params["startIndex"] >= total:
                break
            if not batch:
                raise SourceError("NVD pagination stalled before totalResults")
    else:
        params = {"per_page": min(args.limit, 100), "page": 1, "type": "reviewed"}
        if args.ecosystem:
            params["ecosystem"] = ecosystem(args.ecosystem)
        if args.package:
            params["affects"] = args.package
        if args.cve:
            params["cve_id"] = args.cve.upper()
        if args.published_after or args.published_before:
            params["published"] = (args.published_after or "*") + ".." + (args.published_before or "*")
        if args.updated_after:
            params["modified"] = ">=" + args.updated_after
        if args.query:
            raise ValueError("--query is supported by NVD; use --package for GitHub advisories")
        while count < args.limit:
            body, headers = client.get(GHSA + "?" + urllib.parse.urlencode(params))
            if not isinstance(body, list):
                raise SourceError("Unexpected GitHub advisory response schema")
            remaining = args.limit - count
            rows += [ghsa_row(x) for x in body[:remaining] if not x.get("withdrawn_at")]
            count += min(len(body), remaining)
            report["findings"] = rows[:]
            next_page = 'rel="next"' in headers.get("link", "") or len(body) > remaining
            if not next_page:
                break
            if not body:
                raise SourceError("GitHub advisory pagination stalled")
            params["page"] += 1
    truncated = count < total if total is not None else bool(next_page)
    report["coverage"].append({"source": source, "status": "truncated" if truncated else "ok",
                               "records_examined": count, "total_records": total,
                               "truncated": truncated, "limit": args.limit,
                               "receipts": client.receipts[:]})
    return rows


def discover_auto(args, client, report):
    """Prefer public aggregation only where the original query can fall back.

    Explicit sources and NVD-only criteria retain their original semantics.
    A limited feed is a successful but incomplete response, not an outage.
    """
    if args.source != 'auto' or args.vendor or args.product or args.query:
        return discover(args, client, report)
    from .cvenow import discover as aggregated, ECOSYSTEMS as aggregator_ecosystems
    if args.ecosystem and ecosystem(args.ecosystem) not in aggregator_ecosystems:
        return discover(args, client, report)
    from .store import new_report

    selected = copy.copy(args)
    selected.source = 'cve-now'
    coverage_start = len(report['coverage'])
    try:
        aggregated(selected, client, report)
    except (SourceError, OSError, ValueError) as exc:
        report['coverage'].append({'source': 'cve.now', 'status': 'error', 'error': str(exc)})
    preferred = report['coverage'][coverage_start:]
    failed = any(c['status'] == 'error' for c in preferred)
    stale = any(c.get('stale') or any(r.get('stale') for r in c.get('receipts', [])) for c in preferred)
    report['target']['requested_source'] = 'auto'
    report['source_attempts'] = [{'source': 'cve-now', 'selected': not (failed or stale),
                                  'status': 'error' if failed else 'stale' if stale else preferred[0]['status'],
                                  'coverage': copy.deepcopy(preferred)}]
    if not (failed or stale):
        return report['findings']

    fallback = 'github' if args.ecosystem or args.package else 'nvd'
    report['notes'].append('Automatic discovery: cve.now failed or returned stale data; using ' + fallback +
                           '. Any partial aggregator findings are retained with source-attempt evidence; coverage describes the selected fallback source.')
    for row in report['findings']:
        row['discovery_attempt'] = {'source': 'cve-now', 'status': 'unverified_preferred_source'}
    # Failure diagnostics remain in source_attempts rather than being represented
    # as failed coverage of a source that was successfully replaced. Fallback
    # errors/truncation/staleness still make the selected assessment incomplete.
    del report['coverage'][coverage_start:]
    selected.source = fallback
    child = new_report('find', {})
    receipt_start = len(client.receipts)
    try:
        discover(selected, client, child)
    except (SourceError, OSError, ValueError) as exc:
        child['coverage'].append({'source': fallback, 'status': 'error', 'error': str(exc)})
    for item in child['coverage']:
        # Legacy discover() records all client receipts. Do not attach the stale
        # preferred attempt to fresh fallback coverage, or recovery stays stale.
        item['receipts'] = client.receipts[receipt_start:]
    report['findings'].extend(child['findings'])
    report['coverage'].extend(child['coverage'])
    report['notes'].extend(child['notes'])
    report['limitations'] = list(dict.fromkeys(report['limitations'] + child['limitations']))
    report['target'] = {**child['target'], 'requested_source': 'auto', 'preferred_source': 'cve-now'}
    report['source_attempts'].append({'source': fallback, 'selected': True, 'status': child['coverage'][-1]['status'], 'coverage': copy.deepcopy(child['coverage'])})
    return report['findings']


def enrich_kev(client, report):
    start = len(client.receipts)
    try:
        body, _ = client.get(KEV)
        if not isinstance(body.get("vulnerabilities"), list):
            raise SourceError("Unexpected KEV response schema")
        ids = {x["cveID"] for x in body["vulnerabilities"]}
        for row in report["findings"]:
            row["known_exploited"] = bool(ids & set(row["aliases"]))
            row["exploitation_source"] = {"url": KEV, "catalog_version": body.get("catalogVersion"),
                                           "fetched_at": client.receipts[-1]["fetched_at"]}
        report["coverage"].append({"source": "CISA KEV", "status": "ok", "receipts": client.receipts[start:]})
    except SourceError as exc:
        report["coverage"].append({"source": "CISA KEV", "status": "error", "error": str(exc)})
