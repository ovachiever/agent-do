#!/usr/bin/env python3
"""
UserPromptSubmit hook: Route prompts to appropriate agent-do tools.
Part of the agent-do hook trinity.

Analyzes user prompts and suggests specific agent-do tools when applicable.
Non-blocking — injects additionalContext only, never denies.
"""

import json
import sys
import re

# Keywords/phrases that map to agent-do tools
PROMPT_ROUTES = {
    'ios': {
        'patterns': [
            r'\b(ios|iphone|ipad)\s*(sim|simulator|emulator)?\b',
            r'\bsimulator\b(?!.*android)',
            r'\bxcode\s*(sim|preview)?\b',
            r'\bmobile\s*app\b.*\b(ios|iphone|apple)\b',
            r'\btap\b.*\b(simulator|app)\b',
            r'\bswipe\b.*\b(simulator|app)\b',
            r'\blaunch\s*(app|application)\b.*\b(simulator|ios)\b',
            r'\bscreenshot\b.*\b(simulator|ios|iphone)\b',
        ],
        'suggestion': 'This looks like iOS Simulator work. Use: `agent-do ios --help` or `agent-do "your iOS task"`'
    },
    'android': {
        'patterns': [
            r'\bandroid\s*(emulator|device|app)?\b',
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
}

def analyze_prompt(prompt: str) -> list[tuple[str, str]]:
    """Analyze prompt and return list of (tool, suggestion) tuples."""
    prompt_lower = prompt.lower()
    matches = []

    for tool, config in PROMPT_ROUTES.items():
        for pattern in config['patterns']:
            if re.search(pattern, prompt_lower):
                matches.append((tool, config['suggestion']))
                break  # Only match each tool once

    return matches

def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    prompt = input_data.get("prompt", "")
    if not prompt:
        sys.exit(0)

    matches = analyze_prompt(prompt)

    if matches:
        context = "## agent-do Tool Suggestion\n\nBased on your request, consider using agent-do tools:\n\n"
        for tool, suggestion in matches:
            context += f"**{tool}**: {suggestion}\n\n"
        context += "Reference: `agent-do --list` (all tools) | `agent-do <tool> --help` (per-tool)\n"

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
