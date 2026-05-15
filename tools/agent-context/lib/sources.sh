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

SECRET_NAMES = ("token", "key", "secret", "signature", "sig", "password", "passwd", "auth", "credential")

def redact_url(value):
    if not value:
        return value
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
    parsed = urlparse(value)
    if not parsed.scheme:
        return value
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = "[redacted]@" + netloc.rsplit("@", 1)[1]
    query = []
    for key, current in parse_qsl(parsed.query, keep_blank_values=True):
        if any(secret in key.lower() for secret in SECRET_NAMES):
            query.append((key, "[redacted]"))
        else:
            query.append((key, current))
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, urlencode(query), parsed.fragment))

def redact_source(source):
    redacted = dict(source)
    for key in ("location", "url"):
        if key in redacted:
            redacted[key] = redact_url(redacted[key])
    return redacted

if action == "dump":
    print(json.dumps(sources, ensure_ascii=False))
    raise SystemExit(0)

if action == "list":
    redacted_sources = [redact_source(s) for s in sources]
    if output_format == "json":
        print(json.dumps({"success": True, "count": len(redacted_sources), "sources": redacted_sources}, indent=2))
    else:
        if not redacted_sources:
            print("No sources configured.")
            print("Add one: agent-context add-source <name> <url|path>")
        else:
            print(f"{len(redacted_sources)} source(s):\n")
            for s in redacted_sources:
                stype = s.get("kind") or ("local" if s.get("path") else "remote")
                location = s.get("location") or s.get("path") or s.get("url", "?")
                trust = s.get("trust", "community")
                enabled = "enabled" if s.get("enabled", True) else "disabled"
                sync = s.get("last_sync_status", "never")
                last_sync = s.get("last_sync", "")
                suffix = f"  sync={sync}"
                if last_sync:
                    suffix += f" at {last_sync}"
                print(f"  {s.get('name', '?'):20s} [{trust}] {stype} {enabled}: {location}{suffix}")
    raise SystemExit(0)

if action == "add":
    if len(args) < 10:
        raise SystemExit("Usage: add <name> <location> <trust> <kind> <ttl> <tags> <aliases> <enabled> <crawl_limit> <policy> [ecosystem package registry registry_url doc_version version_policy currency_ttl]")
    name, location, trust, kind, ttl, tags, aliases, enabled, crawl_limit, policy = args[:10]
    optional = args[10:]
    ecosystem = optional[0] if len(optional) > 0 else ""
    package_name = optional[1] if len(optional) > 1 else ""
    registry = optional[2] if len(optional) > 2 else ""
    registry_url = optional[3] if len(optional) > 3 else ""
    doc_version = optional[4] if len(optional) > 4 else ""
    version_policy = optional[5] if len(optional) > 5 else ""
    currency_ttl = optional[6] if len(optional) > 6 else ""
    sources = [s for s in sources if s.get("name") != name]
    entry = {
        "name": name,
        "location": location,
        "kind": kind,
        "trust": trust,
        "ttl": ttl,
        "tags": tags,
        "aliases": [item.strip() for item in aliases.split(",") if item.strip()],
        "enabled": enabled == "true",
        "crawl_limit": int(crawl_limit) if crawl_limit else 20,
        "refresh_policy": policy,
    }
    for key, value in {
        "ecosystem": ecosystem,
        "package_name": package_name,
        "registry": registry,
        "registry_url": registry_url,
        "doc_version": doc_version,
        "version_policy": version_policy,
        "currency_ttl": currency_ttl,
    }.items():
        if value:
            entry[key] = value
    if location.startswith(("http://", "https://")):
        entry["url"] = location
    else:
        entry["path"] = location
    sources.append(entry)
    path.write_text(replace_sources(text, sources))
    if output_format == "json":
        print(json.dumps({"success": True, "message": f"Added source: {name}"}, indent=2))
    else:
        print(f"Added source: {name} ({redact_url(location)})")
    raise SystemExit(0)

if action == "sync-update":
    if len(args) != 3:
        raise SystemExit("Usage: sync-update <name> <status> <message>")
    from datetime import datetime, timezone

    name, status, message = args
    for s in sources:
        if s.get("name") == name:
            s["last_sync"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            s["last_sync_status"] = status
            s["last_sync_error"] = message
            break
    path.write_text(replace_sources(text, sources))
    print(json.dumps({"success": True}))
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
    local subcmd="${1:-list}"
    case "$subcmd" in
        list|ls)
            shift 2>/dev/null || true
            _context_sources_run list "$@"
            ;;
        sync)
            shift
            _context_sources_sync "$@"
            ;;
        *)
            _context_sources_run list "$@"
            ;;
    esac
}

