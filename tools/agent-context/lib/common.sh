#!/usr/bin/env bash
# lib/common.sh — Shared utilities for agent-context
# Sourced by agent-context entry point. Do not run directly.

CONTEXT_HOME="${AGENT_DO_HOME:-$HOME/.agent-do}/context"
CONTEXT_CACHE_DIR="$CONTEXT_HOME/cache"
CONTEXT_INDEX_DB="$CONTEXT_HOME/index.db"

die() { echo "Error: $*" >&2; exit 1; }

today() { date +%Y-%m-%d; }
now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

ensure_init() {
    [[ -d "$CONTEXT_HOME" ]] || {
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_error "Not initialized. Run 'agent-do context init' first." 1
        else
            echo "Error: Not initialized. Run 'agent-do context init' first." >&2
        fi
        exit 1
    }
}

validate_json() {
    echo "$1" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null
}

append_jsonl() {
    local file="$1" line="$2"
    validate_json "$line" || {
        echo "Error: Invalid JSON: $line" >&2
        return 1
    }
    echo "$line" >> "$file"
}

count_lines() {
    local file="$1"
    [[ -f "$file" && -s "$file" ]] && wc -l < "$file" | tr -d ' ' || echo "0"
}

# Approximate token count: words * 1.3
count_tokens() {
    local file="$1"
    if [[ -f "$file" ]]; then
        python3 -c "
import sys
with open(sys.argv[1]) as f:
    words = len(f.read().split())
print(int(words * 1.3))
" "$file"
    else
        echo "0"
    fi
}

# Generate a safe filesystem ID from a URL or name
make_id() {
    python3 -c "
import sys, re
raw = sys.argv[1]
# Strip protocol
raw = re.sub(r'^https?://', '', raw)
# Replace non-alphanumeric with hyphens, collapse
safe = re.sub(r'[^a-zA-Z0-9]+', '-', raw).strip('-').lower()
# Truncate
print(safe[:80])
" "$1"
}

# Extract YAML frontmatter from a markdown file
extract_frontmatter() {
    local file="$1"
    python3 - "$file" << 'PYTHON'
import sys, json

path = sys.argv[1]
with open(path) as f:
    content = f.read()

# Check for YAML frontmatter
if not content.startswith('---'):
    print('{}')
    sys.exit(0)

parts = content.split('---', 2)
if len(parts) < 3:
    print('{}')
    sys.exit(0)

try:
    import yaml
    meta = yaml.safe_load(parts[1])
    print(json.dumps(meta or {}, ensure_ascii=False))
except ImportError:
    # Fallback: parse simple key: value pairs
    meta = {}
    for line in parts[1].strip().split('\n'):
        if ':' in line:
            k, v = line.split(':', 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    print(json.dumps(meta, ensure_ascii=False))
except Exception:
    print('{}')
PYTHON
}

# Strip YAML frontmatter, return body only
strip_frontmatter() {
    local file="$1"
    python3 -c "
import sys
with open(sys.argv[1]) as f:
    content = f.read()
if content.startswith('---'):
    parts = content.split('---', 2)
    if len(parts) >= 3:
        print(parts[2].strip())
    else:
        print(content)
else:
    print(content)
" "$file"
}

# Write meta.json for a cached package
write_meta() {
    local dir="$1" name="$2" type="$3" description="$4" source_url="$5" token_count="$6"
    local trust="${7:-community}" tags="${8:-}"
    python3 - "$dir" "$name" "$type" "$description" "$source_url" "$token_count" "$trust" "$tags" << 'PYTHON'
import json, sys
from datetime import datetime, timezone

meta = {
    "name": sys.argv[2],
    "type": sys.argv[3],
    "description": sys.argv[4],
    "source": sys.argv[5],
    "token_count": int(sys.argv[6]),
    "trust": sys.argv[7],
    "tags": [t.strip() for t in sys.argv[8].split(",") if t.strip()],
    "fetched_at": datetime.now(timezone.utc).isoformat(),
}
with open(f"{sys.argv[1]}/meta.json", "w") as f:
    json.dump(meta, f, indent=2, ensure_ascii=False)
PYTHON
}

# Initialize storage
cmd_init() {
    if [[ -d "$CONTEXT_HOME" ]]; then
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_success "Already initialized at $CONTEXT_HOME"
        else
            echo "Already initialized at $CONTEXT_HOME"
        fi
        return 0
    fi

    mkdir -p "$CONTEXT_CACHE_DIR"
    mkdir -p "$CONTEXT_HOME"

    # Default config
    cat > "$CONTEXT_HOME/config.yaml" << 'YAML'
# agent-context configuration
sources: []

trust_policy:
  allow: [official, maintainer, community, local]
  prefer: official

defaults:
  max_tokens: 8000
  cache_max_mb: 500
  ttl: 7d
YAML

    # Initialize empty JSONL files
    touch "$CONTEXT_HOME/annotations.jsonl"
    touch "$CONTEXT_HOME/feedback.jsonl"

    # Initialize FTS5 index
    python3 - "$CONTEXT_INDEX_DB" << 'PYTHON'
import sqlite3, sys

conn = sqlite3.connect(sys.argv[1])
conn.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS packages USING fts5(
        id, name, description, tags, content_preview,
        source UNINDEXED, trust UNINDEXED, token_count UNINDEXED,
        cache_path UNINDEXED, type UNINDEXED
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS package_meta (
        id TEXT PRIMARY KEY,
        name TEXT,
        type TEXT,
        trust TEXT,
        token_count INTEGER,
        source TEXT,
        cache_path TEXT,
        fetched_at TEXT,
        last_accessed TEXT,
        access_count INTEGER DEFAULT 0
    )
""")
conn.commit()
conn.close()
PYTHON

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_success "Initialized at $CONTEXT_HOME"
    else
        echo "Initialized context store at $CONTEXT_HOME"
        echo "  Config:      $CONTEXT_HOME/config.yaml"
        echo "  Cache:       $CONTEXT_CACHE_DIR/"
        echo "  Index:       $CONTEXT_INDEX_DB"
        echo "  Annotations: $CONTEXT_HOME/annotations.jsonl"
    fi
}

# Status overview
cmd_status() {
    ensure_init

    local pkg_count cache_size_kb annotations_count feedback_count

    pkg_count=$(python3 -c "
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
try:
    row = conn.execute('SELECT COUNT(*) FROM package_meta').fetchone()
    print(row[0])
except:
    print(0)
conn.close()
" "$CONTEXT_INDEX_DB" 2>/dev/null || echo "0")

    cache_size_kb=$(du -sk "$CONTEXT_CACHE_DIR" 2>/dev/null | cut -f1 || echo "0")
    annotations_count=$(count_lines "$CONTEXT_HOME/annotations.jsonl")
    feedback_count=$(count_lines "$CONTEXT_HOME/feedback.jsonl")

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        snapshot_begin "context"
        snapshot_num_field "packages" "$pkg_count"
        snapshot_num_field "cache_size_kb" "$cache_size_kb"
        snapshot_num_field "annotations" "$annotations_count"
        snapshot_num_field "feedback_ratings" "$feedback_count"
        snapshot_field "home" "$CONTEXT_HOME"
        snapshot_end
    else
        echo "agent-context status"
        echo "  Packages:    $pkg_count indexed"
        echo "  Cache:       ${cache_size_kb}KB"
        echo "  Annotations: $annotations_count"
        echo "  Feedback:    $feedback_count ratings"
        echo "  Home:        $CONTEXT_HOME"
    fi
}
