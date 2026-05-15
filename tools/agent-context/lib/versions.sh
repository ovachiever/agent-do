#!/usr/bin/env bash
# lib/versions.sh — Version currency checks for agent-context packages.

cmd_versions() {
    local subcmd="${1:-list}"
    shift 2>/dev/null || true
    case "$subcmd" in
        check)
            _context_versions_check "$@"
            ;;
        list|status)
            _context_versions_list "$@"
            ;;
        outdated)
            _context_versions_list --outdated "$@"
            ;;
        sources|source-coverage)
            _context_versions_sources "$@"
            ;;
        *)
            die "Usage: agent-context versions [check|list|outdated|sources] [--all|--due|id] [--limit N]"
            ;;
    esac
}

_context_versions_sources() {
    local outdated=false limit="500"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --outdated) outdated=true; shift ;;
            --limit) limit="${2:-500}"; shift 2 ;;
            --all) shift ;;
            *) shift ;;
        esac
    done
    ensure_init

    python3 - "$CONTEXT_HOME/config.yaml" "$CONTEXT_INDEX_DB" "$outdated" "$limit" "${OUTPUT_FORMAT:-text}" <<'PY'
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


config_path, db_path, outdated_raw, limit_raw, output_format = sys.argv[1:6]
outdated = outdated_raw == "true"
limit = int(limit_raw)
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
USER_AGENT = "agent-do-context/1.0"
CHANNELS = {"latest", "current", "stable", "main", "head", "floating"}
OUTDATED = {"behind_major", "behind_minor", "behind_patch", "registry_failed"}


def scalar(raw):
    raw = raw.strip()
    if raw == "[]":
        return []
    if raw in {"null", "~"}:
        return None
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [scalar(part.strip()) for part in inner.split(",")]
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    return raw


def parse_sources(path):
    text = Path(path).read_text() if Path(path).exists() else ""
    sources = []
    current = None
    in_sources = False
    for line in text.splitlines():
        if line.startswith("sources:"):
            in_sources = True
            continue
        if in_sources and line and not line.startswith((" ", "\t", "#")):
            break
        if not in_sources:
            continue
        if line.startswith("  - "):
            current = {}
            sources.append(current)
            m = re.match(r"^  -\s+name:\s*(.*)$", line)
            if m:
                current["name"] = scalar(m.group(1))
            continue
        if current is None:
            continue
        m = re.match(r"^    ([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            current[m.group(1)] = scalar(m.group(2))
    return sources


def iso(value):
    return value.replace(microsecond=0).isoformat()


def parse_ttl(value, default_seconds=86400):
    if not value:
        return default_seconds
    m = re.fullmatch(r"(\d+)\s*([smhdw]?)", str(value).strip().lower())
    if not m:
        return default_seconds
    amount = int(m.group(1))
    unit = m.group(2) or "s"
    return amount * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}.get(unit, 1)


def parse_ver(value):
    if not value:
        return None
    value = str(value).strip().lower()
    value = re.sub(r"^[^0-9]*", "", value)
    nums = re.findall(r"\d+", value)
    if not nums:
        return None
    return tuple(int(n) for n in nums[:3])


def compare_status(doc_version, latest_version, doc_channel):
    if doc_channel in CHANNELS and not doc_version:
        return "floating_fresh"
    latest = parse_ver(latest_version)
    doc = parse_ver(doc_version)
    if not latest or not doc:
        return "unknown"
    latest = latest + (0,) * (3 - len(latest))
    doc = doc + (0,) * (3 - len(doc))
    if doc[0] < latest[0]:
        return "behind_major"
    if doc[0] > latest[0]:
        return "future"
    if doc[1] < latest[1] and len(parse_ver(doc_version) or ()) > 1:
        return "behind_minor"
    if doc[2] < latest[2] and len(parse_ver(doc_version) or ()) > 2:
        return "behind_patch"
    return "current"


def split_doc_version(value):
    value = str(value or "").strip()
    if value.lower() in CHANNELS:
        return "", value.lower()
    return value, ""


