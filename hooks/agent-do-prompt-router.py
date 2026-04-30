#!/usr/bin/env python3
"""
UserPromptSubmit hook: route prompts to coord enforcement or precise agent-do suggestions.

Coord is the only blocking behavior. Tool suggestions are AI-gated, advisory, and emitted only
when the model selects high-confidence commands from the full agent-do catalog.
"""

import json
import os
import re
import shlex
import subprocess
import sys
from shutil import which
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

try:
    from registry import (
        load_registry,
        get_recommended_entrypoints,
    )
except ModuleNotFoundError:
    load_registry = None
    get_recommended_entrypoints = None

try:
    from telemetry import record_nudge_event
except ModuleNotFoundError:
    record_nudge_event = None

try:
    from ai_router import call_json_model
except ModuleNotFoundError:
    call_json_model = None

# Frontend/design intent detection — two-stage: UI keywords + action keywords
# If both present, it's a design task. Also catches direct design phrases.
_UI_KEYWORDS = re.compile(
    r'\b(ui|ux|visual|design|styling|css|scss|tailwind|layout|spacing|padding|margin|'
    r'color|colour|font|typography|hierarchy|theme|palette|appearance|aesthetic|'
    r'dashboard|sidebar|navbar|header|footer|card|modal|form|page|screen|component|'
    r'landing.page|homepage|frontend|front.end)\b', re.IGNORECASE
)
_ACTION_KEYWORDS = re.compile(
    r'\b(improv|fix|updat|redesign|refactor|polish|refine|beautif|overhaul|'
    r'make.{0,20}(look|prettier|better|beautiful|modern|cleaner|nicer)|'
    r'chang|adjust|tweak|enhance|redo|rework|clean.up|revamp)\w*\b', re.IGNORECASE
)
# Direct match patterns that don't need two-stage
FRONTEND_DESIGN_DIRECT = [
    r'\b(ugly|bad.looking|needs.work|looks\s*(bad|wrong|off|weird|terrible|awful))\b',
    r'\bdpt\s*(score|audit|check|review|baseline)\b',
    r'\bartful\b',
    r'\bdesign\s*(system|token|review|audit|score|quality)\b',
    r'\b(screenshot|browse).*(before|after|baseline|compare)\b',
]

COMPLETION_DIRECT_WORDS = {
    "continue",
    "cont",
}

COMPLETION_AFFIRMATIONS = {
    "agreed",
    "ok",
    "okay",
    "sure",
    "yep",
    "yes",
}

COMPLETION_STATUS_WORDS = {
    "next",
    "left",
    "else",
}

COMPLETION_STATUS_PATTERNS = [
    r"\bwhere(\s+are)?\s+we\s+at\b",
    r"\bhow('?s|\s+is)\s+it\s+going\b",
    r"\bhow\s+are\s+we\s+doing\b",
]

COMPLETION_CHECK_CONTEXT = """## Completion Check

Before proposing more work, first decide whether the primary goal is already complete.
If it is, stop and label anything else as optional backlog, not required next work.
"""

DESIGN_TOOLKIT_CONTEXT = """## Design Toolkit — ACTIVE for this task

This request involves visual/UI work. Follow this protocol:

### Step 1: Load Design Skills
Read and apply ALL THREE for any UI work:
- `~/.claude/skills/artful-ux/SKILL.md` — layout, hierarchy, interaction, spacing, anti-patterns
- `~/.claude/skills/artful-colors/SKILL.md` — color perception, palette, cultural context
- `~/.claude/skills/artful-typography/SKILL.md` — typeface selection, hierarchy, responsive type

### Step 2: Browser Verification (MANDATORY)
```
agent-do browse open <dev-url>
agent-do browse screenshot /tmp/before.png   # BASELINE — view with Read tool
```

### Step 3: Code → Verify → Score loop
```
# After each change:
agent-do browse reload
agent-do browse wait --stable
agent-do browse screenshot /tmp/after.png    # View with Read tool
agent-do dpt score /tmp/after.png            # 0-100 score with breakdown
```

### Step 4: Structural audit
```
agent-do browse snapshot -i                  # Interactive elements, affordances, labels
```

Screenshots = visual truth. Snapshots = structural truth. Both, in that order.
Never ship UI changes without this verification loop.
"""

