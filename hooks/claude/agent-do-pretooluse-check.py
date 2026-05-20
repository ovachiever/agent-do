#!/usr/bin/env python3
"""
PreToolUse hook: NUDGE about agent-do when raw CLI commands are detected.
Non-blocking — adds context reminder but lets the command through.
Part of the agent-do hook trinity (nudge mode).

To switch to BLOCKING mode, change the output from:
    "additionalContext": nudge
to:
    "permissionDecision": "deny",
    "reason": nudge
"""

import json
import os
import sys
import re
from pathlib import Path
from urllib.parse import urlparse

# File lives at <repo>/hooks/claude/agent-do-pretooluse-check.py, so the repo
# root is two parents up and lib/ is its sibling.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

try:
    from registry import load_registry, find_raw_cli_equivalent, get_tool_readiness
except ModuleNotFoundError:
    load_registry = None
    find_raw_cli_equivalent = None
    get_tool_readiness = None

try:
    from telemetry import record_hook_decision, record_nudge_event
except ModuleNotFoundError:
    record_hook_decision = None
    record_nudge_event = None

# Patterns that have agent-do equivalents — grouped by tool
AGENT_DO_PATTERNS = {
    # === Vercel ===
    r'\bvercel\b': ('vercel', 'agent-do vercel'),
    r'\bnpx\s+vercel\b': ('vercel', 'agent-do vercel'),
    r'\bcurl\b.*\bapi\.vercel\.com\b': ('vercel', 'agent-do vercel'),

    # === Render ===
    r'\brender\s+(services|deploys|deploy)\b': ('render', 'agent-do render'),
    r'\bcurl\b.*\bapi\.render\.com\b': ('render', 'agent-do render'),

    # === Supabase ===
    r'\bsupabase\b': ('supabase', 'agent-do supabase'),
    r'\bnpx\s+supabase\b': ('supabase', 'agent-do supabase'),
    r'\bcurl\b.*\bsupabase\.(co|com|io)\b': ('supabase', 'agent-do supabase'),

    # === Browser automation ===
    r'\bnpx\s+playwright\b': ('browse', 'agent-do browse'),
    r'\bplaywright\s+(test|codegen|install|show-report)\b': ('browse', 'agent-do browse'),
    r'\bpuppeteer\b': ('browse', 'agent-do browse'),
    r'\bselenium\b': ('browse', 'agent-do browse'),

    # === iOS Simulator ===
    r'\bxcrun\s+simctl\b': ('ios', 'agent-do ios'),
    r'\bsimctl\b': ('ios', 'agent-do ios'),

    # === Android Emulator ===
    r'\badb\s+(shell|install|uninstall|push|pull|logcat|devices)': ('android', 'agent-do android'),
    r'\bemulator\s': ('android', 'agent-do android'),

    # === Desktop GUI ===
    r'\bosascript\b': ('macos', 'agent-do macos'),
    r'\bautomator\b': ('macos', 'agent-do macos'),

    # === Google Cloud ===
    r'\bgcloud\s+(auth|projects|iam|secrets|run|functions|compute)\b': ('gcp', 'agent-do gcp'),
    r'\bcurl\b.*\bgoogleapis\.com\b': ('gcp', 'agent-do gcp'),

    # === Docker ===
    r'\bdocker\s+(ps|logs|exec|run|start|stop|compose)\b': ('docker', 'agent-do docker'),

    # === Kubernetes ===
    r'\bkubectl\s': ('k8s', 'agent-do k8s'),

    # === SSH ===
    r'\bssh\s+\S+@': ('ssh', 'agent-do ssh'),
    r'\bscp\s': ('ssh', 'agent-do ssh'),

    # === Database ===
    r'\bpsql\s': ('db', 'agent-do db'),
    r'\bmysql\s': ('db', 'agent-do db'),

    # === Cloud ===
    r'\baws\s+(s3|ec2|lambda|iam)\b': ('cloud', 'agent-do cloud'),
    r'\baz\s+(vm|storage|webapp)\b': ('cloud', 'agent-do cloud'),

    # === Image ===
    r'\b(convert|mogrify|identify)\s.*\.(png|jpg|jpeg|gif|webp)': ('image', 'agent-do image'),
    r'\bffmpeg\b.*\.(png|jpg|jpeg|gif)': ('image', 'agent-do image'),

    # === Video ===
    r'\bffmpeg\b.*\.(mp4|mkv|avi|mov|webm)': ('video', 'agent-do video'),

    # === Audio ===
    r'\bffmpeg\b.*\.(mp3|wav|ogg|flac|m4a)': ('audio', 'agent-do audio'),
    r'\bwhisper\b': ('audio', 'agent-do audio'),
}

