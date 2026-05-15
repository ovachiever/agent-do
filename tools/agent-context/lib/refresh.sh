#!/usr/bin/env bash
# lib/refresh.sh — WAN refresh for agent-context packages
# Sourced by agent-context entry point. Do not run directly.

cmd_refresh() {
    local target="" due=false all=false limit="20"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --due) due=true; shift ;;
            --all) all=true; shift ;;
            --limit) limit="$2"; shift 2 ;;
            --budget-sec) shift 2 ;; # reserved for Phase 2 scheduling; ignored for now
            *) target="$1"; shift ;;
        esac
    done

    ensure_init

    if [[ "$due" == "true" || "$all" == "true" ]]; then
        _context_refresh_many "$limit" "$all"
        return
    fi

    [[ -n "$target" ]] || die "Usage: agent-context refresh <id|name> | --due [--limit N] | --all [--limit N]"
    _context_refresh_one "$target"
}

_context_refresh_many() {
    local limit="$1" include_all="$2"
    local ids
    ids=$(python3 - "$CONTEXT_INDEX_DB" "$limit" "$include_all" << 'PYTHON'
import sqlite3
import sys
from datetime import datetime, timezone

db_path, limit, include_all = sys.argv[1:4]
limit = int(limit)
now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

conn = sqlite3.connect(db_path)
conn.execute("PRAGMA busy_timeout = 5000")
if include_all == "true":
    rows = conn.execute(
        """
        SELECT id FROM package_meta
        WHERE COALESCE(refresh_status, '') != 'local'
        ORDER BY checked_at IS NOT NULL, checked_at
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
else:
    rows = conn.execute(
        """
        SELECT id FROM package_meta
        WHERE COALESCE(refresh_status, 'unknown') IN ('stale', 'failed', 'unknown')
           OR (expires_at IS NOT NULL AND expires_at < ? AND COALESCE(refresh_status, '') != 'local')
        ORDER BY
          CASE COALESCE(refresh_status, 'unknown')
            WHEN 'failed' THEN 0
            WHEN 'stale' THEN 1
            ELSE 2
          END,
          checked_at IS NOT NULL,
          checked_at
        LIMIT ?
        """,
        (now, limit),
    ).fetchall()
conn.close()
for row in rows:
    print(row[0])
PYTHON
    )

    local count=0 failed=0 refreshed=0 skipped=0
    local id output
    while IFS= read -r id; do
        [[ -n "$id" ]] || continue
        count=$((count + 1))
        if ! _context_package_source_enabled "$id"; then
            skipped=$((skipped + 1))
            continue
        fi
        if _context_package_backoff_active "$id"; then
            skipped=$((skipped + 1))
            continue
        fi
        if output=$(_context_refresh_one "$id" 2>&1); then
            if grep -q "already local" <<<"$output"; then
                skipped=$((skipped + 1))
            else
                refreshed=$((refreshed + 1))
            fi
            [[ "${OUTPUT_FORMAT:-text}" == "json" ]] || echo "$output"
        else
            failed=$((failed + 1))
            [[ "${OUTPUT_FORMAT:-text}" == "json" ]] || echo "$output" >&2
        fi
    done <<< "$ids"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        python3 - "$count" "$refreshed" "$failed" "$skipped" << 'PYTHON'
import json
import sys

count, refreshed, failed, skipped = [int(item) for item in sys.argv[1:5]]
print(json.dumps({
    "success": failed == 0,
    "considered": count,
    "refreshed": refreshed,
    "failed": failed,
    "skipped": skipped,
}, indent=2))
PYTHON
    else
        echo "Refresh due: $refreshed refreshed, $failed failed, $skipped skipped."
    fi

    [[ "$failed" -eq 0 ]]
}

_context_package_backoff_active() {
    python3 - "$CONTEXT_INDEX_DB" "$1" << 'PYTHON'
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA busy_timeout = 5000")
row = conn.execute("SELECT refresh_status, checked_at FROM package_meta WHERE id = ?", (sys.argv[2],)).fetchone()
conn.close()
if not row or row[0] != "failed" or not row[1]:
    raise SystemExit(1)
try:
    checked = datetime.fromisoformat(str(row[1]).replace("Z", "+00:00"))
except ValueError:
    raise SystemExit(1)
if checked + timedelta(minutes=15) > datetime.now(timezone.utc):
    raise SystemExit(0)
raise SystemExit(1)
PYTHON
}

_context_package_source_enabled() {
    python3 - "$CONTEXT_INDEX_DB" "$CONTEXT_HOME/config.yaml" "$1" << 'PYTHON'
import re
import sqlite3
import sys
from pathlib import Path

db_path, config_path, package_id = sys.argv[1:4]
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA busy_timeout = 5000")
row = conn.execute(
    "SELECT name, COALESCE(source, ''), COALESCE(canonical_url, '') FROM package_meta WHERE id = ?",
    (package_id,),
).fetchone()
conn.close()
if not row:
    raise SystemExit(0)
pkg_name, source, canonical = row

text = Path(config_path).read_text() if Path(config_path).exists() else ""
disabled = []
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
        disabled.append(current)
        match = re.match(r"^  -\s+name:\s*(.*)$", line)
        if match:
            current["name"] = match.group(1).strip().strip('"').strip("'")
        continue
    if current is None:
        continue
    match = re.match(r"^    ([A-Za-z0-9_-]+):\s*(.*)$", line)
    if match:
        current[match.group(1)] = match.group(2).strip().strip('"').strip("'")

for item in disabled:
    if item.get("enabled", "true").lower() != "false":
        continue
    locations = [
        item.get("name", ""),
        item.get("location", ""),
        item.get("url", ""),
        item.get("path", ""),
    ]
    for location in [value for value in locations if value]:
        base = location.rstrip("/")
        if package_id == location or pkg_name == location or source == location or canonical == location:
            raise SystemExit(1)
        if base and (source.startswith(base + "/") or canonical.startswith(base + "/")):
            raise SystemExit(1)
raise SystemExit(0)
PYTHON
}

_context_refresh_one() {
    local target="$1"
    local meta
    meta=$(python3 - "$CONTEXT_INDEX_DB" "$target" << 'PYTHON'
import json
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA busy_timeout = 5000")
target = sys.argv[2]
row = conn.execute(
    """
    SELECT id, name, type, trust, token_count, source, cache_path, tags,
           source_kind, canonical_url
    FROM package_meta
    WHERE id = ? OR name = ?
    """,
    (target, target),
).fetchone()
conn.close()
if not row:
    print(json.dumps({"found": False}))
else:
    keys = [
        "id", "name", "type", "trust", "token_count", "source", "cache_path",
        "tags", "source_kind", "canonical_url",
    ]
    print(json.dumps({"found": True, **dict(zip(keys, row))}))
PYTHON
    )

    local found
    found=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('found'))" <<<"$meta")
    [[ "$found" == "True" ]] || die "Package not found: $target"

    local pkg_id name ptype trust source cache_path tags source_kind canonical_url
    pkg_id=$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" <<<"$meta")
    name=$(python3 -c "import json,sys; print(json.load(sys.stdin)['name'])" <<<"$meta")
    ptype=$(python3 -c "import json,sys; print(json.load(sys.stdin)['type'])" <<<"$meta")
    trust=$(python3 -c "import json,sys; print(json.load(sys.stdin)['trust'])" <<<"$meta")
    source=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('source') or '')" <<<"$meta")
    cache_path=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('cache_path') or '')" <<<"$meta")
    tags=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('tags') or '')" <<<"$meta")
    source_kind=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('source_kind') or '')" <<<"$meta")
    canonical_url=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('canonical_url') or '')" <<<"$meta")

    if [[ "$source_kind" == "local-skill" || "$ptype" == "skill" ]]; then
        _context_refresh_local_skill "$pkg_id" "$name" "$trust" "$tags" "$source" "$cache_path"
        return
    fi

    if [[ "$source_kind" == "local-project" || "$ptype" == "local" ]]; then
        _context_refresh_local_project "$pkg_id" "$name" "$trust" "$tags" "$source" "$cache_path"
        return 0
    fi

    local url="${canonical_url:-$source}"
    if [[ "$source_kind" == "github-dir" || "$url" == https://github.com/*/tree/* ]]; then
        _context_refresh_github_dir "$pkg_id" "$name" "$ptype" "$trust" "$tags" "$url" "$cache_path"
        return
    fi

    if [[ "$source_kind" == "github-file" || "$url" == https://github.com/* ]]; then
        _context_refresh_github_file "$pkg_id" "$name" "$ptype" "$trust" "$tags" "$url" "$cache_path"
        return
    fi

    if [[ "$source_kind" == "llms" ]]; then
        _context_refresh_llms "$pkg_id" "$name" "$ptype" "$trust" "$tags" "$url" "$cache_path"
        return
    fi

    if [[ "$source_kind" == "html-site" || "$ptype" == "html-site" || "$source_kind" == "html-crawl" || "$ptype" == "html-crawl" ]]; then
        _context_refresh_html_site "$pkg_id" "$name" "$ptype" "$trust" "$tags" "$url" "$cache_path"
        return
    fi

    if [[ -z "$url" || "$url" != http* ]]; then
        _context_mark_refresh_failed "$pkg_id" "No refreshable URL for $pkg_id"
        die "No refreshable URL for $pkg_id"
    fi

    _context_refresh_url "$pkg_id" "$name" "$ptype" "$trust" "$tags" "$url" "$cache_path"
}

_context_refresh_url() {
    local pkg_id="$1" name="$2" ptype="$3" trust="$4" tags="$5" url="$6" cache_path="$7"
    local tmp_dir content_file headers_file http_code validators etag last_modified content_type
    local safe_url
    safe_url=$(redact_url "$url")
    tmp_dir=$(mktemp -d)
    content_file="$tmp_dir/content.md"
    headers_file="$tmp_dir/headers.txt"

    validators=$(_context_refresh_validators "$pkg_id")
    etag=$(sed -n '1p' <<<"$validators")
    last_modified=$(sed -n '2p' <<<"$validators")

    local curl_args=(-sL -D "$headers_file" -w "%{http_code}" -o "$content_file")
    [[ -n "$etag" ]] && curl_args+=(-H "If-None-Match: $etag")
    [[ -n "$last_modified" ]] && curl_args+=(-H "If-Modified-Since: $last_modified")

    http_code=$(curl -q --connect-timeout 5 --max-time 20 "${curl_args[@]}" "$url" 2>/dev/null) || true
    if [[ "$http_code" == "304" ]]; then
        _context_record_http_headers "$pkg_id" "$headers_file"
        _context_mark_refresh_fresh "$pkg_id"
        rm -rf "$tmp_dir"
        _context_refresh_result "$pkg_id" "$name" "fresh" "not modified"
        return 0
    fi

    if [[ "$http_code" != "200" ]]; then
        rm -rf "$tmp_dir"
        _context_mark_refresh_failed "$pkg_id" "HTTP $http_code while refreshing $safe_url"
        die "Refresh failed for $pkg_id: HTTP $http_code"
    fi

    mkdir -p "$cache_path"
    find "$cache_path" -mindepth 1 ! -name meta.json -exec rm -rf {} + 2>/dev/null || true
    local content_kind="$ptype" description canonical_url
    description="Refreshed from $url"
    canonical_url="$url"
    if type _context_is_html_response &>/dev/null && _context_is_html_response "$headers_file" "$content_file"; then
        content_kind="html-page"
        _context_store_html_file "$url" "$content_file" "$headers_file" "$cache_path"
        if [[ -f "$cache_path/metadata.json" ]]; then
            description=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("description",""))' "$cache_path/metadata.json" 2>/dev/null || true)
            canonical_url=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("canonical_url",""))' "$cache_path/metadata.json" 2>/dev/null || true)
        fi
        [[ -n "$description" ]] || description="Refreshed from $url"
        [[ -n "$canonical_url" ]] || canonical_url="$url"
    else
        cp "$content_file" "$cache_path/content.md"
    fi
    local token_count
    token_count=$(_context_count_tree_tokens "$cache_path")
    write_meta "$cache_path" "$name" "$content_kind" "$description" "$url" "$token_count" "$trust" "$tags"
    _index_package "$pkg_id" "$name" "$content_kind" "$description" "$tags" "$trust" "$token_count" "$cache_path" "$canonical_url"
    _context_record_http_headers "$pkg_id" "$headers_file"
    rm -rf "$tmp_dir"
    _context_refresh_result "$pkg_id" "$name" "fresh" "refreshed"
}

_context_refresh_html_site() {
    local pkg_id="$1" name="$2" ptype="$3" trust="$4" tags="$5" url="$6" cache_path="$7"
    local safe_url crawl_limit description token_count
    safe_url=$(redact_url "$url")
    crawl_limit=$(python3 - "$CONTEXT_INDEX_DB" "$pkg_id" << 'PYTHON'
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA busy_timeout = 5000")
row = conn.execute("SELECT COALESCE(crawl_limit, 20) FROM package_meta WHERE id = ?", (sys.argv[2],)).fetchone()
conn.close()
print(row[0] if row else 20)
PYTHON
    )

    mkdir -p "$cache_path"
    find "$cache_path" -mindepth 1 ! -name meta.json -exec rm -rf {} + 2>/dev/null || true
    if ! _context_crawl_html_site "$url" "$cache_path" "$crawl_limit"; then
        _context_mark_refresh_failed "$pkg_id" "HTML crawl failed while refreshing $safe_url"
        die "Refresh failed for $pkg_id: HTML crawl failed"
    fi
    description="Refreshed HTML site from $url"
    if [[ -f "$cache_path/metadata.json" ]]; then
        local extracted_description
        extracted_description=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("description",""))' "$cache_path/metadata.json" 2>/dev/null || true)
        [[ -n "$extracted_description" ]] && description="$extracted_description"
    fi
    token_count=$(_context_count_tree_tokens "$cache_path")
    write_meta "$cache_path" "$name" "html-site" "$description" "$url" "$token_count" "$trust" "$tags"
    _index_package "$pkg_id" "$name" "html-site" "$description" "$tags" "$trust" "$token_count" "$cache_path" "$url"
    _context_mark_refresh_fresh "$pkg_id"
    _context_refresh_result "$pkg_id" "$name" "fresh" "refreshed"
}

_context_refresh_llms() {
    local pkg_id="$1" name="$2" ptype="$3" trust="$4" tags="$5" url="$6" cache_path="$7"
    local domain
    domain=$(python3 - "$url" << 'PYTHON'
import sys
from urllib.parse import urlparse

url = sys.argv[1]
parsed = urlparse(url if url.startswith(("http://", "https://")) else "https://" + url)
print(parsed.netloc or parsed.path.split("/")[0])
PYTHON
    )

    local candidate tmp_dir content_file headers_file http_code last_error=""
    for candidate in "https://${domain}/llms-full.txt" "https://${domain}/llms.txt"; do
        tmp_dir=$(mktemp -d)
        content_file="$tmp_dir/content.md"
        headers_file="$tmp_dir/headers.txt"
        http_code=$(curl -q -sL --connect-timeout 5 --max-time 20 -D "$headers_file" -w "%{http_code}" -o "$content_file" "$candidate" 2>/dev/null) || true
        if [[ "$http_code" == "200" ]]; then
            local content_type first_bytes token_count
            content_type=$(_context_header_value "$headers_file" "content-type")
            first_bytes=$(head -c 20 "$content_file")
            if [[ "$content_type" != *text/html* && "$first_bytes" != "<!DOCTYPE"* && "$first_bytes" != "<html"* ]]; then
                mkdir -p "$cache_path"
                cp "$content_file" "$cache_path/content.md"
                token_count=$(count_tokens "$cache_path/content.md")
                write_meta "$cache_path" "$name" "$ptype" "Refreshed from $candidate" "$candidate" "$token_count" "$trust" "$tags"
                _index_package "$pkg_id" "$name" "$ptype" "Refreshed from $candidate" "$tags" "$trust" "$token_count" "$cache_path" "$candidate"
                _context_record_http_headers "$pkg_id" "$headers_file"
                rm -rf "$tmp_dir"
                _context_refresh_result "$pkg_id" "$name" "fresh" "refreshed"
                return 0
            fi
            last_error="HTML response from $candidate"
        else
            last_error="HTTP $http_code from $candidate"
        fi
        rm -rf "$tmp_dir"
    done

    _context_mark_refresh_failed "$pkg_id" "$last_error"
    die "Refresh failed for $pkg_id: $last_error"
}

_context_refresh_github_file() {
    local pkg_id="$1" name="$2" ptype="$3" trust="$4" tags="$5" url="$6" cache_path="$7"
    command -v gh &>/dev/null || {
        _context_mark_refresh_failed "$pkg_id" "gh CLI required for GitHub refresh"
        die "Refresh failed for $pkg_id: gh CLI required"
    }

    local repo path
    read -r repo path < <(python3 - "$url" "$cache_path" << 'PYTHON'
import os
import re
import sys
from urllib.parse import urlparse

url, cache_path = sys.argv[1:3]
parsed = urlparse(url)
parts = [part for part in parsed.path.split("/") if part]
repo = ""
path = ""
if len(parts) >= 2:
    repo = "/".join(parts[:2])
if len(parts) >= 5 and parts[2] == "blob":
    path = "/".join(parts[4:])
if not path:
    for candidate in ("README.md", "llms.txt", "llms-full.txt", "docs/README.md"):
        if os.path.exists(os.path.join(cache_path, os.path.basename(candidate))):
            path = candidate
            break
print(repo, path)
PYTHON
    )

    if [[ -z "$repo" || -z "$path" ]]; then
        _context_mark_refresh_failed "$pkg_id" "Cannot infer GitHub file path from $url"
        die "Refresh failed for $pkg_id: cannot infer GitHub file path"
    fi

    local tmp_dir filename
    tmp_dir=$(mktemp -d)
    filename=$(basename "$path")
    if ! gh api "repos/$repo/contents/$path" --jq '.content' 2>/dev/null | base64 -d > "$tmp_dir/$filename"; then
        rm -rf "$tmp_dir"
        _context_mark_refresh_failed "$pkg_id" "GitHub fetch failed for $repo/$path"
        die "Refresh failed for $pkg_id: GitHub fetch failed"
    fi

    mkdir -p "$cache_path"
    cp "$tmp_dir/$filename" "$cache_path/$filename"
    local token_count
    token_count=$(count_tokens "$cache_path/$filename")
    write_meta "$cache_path" "$name" "$ptype" "Refreshed from github.com/$repo/$path" "https://github.com/$repo/blob/HEAD/$path" "$token_count" "$trust" "$tags"
    _index_package "$pkg_id" "$name" "$ptype" "Refreshed from github.com/$repo/$path" "$tags" "$trust" "$token_count" "$cache_path" "https://github.com/$repo/blob/HEAD/$path"
    rm -rf "$tmp_dir"
    _context_refresh_result "$pkg_id" "$name" "fresh" "refreshed"
}

_context_refresh_github_dir() {
    local pkg_id="$1" name="$2" ptype="$3" trust="$4" tags="$5" url="$6" cache_path="$7"
    command -v gh &>/dev/null || {
        _context_mark_refresh_failed "$pkg_id" "gh CLI required for GitHub directory refresh"
        die "Refresh failed for $pkg_id: gh CLI required"
    }

    local repo ref path
    read -r repo ref path < <(_context_parse_github_tree_url "$url")
    if [[ -z "$repo" || -z "$path" ]]; then
        _context_mark_refresh_failed "$pkg_id" "Cannot infer GitHub directory path from $url"
        die "Refresh failed for $pkg_id: cannot infer GitHub directory path"
    fi
    [[ -n "$ref" ]] || ref="HEAD"

    local tmp_dir
    tmp_dir=$(mktemp -d)
    if ! _context_fetch_github_directory "$repo" "$ref" "$path" "$tmp_dir"; then
        rm -rf "$tmp_dir"
        _context_mark_refresh_failed "$pkg_id" "GitHub directory fetch failed for $repo/$path"
        die "Refresh failed for $pkg_id: GitHub directory fetch failed"
    fi

    mkdir -p "$cache_path"
    find "$cache_path" -mindepth 1 ! -name meta.json -exec rm -rf {} + 2>/dev/null || true
    cp -R "$tmp_dir"/. "$cache_path"/
    local token_count source_url
    token_count=$(_context_count_tree_tokens "$cache_path")
    source_url="https://github.com/$repo/tree/$ref/$path"
    write_meta "$cache_path" "$name" "$ptype" "Refreshed from github.com/$repo/$path" "$source_url" "$token_count" "$trust" "$tags"
    _index_package "$pkg_id" "$name" "$ptype" "Refreshed from github.com/$repo/$path" "$tags" "$trust" "$token_count" "$cache_path" "$source_url"
    rm -rf "$tmp_dir"
    _context_refresh_result "$pkg_id" "$name" "fresh" "refreshed"
}

_context_refresh_local_skill() {
    local pkg_id="$1" name="$2" trust="$3" tags="$4" source="$5" cache_path="$6"
    local skills_root="${source:-$HOME/.claude/skills}"
    local skill_dir="$skills_root/$name"
    local skill_file="$skill_dir/SKILL.md"
    [[ -f "$skill_file" ]] || {
        _context_mark_refresh_failed "$pkg_id" "Local skill not found: $skill_file"
        die "Refresh failed for $pkg_id: local skill not found"
    }

    rm -rf "$cache_path"
    mkdir -p "$cache_path"
    cp "$skill_file" "$cache_path/SKILL.md"
    python3 - "$skill_dir" "$cache_path" << 'PYTHON'
import shutil
import sys
from pathlib import Path

src_root = Path(sys.argv[1])
dest_root = Path(sys.argv[2])
extensions = {
    ".md", ".mdx", ".txt", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml",
    ".yml", ".py", ".sh", ".css", ".html", ".sql", ".toml",
}
for path in src_root.rglob("*"):
    if not path.is_file() or path.name == "SKILL.md" or path.suffix.lower() not in extensions:
        continue
    rel = path.relative_to(src_root)
    target = dest_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
PYTHON

    local token_count description meta_json skill_tags
    token_count=$(_context_count_tree_tokens "$cache_path")
    meta_json=$(extract_frontmatter "$skill_file")
    description=$(echo "$meta_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description','Skill: $name'))" 2>/dev/null || echo "Skill: $name")
    skill_tags=$(echo "$meta_json" | python3 -c "import sys,json; d=json.load(sys.stdin); tags=d.get('tags', []); print(','.join(tags) if isinstance(tags, list) else (tags if isinstance(tags, str) else ''))" 2>/dev/null || echo "$tags")
    [[ -n "$skill_tags" ]] || skill_tags="$tags"
    write_meta "$cache_path" "$name" "skill" "$description" "$skills_root" "$token_count" "$trust" "$skill_tags"
    _index_package "$pkg_id" "$name" "skill" "$description" "$skill_tags" "$trust" "$token_count" "$cache_path" "$skills_root"
    _context_refresh_result "$pkg_id" "$name" "local" "refreshed"
}

_context_refresh_local_project() {
    local pkg_id="$1" name="$2" trust="$3" tags="$4" source="$5" cache_path="$6"
    local target_dir="$source"
    [[ -d "$target_dir" ]] || {
        _context_mark_refresh_failed "$pkg_id" "Local project path not found: $target_dir"
        die "Refresh failed for $pkg_id: local project path not found"
    }

    rm -rf "$cache_path"
    mkdir -p "$cache_path"
    local count=0 candidate src dest_name
    for candidate in CLAUDE.md .claude/CLAUDE.md .cursorrules .cursor/rules .github/copilot-instructions.md README.md; do
        src="$target_dir/$candidate"
        if [[ -f "$src" ]]; then
            dest_name=$(echo "$candidate" | tr '/' '-')
            cp "$src" "$cache_path/$dest_name"
            count=$((count + 1))
        fi
    done
    [[ "$count" -gt 0 ]] || {
        _context_mark_refresh_failed "$pkg_id" "No local project context files found in $target_dir"
        die "Refresh failed for $pkg_id: no local project context files found"
    }

    local token_count description
    token_count=$(_context_count_tree_tokens "$cache_path")
    description="Local project context from ${name#local-}"
    write_meta "$cache_path" "$name" "local" "$description" "$target_dir" "$token_count" "$trust" "$tags"
    _index_package "$pkg_id" "$name" "local" "$description" "$tags" "$trust" "$token_count" "$cache_path" "$target_dir"
    _context_refresh_result "$pkg_id" "$name" "local" "refreshed"
}

_context_fetch_github_directory() {
    local repo="$1" ref="$2" dir_path="$3" dest_dir="$4"
    local tree_json tree_file rows_file
    tree_json=$(gh api "repos/$repo/git/trees/$ref?recursive=1" 2>/dev/null) || return 1
    tree_file=$(mktemp)
    printf '%s' "$tree_json" > "$tree_file"
    rows_file=$(mktemp)
    python3 - "$dir_path" "$tree_file" > "$rows_file" << 'PYTHON'
import json
import os
import sys

prefix = sys.argv[1].strip("/")
tree_file = sys.argv[2]
allowed = {
    ".md", ".mdx", ".txt", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml",
    ".yml", ".py", ".sh", ".css", ".html", ".sql", ".toml",
}
with open(tree_file, encoding="utf-8") as handle:
    data = json.load(handle)
count = 0
for item in data.get("tree", []):
    path = item.get("path", "")
    if item.get("type") != "blob":
        continue
    if prefix and not (path == prefix or path.startswith(prefix + "/")):
        continue
    if os.path.splitext(path)[1].lower() not in allowed:
        continue
    rel = path[len(prefix):].lstrip("/") if prefix else path
    if not rel:
        continue
    print(f"{path}\t{rel}\t{item.get('sha', '')}")
    count += 1
    if count >= 200:
        break
PYTHON
    if [[ ! -s "$rows_file" ]]; then
        rm -f "$rows_file" "$tree_file"
        return 1
    fi

    local path rel sha target
    while IFS=$'\t' read -r path rel sha; do
        [[ -n "$path" && -n "$rel" && -n "$sha" ]] || continue
        target="$dest_dir/$rel"
        mkdir -p "$(dirname "$target")"
        gh api "repos/$repo/git/blobs/$sha" --jq '.content' 2>/dev/null | base64 -d > "$target" || {
            rm -f "$rows_file" "$tree_file"
            return 1
        }
    done < "$rows_file"
    rm -f "$rows_file" "$tree_file"
}

_context_parse_github_tree_url() {
    python3 - "$1" << 'PYTHON'
import sys
from urllib.parse import urlparse

url = sys.argv[1]
parsed = urlparse(url)
parts = [part for part in parsed.path.split("/") if part]
repo = ""
ref = ""
path = ""
if len(parts) >= 2:
    repo = "/".join(parts[:2])
if len(parts) >= 5 and parts[2] == "tree":
    ref = parts[3]
    path = "/".join(parts[4:])
print(repo, ref, path)
PYTHON
}

_context_count_tree_tokens() {
    python3 - "$1" << 'PYTHON'
import os
import sys

root = sys.argv[1]
extensions = {
    ".md", ".mdx", ".txt", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml",
    ".yml", ".py", ".sh", ".css", ".html", ".sql", ".toml",
}
total = 0
for dirpath, _, filenames in os.walk(root):
    for filename in filenames:
        rel = os.path.relpath(os.path.join(dirpath, filename), root)
        if rel.startswith(("raw/", "_raw/")) or rel.endswith("/raw.html") or filename in {"headers.txt", "extracted.json", "crawl.json", "metadata.json"}:
            continue
        if os.path.splitext(filename)[1].lower() not in extensions:
            continue
        path = os.path.join(dirpath, filename)
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                total += int(len(handle.read().split()) * 1.3)
        except OSError:
            pass
print(total)
PYTHON
}

_context_mark_local() {
    python3 - "$CONTEXT_INDEX_DB" "$1" << 'PYTHON'
import sqlite3
import sys
from datetime import datetime, timezone

conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA busy_timeout = 5000")
conn.execute(
    "UPDATE package_meta SET refresh_status = 'local', checked_at = ?, refresh_error = '' WHERE id = ?",
    (datetime.now(timezone.utc).replace(microsecond=0).isoformat(), sys.argv[2]),
)
conn.commit()
conn.close()
PYTHON
}

_context_mark_refresh_fresh() {
    python3 - "$CONTEXT_INDEX_DB" "$1" << 'PYTHON'
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

now = datetime.now(timezone.utc).replace(microsecond=0)
conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA busy_timeout = 5000")
conn.execute(
    """
    UPDATE package_meta
    SET refresh_status = 'fresh',
        checked_at = ?,
        expires_at = ?,
        refresh_error = ''
    WHERE id = ?
    """,
    (now.isoformat(), (now + timedelta(days=7)).isoformat(), sys.argv[2]),
)
conn.commit()
conn.close()
PYTHON
}

_context_mark_refresh_failed() {
    local pkg_id="$1" error="$2"
    python3 - "$CONTEXT_INDEX_DB" "$pkg_id" "$error" << 'PYTHON'
import sqlite3
import sys
from datetime import datetime, timezone

conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA busy_timeout = 5000")
conn.execute(
    """
    UPDATE package_meta
    SET refresh_status = 'failed',
        checked_at = ?,
        refresh_error = ?
    WHERE id = ?
    """,
    (datetime.now(timezone.utc).replace(microsecond=0).isoformat(), sys.argv[3], sys.argv[2]),
)
conn.commit()
conn.close()
PYTHON
}

_context_record_http_headers() {
    local pkg_id="$1" headers_file="$2"
    python3 - "$CONTEXT_INDEX_DB" "$pkg_id" "$headers_file" << 'PYTHON'
import sqlite3
import sys

db_path, pkg_id, headers_file = sys.argv[1:4]
etag = ""
last_modified = ""
try:
    with open(headers_file, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            lower = line.lower()
            if lower.startswith("etag:"):
                etag = line.split(":", 1)[1].strip()
            elif lower.startswith("last-modified:"):
                last_modified = line.split(":", 1)[1].strip()
except OSError:
    pass

conn = sqlite3.connect(db_path)
conn.execute("PRAGMA busy_timeout = 5000")
conn.execute(
    "UPDATE package_meta SET etag = ?, last_modified = ? WHERE id = ?",
    (etag, last_modified, pkg_id),
)
conn.commit()
conn.close()
PYTHON
}

_context_refresh_validators() {
    python3 - "$CONTEXT_INDEX_DB" "$1" << 'PYTHON'
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA busy_timeout = 5000")
row = conn.execute("SELECT COALESCE(etag, ''), COALESCE(last_modified, '') FROM package_meta WHERE id = ?", (sys.argv[2],)).fetchone()
conn.close()
print(row[0] if row else "")
print(row[1] if row else "")
PYTHON
}

_context_header_value() {
    local headers_file="$1" header_name="$2"
    python3 - "$headers_file" "$header_name" << 'PYTHON'
import sys

path, name = sys.argv[1:3]
needle = name.lower() + ":"
value = ""
try:
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.lower().startswith(needle):
                value = line.split(":", 1)[1].strip().lower()
except OSError:
    pass
print(value)
PYTHON
}

_context_refresh_result() {
    local pkg_id="$1" name="$2" status="$3" message="$4"
    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        python3 - "$pkg_id" "$name" "$status" "$message" << 'PYTHON'
import json
import sys

print(json.dumps({
    "success": True,
    "id": sys.argv[1],
    "name": sys.argv[2],
    "refresh_status": sys.argv[3],
    "message": sys.argv[4],
}, indent=2))
PYTHON
    else
        echo "Refreshed: $name ($pkg_id)"
        echo "  Status:  $status"
        echo "  Result:  $message"
    fi
}