COORD_PATTERNS = [
    r"\banother agent\b",
    r"\bother agent\b",
    r"\bhandoff\b",
    r"\bdon't conflict\b",
    r"\bdo not conflict\b",
    r"\breview .*agent\b",
    r"\bother session\b",
    r"\bseparate tmux sessions?\b",
    r"\bwhat is the other agent doing\b",
    r"\bcoordinate\b.*\bagent\b",
]

COORD_WORK_PATTERNS = [
    r"\b(build|implement|fix|edit|change|update|refactor|write|add|remove|delete)\b",
    r"\b(run|test|debug|repair|review|merge|commit|push|deploy|ship)\b",
    r"\b(open|create)\s+(a\s+)?pr\b",
    r"\baddress\s+(comments?|feedback|review)\b",
    r"\bdo\s+it\b",
    r"\bgo\b.*\b(do|implement|fix|build|ship)\b",
]

COORD_DISCUSSION_PATTERNS = [
    r"\b(could|can)\s+you\s+(tell|explain|discuss)\b",
    r"\b(what|why|how|does|do|is|are)\b.*\?",
    r"\b(thoughts?|opinion|recommend|pick|choose|compare)\b",
    r"\b(let'?s|lets)\s+(talk|discuss|think|pick|choose)\b",
]

BLOCKING_INTERRUPT_KINDS = {"contention", "dependency"}
DEFAULT_HOOK_AI_CONFIDENCE = 0.86


def build_ai_catalog(registry: dict) -> list[dict]:
    """Return the full agent-do catalog in a compact form suitable for hook routing."""
    catalog = []
    for tool, info in sorted(registry.get("tools", {}).items()):
        commands = list((info.get("commands") or {}).keys())
        examples = []
        for example in (info.get("examples") or [])[:3]:
            intent = example.get("intent")
            command = example.get("command")
            if intent and command:
                examples.append({"intent": intent, "command": command})

        catalog.append(
            {
                "tool": tool,
                "description": info.get("description", ""),
                "capabilities": [str(item) for item in (info.get("capabilities") or [])[:6]],
                "commands": commands,
                "recommended_entrypoints": get_recommended_entrypoints(info) if get_recommended_entrypoints else [],
                "examples": examples,
            }
        )
    return catalog


def command_has_shell_control(command: str) -> bool:
    return any(token in command for token in ("\n", "\r", "&&", ";", "|", "`", "$("))