DOCS_FETCH_PATTERN = re.compile(
    r"\bcurl\b.*\b(llms(?:-full)?\.txt|docs?|documentation|reference|raw\.githubusercontent\.com|github\.com/.+/(?:blob|raw)/)",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+")

# Skip these entirely — no nudge needed
SKIP_PATTERNS = [
    r'(^|/)agent-do\b',
    r'(^|/)agent-(browse|browser|tui|ios|android|macos|manna|render|vercel|supabase|gcp|zpc)',
    r'^(ls|cat|head|tail|wc|grep|rg|find|which|pwd|cd|echo|printf)\b',
    r'^(mkdir|rm|cp|mv|touch|chmod|chown|ln|stat|file|diff)\b',
    r'^(git|npm|yarn|pnpm|pip|python|node|ruby|cargo|go|make|cmake|just)\b',
    r'^(brew|apt|yum|dnf|pacman)\b',
    r'^(jq|yq|sed|awk|sort|uniq|tee|xargs|tr|cut|paste)\b',
    r'^(curl\s.*localhost|curl\s.*127\.0\.0\.1|curl\s.*\[::1\])',
    r'--help\s*$',
    r'--version\s*$',
]


# Codex now supports `hookSpecificOutput.additionalContext` on PreToolUse
# (May 2026 hooks release). Previous versions of this hook suppressed output
# when AGENT_DO_HOOK_RUNTIME=codex because Codex rejected the field; that
# suppression is now obsolete. The hook emits the nudge regardless of
# runtime. The `is_codex_runtime` helper is preserved for any downstream
# callers that still want to branch on runtime for other reasons.
def is_codex_runtime() -> bool:
    runtime = os.environ.get("AGENT_DO_HOOK_RUNTIME", "").strip().lower()
    if runtime == "codex":
        return True
    if runtime in {"claude", "test"}:
        return False
    return any(
        os.environ.get(key)
        for key in (
            "CODEX_CI",
            "CODEX_THREAD_ID",
            "CODEX_MANAGED_BY_NPM",
        )
    )


def emit_context(nudge: str) -> None:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": nudge,
        }
    }
    print(json.dumps(output))


