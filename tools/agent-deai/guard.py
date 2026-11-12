"""Advisory Git-index prose checks using the canonical deai engine."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess

import deai

PROSE_SUFFIXES = {".md", ".markdown", ".rst", ".txt"}
START = "# >>> agent-do deai guard >>>\n"
END = "# <<< agent-do deai guard <<<\n"


def git(*args, cwd=None):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip() or "Git command failed")
    return result.stdout


def check(register):
    payload = {"schema": "deai-guard-v1", "tool": "deai", "command": "guard check",
               "advisory": True, "register": register, "success": True, "clean": True,
               "files": [], "skipped": [], "errors": []}
    try:
        catalog, packs = deai.load()
        root = os.fsdecode(git("rev-parse", "--show-toplevel").removesuffix(b"\n"))
        # One index snapshot supplies both names and immutable blob IDs. Disabling
        # rename detection gives one NUL-delimited path per record, even for renames.
        records = git("diff", "--cached", "--raw", "--no-abbrev", "--no-renames",
                      "--no-ext-diff", "--no-textconv", "--diff-filter=ACM", "-z", "--", cwd=root).split(b"\0")
        for offset in range(0, len(records) - 1, 2):
            header, raw_path = records[offset:offset + 2]
            path = os.fsdecode(raw_path)
            if Path(path).suffix.lower() not in PROSE_SUFFIXES:
                continue
            _, mode, _, blob, _ = header.split()
            if mode not in (b"100644", b"100755"):
                payload["skipped"].append({"path": path, "reason": "not a regular file"})
                continue
            try:
                raw = git("cat-file", "blob", blob.decode("ascii"), cwd=root)
                if b"\0" in raw:
                    payload["skipped"].append({"path": path, "reason": "binary content"})
                    continue
                result = deai.lint_text(raw.decode("utf-8"), catalog, packs[register])
                payload["files"].append({"path": path, "blob": blob.decode("ascii"), **result})
            except (OSError, UnicodeError, ValueError) as exc:
                payload["errors"].append({"path": path, "error": str(exc)})
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, re.error) as exc:
        payload["errors"].append({"error": str(exc)})
    payload["success"] = not payload["errors"]
    payload["clean"] = payload["success"] and all(item["clean"] for item in payload["files"])
    payload["total_files"] = len(payload["files"])
    payload["total_findings"] = sum(len(item["findings"]) for item in payload["files"])
    return payload


def install(register):
    root = Path(os.fsdecode(git("rev-parse", "--show-toplevel").removesuffix(b"\n")))
    hooks = Path(os.fsdecode(git("rev-parse", "--git-path", "hooks", cwd=root).removesuffix(b"\n")))
    if not hooks.is_absolute():
        hooks = root / hooks
    hook = hooks / "pre-commit"
    if hook.is_symlink():
        raise ValueError("pre-commit is a symlink; add `agent-do deai guard check || true` in its owner")
    content = hook.read_bytes().decode("utf-8") if hook.exists() else "#!/bin/sh\n"
    first, separator, body = content.partition("\n")
    interpreter = shlex.split(first[2:]) if first.startswith("#!") else []
    if interpreter and Path(interpreter[0]).name == "env":
        interpreter = interpreter[1:]
        if interpreter[:1] == ["-S"]:
            interpreter = interpreter[1:]
    if not interpreter or Path(interpreter[0]).name not in ("sh", "bash", "dash", "ksh", "zsh"):
        raise ValueError("existing pre-commit is not a shell hook; call `agent-do deai guard check` from its owner")
    dispatcher = deai.HERE.parents[1] / "agent-do"
    command = f"{shlex.quote(str(dispatcher))} deai guard check --register {shlex.quote(register)}"
    block = (START + "# Advisory only. Existing commit gates keep their exit status.\n"
             + f"if {command}; then :; else\n"
             + "  printf '%s\\n' 'deai guard WARN: prose check unavailable; commit continues.' >&2\n"
             + "fi\n" + END)
    if START in body or END in body:
        if body.count(START) != 1 or body.count(END) != 1 or body.index(END) < body.index(START):
            raise ValueError("pre-commit contains an incomplete or duplicate deai guard block")
        start = body.index(START)
        end = body.index(END) + len(END)
        updated = first + separator + body[:start] + block + body[end:]
    else:
        # Prepend after the shebang: appending would silently miss hooks ending in exit.
        updated = first + "\n" + block + body
    already = updated == content
    hooks.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(hook.stat().st_mode) if hook.exists() else 0o644
    if not already:
        hook.write_bytes(updated.encode("utf-8"))
    hook.chmod(mode | 0o111)
    return {"schema": "deai-guard-v1", "tool": "deai", "command": "guard install",
            "success": True, "installed": True, "already_installed": already,
            "hook": str(hook.absolute()), "register": register}


def run(args):
    payload = check(args.register) if args.guard_command == "check" else install(args.register)
    if args.json:
        print(json.dumps(payload, indent=2))
    elif args.guard_command == "install":
        print(f"deai guard: installed advisory pre-commit check at {payload['hook']}")
    else:
        for item in payload["files"]:
            for finding in item["findings"]:
                for hit in finding["occurrences"]:
                    print(f"deai guard WARN: staged {item['path']!r}:{hit['line']}:{hit['column']}: "
                          f"{hit['text']!r} [{finding['rule']}]")
        for item in payload["errors"]:
            print(f"deai guard WARN: could not check {item.get('path', 'staged prose')!r}: {item['error']}")
        for item in payload["skipped"]:
            print(f"deai guard: skipped {item['path']!r} ({item['reason']})")
        if payload["total_findings"] or payload["errors"]:
            print("deai guard: advisory only; commit continues. No files were rewritten.")
    # Findings and unavailable checks are advisory. Installation errors are handled
    # by the normal CLI error path and retain its nonzero status.
    return 0