def registry_url(source):
    registry = str(source.get("registry") or source.get("ecosystem") or "").lower()
    package = str(source.get("package_name") or source.get("package") or "")
    explicit = str(source.get("registry_url") or "")
    if registry == "npm":
        base = explicit or os.environ.get("AGENT_CONTEXT_NPM_REGISTRY") or "https://registry.npmjs.org"
        return f"{base.rstrip('/')}/{urllib.parse.quote(package, safe='@')}"
    if registry == "pypi":
        base = explicit or os.environ.get("AGENT_CONTEXT_PYPI_REGISTRY") or "https://pypi.org/pypi"
        return f"{base.rstrip('/')}/{urllib.parse.quote(package)}/json"
    if registry == "crates":
        base = explicit or os.environ.get("AGENT_CONTEXT_CRATES_REGISTRY") or "https://crates.io/api/v1/crates"
        return f"{base.rstrip('/')}/{urllib.parse.quote(package)}"
    if registry == "pub":
        base = explicit or os.environ.get("AGENT_CONTEXT_PUB_REGISTRY") or "https://pub.dev/api/packages"
        return f"{base.rstrip('/')}/{urllib.parse.quote(package)}"
    if registry == "github":
        return explicit or f"https://api.github.com/repos/{package}/releases/latest"
    return ""


def latest_from(registry, payload):
    if registry == "npm":
        return payload.get("dist-tags", {}).get("latest", "")
    if registry == "pypi":
        return payload.get("info", {}).get("version", "")
    if registry == "crates":
        crate = payload.get("crate", {})
        return crate.get("max_stable_version") or crate.get("max_version") or ""
    if registry == "pub":
        return payload.get("latest", {}).get("version", "")
    if registry == "github":
        return payload.get("tag_name", "")
    return ""


def fetch_latest(conn, source):
    ecosystem = str(source.get("ecosystem") or source.get("registry") or "").lower()
    registry = str(source.get("registry") or ecosystem).lower()
    package = str(source.get("package_name") or source.get("package") or "")
    url = registry_url(source)
    if not registry or not package or not url:
        return "", "unknown", "no version registry configured"

    cached = conn.execute(
        """
        SELECT latest_version, status, error, expires_at
        FROM registry_version_cache
        WHERE ecosystem = ? AND package_name = ? AND registry = ?
        """,
        (ecosystem, package, registry),
    ).fetchone()
    if cached and cached["expires_at"]:
        try:
            if dt.datetime.fromisoformat(cached["expires_at"].replace("Z", "+00:00")) > now:
                return cached["latest_version"] or "", cached["status"] or "unknown", cached["error"] or ""
        except ValueError:
            pass

    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        latest = latest_from(registry, payload)
        status = "ok" if latest else "unknown"
        error = "" if latest else "latest version missing from registry response"
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        latest = ""
        status = "failed"
        error = str(exc)

    expires_at = now + dt.timedelta(seconds=parse_ttl(source.get("currency_ttl"), 86400))
    conn.execute(
        """
        INSERT OR REPLACE INTO registry_version_cache
        (ecosystem, package_name, registry, registry_url, latest_version, latest_stable_version,
         dist_tag, checked_at, expires_at, status, error)
        VALUES (?, ?, ?, ?, ?, ?, 'latest', ?, ?, ?, ?)
        """,
        (ecosystem, package, registry, url, latest, latest, iso(now), iso(expires_at), status, error),
    )
    return latest, status, error


sources = parse_sources(config_path)
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA busy_timeout = 5000")
conn.row_factory = sqlite3.Row

items = []
for source in sources:
    name = str(source.get("name") or "")
    registry = str(source.get("registry") or source.get("ecosystem") or "")
    package = str(source.get("package_name") or source.get("package") or "")
    doc_version, doc_channel = split_doc_version(source.get("doc_version"))
    latest = ""
    error = ""

    if registry and package:
        latest, registry_status, registry_error = fetch_latest(conn, source)
        if registry_status == "failed":
            status = "registry_failed"
            error = registry_error
        else:
            status = compare_status(doc_version, latest, doc_channel)
            error = registry_error
    elif source.get("doc_version"):
        status = "archived" if str(source.get("doc_version")).lower() == "archived" else "doc_channel"
    else:
        status = "untracked"

    item = {
        "name": name,
        "kind": source.get("kind") or "",
        "trust": source.get("trust") or "",
        "location": source.get("location") or source.get("url") or source.get("path") or "",
        "registry": registry,
        "package_name": package,
        "doc_version": doc_version or doc_channel or str(source.get("doc_version") or ""),
        "latest_version": latest,
        "version_status": status,
        "version_policy": source.get("version_policy") or "",
        "currency_ttl": source.get("currency_ttl") or "",
        "error": error,
    }
    if outdated and status not in OUTDATED:
        continue
    items.append(item)
    if len(items) >= limit:
        break

