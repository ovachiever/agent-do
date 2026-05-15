#!/usr/bin/env bash
# lib/retrieve.sh — Agent-facing retrieval front door for agent-context
# Sourced by agent-context entry point. Do not run directly.

cmd_retrieve() {
    local query="" max_tokens="8000" limit="5"
    local fresh=false require_fresh=false offline=false require_official=false prefer_latest=false require_current=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --max-tokens) max_tokens="$2"; shift 2 ;;
            --limit) limit="$2"; shift 2 ;;
            --fresh) fresh=true; shift ;;
            --require-fresh) fresh=true; require_fresh=true; shift ;;
            --offline) offline=true; shift ;;
            --require-official) require_official=true; shift ;;
            --prefer-latest|--current) prefer_latest=true; shift ;;
            --require-current) prefer_latest=true; require_current=true; shift ;;
            *) query="${query:+$query }$1"; shift ;;
        esac
    done

    if [[ -z "$query" ]]; then
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "Usage: agent-context retrieve <query> [--max-tokens N] [--fresh|--require-fresh] [--prefer-latest|--require-current] [--offline]"
            return 1
        fi
        die "Usage: agent-context retrieve <query> [--max-tokens N] [--fresh|--require-fresh] [--prefer-latest|--require-current] [--offline]"
    fi

    ensure_init

    local failures_file
    failures_file=$(mktemp)

    if [[ "$fresh" == "true" && "$offline" != "true" ]]; then
        local due_ids id err_file err_msg
        due_ids=$(_context_retrieve_due_ids "$query" "$limit")
        while IFS= read -r id; do
            [[ -n "$id" ]] || continue
            err_file=$(mktemp)
            if ! ( _context_refresh_one "$id" ) >/dev/null 2>"$err_file"; then
                err_msg=$(tr '\n' ' ' < "$err_file" | sed 's/[[:space:]]*$//')
                python3 - "$failures_file" "$id" "$err_msg" << 'PYTHON'
import json
import sys

path, package_id, error = sys.argv[1:4]
with open(path, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"id": package_id, "error": error}) + "\n")
PYTHON
            fi
            rm -f "$err_file"
        done <<< "$due_ids"
    fi

    if [[ "$prefer_latest" == "true" && "$offline" != "true" ]] && type _context_versions_check &>/dev/null; then
        _context_versions_check --due --limit "$limit" --quiet >/dev/null 2>&1 || true
    fi

    _context_retrieve_emit "$query" "$max_tokens" "$limit" "$fresh" "$require_fresh" "$offline" "$require_official" "$prefer_latest" "$require_current" "$failures_file"
    local rc=$?
    rm -f "$failures_file"
    return "$rc"
}

