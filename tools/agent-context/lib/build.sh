#!/usr/bin/env bash
# lib/build.sh — Build pipeline for private content
# Sourced by agent-context entry point. Do not run directly.

cmd_build() {
    local content_dir="" output_dir=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -o|--output) output_dir="$2"; shift 2 ;;
            *) content_dir="$1"; shift ;;
        esac
    done

    [[ -n "$content_dir" ]] || die "Usage: agent-context build <content-dir> [-o output]"
    [[ -d "$content_dir" ]] || die "Directory not found: $content_dir"

    output_dir="${output_dir:-$content_dir/dist}"

    python3 - "$content_dir" "$output_dir" "${OUTPUT_FORMAT:-text}" << 'PYTHON'
import sys, json, os, glob, shutil
from datetime import datetime, timezone

content_dir, output_dir, output_format = sys.argv[1:4]

errors = []
entries = []

# Walk content directory for DOC.md and SKILL.md files
for root, dirs, files in os.walk(content_dir):
    for fname in files:
        if fname not in ("DOC.md", "SKILL.md"):
            continue

        filepath = os.path.join(root, fname)
        rel_path = os.path.relpath(filepath, content_dir)

        # Parse frontmatter
        with open(filepath) as f:
            content = f.read()

        if not content.startswith("---"):
            errors.append(f"{rel_path}: missing YAML frontmatter")
            continue

        parts = content.split("---", 2)
        if len(parts) < 3:
            errors.append(f"{rel_path}: malformed frontmatter")
            continue

        try:
            import yaml
            meta = yaml.safe_load(parts[1]) or {}
        except ImportError:
            meta = {}
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"').strip("'")
        except Exception as e:
            errors.append(f"{rel_path}: invalid YAML: {e}")
            continue

        # Validate required fields
        name = meta.get("name")
        if not name:
            errors.append(f"{rel_path}: missing 'name' field")
            continue

        description = meta.get("description")
        if not description:
            errors.append(f"{rel_path}: missing 'description' field")

        entry_type = "skill" if fname == "SKILL.md" else "doc"

        # Count tokens
        body = parts[2].strip()
        token_count = int(len(body.split()) * 1.3)

        # Check for references
        entry_dir = os.path.dirname(filepath)
        refs_dir = os.path.join(entry_dir, "references")
        reference_files = []
        if os.path.isdir(refs_dir):
            for ref in os.listdir(refs_dir):
                if ref.endswith(".md"):
                    reference_files.append(ref)

        entries.append({
            "id": name.lower().replace(" ", "-"),
            "name": name,
            "type": entry_type,
            "description": description or "",
            "tags": meta.get("tags", []),
            "token_count": token_count,
            "path": rel_path,
            "references": reference_files,
            "metadata": {k: v for k, v in meta.items() if k not in ("name", "description", "tags")},
        })

# Output
if errors:
    if output_format == "json":
        print(json.dumps({
            "success": False,
            "errors": errors,
            "valid_entries": len(entries),
        }, indent=2))
    else:
        print(f"Validation errors ({len(errors)}):")
        for e in errors:
            print(f"  ! {e}")
        print()

if entries:
    # Write registry.json to output
    os.makedirs(output_dir, exist_ok=True)

    registry = {
        "docs": [e for e in entries if e["type"] == "doc"],
        "skills": [e for e in entries if e["type"] == "skill"],
        "built_at": datetime.now(timezone.utc).isoformat(),
        "entry_count": len(entries),
    }

    with open(os.path.join(output_dir, "registry.json"), "w") as f:
        json.dump(registry, f, indent=2)

    # Copy content files
    for entry in entries:
        src_dir = os.path.dirname(os.path.join(content_dir, entry["path"]))
        dest_dir = os.path.join(output_dir, os.path.dirname(entry["path"]))
        os.makedirs(dest_dir, exist_ok=True)

        # Copy entry file
        src_file = os.path.join(content_dir, entry["path"])
        shutil.copy2(src_file, dest_dir)

        # Copy references
        refs_src = os.path.join(src_dir, "references")
        if os.path.isdir(refs_src):
            refs_dest = os.path.join(dest_dir, "references")
            if os.path.exists(refs_dest):
                shutil.rmtree(refs_dest)
            shutil.copytree(refs_src, refs_dest)

    if output_format == "json":
        print(json.dumps({
            "success": len(errors) == 0,
            "entries": len(entries),
            "docs": len(registry["docs"]),
            "skills": len(registry["skills"]),
            "errors": len(errors),
            "output": output_dir,
        }, indent=2))
    else:
        print(f"Built {len(entries)} entries ({len(registry['docs'])} docs, {len(registry['skills'])} skills)")
        print(f"  Output: {output_dir}")
        if errors:
            print(f"  Warnings: {len(errors)} (see above)")

PYTHON
}

cmd_validate() {
    local content_dir="${1:-}"
    [[ -n "$content_dir" ]] || die "Usage: agent-context validate <content-dir>"
    [[ -d "$content_dir" ]] || die "Directory not found: $content_dir"

    # Reuse build with a temp output that we discard
    local tmp_out
    tmp_out=$(mktemp -d)
    cmd_build "$content_dir" -o "$tmp_out"
    rm -rf "$tmp_out"
}
