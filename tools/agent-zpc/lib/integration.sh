#!/usr/bin/env bash
# lib/integration.sh — Inject, Init, Status, Profile commands
# Sourced by agent-zpc. Do not run directly.

cmd_inject() {
    ensure_zpc

    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    local decisions_file="$ZPC_MEMORY_DIR/decisions.jsonl"
    local patterns_file="$ZPC_MEMORY_DIR/patterns.md"
    local profile_file="$ZPC_MEMORY_DIR/profile.md"

    local lesson_count decision_count
    lesson_count=$(count_lines "$lessons_file")
    decision_count=$(count_lines "$decisions_file")

    local context=""

    # Section 1: Protocol
    context+="--- ZPC Agent Protocol (MANDATORY) ---\n"
    context+="BEFORE writing code: check Established Patterns below. Note which apply.\n"
    context+="DURING work: use 'agent-do zpc learn' to capture lessons.\n"
    context+="  EXACT format is handled by the tool. Usage:\n"
    context+="  agent-do zpc learn \"context\" \"problem\" \"solution\" \"takeaway\" --tags \"tag1,tag2\"\n"
    context+="BEFORE reporting completion:\n"
    context+="  Log EVERY error-resolution pair as a lesson.\n"
    context+="  Include in completion message: \"Lessons logged: N (new) | Decisions logged: N (new)\"\n"
    context+="\n"

    # Section 2: Profile
    if [[ -f "$profile_file" && -s "$profile_file" ]]; then
        context+="--- Project Profile ---\n"
        context+="$(cat "$profile_file")\n\n"
    fi

    # Section 3: Patterns
    if [[ -f "$patterns_file" && -s "$patterns_file" ]]; then
        context+="--- Established Patterns (follow these) ---\n"
        context+="$(cat "$patterns_file")\n\n"
    fi

    # Section 4: Recent lessons
    context+="--- Recent Lessons (newest last) ---\n"
    if [[ -f "$lessons_file" && -s "$lessons_file" ]]; then
        context+="$(tail -n 20 "$lessons_file")\n"
    else
        context+="(none)\n"
    fi
    context+="\n"

    # Section 5: Decisions
    context+="--- Settled Decisions (do not re-derive) ---\n"
    if [[ -f "$decisions_file" && -s "$decisions_file" ]]; then
        context+="$(python3 << 'PYTHON' - "$decisions_file"
import json, sys, os
decisions_file = sys.argv[1]
if os.path.exists(decisions_file):
    with open(decisions_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                date = obj.get("date", "?")
                chosen = obj.get("chosen", "?")
                rationale = obj.get("rationale", "")
                print(f"[{date}] {chosen}: {rationale}")
            except:
                pass
PYTHON
)\n"
    else
        context+="(none)\n"
    fi
    context+="\n"

    # Section 6: Baseline counts
    context+="--- Baseline Counts (your starting point) ---\n"
    context+="lessons.jsonl: ${lesson_count} entries | decisions.jsonl: ${decision_count} entries\n"
    context+="Only count entries YOU append as 'new'. Do not count pre-existing entries.\n"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        # Claude Code additionalContext format
        python3 << 'PYTHON' - "$context"
import json, sys
ctx = sys.argv[1]
print(json.dumps({"additionalContext": ctx}))
PYTHON
    else
        printf '%b' "$context"
    fi
}

