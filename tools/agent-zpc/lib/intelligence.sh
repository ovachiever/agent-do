#!/usr/bin/env bash
# lib/intelligence.sh — Harvest, Query, Patterns, Promote commands
# Sourced by agent-zpc. Do not run directly.

cmd_harvest() {
    ensure_zpc
    mkdir -p "$ZPC_STATE_DIR"

    local auto=false dry_run=false since=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --auto) auto=true; shift ;;
            --dry-run) dry_run=true; shift ;;
            --since) since="$2"; shift 2 ;;
            --help|-h)
                echo "Usage: agent-zpc harvest [--auto] [--dry-run] [--since last]"
                return 0
                ;;
            *) shift ;;
        esac
    done

    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    local decisions_file="$ZPC_MEMORY_DIR/decisions.jsonl"
    local patterns_file="$ZPC_MEMORY_DIR/patterns.md"
    local harvest_log="$ZPC_STATE_DIR/harvest-log.jsonl"

    # Determine since-line for incremental scan
    local since_line=0
    if [[ "$since" == "last" && -f "$harvest_log" && -s "$harvest_log" ]]; then
        since_line=$(python3 << 'PYTHON' - "$harvest_log"
import json, sys
last = ""
with open(sys.argv[1]) as f:
    for line in f:
        line = line.strip()
        if line:
            last = line
if last:
    try:
        obj = json.loads(last)
        print(obj.get("lesson_count", 0))
    except:
        print(0)
else:
    print(0)
PYTHON
        )
    fi

    # Run harvest via python
    local result
    result=$(python3 << 'PYTHON' - "$lessons_file" "$decisions_file" "$patterns_file" "$since_line" "$auto" "$dry_run"
import json, sys, os, re
from collections import Counter

lessons_file = sys.argv[1]
decisions_file = sys.argv[2]
patterns_file = sys.argv[3]
since_line = int(sys.argv[4])
auto_mode = sys.argv[5] == "true"
dry_run = sys.argv[6] == "true"

# Read lessons
lessons = []
format_issues = []
if os.path.exists(lessons_file):
    with open(lessons_file) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                lessons.append((i, obj))
                required = ["date", "context", "problem", "solution", "takeaway", "tags"]
                missing = [k for k in required if k not in obj]
                if missing:
                    format_issues.append({"line": i, "missing": missing})
                elif not isinstance(obj.get("tags"), list):
                    format_issues.append({"line": i, "missing": ["tags (not array)"]})
            except json.JSONDecodeError:
                format_issues.append({"line": i, "missing": ["INVALID JSON"]})

# Count decisions
decision_count = 0
if os.path.exists(decisions_file):
    with open(decisions_file) as f:
        decision_count = sum(1 for line in f if line.strip())

# Count patterns
pattern_count = 0
pattern_tags = set()
if os.path.exists(patterns_file):
    with open(patterns_file) as f:
        for line in f:
            m = re.match(r"^## (.+)$", line.strip())
            if m:
                pattern_count += 1
                pattern_tags.add(m.group(1).strip())

# Tag counts (optionally from since_line)
tag_counter = Counter()
for i, obj in lessons:
    if since_line and i <= since_line:
        continue
    for tag in obj.get("tags", []):
        if isinstance(tag, str):
            tag_counter[tag] += 1

# Consolidation gaps
gaps = []
for tag, count in tag_counter.most_common():
    if count >= 3 and tag not in pattern_tags:
        # Collect takeaways for this tag
        takeaways = []
        for _, obj in lessons:
            if tag in obj.get("tags", []):
                takeaways.append(obj.get("takeaway", ""))
        gaps.append({"tag": tag, "count": count, "takeaways": takeaways})

# Draft patterns for gaps
drafts = []
for gap in gaps:
    bullets = list(set(t for t in gap["takeaways"] if t))[:5]
    if bullets:
        section = f"\n## {gap['tag']}\n" + "\n".join(f"- {b}" for b in bullets) + "\n"
        drafts.append({"tag": gap["tag"], "count": gap["count"], "section": section})

# Auto-write patterns with 5+ lessons
auto_written = []
if auto_mode and not dry_run and drafts:
    with open(patterns_file, "a") as f:
        for draft in drafts:
            if draft["count"] >= 5:
                f.write(draft["section"])
                auto_written.append(draft["tag"])

output = {
    "lesson_count": len(lessons),
    "decision_count": decision_count,
    "pattern_count": pattern_count,
    "format_issues": format_issues,
    "consolidation_gaps": [{"tag": g["tag"], "count": g["count"]} for g in gaps],
    "drafts": drafts,
    "auto_written": auto_written,
    "dry_run": dry_run
}
print(json.dumps(output))
PYTHON
    )

    # Log harvest
    if [[ "$dry_run" == "false" ]]; then
        local log_entry
        log_entry=$(python3 << 'PYTHON' - "$result"
import json, sys
from datetime import datetime
data = json.loads(sys.argv[1])
entry = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "timestamp": datetime.now().isoformat(),
    "lesson_count": data["lesson_count"],
    "decision_count": data["decision_count"],
    "pattern_count": data["pattern_count"],
    "format_issues": len(data["format_issues"]),
    "gaps": len(data["consolidation_gaps"])
}
print(json.dumps(entry))
PYTHON
        )
        echo "$log_entry" >> "$ZPC_STATE_DIR/harvest-log.jsonl"
    fi

    # Output
    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$result"
    else
        python3 << 'PYTHON' - "$result"
