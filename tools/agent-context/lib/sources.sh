#!/usr/bin/env bash
# lib/sources.sh — Source management for agent-context
# Sourced by agent-context entry point. Do not run directly.

cmd_sources() {
    ensure_init

    python3 - "$CONTEXT_HOME/config.yaml" "${OUTPUT_FORMAT:-text}" << 'PYTHON'
import sys, json

config_path, output_format = sys.argv[1:3]

try:
    import yaml
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}
except ImportError:
    # Minimal YAML parse
    config = {"sources": []}

sources = config.get("sources", [])

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
PYTHON
}

cmd_add_source() {
    local name="" location=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --trust) local trust="$2"; shift 2 ;;
            *)
                if [[ -z "$name" ]]; then name="$1"
                elif [[ -z "$location" ]]; then location="$1"
                fi
                shift
                ;;
        esac
    done

    [[ -n "$name" && -n "$location" ]] || die "Usage: agent-context add-source <name> <url|path> [--trust official|maintainer|community]"
    ensure_init

    local trust_val="${trust:-community}"

    python3 - "$CONTEXT_HOME/config.yaml" "$name" "$location" "$trust_val" << 'PYTHON'
import sys, json

config_path, name, location, trust = sys.argv[1:5]

try:
    import yaml
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}
except ImportError:
    config = {"sources": []}

sources = config.get("sources", [])

# Remove existing with same name
sources = [s for s in sources if s.get("name") != name]

# Determine type
entry = {"name": name, "trust": trust}
if location.startswith("http://") or location.startswith("https://"):
    entry["url"] = location
else:
    entry["path"] = location

sources.append(entry)
config["sources"] = sources

try:
    import yaml
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
except ImportError:
    # Minimal write
    with open(config_path, "w") as f:
        f.write(f"sources:\n")
        for s in sources:
            f.write(f"  - name: {s['name']}\n")
            for k, v in s.items():
                if k != "name":
                    f.write(f"    {k}: {v}\n")
PYTHON

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_success "Added source: $name"
    else
        echo "Added source: $name ($location)"
    fi
}

cmd_remove_source() {
    local name="${1:-}"
    [[ -n "$name" ]] || die "Usage: agent-context remove-source <name>"
    ensure_init

    python3 - "$CONTEXT_HOME/config.yaml" "$name" << 'PYTHON'
import sys

config_path, name = sys.argv[1:3]

try:
    import yaml
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}
    sources = config.get("sources", [])
    config["sources"] = [s for s in sources if s.get("name") != name]
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
except ImportError:
    pass
PYTHON

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_success "Removed source: $name"
    else
        echo "Removed source: $name"
    fi
}