cmd_init() {
    local platform="" force=false
    local positionals=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --platform|-p) platform="$2"; shift 2 ;;
            --force|-f) force=true; shift ;;
            --help|-h)
                echo "Usage: agent-zpc init [--platform claude|cursor|codex|generic] [--force]"
                return 0
                ;;
            *) positionals+=("$1"); shift ;;
        esac
    done

    local project_dir="$PWD"

    # Create directories
    mkdir -p "$project_dir/.zpc/memory"
    mkdir -p "$project_dir/.zpc/team"
    mkdir -p "$project_dir/.zpc/.state"

    local created=()

    # Create data files (skip if exists to preserve memory)
    for f in lessons.jsonl decisions.jsonl; do
        if [[ ! -f "$project_dir/.zpc/memory/$f" ]]; then
            touch "$project_dir/.zpc/memory/$f"
            created+=("$f")
        fi
    done

    # Default patterns.md
    if [[ ! -f "$project_dir/.zpc/memory/patterns.md" ]]; then
        printf '# Patterns\n\nNo patterns yet. Run `agent-do zpc harvest` after accumulating 3+ lessons with shared tags.\n' \
            > "$project_dir/.zpc/memory/patterns.md"
        created+=("patterns.md")
    fi

    # Auto-detect stack and write profile
    if [[ ! -f "$project_dir/.zpc/memory/profile.md" ]] || [[ "$force" == "true" ]]; then
        local stack
        stack=$(_detect_stack "$project_dir")
        printf '# Project Profile\n\n## Stack\n%s\n\n## Architecture\n(not yet documented)\n\n## Testing\n(not yet documented)\n\n## Conventions\n(not yet documented)\n' \
            "$stack" > "$project_dir/.zpc/memory/profile.md"
        created+=("profile.md")
    fi

    # Add .zpc/ to .gitignore (but NOT .zpc/team/)
    if [[ -f "$project_dir/.gitignore" ]]; then
        if ! grep -qF ".zpc/" "$project_dir/.gitignore" 2>/dev/null; then
            printf '\n# ZPC memory (local, git-ignored)\n.zpc/\n!.zpc/team/\n' >> "$project_dir/.gitignore"
        fi
    else
        printf '# ZPC memory (local, git-ignored)\n.zpc/\n!.zpc/team/\n' > "$project_dir/.gitignore"
    fi

    # Auto-detect platform if not specified
    if [[ -z "$platform" ]]; then
        if [[ -d "$project_dir/.claude" ]]; then
            platform="claude"
        elif [[ -f "$project_dir/.cursorrules" ]]; then
            platform="cursor"
        elif [[ -f "$project_dir/AGENTS.md" ]]; then
            platform="codex"
        else
            platform="generic"
        fi
    fi

    # Generate platform instruction file
    local template_dir="$SCRIPT_DIR/templates"
    local instruction_file="" template_file=""

    case "$platform" in
        claude)   instruction_file="CLAUDE.md";          template_file="$template_dir/claude.md.tmpl" ;;
        cursor)   instruction_file=".cursorrules";       template_file="$template_dir/cursor.rules.tmpl" ;;
        codex)    instruction_file="AGENTS.md";          template_file="$template_dir/agents.md.tmpl" ;;
        generic)  instruction_file="ZPC-INSTRUCTIONS.md"; template_file="$template_dir/generic.md.tmpl" ;;
    esac

    if [[ -n "$template_file" && -f "$template_file" ]]; then
        local stack_info
        stack_info=$(_detect_stack "$project_dir")

        if [[ ! -f "$project_dir/$instruction_file" ]] || [[ "$force" == "true" ]]; then
            sed -e "s|{{PROJECT_PATH}}|$project_dir|g" \
                -e "s|{{STACK}}|$stack_info|g" \
                "$template_file" > "$project_dir/$instruction_file"
            created+=("$instruction_file")
        elif ! grep -qiF "zpc" "$project_dir/$instruction_file" 2>/dev/null; then
            # Existing file without ZPC — add import
            mkdir -p "$project_dir/.zpc"
            sed -e "s|{{PROJECT_PATH}}|$project_dir|g" \
                -e "s|{{STACK}}|$stack_info|g" \
                "$template_file" > "$project_dir/.zpc/zpc-brain.md"
            printf '\n@.zpc/zpc-brain.md\n' >> "$project_dir/$instruction_file"
            created+=("zpc-brain.md (imported)")
        fi
    fi

    # Update global project index
    ZPC_GLOBAL_DIR="${AGENT_DO_HOME:-$HOME/.agent-do}/zpc"
    ensure_global
    python3 << 'PYTHON' - "$ZPC_GLOBAL_DIR/project-index.jsonl" "$project_dir"
