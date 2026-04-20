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
    lines = []
    for tool, info in sorted(registry.get('tools', {}).items()):
        lines.append(f"## {tool}")
        lines.append(f"{info.get('description', 'No description')}")

        commands = info.get('commands', {})
        if commands:
            cmd_list = ', '.join(commands.keys())
            lines.append(f"Commands: {cmd_list}")

        examples = info.get('examples', [])
        if examples:
            lines.append("Examples:")
            for ex in examples[:3]:
                lines.append(f"  \"{ex.get('intent', '')}\" → `{ex.get('command', '')}`")

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
    return {
        'required': [item for item in credentials.get('required', []) if item],
        'optional': [item for item in credentials.get('optional', []) if item],
        'one_of': [
            [entry for entry in group if entry]
            for group in credentials.get('one_of', [])
            if group
        ],
    }


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
