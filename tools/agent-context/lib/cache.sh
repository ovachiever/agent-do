#!/usr/bin/env bash
# lib/cache.sh — Cache management for agent-context
# Sourced by agent-context entry point. Do not run directly.

cmd_cache() {
    local subcmd="${1:-list}"
    shift 2>/dev/null || true

    case "$subcmd" in
        list|ls)
            _cache_list "$@"
            ;;
        clear|clean)
            _cache_clear "$@"
            ;;
        pin)
            _cache_pin "$@"
            ;;
        stats)
            _cache_stats "$@"
            ;;
        *)
            echo "Usage: agent-context cache [list|clear|pin|stats]" >&2
            exit 1
            ;;
    esac
}

_cache_list() {
    ensure_init

    python3 - "$CONTEXT_CACHE_DIR" "$CONTEXT_INDEX_DB" "${OUTPUT_FORMAT:-text}" << 'PYTHON'
import os, sys, json, sqlite3

cache_dir, db_path, output_format = sys.argv[1:4]

conn = sqlite3.connect(db_path)
rows = conn.execute(
    "SELECT id, name, type, trust, token_count, cache_path, fetched_at, last_accessed, access_count "
    "FROM package_meta ORDER BY last_accessed DESC"
).fetchall()

# Load pins
pins_path = os.path.join(cache_dir, "_pins.json")
pins = set()
if os.path.exists(pins_path):
    with open(pins_path) as f:
        pins = set(json.load(f))

entries = []
for row in rows:
    pkg_id, name, ptype, trust, tokens, cache_path, fetched, accessed, count = row

    # Calculate disk size
    size_bytes = 0
    if cache_path and os.path.isdir(cache_path):
        for dirpath, _, filenames in os.walk(cache_path):
            for fname in filenames:
                fp = os.path.join(dirpath, fname)
                if os.path.isfile(fp):
                    size_bytes += os.path.getsize(fp)

    entries.append({
        "id": pkg_id,
        "name": name,
        "type": ptype,
        "trust": trust,
        "token_count": int(tokens) if tokens else 0,
        "size_bytes": size_bytes,
        "fetched_at": fetched,
        "last_accessed": accessed,
        "access_count": int(count) if count else 0,
        "pinned": pkg_id in pins,
    })

total_size = sum(e["size_bytes"] for e in entries)

if output_format == "json":
    print(json.dumps({
        "success": True,
        "count": len(entries),
        "total_size_bytes": total_size,
        "entries": entries
    }, indent=2))
else:
    if not entries:
        print("Cache is empty.")
    else:
        print(f"Cached packages ({len(entries)}, {total_size // 1024}KB total):\n")
        for e in entries:
            pin_mark = " [pinned]" if e["pinned"] else ""
            size_kb = e["size_bytes"] // 1024 or 1
            print(f"  {e['name']:30s} {size_kb:>5d}KB  ~{e['token_count']} tokens  ({e['access_count']} hits){pin_mark}")

conn.close()
PYTHON
}

