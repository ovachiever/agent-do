#!/usr/bin/env bash
# Integration tests for agent-context
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$SCRIPT_DIR/../agent-context"
PASS=0
FAIL=0

# Use isolated test home
export AGENT_DO_HOME=$(mktemp -d)
trap "rm -rf $AGENT_DO_HOME" EXIT

check() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  ✓ $desc"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $desc"
        FAIL=$((FAIL + 1))
    fi
}

check_output() {
    local desc="$1" expected="$2"
    shift 2
    local output
    output=$("$@" 2>&1) || true
    if grep -q "$expected" <<<"$output"; then
        echo "  ✓ $desc"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $desc (expected: $expected)"
        echo "    got: $(echo "$output" | head -3)"
        FAIL=$((FAIL + 1))
    fi
}

echo "agent-context integration tests"
echo "================================"
echo ""

echo "1. Initialization"
check "help works" "$TOOL" --help
check "init creates store" "$TOOL" init
check "init is idempotent" "$TOOL" init
check_output "status shows 0 packages" "0 indexed" "$TOOL" status
check_output "status --json includes freshness counts" "fresh_packages" "$TOOL" status --json
check_output "stale --json works on empty store" "success" "$TOOL" stale --json

echo ""
echo "2. Fetch"
check "fetch URL" "$TOOL" fetch https://raw.githubusercontent.com/anthropics/anthropic-cookbook/main/README.md
check_output "list shows 1 package" "1 package" "$TOOL" list
check_output "freshness tracks fetched package" "1 fresh" "$TOOL" status

echo ""
echo "3. Fetch LLMs"
check "fetch-llms" "$TOOL" fetch-llms supabase.com
check_output "list shows 2" "2 package" "$TOOL" list

echo ""
echo "4. Search"
check_output "search finds supabase" "supabase" "$TOOL" search supabase
check_output "search --json returns JSON" "success" "$TOOL" search supabase --json

echo ""
echo "5. Get"
check "get by id" "$TOOL" get supabase-com-llms
check_output "get --json has content" "content" "$TOOL" get supabase-com-llms --json
check_output "get unknown shows error" "not found" "$TOOL" get nonexistent-package

echo ""
echo "6. Annotations"
check "annotate" "$TOOL" annotate supabase-com-llms "test note"
check_output "annotate shows on get" "test note" "$TOOL" get supabase-com-llms
check_output "annotate list" "test note" "$TOOL" annotate --list
check "annotate clear" "$TOOL" annotate supabase-com-llms --clear

echo ""
echo "7. Feedback"
check "feedback up" "$TOOL" feedback supabase-com-llms up "good docs"
check "feedback down" "$TOOL" feedback supabase-com-llms down

echo ""
echo "8. Cache"
check_output "cache list" "package" "$TOOL" cache list
check_output "cache stats" "Packages" "$TOOL" cache stats
check "cache pin" "$TOOL" cache pin supabase-com-llms
check "cache clear specific" "$TOOL" cache clear supabase-com-llms
check "cache clear all" "$TOOL" cache clear

echo ""
echo "9. Sources"
check_output "sources empty" "No sources" "$TOOL" sources
check "add-source" "$TOOL" add-source test-source https://example.com/docs
check_output "config keeps trust policy" "trust_policy" grep -n "trust_policy" "$AGENT_DO_HOME/context/config.yaml"
check_output "sources shows entry" "test-source" "$TOOL" sources
check "remove-source" "$TOOL" remove-source test-source
check_output "sources empty after remove" "No sources" "$TOOL" sources

echo ""
echo "10. HTML and version currency"
html_script=$(mktemp)
cat > "$html_script" <<'BASH'
set -euo pipefail
tool="$1"
html_home=$(mktemp -d)
html_root=$(mktemp -d)
port_file=$(mktemp)
server_pid=""
cleanup() {
    [[ -n "$server_pid" ]] && kill "$server_pid" 2>/dev/null || true
    rm -rf "$html_home" "$html_root" "$port_file"
}
trap cleanup EXIT

cat > "$html_root/index.html" <<'HTML'
<!doctype html>
<html>
<head>
  <title>Next 14 Docs</title>
  <meta name="description" content="HTML docs extraction fixture">
  <script>hidden-script-token</script>
  <style>.ignored { color: red; }</style>
