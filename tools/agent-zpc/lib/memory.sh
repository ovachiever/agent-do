#!/usr/bin/env bash
# lib/memory.sh — Learn and Decide commands
# Sourced by agent-zpc. Do not run directly.

cmd_learn() {
    ensure_zpc

    local context="" problem="" solution="" takeaway="" tags=""
    local positionals=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tags|-t) tags="$2"; shift 2 ;;
            --help|-h)
                echo "Usage: agent-zpc learn <context> <problem> <solution> <takeaway> --tags \"tag1,tag2\""
                return 0
                ;;
            *) positionals+=("$1"); shift ;;
        esac
    done

    # Assign positional args
    context="${positionals[0]:-}"
    problem="${positionals[1]:-}"
    solution="${positionals[2]:-}"
    takeaway="${positionals[3]:-}"

    # Validate required fields
    if [[ -z "$context" || -z "$problem" || -z "$solution" || -z "$takeaway" ]]; then
        die "Usage: agent-zpc learn <context> <problem> <solution> <takeaway> --tags \"tag1,tag2\""
    fi
    if [[ -z "$tags" ]]; then
        die "Tags required. Use --tags \"tag1,tag2\""
    fi

    local date_str
    date_str="$(today)"

    # Build JSON via python3
    local json_line
    json_line=$(python3 << 'PYTHON' - "$date_str" "$context" "$problem" "$solution" "$takeaway" "$tags"
import json, sys
entry = {
    "date": sys.argv[1],
    "context": sys.argv[2],
    "problem": sys.argv[3],
    "solution": sys.argv[4],
    "takeaway": sys.argv[5],
    "tags": [t.strip() for t in sys.argv[6].split(",") if t.strip()]
}
print(json.dumps(entry, ensure_ascii=False))
PYTHON
    )

    append_jsonl "$ZPC_MEMORY_DIR/lessons.jsonl" "$json_line" || return 1

    # Update global project index
    ensure_global
    local project_path
    project_path="$(dirname "$ZPC_DIR")"
    python3 << 'PYTHON' - "$ZPC_GLOBAL_DIR/project-index.jsonl" "$project_path" "$date_str"
import json, sys, os
index_file, project_path, date = sys.argv[1], sys.argv[2], sys.argv[3]
entry = {"project": project_path, "last_activity": date}
# Dedup: remove existing entry for this project, append fresh
lines = []
if os.path.exists(index_file):
    with open(index_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("project") != project_path:
                    lines.append(line)
            except:
                lines.append(line)
lines.append(json.dumps(entry))
with open(index_file, "w") as f:
    f.write("\n".join(lines) + "\n")
PYTHON

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_success "$json_line"
    else
        echo "Lesson captured: $takeaway (tags: $tags)"
    fi
}

cmd_decide() {
    ensure_zpc

    local decision="" options="" chosen="" rationale="" confidence="0.5" mode="lite" tags=""
    local positionals=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --options|-o) options="$2"; shift 2 ;;
            --chosen|-c) chosen="$2"; shift 2 ;;
            --rationale|-r) rationale="$2"; shift 2 ;;
            --confidence) confidence="$2"; shift 2 ;;
            --mode|-m) mode="$2"; shift 2 ;;
            --tags|-t) tags="$2"; shift 2 ;;
            --help|-h)
                echo "Usage: agent-zpc decide <problem> --options \"a,b,c\" --chosen a --rationale \"why\""
                return 0
                ;;
            *) positionals+=("$1"); shift ;;
        esac
    done

    decision="${positionals[0]:-}"

    if [[ -z "$decision" || -z "$options" || -z "$chosen" || -z "$rationale" ]]; then
        die "Usage: agent-zpc decide <problem> --options \"a,b,c\" --chosen X --rationale \"why\""
    fi

    local date_str
    date_str="$(today)"

    local json_line
    json_line=$(python3 << 'PYTHON' - "$date_str" "$decision" "$options" "$chosen" "$rationale" "$confidence" "$mode" "$tags"
import json, sys
date, decision, options_str, chosen, rationale, confidence, mode, tags_str = sys.argv[1:9]
entry = {
    "date": date,
    "decision": decision,
    "options": [o.strip() for o in options_str.split(",") if o.strip()],
    "chosen": chosen,
    "rationale": rationale,
    "confidence": float(confidence),
    "mode": mode
}
if tags_str:
    entry["tags"] = [t.strip() for t in tags_str.split(",") if t.strip()]
if mode == "full":
    entry["research"] = ""
    entry["evaluation"] = ""
    entry["confidence_justification"] = ""
print(json.dumps(entry, ensure_ascii=False))
PYTHON
    )

    append_jsonl "$ZPC_MEMORY_DIR/decisions.jsonl" "$json_line" || return 1

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_success "$json_line"
    else
        echo "Decision logged: $chosen (confidence: $confidence)"
    fi
}
