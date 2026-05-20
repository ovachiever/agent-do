#!/usr/bin/env python3
"""
UserPromptSubmit hook: route prompts to coord requirements or precise agent-do suggestions.

Coord requirements are emitted as hard context, not blocking hook decisions. Tool suggestions
are AI-gated, advisory, and emitted only when the model selects high-confidence commands from
the full agent-do catalog.
"""

import json
import os
import re
import shlex
import subprocess
import sys
from shutil import which
from pathlib import Path

# File lives at <repo>/hooks/claude/agent-do-prompt-router.py, so the repo
# root is two parents up and lib/ is its sibling.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

try:
    from registry import (
        load_registry,
        get_recommended_entrypoints,
    )
except ModuleNotFoundError:
    load_registry = None
    get_recommended_entrypoints = None

try:
    from telemetry import record_hook_decision, record_nudge_event
except ModuleNotFoundError:
    record_hook_decision = None
    record_nudge_event = None

try:
    from ai_router import call_json_model
except ModuleNotFoundError:
    call_json_model = None

# Intent classification (docs-retrieval, design-work, coord-discussion) is
# routed through the AI classifier in ai_route_prompt(). Keyword-only paths
# were removed because regex cannot distinguish "user wants X done now" from
# "user is discussing X as a topic" or "user is forwarding a handoff that
# describes X." Misfires from those false positives motivated this design.
# When the AI router is unavailable, the hook stays silent on intent-bound
# nudges rather than guessing. State-grounded paths (coord_required,
# needs_completion_check) still fire because they don't require classification.

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