</head>
<body>
  <nav>nav-only-token</nav>
  <main>
    <h1>Next 14 Docs</h1>
    <p>html-root-token</p>
    <a href="/guide.html">Guide</a>
  </main>
</body>
</html>
HTML
cat > "$html_root/guide.html" <<'HTML'
<!doctype html>
<html>
<head><title>Guide</title></head>
<body><main><h1>Guide</h1><p>html-guide-token</p><pre>const htmlCodeToken = true</pre></main></body>
</html>
HTML

python3 - "$html_root" "$port_file" <<'PYTHON' &
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
port_file = Path(sys.argv[2])

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/npm/next":
            body = json.dumps({"dist-tags": {"latest": "16.0.0"}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return
        path = self.path
        if path == "/":
            path = "/index.html"
        file_path = root / path.lstrip("/")
        if not file_path.exists():
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("ETag", '"' + file_path.name + '"')
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port_file.write_text(str(server.server_address[1]))
server.serve_forever()
PYTHON
server_pid=$!

for _ in $(seq 1 50); do
    [[ -s "$port_file" ]] && break
    sleep 0.1
done
[[ -s "$port_file" ]]
port=$(cat "$port_file")
base="http://127.0.0.1:${port}"

AGENT_DO_HOME="$html_home" "$tool" init >/dev/null
AGENT_DO_HOME="$html_home" "$tool" fetch "$base/" >/dev/null
AGENT_DO_HOME="$html_home" "$tool" search html-root-token | grep -q "Next 14 Docs"
hidden_out=$(AGENT_DO_HOME="$html_home" "$tool" search hidden-script-token)
! grep -q "Next 14 Docs" <<<"$hidden_out"
find "$html_home/context/cache" -path "*/raw/raw.html" | grep -q raw.html

AGENT_DO_HOME="$html_home" "$tool" add-source next "$base/" --kind html-site --trust official --crawl-limit 3 --tags html-test --ecosystem npm --package next --doc-version 14 --registry npm --registry-url "$base/npm" >/dev/null
AGENT_DO_HOME="$html_home" "$tool" sources sync next >/dev/null
AGENT_DO_HOME="$html_home" "$tool" retrieve html-guide-token --max-tokens 2000 | grep -q html-guide-token
AGENT_DO_HOME="$html_home" "$tool" versions sources --outdated | grep -q behind_major
AGENT_DO_HOME="$html_home" "$tool" versions check --all --limit 5 >/dev/null
AGENT_DO_HOME="$html_home" "$tool" versions outdated | grep -q behind_major
! AGENT_DO_HOME="$html_home" "$tool" retrieve html-guide-token --require-current --max-tokens 2000 >/dev/null 2>&1
AGENT_DO_HOME="$html_home" "$tool" serve --print-url --port 9876 | grep -q "http://127.0.0.1:9876/"
BASH
check "HTML fetch/crawl extraction and version currency" bash "$html_script" "$TOOL"
rm -f "$html_script"

echo ""
echo "11. Scan local"
check "scan-local" "$TOOL" scan-local "$SCRIPT_DIR/../../.."

echo ""
echo "12. Schema migration"
old_context=$(mktemp -d)
mkdir -p "$old_context/context/cache/local/old-package"
cat > "$old_context/context/cache/local/old-package/README.md" <<'OLD'
# Old Package

old-schema-token
OLD
python3 - "$old_context/context/index.db" "$old_context/context/cache/local/old-package" <<'PYTHON'
import sqlite3
import sys

db, cache_path = sys.argv[1:3]
conn = sqlite3.connect(db)
conn.execute("""
    CREATE VIRTUAL TABLE packages USING fts5(
        id, name, description, tags, content_preview,
        source UNINDEXED, trust UNINDEXED, token_count UNINDEXED,
        cache_path UNINDEXED, type UNINDEXED
    )
""")
conn.execute("""
    CREATE TABLE package_meta (
        id TEXT PRIMARY KEY,
        name TEXT,
        type TEXT,
        trust TEXT,
        token_count INTEGER,
        source TEXT,
        cache_path TEXT,
        fetched_at TEXT,
        last_accessed TEXT,
        access_count INTEGER DEFAULT 0
    )
""")
conn.execute(
    "INSERT INTO packages VALUES (?,?,?,?,?,?,?,?,?,?)",
    ("old-package", "old-package", "Old package", "", "old-schema-token", cache_path, "local", 3, cache_path, "local"),
)
conn.execute(
    "INSERT INTO package_meta VALUES (?,?,?,?,?,?,?,?,?,?)",
    ("old-package", "old-package", "local", "local", 3, cache_path, cache_path, "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", 0),
)
conn.commit()
conn.close()
PYTHON
check "old schema migrates on status" bash -c "AGENT_DO_HOME='$old_context' '$TOOL' status --json | grep -q local_packages && AGENT_DO_HOME='$old_context' '$TOOL' stale --json | grep -q '\"count\": 0' && sqlite3 '$old_context/context/index.db' \"select count(*) from package_files\" | grep -q 1"
rm -rf "$old_context"

echo ""
echo "13. Refresh"
refresh_script=$(mktemp)
cat > "$refresh_script" <<'BASH'
set -euo pipefail
tool="$1"
refresh_home=$(mktemp -d)
refresh_root=$(mktemp -d)
port_file=$(mktemp)
server_pid=""
cleanup() {
    [[ -n "$server_pid" ]] && kill "$server_pid" 2>/dev/null || true
    rm -rf "$refresh_home" "$refresh_root" "$port_file"
}
trap cleanup EXIT

cat > "$refresh_root/doc.md" <<'DOC'
# Refresh Doc

old-refresh-token
DOC

python3 - "$refresh_root" "$port_file" <<'PYTHON' &
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

root = Path(sys.argv[1])
port_file = Path(sys.argv[2])

class QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if (root / "fail").exists():
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"failure")
            return
        if self.path != "/doc.md":
            self.send_response(404)
            self.end_headers()
            return
        body = (root / "doc.md").read_bytes()
        etag = '"' + sha256(body).hexdigest() + '"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", "Fri, 08 May 2026 12:00:00 GMT")
        self.end_headers()
        self.wfile.write(body)

server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
port_file.write_text(str(server.server_address[1]))
server.serve_forever()
PYTHON
server_pid=$!

for _ in $(seq 1 50); do
    [[ -s "$port_file" ]] && break
    sleep 0.1
done
[[ -s "$port_file" ]]
port=$(cat "$port_file")
url="http://127.0.0.1:${port}/doc.md"

AGENT_DO_HOME="$refresh_home" "$tool" init >/dev/null
AGENT_DO_HOME="$refresh_home" "$tool" add-source refresh-source "$url" --kind url --trust official --ttl 1d --tags refresh-test >/dev/null
AGENT_DO_HOME="$refresh_home" "$tool" sources sync refresh-source >/dev/null
sources_out=$(AGENT_DO_HOME="$refresh_home" "$tool" sources)
grep -q "sync=ok" <<<"$sources_out"
official_retrieve=$(AGENT_DO_HOME="$refresh_home" "$tool" retrieve old-refresh-token --require-official --max-tokens 1000)
grep -q old-refresh-token <<<"$official_retrieve"
fetch_out=$(AGENT_DO_HOME="$refresh_home" "$tool" fetch "$url")
pkg_id=$(printf '%s\n' "$fetch_out" | sed -n 's/^Fetched: .* (\([^)]*\))$/\1/p')
[[ -n "$pkg_id" ]]

cat > "$refresh_root/doc.md" <<'DOC'
# Refresh Doc

new-refresh-token
DOC

AGENT_DO_HOME="$refresh_home" "$tool" refresh "$pkg_id" >/dev/null
get_out=$(AGENT_DO_HOME="$refresh_home" "$tool" get "$pkg_id")
grep -q new-refresh-token <<<"$get_out"
status_out=$(AGENT_DO_HOME="$refresh_home" "$tool" status)
grep -q "1 fresh" <<<"$status_out"
retrieve_json=$(AGENT_DO_HOME="$refresh_home" "$tool" retrieve "Refresh Doc" --max-tokens 1000 --json)
grep -q new-refresh-token <<<"$retrieve_json"
grep -q '"freshness"' <<<"$retrieve_json"

cat > "$refresh_root/doc.md" <<'DOC'
# Refresh Doc

new-refresh-token
retrieve-refresh-token
DOC
sqlite3 "$refresh_home/context/index.db" "UPDATE package_meta SET refresh_status = 'stale', expires_at = '2000-01-01T00:00:00+00:00' WHERE id = '$pkg_id'"
retrieve_out=$(AGENT_DO_HOME="$refresh_home" "$tool" retrieve "Refresh Doc" --require-fresh --max-tokens 1000)
grep -q retrieve-refresh-token <<<"$retrieve_out"
not_modified_out=$(AGENT_DO_HOME="$refresh_home" "$tool" refresh "$pkg_id")
grep -q "not modified" <<<"$not_modified_out"
touch "$refresh_root/fail"
sqlite3 "$refresh_home/context/index.db" "UPDATE package_meta SET refresh_status = 'stale', expires_at = '2000-01-01T00:00:00+00:00' WHERE id = '$pkg_id'"
! AGENT_DO_HOME="$refresh_home" "$tool" refresh "$pkg_id" >/dev/null 2>&1
failed_status=$(sqlite3 "$refresh_home/context/index.db" "SELECT refresh_status FROM package_meta WHERE id = '$pkg_id'")
[[ "$failed_status" == "failed" ]]
last_good=$(AGENT_DO_HOME="$refresh_home" "$tool" get "$pkg_id")
grep -q retrieve-refresh-token <<<"$last_good"
rm -f "$refresh_root/fail"
AGENT_DO_HOME="$refresh_home" "$tool" add-source disabled-refresh "$url" --kind url --disabled >/dev/null
sqlite3 "$refresh_home/context/index.db" "UPDATE package_meta SET refresh_status = 'stale', expires_at = '2000-01-01T00:00:00+00:00' WHERE id = '$pkg_id'"
due_out=$(AGENT_DO_HOME="$refresh_home" "$tool" refresh --due --limit 1)
grep -q "0 refreshed" <<<"$due_out"
grep -q "1 skipped" <<<"$due_out"
maintain_json=$(AGENT_DO_HOME="$refresh_home" "$tool" maintain --limit 1 --max-mb 100 --json)
grep -q '"freshness"' <<<"$maintain_json"
BASH
check "refresh, retrieve, and sources sync URL package" bash "$refresh_script" "$TOOL"
rm -f "$refresh_script"

gh_script=$(mktemp)
cat > "$gh_script" <<'BASH'
#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == "api" ]] || exit 1
shift
endpoint="${1:-}"
case "$endpoint" in
    repos/example/repo/contents/docs)
        exit 0
        ;;
    'repos/example/repo/git/trees/HEAD?recursive=1')
        cat <<'JSON'
{"tree":[
  {"path":"docs/guide.md","type":"blob","sha":"sha-guide"},
  {"path":"docs/deep/ref.txt","type":"blob","sha":"sha-ref"},
  {"path":"src/ignored.md","type":"blob","sha":"sha-ignore"}
]}
JSON
        ;;
    repos/example/repo/git/blobs/sha-guide)
        printf '# Guide\n\ngithub-dir-token\n' | base64
        ;;
    repos/example/repo/git/blobs/sha-ref)
        printf 'deep-github-dir-token\n' | base64
        ;;
    repos/example/repo/git/blobs/sha-ignore)
        printf 'ignored-token\n' | base64
        ;;
    *)
        exit 1
        ;;
