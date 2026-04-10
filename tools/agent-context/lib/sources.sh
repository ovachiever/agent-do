#!/usr/bin/env bash
# lib/sources.sh — Source management for agent-context
# Sourced by agent-context entry point. Do not run directly.

_context_sources_run() {
    local action="$1"
    shift

    python3 - "$action" "$CONTEXT_HOME/config.yaml" "${OUTPUT_FORMAT:-text}" "$@" << 'PYTHON'
import json
import re
import sys
from pathlib import Path

action, config_path, output_format, *args = sys.argv[1:]
path = Path(config_path)
text = path.read_text() if path.exists() else ""


def format_scalar(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(format_scalar(item) for item in value) + "]"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)

    s = str(value)
    if s == "":
        return '""'
    if re.search(r"[:#\n\r\t]|^\s|\s$", s) or s in {"[]", "{}", "null", "true", "false"}:
        return json.dumps(s, ensure_ascii=False)
    return s


def parse_scalar(raw):
    raw = raw.strip()
    if raw == "[]":
        return []
    if raw == "{}":
        return {}
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
        return [parse_scalar(part.strip()) for part in inner.split(",")]
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    if re.fullmatch(r"-?\d+", raw):
        try:
            return int(raw)
        except ValueError:
            pass
    if re.fullmatch(r"-?\d+\.\d+", raw):
        try:
            return float(raw)
        except ValueError:
            pass
    return raw


def find_sources_block(lines):
    start = None
    end = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if line.startswith("sources:"):
            start = i
            if stripped == "sources: []" or stripped == "sources:":
                if stripped.endswith("[]"):
                    end = i
                else:
                    j = i + 1
                    while j < len(lines):
                        nxt = lines[j]
                        nxt_stripped = nxt.strip()
                        if not nxt_stripped:
                            j += 1
                            continue
                        if not nxt.startswith((" ", "\t")) and not nxt.startswith("#"):
                            break
                        j += 1
                    end = j - 1
            else:
                end = i
            break
    return start, end


def parse_sources(text):
    lines = text.splitlines(True)
    start, end = find_sources_block(lines)
    if start is None:
        return []
    if end == start:
        return []

    sources = []
    current = None
    for line in lines[start + 1 : end + 1]:
        if not line.strip():
            continue
        if line.startswith("  - "):
            m = re.match(r"^  -\s+name:\s*(.*)$", line)
            current = {"name": parse_scalar(m.group(1)) if m else ""}
            sources.append(current)
            continue
        if current is None:
            continue
        m = re.match(r"^    ([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            key = m.group(1)
            value = parse_scalar(m.group(2))
            current[key] = value
    return sources


def render_sources_block(sources):
    if not sources:
        return "sources: []\n"

    out = ["sources:\n"]
    for source in sources:
        out.append(f"  - name: {format_scalar(source.get('name', ''))}\n")
        for key, value in source.items():
            if key == "name":
                continue
            out.append(f"    {key}: {format_scalar(value)}\n")
    return "".join(out)


def replace_sources(text, sources):
    lines = text.splitlines(True)
    start, end = find_sources_block(lines)
    block = render_sources_block(sources)

    if start is None:
        if text and not text.endswith("\n"):
            text += "\n"
        return text + block

    if end is None:
        end = start

    prefix = "".join(lines[:start])
    suffix = "".join(lines[end + 1 :])
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    return prefix + block + suffix


sources = parse_sources(text)

if action == "list":
    if output_format == "json":
        print(json.dumps({"success": True, "count": len(sources), "sources": sources}, indent=2))
    else:
        if not sources:
            print("No sources configured.")
            print("Add one: agent-context add-source <name> <url|path>")
        else:
            print(f"{len(sources)} source(s):\n")
            for s in sources:
                stype = "local" if s.get("path") else "remote"
                location = s.get("path") or s.get("url", "?")
                trust = s.get("trust", "community")
                print(f"  {s.get('name', '?'):20s} [{trust}] {stype}: {location}")
    raise SystemExit(0)

if action == "add":
    if len(args) != 3:
        raise SystemExit("Usage: add <name> <location> <trust>")
    name, location, trust = args
    sources = [s for s in sources if s.get("name") != name]
    entry = {"name": name, "trust": trust}
    if location.startswith(("http://", "https://")):
        entry["url"] = location
    else:
        entry["path"] = location
    sources.append(entry)
    path.write_text(replace_sources(text, sources))
    if output_format == "json":
        print(json.dumps({"success": True, "message": f"Added source: {name}"}, indent=2))
    else:
        print(f"Added source: {name} ({location})")
    raise SystemExit(0)

if action == "remove":
    if len(args) != 1:
        raise SystemExit("Usage: remove <name>")
    name = args[0]
    sources = [s for s in sources if s.get("name") != name]
    path.write_text(replace_sources(text, sources))
    if output_format == "json":
        print(json.dumps({"success": True, "message": f"Removed source: {name}"}, indent=2))
    else:
        print(f"Removed source: {name}")
    raise SystemExit(0)

raise SystemExit(f"Unknown action: {action}")
PYTHON
}

cmd_sources() {
    ensure_init
    _context_sources_run list
}

cmd_add_source() {
    local name="" location="" trust="community"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --trust)
                trust="${2:-}"
                shift 2
                ;;
            *)
                if [[ -z "$name" ]]; then
                    name="$1"
                elif [[ -z "$location" ]]; then
                    location="$1"
                fi
                shift
                ;;
        esac
    done

    [[ -n "$name" && -n "$location" ]] || die "Usage: agent-context add-source <name> <url|path> [--trust official|maintainer|community]"
    ensure_init
    _context_sources_run add "$name" "$location" "$trust"
}

cmd_remove_source() {
    local name="${1:-}"
    [[ -n "$name" ]] || die "Usage: agent-context remove-source <name>"
    ensure_init
    _context_sources_run remove "$name"
}
