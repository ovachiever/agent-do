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
import sys
import re

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

# Skip these entirely — no nudge needed
SKIP_PATTERNS = [
    r'(^|/)agent-do\b',
    r'(^|/)agent-(browse|browser|tui|ios|android|macos|manna|render|vercel|supabase|gcp)',
    r'^(ls|cat|head|tail|wc|grep|rg|find|which|pwd|cd|echo|printf)\b',
    r'^(mkdir|rm|cp|mv|touch|chmod|chown|ln|stat|file|diff)\b',
    r'^(git|npm|yarn|pnpm|pip|python|node|ruby|cargo|go|make|cmake|just)\b',
    r'^(brew|apt|yum|dnf|pacman)\b',
    r'^(jq|yq|sed|awk|sort|uniq|tee|xargs|tr|cut|paste)\b',
    r'^(curl\s.*localhost|curl\s.*127\.0\.0\.1|curl\s.*\[::1\])',
    r'--help\s*$',
    r'--version\s*$',
]

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
            sys.exit(0)

    # Check for agent-do matches
    for pattern, (tool, hint) in AGENT_DO_PATTERNS.items():
        if re.search(pattern, command, re.IGNORECASE):
            nudge = (
                f"FRIENDLY REMINDER: `{hint}` exists and is purpose-built for this. "
                f"It returns structured, snapshot-based output optimized for AI agents. "
                f"Run `{hint} --help` for commands. "
                f"Proceeding with your command is fine, but next time prefer agent-do."
            )
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": nudge
                }
            }
            print(json.dumps(output))
            sys.exit(0)

    sys.exit(0)

if __name__ == "__main__":
    main()