import json, sys
data = json.loads(sys.argv[1])
prefix = "DRY RUN — " if data["dry_run"] else ""
print(f"{prefix}ZPC HARVEST SUMMARY")
print(f"  Lessons:    {data['lesson_count']} total")
print(f"  Decisions:  {data['decision_count']} total")
print(f"  Patterns:   {data['pattern_count']} sections")
issues = data["format_issues"]
if issues:
    lines = ", ".join(str(i["line"]) for i in issues)
    print(f"  Format issues: {len(issues)} entries (lines: {lines})")
else:
    print(f"  Format issues: 0")
gaps = data["consolidation_gaps"]
print(f"  Consolidation gaps: {len(gaps)} tags need patterns")
for g in gaps:
    print(f"    {g['tag']} ({g['count']} lessons)")
if data["auto_written"]:
    print(f"\n  Auto-written patterns: {', '.join(data['auto_written'])}")
if data["drafts"]:
    print("\n--- Draft Patterns ---")
    for d in data["drafts"]:
        if d["tag"] not in data["auto_written"]:
            print(d["section"])
PYTHON
    fi
}

cmd_query() {
    ensure_zpc

    local tag="" since="" text="" qtype="all" limit=20

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tag|-t) tag="$2"; shift 2 ;;
            --since|-s) since="$2"; shift 2 ;;
            --text) text="$2"; shift 2 ;;
            --type) qtype="$2"; shift 2 ;;
            --limit|-n) limit="$2"; shift 2 ;;
            --help|-h)
                echo "Usage: agent-zpc query [--tag X] [--since DATE] [--text \"...\"] [--type lessons|decisions|all]"
                return 0
                ;;
            *) shift ;;
        esac
    done

    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    local decisions_file="$ZPC_MEMORY_DIR/decisions.jsonl"

    local result
    result=$(python3 << 'PYTHON' - "$lessons_file" "$decisions_file" "$tag" "$since" "$text" "$qtype" "$limit"
import json, sys, os

lessons_file, decisions_file = sys.argv[1], sys.argv[2]
tag, since, text, qtype, limit = sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], int(sys.argv[7])

def matches(obj, tag, since, text):
    if tag and tag not in obj.get("tags", []):
        return False
    if since and obj.get("date", "") < since:
        return False
    if text:
        text_lower = text.lower()
        blob = json.dumps(obj).lower()
        if text_lower not in blob:
            return False
    return True

results = []

