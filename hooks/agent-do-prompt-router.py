#!/usr/bin/env python3
"""
UserPromptSubmit hook: Route prompts to appropriate agent-do tools.
Part of the agent-do hook trinity.

Analyzes user prompts and suggests specific agent-do tools when applicable.
Non-blocking — injects additionalContext only, never denies.
"""

import json
import re
import subprocess
import sys
from shutil import which
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

try:
    from registry import (
        load_registry,
        match_prompt_tools,
        get_default_command,
        get_recommended_entrypoints,
        get_tool_readiness,
    )
except ModuleNotFoundError:
    load_registry = None
    match_prompt_tools = None
    get_default_command = None
    get_recommended_entrypoints = None
    get_tool_readiness = None

try:
    from telemetry import record_nudge_event
except ModuleNotFoundError:
    record_nudge_event = None

try:
    from ai_router import call_json_model
except ModuleNotFoundError:
    call_json_model = None

# Keywords/phrases that map to agent-do tools
PROMPT_ROUTES = {
    'ios': {
        'patterns': [
            r'\b(ios|iphone|ipad)\s+(sim|simulator|emulator)\b',
            r'\bsimulator\b(?!.*android)',
            r'\bxcode\s*(sim|preview)?\b',
            r'\bmobile\s*app\b.*\b(ios|iphone|apple)\b',
            r'\btap\b.*\b(simulator|app)\b',
            r'\bswipe\b.*\b(simulator|app)\b',
            r'\blaunch\s*(app|application)\b.*\b(simulator|ios)\b',
            r'\bscreenshot\b.*\b(simulator|ios|iphone)\b',
            r'\bios\s+(app|build|deploy|test|run|debug)\b',
            r'\b(build|deploy|test|run)\s+(for|on)\s+ios\b',
        ],
        'suggestion': 'This looks like iOS Simulator work. Use: `agent-do ios --help` or `agent-do "your iOS task"`'
    },
    'android': {
        'patterns': [
            r'\bandroid\s+(emulator|device|app)\b',
            r'\bavd\b',
            r'\bpixel\s*(emulator)?\b',
            r'\badb\b',
            r'\bmobile\s*app\b.*\bandroid\b',
        ],
        'suggestion': 'This looks like Android Emulator work. Use: `agent-do android --help` or `agent-do "your Android task"`'
    },
    'macos': {
        'patterns': [
            r'\b(click|press)\s*(button|menu)\b.*\b(app|application|finder|safari|photoshop)\b',
            r'\bdesktop\s*(app|automation)\b',
            r'\b(macos|mac\s*os)\s*(app|automation)\b',
            r'\bui\s*element\b',
            r'\b(native|desktop)\s*app\b',
            r'\bfocus\s*(window|app)\b',
            r'\bmenu\s*item\b',
        ],
        'suggestion': 'This looks like desktop GUI automation. Use: `agent-do macos --help` or `agent-do "your GUI task"`'
    },
    'gcp': {
        'patterns': [
            r'\bgcp\s*(project|api|secret|service.account|oauth)\b',
            r'\bgoogle\s*cloud\b',
            r'\b(gcloud|googleapis)\b',
            r'\boauth\s*(client|credential|consent)\b.*\bgoogle\b',
        ],
        'suggestion': 'Use `agent-do gcp` for GCP operations (NOT gcloud CLI). Run: `agent-do gcp --help`'
    },
    'tui': {
        'patterns': [
            r'\binteractive\s*(cli|terminal|repl)\b',
            r'\b(vim|nvim|nano|htop|top)\b.*\b(run|open|use)\b',
            r'\bterminal\s*(app|ui)\b',
            r'\bcurses\b',
            r'\btui\b',
        ],
        'suggestion': 'This looks like terminal UI automation. Use: `agent-do tui --help` or `agent-do "your TUI task"`'
    },
    'browser': {
        'patterns': [
            r'\b(browse|navigate|open)\s*(website|url|page|web)\b',
            r'\bweb\s*(scrape|scraping|automation)\b',
            r'\bfill\s*(form|input)\b.*\bweb\b',
            r'\bclick\b.*\b(link|button)\b.*\bweb\b',
            r'\bselenium\b',
            r'\bplaywright\b',
            r'\bpuppeteer\b',
        ],
        'suggestion': 'This looks like browser automation. Use: `agent-do browse --help` or `agent-do browse open <url>`'
    },
    'db': {
        'patterns': [
            r'\b(database|db)\s*(query|select|insert|update|delete)\b',
            r'\bsql\s*(query|command)\b',
            r'\b(postgres|mysql|sqlite)\s*(query|connect)\b',
            r'\btable\s*(schema|structure)\b',
        ],
        'suggestion': 'This looks like database work. Use: `agent-do db --help` or `agent-do "your DB query"`'
    },
    'k8s': {
        'patterns': [
            r'\bkubernetes\b',
            r'\bk8s\b',
            r'\bkubectl\b',
            r'\bpods?\b.*\b(list|logs|exec|describe)\b',
            r'\bdeployment\b.*\b(scale|rollout)\b',
            r'\bhelm\b',
        ],
        'suggestion': 'This looks like Kubernetes work. Use: `agent-do k8s --help` or `agent-do "your k8s task"`'
    },
    'docker': {
        'patterns': [
            r'\bdocker\s*(container|image|compose|logs)\b',
            r'\bcontainer\s*(start|stop|logs|exec)\b',
        ],
        'suggestion': 'This looks like Docker work. Use: `agent-do docker --help` or `agent-do "your Docker task"`'
    },
    'slack': {
        'patterns': [
            r'\bslack\s*(message|post|send|notification)\b',
            r'\b(post|send)\s*(to|on)\s*slack\b',
            r'\b#\w+\b.*\bslack\b',
        ],
        'suggestion': 'This looks like Slack messaging. Use: `agent-do slack --help` or `agent-do "post X to #channel"`'
    },
    'email': {
        'patterns': [
            r'\b(send|compose|read)\s*email\b',
            r'\bemail\s*(to|from)\b',
            r'\b(check|read|open|search)\s*(my\s*)?mail\b',
            r'\binbox\b',
        ],
        'suggestion': 'This looks like email work. Use: `agent-do email --help` or `agent-do "your email task"`'
    },
    'image': {
        'patterns': [
            r'\b(resize|crop|convert|compress)\s*(image|photo|picture|png|jpg)\b',
            r'\bimage\s*(resize|crop|convert|compress|thumbnail)\b',
            r'\b(png|jpg|jpeg|gif|webp)\b.*\b(resize|crop|convert)\b',
        ],
        'suggestion': 'This looks like image processing. Use: `agent-do image --help` or `agent-do "your image task"`'
    },
    'video': {
        'patterns': [
            r'\b(convert|trim|merge|compress)\s*(video|mp4|mkv|mov)\b',
            r'\bvideo\s*(convert|trim|merge|compress|gif)\b',
            r'\bffmpeg\b.*\bvideo\b',
        ],
        'suggestion': 'This looks like video processing. Use: `agent-do video --help` or `agent-do "your video task"`'
    },
    'audio': {
        'patterns': [
            r'\b(convert|trim|transcribe)\s*(audio|mp3|wav)\b',
            r'\baudio\s*(convert|trim|transcribe|merge)\b',
            r'\btranscribe\b',
            r'\bwhisper\b',
        ],
        'suggestion': 'This looks like audio processing. Use: `agent-do audio --help` or `agent-do "your audio task"`'
    },
    'calendar': {
        'patterns': [
            r'\b(calendar|schedule|event|meeting)\s*(create|add|list|show)\b',
            r'\b(create|add|show)\s*(event|meeting|appointment)\b',
        ],
        'suggestion': 'This looks like calendar work. Use: `agent-do calendar --help` or `agent-do "your calendar task"`'
    },
    'cloud': {
        'patterns': [
            r'\b(aws|gcp|azure)\s*(s3|ec2|lambda|compute|storage)\b',
            r'\bcloud\s*(instance|bucket|function)\b',
        ],
        'suggestion': 'This looks like cloud operations. Use: `agent-do cloud --help` or `agent-do "your cloud task"`'
    },
    'vercel': {
        'patterns': [
            r'\bvercel\b',
            r'\bvercel\s*(deploy|project|domain|env|log|promotion)\b',
            r'\bdeploy\b.*\bvercel\b',
        ],
        'suggestion': 'Use `agent-do vercel` for Vercel operations (NOT the vercel CLI). Run: `agent-do vercel --help`'
    },
    'render': {
        'patterns': [
            r'\brender\.com\b',
            r'\brender\s*(service|deploy|web\s*service|database)\b',
            r'\bdeploy\b.*\brender\b',
        ],
        'suggestion': 'Use `agent-do render` for Render.com operations (NOT curl to the Render API). Run: `agent-do render --help`'
    },
    'supabase': {
        'patterns': [
            r'\bsupabase\b',
            r'\bsupabase\s*(project|database|function|auth|storage|migration)\b',
        ],
        'suggestion': 'Use `agent-do supabase` for Supabase operations (NOT the supabase CLI). Run: `agent-do supabase --help`'
    },
    'zpc': {
        'patterns': [
            r'\b(lesson|lessons)\s*(log|capture|record)\b',
            r'\b(decision|decisions)\s*(log|record|track)\b',
            r'\bproject\s*memory\b',
            r'\bpatterns?\s*(consolidat|harvest|extract)\b',
            r'\b\.zpc\b',
            r'\bzpc\b',
        ],
        'suggestion': 'This looks like project memory work. Use: `agent-do zpc --help` or `agent-do zpc status`'
    },
}

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


