#!/usr/bin/env bash
# lib/fetch.sh — Content fetching for agent-context
# Sourced by agent-context entry point. Do not run directly.

# Fetch markdown from any URL
cmd_fetch() {
    local url=""
    local tags=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tags) tags="$2"; shift 2 ;;
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
    local http_code content_file="$pkg_dir/content.md"
    http_code=$(curl -sL -w "%{http_code}" -o "$content_file" "$url" 2>/dev/null) || true

    if [[ "$http_code" != "200" ]]; then
        rm -rf "$pkg_dir"
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "Fetch failed: HTTP $http_code for $url"
        else
            die "Fetch failed: HTTP $http_code for $url"
        fi
        return 1
    fi

    # Check if content is actually markdown-like (not HTML error page)
    local first_bytes
    first_bytes=$(head -c 20 "$content_file")
    if [[ "$first_bytes" == "<!DOCTYPE"* ]] || [[ "$first_bytes" == "<html"* ]]; then
        rm -rf "$pkg_dir"
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "URL returned HTML, not markdown: $url"
        else
            die "URL returned HTML, not markdown. Use a raw content URL."
        fi
        return 1
    fi

    # Extract frontmatter if present, otherwise generate
    local meta_json
    meta_json=$(extract_frontmatter "$content_file")
    local name
    name=$(echo "$meta_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('name',''))" 2>/dev/null || true)
    [[ -n "$name" ]] || name="$id"

    local description
    description=$(echo "$meta_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description',''))" 2>/dev/null || true)
    [[ -n "$description" ]] || description="Fetched from $url"

    local token_count
    token_count=$(count_tokens "$content_file")

    # Write meta.json
    write_meta "$pkg_dir" "$name" "reference" "$description" "$url" "$token_count" "community" "$tags"

    # Index into FTS5
    _index_package "$id" "$name" "reference" "$description" "$tags" "community" "$token_count" "$pkg_dir" "$url"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$(python3 -c "
import json
print(json.dumps({
    'id': '$id',
    'name': '$name',
    'description': '$description',
    'token_count': $token_count,
    'source': '$url',
    'cached_at': '$pkg_dir'
}))
")"
    else
        echo "Fetched: $name ($id)"
        echo "  Source:  $url"
        echo "  Tokens:  ~$token_count"
        echo "  Cached:  $pkg_dir"
    fi
}

# Fetch llms.txt / llms-full.txt from a domain
cmd_fetch_llms() {
    local domain=""
    local tags=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tags) tags="$2"; shift 2 ;;
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
    local url="" http_code content_file="$pkg_dir/content.md"
    local found=false

    for path in "llms-full.txt" "llms.txt"; do
        url="https://${domain}/${path}"
        http_code=$(curl -sL -w "%{http_code}" -o "$content_file" "$url" 2>/dev/null) || true
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

    write_meta "$pkg_dir" "$name" "reference" "$description" "$url" "$token_count" "community" "$tags"
    _index_package "$id" "$name" "reference" "$description" "$tags" "community" "$token_count" "$pkg_dir" "$url"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$(python3 -c "
import json
print(json.dumps({
    'id': '$id',
    'name': '$name',
    'description': '$description',
    'token_count': $token_count,
    'source': '$url',
    'cached_at': '$pkg_dir'
}))
")"
    else
        echo "Fetched: $name ($id)"
        echo "  Source:  $url"
        echo "  Tokens:  ~$token_count"
        echo "  Cached:  $pkg_dir"
    fi
}

# Fetch docs from a GitHub repo
cmd_fetch_repo() {
    local repo="" path="" tags=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tags) tags="$2"; shift 2 ;;
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
    if [[ -n "$path" ]]; then
        _fetch_repo_path "$repo" "$path" "$pkg_dir"
    else
        # Try README.md, then docs/, then llms.txt
        local found=false
        for try_path in "README.md" "llms.txt" "llms-full.txt" "docs/README.md"; do
            if _fetch_repo_path "$repo" "$try_path" "$pkg_dir" 2>/dev/null; then
                found=true
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
    local token_count=0
    for f in "$pkg_dir"/*.md "$pkg_dir"/*.txt; do
        [[ -f "$f" ]] || continue
        local tc
        tc=$(count_tokens "$f")
        token_count=$((token_count + tc))
    done

    write_meta "$pkg_dir" "$name" "doc" "$description" "https://github.com/$repo" "$token_count" "community" "$tags"
    _index_package "$id" "$name" "doc" "$description" "$tags" "community" "$token_count" "$pkg_dir" "https://github.com/$repo"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$(python3 -c "
import json
print(json.dumps({
    'id': '$id',
    'name': '$name',
    'description': '$description',
    'token_count': $token_count,
    'source': 'https://github.com/$repo'
}))
")"
    else
        echo "Fetched: $name"
        echo "  Source:  https://github.com/$repo"
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
    content=$(gh api "repos/$repo/contents/$path" --jq '.content' 2>/dev/null) || return 1
    [[ -n "$content" && "$content" != "null" ]] || return 1

    echo "$content" | base64 -d > "$dest_dir/$filename"
    return 0
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
        json_result "$(python3 -c "
import json
print(json.dumps({
    'id': '$id',
    'name': 'local-${project_name}',
    'files_indexed': $count,
    'token_count': $token_count
}))
")"
    else
        echo "Indexed: local-${project_name}"
        echo "  Files: $count context files"
        echo "  Tokens: ~$token_count"
    fi
}

# Index ~/.claude/skills/ directory
cmd_scan_skills() {
    ensure_init

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
        local id
        id=$(make_id "skill-${skill_name}")
        local pkg_dir="$CONTEXT_CACHE_DIR/skills/$id"
        mkdir -p "$pkg_dir"

        cp "$skill_file" "$pkg_dir/SKILL.md"

        local meta_json
        meta_json=$(extract_frontmatter "$skill_file")
        local description
        description=$(echo "$meta_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description','Skill: $skill_name'))" 2>/dev/null || echo "Skill: $skill_name")

        local token_count
        token_count=$(count_tokens "$skill_file")
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
        json_result "$(python3 -c "
import json
print(json.dumps({
    'skills_indexed': $count,
    'total_tokens': $total_tokens
}))
")"
    else
        echo "Indexed $count skills (~$total_tokens tokens)"
    fi
}