_cache_clear() {
    local target="${1:-}"
    ensure_init

    if [[ -n "$target" ]]; then
        # Clear specific package
        local cache_path
        cache_path=$(python3 -c "
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
row = conn.execute('SELECT cache_path FROM package_meta WHERE id = ? OR name = ?', (sys.argv[2], sys.argv[2])).fetchone()
print(row[0] if row else '')
conn.close()
" "$CONTEXT_INDEX_DB" "$target")

        if [[ -z "$cache_path" || ! -d "$cache_path" ]]; then
            if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
                json_error "Package not found: $target"
            else
                die "Package not found: $target"
            fi
            return 1
        fi

        rm -rf "$cache_path"

        # Remove from index
        python3 -c "
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
pkg_id = sys.argv[2]
conn.execute('DELETE FROM packages WHERE id = ?', (pkg_id,))
conn.execute('DELETE FROM package_meta WHERE id = ?', (pkg_id,))
conn.commit()
conn.close()
" "$CONTEXT_INDEX_DB" "$target"

        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_success "Cleared: $target"
        else
            echo "Cleared: $target"
        fi
    else
        # Clear all
        rm -rf "$CONTEXT_CACHE_DIR"
        mkdir -p "$CONTEXT_CACHE_DIR"

        # Rebuild empty index
        python3 -c "
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute('DELETE FROM packages')
conn.execute('DELETE FROM package_meta')
conn.commit()
conn.close()
" "$CONTEXT_INDEX_DB"

        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_success "Cache cleared"
        else
            echo "Cache cleared."
        fi
    fi
}

_cache_pin() {
    local pkg_id="${1:-}"
    [[ -n "$pkg_id" ]] || die "Usage: agent-context cache pin <id>"
    ensure_init

    local pins_file="$CONTEXT_CACHE_DIR/_pins.json"

    python3 - "$pins_file" "$pkg_id" << 'PYTHON'
import json, sys, os

pins_path, pkg_id = sys.argv[1:3]

pins = []
if os.path.exists(pins_path):
    with open(pins_path) as f:
        pins = json.load(f)

if pkg_id not in pins:
    pins.append(pkg_id)

with open(pins_path, "w") as f:
    json.dump(pins, f, indent=2)
PYTHON

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_success "Pinned: $pkg_id"
    else
        echo "Pinned: $pkg_id (will not be evicted)"
    fi
}

_cache_stats() {
    ensure_init

    python3 - "$CONTEXT_CACHE_DIR" "$CONTEXT_INDEX_DB" "${OUTPUT_FORMAT:-text}" << 'PYTHON'
import os, sys, json, sqlite3

cache_dir, db_path, output_format = sys.argv[1:4]

conn = sqlite3.connect(db_path)

total = conn.execute("SELECT COUNT(*) FROM package_meta").fetchone()[0]
total_tokens = conn.execute("SELECT COALESCE(SUM(token_count), 0) FROM package_meta").fetchone()[0]
total_hits = conn.execute("SELECT COALESCE(SUM(access_count), 0) FROM package_meta").fetchone()[0]

# Type breakdown
types = {}
for row in conn.execute("SELECT type, COUNT(*), SUM(token_count) FROM package_meta GROUP BY type"):
    types[row[0]] = {"count": row[1], "tokens": int(row[2]) if row[2] else 0}

# Trust breakdown
trusts = {}
for row in conn.execute("SELECT trust, COUNT(*) FROM package_meta GROUP BY trust"):
    trusts[row[0]] = row[1]

# Disk usage
total_bytes = 0
for dirpath, _, filenames in os.walk(cache_dir):
    for fname in filenames:
        fp = os.path.join(dirpath, fname)
        if os.path.isfile(fp):
            total_bytes += os.path.getsize(fp)

# Pins
pins_path = os.path.join(cache_dir, "_pins.json")
pin_count = 0
if os.path.exists(pins_path):
    with open(pins_path) as f:
        pin_count = len(json.load(f))

stats = {
    "packages": total,
    "total_tokens": int(total_tokens),
    "total_hits": int(total_hits),
    "disk_bytes": total_bytes,
    "disk_mb": round(total_bytes / 1048576, 1),
    "pinned": pin_count,
    "by_type": types,
    "by_trust": trusts,
}

if output_format == "json":
    print(json.dumps({"success": True, "stats": stats}, indent=2))
else:
    print(f"Cache Statistics:")
    print(f"  Packages:     {total}")
    print(f"  Total tokens: ~{int(total_tokens)}")
    print(f"  Total hits:   {int(total_hits)}")
    print(f"  Disk usage:   {round(total_bytes / 1048576, 1)}MB")
    print(f"  Pinned:       {pin_count}")
    if types:
        print(f"\n  By type:")
        for t, info in types.items():
            print(f"    {t}: {info['count']} (~{info['tokens']} tokens)")
    if trusts:
        print(f"\n  By trust:")
        for t, count in trusts.items():
            print(f"    {t}: {count}")

conn.close()
PYTHON
}