esac
BASH
chmod +x "$gh_script"
gh_bin=$(mktemp -d)
ln -s "$gh_script" "$gh_bin/gh"
gh_home=$(mktemp -d)
check "fetch-repo indexes mocked GitHub directory" bash -c "PATH='$gh_bin':\$PATH AGENT_DO_HOME='$gh_home' '$TOOL' init >/dev/null && PATH='$gh_bin':\$PATH AGENT_DO_HOME='$gh_home' '$TOOL' fetch-repo example/repo docs >/dev/null && PATH='$gh_bin':\$PATH AGENT_DO_HOME='$gh_home' '$TOOL' get example-repo --full | grep -q github-dir-token && PATH='$gh_bin':\$PATH AGENT_DO_HOME='$gh_home' '$TOOL' get example-repo --full | grep -q deep-github-dir-token && sqlite3 '$gh_home/context/index.db' \"SELECT source_kind FROM package_meta WHERE id = 'example-repo'\" | grep -q github-dir"
check "refresh updates mocked GitHub directory" bash -c "sqlite3 '$gh_home/context/index.db' \"UPDATE package_meta SET refresh_status = 'stale', expires_at = '2000-01-01T00:00:00+00:00' WHERE id = 'example-repo'\" && PATH='$gh_bin':\$PATH AGENT_DO_HOME='$gh_home' '$TOOL' refresh example-repo >/dev/null && PATH='$gh_bin':\$PATH AGENT_DO_HOME='$gh_home' '$TOOL' get example-repo --full | grep -q deep-github-dir-token"
rm -rf "$gh_script" "$gh_bin" "$gh_home"