if qtype in ("all", "lessons") and os.path.exists(lessons_file):
    with open(lessons_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                obj["_type"] = "lesson"
                if matches(obj, tag, since, text):
                    results.append(obj)
            except:
                pass

if qtype in ("all", "decisions") and os.path.exists(decisions_file):
    with open(decisions_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                obj["_type"] = "decision"
                if matches(obj, tag, since, text):
                    results.append(obj)
            except:
                pass

# Sort by date descending, limit
results.sort(key=lambda x: x.get("date", ""), reverse=True)
results = results[:limit]

print(json.dumps({"count": len(results), "results": results}))
PYTHON
    )

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$result"
    else
        python3 << 'PYTHON' - "$result"
import json, sys
data = json.loads(sys.argv[1])
if data["count"] == 0:
    print("No matches found.")
else:
    print(f"Found {data['count']} entries:\n")
    for r in data["results"]:
        t = r.pop("_type", "unknown")
        date = r.get("date", "?")
        if t == "lesson":
            print(f"[{date}] LESSON: {r.get('takeaway', '?')}")
            print(f"  Context: {r.get('context', '')}")
            print(f"  Problem: {r.get('problem', '')}")
            print(f"  Tags: {', '.join(r.get('tags', []))}")
        elif t == "decision":
            print(f"[{date}] DECISION: {r.get('chosen', '?')}")
            print(f"  Problem: {r.get('decision', '')}")
            print(f"  Rationale: {r.get('rationale', '')}")
            print(f"  Confidence: {r.get('confidence', '?')}")
        print()
PYTHON
    fi
}

cmd_patterns() {
    ensure_zpc

    local score=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --score) score=true; shift ;;
            --help|-h)
                echo "Usage: agent-zpc patterns [--score]"
                return 0
                ;;
            *) shift ;;
        esac
    done

    local patterns_file="$ZPC_MEMORY_DIR/patterns.md"

    if [[ ! -f "$patterns_file" ]]; then
        echo "No patterns file found."
        return 0
    fi

    if [[ "$score" == "false" ]]; then
        if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
            local content
            content=$(<"$patterns_file")
            json_success "$content"
        else
            cat "$patterns_file"
        fi
        return 0
    fi

    # Score patterns
    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    local result
    result=$(python3 << 'PYTHON' - "$patterns_file" "$lessons_file"
import json, sys, os, re, subprocess
from datetime import datetime, timedelta

patterns_file = sys.argv[1]
lessons_file = sys.argv[2]

# Extract pattern tags
pattern_tags = []
with open(patterns_file) as f:
    for line in f:
        m = re.match(r"^## (.+)$", line.strip())
        if m:
            pattern_tags.append(m.group(1).strip())

# Try to get pattern file modification dates via git
pattern_dates = {}
try:
    git_log = subprocess.check_output(
        ["git", "log", "--follow", "--format=%H %aI", "--", patterns_file],
        stderr=subprocess.DEVNULL, text=True
    ).strip()
    if git_log:
        # Use earliest commit date as baseline
        lines = git_log.strip().split("\n")
        if lines:
            earliest = lines[-1].split(" ", 1)[1][:10]
            for tag in pattern_tags:
                pattern_dates[tag] = earliest
except:
    pass

# Count lessons per tag, split by pattern date
lessons = []
if os.path.exists(lessons_file):
    with open(lessons_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                lessons.append(json.loads(line))
            except:
                pass

scores = []
for tag in pattern_tags:
    pattern_date = pattern_dates.get(tag, "unknown")
    pre = 0
    post = 0
    for lesson in lessons:
        if tag in lesson.get("tags", []):
            if pattern_date != "unknown" and lesson.get("date", "") > pattern_date:
                post += 1
            else:
                pre += 1

    days = 0
    if pattern_date != "unknown":
        try:
            pd = datetime.strptime(pattern_date, "%Y-%m-%d")
            days = (datetime.now() - pd).days
        except:
            pass

    effectiveness = days / (post + 1) if days > 0 else 0
    warning = "Pattern may not be effective" if post > pre and pre > 0 else ""

    scores.append({
        "tag": tag,
        "pattern_date": pattern_date,
        "pre_lessons": pre,
        "post_lessons": post,
        "days_active": days,
        "effectiveness": round(effectiveness, 1),
        "warning": warning
    })

print(json.dumps(scores))
PYTHON
    )

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$result"
    else
        python3 << 'PYTHON' - "$result"
import json, sys
scores = json.loads(sys.argv[1])
if not scores:
    print("No patterns to score.")
else:
    print(f"{'Pattern':<20} {'Since':<12} {'Pre':<5} {'Post':<5} {'Score':<8} {'Note'}")
    print("-" * 70)
    for s in scores:
        note = s["warning"] if s["warning"] else "OK"
        print(f"{s['tag']:<20} {s['pattern_date']:<12} {s['pre_lessons']:<5} {s['post_lessons']:<5} {s['effectiveness']:<8} {note}")
PYTHON
    fi
}

