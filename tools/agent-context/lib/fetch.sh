#!/usr/bin/env bash
# lib/fetch.sh — Content fetching for agent-context
# Sourced by agent-context entry point. Do not run directly.

# Fetch markdown from any URL
cmd_fetch() {
    local url=""
    local tags="" trust="community"
    local register_source=false source_name=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tags) tags="$2"; shift 2 ;;
            --trust) trust="$2"; shift 2 ;;
            --register-source) register_source=true; shift ;;
            --source-name) source_name="$2"; shift 2 ;;
            *) url="$1"; shift ;;
        esac
    done

    [[ -n "$url" ]] || die "Usage: agent-context fetch <url> [--tags t1,t2]"
    ensure_init

    local id
    id=$(make_id "$url")
    local pkg_dir="$CONTEXT_CACHE_DIR/fetched/$id"
    mkdir -p "$pkg_dir"

    # Fetch content
    local http_code content_file="$pkg_dir/content.md" headers_file="$pkg_dir/headers.txt"
    http_code=$(curl -q -sL --connect-timeout 5 --max-time 20 -D "$headers_file" -w "%{http_code}" -o "$content_file" "$url" 2>/dev/null) || true

    if [[ "$http_code" != "200" ]]; then
        rm -rf "$pkg_dir"
        local safe_url
        safe_url=$(redact_url "$url")
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "Fetch failed: HTTP $http_code for $safe_url"
        else
            die "Fetch failed: HTTP $http_code for $safe_url"
        fi
        return 1
    fi

    local is_html=false source_type="reference"
    if type _context_is_html_response &>/dev/null && _context_is_html_response "$headers_file" "$content_file"; then
        is_html=true
        source_type="html-page"
        _context_store_html_file "$url" "$content_file" "$headers_file" "$pkg_dir"
        content_file="$pkg_dir/content.md"
    fi

    # Extract frontmatter if present, otherwise generate
    local meta_json name description canonical_url
    if [[ "$is_html" == "true" && -f "$pkg_dir/metadata.json" ]]; then
        meta_json="{}"
        name=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("title",""))' "$pkg_dir/metadata.json" 2>/dev/null || true)
        description=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("description",""))' "$pkg_dir/metadata.json" 2>/dev/null || true)
        canonical_url=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("canonical_url",""))' "$pkg_dir/metadata.json" 2>/dev/null || true)
    else
        meta_json=$(extract_frontmatter "$content_file")
        name=$(echo "$meta_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('name',''))" 2>/dev/null || true)
        description=$(echo "$meta_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description',''))" 2>/dev/null || true)
    fi
    [[ -n "$name" ]] || name="$id"

    [[ -n "$description" ]] || description="Fetched from $url"
    [[ -n "${canonical_url:-}" ]] || canonical_url="$url"

    local token_count
    token_count=$(count_tokens "$content_file")

    # Write meta.json
    write_meta "$pkg_dir" "$name" "$source_type" "$description" "$url" "$token_count" "$trust" "$tags"

    # Index into FTS5
    _index_package "$id" "$name" "$source_type" "$description" "$tags" "$trust" "$token_count" "$pkg_dir" "$canonical_url"
    type _context_record_http_headers &>/dev/null && _context_record_http_headers "$id" "$headers_file"
    if [[ "$register_source" == "true" ]] && type _context_sources_run &>/dev/null; then
        [[ -n "$source_name" ]] || source_name="$name"
        local registered_kind="url"
        [[ "$is_html" == "true" ]] && registered_kind="html-page"
        _context_sources_run add "$source_name" "$url" "$trust" "$registered_kind" "7d" "$tags" "" "true" "200" "on-use" >/dev/null
    fi

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        local safe_url payload
        safe_url=$(redact_url "$url")
        payload=$(python3 - "$id" "$name" "$description" "$token_count" "$safe_url" "$pkg_dir" << 'PYTHON'
import json
import sys

package_id, name, description, token_count, source, cached_at = sys.argv[1:7]
print(json.dumps({
    "id": package_id,
    "name": name,
    "description": description,
    "token_count": int(token_count),
    "source": source,
    "cached_at": cached_at,
}))
PYTHON
)
        json_result "$payload"
    else
        echo "Fetched: $name ($id)"
        echo "  Source:  $(redact_url "$url")"
        echo "  Tokens:  ~$token_count"
        echo "  Cached:  $pkg_dir"
    fi
}