echo ""
echo "14. Scan skills"
skill_home=$(mktemp -d)
skill_context=$(mktemp -d)
mkdir -p "$skill_home/.claude/skills/sample-skill/references" "$skill_home/.claude/skills/ignored-skill"
cat > "$skill_home/.claude/skills/sample-skill/SKILL.md" <<'SKILL'
---
name: sample-skill
description: |
  Sample skill for scan-skills integration testing.
  Exercises block scalar descriptions.
---

# Sample Skill

Main skill content.
SKILL
cat > "$skill_home/.claude/skills/sample-skill/references/deep.md" <<'REF'
# Deep Reference

sample-reference-token
sample-v4-to-v5-token
REF
cat > "$skill_home/.claude/skills/ignored-skill/SKILL.md" <<'SKILL'
---
name: ignored-skill
description: Should not be indexed by named scan.
---

# Ignored
SKILL
check "scan-skills named skill with bundled reference" bash -c "HOME='$skill_home' AGENT_DO_HOME='$skill_context' '$TOOL' init >/dev/null && HOME='$skill_home' AGENT_DO_HOME='$skill_context' '$TOOL' scan-skills sample-skill >/dev/null && HOME='$skill_home' AGENT_DO_HOME='$skill_context' '$TOOL' get skill-sample-skill --file references/deep.md | grep -q sample-reference-token && HOME='$skill_home' AGENT_DO_HOME='$skill_context' '$TOOL' search sample-reference-token | grep -q sample-skill && ! HOME='$skill_home' AGENT_DO_HOME='$skill_context' '$TOOL' list | grep -q ignored-skill"
check "budget handles hyphenated support-file query" bash -c "HOME='$skill_home' AGENT_DO_HOME='$skill_context' '$TOOL' budget 5000 sample-v4-to-v5-token --json | grep -q sample-v4-to-v5-token"
check "retrieve includes recursive package content" bash -c "HOME='$skill_home' AGENT_DO_HOME='$skill_context' '$TOOL' retrieve sample-v4-to-v5-token --max-tokens 5000 --json | grep -q sample-v4-to-v5-token"
check "inject includes recursive package files" bash -c "HOME='$skill_home' AGENT_DO_HOME='$skill_context' '$TOOL' get skill-sample-skill >/dev/null && HOME='$skill_home' AGENT_DO_HOME='$skill_context' '$TOOL' inject --max-tokens 5000 --json | grep -q sample-v4-to-v5-token"
cat > "$skill_home/.claude/skills/sample-skill/references/deep.md" <<'REF'
# Deep Reference