_context_retrieve_due_ids() {
    local query="$1" limit="$2"
    python3 - "$CONTEXT_INDEX_DB" "$query" "$limit" "$CONTEXT_HOME/feedback.jsonl" << 'PYTHON'
import os
import sqlite3
import sys
from datetime import datetime, timezone

db_path, query, limit_str, feedback_path = sys.argv[1:5]
limit = int(limit_str)

EXPANSIONS = {
    "react": "react reactjs jsx",
    "next": "next nextjs",
    "vue": "vue vuejs",
    "python": "python python3 py",
    "js": "javascript js ecmascript",
    "ts": "typescript ts",
    "db": "database db sql",
    "auth": "auth authentication authorization",
    "api": "api rest endpoint",
    "k8s": "kubernetes k8s",
    "docker": "docker container",
    "aws": "aws amazon",
    "gcp": "gcp google cloud",
    "ml": "ml machine learning ai",
    "llm": "llm language model ai",
}
TRUST_MULT = {"official": 1.5, "maintainer": 1.2, "local": 1.3, "community": 1.0}

def quote_fts_term(term):
    return '"' + term.replace('"', '""') + '"'

def expanded_query(text):
    terms = []
    for word in text.lower().split():
        terms.append(word)
        terms.extend(exp for exp in EXPANSIONS.get(word, "").split() if exp != word)
    return " OR ".join(quote_fts_term(term) for term in terms)

def load_feedback(path):
    feedback = {}
    if not os.path.exists(path):
        return feedback
    import json
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            package_id = entry.get("package", "")
            if package_id:
                feedback[package_id] = feedback.get(package_id, 0) + (1 if entry.get("rating") == "up" else -1)
    return feedback

def is_due(row, now):
    source_kind = row["source_kind"] or ""
    ptype = row["type"] or ""
    status = row["refresh_status"] or "unknown"
    expires_at = row["expires_at"] or ""
    if source_kind.startswith("local") or ptype in {"skill", "local"} or status == "local":
        return False
    if status != "fresh":
        return True
    if expires_at:
        try:
            return datetime.fromisoformat(expires_at.replace("Z", "+00:00")) < now
        except ValueError:
            return True
    return True

conn = sqlite3.connect(db_path)
conn.execute("PRAGMA busy_timeout = 5000")
conn.row_factory = sqlite3.Row
feedback = load_feedback(feedback_path)

try:
    rows = conn.execute(
        """
        SELECT p.id, p.name, p.description, p.trust, p.token_count, p.type,
               bm25(packages) AS bm25_score,
               pm.source_kind, pm.refresh_status, pm.expires_at
        FROM packages p
        JOIN package_meta pm ON pm.id = p.id
        WHERE packages MATCH ?
        ORDER BY bm25(packages)
        LIMIT ?
        """,
        (expanded_query(query), limit * 3),
    ).fetchall()
except Exception:
    rows = []

candidates = []
for row in rows:
    trust_mult = TRUST_MULT.get(row["trust"], 1.0)
    fb_score = feedback.get(row["id"], 0)
    fb_mult = 1.1 if fb_score > 0 else (0.8 if fb_score < 0 else 1.0)
    score = abs(row["bm25_score"]) * trust_mult * fb_mult
    candidates.append((score, row))

now = datetime.now(timezone.utc)
for _, row in sorted(candidates, key=lambda item: item[0], reverse=True)[:limit]:
    if is_due(row, now):
        print(row["id"])

conn.close()
PYTHON
}

_context_retrieve_emit() {
    local query="$1" max_tokens="$2" limit="$3" fresh="$4" require_fresh="$5" offline="$6" require_official="$7" prefer_latest="$8" require_current="$9" failures_file="${10}"
    python3 - "$CONTEXT_INDEX_DB" "$query" "$max_tokens" "$limit" "$fresh" "$require_fresh" "$offline" "$require_official" "$prefer_latest" "$require_current" "$failures_file" "$CONTEXT_HOME/feedback.jsonl" "${OUTPUT_FORMAT:-text}" << 'PYTHON'
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

(
    db_path,
    query,
    max_tokens_str,
    limit_str,
    fresh_flag,
    require_fresh_flag,
    offline_flag,
    require_official_flag,
    prefer_latest_flag,
    require_current_flag,
    failures_file,
    feedback_path,
    output_format,
) = sys.argv[1:14]

max_tokens = int(max_tokens_str)
limit = int(limit_str)
fresh_requested = fresh_flag == "true"
require_fresh = require_fresh_flag == "true"
offline = offline_flag == "true"
require_official = require_official_flag == "true"
prefer_latest = prefer_latest_flag == "true"
require_current = require_current_flag == "true"

TEXT_EXTENSIONS = {
    ".md", ".mdx", ".txt", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml",
    ".yml", ".py", ".sh", ".css", ".html", ".sql", ".toml",
}
EXPANSIONS = {
    "react": "react reactjs jsx",
    "next": "next nextjs",
    "vue": "vue vuejs",
    "python": "python python3 py",
    "js": "javascript js ecmascript",
    "ts": "typescript ts",
    "db": "database db sql",
    "auth": "auth authentication authorization",
    "api": "api rest endpoint",
    "k8s": "kubernetes k8s",
    "docker": "docker container",
    "aws": "aws amazon",
    "gcp": "gcp google cloud",
    "ml": "ml machine learning ai",
    "llm": "llm language model ai",
}
TRUST_MULT = {"official": 1.5, "maintainer": 1.2, "local": 1.3, "community": 1.0}
OFFICIAL_TRUSTS = {"official", "local"}
CURRENT_VERSION_STATUSES = {"current", "floating_fresh", "local", ""}
CURRENCY_MULT = {
    "current": 1.12,
    "floating_fresh": 1.05,
    "future": 0.95,
    "behind_patch": 0.92,
    "behind_minor": 0.75,
    "behind_major": 0.45,
    "floating_stale": 0.5,
    "registry_failed": 0.65,
    "unknown": 0.9,
    "": 1.0,
}
SECRET_NAMES = ("token", "key", "secret", "signature", "sig", "password", "passwd", "auth", "credential")

def quote_fts_term(term):
    return '"' + term.replace('"', '""') + '"'

def redact_url(url):
    if not url:
        return ""
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
    parsed = urlparse(url)
    if not parsed.scheme:
        return url
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = "[redacted]@" + netloc.rsplit("@", 1)[1]
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if any(secret in key.lower() for secret in SECRET_NAMES):
            query.append((key, "[redacted]"))
        else:
            query.append((key, value))
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, urlencode(query), parsed.fragment))