conn.commit()
conn.close()

counts = Counter(item["version_status"] for item in items)
summary = {
    "sources": len(sources),
    "shown": len(items),
    "registry_backed": sum(1 for item in items if item["registry"] and item["package_name"]),
    "doc_only": sum(1 for item in items if item["version_status"] in {"doc_channel", "archived"}),
    "behind": sum(counts.get(key, 0) for key in ("behind_major", "behind_minor", "behind_patch")),
    "registry_failed": counts.get("registry_failed", 0),
    "untracked": counts.get("untracked", 0),
}
success = summary["registry_failed"] == 0

if output_format == "json":
    print(json.dumps({"success": success, "summary": summary, "results": items}, indent=2))
else:
    if not items:
        print("No source version records." if not outdated else "No outdated source docs found.")
    else:
        print(
            f"{len(items)} source version record(s): "
            f"{summary['registry_backed']} registry-backed, {summary['doc_only']} doc-channel, "
            f"{summary['behind']} behind, {summary['registry_failed']} registry failed"
        )
        print("")
        for item in items:
            package = item["package_name"] or "doc-channel"
            print(
                f"  {item['version_status']:15s} {item['name']} "
                f"doc={item['doc_version'] or 'unknown'} latest={item['latest_version'] or 'unknown'} "
                f"pkg={package}"
            )
            if item["error"]:
                print(f"      {item['error']}")
PY
}

_context_versions_check() {
    local target="" all=false due=false limit="25" quiet=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --all) all=true; shift ;;
            --due) due=true; shift ;;
            --limit) limit="${2:-25}"; shift 2 ;;
            --quiet) quiet=true; shift ;;
            *) target="$1"; shift ;;
        esac
    done
    [[ -n "$target" || "$all" == "true" || "$due" == "true" ]] || due=true
    ensure_init

    python3 - "$CONTEXT_INDEX_DB" "$CONTEXT_HOME/config.yaml" "$target" "$all" "$due" "$limit" "$quiet" "${OUTPUT_FORMAT:-text}" <<'PY'
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


db_path, config_path, target, all_flag, due_flag, limit_raw, quiet_raw, output_format = sys.argv[1:9]
all_flag = all_flag == "true"
due_flag = due_flag == "true"
limit = int(limit_raw)
quiet = quiet_raw == "true"
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
USER_AGENT = "agent-do-context/1.0"


KNOWN = [
    (("tanstack-query", "react-query"), "npm", "@tanstack/react-query"),
    (("tanstack-router",), "npm", "@tanstack/react-router"),
    (("nextjs", "next.js", "next "), "npm", "next"),
    (("react-native",), "npm", "react-native"),
    (("react",), "npm", "react"),
    (("expo",), "npm", "expo"),
    (("typescript",), "npm", "typescript"),
    (("tailwind",), "npm", "tailwindcss"),
    (("vite",), "npm", "vite"),
    (("vitest",), "npm", "vitest"),
    (("svelte",), "npm", "svelte"),
    (("vue",), "npm", "vue"),
    (("nuxt",), "npm", "nuxt"),
    (("astro",), "npm", "astro"),
    (("openai",), "npm", "openai"),
    (("anthropic", "claude"), "npm", "@anthropic-ai/sdk"),
    (("ai-sdk", "vercel-ai"), "npm", "ai"),
    (("supabase",), "npm", "@supabase/supabase-js"),
    (("clerk",), "npm", "@clerk/nextjs"),
    (("stripe",), "npm", "stripe"),
    (("prisma",), "npm", "prisma"),
    (("playwright",), "npm", "@playwright/test"),
    (("textual",), "pypi", "textual"),
    (("fastapi",), "pypi", "fastapi"),
    (("django",), "pypi", "django"),
    (("flask",), "pypi", "flask"),
    (("pydantic",), "pypi", "pydantic"),
    (("pytest",), "pypi", "pytest"),
    (("ruff",), "pypi", "ruff"),
    (("requests",), "pypi", "requests"),
    (("axum",), "crates", "axum"),
    (("tokio",), "crates", "tokio"),
    (("serde",), "crates", "serde"),
    (("reqwest",), "crates", "reqwest"),
    (("clap",), "crates", "clap"),
    (("tracing",), "crates", "tracing"),
    (("sqlx",), "crates", "sqlx"),
    (("actix",), "crates", "actix-web"),
    (("tauri",), "crates", "tauri"),
    (("riverpod",), "pub", "riverpod"),
    (("go_router", "go-router"), "pub", "go_router"),
    (("dio",), "pub", "dio"),
    (("bloc",), "pub", "bloc"),
]