# Fetch llms.txt / llms-full.txt from a domain
cmd_fetch_llms() {
    local domain=""
    local tags="" trust="community"
    local register_source=false source_name=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tags) tags="$2"; shift 2 ;;
            --trust) trust="$2"; shift 2 ;;
            --register-source) register_source=true; shift ;;
            --source-name) source_name="$2"; shift 2 ;;
            *) domain="$1"; shift ;;
        esac
    done

    [[ -n "$domain" ]] || die "Usage: agent-context fetch-llms <domain> [--tags t1,t2]"
    ensure_init

    # Strip protocol if present
    domain="${domain#https://}"
    domain="${domain#http://}"
    domain="${domain%%/*}"

    local id
    id=$(make_id "${domain}-llms")
    local pkg_dir="$CONTEXT_CACHE_DIR/fetched/$id"
    mkdir -p "$pkg_dir"

    # Try llms-full.txt first, fall back to llms.txt
    local url="" http_code content_file="$pkg_dir/content.md" headers_file="$pkg_dir/headers.txt"
    local found=false

    for path in "llms-full.txt" "llms.txt"; do
        url="https://${domain}/${path}"
        http_code=$(curl -q -sL --connect-timeout 5 --max-time 20 -D "$headers_file" -w "%{http_code}" -o "$content_file" "$url" 2>/dev/null) || true
        if [[ "$http_code" == "200" ]]; then
            # Verify it's text, not an error page
            local first_bytes
            first_bytes=$(head -c 20 "$content_file")
            if [[ "$first_bytes" != "<!DOCTYPE"* ]] && [[ "$first_bytes" != "<html"* ]]; then
                found=true
                break
            fi
        fi
    done

    if [[ "$found" != "true" ]]; then
        rm -rf "$pkg_dir"
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "No llms.txt or llms-full.txt found at $domain"
        else
            die "No llms.txt or llms-full.txt found at $domain"
        fi
        return 1
    fi

    local name="${domain}-llms"
    local description="LLM documentation from ${domain}"
    local token_count
    token_count=$(count_tokens "$content_file")

    write_meta "$pkg_dir" "$name" "reference" "$description" "$url" "$token_count" "$trust" "$tags"
    _index_package "$id" "$name" "reference" "$description" "$tags" "$trust" "$token_count" "$pkg_dir" "$url"
    type _context_record_http_headers &>/dev/null && _context_record_http_headers "$id" "$headers_file"
    if [[ "$register_source" == "true" ]] && type _context_sources_run &>/dev/null; then
        [[ -n "$source_name" ]] || source_name="$name"
        _context_sources_run add "$source_name" "$domain" "$trust" "llms" "7d" "$tags" "" "true" "200" "on-use" >/dev/null
    fi

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        local safe_url payload
        safe_url=$(redact_url "$url")
        payload=$(python3 - "$id" "$name" "$description" "$token_count" "$safe_url" "$pkg_dir" << 'PYTHON'
import json
import sys

package_id, name, description, token_count, source, cached_at = sys.argv[1:7]
print(json.dumps({
    "id": package_id,
    "name": name,
    "description": description,
    "token_count": int(token_count),
    "source": source,
    "cached_at": cached_at,
}))
PYTHON
)
        json_result "$payload"
    else
        echo "Fetched: $name ($id)"
        echo "  Source:  $(redact_url "$url")"
        echo "  Tokens:  ~$token_count"
        echo "  Cached:  $pkg_dir"
    fi
}