def expanded_query(text):
    terms = []
    for word in text.lower().split():
        terms.append(word)
        terms.extend(exp for exp in EXPANSIONS.get(word, "").split() if exp != word)
    return " OR ".join(quote_fts_term(term) for term in terms)

def approx_tokens(text):
    return int(len(text.split()) * 1.3)

def trim_to_tokens(text, token_budget):
    if token_budget <= 0:
        return "", 0, True
    words = text.split()
    max_words = max(1, int(token_budget / 1.3))
    if len(words) <= max_words:
        return text, approx_tokens(text), False
    trimmed = " ".join(words[:max_words])
    return trimmed + "\n\n[truncated to fit token budget]", token_budget, True

def load_feedback(path):
    feedback = {}
    if not os.path.exists(path):
        return feedback
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            package_id = entry.get("package", "")
            if package_id:
                feedback[package_id] = feedback.get(package_id, 0) + (1 if entry.get("rating") == "up" else -1)
    return feedback

def load_failures(path):
    failures = []
    if not os.path.exists(path):
        return failures
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                failures.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return failures

def query_mentions_specific_version(text):
    return bool(re.search(r"\b(v\d+|version\s+\d+|\d+\.\d+(?:\.\d+)?)\b", text.lower()))

def derived_freshness(row, now):
    source_kind = row["source_kind"] or ""
    ptype = row["type"] or ""
    status = row["refresh_status"] or "unknown"
    expires_at = row["expires_at"] or ""
    if source_kind.startswith("local") or ptype in {"skill", "local"} or status == "local":
        return "local", False
    stale = status != "fresh"
    if expires_at:
        try:
            stale = stale or datetime.fromisoformat(expires_at.replace("Z", "+00:00")) < now
        except ValueError:
            stale = True
    else:
        stale = True
    if stale and status == "failed":
        return "failed", True
    if stale:
        return "stale", True
    return "fresh", False

def iter_text_files(cache_path):
    if not cache_path or not os.path.isdir(cache_path):
        return
    for dirpath, _, filenames in os.walk(cache_path):
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, cache_path)
            if rel == "meta.json":
                continue
            if rel.startswith(("raw/", "_raw/")) or rel.endswith("/raw.html") or filename in {"headers.txt", "extracted.json", "crawl.json", "metadata.json"}:
                continue
            if os.path.splitext(filename)[1].lower() not in TEXT_EXTENSIONS:
                continue
            yield rel, path

def read_content(cache_path, token_budget):
    chunks = []
    files = []
    used = 0
    truncated = False
    for rel, path in iter_text_files(cache_path):
        if token_budget - used <= 0:
            truncated = True
            break
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                content = handle.read()
        except OSError:
            continue
        chunk = f"--- {rel} ---\n{content}"
        chunk_tokens = approx_tokens(chunk)
        remaining = token_budget - used
        if chunk_tokens > remaining:
            chunk, chunk_tokens, was_truncated = trim_to_tokens(chunk, remaining)
            truncated = truncated or was_truncated
        chunks.append(chunk)
        files.append(rel)
        used += chunk_tokens
        if used >= token_budget:
            truncated = True
            break
    return "\n\n".join(chunks), used, files, truncated