def analyze_prompt(prompt: str, skip_tools: set[str] | None = None) -> list[tuple[str, str]]:
    """Analyze prompt with the legacy route table."""
    prompt_lower = prompt.lower()
    matches = []
    skip_tools = skip_tools or set()

    for tool, config in PROMPT_ROUTES.items():
        if tool in skip_tools:
            continue
        for pattern in config['patterns']:
            if re.search(pattern, prompt_lower):
                matches.append((tool, config['suggestion']))
                break  # Only match each tool once

    return matches


def analyze_registry_prompt(prompt: str) -> list[tuple[str, str]]:
    """Analyze prompt using shared routing metadata from the registry."""
    if load_registry is None or match_prompt_tools is None:
        return []

    registry = load_registry()
    matches = match_prompt_tools(registry, prompt, limit=5)
    suggestions = []

    for match in matches:
        tool = match['tool']
        info = match['info']
        commands = list(info.get('commands', {}).keys())
        entrypoints = get_recommended_entrypoints(info) if get_recommended_entrypoints else []
        readiness = get_tool_readiness(info) if get_tool_readiness else {}

        primary = None
        if tool == "gh" and re.search(r"\b(?:awaiting|waiting)\b.*\breview\b|\breview\b.*\b(?:awaiting|waiting)\b", prompt.lower()):
            primary = "agent-do gh awaiting --owner <owner>"
        elif tool == "gh" and re.search(r"\b(?:need|needs|requested|review|reviewing|approve|merge|blocked|inbox)\b", prompt.lower()):
            primary = "agent-do gh inbox"
        else:
            command_hits = []
            prompt_lower = prompt.lower()
            for command in commands:
                variants = {command.lower(), command.lower().replace("-", " ")}
                if command.endswith("s"):
                    variants.add(command[:-1].lower())
                for variant in variants:
                    match = re.search(rf"(?<!\w){re.escape(variant)}(?!\w)", prompt_lower)
                    if match:
                        command_hits.append((match.start(), -len(variant), command))
                        break
            if command_hits:
                _pos, _length, command = sorted(command_hits)[0]
                primary = f"agent-do {tool} {command}"

        if primary is None and get_default_command is not None:
            default_command = get_default_command(info)
            if default_command:
                primary = f"agent-do {tool} {default_command}"

        if primary is None:
            primary = entrypoints[0] if entrypoints else f"agent-do {tool} --help"

        extra = entrypoints[1] if len(entrypoints) > 1 else None

        suggestion = f"Start with `{primary}`."
        if extra:
            suggestion += f" Next likely step: `{extra}`."

        fix = readiness.get('fix')
        note = readiness.get('note')
        if fix and note:
            suggestion += f" If setup is missing: `{fix}`. {note}"
        elif note:
            suggestion += f" {note}"

        suggestions.append((tool, suggestion))

    return suggestions


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


