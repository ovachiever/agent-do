#!/usr/bin/env bash
# lib/search.sh — Search index and query for agent-context
# Sourced by agent-context entry point. Do not run directly.

# Index a package into SQLite FTS5
_index_package() {
    local id="$1" name="$2" type="$3" description="$4" tags="$5"
    local trust="$6" token_count="$7" cache_path="$8" source="$9"

    # Read first 500 chars of content for preview
    local content_preview=""
    for f in "$cache_path"/content.md "$cache_path"/DOC.md "$cache_path"/SKILL.md "$cache_path"/README.md; do
        if [[ -f "$f" ]]; then
            content_preview=$(head -c 500 "$f" | tr '\n' ' ')
            break
        fi
    done

    python3 - "$CONTEXT_INDEX_DB" "$id" "$name" "$type" "$description" "$tags" "$trust" "$token_count" "$cache_path" "$source" "$content_preview" << 'PYTHON'
import sqlite3, sys
from datetime import datetime, timezone

db, pkg_id, name, ptype, desc, tags, trust, tokens, cache_path, source, preview = sys.argv[1:12]

conn = sqlite3.connect(db)

# Remove existing entry if present
conn.execute("DELETE FROM packages WHERE id = ?", (pkg_id,))
conn.execute("DELETE FROM package_meta WHERE id = ?", (pkg_id,))

# Insert into FTS5
conn.execute(
    "INSERT INTO packages (id, name, description, tags, content_preview, source, trust, token_count, cache_path, type) VALUES (?,?,?,?,?,?,?,?,?,?)",
    (pkg_id, name, desc, tags, preview, source, trust, int(tokens), cache_path, ptype)
)

# Insert into meta table
now = datetime.now(timezone.utc).isoformat()
conn.execute(
    "INSERT INTO package_meta (id, name, type, trust, token_count, source, cache_path, fetched_at, last_accessed, access_count) VALUES (?,?,?,?,?,?,?,?,?,0)",
    (pkg_id, name, ptype, trust, int(tokens), source, cache_path, now, now)
)

conn.commit()
conn.close()
PYTHON
}

# Search across all indexed content
cmd_search() {
    local query="" limit="20" tags=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --limit) limit="$2"; shift 2 ;;
            --tags) tags="$2"; shift 2 ;;
            *) query="${query:+$query }$1"; shift ;;
        esac
    done

    [[ -n "$query" ]] || die "Usage: agent-context search <query> [--limit N] [--tags t1,t2]"
    ensure_init

    python3 - "$CONTEXT_INDEX_DB" "$query" "$limit" "$tags" "$CONTEXT_HOME/feedback.jsonl" "${OUTPUT_FORMAT:-text}" << 'PYTHON'
import sqlite3, sys, json, os

db_path, query, limit, tags_filter, feedback_path, output_format = sys.argv[1:7]
limit = int(limit)

conn = sqlite3.connect(db_path)

# Load feedback for score boosting
feedback = {}
if os.path.exists(feedback_path):
    with open(feedback_path) as f:
        for line in f:
            try:
                entry = json.loads(line)
                pkg = entry.get("package", "")
                rating = entry.get("rating", "")
                if pkg:
                    feedback[pkg] = feedback.get(pkg, 0) + (1 if rating == "up" else -1)
            except:
                pass

# Trust tier multipliers
TRUST_MULT = {"official": 1.5, "maintainer": 1.2, "local": 1.3, "community": 1.0}

# Keyword expansion for common aliases
EXPANSIONS = {
    "react": "react reactjs jsx",
    "next": "next nextjs",
    "vue": "vue vuejs",
    "python": "python python3 py",
    "js": "javascript js ecmascript",
    "ts": "typescript ts",
    "db": "database db sql",
    "css": "css stylesheet styling",
    "auth": "auth authentication authorization",
    "api": "api rest endpoint",
    "k8s": "kubernetes k8s",
    "docker": "docker container",
    "aws": "aws amazon",
    "gcp": "gcp google cloud",
    "ml": "ml machine learning ai",
    "llm": "llm language model ai",
}