def command_parts(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return []


def valid_agent_do_command(command: str, registry: dict, expected_tool: str | None = None) -> bool:
    command = command.strip()
    if not command or command_has_shell_control(command):
        return False
    parts = command_parts(command)
    if len(parts) < 2 or parts[0] != "agent-do":
        return False
    tool = parts[1]
    if tool not in registry.get("tools", {}):
        return False
    return expected_tool is None or tool == expected_tool


def valid_focus_command(command: str) -> bool:
    command = command.strip()
    if not command or command_has_shell_control(command):
        return False
    parts = command_parts(command)
    return len(parts) >= 5 and parts[:4] == ["agent-do", "coord", "focus", "set"]


def infer_focus_goal(prompt: str) -> str:
    prompt_lower = prompt.lower()
    if "userprompt" in prompt_lower or "prompt submit" in prompt_lower or "prompt-router" in prompt_lower:
        return "fix UserPromptSubmit coordination enforcement"
    if "global agents" in prompt_lower or "global agents file" in prompt_lower:
        return "update global AGENTS workflow policy"

    words = re.findall(r"[A-Za-z0-9_./-]+", prompt)
    goal = " ".join(words[:10]).strip()
    return goal or "repo work"


def infer_focus_paths(prompt: str, cwd: str | None) -> list[str]:
    prompt_lower = prompt.lower()
    paths: list[str] = []

    if "global agents" in prompt_lower or "global agents file" in prompt_lower:
        paths.append(str(Path.home() / ".codex" / "AGENTS.md"))

    if "userprompt" in prompt_lower or "prompt submit" in prompt_lower or "prompt-router" in prompt_lower or "hook" in prompt_lower:
        paths.extend(["hooks/agent-do-prompt-router.py", "tests/test_v11_routing.py"])

    if not paths:
        paths.append(".")

    return paths


def fallback_focus_command(prompt: str, cwd: str | None) -> str:
    command = f"agent-do coord focus set {shlex.quote(infer_focus_goal(prompt))}"
    for path in infer_focus_paths(prompt, cwd):
        command += f" --path {shlex.quote(path)}"
    return command


def compact_peers(active_peers: list[dict]) -> list[dict]:
    return [
        {
            "agent": peer.get("alias") or peer.get("agent_id"),
            "goal": ((peer.get("focus") or {}).get("goal")) or "",
            "paths": ((peer.get("focus") or {}).get("paths")) or [],
        }
        for peer in active_peers[:8]
    ]


def compact_interrupts(interrupts: list[dict]) -> list[dict]:
    return [
        {"kind": item.get("kind"), "summary": item.get("summary"), "new": bool(item.get("new"))}
        for item in interrupts[:8]
    ]


def parse_confidence(value) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def hook_confidence_threshold() -> float:
    value = os.environ.get("AGENT_DO_HOOK_AI_CONFIDENCE")
    if value:
        try:
            parsed = float(value)
            if 0 <= parsed <= 1:
                return parsed
        except ValueError:
            pass
    return DEFAULT_HOOK_AI_CONFIDENCE


def detect_frontend_design(prompt: str) -> bool:
    """Detect if prompt involves frontend/design/visual work."""
    # Two-stage: UI keyword + action keyword = design intent
    has_ui = bool(_UI_KEYWORDS.search(prompt))
    has_action = bool(_ACTION_KEYWORDS.search(prompt))
    if has_ui and has_action:
        return True
    # Direct match patterns
    prompt_lower = prompt.lower()
    for pattern in FRONTEND_DESIGN_DIRECT:
        if re.search(pattern, prompt_lower):
            return True
    return False


def needs_completion_check(prompt: str) -> bool:
    """Detect short continuation/status prompts that should refresh the stop condition."""
    prompt_lower = prompt.lower().strip()
    normalized = re.sub(r"[^a-z0-9'\s]+", " ", prompt_lower)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return False

    words = normalized.split()
    short_prompt = len(words) <= 8

    if short_prompt and any(word in COMPLETION_DIRECT_WORDS for word in words):
        return True

    if short_prompt and words and words[0] in COMPLETION_AFFIRMATIONS:
        if any(word in COMPLETION_DIRECT_WORDS or (word == "go" and "ahead" in words) for word in words[1:]):
            return True

    if short_prompt and re.search(r"\bwhat('?s|\s+is)?\s+(next|left)\b", normalized):
        return True

    if short_prompt and "what" in words:
        if any(word in COMPLETION_STATUS_WORDS for word in words):
            return True

    if short_prompt and "anything" in words and "else" in words:
        return True

    for pattern in COMPLETION_STATUS_PATTERNS:
        if re.search(pattern, normalized):
            return True

    return False


def detect_coord_prompt(prompt: str) -> bool:
    prompt_lower = prompt.lower()
    return any(re.search(pattern, prompt_lower) for pattern in COORD_PATTERNS)


def prompt_looks_like_coord_work(prompt: str) -> bool:
    prompt_lower = prompt.lower()
    work = any(re.search(pattern, prompt_lower) for pattern in COORD_WORK_PATTERNS)
    if not work:
        return False

    discussion = any(re.search(pattern, prompt_lower) for pattern in COORD_DISCUSSION_PATTERNS)
    if discussion and not re.search(r"\b(do\s+it|go|now|please\s+(build|fix|implement|update))\b", prompt_lower):
        return False

    return True


def ai_route_prompt(
    prompt: str,
    *,
    cwd: str | None,
    coord_state: dict,
    registry: dict,
) -> dict | None:
    if call_json_model is None:
        return None

    payload = {
        "prompt": prompt,
        "cwd": cwd,
        "coord": {
            "current_agent_has_focus": bool(coord_state.get("focus_goal")),
            "current_focus_goal": coord_state.get("focus_goal") or "",
            "active_peers": compact_peers(coord_state.get("active_peers") or []),
            "interrupts": compact_interrupts(coord_state.get("interrupts") or []),
        },
        "path_hints": {
            "global_agents": str(Path.home() / ".codex" / "AGENTS.md"),
            "repo_userprompt_hook": "hooks/agent-do-prompt-router.py",
            "repo_userprompt_tests": "tests/test_v11_routing.py",
        },
        "catalog": build_ai_catalog(registry),
    }
    prompt_text = f"""Classify a Codex UserPromptSubmit prompt and decide whether to emit anything.

Two products share this hook:
1. Coordination enforcement. This is the only thing that may block.
2. agent-do tool suggestions. These are advisory only and should be rare.

Rules:
- If another active peer exists, this agent has no focus, and the prompt starts workspace work, require a coord focus block.
- Workspace work includes editing files, debugging, testing, reviewing code/PRs, committing, pushing, deploying, or "do it/go" continuation of work.
- Pure discussion, status questions, explanations, model choice, and "no touching" prompts should not be blocked.
- For tool suggestions, inspect the full catalog and emit only if one or two agent-do commands are clearly stellar and exact.
- Do not emit generic setup/search/status suggestions unless the prompt directly asks for that operation.
- It is good to emit nothing.
- Never invent tools. Commands must start with `agent-do <tool>`.

Input JSON:
{json.dumps({
    "prompt": payload["prompt"],
    "cwd": payload["cwd"],
    "coord": payload["coord"],
    "path_hints": payload["path_hints"],
    "catalog": payload["catalog"],
}, indent=2)}

Respond with JSON only:
{{
  "prompt_kind": "work_starting|discussion|coordination|status|other",
  "starts_work": true,
  "coord": {{
    "block": true,
    "reason": "short reason",
    "focus_command": "agent-do coord focus set \\"goal\\" --path path"
  }},
  "emit_tools": true,
  "tool_suggestions": [
    {{
      "tool": "tool-name-from-catalog",
      "command": "agent-do tool-name command",
      "why": "short reason",
      "confidence": 0.0
    }}
  ]
}}
"""
    return call_json_model(
        prompt_text,
        flag_name="AGENT_DO_HOOK_AI",
        system=(
            "You are a fast, high-precision routing gate for Codex UserPromptSubmit hooks. "
            "Return strict JSON only. "
            "Be engineering-ready, clear, and concise. Use the fewest words that preserve correctness; "
            "do not omit necessary operational detail."
        ),
    )


def decision_starts_work(prompt: str, decision: dict | None) -> bool:
    if isinstance(decision, dict) and isinstance(decision.get("starts_work"), bool):
        return bool(decision["starts_work"])
    return prompt_looks_like_coord_work(prompt)


def blocking_interrupts(interrupts: list[dict]) -> list[dict]:
    return [item for item in interrupts if item.get("kind") in BLOCKING_INTERRUPT_KINDS]


def ai_coord_payload(decision: dict | None) -> dict:
    if not isinstance(decision, dict):
        return {}
    coord = decision.get("coord")
    return coord if isinstance(coord, dict) else {}


def format_coord_block(
    *,
    prompt: str,
    cwd: str | None,
    coord_state: dict,
    decision: dict | None,
    reason: str,
) -> str:
    coord = ai_coord_payload(decision)
    command = str(coord.get("focus_command") or "").strip()
    if not valid_focus_command(command):
        command = fallback_focus_command(prompt, cwd)

    peer_lines = []
    for peer in compact_peers(coord_state.get("active_peers") or []):
        suffix = f" goal: {peer['goal']}" if peer.get("goal") else ""
        peer_lines.append(f"- {peer.get('agent')}{suffix}")
    peers = "\n".join(peer_lines) if peer_lines else "- active peer present"

    return (
        "Coord focus required before starting workspace work.\n\n"
        f"Reason: {reason}\n\n"
        f"Run:\n{command}\n\n"
        f"Active peers:\n{peers}\n\n"
        "Then retry the prompt."
    )


def coord_block_reason(prompt: str, cwd: str | None, coord_state: dict, decision: dict | None) -> str | None:
    starts_work = decision_starts_work(prompt, decision)
    coord = ai_coord_payload(decision)
    ai_requested_block = bool(coord.get("block")) if isinstance(coord.get("block"), bool) else False
    active_peers = coord_state.get("active_peers") or []
    focus_goal = coord_state.get("focus_goal") or ""
    blockers = blocking_interrupts(coord_state.get("interrupts") or [])

    if blockers and (starts_work or ai_requested_block):
        summary = "; ".join(str(item.get("summary") or item.get("kind")) for item in blockers[:3])
        return format_coord_block(
            prompt=prompt,
            cwd=cwd,
            coord_state=coord_state,
            decision=decision,
            reason=f"coord interrupt is active: {summary}",
        )

    if active_peers and not focus_goal and (starts_work or ai_requested_block):
        reason = str(coord.get("reason") or "another active peer exists and this agent has no declared focus")
        return format_coord_block(
            prompt=prompt,
            cwd=cwd,
            coord_state=coord_state,
            decision=decision,
            reason=reason,
        )

    return None


def ai_tool_suggestion_context(decision: dict | None, registry: dict) -> tuple[str, list[str]]:
    if not isinstance(decision, dict) or decision.get("emit_tools") is not True:
        return "", []

    threshold = hook_confidence_threshold()
    raw_suggestions = decision.get("tool_suggestions") or []
    if not isinstance(raw_suggestions, list):
        return "", []

    lines = []
    tools = []
    seen_commands = set()
    for item in raw_suggestions:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "").strip()
        command = str(item.get("command") or "").strip()
        confidence = parse_confidence(item.get("confidence"))
        why = str(item.get("why") or "").strip()
        if confidence < threshold:
            continue
        if not valid_agent_do_command(command, registry, expected_tool=tool):
            continue
        if command in seen_commands:
            continue
        seen_commands.add(command)
        tools.append(tool)
        suffix = f" - {why}" if why else ""
        lines.append(f"- `{command}`{suffix}")

    if not lines:
        return "", []

    return (
        "## agent-do Tool Suggestion\n\n"
        "High-confidence agent-do path:\n"
        + "\n".join(lines)
        + "\n",
        tools,
    )


