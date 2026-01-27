"""State management for agent-do."""

import os
import yaml
from pathlib import Path
from datetime import datetime
from typing import Optional

AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))


def get_state_path() -> Path:
    """Get path to state file."""
    return AGENT_DO_HOME / "state.yaml"


def load_state() -> dict:
    """Load current session state."""
    state_path = get_state_path()
    if state_path.exists():
        with open(state_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_state(state: dict) -> None:
    """Save session state."""
    AGENT_DO_HOME.mkdir(parents=True, exist_ok=True)
    state_path = get_state_path()
    with open(state_path, 'w') as f:
        yaml.dump(state, f, default_flow_style=False)


def build_state_context(state: dict) -> str:
    """Build state summary for LLM context."""
    if not state:
        return "No active sessions."

    lines = []
    if state.get('tui'):
        lines.append("Active TUI sessions:")
        for s in state['tui']:
            lines.append(f"  - Session {s['id']}: {s.get('label', s.get('command', 'unknown'))}")

    if state.get('repl'):
        lines.append("Active REPL sessions:")
        for s in state['repl']:
            lines.append(f"  - Session {s['id']}: {s.get('type', 'unknown')}")

    if state.get('ios'):
        ios = state['ios']
        if isinstance(ios, dict):
            lines.append(f"iOS Simulator: {ios.get('booted', 'not running')}")
        else:
            lines.append(f"iOS Simulator: {ios}")

    if state.get('android'):
        android = state['android']
        if isinstance(android, dict):
            lines.append(f"Android Emulator: {android.get('booted', 'not running')}")
        else:
            lines.append(f"Android Emulator: {android}")

    if state.get('docker'):
        containers = state['docker'].get('containers', [])
        if containers:
            lines.append(f"Docker: {len(containers)} containers running")
            for c in containers[:5]:
                name = c.get('name', c.get('id', 'unknown'))
                lines.append(f"  - {name}")

    if state.get('ssh'):
        lines.append("Active SSH sessions:")
        for s in state['ssh']:
            lines.append(f"  - Session {s['id']}: {s.get('host', 'unknown')}")

    return "\n".join(lines) if lines else "No active sessions."


def add_tui_session(session_id: int, command: str, label: Optional[str] = None) -> None:
    """Add a TUI session to state."""
    state = load_state()
    if 'tui' not in state:
        state['tui'] = []

    state['tui'].append({
        'id': session_id,
        'command': command,
        'label': label or command,
        'started': datetime.now().isoformat()
    })
    save_state(state)


def remove_tui_session(session_id: int) -> None:
    """Remove a TUI session from state."""
    state = load_state()
    if 'tui' in state:
        state['tui'] = [s for s in state['tui'] if s['id'] != session_id]
        if not state['tui']:
            del state['tui']
    save_state(state)


def add_repl_session(session_id: int, repl_type: str) -> None:
    """Add a REPL session to state."""
    state = load_state()
    if 'repl' not in state:
        state['repl'] = []

    state['repl'].append({
        'id': session_id,
        'type': repl_type,
        'started': datetime.now().isoformat()
    })
    save_state(state)


def remove_repl_session(session_id: int) -> None:
    """Remove a REPL session from state."""
    state = load_state()
    if 'repl' in state:
        state['repl'] = [s for s in state['repl'] if s['id'] != session_id]
        if not state['repl']:
            del state['repl']
    save_state(state)


def set_ios_state(booted: Optional[str] = None, udid: Optional[str] = None) -> None:
    """Set iOS simulator state."""
    state = load_state()
    if booted:
        state['ios'] = {'booted': booted}
        if udid:
            state['ios']['udid'] = udid
    elif 'ios' in state:
        del state['ios']
    save_state(state)


def set_android_state(booted: Optional[str] = None, avd: Optional[str] = None) -> None:
    """Set Android emulator state."""
    state = load_state()
    if booted:
        state['android'] = {'booted': booted}
        if avd:
            state['android']['avd'] = avd
    elif 'android' in state:
        del state['android']
    save_state(state)