sample-reference-token
sample-v4-to-v5-token
sample-refresh-token
REF
check "refresh rescans local skill support files" bash -c "HOME='$skill_home' AGENT_DO_HOME='$skill_context' '$TOOL' refresh skill-sample-skill >/dev/null && HOME='$skill_home' AGENT_DO_HOME='$skill_context' '$TOOL' get skill-sample-skill --file references/deep.md | grep -q sample-refresh-token"
check "cache clear by package name removes index row" bash -c "HOME='$skill_home' AGENT_DO_HOME='$skill_context' '$TOOL' cache clear sample-skill >/dev/null && ! HOME='$skill_home' AGENT_DO_HOME='$skill_context' '$TOOL' list | grep -q sample-skill"
rm -rf "$skill_home" "$skill_context"

echo ""
echo "15. Budget"
# Re-fetch something for budget to work with
"$TOOL" fetch https://raw.githubusercontent.com/anthropics/anthropic-cookbook/main/README.md >/dev/null 2>&1
check_output "budget" "Budget" "$TOOL" budget 5000 "api documentation"

echo ""
echo "16. Status (final)"
check_output "redact_url hides secret query params" "api_key=%5Bredacted%5D" bash -c "source '$SCRIPT_DIR/../lib/common.sh'; redact_url 'https://example.com/doc.md?api_key=secret&ok=1'"
check_output "maintain schedule print" "com.agent-do.context-maintain" "$TOOL" maintain schedule print
check "maintain --json" "$TOOL" maintain --limit 0 --max-mb 500 --json
check "status --json" "$TOOL" status --json

echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && echo "All tests passed!" || exit 1
