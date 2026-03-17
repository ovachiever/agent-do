#!/usr/bin/env bash
# lib/budget.sh — Token budgeting and context injection for agent-context
# Sourced by agent-context entry point. Do not run directly.

# Best content fitting within a token budget
cmd_budget() {
    local budget="" query=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            *)
                if [[ -z "$budget" && "$1" =~ ^[0-9]+$ ]]; then
                    budget="$1"
                else
                    query="${query:+$query }$1"
                fi
                shift
                ;;
        esac
    done

    [[ -n "$budget" && -n "$query" ]] || die "Usage: agent-context budget <tokens> <query>"
    ensure_init

    python3 - "$CONTEXT_INDEX_DB" "$budget" "$query" "$CONTEXT_CACHE_DIR" "$CONTEXT_HOME/feedback.jsonl" "${OUTPUT_FORMAT:-text}" << 'PYTHON'
import sqlite3, sys, json, os

db_path, budget_str, query, cache_dir, feedback_path, output_format = sys.argv[1:7]
budget = int(budget_str)

conn = sqlite3.connect(db_path)

# Trust multipliers
TRUST_MULT = {"official": 1.5, "maintainer": 1.2, "local": 1.3, "community": 1.0}

# Keyword expansion
EXPANSIONS = {
    "react": "react reactjs jsx", "next": "next nextjs", "python": "python python3 py",
    "js": "javascript js", "ts": "typescript ts", "db": "database db sql",
    "auth": "auth authentication", "api": "api rest endpoint",
    "k8s": "kubernetes k8s", "docker": "docker container",
    "ml": "ml machine learning ai", "llm": "llm language model ai",
}

expanded_terms = []
for word in query.lower().split():
    expanded_terms.append(word)
    if word in EXPANSIONS:
        for exp in EXPANSIONS[word].split():
            if exp != word:
                expanded_terms.append(exp)

fts_query = " OR ".join(expanded_terms)

# Load feedback
feedback = {}
if os.path.exists(feedback_path):
    with open(feedback_path) as f:
        for line in f:
            try:
                entry = json.loads(line)
                pkg = entry.get("package", "")
                rating = entry.get("rating", "")
                if pkg:
                    feedback[pkg] = feedback.get(pkg, 0) + (1 if rating == "up" else -1)
            except:
                pass

# Search and rank
try:
    rows = conn.execute(
        "SELECT id, name, description, trust, token_count, cache_path, type, bm25(packages) as score "
        "FROM packages WHERE packages MATCH ? ORDER BY bm25(packages) LIMIT 50",
        (fts_query,)
    ).fetchall()
except:
    rows = []

# Score and sort
candidates = []
for row in rows:
    pkg_id, name, desc, trust, tokens, cache_path, ptype, bm25_score = row
    tokens = int(tokens) if tokens else 0
    if tokens == 0:
        continue

    trust_mult = TRUST_MULT.get(trust, 1.0)
    fb_score = feedback.get(pkg_id, 0)
    fb_mult = 1.1 if fb_score > 0 else (0.8 if fb_score < 0 else 1.0)
    score = abs(bm25_score) * trust_mult * fb_mult

    candidates.append({
        "id": pkg_id, "name": name, "description": desc, "type": ptype,
        "trust": trust, "token_count": tokens, "score": round(score, 3),
        "cache_path": cache_path,
    })

candidates.sort(key=lambda x: x["score"], reverse=True)

# Greedy knapsack: pack by score until budget exhausted
selected = []
remaining = budget
for c in candidates:
    if c["token_count"] <= remaining:
        selected.append(c)
        remaining -= c["token_count"]

total_tokens = sum(s["token_count"] for s in selected)

if output_format == "json":
    # Include content in JSON mode
    for s in selected:
        cp = s["cache_path"]
        for fname in ["content.md", "DOC.md", "SKILL.md", "README.md"]:
            fp = os.path.join(cp, fname) if cp else ""
            if fp and os.path.exists(fp):
                with open(fp) as f:
                    s["content"] = f.read()
                break
        s.pop("cache_path", None)

    print(json.dumps({
        "success": True,
        "budget": budget,
        "used_tokens": total_tokens,
        "remaining_tokens": remaining,
        "packages": selected,
    }, indent=2))
else:
    print(f"Budget: {budget} tokens | Used: {total_tokens} | Remaining: {remaining}\n")
    if not selected:
        print("No matching content found.")
    else:
        for s in selected:
            print(f"  {s['name']:30s} ~{s['token_count']} tokens  (score: {s['score']})")
        print(f"\nUse 'agent-context get <id>' to view content.")

conn.close()
PYTHON
}

# Emit structured context blob for agent consumption
cmd_inject() {
    local max_tokens="8000"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --max-tokens) max_tokens="$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    ensure_init

    python3 - "$CONTEXT_INDEX_DB" "$max_tokens" "$CONTEXT_CACHE_DIR" "${OUTPUT_FORMAT:-text}" << 'PYTHON'
import sqlite3, sys, json, os

db_path, max_tokens_str, cache_dir, output_format = sys.argv[1:5]
max_tokens = int(max_tokens_str)

conn = sqlite3.connect(db_path)

# Get most recently accessed and most used packages
rows = conn.execute(
    "SELECT id, name, type, trust, token_count, cache_path "
    "FROM package_meta ORDER BY access_count DESC, last_accessed DESC LIMIT 20"
).fetchall()

# Pack by recency/frequency until budget met
selected = []
remaining = max_tokens
for row in rows:
    pkg_id, name, ptype, trust, tokens, cache_path = row
    tokens = int(tokens) if tokens else 0
    if tokens == 0 or tokens > remaining:
        continue

    # Read content
    content = ""
    if cache_path:
        for fname in ["content.md", "DOC.md", "SKILL.md", "README.md"]:
            fp = os.path.join(cache_path, fname)
            if os.path.exists(fp):
                with open(fp) as f:
                    content = f.read()
                break

    if content:
        selected.append({
            "id": pkg_id,
            "name": name,
            "type": ptype,
            "trust": trust,
            "token_count": tokens,
            "content": content,
        })
        remaining -= tokens

total_used = sum(s["token_count"] for s in selected)

if output_format == "json":
    print(json.dumps({
        "success": True,
        "max_tokens": max_tokens,
        "used_tokens": total_used,
        "package_count": len(selected),
        "packages": selected,
    }, indent=2))
else:
    # Emit as markdown blob suitable for agent context
    print(f"# Context Hub ({len(selected)} packages, ~{total_used} tokens)\n")
    for s in selected:
        print(f"## {s['name']} [{s['trust']}]\n")
        print(s["content"])
        print("\n---\n")

conn.close()
PYTHON
}
