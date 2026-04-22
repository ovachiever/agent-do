#!/usr/bin/env python3
"""Focused routing and nudge regression tests for v1.1."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from registry import load_registry, match_prompt_tools, find_raw_cli_equivalent  # noqa: E402


def run(*args: str, input_text: str | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=ROOT,
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    registry = load_registry()

    vercel_matches = match_prompt_tools(registry, "deploy this on vercel and check logs", limit=3)
    require(vercel_matches, "expected shared prompt matches for vercel")
    require(vercel_matches[0]["tool"] == "vercel", f"unexpected top prompt match: {vercel_matches}")

    resend_matches = match_prompt_tools(registry, "verify resend dkim and spf records for this domain", limit=3)
    require(resend_matches, "expected shared prompt matches for resend")
    require(resend_matches[0]["tool"] == "resend", f"unexpected resend prompt match: {resend_matches}")

    browse_equivalent = find_raw_cli_equivalent(registry, "npx playwright test")
    require(browse_equivalent is not None, "expected a shared raw-command equivalent for playwright")
    require(browse_equivalent["tool"] == "browse", f"unexpected raw equivalent: {browse_equivalent}")
    require(
        browse_equivalent["replacement"] == "agent-do browse",
        f"unexpected browse replacement: {browse_equivalent}",
    )

    prompt_result = run(
        "python3",
        "hooks/agent-do-prompt-router.py",
        input_text='{"prompt":"deploy this on vercel and check logs"}',
    )
    require(prompt_result.returncode == 0, f"prompt-router failed: {prompt_result.stderr}")
    prompt_payload = json.loads(prompt_result.stdout)
    prompt_context = prompt_payload["hookSpecificOutput"]["additionalContext"]
    require(
        "agent-do vercel deploy" in prompt_context,
        f"expected concrete vercel deploy suggestion, got: {prompt_context}",
    )

    dpt_result = run(
        "python3",
        "hooks/agent-do-prompt-router.py",
        input_text='{"prompt":"check the design quality of this page"}',
    )
    require(dpt_result.returncode == 0, f"dpt prompt-router failed: {dpt_result.stderr}")
    dpt_payload = json.loads(dpt_result.stdout)
    dpt_context = dpt_payload["hookSpecificOutput"]["additionalContext"]
    require("agent-do dpt score" in dpt_context, f"expected DPT routing context, got: {dpt_context}")

    spec_prompt_result = run(
        "python3",
        "hooks/agent-do-prompt-router.py",
        input_text='{"prompt":"write a change proposal and spec package for this feature"}',
    )
    require(spec_prompt_result.returncode == 0, f"spec prompt-router failed: {spec_prompt_result.stderr}")
    spec_prompt_payload = json.loads(spec_prompt_result.stdout)
    spec_prompt_context = spec_prompt_payload["hookSpecificOutput"]["additionalContext"]
    require("agent-do spec" in spec_prompt_context, f"expected spec routing context, got: {spec_prompt_context}")

    completion_prompts = [
        "continue",
        "agreed, continue",
        "what's left",
        "how's it going",
        "where we at",
    ]
    for completion_prompt in completion_prompts:
        completion_result = run(
            "python3",
            "hooks/agent-do-prompt-router.py",
            input_text=json.dumps({"prompt": completion_prompt}),
        )
        require(completion_result.returncode == 0, f"completion prompt-router failed: {completion_result.stderr}")
        completion_payload = json.loads(completion_result.stdout)
        completion_context = completion_payload["hookSpecificOutput"]["additionalContext"]
        require("## Completion Check" in completion_context, f"expected completion check context, got: {completion_context}")
        require("primary goal is already complete" in completion_context, f"unexpected completion check wording: {completion_context}")

    playwright_nudge = run(
        "python3",
        "hooks/agent-do-pretooluse-check.py",
        input_text='{"tool_name":"Bash","tool_input":{"command":"npx playwright test"}}',
    )
    require(playwright_nudge.returncode == 0, f"pretool hook failed: {playwright_nudge.stderr}")
    playwright_payload = json.loads(playwright_nudge.stdout)
    playwright_context = playwright_payload["hookSpecificOutput"]["additionalContext"]
    require("HARD NUDGE:" in playwright_context, f"expected hard nudge wording, got: {playwright_context}")
    require("agent-do browse" in playwright_context, f"expected browse replacement, got: {playwright_context}")

    ios_nudge = run(
        "python3",
        "hooks/agent-do-pretooluse-check.py",
        input_text='{"tool_name":"Bash","tool_input":{"command":"xcrun simctl io booted screenshot /tmp/out.png"}}',
    )
    require(ios_nudge.returncode == 0, f"ios pretool hook failed: {ios_nudge.stderr}")
    ios_payload = json.loads(ios_nudge.stdout)
    ios_context = ios_payload["hookSpecificOutput"]["additionalContext"]
    require("agent-do ios screenshot" in ios_context, f"expected ios replacement, got: {ios_context}")

    offline = run("python3", "bin/pattern-matcher", "--json", "deploy this on vercel")
    require(offline.returncode == 0, f"pattern matcher failed: {offline.stderr}")
    offline_payload = json.loads(offline.stdout)
    require(offline_payload["tool"] == "vercel", f"unexpected offline tool: {offline_payload}")
    require(offline_payload["command"] == "deploy", f"unexpected offline command: {offline_payload}")
    require(
        offline_payload.get("from_registry_routing") is True,
        f"expected registry-driven offline routing, got: {offline_payload}",
    )

    suggest = run("./agent-do", "suggest", "deploy this on vercel", "--json")
    require(suggest.returncode == 0, f"suggest failed: {suggest.stderr}")
    suggest_payload = json.loads(suggest.stdout)
    require(suggest_payload["results"], f"expected suggest results, got: {suggest_payload}")
    require(suggest_payload["results"][0]["tool"] == "vercel", f"unexpected suggest result: {suggest_payload}")

    find = run("./agent-do", "find", "playwright", "--json")
    require(find.returncode == 0, f"find failed: {find.stderr}")
    find_payload = json.loads(find.stdout)
    require(find_payload["results"], f"expected find results, got: {find_payload}")
    require(find_payload["results"][0]["tool"] == "browse", f"unexpected find result: {find_payload}")

    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)
        (project / "package.json").write_text('{"dependencies":{"next":"15.0.0"}}', encoding="utf-8")
        (project / "vercel.json").write_text("{}", encoding="utf-8")
        (project / "README.md").write_text("Use agent-do browse for web verification", encoding="utf-8")

        project_suggest = run("./agent-do", "suggest", "--project", "--cwd", str(project), "--json")
        require(project_suggest.returncode == 0, f"project suggest failed: {project_suggest.stderr}")
        project_payload = json.loads(project_suggest.stdout)
        require("vercel" in project_payload["signals"], f"expected vercel signal, got: {project_payload}")
        require(project_payload["results"], f"expected project results, got: {project_payload}")
        require(
            project_payload["results"][0]["tool"] in {"vercel", "browse"},
            f"unexpected project top tool: {project_payload}",
        )

        hook_input = json.dumps({"cwd": str(project)})
        session_hook = run("bash", "hooks/agent-do-session-start.sh", input_text=hook_input)
        require(session_hook.returncode == 0, f"session hook failed: {session_hook.stderr}")
        session_payload = json.loads(session_hook.stdout)
        additional = session_payload["hookSpecificOutput"]["additionalContext"]
        require("Project-Scoped agent-do Tools" in additional, f"expected project tooling section, got: {additional}")
        require("agent-do suggest --project" in additional, f"expected project discovery hint, got: {additional}")

    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        (project / "README.md").write_text("coord hook test", encoding="utf-8")

        env = os.environ.copy()
        env["AGENT_DO_HOME"] = str(project / ".agent-do-home")

        first_env = dict(env)
        first_env["CODEX_THREAD_ID"] = "alpha-123"
        first_hook = run(
            "bash",
            "hooks/agent-do-session-start.sh",
            input_text=json.dumps({"cwd": str(project)}),
            env=first_env,
        )
        require(first_hook.returncode == 0, f"first coord session hook failed: {first_hook.stderr}")
        first_payload = json.loads(first_hook.stdout)
        first_additional = first_payload["hookSpecificOutput"]["additionalContext"]
        require("Active Agent Peers" not in first_additional, f"unexpected coord peer context for first session: {first_additional}")

        second_env = dict(env)
        second_env["CODEX_THREAD_ID"] = "beta-456"
        second_hook = run(
            "bash",
            "hooks/agent-do-session-start.sh",
            input_text=json.dumps({"cwd": str(project)}),
            env=second_env,
        )
        require(second_hook.returncode == 0, f"second coord session hook failed: {second_hook.stderr}")
        second_payload = json.loads(second_hook.stdout)
        second_additional = second_payload["hookSpecificOutput"]["additionalContext"]
        require("Active Agent Peers" in second_additional, f"expected coord peer context, got: {second_additional}")
        require("agent-do coord inbox" in second_additional, f"expected coord inbox hint, got: {second_additional}")
        require("reviewer" not in second_additional, "unexpected alias text before aliases were set")

    with tempfile.TemporaryDirectory() as telemetry_home:
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = telemetry_home

        clear = run("./agent-do", "nudges", "clear", "--json", env=env)
        require(clear.returncode == 0, f"nudges clear failed: {clear.stderr}")

        _ = run(
            "python3",
            "hooks/agent-do-prompt-router.py",
            input_text='{"prompt":"deploy this on vercel"}',
            env=env,
        )
        _ = run(
            "python3",
            "hooks/agent-do-prompt-router.py",
            input_text='{"prompt":"continue"}',
            env=env,
        )
        _ = run(
            "python3",
            "hooks/agent-do-pretooluse-check.py",
            input_text='{"tool_name":"Bash","tool_input":{"command":"npx playwright test"}}',
            env=env,
        )

        stats = run("./agent-do", "nudges", "stats", "--json", env=env)
        require(stats.returncode == 0, f"nudges stats failed: {stats.stderr}")
        stats_payload = json.loads(stats.stdout)
        require(stats_payload["total_events"] >= 3, f"expected telemetry events, got: {stats_payload}")
        require("prompt_router" in stats_payload["sources"], f"missing prompt router telemetry: {stats_payload}")
        require("pretool" in stats_payload["sources"], f"missing pretool telemetry: {stats_payload}")

    with tempfile.TemporaryDirectory() as cache_home:
        cache_code = """
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path('lib').resolve()))
from cache import cache_result, check_cache, fuzzy_match, note_route_outcome