cmd_promote() {
    ensure_zpc

    local source="" target=""
    local positionals=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --to) target="$2"; shift 2 ;;
            --help|-h)
                echo "Usage: agent-zpc promote <line-numbers|tag> --to team|global"
                return 0
                ;;
            *) positionals+=("$1"); shift ;;
        esac
    done

    source="${positionals[0]:-}"

    if [[ -z "$source" || -z "$target" ]]; then
        die "Usage: agent-zpc promote <line-numbers|tag> --to team|global"
    fi

    if [[ "$target" != "team" && "$target" != "global" ]]; then
        die "Target must be 'team' or 'global'"
    fi

    local lessons_file="$ZPC_MEMORY_DIR/lessons.jsonl"
    local dest_file

    if [[ "$target" == "team" ]]; then
        mkdir -p "$ZPC_TEAM_DIR"
        dest_file="$ZPC_TEAM_DIR/shared-lessons.jsonl"
    else
        ensure_global
        dest_file="$ZPC_GLOBAL_DIR/global-lessons.jsonl"
    fi

    local result
    result=$(python3 << 'PYTHON' - "$lessons_file" "$dest_file" "$source"
import json, sys, os

lessons_file, dest_file, source = sys.argv[1], sys.argv[2], sys.argv[3]

# Read source lessons
lessons = []
if os.path.exists(lessons_file):
    with open(lessons_file) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    lessons.append((i, json.loads(line)))
                except:
                    pass

# Read existing dest for dedup
existing = set()
if os.path.exists(dest_file):
    with open(dest_file) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    obj = json.loads(line)
                    key = (obj.get("date",""), obj.get("context",""), obj.get("problem",""))
                    existing.add(key)
                except:
                    pass

# Select lessons to promote
selected = []
if source.replace(",", "").isdigit():
    # Line numbers
    line_nums = set(int(n.strip()) for n in source.split(",") if n.strip())
    for i, obj in lessons:
        if i in line_nums:
            selected.append(obj)
else:
    # Tag name
    for i, obj in lessons:
        if source in obj.get("tags", []):
            selected.append(obj)

# Write, deduplicating
promoted = 0
with open(dest_file, "a") as f:
    for obj in selected:
        key = (obj.get("date",""), obj.get("context",""), obj.get("problem",""))
        if key not in existing:
            f.write(json.dumps(obj) + "\n")
            existing.add(key)
            promoted += 1

print(json.dumps({"promoted": promoted, "skipped": len(selected) - promoted, "total_selected": len(selected)}))
PYTHON
    )

    if [[ "${OUTPUT_FORMAT:-text}" == "json" ]]; then
        json_result "$result"
    else
        python3 << 'PYTHON' - "$result" "$target"
import json, sys
data = json.loads(sys.argv[1])
target = sys.argv[2]
print(f"Promoted {data['promoted']} lessons to {target}")
if data["skipped"]:
    print(f"  ({data['skipped']} duplicates skipped)")
PYTHON
    fi
}
