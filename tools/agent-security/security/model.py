"""Versioned evidence model, advisory normalization, and shared report filters."""
from __future__ import annotations

import copy
import math
from datetime import datetime, timezone

SCHEMA_VERSION = 1
ECOSYSTEMS = {"python": "pip", "pypi": "pip", "pip": "pip", "javascript": "npm",
              "node": "npm", "npm": "npm", "php": "composer", "composer": "composer", "packagist": "composer",
              "java": "maven", "maven": "maven", "go": "go", "rust": "rust",
              "crates.io": "rust", "rubygems": "rubygems", "nuget": "nuget",
              "pub": "pub", "erlang": "erlang", "actions": "actions", "swift": "swift"}


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def timestamp(value):
    if not value:
        return None
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result.replace(tzinfo=result.tzinfo or timezone.utc).astimezone(timezone.utc)


def ecosystem(value):
    return ECOSYSTEMS.get((value or "").lower(), (value or "").lower())


def score_severity(score):
    if score is None:
        return "unknown"
    return "critical" if score >= 9 else "high" if score >= 7 else "medium" if score >= 4 else "low" if score > 0 else "none"


def numeric_score(value):
    try:
        score = float(value)
        return score if math.isfinite(score) and 0 <= score <= 10 else None
    except (TypeError, ValueError):
        return None


def cvss_scores(entries, source):
    """Use the maintained cvss library for vectors; retain raw vectors if absent."""
    scores = []
    for entry in entries or []:
        vector = entry.get("vectorString") or entry.get("vector_string")
        if not vector and isinstance(entry.get("score"), str) and "/" in entry["score"]:
            vector = entry["score"]
        number = numeric_score(entry.get("baseScore", entry.get("score")))
        version = entry.get("version")
        if isinstance(vector, str) and "/" in vector:
            version = "4.0" if vector.startswith("CVSS:4.") else "3.1" if vector.startswith("CVSS:3.1") else "3.0" if vector.startswith("CVSS:3.0") else "2.0"
            if number is None:
                try:
                    import cvss
                    cls = cvss.CVSS4 if version == "4.0" else cvss.CVSS3 if version.startswith("3") else cvss.CVSS2
                    number = float(cls(vector).scores()[0])
                except Exception:
                    # A missing library or malformed upstream vector must not erase evidence.
                    number = None
        if number is not None or vector:
            scores.append({"score": number, "version": version, "vector": vector, "source": source})
    return scores


def finding(ids, summary, source, url, *, scores=None, severity=None, published=None,
            modified=None, package=None, affected=None, evidence=None):
    scores = scores or []
    numbers = [s["score"] for s in scores if s.get("score") is not None]
    score = max(numbers) if numbers else None
    identifiers = sorted(set(x for x in ids if x))
    preferred = next((x for x in identifiers if x.startswith("CVE-")), identifiers[0])
    return {"id": preferred, "aliases": identifiers, "summary": summary or "",
            "sources": [{"name": source, "url": url}], "scores": scores,
            "cvss": score, "severity": score_severity(score) if score is not None else (severity or "unknown").lower(),
            "published": published, "modified": modified, "package": package,
            "advisory_dates": [{"source": source, "url": url, "published": published, "modified": modified}],
            "matched_targets": [], "target_matches": [],
            "affected": affected or [], "evidence": evidence or [],
            "known_exploited": None, "exploitation_source": None,
            "exploitability": "not_assessed"}


def merge_findings(rows):
    """Union aliases transitively, keeping distinct versions and occurrences separate."""
    merged = []
    for original in rows:
        row = copy.deepcopy(original)
        indices = [i for i, old in enumerate(merged)
                   if old.get('repository_target') == row.get('repository_target')
                   and old["package"] == row["package"] and set(old["aliases"]) & set(row["aliases"])]
        for i in reversed(indices):
            old = merged.pop(i)
            if row["severity"] == "unknown" and old["severity"] != "unknown":
                row["severity"] = old["severity"]
            for field in ("aliases", "scores", "sources", "affected", "evidence", "advisory_dates", "matched_targets", "target_matches"):
                row.setdefault(field, [])
                row[field] += [x for x in old.get(field, []) if x not in row[field]]
            if not row["published"] or (old["published"] and timestamp(old["published"]) < timestamp(row["published"])):
                row["published"] = old["published"]
            if old["modified"] and (not row["modified"] or timestamp(old["modified"]) > timestamp(row["modified"])):
                row["modified"] = old["modified"]
            if old["known_exploited"] is True:
                row["known_exploited"] = True
                row["exploitation_source"] = old["exploitation_source"]
        row["aliases"] = sorted(set(row["aliases"]))
        row['matched_targets'] = sorted(set(row.get('matched_targets', [])))
        row["id"] = next((x for x in row["aliases"] if x.startswith("CVE-")), row["aliases"][0])
        numbers = [x["score"] for x in row["scores"] if x["score"] is not None]
        row["cvss"] = max(numbers) if numbers else None
        if numbers:
            row["severity"] = score_severity(row["cvss"])
        merged.append(row)
    return sorted(merged, key=lambda r: (-(r["cvss"] if r["cvss"] is not None else -1), r["id"], str(r["package"])))