# Fetch docs from a GitHub repo
cmd_fetch_repo() {
    local repo="" path="" tags="" trust="community"
    local register_source=false source_name=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tags) tags="$2"; shift 2 ;;
            --trust) trust="$2"; shift 2 ;;
            --register-source) register_source=true; shift ;;
            --source-name) source_name="$2"; shift 2 ;;
            *)
                if [[ -z "$repo" ]]; then
                    repo="$1"
                else
                    path="$1"
                fi
                shift
                ;;
        esac
    done

    [[ -n "$repo" ]] || die "Usage: agent-context fetch-repo <owner/repo> [path] [--tags t1,t2]"
    command -v gh &>/dev/null || die "gh CLI required for fetch-repo. Install: https://cli.github.com"
    ensure_init

    local id
    id=$(make_id "$repo")
    local pkg_dir="$CONTEXT_CACHE_DIR/fetched/$id"
    mkdir -p "$pkg_dir"

    # If path specified, fetch that file/directory; otherwise try common doc locations
    local fetched_path="$path"
    if [[ -n "$path" ]]; then
        _fetch_repo_path "$repo" "$path" "$pkg_dir"
    else
        # Try README.md, then docs/, then llms.txt
        local found=false
        for try_path in "README.md" "llms.txt" "llms-full.txt" "docs/README.md"; do
            if _fetch_repo_path "$repo" "$try_path" "$pkg_dir" 2>/dev/null; then
                found=true
                fetched_path="$try_path"
                break
            fi
        done
        [[ "$found" == "true" ]] || {
            rm -rf "$pkg_dir"
            die "No docs found in $repo. Specify a path: agent-context fetch-repo $repo <path>"
        }
    fi

    local name="$id"
    local description="Docs from github.com/$repo"
    local token_count=0 file_count source_url
    token_count=$(_context_count_tree_tokens "$pkg_dir")
    file_count=$(find "$pkg_dir" -type f \( -name "*.md" -o -name "*.mdx" -o -name "*.txt" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.json" -o -name "*.yaml" -o -name "*.yml" -o -name "*.py" -o -name "*.sh" -o -name "*.css" -o -name "*.html" -o -name "*.sql" -o -name "*.toml" \) 2>/dev/null | wc -l | tr -d ' ')
    if [[ -n "$fetched_path" && "$file_count" -gt 1 ]]; then
        source_url="https://github.com/$repo/tree/HEAD/${fetched_path%/}"
    elif [[ -n "$fetched_path" ]]; then
        source_url="https://github.com/$repo/blob/HEAD/${fetched_path%/}"
    else
        source_url="https://github.com/$repo"
    fi

    write_meta "$pkg_dir" "$name" "doc" "$description" "$source_url" "$token_count" "$trust" "$tags"
    _index_package "$id" "$name" "doc" "$description" "$tags" "$trust" "$token_count" "$pkg_dir" "$source_url"
    if [[ "$register_source" == "true" ]] && type _context_sources_run &>/dev/null; then
        [[ -n "$source_name" ]] || source_name="$name"
        local source_kind
        source_kind=$(_context_infer_source_kind "$source_url")
        _context_sources_run add "$source_name" "$source_url" "$trust" "$source_kind" "7d" "$tags" "" "true" "200" "on-use" >/dev/null
    fi

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        local safe_source_url payload
        safe_source_url=$(redact_url "$source_url")
        payload=$(python3 - "$id" "$name" "$description" "$token_count" "$safe_source_url" << 'PYTHON'
import json
import sys

package_id, name, description, token_count, source = sys.argv[1:6]
print(json.dumps({
    "id": package_id,
    "name": name,
    "description": description,
    "token_count": int(token_count),
    "source": source,
}))
PYTHON
)
        json_result "$payload"
    else
        echo "Fetched: $name"
        echo "  Source:  $(redact_url "$source_url")"
        echo "  Tokens:  ~$token_count"
        echo "  Cached:  $pkg_dir"
    fi
}

# Helper: fetch a single file from a GitHub repo
_fetch_repo_path() {
    local repo="$1" path="$2" dest_dir="$3"
    local filename
    filename=$(basename "$path")

    # Try to get file content via gh api
    local content
    content=$(gh api "repos/$repo/contents/$path" --jq '.content // empty' 2>/dev/null || true)

    if [[ -n "$content" && "$content" != "null" ]]; then
        echo "$content" | base64 -d > "$dest_dir/$filename"
        return 0
    fi

    type _context_fetch_github_directory &>/dev/null || return 1
    _context_fetch_github_directory "$repo" "HEAD" "$path" "$dest_dir"
}

# Index local project files
cmd_scan_local() {
    local target_dir="${1:-.}"
    ensure_init

    [[ -d "$target_dir" ]] || die "Directory not found: $target_dir"

    local project_name
    project_name=$(basename "$(cd "$target_dir" && pwd)")
    local id
    id=$(make_id "local-${project_name}")
    local pkg_dir="$CONTEXT_CACHE_DIR/local/$id"
    mkdir -p "$pkg_dir"

    local count=0
    for candidate in CLAUDE.md .claude/CLAUDE.md .cursorrules .cursor/rules .github/copilot-instructions.md README.md; do
        local src="$target_dir/$candidate"
        if [[ -f "$src" ]]; then
            local dest_name
            dest_name=$(echo "$candidate" | tr '/' '-')
            cp "$src" "$pkg_dir/$dest_name"
            count=$((count + 1))
        fi
    done

    if [[ $count -eq 0 ]]; then
        rm -rf "$pkg_dir"
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "No project context files found in $target_dir"
        else
            echo "No project context files found in $target_dir" >&2
        fi
        return 1
    fi

    local token_count=0
    for f in "$pkg_dir"/*; do
        [[ -f "$f" ]] || continue
        local tc
        tc=$(count_tokens "$f")
        token_count=$((token_count + tc))
    done

    local description="Local project context from $project_name"
    write_meta "$pkg_dir" "local-${project_name}" "local" "$description" "$target_dir" "$token_count" "local" ""
    _index_package "$id" "local-${project_name}" "local" "$description" "" "local" "$token_count" "$pkg_dir" "$target_dir"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        local payload
        payload=$(python3 - "$id" "local-${project_name}" "$count" "$token_count" << 'PYTHON'
import json
import sys

package_id, name, files_indexed, token_count = sys.argv[1:5]
print(json.dumps({
    "id": package_id,
    "name": name,
    "files_indexed": int(files_indexed),
    "token_count": int(token_count),
}))
PYTHON
)
        json_result "$payload"
    else
        echo "Indexed: local-${project_name}"
        echo "  Files: $count context files"
        echo "  Tokens: ~$token_count"
    fi
}

# Index ~/.claude/skills/ directory
cmd_scan_skills() {
    ensure_init
    local requested=("$@")

    local skills_dir="${HOME}/.claude/skills"
    [[ -d "$skills_dir" ]] || die "Skills directory not found: $skills_dir"

    local count=0
    local total_tokens=0

    for skill_dir in "$skills_dir"/*/; do
        [[ -d "$skill_dir" ]] || continue
        local skill_file="$skill_dir/SKILL.md"
        [[ -f "$skill_file" ]] || continue

        local skill_name
        skill_name=$(basename "$skill_dir")
        if [[ "${#requested[@]}" -gt 0 ]]; then
            local matched=false
            local requested_name
            for requested_name in "${requested[@]}"; do
                if [[ "$skill_name" == "$requested_name" ]]; then
                    matched=true
                    break
                fi
            done
            [[ "$matched" == "true" ]] || continue
        fi
        local id
        id=$(make_id "skill-${skill_name}")
        local pkg_dir="$CONTEXT_CACHE_DIR/skills/$id"
        rm -rf "$pkg_dir"
        mkdir -p "$pkg_dir"

        cp "$skill_file" "$pkg_dir/SKILL.md"
        python3 - "$skill_dir" "$pkg_dir" << 'PYTHON'
import os
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
    if not path.is_file():
        continue
    rel = path.relative_to(src_root)
    if rel.name == "SKILL.md":
        continue
    if path.suffix.lower() not in extensions:
        continue
    target = dest_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
PYTHON

        local meta_json
        meta_json=$(extract_frontmatter "$skill_file")
        local description
        description=$(echo "$meta_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description','Skill: $skill_name'))" 2>/dev/null || echo "Skill: $skill_name")

        local token_count
        token_count=0
        while IFS= read -r indexed_file; do
            local tc
            tc=$(count_tokens "$indexed_file")
            token_count=$((token_count + tc))
        done < <(find "$pkg_dir" -type f \( -name "*.md" -o -name "*.mdx" -o -name "*.txt" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.json" -o -name "*.yaml" -o -name "*.yml" -o -name "*.py" -o -name "*.sh" -o -name "*.css" -o -name "*.html" -o -name "*.sql" -o -name "*.toml" \) 2>/dev/null)
        total_tokens=$((total_tokens + token_count))

        local skill_tags
        skill_tags=$(echo "$meta_json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
tags = d.get('tags', [])
if isinstance(tags, list):
    print(','.join(str(t) for t in tags))
elif isinstance(tags, str):
    print(tags)
else:
    print('')
" 2>/dev/null || echo "")

        write_meta "$pkg_dir" "$skill_name" "skill" "$description" "$skills_dir" "$token_count" "local" "$skill_tags"
        _index_package "$id" "$skill_name" "skill" "$description" "$skill_tags" "local" "$token_count" "$pkg_dir" "$skills_dir"

        count=$((count + 1))
    done

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        local payload
        payload=$(python3 - "$count" "$total_tokens" << 'PYTHON'
import json
import sys

skills_indexed, total_tokens = sys.argv[1:3]
print(json.dumps({
    "skills_indexed": int(skills_indexed),
    "total_tokens": int(total_tokens),
}))
PYTHON
)
        json_result "$payload"
    else
        echo "Indexed $count skills (~$total_tokens tokens)"
    fi
}
