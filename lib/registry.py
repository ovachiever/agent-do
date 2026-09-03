"""Registry loading for agent-do."""

import os
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))
CONTRACT_BEATS = ("connect", "snapshot", "interact", "verify", "save")
# Orthogonal verb attributes. The beats stay five; shapes the beats cannot
# express are declared as attributes instead of new beats:
#   destructive  — irreversible data loss; needs confirm/backup before the audit trusts it
#   long_running — daemon/stream/session verb; exempt from atomicity, may never return
#   polymorphic  — beat decided by payload/flag at call time (sql, query, shell-style)
#   composite    — one call performs several beats internally (ensure, dns-add, emit)
#   sensitive    — emits or persists secret material; audit treats as a guarded class
#   passthrough  — arbitrary-code escape hatch (shell/eval/run); statically unclassifiable
#   own_state    — writes confined to the tool's own cache/state/derived output;
#                  parallel-safe relative to other tools
CONTRACT_ATTRIBUTES = (
    "destructive",
    "long_running",
    "polymorphic",
    "composite",
    "sensitive",
    "passthrough",
    "own_state",
)
# Attributes that legitimately stand alone, without beat membership.
_BEATLESS_ATTRIBUTES = {"passthrough", "long_running"}


def _load_yaml_data(path: Path) -> dict:
    """Load YAML data, falling back to Ruby's stdlib YAML when PyYAML is unavailable."""
    if yaml is not None:
        with open(path) as f:
            return yaml.safe_load(f) or {}

    ruby = subprocess.run(
        [
            "ruby",
            "-e",
            'require "yaml"; require "json"; print JSON.generate(YAML.load_file(ARGV[0]) || {})',
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if ruby.returncode != 0:
        raise RuntimeError(
            f"Could not parse YAML without PyYAML. Ruby fallback failed: {ruby.stderr.strip()}"
        )
    return json.loads(ruby.stdout or "{}")


def get_registry_paths() -> list[Path]:
    """Get list of registry paths to check."""
    paths = []

    # User registry (highest priority)
    user_registry = AGENT_DO_HOME / "registry.yaml"
    if user_registry.exists():
        paths.append(user_registry)

    # Bundled registry
    bundled = Path(__file__).parent.parent / "registry.yaml"
    if bundled.exists():
        paths.append(bundled)

    # Plugin registries
    plugins_dir = AGENT_DO_HOME / "plugins"
    if plugins_dir.exists():
        for plugin_file in plugins_dir.glob("*.yaml"):
            paths.append(plugin_file)

    return paths


def load_registry() -> dict:
    """Load tool registry from all sources."""
    registry = {'tools': {}}

    paths = get_registry_paths()

    # Load in reverse order so higher priority overwrites
    for path in reversed(paths):
        try:
            data = _load_yaml_data(path)
            if 'tools' in data:
                registry['tools'].update(data['tools'])
        except Exception as e:
            print(f"Warning: Could not load registry from {path}: {e}")

    return registry


def build_registry_context(registry: dict) -> str:
    """Build compact tool summary for LLM context."""
    # This is prompt context, not a complete reference document.  Keep the
    # executable surface and safety markers for every tool, then retain up to
    # two examples per tool only while they fit the context budget.  Otherwise
    # a perfectly valid registry addition can make the contracts gate fail.
    max_context_chars = 39_000
    lines = []
    for tool, info in sorted(registry.get('tools', {}).items()):
        lines.append(f"## {tool}")
        lines.append(f"{info.get('description', 'No description')}")

        commands = info.get('commands', {})
        if commands:
            cmd_list = ', '.join(commands.keys())
            lines.append(f"Commands: {cmd_list}")

        # Compact safety line from contracts: writes and the flags that
        # change agent behavior. Read verbs are the default and stay implicit.
        contracts = get_tool_contracts(info)
        attributes = get_tool_contract_attributes(info)
        write_verbs = sorted({
            verb
            for beat in ("connect", "interact", "save")
            for verb in contracts.get(beat, [])
        })
        parts = []
        if write_verbs:
            joined = ",".join(write_verbs)
            parts.append(
                f"writes=[{joined}]" if len(joined) <= 90
                else f"writes={len(write_verbs)} verbs"
            )
        for attr in ("destructive", "sensitive", "passthrough"):
            flagged = sorted(v for v, attrs in attributes.items() if attr in attrs)
            if flagged:
                parts.append(f"{attr}=[{','.join(flagged)}]")
        if contracts:
            lines.append("Safety: " + (" ".join(parts) if parts else "read-only"))

        examples = info.get('examples', [])
        if examples:
            example_lines = ["Examples:"]
            for ex in examples[:2]:
                example_lines.append(f"  \"{ex.get('intent', '')}\" → `{ex.get('command', '')}`")
            # Account for the separating newline added by join() as well as
            # this tool's trailing blank line.
            prospective = "\n".join([*lines, *example_lines, ""])
            if len(prospective) <= max_context_chars:
                lines.extend(example_lines)

        lines.append("")

    return "\n".join(lines)


def get_tool_info(registry: dict, tool_name: str) -> Optional[dict]:
    """Get info for a specific tool."""
    return registry.get('tools', {}).get(tool_name)


def has_tool(registry: dict, tool_name: str) -> bool:
    """Return whether a tool name is declared in the registry."""
    return tool_name in registry.get('tools', {})


def list_tools(registry: dict) -> list[str]:
    """List all available tools."""
    return sorted(registry.get('tools', {}).keys())


def get_tool_routing(info: dict) -> dict:
    """Return routing/discovery metadata for a tool."""
    return info.get('routing') or {}


def get_tool_readiness(info: dict) -> dict:
    """Return readiness metadata for a tool."""
    return get_tool_routing(info).get('readiness') or {}


def get_tool_credentials(info: dict) -> dict:
    """Return credential metadata for a tool."""
    credentials = info.get('credentials') or {}
    result = {
        'required': [item for item in credentials.get('required', []) if item],
        'optional': [item for item in credentials.get('optional', []) if item],
        'one_of': [
            [entry for entry in group if entry]
            for group in credentials.get('one_of', [])
            if group
        ],
    }
    features = credentials.get('features')
    if isinstance(features, dict):
        result['features'] = features
    notes = credentials.get('notes')
    if isinstance(notes, list):
        result['notes'] = [str(note) for note in notes if str(note).strip()]
    return result


def get_tool_secret_envs(info: dict) -> list[str]:
    """Return all environment-variable names a tool may resolve from secure storage."""
    credentials = get_tool_credentials(info)
    envs: list[str] = []
    for key in credentials.get('required', []):
        if key not in envs:
            envs.append(key)
    for key in credentials.get('optional', []):
        if key not in envs:
            envs.append(key)
    for group in credentials.get('one_of', []):
        for key in group:
            if key not in envs:
                envs.append(key)
    return envs


def get_tool_contracts(info: dict) -> dict:
    """Return normalized contract beat declarations for a tool."""
    contracts = info.get("contracts") or {}
    if not isinstance(contracts, dict):
        return {}
    normalized = {}
    for beat, verbs in contracts.items():
        if beat == "attributes":
            continue
        if isinstance(verbs, list):
            normalized[str(beat)] = [str(verb) for verb in verbs if str(verb).strip()]
        elif verbs:
            normalized[str(beat)] = [str(verbs)]
        else:
            normalized[str(beat)] = []
    return normalized


def get_tool_contract_attributes(info: dict) -> dict:
    """Return normalized verb→attribute declarations from a contracts block."""
    contracts = info.get("contracts") or {}
    if not isinstance(contracts, dict):
        return {}
    raw = contracts.get("attributes") or {}
    if not isinstance(raw, dict):
        return {}
    normalized = {}
    for verb, attrs in raw.items():
        if isinstance(attrs, list):
            normalized[str(verb)] = [str(attr) for attr in attrs if str(attr).strip()]
        elif attrs:
            normalized[str(verb)] = [str(attrs)]
        else:
            normalized[str(verb)] = []
    return normalized


def _contract_command_exists(verb: str, commands: dict) -> bool:
    if not commands:
        return True
    if verb in commands:
        return True
    return verb.split()[0] in commands


def validate_tool_contracts(tool_name: str, info: dict) -> dict:
    """Validate one tool's contract declaration against registry commands.

    This is intentionally registry-shape validation, not live behavior grading.
    Live checks belong in the contract audit once declarations exist.
    """
    contracts_raw = info.get("contracts")
    commands = info.get("commands") or {}
    result = {
        "tool": tool_name,
        "declared": isinstance(contracts_raw, dict),
        "beats": {},
        "errors": [],
        "warnings": [],
    }
    if not isinstance(contracts_raw, dict):
        result["warnings"].append({
            "code": "missing_contracts",
            "message": "tool has no contracts block",
        })
        result["ok"] = True
        return result

    seen: dict[str, list[str]] = {}
    contracts = get_tool_contracts(info)
    for beat, verbs in contracts.items():
        if beat not in CONTRACT_BEATS:
            result["errors"].append({
                "code": "unknown_beat",
                "beat": beat,
                "message": f"unknown contract beat: {beat}",
            })
            continue
        result["beats"][beat] = verbs
        for verb in verbs:
            seen.setdefault(verb, []).append(beat)
            if not _contract_command_exists(verb, commands):
                result["errors"].append({
                    "code": "unknown_command",
                    "beat": beat,
                    "verb": verb,
                    "message": f"contract verb does not match declared commands: {verb}",
                })

    attributes = get_tool_contract_attributes(info)
    result["attributes"] = attributes
    for verb, attrs in sorted(attributes.items()):
        if not _contract_command_exists(verb, commands):
            result["errors"].append({
                "code": "unknown_command",
                "verb": verb,
                "message": f"attribute verb does not match declared commands: {verb}",
            })
        for attr in attrs:
            if attr not in CONTRACT_ATTRIBUTES:
                result["errors"].append({
                    "code": "unknown_attribute",
                    "verb": verb,
                    "attribute": attr,
                    "message": f"unknown contract attribute on {verb}: {attr}",
                })
        if verb not in seen and not (_BEATLESS_ATTRIBUTES & set(attrs)):
            result["warnings"].append({
                "code": "attribute_without_beat",
                "verb": verb,
                "message": (
                    f"verb {verb} carries attributes but belongs to no beat; "
                    "only passthrough/long_running verbs may stand alone"
                ),
            })

    for verb, beats in sorted(seen.items()):
        if len(beats) > 1 and not ({"polymorphic", "composite"} & set(attributes.get(verb, []))):
            result["warnings"].append({
                "code": "multi_beat_verb",
                "verb": verb,
                "beats": beats,
                "message": (
                    "verb is declared under multiple beats; mark it polymorphic "
                    "or composite in contracts.attributes if intentional"
                ),
            })

    # Concurrency must agree with the declared write surface. own_state writes
    # (a tool's own cache/state/derived output) are parallel-safe and exempt.
    concurrency = info.get("concurrency")
    write_verbs = sorted(
        verb
        for verb, beats in seen.items()
        if ({"connect", "interact", "save"} & set(beats))
        and "own_state" not in attributes.get(verb, [])
    )
    if concurrency == "read" and write_verbs:
        result["errors"].append({
            "code": "concurrency_mismatch",
            "verbs": write_verbs,
            "message": (
                "tool is declared concurrency:read but holds world-write verbs: "
                + ", ".join(write_verbs)
            ),
        })
    elif concurrency in ("write", "mixed") and seen and not write_verbs:
        result["warnings"].append({
            "code": "concurrency_overdeclared",
            "message": (
                f"tool is declared concurrency:{concurrency} but declares no "
                "world-write verbs; consider read"
            ),
        })

    result["ok"] = not result["errors"]
    return result


def validate_registry_contracts(registry: dict) -> dict:
    """Validate contract coverage and registry-shape consistency."""
    tools = registry.get("tools") or {}
    results = [
        validate_tool_contracts(tool, info)
        for tool, info in sorted(tools.items())
        if isinstance(info, dict)
    ]
    return {
        "tools": len(results),
        "declared": sum(1 for item in results if item["declared"]),
        "missing": sum(1 for item in results if not item["declared"]),
        "errors": sum(len(item["errors"]) for item in results),
        "warnings": sum(len(item["warnings"]) for item in results),
        "ok": all(item["ok"] for item in results),
        "results": results,
    }


def get_recommended_entrypoints(info: dict) -> list[str]:
    """Return the recommended entrypoints for a tool."""
    entrypoints = get_tool_routing(info).get('recommended_entrypoints') or []
    return [entry for entry in entrypoints if entry]


def get_default_command(info: dict) -> Optional[str]:
    """Return the preferred default command for a tool, if declared."""
    routing = get_tool_routing(info)
    default_command = routing.get('default_command')
    if default_command:
        return str(default_command)

    commands = info.get('commands', {})
    if commands:
        return next(iter(commands.keys()))
    return None


def get_project_signals(info: dict) -> list[str]:
    """Return project-signal tags for a tool."""
    return [signal for signal in get_tool_routing(info).get('project_signals', []) if signal]


def match_prompt_tools(registry: dict, prompt: str, limit: Optional[int] = None) -> list[dict]:
    """Return tools whose shared routing metadata matches a natural-language prompt."""
    prompt_lower = prompt.lower()
    matches = []

    for tool, info in registry.get('tools', {}).items():
        routing = get_tool_routing(info)
        score = 0
        matched_keywords = []
        matched_patterns = []

        for keyword in routing.get('discover_keywords', []):
            keyword_text = str(keyword).strip().lower()
            if not keyword_text:
                continue
            if keyword_text in prompt_lower:
                score += max(2, min(5, len(keyword_text.split()) + 1))
                matched_keywords.append(keyword)

        for pattern in routing.get('prompt_patterns', []):
            try:
                if re.search(pattern, prompt, re.IGNORECASE):
                    score += 6
                    matched_patterns.append(pattern)
            except re.error:
                continue

        if score > 0:
            matches.append({
                'tool': tool,
                'info': info,
                'score': score,
                'matched_keywords': matched_keywords,
                'matched_patterns': matched_patterns,
            })

    matches.sort(key=lambda item: (-item['score'], item['tool']))
    if limit is not None:
        return matches[:limit]
    return matches


def find_raw_cli_equivalent(registry: dict, command: str) -> Optional[dict]:
    """Return the first shared raw-command equivalent that matches a shell command."""
    for tool, info in registry.get('tools', {}).items():
        routing = get_tool_routing(info)
        for mapping in routing.get('raw_cli_equivalents', []):
            pattern = mapping.get('pattern')
            if not pattern:
                continue
            try:
                if not re.search(pattern, command, re.IGNORECASE):
                    continue
            except re.error:
                continue

            replacement = mapping.get('replacement') or f"agent-do {tool}"
            entrypoints = get_recommended_entrypoints(info)
            example = mapping.get('example') or (entrypoints[0] if entrypoints else replacement)
            return {
                'tool': tool,
                'info': info,
                'pattern': pattern,
                'replacement': replacement,
                'example': example,
                'reason': mapping.get('reason'),
            }
    return None


def rank_tools_for_project_signals(registry: dict, signals: list[str], limit: Optional[int] = None) -> list[dict]:
    """Return tools ranked by overlap with a set of normalized project signals."""
    normalized_signals = {signal.strip().lower() for signal in signals if signal and signal.strip()}
    ranked = []

    if not normalized_signals:
        return ranked

    for tool, info in registry.get('tools', {}).items():
        project_signals = {signal.strip().lower() for signal in get_project_signals(info)}
        overlap = normalized_signals & project_signals
        if overlap:
            ranked.append({
                'tool': tool,
                'info': info,
                'score': len(overlap),
                'matched_signals': sorted(overlap),
            })

    ranked.sort(key=lambda item: (-item['score'], item['tool']))
    if limit is not None:
        return ranked[:limit]
    return ranked


def search_tools(registry: dict, query: str) -> list[tuple[str, dict]]:
    """Search tools by query."""
    query = query.lower()
    results = []

    for tool, info in registry.get('tools', {}).items():
        score = 0

        # Check tool name
        if query in tool.lower():
            score += 10

        # Check description
        desc = info.get('description', '').lower()
        if query in desc:
            score += 5

        # Check capabilities
        for cap in info.get('capabilities', []):
            if query in cap.lower():
                score += 3

        # Check commands
        for cmd in info.get('commands', {}).keys():
            if query in cmd.lower():
                score += 2

        # Check examples
        for ex in info.get('examples', []):
            if query in ex.get('intent', '').lower():
                score += 1

        # Check shared routing metadata
        routing = get_tool_routing(info)
        for keyword in routing.get('discover_keywords', []):
            keyword_text = str(keyword).lower()
            if query in keyword_text or keyword_text in query:
                score += 4

        if score > 0:
            results.append((tool, info, score))

    # Sort by score descending
    results.sort(key=lambda x: x[2], reverse=True)
    return [(tool, info) for tool, info, _ in results]