project_a = '/tmp/project-a'
project_b = '/tmp/project-b'

cache_result('deploy app', {'tool': 'render', 'command': 'deploy'}, project_scope=project_a, route_source='llm')
cache_result('deploy app', {'tool': 'vercel', 'command': 'deploy'}, project_scope='', route_source='llm')
note_route_outcome('deploy app', {'tool': 'render', 'command': 'deploy'}, success=True, project_scope=project_a, route_source='llm')
note_route_outcome('deploy app', {'tool': 'vercel', 'command': 'deploy'}, success=False, project_scope='', route_source='llm')

cache_result('deploy service', {'tool': 'render', 'command': 'deploy'}, project_scope=project_a, route_source='llm')
note_route_outcome('deploy service', {'tool': 'render', 'command': 'deploy'}, success=True, project_scope=project_a, route_source='llm')
cache_result('deploy site', {'tool': 'vercel', 'command': 'deploy'}, project_scope='', route_source='llm')
note_route_outcome('deploy site', {'tool': 'vercel', 'command': 'deploy'}, success=False, project_scope='', route_source='llm')

print(json.dumps({
  'exact_project': check_cache('deploy app', project_scope=project_a),
  'exact_global': check_cache('deploy app', project_scope=project_b),
  'fuzzy_project': fuzzy_match('deploy production app', threshold=0.2, project_scope=project_a),
}))
"""
        env = os.environ.copy()
        env["AGENT_DO_HOME"] = cache_home
        cache_proc = run("python3", "-c", cache_code, env=env)
        require(cache_proc.returncode == 0, f"cache regression script failed: {cache_proc.stderr}")
        cache_payload = json.loads(cache_proc.stdout)
        require(cache_payload["exact_project"]["tool"] == "render", f"expected project-scoped exact cache, got: {cache_payload}")
        require(cache_payload["exact_global"]["tool"] == "vercel", f"expected global exact cache, got: {cache_payload}")
        require(cache_payload["fuzzy_project"]["tool"] == "render", f"expected fuzzy project bias toward render, got: {cache_payload}")

    print("v1.1 routing tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
