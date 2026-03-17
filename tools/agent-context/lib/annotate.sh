#!/usr/bin/env bash
# lib/annotate.sh — Annotations and feedback for agent-context
# Sourced by agent-context entry point. Do not run directly.

cmd_annotate() {
    local pkg_id="" note="" clear=false list_all=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --clear) clear=true; shift ;;
            --list) list_all=true; shift ;;
            *)
                if [[ -z "$pkg_id" ]]; then pkg_id="$1"
                elif [[ -z "$note" ]]; then note="$1"
                fi
                shift
                ;;
        esac
    done

    ensure_init
    local annotations_file="$CONTEXT_HOME/annotations.jsonl"

    if [[ "$list_all" == "true" ]]; then
        _annotate_list
        return
    fi

    [[ -n "$pkg_id" ]] || die "Usage: agent-context annotate <id> <note> | --clear | --list"

    if [[ "$clear" == "true" ]]; then
        # Remove all annotations for this package
        python3 -c "
import json, sys, os
path = sys.argv[1]
pkg = sys.argv[2]
if not os.path.exists(path): sys.exit(0)
with open(path) as f:
    lines = f.readlines()
with open(path, 'w') as f:
    for line in lines:
        try:
            e = json.loads(line)
            if e.get('package') != pkg:
                f.write(line)
        except:
            f.write(line)
" "$annotations_file" "$pkg_id"

        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            json_success "Cleared annotations for $pkg_id"
        else
            echo "Cleared annotations for $pkg_id"
        fi
        return
    fi

    if [[ -z "$note" ]]; then
        # Show annotations for this package
        python3 -c "
import json, sys, os
path = sys.argv[1]
pkg = sys.argv[2]
fmt = sys.argv[3]
if not os.path.exists(path):
    if fmt == 'json':
        print(json.dumps({'success': True, 'annotations': []}))
    else:
        print('No annotations.')
    sys.exit(0)
notes = []
with open(path) as f:
    for line in f:
        try:
            e = json.loads(line)
            if e.get('package') == pkg:
                notes.append(e)
        except:
            pass
if fmt == 'json':
    print(json.dumps({'success': True, 'annotations': notes}, indent=2))
else:
    if not notes:
        print(f'No annotations for {pkg}.')
    else:
        for n in notes:
            print(f\"  [{n.get('created','')}] {n.get('note','')}\")
" "$annotations_file" "$pkg_id" "${OUTPUT_FORMAT:-text}"
        return
    fi

    # Add annotation
    local json_line
    json_line=$(python3 -c "
import json, sys
from datetime import datetime, timezone
entry = {
    'package': sys.argv[1],
    'note': sys.argv[2],
    'created': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
}
print(json.dumps(entry, ensure_ascii=False))
" "$pkg_id" "$note")

    append_jsonl "$annotations_file" "$json_line"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_success "Annotated $pkg_id"
    else
        echo "Annotated: $pkg_id"
        echo "  $note"
    fi
}

_annotate_list() {
    local annotations_file="$CONTEXT_HOME/annotations.jsonl"

    python3 -c "
import json, sys, os
path = sys.argv[1]
fmt = sys.argv[2]
if not os.path.exists(path) or os.path.getsize(path) == 0:
    if fmt == 'json':
        print(json.dumps({'success': True, 'annotations': []}))
    else:
        print('No annotations.')
    sys.exit(0)
notes = []
with open(path) as f:
    for line in f:
        try:
            notes.append(json.loads(line))
        except:
            pass
if fmt == 'json':
    print(json.dumps({'success': True, 'count': len(notes), 'annotations': notes}, indent=2))
else:
    if not notes:
        print('No annotations.')
    else:
        # Group by package
        by_pkg = {}
        for n in notes:
            pkg = n.get('package', '?')
            by_pkg.setdefault(pkg, []).append(n)
        for pkg, pkg_notes in sorted(by_pkg.items()):
            print(f'{pkg}:')
            for n in pkg_notes:
                print(f\"  [{n.get('created','')}] {n.get('note','')}\")
            print()
" "$annotations_file" "${OUTPUT_FORMAT:-text}"
}

cmd_feedback() {
    local pkg_id="" rating="" reason=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            up|down) rating="$1"; shift ;;
            *)
                if [[ -z "$pkg_id" ]]; then pkg_id="$1"
                elif [[ -n "$rating" && -z "$reason" ]]; then reason="$1"
                fi
                shift
                ;;
        esac
    done

    [[ -n "$pkg_id" && -n "$rating" ]] || die "Usage: agent-context feedback <id> up|down [reason]"
    ensure_init

    local feedback_file="$CONTEXT_HOME/feedback.jsonl"
    local json_line
    json_line=$(python3 -c "
import json, sys
from datetime import datetime, timezone
entry = {
    'package': sys.argv[1],
    'rating': sys.argv[2],
    'reason': sys.argv[3] if sys.argv[3] else None,
    'timestamp': datetime.now(timezone.utc).isoformat(),
}
# Remove None values
entry = {k: v for k, v in entry.items() if v is not None}
print(json.dumps(entry, ensure_ascii=False))
" "$pkg_id" "$rating" "$reason")

    append_jsonl "$feedback_file" "$json_line"

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_success "Feedback recorded: $pkg_id $rating"
    else
        echo "Feedback: $rating for $pkg_id"
        [[ -n "$reason" ]] && echo "  Reason: $reason" || true
    fi
}