conn = sqlite3.connect(db_path)
conn.execute("PRAGMA busy_timeout = 5000")
conn.row_factory = sqlite3.Row
feedback = load_feedback(feedback_path)

try:
    rows = conn.execute(
        """
        SELECT p.id, p.name, p.description, p.tags, p.trust, p.token_count,
               p.type, p.cache_path, bm25(packages) AS bm25_score,
               pm.source, pm.canonical_url, pm.source_kind, pm.fetched_at,
               pm.checked_at, pm.expires_at, pm.refresh_status, pm.refresh_error,
               pm.version_registry, pm.version_package, pm.doc_version,
               pm.latest_version, pm.version_status, pm.version_checked_at,
               pm.version_error
        FROM packages p
        JOIN package_meta pm ON pm.id = p.id
        WHERE packages MATCH ?
        ORDER BY bm25(packages)
        LIMIT ?
        """,
        (expanded_query(query), limit * 4),
    ).fetchall()
except Exception as exc:
    conn.close()
    result = {
        "success": False,
        "error": f"Retrieve search failed: {exc}",
        "query": query,
    }
    print(json.dumps(result, indent=2) if output_format == "json" else f"Error: {result['error']}", file=sys.stderr if output_format != "json" else sys.stdout)
    sys.exit(1)

candidates = []
for row in rows:
    trust_mult = TRUST_MULT.get(row["trust"], 1.0)
    fb_score = feedback.get(row["id"], 0)
    fb_mult = 1.1 if fb_score > 0 else (0.8 if fb_score < 0 else 1.0)
    currency_status = row["version_status"] or ""
    currency_mult = 1.0
    if prefer_latest and not query_mentions_specific_version(query):
        currency_mult = CURRENCY_MULT.get(currency_status, CURRENCY_MULT["unknown"])
    score = abs(row["bm25_score"]) * trust_mult * fb_mult * currency_mult
    candidates.append((score, row))
candidates.sort(key=lambda item: item[0], reverse=True)

now = datetime.now(timezone.utc)
selected = []
remaining = max_tokens
for score, row in candidates:
    if len(selected) >= limit or remaining <= 0:
        break
    if require_official and (row["trust"] or "") not in OFFICIAL_TRUSTS:
        continue
    version_status = row["version_status"] or ""
    if require_current and not query_mentions_specific_version(query) and version_status not in CURRENT_VERSION_STATUSES:
        continue
    content, used_tokens, files, truncated = read_content(row["cache_path"], remaining)
    if not content:
        continue
    freshness, stale = derived_freshness(row, now)
    selected.append({
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "type": row["type"] or "",
        "trust": row["trust"] or "",
        "score": round(score, 3),
        "source": redact_url(row["source"] or ""),
        "canonical_url": redact_url(row["canonical_url"] or row["source"] or ""),
        "source_kind": row["source_kind"] or "",
        "fetched_at": row["fetched_at"] or "",
        "checked_at": row["checked_at"] or "",
        "expires_at": row["expires_at"] or "",
        "refresh_status": row["refresh_status"] or "unknown",
        "freshness": freshness,
        "is_stale": stale,
        "refresh_error": row["refresh_error"] or "",
        "version_registry": row["version_registry"] or "",
        "version_package": row["version_package"] or "",
        "doc_version": row["doc_version"] or "",
        "latest_version": row["latest_version"] or "",
        "version_status": row["version_status"] or "unknown",
        "version_checked_at": row["version_checked_at"] or "",
        "version_error": row["version_error"] or "",
        "package_tokens": int(row["token_count"] or 0),
        "used_tokens": used_tokens,
        "files": files,
        "truncated": truncated,
        "content": content,
    })
    remaining -= used_tokens

conn.close()