cmd_add_source() {
    local name="" location="" trust="community" kind="" ttl="7d" tags="" aliases="" enabled="true" crawl_limit="20" policy="on-use"
    local ecosystem="" package_name="" registry="" registry_url="" doc_version="" version_policy="" currency_ttl=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --trust)
                trust="${2:-}"
                shift 2
                ;;
            --kind)
                kind="${2:-}"
                shift 2
                ;;
            --ttl)
                ttl="${2:-}"
                shift 2
                ;;
            --tags)
                tags="${2:-}"
                shift 2
                ;;
            --alias|--aliases)
                aliases="${aliases:+$aliases,}${2:-}"
                shift 2
                ;;
            --crawl-limit)
                crawl_limit="${2:-200}"
                shift 2
                ;;
            --policy|--refresh-policy)
                policy="${2:-on-use}"
                shift 2
                ;;
            --ecosystem)
                ecosystem="${2:-}"
                shift 2
                ;;
            --package|--package-name)
                package_name="${2:-}"
                shift 2
                ;;
            --registry)
                registry="${2:-}"
                shift 2
                ;;
            --registry-url)
                registry_url="${2:-}"
                shift 2
                ;;
            --doc-version)
                doc_version="${2:-}"
                shift 2
                ;;
            --version-policy)
                version_policy="${2:-}"
                shift 2
                ;;
            --currency-ttl)
                currency_ttl="${2:-}"
                shift 2
                ;;
            --disabled)
                enabled="false"
                shift
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

    [[ -n "$name" && -n "$location" ]] || die "Usage: agent-context add-source <name> <url|path> [--kind url|llms|github-file|github-dir|local-project|local-skill] [--trust official|maintainer|community|local]"
    ensure_init
    [[ -n "$kind" ]] || kind=$(_context_infer_source_kind "$location")
    _context_sources_run add "$name" "$location" "$trust" "$kind" "$ttl" "$tags" "$aliases" "$enabled" "$crawl_limit" "$policy" "$ecosystem" "$package_name" "$registry" "$registry_url" "$doc_version" "$version_policy" "$currency_ttl"
}

cmd_remove_source() {
    local name="${1:-}"
    [[ -n "$name" ]] || die "Usage: agent-context remove-source <name>"
    ensure_init
    _context_sources_run remove "$name"
}

_context_infer_source_kind() {
    python3 - "$1" << 'PYTHON'
import sys

location = sys.argv[1].lower()
if "github.com" in location and "/tree/" in location:
    print("github-dir")
elif "github.com" in location and "/blob/" in location:
    print("github-file")
elif "llms" in location:
    print("llms")
elif location.startswith(("http://", "https://")) and not location.endswith((".md", ".mdx", ".txt")):
    print("html-site")
elif location.startswith(("http://", "https://")):
    print("url")
elif location.endswith("/skill.md") or location.endswith("skill.md"):
    print("local-skill")
else:
    print("local-project")
PYTHON
}