def parse_sources(path):
    text = Path(path).read_text() if Path(path).exists() else ""
    sources = []
    current = None
    in_sources = False
    for line in text.splitlines():
        if line.startswith("sources:"):
            in_sources = True
            continue
        if in_sources and line and not line.startswith((" ", "\t", "#")):
            break
        if not in_sources:
            continue
        if line.startswith("  - "):
            current = {}
            sources.append(current)
            m = re.match(r"^  -\s+name:\s*(.*)$", line)
            if m:
                current["name"] = scalar(m.group(1))
            continue
        if current is None:
            continue
        m = re.match(r"^    ([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            current[m.group(1)] = scalar(m.group(2))
    return sources


def scalar(raw):
    raw = raw.strip()
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    if raw in {"true", "false"}:
        return raw == "true"
    if raw == "null":
        return None
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    return raw


def make_id(value):
    value = re.sub(r"^https?://", "", value or "")
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()[:80]


def iso(value):
    return value.replace(microsecond=0).isoformat()


def parse_ttl(value, default_seconds=86400):
    if not value:
        return default_seconds
    m = re.fullmatch(r"(\d+)\s*([smhdw]?)", str(value).strip().lower())
    if not m:
        return default_seconds
    amount = int(m.group(1))
    unit = m.group(2) or "s"
    return amount * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}.get(unit, 1)


def parse_ver(value):
    if not value:
        return None
    value = str(value).strip().lower()
    value = re.sub(r"^[^0-9]*", "", value)
    nums = re.findall(r"\d+", value)
    if not nums:
        return None
    return tuple(int(n) for n in nums[:3])


def compare_status(doc_version, latest_version, doc_channel):
    if doc_channel in {"latest", "current", "stable", "main", "head", "floating"} and not doc_version:
        return "floating_fresh"
    latest = parse_ver(latest_version)
    doc = parse_ver(doc_version)
    if not latest:
        return "unknown"
    if not doc:
        return "unknown"
    latest = latest + (0,) * (3 - len(latest))
    doc = doc + (0,) * (3 - len(doc))
    if doc[0] < latest[0]:
        return "behind_major"
    if doc[0] > latest[0]:
        return "future"
    if doc[1] < latest[1] and len(parse_ver(doc_version) or ()) > 1:
        return "behind_minor"
    if doc[2] < latest[2] and len(parse_ver(doc_version) or ()) > 2:
        return "behind_patch"
    return "current"


def detect_doc_version(row, source_config):
    explicit = source_config.get("doc_version") or row["doc_version"]
    if explicit:
        value = str(explicit)
        if value.lower() in {"latest", "current", "stable", "main", "head"}:
            return "", value.lower()
        return value, ""

    blob = " ".join(str(row[key] or "") for key in ("name", "source", "canonical_url", "tags")).lower()
    if any(marker in blob for marker in ["/latest", "latest/", "/current", "current/", "/stable", "stable/", "/main", "/head"]):
        return "", "latest"

    patterns = [
        r"(?:^|[/_.-])v(?:ersion)?[-_/ ]?(\d+(?:\.\d+){0,2})(?:$|[/_.-])",
        r"(?:^|[/_.-])docs[-_/ ]?(\d+(?:\.\d+){0,2})(?:$|[/_.-])",
        r"(?:^|[/_.-])sdk[-_/ ]?(\d+(?:\.\d+){0,2})(?:$|[/_.-])",
    ]
    for pattern in patterns:
        m = re.search(pattern, blob)
        if m:
            first = int(m.group(1).split(".")[0])
            if 0 < first < 100:
                return m.group(1), ""
    return "", "floating"