# Expand query
expanded_terms = []
for word in query.lower().split():
    expanded_terms.append(word)
    if word in EXPANSIONS:
        for exp in EXPANSIONS[word].split():
            if exp != word:
                expanded_terms.append(exp)

# Build FTS5 query: OR of all terms
fts_query = " OR ".join(expanded_terms)

try:
    cursor = conn.execute(
        "SELECT id, name, description, tags, trust, token_count, type, cache_path, bm25(packages) as score "
        "FROM packages WHERE packages MATCH ? ORDER BY bm25(packages) LIMIT ?",
        (fts_query, limit * 3)  # Over-fetch for re-ranking
    )
    rows = cursor.fetchall()
except Exception as e:
    # Fallback: simple LIKE query
    rows = conn.execute(
        "SELECT id, name, description, tags, trust, token_count, type, cache_path, 0 "
        "FROM package_meta pm JOIN packages p ON pm.id = p.id "
        "WHERE p.name LIKE ? OR p.description LIKE ? LIMIT ?",
        (f"%{query}%", f"%{query}%", limit)
    ).fetchall()

# Re-rank with trust + feedback
results = []
for row in rows:
    pkg_id, name, desc, tags_str, trust, tokens, ptype, cache_path, bm25_score = row

    # Apply tag filter if specified
    if tags_filter:
        pkg_tags = set(t.strip().lower() for t in (tags_str or "").split(","))
        filter_tags = set(t.strip().lower() for t in tags_filter.split(","))
        if not filter_tags.intersection(pkg_tags):
            continue

    # Composite score
    trust_mult = TRUST_MULT.get(trust, 1.0)
    fb_score = feedback.get(pkg_id, 0)
    fb_mult = 1.1 if fb_score > 0 else (0.8 if fb_score < 0 else 1.0)

    # BM25 returns negative scores (lower = better match)
    final_score = abs(bm25_score) * trust_mult * fb_mult

    results.append({
        "id": pkg_id,
        "name": name,
        "description": desc,
        "type": ptype,
        "trust": trust,
        "token_count": int(tokens) if tokens else 0,
        "score": round(final_score, 3),
    })

results.sort(key=lambda x: x["score"], reverse=True)
results = results[:limit]

if output_format == "json":
    print(json.dumps({"success": True, "count": len(results), "results": results}, indent=2))
else:
    if not results:
        print(f"No results for '{query}'")
    else:
        print(f"Found {len(results)} result(s) for '{query}':\n")
        for r in results:
            trust_badge = {"official": "[*]", "maintainer": "[M]", "community": "[C]", "local": "[L]"}.get(r["trust"], "[ ]")
            print(f"  {trust_badge} {r['name']} ({r['id']})")
            print(f"      {r['description']}")
            print(f"      Type: {r['type']}  Tokens: ~{r['token_count']}  Score: {r['score']}")
            print()

conn.close()
PYTHON
}

