#!/usr/bin/env bash
# lib/maintenance.sh — Bounded maintenance for agent-context
# Sourced by agent-context entry point. Do not run directly.

cmd_maintain() {
    local limit="10" max_mb="" subcmd=""
    if [[ "${1:-}" == "schedule" ]]; then
        shift
        _context_maintain_schedule "$@"
        return
    fi

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --limit) limit="$2"; shift 2 ;;
            --max-mb) max_mb="$2"; shift 2 ;;
            *) subcmd="$1"; shift ;;
        esac
    done
    [[ -z "$subcmd" ]] || die "Usage: agent-context maintain [--limit N] [--max-mb N]"

    ensure_init
    [[ -n "$max_mb" ]] || max_mb=$(_context_default_cache_max_mb)

    local refresh_output refresh_rc versions_output versions_rc pruned_json counts_json
    if refresh_output=$(cmd_refresh --due --limit "$limit" 2>&1); then
        refresh_rc=0
    else
        refresh_rc=$?
    fi
    if type _context_versions_check &>/dev/null; then
        if versions_output=$(_context_versions_check --due --limit "$limit" --quiet 2>&1); then
            versions_rc=0
        else
            versions_rc=$?
        fi
    else
        versions_output=""
        versions_rc=0
    fi
    pruned_json=$(_context_prune_cache "$max_mb")
    counts_json=$(_context_maintenance_counts)

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        python3 - "$refresh_rc" "$refresh_output" "$versions_rc" "$versions_output" "$pruned_json" "$counts_json" << 'PYTHON'
import json
import sys

refresh_rc = int(sys.argv[1])
refresh_output = sys.argv[2]
versions_rc = int(sys.argv[3])
versions_output = sys.argv[4]
pruned = json.loads(sys.argv[5])
counts = json.loads(sys.argv[6])
print(json.dumps({
    "success": refresh_rc == 0 and versions_rc == 0,
    "refresh_success": refresh_rc == 0,
    "refresh_output": refresh_output,
    "versions_success": versions_rc == 0,
    "versions_output": versions_output,
    "pruned": pruned,
    "freshness": counts,
}, indent=2))
PYTHON
    else
        echo "agent-context maintenance"
        echo "$refresh_output"
        if [[ -n "$versions_output" ]]; then
            echo "$versions_output"
        elif [[ "$versions_rc" -eq 0 ]]; then
            echo "Version check: due packages checked."
        fi
        python3 - "$pruned_json" "$counts_json" << 'PYTHON'
import json
import sys

pruned = json.loads(sys.argv[1])
counts = json.loads(sys.argv[2])
print(f"Prune: {pruned['removed_count']} removed, {pruned['bytes_removed'] // 1024}KB reclaimed, {pruned['cache_mb']}MB current / {pruned['max_mb']}MB max")
print(
    "Freshness: "
    f"{counts.get('fresh', 0)} fresh, {counts.get('stale', 0)} stale, "
    f"{counts.get('failed', 0)} failed, {counts.get('local', 0)} local, "
    f"{counts.get('unknown', 0)} unknown"
)
PYTHON
    fi

    [[ "$refresh_rc" -eq 0 && "$versions_rc" -eq 0 ]]
}

_context_default_cache_max_mb() {
    python3 - "$CONTEXT_HOME/config.yaml" << 'PYTHON'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text() if Path(sys.argv[1]).exists() else ""
match = re.search(r"^\s*cache_max_mb:\s*(\d+)\s*$", text, re.M)
print(match.group(1) if match else "500")
PYTHON
}

_context_maintenance_counts() {
    python3 - "$CONTEXT_INDEX_DB" << 'PYTHON'
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA busy_timeout = 5000")
now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
counts = Counter()
for status, expires_at in conn.execute("SELECT COALESCE(refresh_status, 'unknown'), expires_at FROM package_meta"):
    resolved = status or "unknown"
    if resolved not in {"local", "failed"} and expires_at and expires_at < now:
        resolved = "stale"
    counts[resolved] += 1
conn.close()
print(json.dumps({key: counts.get(key, 0) for key in ["fresh", "stale", "failed", "local", "unknown"]}))
PYTHON
}