def source_config_for(row, sources):
    source = row["source"] or ""
    canonical = row["canonical_url"] or ""
    for item in sources:
        locations = [str(item.get(key) or "") for key in ("name", "location", "url", "path")]
        if row["name"] == item.get("name") or row["id"] == make_id(str(item.get("name") or "")):
            return item
        for location in [value.rstrip("/") for value in locations if value]:
            if source.rstrip("/") == location or canonical.rstrip("/") == location:
                return item
            if location and (source.startswith(location + "/") or canonical.startswith(location + "/")):
                return item
    return {}


def infer_policy(row, source_config):
    source_config_has_version = any(
        source_config.get(key)
        for key in ("ecosystem", "package_name", "package", "registry", "registry_url", "doc_version", "version_policy")
    )
    is_local = str(row["source_kind"] or "").startswith("local") or row["type"] in {"skill", "local"}

    ecosystem = source_config.get("ecosystem") or (row["version_registry"] if not is_local else "") or ""
    package_name = source_config.get("package_name") or source_config.get("package") or (row["version_package"] if not is_local else "") or ""
    registry = source_config.get("registry") or (row["version_registry"] if not is_local else "") or ecosystem
    registry_url = source_config.get("registry_url") or ""
    version_policy = source_config.get("version_policy") or row["version_policy"] or "latest-stable"
    currency_ttl = source_config.get("currency_ttl") or "1d"

    if is_local and not source_config_has_version:
        return {
            "ecosystem": "",
            "package_name": "",
            "registry": "",
            "registry_url": "",
            "doc_version": "",
            "doc_channel": "",
            "version_policy": version_policy,
            "currency_ttl": currency_ttl,
        }

    if not ecosystem or not package_name:
        blob = " ".join(str(row[key] or "") for key in ("id", "name", "canonical_url", "tags")).lower()
        for needles, candidate_ecosystem, candidate_package in KNOWN:
            if any(needle in blob for needle in needles):
                ecosystem = ecosystem or candidate_ecosystem
                package_name = package_name or candidate_package
                registry = registry or candidate_ecosystem
                break

    doc_version, doc_channel = detect_doc_version(row, source_config)
    return {
        "ecosystem": ecosystem,
        "package_name": package_name,
        "registry": registry or ecosystem,
        "registry_url": registry_url,
        "doc_version": doc_version,
        "doc_channel": doc_channel,
        "version_policy": version_policy,
        "currency_ttl": currency_ttl,
    }


def registry_url(policy):
    registry = (policy["registry"] or policy["ecosystem"] or "").lower()
    package = policy["package_name"]
    explicit = policy.get("registry_url") or ""
    if registry == "npm":
        base = explicit or os.environ.get("AGENT_CONTEXT_NPM_REGISTRY") or "https://registry.npmjs.org"
        return f"{base.rstrip('/')}/{urllib.parse.quote(package, safe='@')}"
    if registry == "pypi":
        base = explicit or os.environ.get("AGENT_CONTEXT_PYPI_REGISTRY") or "https://pypi.org/pypi"
        return f"{base.rstrip('/')}/{urllib.parse.quote(package)}/json"
    if registry == "crates":
        base = explicit or os.environ.get("AGENT_CONTEXT_CRATES_REGISTRY") or "https://crates.io/api/v1/crates"
        return f"{base.rstrip('/')}/{urllib.parse.quote(package)}"
    if registry == "pub":
        base = explicit or os.environ.get("AGENT_CONTEXT_PUB_REGISTRY") or "https://pub.dev/api/packages"
        return f"{base.rstrip('/')}/{urllib.parse.quote(package)}"
    if registry == "github":
        base = explicit or f"https://api.github.com/repos/{package}/releases/latest"
        return base
    return ""