_context_sources_sync() {
    local target="" all=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --all) all=true; shift ;;
            *) target="$1"; shift ;;
        esac
    done

    local sources_json selected_json
    sources_json=$(_context_sources_run dump)
    selected_json=$(python3 - "$sources_json" "$target" "$all" << 'PYTHON'
import json
import sys

sources = json.loads(sys.argv[1])
target = sys.argv[2]
all_flag = sys.argv[3] == "true"
selected = []
for source in sources:
    if target and source.get("name") != target:
        continue
    if not target and not all_flag:
        continue
    selected.append(source)
print(json.dumps(selected))
PYTHON
    )

    local count
    count=$(python3 - "$selected_json" << 'PYTHON'
import json
import sys
print(len(json.loads(sys.argv[1])))
PYTHON
    )
    [[ "$count" -gt 0 ]] || die "No matching sources to sync. Use: agent-context sources sync <name> or --all"

    local synced=0 failed=0 skipped=0
    while IFS= read -r source_json; do
        [[ -n "$source_json" ]] || continue
        local name kind location trust tags enabled crawl_limit
        name=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('name',''))" "$source_json")
        kind=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('kind','url'))" "$source_json")
        location=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('location') or d.get('url') or d.get('path') or '')" "$source_json")
        trust=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('trust','community'))" "$source_json")
        tags=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('tags',''))" "$source_json")
        enabled=$(python3 -c "import json,sys; print('true' if json.loads(sys.argv[1]).get('enabled', True) else 'false')" "$source_json")
        crawl_limit=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('crawl_limit',20))" "$source_json")

        if [[ "$enabled" != "true" ]]; then
            skipped=$((skipped + 1))
            continue
        fi

        if _context_sync_one_source "$kind" "$location" "$tags" "$trust" "$name" "$crawl_limit"; then
            synced=$((synced + 1))
            _context_sources_run sync-update "$name" ok "" >/dev/null
        else
            failed=$((failed + 1))
            _context_sources_run sync-update "$name" failed "sync failed" >/dev/null
        fi
    done < <(python3 - "$selected_json" << 'PYTHON'
import json
import sys
for source in json.loads(sys.argv[1]):
    print(json.dumps(source))
PYTHON
    )

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        python3 - "$synced" "$failed" "$skipped" << 'PYTHON'
import json
import sys
synced, failed, skipped = [int(item) for item in sys.argv[1:4]]
print(json.dumps({
    "success": failed == 0,
    "synced": synced,
    "failed": failed,
    "skipped": skipped,
}, indent=2))
PYTHON
    else
        echo "Sources sync: $synced synced, $failed failed, $skipped skipped."
    fi
    [[ "$failed" -eq 0 ]]
}

_context_sync_one_source() {
    local kind="$1" location="$2" tags="$3" trust="$4" name="${5:-}" crawl_limit="${6:-20}"
    case "$kind" in
        html|html-page)
            cmd_fetch "$location" --tags "$tags" --trust "$trust" --source-name "$name" >/dev/null
            ;;
        html-site|html-crawl)
            cmd_crawl "$location" --source-name "$name" --tags "$tags" --trust "$trust" --limit "$crawl_limit" >/dev/null
            ;;
        llms)
            cmd_fetch_llms "$location" --tags "$tags" --trust "$trust" >/dev/null
            ;;
        github-file|github-dir)
            local repo path
            read -r repo path < <(_context_parse_github_source "$location")
            [[ -n "$repo" ]] || return 1
            if [[ -n "$path" ]]; then
                cmd_fetch_repo "$repo" "$path" --tags "$tags" --trust "$trust" >/dev/null
            else
                cmd_fetch_repo "$repo" --tags "$tags" --trust "$trust" >/dev/null
            fi
            ;;
        local-skill)
            local skill_name
            skill_name=$(basename "$(dirname "$location")")
            [[ "$(basename "$location")" == "SKILL.md" ]] || skill_name=$(basename "$location")
            cmd_scan_skills "$skill_name" >/dev/null
            ;;
        local-project)
            cmd_scan_local "$location" >/dev/null
            ;;
        url|*)
            if [[ "$location" == http* ]] && type cmd_crawl &>/dev/null; then
                cmd_crawl "$location" --source-name "$name" --tags "$tags" --trust "$trust" --limit "$crawl_limit" >/dev/null 2>&1 || \
                    cmd_fetch "$location" --tags "$tags" --trust "$trust" --source-name "$name" >/dev/null
            else
                cmd_fetch "$location" --tags "$tags" --trust "$trust" --source-name "$name" >/dev/null
            fi
            ;;
    esac
}

_context_parse_github_source() {
    python3 - "$1" << 'PYTHON'
import sys
from urllib.parse import urlparse

location = sys.argv[1]
if "/" in location and not location.startswith(("http://", "https://")):
    parts = location.split("/", 2)
    repo = "/".join(parts[:2])
    path = parts[2] if len(parts) > 2 else ""
    print(repo, path)
    raise SystemExit(0)

parsed = urlparse(location)
parts = [part for part in parsed.path.split("/") if part]
repo = "/".join(parts[:2]) if len(parts) >= 2 else ""
path = ""
if len(parts) >= 5 and parts[2] in {"blob", "tree"}:
    path = "/".join(parts[4:])
print(repo, path)
PYTHON
}