CONTEXT_RETRIEVE_QUERY_MAX_CHARS = 280


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
        routing_intents = []
        routing = info.get("routing") or {}
        for item in (routing.get("intents") or [])[:8]:
            if not isinstance(item, dict):
                continue
            label = item.get("label")
            if not label:
                continue
            routing_intents.append(
                {
                    "label": str(label),
                    "examples": [str(ex) for ex in (item.get("examples") or [])[:4]],
                    "recommended_entrypoint": str(item.get("recommended_entrypoint") or ""),
                }
            )

        catalog.append(
            {
                "tool": tool,
                "description": info.get("description", ""),
                "capabilities": [str(item) for item in (info.get("capabilities") or [])[:6]],
                "commands": commands,
                "recommended_entrypoints": get_recommended_entrypoints(info) if get_recommended_entrypoints else [],
                "examples": examples,
                "routing_intents": routing_intents,
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


def build_context_retrieve_command(query: str) -> str:
    """Build the suggested context retrieve command from a short, focused query.

    The query is provided by the AI classifier as a distilled phrase describing
    what the user actually wants retrieved. The hook caps the query length so
    we never emit multi-kilobyte shell-quoted blobs, but the AI is expected to
    return something already short and specific.
    """
    query = (query or "").strip()
    if not query:
        return ""
    if len(query) > CONTEXT_RETRIEVE_QUERY_MAX_CHARS:
        query = query[:CONTEXT_RETRIEVE_QUERY_MAX_CHARS].rstrip() + "..."
    return f"agent-do context retrieve {shlex.quote(query)} --fresh --prefer-latest --max-tokens 8000"


def ai_context_retrieval_context(decision: dict | None) -> tuple[str, list[str], list[str]]:
    """Emit a context-retrieval nudge only when the AI classifier says the user
    is requesting external docs RIGHT NOW (intent, not topic). The classifier
    also supplies the focused retrieval query; the hook never derives the query
    from prompt text directly.
    """
    if not isinstance(decision, dict) or decision.get("needs_docs_retrieval") is not True:
        return "", [], []

    query = str(decision.get("docs_query") or "").strip()
    command = build_context_retrieve_command(query)
    if not command:
        return "", [], []

    return (
        "## agent-do Context Retrieval\n\n"
        "This prompt asks for external docs/API/library behavior. Before answering or implementing, run:\n"
        f"- `{command}`\n\n"
        "Use the returned provenance and freshness metadata. If retrieval fails, say what remains stale instead of guessing.\n",
        ["context"],
        [command],
    )


def ai_is_design_work(decision: dict | None) -> bool:
    """The AI classifier says the user is performing UI/design work right now
    (not merely discussing design as a topic)."""
    return isinstance(decision, dict) and decision.get("is_design_work") is True


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

Four products share this hook. All of them must be classified by INTENT, not by topic keywords. A prompt that discusses a topic is not the same as a prompt that asks the agent to act on that topic right now.

1. Coordination enforcement. The only product that may block. Fires when another active peer exists, this agent has no focus, and the prompt starts workspace work.
2. agent-do tool suggestions. Advisory. Emit at most one or two when an exact agent-do command is clearly the right first move for the user's immediate ask.
3. External docs/API retrieval (needs_docs_retrieval). Emit ONLY when the user is asking the agent to use, check, or rely on external docs/APIs/SDKs to perform the current task. A long handoff or design discussion that MENTIONS docs as a topic is NOT this intent. Mere occurrence of "docs," "api," "sdk," "library" is not enough; the user must be requesting their use right now.
4. Frontend/design work toolkit (is_design_work). Emit ONLY when the user is asking the agent to perform UI/visual/design work right now (build a page, score a UI, improve styling, audit visuals, screenshot-and-verify). A prompt that discusses design as a topic or reviews a design plan is NOT this intent.

Rules:
- "Workspace work" for coord includes editing files, debugging, testing, reviewing code/PRs, committing, pushing, deploying, or "do it/go" continuation of work.
- Pure discussion, status questions, explanations, model choice, and "no touching" prompts should not be blocked.
- For tool suggestions, inspect the full catalog and emit only if one or two agent-do commands are clearly stellar and exact.
- Tools may declare routing_intents with labels and examples. Treat those as classifier labels, not keyword rules. If a prompt matches one, suggest the recommended entrypoint only when it is the right immediate action.
- Do not emit generic setup/search/status suggestions unless the prompt directly asks for that operation.
- It is good to emit nothing. Be conservative on every classification. False positives are worse than false negatives.
- Never invent tools. Commands must start with `agent-do <tool>`.

Specific guidance for needs_docs_retrieval:
- True only if the prompt's primary ask depends on current external API/library/SDK behavior the agent doesn't already know.
- Examples that ARE this intent: "use the latest Stripe webhook docs to fix our handler," "check the current Anthropic API for cache_control format," "look up the v11 better-auth migration guide and apply it."
- Examples that are NOT this intent: "review this handoff that discusses docs retrieval," "explain how agent-do context works," "the README mentions docs," forwarded narrative prose that incidentally contains the word "docs" or "api."
- If true, also produce docs_query: a SHORT focused phrase (max 200 chars) describing what should be retrieved. Not the full prompt. Not a question. Just the topic, e.g., "Anthropic prompt caching with cache_control," "Stripe webhook idempotency 2024."

Specific guidance for is_design_work:
- True only when the user is asking the agent to perform UI/visual/design work as the primary action of this turn.
- Examples that ARE this intent: "the landing page looks bad, fix it," "score this screenshot," "redesign the dashboard header," "audit the form's spacing."
- Examples that are NOT this intent: "review this design plan," "discuss the design system," any prompt where the agent will be editing backend code, infra, hooks, docs, or anything non-visual, even if the word "design" appears in the prompt.

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
  "needs_docs_retrieval": false,
  "docs_query": "",
  "is_design_work": false,
  "matched_intents": ["optional catalog routing intent labels"],
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


def format_coord_requirement(
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
        "## Coord Focus Required\n\n"
        "Before starting workspace work, set coord focus. This is not a blocking hook decision, "
        "but it is required workflow context.\n\n"
        f"Reason: {reason}\n\n"
        f"Run before editing/testing/reviewing:\n`{command}`\n\n"
        f"Active peers:\n{peers}\n\n"
        "After focus is set, continue with the user request."
    )


def coord_required_context(prompt: str, cwd: str | None, coord_state: dict, decision: dict | None) -> str | None:
    starts_work = decision_starts_work(prompt, decision)
    coord = ai_coord_payload(decision)
    ai_requested_block = bool(coord.get("block")) if isinstance(coord.get("block"), bool) else False
    active_peers = coord_state.get("active_peers") or []
    focus_goal = coord_state.get("focus_goal") or ""
    blockers = blocking_interrupts(coord_state.get("interrupts") or [])

    if blockers and (starts_work or ai_requested_block):
        summary = "; ".join(str(item.get("summary") or item.get("kind")) for item in blockers[:3])
        return format_coord_requirement(
            prompt=prompt,
            cwd=cwd,
            coord_state=coord_state,
            decision=decision,
            reason=f"coord interrupt is active: {summary}",
        )

    if active_peers and not focus_goal and (starts_work or ai_requested_block):
        reason = str(coord.get("reason") or "another active peer exists and this agent has no declared focus")
        return format_coord_requirement(
            prompt=prompt,
            cwd=cwd,
            coord_state=coord_state,
            decision=decision,
            reason=reason,
        )

    return None


def ai_tool_suggestion_context(decision: dict | None, registry: dict) -> tuple[str, list[str], list[str]]:
    if not isinstance(decision, dict) or decision.get("emit_tools") is not True:
        return "", [], []

    threshold = hook_confidence_threshold()
    raw_suggestions = decision.get("tool_suggestions") or []
    if not isinstance(raw_suggestions, list):
        return "", [], []

    lines = []
    tools = []
    commands = []
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
        commands.append(command)
        suffix = f" - {why}" if why else ""
        lines.append(f"- `{command}`{suffix}")

    if not lines:
        return "", [], []

    return (
        "## agent-do Tool Suggestion\n\n"
        "High-confidence agent-do path:\n"
        + "\n".join(lines)
        + "\n",
        tools,
        commands,
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

    hook_env = os.environ.copy()
    hook_env["AGENT_DO_TELEMETRY_SUPPRESS"] = "1"

    touched = subprocess.run(
        [agent_do, "coord", "touch", "--json"],
        cwd=cwd,
        env=hook_env,
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
        env=hook_env,
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
    coord_required = coord_required_context(prompt, cwd, coord_state, ai_decision)
    tool_context, tool_tools, tool_commands = ai_tool_suggestion_context(ai_decision, registry)
    context_retrieve, context_tools, context_commands = ai_context_retrieval_context(ai_decision)
    is_design = ai_is_design_work(ai_decision)
    needs_completion = needs_completion_check(prompt)

    should_emit = bool(coord_required or tool_context or context_retrieve or is_design or needs_completion)
    if record_hook_decision is not None:
        try:
            decision_tools = []
            decision_commands = []
            if coord_required:
                decision_tools.append("coord")
            if tool_tools:
                decision_tools.extend(tool_tools)
                decision_commands.extend(tool_commands)
            if context_tools:
                decision_tools.extend(context_tools)
                decision_commands.extend(context_commands)
            if is_design:
                decision_tools.extend(["browse", "dpt"])
            record_hook_decision(
                "UserPromptSubmit",
                "prompt_router",
                "emit" if should_emit else "suppress",
                prompt=prompt,
                cwd=cwd,
                tools=list(dict.fromkeys(decision_tools)),
                commands=decision_commands,
                reason="context_emitted" if should_emit else "no_high_confidence_context",
            )
        except Exception:
            pass

    if should_emit:
        context = ""

        if coord_required:
            context += coord_required
            if record_nudge_event is not None:
                try:
                    record_nudge_event(
                        "prompt_coord_required",
                        "prompt_router",
                        tools=["coord"],
                        prompt=prompt[:240],
                        cwd=cwd,
                    )
                except Exception:
                    pass

        if tool_context:
            if context:
                context += "\n"
            context += tool_context
            if record_nudge_event is not None:
                try:
                    record_nudge_event(
                        "prompt_tool_suggestion",
                        "prompt_router",
                        tools=tool_tools,
                        commands=tool_commands,
                        prompt=prompt[:240],
                        cwd=cwd,
                    )
                except Exception:
                    pass

        if context_retrieve:
            if context:
                context += "\n"
            context += context_retrieve
            if record_nudge_event is not None:
                try:
                    record_nudge_event(
                        "prompt_context_retrieve",
                        "prompt_router",
                        tools=context_tools,
                        commands=context_commands,
                        prompt=prompt[:240],
                        cwd=cwd,
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
                        cwd=cwd,
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
                        cwd=cwd,
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