def fetch_latest(conn, policy):
    registry = (policy["registry"] or policy["ecosystem"] or "").lower()
    package = policy["package_name"]
    url = registry_url(policy)
    if not registry or not package or not url:
        return "", "unknown", "no version registry inferred"

    cached = conn.execute(
        """
        SELECT latest_version, status, error, expires_at
        FROM registry_version_cache
        WHERE ecosystem = ? AND package_name = ? AND registry = ?
        """,
        (policy["ecosystem"], package, registry),
    ).fetchone()
    if cached and cached["expires_at"]:
        try:
            if dt.datetime.fromisoformat(cached["expires_at"].replace("Z", "+00:00")) > now:
                return cached["latest_version"] or "", cached["status"] or "unknown", cached["error"] or ""
        except ValueError:
            pass

    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        if registry == "npm":
            latest = payload.get("dist-tags", {}).get("latest", "")
        elif registry == "pypi":
            latest = payload.get("info", {}).get("version", "")
        elif registry == "crates":
            crate = payload.get("crate", {})
            latest = crate.get("max_stable_version") or crate.get("max_version") or ""
        elif registry == "pub":
            latest = payload.get("latest", {}).get("version", "")
        elif registry == "github":
            latest = payload.get("tag_name", "")
        else:
            latest = ""
        status = "ok" if latest else "unknown"
        error = "" if latest else "latest version missing from registry response"
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        latest = ""
        status = "failed"
        error = str(exc)

    expires_at = now + dt.timedelta(seconds=parse_ttl(policy.get("currency_ttl"), 86400))
    conn.execute(
        """
        INSERT OR REPLACE INTO registry_version_cache
        (ecosystem, package_name, registry, registry_url, latest_version, latest_stable_version,
         dist_tag, checked_at, expires_at, status, error)
        VALUES (?, ?, ?, ?, ?, ?, 'latest', ?, ?, ?, ?)
        """,
        (policy["ecosystem"], package, registry, url, latest, latest, iso(now), iso(expires_at), status, error),
    )
    return latest, status, error


sources = parse_sources(config_path)
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA busy_timeout = 5000")
conn.row_factory = sqlite3.Row

rows = conn.execute(
    """
    SELECT id, name, type, tags, source, canonical_url, source_kind,
           version_registry, version_package, doc_version, latest_version,
           version_status, version_checked_at, version_policy
    FROM package_meta
    ORDER BY name
    """
).fetchall()

selected = []
for row in rows:
    if target and target not in {row["id"], row["name"]}:
        continue
    if not target and not all_flag and not due_flag:
        continue
    if due_flag and not all_flag and not target:
        checked = row["version_checked_at"]
        if checked:
            try:
                if dt.datetime.fromisoformat(checked.replace("Z", "+00:00")) + dt.timedelta(days=1) > now:
                    continue
            except ValueError:
                pass
    selected.append(row)
    if len(selected) >= limit:
        break

if target and not selected:
    result = {"success": False, "error": f"Package not found: {target}", "checked": 0}
    print(json.dumps(result, indent=2) if output_format == "json" else f"Error: {result['error']}")
    raise SystemExit(1)

