#!/usr/bin/env python3
"""Recover design evidence from saved records, without executing recorded code.

No metric is computed here. All transcript records are traversed, without a
record-count cap. Versions are content addressed and never overwrite evidence.
"""
import base64
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CORPUS = ROOT / "corpus/design/rounds"
ARCHIVE = ROOT / ".dev/dpt-wildhunt/evidence"
SESSION = "fae1af41-26ba-4c61-9805-d261387c8a4a"
RECORD = Path.home() / ".claude/projects/-Users-erik-Custom-Coding-agent-do" / f"{SESSION}.jsonl"
ROUNDS = {"concept", "concept2", "lib3", "lib4", "eng3", "eng4", "eng5", "eng6", "eng7", "reground"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def relative(original):
    if "/moon1/" not in original:
        return None
    p = Path(original.split("/moon1/", 1)[1])
    return p if p.parts[0] in ROUNDS and ".." not in p.parts else None


def save_version(data, rel, receipt, versions):
    digest = sha(data)
    target = ARCHIVE / digest / rel.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == data
    else:
        target.write_bytes(data)
    versions.append(dict(receipt, relative_path=str(rel), archive=str(target.relative_to(ROOT)), sha256=digest, bytes=len(data)))


def content_text(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))


def main():
    versions, events, feedback, galleries, missing, edits_failed = [], [], [], [], [], []
    files = [RECORD] + sorted((RECORD.with_suffix("") / "subagents").glob("*.jsonl"))
    sources = []
    for path in files:
        sources.append({"path": str(path), "sha256": sha(path.read_bytes()), "bytes": path.stat().st_size})
        uses = {}
        for line_no, line in enumerate(path.open(), 1):
            record = json.loads(line)
            receipt = {"transcript": str(path), "line": line_no, "uuid": record.get("uuid"), "timestamp": record.get("timestamp")}
            content = record.get("message", {}).get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if block.get("type") == "tool_use":
                    uses[block["id"]] = (block, receipt)
                elif block.get("type") == "tool_result":
                    use = uses.get(block.get("tool_use_id"))
                    if use is None or block.get("is_error"):
                        continue
                    call, call_receipt = use
                    inp, name = call.get("input", {}), call.get("name")
                    original = inp.get("file_path", "")
                    rel = relative(original)
                    result = block.get("content", [])
                    evidence = dict(receipt, call_line=call_receipt["line"], tool_use_id=call["id"], original_path=original)
                    if rel and name == "Read" and rel.suffix == ".png":
                        for part in result if isinstance(result, list) else []:
                            source = part.get("source", {})
                            if part.get("type") == "image" and source.get("type") == "base64":
                                data = base64.b64decode(source["data"], validate=True)
                                if data.startswith(b"\x89PNG\r\n\x1a\n"):
                                    image_rel = rel
                                elif data.startswith(b"\xff\xd8\xff"):
                                    image_rel = rel.with_suffix(".jpg")
                                else:
                                    raise ValueError(f"Unknown image encoding at {path}:{line_no}")
                                save_version(data, image_rel, dict(evidence, media_type=source.get("media_type"), method="Read image result; may be downscaled or transcoded by original reader"), versions)
                    if rel and rel.suffix in {".html", ".json", ".md"} and name in {"Write", "Edit"}:
                        events.append((call_receipt.get("timestamp") or "", name, rel, inp, evidence))
                    text = content_text(result)
                    if name == "Artifact" and text.startswith("[Artifact"):
                        match = re.search(r"full HTML saved to (.+?\.html)", text)
                        if match:
                            saved = Path(match.group(1))
                            if saved.exists():
                                raw = saved.read_bytes()
                                dest = ARCHIVE / sha(raw) / saved.name
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                dest.write_bytes(raw)
                                galleries.append(dict(evidence, path=str(saved), archive=str(dest.relative_to(ROOT)), sha256=sha(raw), url=inp.get("url")))
                            else:
                                missing.append({"path": str(saved), "receipt": evidence})
                        for match in re.finditer(r'<script[^>]*id="fb-state"[^>]*>(.*?)</script>', text, re.S):
                            feedback.append(dict(evidence, url=inp.get("url"), state=json.loads(match.group(1))))
                    if name == "Bash":
                        command = inp.get("command", "")
                        # Only literal absolute-path heredocs; never run a command from a transcript.
                        for match in re.finditer(r"cat\s*>\s*['\"]?(/[^\s'\"]+)['\"]?\s*<<\s*['\"]?(\w+)['\"]?\n(.*?)\n\2(?:\n|$)", command, re.S):
                            bash_rel = relative(match.group(1))
                            if bash_rel and bash_rel.suffix == ".html":
                                events.append((call_receipt.get("timestamp") or "", "Write", bash_rel, {"content": match.group(3) + "\n"}, dict(evidence, original_path=match.group(1), method="literal heredoc, not executed")))
    current = {}
    for _, name, rel, inp, receipt in sorted(events, key=lambda row: row[0]):
        if name == "Write":
            text = inp["content"]
        else:
            old = inp.get("old_string", "")
            before = current.get(str(rel))
            if before is None or not old or old not in before or (not inp.get("replace_all") and before.count(old) != 1):
                edits_failed.append(dict(receipt, relative_path=str(rel), reason="No exact unique predecessor; edit not guessed"))
                continue
            text = before.replace(old, inp.get("new_string", ""), -1 if inp.get("replace_all") else 1)
        current[str(rel)] = text
        save_version(text.encode(), rel, dict(receipt, method=receipt.get("method", "successful " + name + " replay")), versions)
    # Latest recoverable version is a source reconstruction, not proof of final rendered identity.
    selected = {}
    for version in sorted(versions, key=lambda row: row.get("timestamp") or ""):
        selected[version["relative_path"]] = version
    for rel, version in selected.items():
        target = CORPUS / rel
        data = (ROOT / version["archive"]).read_bytes()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != data:
            raise RuntimeError(f"Refusing to replace existing evidence: {target}")
        target.write_bytes(data)
        version["selected_path"] = str(target.relative_to(ROOT))
    manifest = dict(sources=sources, versions=versions, selected=list(selected.values()), galleries=galleries, feedback=feedback, missing=missing, edits_not_replayed=edits_failed)
    (HERE / "recovery.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"transcripts": len(sources), "versions": len(versions), "selected": len(selected), "galleries": len(galleries), "missing_saved_galleries": len(missing), "edits_not_replayed": len(edits_failed)}))


if __name__ == "__main__":
    main()