def matches(row, args):
    targets = getattr(args, 'target', [])
    if targets and not set(targets) & set(row.get('matched_targets', [])):
        return False
    if args.cve and args.cve.upper() not in row["aliases"]:
        return False
    if args.ecosystem:
        packages = ([row["package"]] if row["package"] else []) + [x.get("package", {}) for x in row["affected"]]
        if not any(ecosystem(p.get("ecosystem")) == ecosystem(args.ecosystem) for p in packages):
            return False
    if args.package:
        packages = ([row["package"]] if row["package"] else []) + [x.get("package", {}) for x in row["affected"]]
        if not any(p.get("name", "").lower() == args.package.lower() for p in packages):
            return False
    if args.cvss_min is not None or args.cvss_gt is not None:
        if row["cvss"] is None:
            if not args.include_unscored:
                return False
        elif ((args.cvss_min is not None and row["cvss"] < args.cvss_min)
              or (args.cvss_gt is not None and row["cvss"] <= args.cvss_gt)):
            return False
    if args.severity and row["severity"] not in args.severity.split(","):
        return False
    date_filters = (("published_after", "published", "after"), ("published_before", "published", "before"), ("updated_after", "modified", "after"))
    if any(getattr(args, option) for option, _, _ in date_filters):
        events = ([item for item in row.get('target_matches', []) if item['target'] in targets] if targets
                  else row.get('advisory_dates') or [row])
        def dates_match(event):
            for option, field, op in date_filters:
                boundary = getattr(args, option)
                if boundary:
                    actual = timestamp(event.get(field))
                    if actual is None or (op == 'after' and actual < timestamp(boundary)) or (op == 'before' and actual >= timestamp(boundary)):
                        return False
            return True
        if not any(dates_match(event) for event in events):
            return False
    if args.known_exploited and row["known_exploited"] is not True:
        return False
    if args.fix_available:
        for affected in row['affected']:
            package = affected.get('package') or row.get('package') or {}
            if args.package and package.get('name', '').lower() != args.package.lower():
                continue
            if args.ecosystem and ecosystem(package.get('ecosystem')) != ecosystem(args.ecosystem):
                continue
            if affected.get('fixed_versions'):
                break
        else:
            return False
    return True


def present(report, args):
    payload = copy.deepcopy(report)
    rows = report["findings"]
    payload["findings"] = [x for x in rows if matches(x, args)]
    payload["summary"] = {"total": len(rows), "shown": len(payload["findings"]),
                          "excluded": len(rows) - len(payload["findings"]),
                          "unscored": sum(x["cvss"] is None for x in rows)}
    payload["filters"] = {k: getattr(args, k) for k in ("cve", "ecosystem", "package", "cvss_min", "cvss_gt", "severity", "published_after", "published_before", "updated_after", "known_exploited", "fix_available", "include_unscored") if getattr(args, k) is not None}
    if getattr(args, 'target', []):
        payload['filters']['targets'] = list(dict.fromkeys(args.target))
    if report.get('target', {}).get('kind') == 'github_batch':
        payload['repository_summaries'] = []
        shared = [item for item in report['coverage'] if not item.get('repository_target')]
        for entry in report['target']['repositories']:
            def belongs(item):
                return item.get('repository_target', {}).get('entry_id') == entry['entry_id']
            coverage = shared + [item for item in report['coverage'] if belongs(item)]
            child = next((item for item in report.get('repositories', []) if item['entry_id'] == entry['entry_id']), None)
            selected = [row for row in rows if belongs(row)]
            payload['repository_summaries'].append({**entry,
                'commit': child['target'].get('commit') if child else None,
                'status': 'complete' if child and child['source_scan_status'] == 'complete' and all(item['status'] == 'ok' for item in coverage) else 'incomplete',
                'total': len(selected), 'shown': sum(matches(row, args) for row in selected),
                'unscored': sum(row['cvss'] is None for row in selected)})
    if report.get('target', {}).get('kind') == 'multi_advisory_query':
        payload['target_summaries'] = []
        for target in report['target']['targets']:
            coverage = [item for item in report['coverage'] if item.get('target') == target]
            target_args = copy.copy(args)
            target_args.target = [target]
            active = not getattr(args, 'target', []) or target in args.target
            payload['target_summaries'].append({'target': target, 'queries': len(coverage),
                'status': 'complete' if coverage and all(item['status'] == 'ok' for item in coverage) else 'incomplete',
                'total': sum(target in row.get('matched_targets', []) for row in rows),
                'shown': sum(matches(row, target_args) for row in rows) if active else 0,
                'query_statuses': {status: sum(item['status'] == status for item in coverage) for status in sorted({item['status'] for item in coverage})}})
    return payload