results = []
for row in selected:
    source_config = source_config_for(row, sources)
    policy = infer_policy(row, source_config)
    latest, registry_status, registry_error = fetch_latest(conn, policy)
    if registry_status == "failed":
        currency = "registry_failed"
    elif not policy.get("package_name") or not policy.get("registry") or (not latest and registry_error):
        currency = "unknown"
    else:
        currency = compare_status(policy["doc_version"], latest, policy["doc_channel"])

    expires_at = now + dt.timedelta(seconds=parse_ttl(policy.get("currency_ttl"), 86400))
    conn.execute(
        """
        UPDATE package_meta
        SET version_registry = ?,
            version_package = ?,
            doc_version = ?,
            latest_version = ?,
            version_status = ?,
            version_checked_at = ?,
            version_error = ?,
            release_url = ?,
            version_policy = ?
        WHERE id = ?
        """,
        (
            policy["registry"],
            policy["package_name"],
            policy["doc_version"] or policy["doc_channel"],
            latest,
            currency,
            iso(now),
            registry_error,
            registry_url(policy),
            policy["version_policy"],
            row["id"],
        ),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO package_currency
        (package_id, ecosystem, package_name, registry, registry_url, doc_version,
         doc_channel, version_policy, current_version, latest_version, currency_status,
         currency_checked_at, currency_expires_at, currency_error, release_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["id"],
            policy["ecosystem"],
            policy["package_name"],
            policy["registry"],
            registry_url(policy),
            policy["doc_version"],
            policy["doc_channel"],
            policy["version_policy"],
            latest,
            latest,
            currency,
            iso(now),
            iso(expires_at),
            registry_error,
            registry_url(policy),
        ),
    )
    results.append(
        {
            "id": row["id"],
            "name": row["name"],
            "ecosystem": policy["ecosystem"],
            "package_name": policy["package_name"],
            "registry": policy["registry"],
            "doc_version": policy["doc_version"] or policy["doc_channel"],
            "latest_version": latest,
            "version_status": currency,
            "error": registry_error,
        }
    )

conn.commit()
conn.close()

success = not any(item["version_status"] == "registry_failed" for item in results)
if output_format == "json":
    print(json.dumps({"success": success, "checked": len(results), "results": results}, indent=2))
elif not quiet:
    print(f"Version check: {len(results)} checked")
    for item in results:
        package = item["package_name"] or "unknown"
        print(
            f"  {item['name']} ({item['id']}): {item['version_status']} "
            f"doc={item['doc_version'] or 'unknown'} latest={item['latest_version'] or 'unknown'} package={package}"
        )
        if item["error"]:
            print(f"    error: {item['error']}")

raise SystemExit(0 if success else 1)
PY
}

_context_versions_list() {
    local outdated=false limit="100"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --outdated) outdated=true; shift ;;
            --limit) limit="${2:-100}"; shift 2 ;;
            *) shift ;;
        esac
    done
    ensure_init

    python3 - "$CONTEXT_INDEX_DB" "$outdated" "$limit" "${OUTPUT_FORMAT:-text}" <<'PY'
import json
import sqlite3
import sys

db_path, outdated_raw, limit_raw, output_format = sys.argv[1:5]
outdated = outdated_raw == "true"
limit = int(limit_raw)
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA busy_timeout = 5000")
where = ""
params = []
if outdated:
    where = "WHERE COALESCE(version_status, '') IN ('behind_major', 'behind_minor', 'behind_patch', 'floating_stale', 'registry_failed')"
rows = conn.execute(
    f"""
    SELECT id, name, version_registry, version_package, doc_version, latest_version,
           COALESCE(version_status, 'unknown'), version_checked_at, version_error
    FROM package_meta
    {where}
    ORDER BY
      CASE COALESCE(version_status, 'unknown')
        WHEN 'behind_major' THEN 0
        WHEN 'behind_minor' THEN 1
        WHEN 'behind_patch' THEN 2
        WHEN 'registry_failed' THEN 3
        ELSE 4
      END,
      name
    LIMIT ?
    """,
    params + [limit],
).fetchall()
conn.close()

items = [
    {
        "id": row[0],
        "name": row[1],
        "registry": row[2] or "",
        "package_name": row[3] or "",
        "doc_version": row[4] or "",
        "latest_version": row[5] or "",
        "version_status": row[6],
        "checked_at": row[7] or "",
        "error": row[8] or "",
    }
    for row in rows
]

if output_format == "json":
    print(json.dumps({"success": True, "count": len(items), "results": items}, indent=2))
else:
    if not items:
        print("No version records." if not outdated else "No outdated docs found.")
    else:
        print(f"{len(items)} version record(s):\n")
        for item in items:
            print(
                f"  {item['version_status']:15s} {item['name']} "
                f"doc={item['doc_version'] or 'unknown'} latest={item['latest_version'] or 'unknown'} "
                f"pkg={item['package_name'] or 'unknown'}"
            )
            if item["error"]:
                print(f"      {item['error']}")
PY
}