def resolve_agent_do_binary() -> str | None:
    direct = which("agent-do")
    if direct:
        return direct

    repo_candidate = Path(__file__).resolve().parents[1] / "agent-do"
    if repo_candidate.exists():
        return str(repo_candidate)

    local = Path.home() / ".local" / "bin" / "agent-do"
    if local.exists():
        return str(local)

    breadcrumb = Path.home() / ".agent-do" / "install-path"
    if breadcrumb.exists():
        resolved = breadcrumb.read_text().strip()
        candidate = Path(resolved) / "agent-do"
        if candidate.exists():
            return str(candidate)

    return None


def load_coord_state(cwd: str | None) -> dict:
    state = {"active_peers": [], "focus_goal": "", "interrupts": []}
    if not cwd:
        return state
    agent_do = resolve_agent_do_binary()
    if not agent_do:
        return state

    touched = subprocess.run(
        [agent_do, "coord", "touch", "--json"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if touched.returncode != 0 or not touched.stdout.strip():
        return state

    touch_payload = json.loads(touched.stdout)
    state["active_peers"] = touch_payload.get("active_peers", [])
    state["focus_goal"] = ((touch_payload.get("focus") or {}).get("goal")) or ""

    interrupts_run = subprocess.run(
        [agent_do, "coord", "interrupts", "--json", "--limit", "5"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if interrupts_run.returncode != 0 or not interrupts_run.stdout.strip():
        interrupts_payload = {"interrupts": []}
    else:
        interrupts_payload = json.loads(interrupts_run.stdout)

    state["interrupts"] = interrupts_payload.get("interrupts", [])
    return state


def coord_advisory_context(prompt: str, coord_state: dict) -> tuple[str, list[str]]:
    if detect_coord_prompt(prompt):
        return (
            "## Coord Suggestion\n\n"
            "This sounds like multi-agent coordination. Start with:\n"
            "- `agent-do coord status`\n"
            "- `agent-do coord interrupts`\n"
            "- `agent-do coord focus set \"<goal>\" --path <path>`\n",
            ["coord"],
        )

    return "", []


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    prompt = input_data.get("prompt", "")
    if not prompt:
        sys.exit(0)
    cwd = input_data.get("cwd")

    registry = load_registry() if load_registry is not None else {"tools": {}}
    coord_state = load_coord_state(cwd)
    ai_decision = ai_route_prompt(prompt, cwd=cwd, coord_state=coord_state, registry=registry)
    block_reason = coord_block_reason(prompt, cwd, coord_state, ai_decision)
    if block_reason:
        if record_nudge_event is not None:
            try:
                record_nudge_event(
                    "prompt_coord_block",
                    "prompt_router",
                    tools=["coord"],
                    prompt=prompt[:240],
                )
            except Exception:
                pass
        print(json.dumps({"decision": "block", "reason": block_reason}))
        sys.exit(0)

    tool_context, tool_tools = ai_tool_suggestion_context(ai_decision, registry)
    coord_context, coord_tools = coord_advisory_context(prompt, coord_state)
    is_design = detect_frontend_design(prompt)

    needs_completion = needs_completion_check(prompt)

    if tool_context or is_design or needs_completion or coord_context:
        context = ""

        if tool_context:
            context += tool_context
            if record_nudge_event is not None:
                try:
                    record_nudge_event(
                        "prompt_tool_suggestion",
                        "prompt_router",
                        tools=tool_tools,
                        prompt=prompt[:240],
                    )
                except Exception:
                    pass

        if is_design:
            context += "\n" + DESIGN_TOOLKIT_CONTEXT
            if record_nudge_event is not None:
                try:
                    record_nudge_event(
                        "prompt_design_toolkit",
                        "prompt_router",
                        tools=["browse", "dpt"],
                        prompt=prompt[:240],
                    )
                except Exception:
                    pass

        if needs_completion:
            if context:
                context += "\n"
            context += COMPLETION_CHECK_CONTEXT
            if record_nudge_event is not None:
                try:
                    record_nudge_event(
                        "prompt_completion_check",
                        "prompt_router",
                        prompt=prompt[:240],
                    )
                except Exception:
                    pass

        if coord_context:
            if context:
                context += "\n"
            context += coord_context
            if record_nudge_event is not None:
                try:
                    record_nudge_event(
                        "prompt_coord_context",
                        "prompt_router",
                        tools=coord_tools,
                        prompt=prompt[:240],
                    )
                except Exception:
                    pass

        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    # No matches — pass through
    sys.exit(0)

if __name__ == "__main__":
    main()