def ai_should_emit_coord_context(
    prompt: str,
    *,
    active_peers: list[dict],
    focus_goal: str,
    interrupts: list[dict],
    explicit: bool,
    local_work_signal: bool,
) -> bool | None:
    if call_json_model is None:
        return None

    interrupt_summaries = [
        {"kind": item.get("kind"), "summary": item.get("summary")}
        for item in interrupts[:3]
    ]
    peer_summaries = [
        {
            "agent": peer.get("alias") or peer.get("agent_id"),
            "goal": ((peer.get("focus") or {}).get("goal")) or "",
        }
        for peer in active_peers[:5]
    ]
    prompt_text = f"""Decide whether a UserPromptSubmit hook should show agent-do coordination context.

Show coord context only when it is useful now:
- yes for prompts asking the assistant to edit files, run tests, review code/PRs, commit, push, deploy, or coordinate with other agents
- yes for real coord interrupts that affect the requested work
- no for discussion, model choice, explanation, planning, or "tell me" questions where no work is starting yet

Input:
{json.dumps({
    "prompt": prompt,
    "explicit_coord_request": explicit,
    "local_work_signal": local_work_signal,
    "current_agent_has_focus": bool(focus_goal),
    "active_peers": peer_summaries,
    "interrupts": interrupt_summaries,
}, indent=2)}

Respond with JSON only:
{{
  "emit_coord_context": true,
  "reason": "short reason"
}}
"""
    decision = call_json_model(
        prompt_text,
        flag_name="AGENT_DO_HOOK_AI",
        system=(
            "You are a precise hook gate for coding-agent prompts. Return strict JSON only. "
            "Be engineering-ready, clear, and concise. Use the fewest words that preserve correctness; "
            "do not omit necessary operational detail."
        ),
    )
    if not isinstance(decision, dict):
        return None
    value = decision.get("emit_coord_context")
    return value if isinstance(value, bool) else None