import json, sys, os
from datetime import datetime
index_file, project = sys.argv[1], sys.argv[2]
entry = {"project": project, "initialized": datetime.now().strftime("%Y-%m-%d"), "last_activity": datetime.now().strftime("%Y-%m-%d")}
lines = []
if os.path.exists(index_file):
    with open(index_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("project") != project:
                    lines.append(line)
            except:
                lines.append(line)
lines.append(json.dumps(entry))
with open(index_file, "w") as f:
    f.write("\n".join(lines) + "\n")
PYTHON

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        python3 << 'PYTHON' - "${created[*]}"
import json, sys
files = sys.argv[1].split()
print(json.dumps({"success": True, "result": {"created": files, "platform": "'"$platform"'"}}))
PYTHON
    else
        echo "ZPC initialized in $project_dir"
        echo "  Platform: $platform"
        if [[ ${#created[@]} -gt 0 ]]; then
            echo "  Created: ${created[*]}"
        fi
        echo ""
        echo "Start capturing lessons: agent-do zpc learn ..."
    fi
}

_detect_stack() {
    local dir="$1"
    local stack=""

    if [[ -f "$dir/package.json" ]]; then
        stack="Node.js"
        [[ -f "$dir/tsconfig.json" ]] && stack="TypeScript / Node.js"
        grep -q '"react"' "$dir/package.json" 2>/dev/null && stack="$stack + React"
        grep -q '"next"' "$dir/package.json" 2>/dev/null && stack="$stack (Next.js)"
        grep -q '"vue"' "$dir/package.json" 2>/dev/null && stack="$stack + Vue"
    elif [[ -f "$dir/tsconfig.json" ]]; then
        stack="TypeScript"
    elif [[ -f "$dir/pyproject.toml" ]]; then
        stack="Python"
        grep -q "fastapi" "$dir/pyproject.toml" 2>/dev/null && stack="$stack + FastAPI"
        grep -q "django" "$dir/pyproject.toml" 2>/dev/null && stack="$stack + Django"
        grep -q "flask" "$dir/pyproject.toml" 2>/dev/null && stack="$stack + Flask"
    elif [[ -f "$dir/requirements.txt" ]]; then
        stack="Python"
    elif [[ -f "$dir/Cargo.toml" ]]; then
        stack="Rust"
    elif [[ -f "$dir/go.mod" ]]; then
        stack="Go"
    elif [[ -f "$dir/pubspec.yaml" ]]; then
        stack="Flutter / Dart"
    elif [[ -f "$dir/Gemfile" ]]; then
        stack="Ruby"
    else
        stack="Unknown stack"
    fi

    echo "$stack"
}

cmd_status() {
    ensure_zpc

    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    local decisions_file="$ZPC_MEMORY_DIR/decisions.jsonl"
    local patterns_file="$ZPC_MEMORY_DIR/patterns.md"
    local harvest_log="$ZPC_STATE_DIR/harvest-log.jsonl"
    local team_lessons="$ZPC_TEAM_DIR/shared-lessons.jsonl"

    local project_path
    project_path="$(dirname "$ZPC_DIR")"
    local lesson_count decision_count pattern_count team_count
    lesson_count=$(count_lines "$lessons_file")
    decision_count=$(count_lines "$decisions_file")
    pattern_count=$(grep -c "^## " "$patterns_file" 2>/dev/null) || pattern_count=0
    team_count=$(count_lines "$team_lessons")

    # Format issues + consolidation gaps via python
    local health
    health=$(python3 << 'PYTHON' - "$lessons_file" "$patterns_file"
import json, sys, os, re
from collections import Counter

lessons_file, patterns_file = sys.argv[1], sys.argv[2]

# Format issues
issues = 0
if os.path.exists(lessons_file):
    with open(lessons_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                required = ["date", "context", "problem", "solution", "takeaway", "tags"]
                if any(k not in obj for k in required) or not isinstance(obj.get("tags"), list):
                    issues += 1
            except:
                issues += 1

# Consolidation gaps
pattern_tags = set()
if os.path.exists(patterns_file):
    with open(patterns_file) as f:
        for line in f:
            m = re.match(r"^## (.+)$", line.strip())
            if m:
                pattern_tags.add(m.group(1).strip())

tag_counter = Counter()
if os.path.exists(lessons_file):
    with open(lessons_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                for tag in obj.get("tags", []):
                    if isinstance(tag, str):
                        tag_counter[tag] += 1
            except:
                pass

gaps = sum(1 for tag, count in tag_counter.items() if count >= 3 and tag not in pattern_tags)

print(json.dumps({"format_issues": issues, "consolidation_gaps": gaps}))
PYTHON
    )

    local format_issues gaps last_harvest global_exists
    format_issues=$(echo "$health" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['format_issues'])")
    gaps=$(echo "$health" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['consolidation_gaps'])")

    last_harvest="never"
    if [[ -f "$harvest_log" && -s "$harvest_log" ]]; then
        last_harvest=$(tail -1 "$harvest_log" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('date','unknown'))" 2>/dev/null || echo "unknown")
    fi

    global_exists="false"
    [[ -d "$ZPC_GLOBAL_DIR" ]] && global_exists="true"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        snapshot_begin "zpc"
        snapshot_field "project" "$project_path"
        snapshot_num_field "lessons" "$lesson_count"
        snapshot_num_field "decisions" "$decision_count"
        snapshot_num_field "patterns" "$pattern_count"
        snapshot_num_field "team_lessons" "$team_count"
        snapshot_num_field "format_issues" "$format_issues"
        snapshot_num_field "consolidation_gaps" "$gaps"
        snapshot_field "last_harvest" "$last_harvest"
        snapshot_bool_field "global_memory" "$global_exists"
        snapshot_end
    else
        echo "ZPC STATUS — $project_path"
        echo "  Lessons:           $lesson_count"
        echo "  Decisions:         $decision_count"
        echo "  Patterns:          $pattern_count"
        echo "  Team lessons:      $team_count"
        echo "  Format issues:     $format_issues"
        echo "  Consolidation gaps: $gaps"
        echo "  Last harvest:      $last_harvest"
    fi
}

cmd_profile() {
    ensure_zpc

    local subcmd="${1:-show}"
    shift 2>/dev/null || true

    local profile_file="$ZPC_MEMORY_DIR/profile.md"

    case "$subcmd" in
        show)
            if [[ ! -f "$profile_file" ]]; then
                echo "No profile found. Run 'agent-do zpc init' first."
                return 0
            fi
            if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
                local content
                content=$(<"$profile_file")
                json_success "$content"
            else
                cat "$profile_file"
            fi
            ;;
        update)
            local section="${1:-}"
            local content="${2:-}"
            if [[ -z "$section" || -z "$content" ]]; then
                die "Usage: agent-zpc profile update <section> <content>"
            fi
            python3 << 'PYTHON' - "$profile_file" "$section" "$content"
import sys, os, re

profile_file, section, new_content = sys.argv[1], sys.argv[2], sys.argv[3]

if not os.path.exists(profile_file):
    with open(profile_file, "w") as f:
        f.write(f"# Project Profile\n\n## {section}\n{new_content}\n")
    print(f"Created profile with section: {section}")
    sys.exit(0)

with open(profile_file) as f:
    lines = f.readlines()

# Find and replace section content
new_lines = []
in_section = False
replaced = False
for line in lines:
    if re.match(rf"^## {re.escape(section)}\s*$", line.strip()):
        new_lines.append(line)
        new_lines.append(new_content + "\n\n")
        in_section = True
        replaced = True
        continue
    if in_section:
        if line.startswith("## "):
            in_section = False
            new_lines.append(line)
        # Skip old content
        continue
    new_lines.append(line)

if not replaced:
    new_lines.append(f"\n## {section}\n{new_content}\n")

with open(profile_file, "w") as f:
    f.writelines(new_lines)

print(f"Updated section: {section}")
PYTHON
            ;;
        detect)
            local project_dir
            project_dir="$(dirname "$ZPC_DIR")"
            local stack
            stack=$(_detect_stack "$project_dir")
            # Update just the Stack section
            cmd_profile update "Stack" "$stack"
            ;;
        *)
            die "Unknown profile subcommand: $subcmd. Use: show, update, detect"
            ;;
    esac
}