# Get a specific package by ID
cmd_get() {
    local pkg_id="" file_filter="" full=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --file) file_filter="$2"; shift 2 ;;
            --full) full=true; shift ;;
            *) pkg_id="$1"; shift ;;
        esac
    done

    [[ -n "$pkg_id" ]] || die "Usage: agent-context get <id> [--file <name>] [--full]"
    ensure_init

    # Look up in meta table
    local result
    result=$(python3 - "$CONTEXT_INDEX_DB" "$pkg_id" << 'PYTHON'
import sqlite3, sys, json

conn = sqlite3.connect(sys.argv[1])
pkg_id = sys.argv[2]

row = conn.execute(
    "SELECT id, name, type, trust, token_count, source, cache_path, fetched_at FROM package_meta WHERE id = ?",
    (pkg_id,)
).fetchone()

if not row:
    # Try fuzzy match on name
    rows = conn.execute(
        "SELECT id, name, type, trust, token_count, source, cache_path, fetched_at FROM package_meta WHERE name LIKE ? OR id LIKE ?",
        (f"%{pkg_id}%", f"%{pkg_id}%")
    ).fetchall()
    if len(rows) == 1:
        row = rows[0]
    elif len(rows) > 1:
        suggestions = [{"id": r[0], "name": r[1]} for r in rows[:5]]
        print(json.dumps({"found": False, "suggestions": suggestions}))
        sys.exit(0)
    else:
        print(json.dumps({"found": False, "suggestions": []}))
        sys.exit(0)

# Update access stats
from datetime import datetime, timezone
now = datetime.now(timezone.utc).isoformat()
conn.execute(
    "UPDATE package_meta SET last_accessed = ?, access_count = access_count + 1 WHERE id = ?",
    (now, row[0])
)
conn.commit()

print(json.dumps({
    "found": True,
    "id": row[0], "name": row[1], "type": row[2], "trust": row[3],
    "token_count": row[4], "source": row[5], "cache_path": row[6], "fetched_at": row[7]
}))
conn.close()
PYTHON
    )

    local found
    found=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('found', False))")

    if [[ "$found" != "True" ]]; then
        local suggestions
        suggestions=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f\"  {s['id']}  ({s['name']})\" ) for s in d.get('suggestions',[])]" 2>/dev/null || true)
        if [[ -n "$suggestions" ]]; then
            if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
                json_result "$result"
            else
                echo "Package '$pkg_id' not found. Did you mean:"
                echo "$suggestions"
            fi
        else
            if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
                json_error "Package '$pkg_id' not found"
            else
                echo "Package '$pkg_id' not found. Try: agent-context search <query>" >&2
            fi
        fi
        return 1
    fi

    local cache_path name trust token_count
    cache_path=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['cache_path'])")
    name=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
    trust=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['trust'])")
    token_count=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['token_count'])")

    # Find content file(s)
    if [[ -n "$file_filter" ]]; then
        # Specific file requested
        local target="$cache_path/$file_filter"
        [[ -f "$target" ]] || die "File not found: $file_filter in $pkg_id"
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            _get_json_output "$pkg_id" "$name" "$trust" "$token_count" "$target"
        else
            cat "$target"
        fi
    elif [[ "$full" == "true" ]]; then
        # All files
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            _get_json_full "$pkg_id" "$name" "$trust" "$token_count" "$cache_path"
        else
            for f in "$cache_path"/*.md "$cache_path"/*.txt; do
                [[ -f "$f" ]] || continue
                echo "--- $(basename "$f") ---"
                cat "$f"
                echo ""
            done
        fi
    else
        # Main content file
        local main_file=""
        for candidate in content.md DOC.md SKILL.md README.md; do
            if [[ -f "$cache_path/$candidate" ]]; then
                main_file="$cache_path/$candidate"
                break
            fi
        done
        # Fall back to first .md file
        if [[ -z "$main_file" ]]; then
            main_file=$(find "$cache_path" -name "*.md" -o -name "*.txt" 2>/dev/null | head -1)
        fi

        [[ -n "$main_file" && -f "$main_file" ]] || die "No content found for $pkg_id"

        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            _get_json_output "$pkg_id" "$name" "$trust" "$token_count" "$main_file"
        else
            cat "$main_file"
            # Show annotations if any
            _show_annotations "$pkg_id"
            # Show additional files hint
            local extra_files
            extra_files=$(find "$cache_path" -name "*.md" -o -name "*.txt" 2>/dev/null | wc -l | tr -d ' ')
            if [[ "$extra_files" -gt 1 ]]; then
                echo ""
                echo "---"
                echo "Additional files available (use --file or --full):"
                for f in "$cache_path"/*.md "$cache_path"/*.txt; do
                    [[ -f "$f" ]] || continue
                    [[ "$f" == "$main_file" ]] && continue
                    echo "  $(basename "$f")"
                done
            fi
        fi
    fi
}

# JSON output for get command (single file)
_get_json_output() {
    local pkg_id="$1" name="$2" trust="$3" token_count="$4" file="$5"
    python3 - "$pkg_id" "$name" "$trust" "$token_count" "$file" "$CONTEXT_HOME/annotations.jsonl" << 'PYTHON'
import json, sys, os

pkg_id, name, trust, tokens, filepath, annotations_path = sys.argv[1:7]

with open(filepath) as f:
    content = f.read()

# Load annotations
annotations = []
if os.path.exists(annotations_path):
    with open(annotations_path) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("package") == pkg_id:
                    annotations.append(entry.get("note", ""))
            except:
                pass

result = {
    "id": pkg_id,
    "name": name,
    "trust": trust,
    "token_count": int(tokens),
    "content": content,
    "annotations": annotations,
}
print(json.dumps({"success": True, "result": result}, indent=2))
PYTHON
}

# JSON output for get --full
_get_json_full() {
    local pkg_id="$1" name="$2" trust="$3" token_count="$4" cache_path="$5"
    python3 - "$pkg_id" "$name" "$trust" "$token_count" "$cache_path" << 'PYTHON'
import json, sys, os, glob

pkg_id, name, trust, tokens, cache_path = sys.argv[1:6]

files = {}
for pattern in ["*.md", "*.txt"]:
    for fp in glob.glob(os.path.join(cache_path, pattern)):
        with open(fp) as f:
            files[os.path.basename(fp)] = f.read()

result = {
    "id": pkg_id,
    "name": name,
    "trust": trust,
    "token_count": int(tokens),
    "files": files,
}
print(json.dumps({"success": True, "result": result}, indent=2))
PYTHON
}

# Show annotations inline (text mode)
_show_annotations() {
    local pkg_id="$1"
    local annotations_file="$CONTEXT_HOME/annotations.jsonl"
    [[ -f "$annotations_file" && -s "$annotations_file" ]] || return 0

    local notes
    notes=$(python3 -c "
import json, sys
pkg = sys.argv[1]
with open(sys.argv[2]) as f:
    for line in f:
        try:
            e = json.loads(line)
            if e.get('package') == pkg:
                print(f\"  [{e.get('created','')}] {e.get('note','')}\")
        except:
            pass
" "$pkg_id" "$annotations_file" 2>/dev/null || true)

    if [[ -n "$notes" ]]; then
        echo ""
        echo "--- Annotations ---"
        echo "$notes"
    fi
}

# List all indexed packages
cmd_list() {
    local source_filter="" tags_filter=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --source) source_filter="$2"; shift 2 ;;
            --tags) tags_filter="$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    ensure_init

    python3 - "$CONTEXT_INDEX_DB" "$source_filter" "$tags_filter" "${OUTPUT_FORMAT:-text}" << 'PYTHON'
import sqlite3, sys, json

db_path, source_filter, tags_filter, output_format = sys.argv[1:5]

conn = sqlite3.connect(db_path)

query = "SELECT id, name, type, trust, token_count, source, fetched_at FROM package_meta ORDER BY name"
rows = conn.execute(query).fetchall()

results = []
for row in rows:
    pkg_id, name, ptype, trust, tokens, source, fetched_at = row

    if source_filter and source_filter.lower() not in (source or "").lower():
        continue

    results.append({
        "id": pkg_id,
        "name": name,
        "type": ptype,
        "trust": trust,
        "token_count": int(tokens) if tokens else 0,
        "source": source or "",
    })

if output_format == "json":
    print(json.dumps({"success": True, "count": len(results), "packages": results}, indent=2))
else:
    if not results:
        print("No packages indexed. Try: agent-context fetch <url>")
    else:
        print(f"{len(results)} package(s):\n")
        for r in results:
            badge = {"official": "[*]", "maintainer": "[M]", "community": "[C]", "local": "[L]"}.get(r["trust"], "[ ]")
            print(f"  {badge} {r['name']:30s} {r['type']:10s} ~{r['token_count']} tokens")

conn.close()
PYTHON
}
