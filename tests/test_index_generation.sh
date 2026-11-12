#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="$(mktemp -d)"
trap 'rm -rf "$TEST_DIR"' EXIT

"$ROOT/bin/gen-index" --output "$TEST_DIR/index.yaml"
"$ROOT/bin/gen-index" --output "$TEST_DIR/index-again.yaml"
cmp "$TEST_DIR/index.yaml" "$TEST_DIR/index-again.yaml"

python3 - "$ROOT" "$TEST_DIR/index.yaml" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
index_path = Path(sys.argv[2])
sys.path.insert(0, str(root / "lib"))
from registry import _load_yaml_data

registry_tools = _load_yaml_data(root / "registry.yaml")["tools"]
index = _load_yaml_data(index_path)
index_tools = index["tools"]
tool_paths = {
    path.name.removeprefix("agent-")
    for path in (root / "tools").glob("agent-*")
}

assert tool_paths == set(registry_tools), (
    f"tool paths and registry differ: missing registry={sorted(tool_paths - set(registry_tools))}; "
    f"missing path={sorted(set(registry_tools) - tool_paths)}"
)
assert set(index_tools) == set(registry_tools), (
    f"generated index differs from registry: missing={sorted(set(registry_tools) - set(index_tools))}; "
    f"extra={sorted(set(index_tools) - set(registry_tools))}"
)
assert index["tool_count"] == len(registry_tools) == len(tool_paths)
assert set(index["tool_categories"]) == set(registry_tools)
assert index["task_routing"]["github"] == "gh"
assert "GitHub PRs/reviews use: agent-do gh" in index_tools["git"]
assert "local repository work use: agent-do git" in index_tools["gh"]
assert "models" in index_tools
assert '"$REPO_DIR/bin/gen-index" --output "$FACTORY_INDEX_PATH"' in (root / "install.sh").read_text()
PY

git_first="$($ROOT/tools/agent-git --help | head -1)"
gh_first="$($ROOT/tools/agent-gh --help | head -1)"
[[ "$git_first" == "Local repository operations. For GitHub PRs/reviews use: agent-do gh" ]]
[[ "$gh_first" == "GitHub issue and PR/review operations. For local repository work use: agent-do git" ]]

echo "index generation tests passed"