_context_prune_cache() {
    local max_mb="$1"
    python3 - "$CONTEXT_INDEX_DB" "$CONTEXT_CACHE_DIR" "$max_mb" << 'PYTHON'
import json
import os
import shutil
import sqlite3
import sys

db_path, cache_dir, max_mb = sys.argv[1:4]
max_bytes = int(max_mb) * 1024 * 1024
pins_path = os.path.join(cache_dir, "_pins.json")
pins = set()
if os.path.exists(pins_path):
    try:
        with open(pins_path, encoding="utf-8") as handle:
            pins = set(json.load(handle))
    except (OSError, json.JSONDecodeError):
        pins = set()

conn = sqlite3.connect(db_path)
conn.execute("PRAGMA busy_timeout = 5000")
rows = conn.execute(
    """
    SELECT id, cache_path, COALESCE(last_accessed, ''), COALESCE(access_count, 0)
    FROM package_meta
    ORDER BY access_count ASC, last_accessed ASC
    """
).fetchall()

def dir_size(path):
    total = 0
    if not path or not os.path.isdir(path):
        return 0
    for dirpath, _, filenames in os.walk(path):
        for filename in filenames:
            fp = os.path.join(dirpath, filename)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total

entries = []
total = 0
for package_id, cache_path, last_accessed, access_count in rows:
    size = dir_size(cache_path)
    total += size
    entries.append({
        "id": package_id,
        "cache_path": cache_path,
        "size": size,
        "pinned": package_id in pins,
        "last_accessed": last_accessed,
        "access_count": int(access_count or 0),
    })

removed = []
bytes_removed = 0
if total > max_bytes:
    for entry in entries:
        if total <= max_bytes:
            break
        if entry["pinned"] or not entry["cache_path"]:
            continue
        cache_path = entry["cache_path"]
        if os.path.isdir(cache_path):
            shutil.rmtree(cache_path)
        conn.execute("DELETE FROM packages WHERE id = ?", (entry["id"],))
        conn.execute("DELETE FROM package_meta WHERE id = ?", (entry["id"],))
        conn.execute("DELETE FROM package_files WHERE package_id = ?", (entry["id"],))
        conn.execute("DELETE FROM package_currency WHERE package_id = ?", (entry["id"],))
        total -= entry["size"]
        bytes_removed += entry["size"]
        removed.append(entry["id"])

conn.commit()
conn.close()
print(json.dumps({
    "removed_count": len(removed),
    "removed_ids": removed,
    "bytes_removed": bytes_removed,
    "cache_mb": round(total / 1048576, 2),
    "max_mb": int(max_mb),
}))
PYTHON
}

_context_maintain_schedule() {
    local action="${1:-print}" interval="3600" limit="10" max_mb=""
    shift 2>/dev/null || true
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --interval) interval="$2"; shift 2 ;;
            --limit) limit="$2"; shift 2 ;;
            --max-mb) max_mb="$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    local plist_path="$HOME/Library/LaunchAgents/com.agent-do.context-maintain.plist"
    case "$action" in
        print)
            _context_maintain_plist "$interval" "$limit" "$max_mb"
            ;;
        install)
            mkdir -p "$(dirname "$plist_path")"
            _context_maintain_plist "$interval" "$limit" "$max_mb" > "$plist_path"
            launchctl unload "$plist_path" >/dev/null 2>&1 || true
            launchctl load -w "$plist_path"
            echo "Installed context maintenance schedule: $plist_path"
            ;;
        uninstall)
            launchctl unload "$plist_path" >/dev/null 2>&1 || true
            rm -f "$plist_path"
            echo "Removed context maintenance schedule: $plist_path"
            ;;
        status)
            if [[ -f "$plist_path" ]]; then
                echo "Installed: $plist_path"
            else
                echo "Not installed."
            fi
            ;;
        *)
            die "Usage: agent-context maintain schedule [print|install|uninstall|status] [--interval seconds] [--limit N] [--max-mb N]"
            ;;
    esac
}

_context_maintain_plist() {
    local interval="$1" limit="$2" max_mb="$3"
    local agent_do
    agent_do=$(command -v agent-do 2>/dev/null || true)
    [[ -n "$agent_do" ]] || agent_do="$(cd "$SCRIPT_DIR/../.." && pwd)/agent-do"
    python3 - "$agent_do" "$interval" "$limit" "$max_mb" << 'PYTHON'
import plistlib
import sys

agent_do, interval, limit, max_mb = sys.argv[1:5]
args = [agent_do, "context", "maintain", "--limit", limit]
if max_mb:
    args.extend(["--max-mb", max_mb])
plist = {
    "Label": "com.agent-do.context-maintain",
    "ProgramArguments": args,
    "StartInterval": int(interval),
    "RunAtLoad": False,
    "StandardOutPath": "/tmp/agent-do-context-maintain.out.log",
    "StandardErrorPath": "/tmp/agent-do-context-maintain.err.log",
}
sys.stdout.buffer.write(plistlib.dumps(plist, sort_keys=False))
PYTHON
}