def context_fetch_command_for_raw_docs(command: str) -> str:
    match = URL_PATTERN.search(command)
    if not match:
        return "agent-do context fetch <url>"

    url = match.group(0)
    parsed = urlparse(url)
    if re.search(r"/llms(?:-full)?\.txt$", parsed.path, re.IGNORECASE) and parsed.netloc:
        return f"agent-do context fetch-llms {parsed.netloc}"
    return f"agent-do context fetch {url}"


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    if input_data.get("tool_name") != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "").strip()
    if not command:
        sys.exit(0)

    # Skip known-safe commands
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            if record_hook_decision is not None:
                try:
                    record_hook_decision("PreToolUse", "pretool", "suppress", reason="skip_pattern")
                except Exception:
                    pass
            sys.exit(0)

    # Check for agent-do matches
    if DOCS_FETCH_PATTERN.search(command):
        replacement = context_fetch_command_for_raw_docs(command)
        nudge = (
            "HARD NUDGE: `agent-do context` is the native path for fetching and indexing docs/reference content. "
            f"Closest replacement: `{replacement}`. "
            "It stores provenance and freshness metadata so later agents can use `agent-do context retrieve ... --fresh` instead of ad hoc downloaded files. "
            "Proceeding with your raw command is allowed, but agent-do context should be the default choice here."
        )
        if record_hook_decision is not None:
            try:
                record_hook_decision(
                    "PreToolUse",
                    "pretool",
                    "emit",
                    tools=["context"],
                    commands=[replacement],
                    reason="raw_docs_fetch",
                )
            except Exception:
                pass
        if record_nudge_event is not None:
            try:
                record_nudge_event(
                    "pretool_context_fetch_nudge",
                    "pretool",
                    tool="context",
                    tools=["context"],
                    commands=[replacement],
                    replacement=replacement,
                    command=command[:240],
                )
            except Exception:
                pass
        emit_context(nudge)
        sys.exit(0)

    if load_registry is not None and find_raw_cli_equivalent is not None:
        registry = load_registry()
        shared_match = find_raw_cli_equivalent(registry, command)
        if shared_match:
            readiness = get_tool_readiness(shared_match['info']) if get_tool_readiness else {}
            replacement = shared_match['replacement']
            example = shared_match.get('example') or replacement
            reason = shared_match.get('reason') or "agent-do already exposes this workflow with structured output."
            fix = readiness.get('fix')
            note = readiness.get('note')

            nudge = (
                f"HARD NUDGE: `{replacement}` is the native agent-do path for this command family. "
                f"Closest replacement: `{example}`. "
                f"{reason} "
            )
            if fix and note:
                nudge += f"If setup is missing: `{fix}`. {note} "
            elif note:
                nudge += f"{note} "
            nudge += "Proceeding with your raw command is allowed, but agent-do should be the default choice here."

            if record_hook_decision is not None:
                try:
                    record_hook_decision(
                        "PreToolUse",
                        "pretool",
                        "emit",
                        tools=[shared_match["tool"]],
                        commands=[replacement, example],
                        reason="registry_raw_cli_equivalent",
                    )
                except Exception:
                    pass
            if record_nudge_event is not None:
                try:
                    record_nudge_event(
                        "pretool_hard_nudge",
                        "pretool",
                        tool=shared_match["tool"],
                        tools=[shared_match["tool"]],
                        commands=[replacement, example],
                        replacement=replacement,
                        command=command[:240],
                    )
                except Exception:
                    pass
            emit_context(nudge)
            sys.exit(0)

    for pattern, (tool, hint) in AGENT_DO_PATTERNS.items():
        if re.search(pattern, command, re.IGNORECASE):
            nudge = (
                f"FRIENDLY REMINDER: `{hint}` exists and is purpose-built for this. "
                f"It returns structured, snapshot-based output optimized for AI agents. "
                f"Run `{hint} --help` for commands. "
                f"Proceeding with your command is fine, but next time prefer agent-do."
            )
            if record_hook_decision is not None:
                try:
                    record_hook_decision(
                        "PreToolUse",
                        "pretool",
                        "emit",
                        tools=[tool],
                        commands=[hint],
                        reason="legacy_pattern_match",
                    )
                except Exception:
                    pass
            if record_nudge_event is not None:
                try:
                    record_nudge_event(
                        "pretool_legacy_nudge",
                        "pretool",
                        tool=tool,
                        tools=[tool],
                        commands=[hint],
                        replacement=hint,
                        command=command[:240],
                    )
                except Exception:
                    pass
            emit_context(nudge)
            sys.exit(0)

    if record_hook_decision is not None:
        try:
            record_hook_decision("PreToolUse", "pretool", "suppress", reason="no_agent_do_match")
        except Exception:
            pass
    sys.exit(0)

if __name__ == "__main__":
    main()
