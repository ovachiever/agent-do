"""Registry loading for agent-do."""

import os
import yaml
from pathlib import Path
from typing import Optional

AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))


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
            with open(path) as f:
                data = yaml.safe_load(f) or {}
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


def list_tools(registry: dict) -> list[str]:
    """List all available tools."""
    return sorted(registry.get('tools', {}).keys())


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

        if score > 0:
            results.append((tool, info, score))

    # Sort by score descending
    results.sort(key=lambda x: x[2], reverse=True)
    return [(tool, info) for tool, info, _ in results]
