#!/usr/bin/env python3
"""Codex SessionStart hook: inject compact agent-do project context."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def read_payload() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def resolve_agent_do() -> str | None:
    direct = shutil.which("agent-do")
    if direct:
        return direct

    local = Path.home() / ".local" / "bin" / "agent-do"
    if local.exists():
        return str(local)

    breadcrumb = Path.home() / ".agent-do" / "install-path"
    if breadcrumb.exists():
        candidate = Path(breadcrumb.read_text().strip()) / "agent-do"
        if candidate.exists():
            return str(candidate)

    return None


def run_json(cmd: list[str], cwd: str | None = None) -> dict:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=4,
            check=False,
        )
    except Exception:
        return {}
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {}


def run_capture(cmd: list[str], cwd: str | None = None, timeout: int = 10) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return (1, "", "")
    return (proc.returncode, proc.stdout, proc.stderr)


def native_bootstrap(agent_do: str, cwd: str | None, ask: str, root: str) -> bool:
    mode = os.environ.get("AGENT_DO_BOOTSTRAP_PROMPT_MODE", "").strip().lower()
    if not mode:
        mode = "native" if sys.platform == "darwin" and shutil.which("osascript") else "context"

    if mode == "disabled":
        return True
    if mode != "native":
        return False

    auto_response = os.environ.get("AGENT_DO_BOOTSTRAP_AUTO_RESPONSE", "").strip().lower()
    if auto_response == "bootstrap":
        response = "Bootstrap"
    elif auto_response == "not_now":
        response = "Not now"
    else:
        if not shutil.which("osascript"):
            return False
        code, stdout, _ = run_capture(
            [
                "osascript",
                "-e",
                (
                    f'display dialog {json.dumps(ask)} '
                    'with title "agent-do Bootstrap" '
                    'buttons {"Not now", "Bootstrap"} default button "Bootstrap"\n'
                    "button returned of result"
                ),
            ],
            timeout=15,
        )
        if code != 0:
            return False
        response = stdout.strip()

    if response == "Bootstrap":
        # Capture output to a log; emit a macOS notification with status; on
        # failure also surface a follow-up dialog with the option to view the
        # log. Without this the user clicks Bootstrap and sees nothing.
        log_dir = Path.home() / ".agent-do" / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            log_dir = Path("/tmp")
        timestamp = subprocess.run(
            ["date", "+%Y%m%d-%H%M%S"], capture_output=True, text=True, check=False
        ).stdout.strip() or "now"
        log_file = log_dir / f"bootstrap-{timestamp}-{os.getpid()}.log"
        project_label = Path(root).name or root

        try:
            with log_file.open("w") as fh:
                fh.write(f"agent-do bootstrap --yes\nproject: {root}\nstarted: {timestamp}\n---\n")
                fh.flush()
                completed = subprocess.run(
                    [agent_do, "bootstrap", "--yes"],
                    cwd=root,
                    stdout=fh,
                    stderr=subprocess.STDOUT,
                    timeout=60,
                    check=False,
                )
            run_exit = completed.returncode
        except subprocess.TimeoutExpired:
            run_exit = 124
        except Exception:
            run_exit = 1

        if shutil.which("osascript"):
            if run_exit == 0:
                subprocess.run(
                    [
                        "osascript",
                        "-e",
                        f'display notification "Bootstrap completed for {project_label}. Log: {log_file}" '
                        f'with title "agent-do Bootstrap" sound name "Glass"',
                    ],
                    check=False,
                )
            else:
                subprocess.run(
                    [
                        "osascript",
                        "-e",
                        f'display notification "Bootstrap FAILED for {project_label} (exit {run_exit}). Log: {log_file}" '
                        f'with title "agent-do Bootstrap" sound name "Basso"',
                    ],
                    check=False,
                )
                # Failure dialog with "Open log" option.
                failure_message = (
                    f"agent-do bootstrap failed (exit {run_exit}) for {project_label}."
                    + "\n\n"
                    + f"Log: {log_file}"
                )
                code, choice, _ = run_capture(
                    [
                        "osascript",
                        "-e",
                        (
                            f'display dialog {json.dumps(failure_message)} '
                            'with title "agent-do Bootstrap failed" '
                            'buttons {"Dismiss", "Open log"} default button "Open log"\n'
                            "button returned of result"
                        ),
                    ],
                    timeout=15,
                )
                if code == 0 and choice.strip() == "Open log" and shutil.which("open"):
                    subprocess.run(["open", str(log_file)], check=False)
        else:
            status = "completed" if run_exit == 0 else f"FAILED (exit {run_exit})"
            print(f"[agent-do bootstrap] {status} for {project_label}. Log: {log_file}", file=sys.stderr)
    return True


def is_frontend_project(cwd: str | None) -> bool:
    if not cwd:
        return False
    root = Path(cwd)
    package = root / "package.json"
    frontend_tokens = (
        "react",
        "next",
        "vue",
        "nuxt",
        "svelte",
        "astro",
        "angular",
        "remix",
        "gatsby",
        "solid-js",
    )
    if package.exists():
        text = package.read_text(errors="ignore").lower()
        if any(f'"{token}"' in text for token in frontend_tokens):
            return True
    for rel in ("src", "app", "apps", "components", "pages"):
        directory = root / rel
        if not directory.exists():
            continue
        for ext in ("*.tsx", "*.jsx", "*.vue", "*.svelte", "*.astro"):
            if next(directory.glob(f"**/{ext}"), None):
                return True
    pubspec = root / "pubspec.yaml"
    return pubspec.exists() and "flutter" in pubspec.read_text(errors="ignore").lower()


def project_tools(agent_do: str, cwd: str | None) -> str:
    if not cwd:
        return ""
    data = run_json([agent_do, "suggest", "--project", "--json", "--cwd", cwd, "--limit", "5"])
    results = data.get("results") or []
    if not results:
        return ""
    lines = []
    for item in results[:5]:
        tool = item.get("tool")
        primary = item.get("primary") or f"agent-do {tool} --help"
        if tool:
            lines.append(f"- {tool}: start with `{primary}`")
    if not lines:
        return ""
    signals = ", ".join(data.get("signals") or []) or "general"
    project = data.get("project") or cwd
    return (
        "## Project-Scoped agent-do Tools\n\n"
        f"Project root: `{project}`\n"
        f"Detected signals: `{signals}`\n\n"
        + "\n".join(lines)
        + "\n\nRefresh with `agent-do suggest --project`.\n"
    )


def bootstrap(agent_do: str, cwd: str | None) -> str:
    if not cwd:
        return ""
    data = run_json([agent_do, "bootstrap", "--recommend", "--json", "--cwd", cwd])
    if not data.get("needs_bootstrap"):
        return ""
    ask = data.get("ask_prompt") or "Run agent-do bootstrap for this project?"
    root = data.get("project_root") or cwd
    commands = "\n".join(data.get("commands") or [])
    if native_bootstrap(agent_do, cwd, ask, root):
        return ""
    return (
        "## Bootstrap Opportunity\n\n"
        "At the start of your first reply in this session, ask exactly one short yes/no question:\n"
        f"`{ask}`\n\n"
        "If the user says yes, run `agent-do bootstrap --yes` from:\n"
        f"`{root}`\n\n"
        f"Planned bootstrap:\n```text\n{commands}\n```\n"
    )


def coord(agent_do: str, cwd: str | None) -> str:
    if not cwd:
        return ""
    touch = run_json([agent_do, "coord", "touch", "--json"], cwd=cwd)
    if not touch:
        return ""

    interrupts = run_json(
        [agent_do, "coord", "interrupts", "--json", "--mark-seen", "--limit", "5"],
        cwd=cwd,
    ).get("interrupts") or []
    if interrupts:
        lines = [
            f"- {'[new] ' if item.get('new') else ''}{item.get('kind')}: {item.get('summary')}"
            for item in interrupts
        ]
        return (
            "## Coord Interrupts\n\n"
            "Relevant coordination interrupts are active in this repo:\n"
            + "\n".join(lines)
            + "\n\nUse `agent-do coord status`, `agent-do coord interrupts`, or `agent-do coord focus show`.\n"
        )

    active = touch.get("active_peers") or []
    focus_goal = ((touch.get("focus") or {}).get("goal")) or ""
    if active and not focus_goal:
        lines = []
        for peer in active:
            label = peer.get("alias") or peer.get("agent_id")
            goal = ((peer.get("focus") or {}).get("goal")) or ""
            lines.append(f"- {label}{f' goal: {goal}' if goal else ''}")
        return (
            "## Coord Focus Reminder\n\n"
            "Other active peers exist in this repo, and you have not declared focus yet.\n"
            + "\n".join(lines)
            + "\n\nSet focus before overlapping work starts:\n"
            "`agent-do coord focus set \"<goal>\" --path <path> [--path <path> ...]`\n"
        )
    return ""


def zpc(cwd: str | None) -> str:
    if cwd and (Path(cwd) / ".zpc").exists():
        return (
            "## ZPC Memory Available\n\n"
            "This project has `.zpc/` memory. Start with `agent-do zpc status` and "
            "`agent-do zpc patterns` before coding.\n"
        )
    return ""


def frontend_context(cwd: str | None) -> str:
    if not is_frontend_project(cwd):
        return ""
    return (
        "## Frontend Project Detected\n\n"
        "For visual/UI work, use screenshots as visual truth and `agent-do dpt` for scoring:\n"
        "- `agent-do browse open <dev-url>`\n"
        "- `agent-do browse screenshot /tmp/before.png`\n"
        "- after edits: `agent-do browse reload && agent-do browse screenshot /tmp/after.png`\n"
        "- `agent-do dpt score /tmp/after.png`\n\n"
        "Use Codex UI skills when applicable, especially `building-ui` and `layout-rhythm-repair`.\n"
    )


def main() -> None:
    payload = read_payload()
    cwd = payload.get("cwd") or os.getcwd()
    agent_do = resolve_agent_do()

    sections = [
        "## TOOLING REMINDER - agent-do\n\n"
        "Before writing raw automation or vendor API glue, check whether `agent-do` already has the path:\n"
        "`agent-do suggest \"task\"`, `agent-do suggest --project`, `agent-do find <keyword>`, "
        "`agent-do --list`, `agent-do <tool> --help`.\n"
    ]

    if agent_do:
        sections.extend(
            part
            for part in (
                project_tools(agent_do, cwd),
                bootstrap(agent_do, cwd),
                coord(agent_do, cwd),
            )
            if part
        )
    sections.extend(part for part in (frontend_context(cwd), zpc(cwd)) if part)

    context = "\n---\n\n".join(sections)
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