def should_emit_coord_context(
    prompt: str,
    *,
    active_peers: list[dict],
    focus_goal: str,
    interrupts: list[dict],
    explicit: bool,
) -> bool:
    if explicit:
        return True
    if not active_peers and not interrupts:
        return False

    local_work_signal = prompt_looks_like_coord_work(prompt)
    if not local_work_signal and not interrupts:
        return False

    ai_decision = ai_should_emit_coord_context(
        prompt,
        active_peers=active_peers,
        focus_goal=focus_goal,
        interrupts=interrupts,
        explicit=explicit,
        local_work_signal=local_work_signal,
    )
    if ai_decision is not None:
        return ai_decision

    return local_work_signal


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


def load_coord_context(prompt: str, cwd: str | None) -> tuple[str, list[str]]:
    explicit = detect_coord_prompt(prompt)
    if not cwd:
        if not explicit:
            return "", []
        return (
            "## Coord Suggestion\n\n"
            "This sounds like multi-agent coordination. Start with:\n"
            "- `agent-do coord status`\n"
            "- `agent-do coord interrupts`\n"
            "- `agent-do coord focus set \"<goal>\" --path <path>`\n",
            ["coord"],
        )

    agent_do = resolve_agent_do_binary()
    if not agent_do:
        return "", []

    touched = subprocess.run(
        [agent_do, "coord", "touch", "--json"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if touched.returncode != 0 or not touched.stdout.strip():
        return "", []

    touch_payload = json.loads(touched.stdout)
    active_peers = touch_payload.get("active_peers", [])
    focus_goal = ((touch_payload.get("focus") or {}).get("goal")) or ""

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

    interrupts = interrupts_payload.get("interrupts", [])
    should_emit = should_emit_coord_context(
        prompt,
        active_peers=active_peers,
        focus_goal=focus_goal,
        interrupts=interrupts,
        explicit=explicit,
    )
    if not should_emit:
        return "", []

    if interrupts:
        subprocess.run(
            [agent_do, "coord", "interrupts", "--json", "--mark-seen", "--limit", "5"],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        lines = []
        for item in interrupts:
            prefix = "[new] " if item.get("new") else ""
            lines.append(f"- {prefix}{item.get('kind')}: {item.get('summary')}")
        context = (
            "## Coord Interrupts\n\n"
            "Relevant coordination interrupts are active in this repo:\n"
            f"{chr(10).join(lines)}\n\n"
            "Use `agent-do coord status`, `agent-do coord interrupts`, or `agent-do coord focus show`.\n"
        )
        return context, ["coord"]

    if active_peers and not focus_goal:
        peer_lines = []
        for peer in active_peers:
            label = peer.get("alias") or peer.get("agent_id")
            goal = ((peer.get("focus") or {}).get("goal")) or ""
            suffix = f" goal: {goal}" if goal else ""
            peer_lines.append(f"- {label}{suffix}")
        context = (
            "## Coord Focus Reminder\n\n"
            "Other active peers exist in this repo, and you have not declared focus yet.\n"
            f"{chr(10).join(peer_lines)}\n\n"
            "Set focus before overlapping work starts with "
            "`agent-do coord focus set \"<goal>\" --path <path> [--path <path> ...]`.\n"
        )
        return context, ["coord"]

    if explicit:
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

    shared_matches = analyze_registry_prompt(prompt)
    matches = shared_matches + analyze_prompt(prompt, skip_tools={tool for tool, _ in shared_matches})
    is_design = detect_frontend_design(prompt)

    needs_completion = needs_completion_check(prompt)
    coord_context, coord_tools = load_coord_context(prompt, cwd)

    if matches or is_design or needs_completion or coord_context:
        context = ""

        if matches:
            context += "## agent-do Tool Suggestion\n\nBased on your request, consider using agent-do tools:\n\n"
            for tool, suggestion in matches:
                context += f"**{tool}**: {suggestion}\n\n"
            context += "Reference: `agent-do suggest \"task\"` | `agent-do suggest --project` | `agent-do find <keyword>` | `agent-do --list` | `agent-do <tool> --help`\n"
            if record_nudge_event is not None:
                try:
                    record_nudge_event(
                        "prompt_tool_suggestion",
                        "prompt_router",
                        tools=[tool for tool, _ in matches],
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