failures = load_failures(failures_file)
stale_selected = [
    {
        "id": item["id"],
        "name": item["name"],
        "freshness": item["freshness"],
        "refresh_status": item["refresh_status"],
        "expires_at": item["expires_at"],
        "refresh_error": item["refresh_error"],
    }
    for item in selected
    if item["is_stale"]
]
noncurrent_selected = [
    {
        "id": item["id"],
        "name": item["name"],
        "version_status": item["version_status"],
        "doc_version": item["doc_version"],
        "latest_version": item["latest_version"],
        "version_package": item["version_package"],
        "version_error": item["version_error"],
    }
    for item in selected
    if item["version_status"] not in {"current", "floating_fresh", "local", ""}
    and (prefer_latest or item["version_status"] not in {"unknown", ""})
]
success = bool(selected)
error = ""
if not selected:
    success = False
    if require_current:
        error = f"No current context results for '{query}'"
    else:
        error = f"No context results for '{query}'"
elif require_fresh and stale_selected:
    success = False
    if offline:
        error = "Selected context is stale and --offline prevents refresh"
    else:
        error = "Selected context could not be verified fresh"
elif require_current and noncurrent_selected and not query_mentions_specific_version(query):
    success = False
    error = "Selected context could not be verified current"

result = {
    "success": success,
    "query": query,
    "fresh_requested": fresh_requested,
    "require_fresh": require_fresh,
    "offline": offline,
    "require_official": require_official,
    "prefer_latest": prefer_latest,
    "require_current": require_current,
    "freshness_ok": not stale_selected,
    "version_currency_ok": not noncurrent_selected,
    "max_tokens": max_tokens,
    "used_tokens": sum(item["used_tokens"] for item in selected),
    "remaining_tokens": max(0, remaining),
    "package_count": len(selected),
    "refresh_failures": failures,
    "stale_packages": stale_selected,
    "noncurrent_packages": noncurrent_selected,
}
if error:
    result["error"] = error

packages_for_json = []
for item in selected:
    item = dict(item)
    if require_fresh and stale_selected:
        item.pop("content", None)
    packages_for_json.append(item)
result["packages"] = packages_for_json

if output_format == "json":
    print(json.dumps(result, indent=2))
else:
    if not success:
        print(f"Error: {error}", file=sys.stderr)
        if stale_selected:
            print("Stale selected packages:", file=sys.stderr)
            for item in stale_selected:
                print(f"  {item['id']} ({item['freshness']})", file=sys.stderr)
        if noncurrent_selected:
            print("Non-current selected packages:", file=sys.stderr)
            for item in noncurrent_selected:
                print(f"  {item['id']} ({item['version_status']}) doc={item['doc_version']} latest={item['latest_version']}", file=sys.stderr)
        sys.exit(1)

    print(f"# Retrieved context for: {query}")
    print()
    print(f"Packages: {len(selected)} | Tokens: ~{result['used_tokens']}/{max_tokens} | Freshness: {'ok' if result['freshness_ok'] else 'stale'} | Currency: {'ok' if result['version_currency_ok'] else 'check'}")
    if failures:
        print("Refresh failures:")
        for failure in failures:
            print(f"  {failure.get('id', '')}: {failure.get('error', '')}")
    if stale_selected:
        print("Stale packages included from last-good cache:")
        for item in stale_selected:
            print(f"  {item['id']} ({item['freshness']})")
    if noncurrent_selected:
        print("Version currency warnings:")
        for item in noncurrent_selected:
            print(f"  {item['id']} ({item['version_status']}) doc={item['doc_version'] or 'unknown'} latest={item['latest_version'] or 'unknown'}")
    print()
    for item in selected:
        print(f"## {item['name']} ({item['id']})")
        print(f"Source: {item['canonical_url']}")
        print(f"Trust: {item['trust']} | Freshness: {item['freshness']} | Currency: {item['version_status']} | Checked: {item['checked_at'] or 'unknown'}")
        if item["doc_version"] or item["latest_version"]:
            print(f"Version: docs={item['doc_version'] or 'unknown'} latest={item['latest_version'] or 'unknown'} package={item['version_package'] or 'unknown'}")
        print()
        print(item["content"])
        print()
        print("---")
        print()

sys.exit(0 if success else 1)
PYTHON
}
