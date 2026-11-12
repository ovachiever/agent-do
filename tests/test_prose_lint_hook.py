#!/usr/bin/env python3
"""Execute the prose hook and real deai CLI in isolated filesystem fixtures.

No installer, live hook configuration, app, or host session is started.
Failure injection covers the CLI boundary separately from real lint receipts.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks/claude/agent-do-prose-lint.py"
spec = importlib.util.spec_from_file_location("prose_lint_hook", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class ProseLintHookTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()
        self.env = dict(os.environ, AGENT_DO_HOME=str(self.root / "agent-home"),
                        AGENT_DO_REPO=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
        self.env.pop("AGENT_DO_PROSE_LINT", None)

    def payload(self, name="README.md", content="It is worth noting that the gate opened.\n", tool="Write"):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"hook_event_name": "PostToolUse", "session_id": "prose-hook-fixture",
                "cwd": str(self.project), "tool_name": tool,
                "tool_input": {"file_path": str(path), "content": content}}

    def invoke(self, payload, *, raw=None, env=None):
        result = subprocess.run([sys.executable, str(HOOK)],
                                input=json.dumps(payload) if raw is None else raw,
                                cwd=self.root, env=env or self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def context(self, result):
        self.assertEqual(set(result), {"hookSpecificOutput"})
        output = result["hookSpecificOutput"]
        self.assertEqual(set(output), {"hookEventName", "additionalContext"})
        self.assertEqual(output["hookEventName"], "PostToolUse")
        return output["additionalContext"]

    def in_process(self, payload):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            hook.run(payload)
        return json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}

    def test_write_calls_real_deai_and_preserves_file(self):
        payload = self.payload(content="# Note\n\nIt is worth noting that the gate opened.\n")
        path = Path(payload["tool_input"]["file_path"])
        before = path.read_bytes()
        message = self.context(self.invoke(payload))
        self.assertIn("README.md (register: default)", message)
        self.assertIn("3:1", message)
        self.assertIn("agent-do deai lint", message)
        self.assertIn("before finishing", message)
        self.assertEqual(path.read_bytes(), before)

    def test_edit_uses_saved_document_and_real_file_locations(self):
        payload = self.payload(content="The gate opened.\n\nIt is worth noting that rain fell.\n", tool="Edit")
        payload["tool_input"] = {"file_path": payload["tool_input"]["file_path"],
                                 "old_string": "rain stopped", "new_string": "rain fell"}
        message = self.context(self.invoke(payload))
        self.assertIn("3:1", message)
        path = Path(payload["tool_input"]["file_path"])
        path.write_text("The gate opened.\n", encoding="utf-8")
        payload["tool_input"]["new_string"] = "It is worth noting that this is stale input."
        self.assertEqual(self.invoke(payload), {})

    def test_edit_keeps_code_fence_and_frontmatter_context(self):
        text = '---\nexample: "it is worth noting"\n---\n\n```text\nit is worth noting\n```\nThe gate opened.\n'
        payload = self.payload(content=text, tool="Edit")
        payload["tool_input"]["new_string"] = "it is worth noting"
        self.assertEqual(self.invoke(payload), {})

    def test_every_revision_is_checked_without_a_session_cooldown(self):
        payload = self.payload(tool="MultiEdit")
        self.context(self.invoke(payload))
        path = Path(payload["tool_input"]["file_path"])
        path.write_text("The gate opened.\n", encoding="utf-8")
        self.assertEqual(self.invoke(payload), {})
        path.write_text(payload["tool_input"]["content"], encoding="utf-8")
        self.context(self.invoke(payload))

    def test_drafts_select_real_essay_policy_while_docs_keep_technical_language(self):
        for name, flagged in (("docs/design.md", False), ("drafts/design.md", True)):
            with self.subTest(name=name):
                result = self.invoke(self.payload(name, "The architecture is structural.\n"))
                if flagged:
                    self.assertIn("register: essay", self.context(result))
                else:
                    self.assertEqual(result, {})

    def test_other_register_directories(self):
        for name, register in (("essays/a.markdown", "essay"), ("email/a.txt", "email"),
                               ("emails/a.rst", "email"), ("product-answers/a.md", "product-answer"),
                               ("product_answers/a.MD", "product-answer"),
                               ("drafts/emails/a.md", "email")):
            with self.subTest(name=name):
                self.assertIn(f"register: {register}", self.context(self.invoke(self.payload(name))))

    def test_relative_path_with_spaces_and_nested_working_directory(self):
        payload = self.payload("drafts/- quoted ' draft.md", "The architecture is structural.\n")
        payload["cwd"] = str(self.project / "drafts")
        payload["tool_input"]["file_path"] = "- quoted ' draft.md"
        message = self.context(self.invoke(payload))
        self.assertIn("register: essay", message)
        self.assertIn("- quoted ' draft.md", message)

    def test_source_and_generated_paths_never_invoke_deai(self):
        for name in ("drafts/a.py", "drafts/a.ts", "drafts/a.json", "drafts/a.yaml", "drafts/a.mdx",
                     "node_modules/a.md", ".git/a.md", ".venv/a.txt", "vendor/a.md", "build/a.md"):
            with self.subTest(name=name), patch.object(hook, "lint") as lint:
                self.assertEqual(self.in_process(self.payload(name)), {})
                lint.assert_not_called()

    def test_symlink_to_code_does_not_treat_source_as_prose(self):
        target = self.project / "source.py"
        target.write_text("it is worth noting", encoding="utf-8")
        alias = self.project / "source.md"
        alias.symlink_to(target)
        payload = {"tool_name": "Write", "cwd": str(self.project),
                   "tool_input": {"file_path": str(alias)}}
        self.assertEqual(self.invoke(payload), {})

    def test_other_events_and_failed_tools_are_silent(self):
        payload = self.payload()
        for overrides in ({"hook_event_name": "PreToolUse"}, {"tool_name": "Bash"},
                          {"tool_response": {"is_error": True}}, {"tool_response": {"success": False}}):
            with self.subTest(overrides=overrides):
                self.assertEqual(self.invoke({**payload, **overrides}), {})

    def test_disabled_and_malformed_inputs_are_silent(self):
        self.assertEqual(self.invoke(self.payload(), env={**self.env, "AGENT_DO_PROSE_LINT": "0"}), {})
        for raw in ("", "{invalid", "null", "[]", '"text"', "{}", '{"tool_name":"Write","tool_input":7}',
                    '{"tool_name":"Edit","tool_input":{"file_path":4}}'):
            with self.subTest(raw=raw):
                self.assertEqual(self.invoke(None, raw=raw), {})

    def test_missing_file_is_reported_unchecked(self):
        payload = {"tool_name": "Edit", "cwd": str(self.project),
                   "tool_input": {"file_path": "missing.md"}}
        message = self.context(self.invoke(payload))
        self.assertIn("remains unchecked", message)
        self.assertIn("agent-do deai lint", message)

    def test_linter_errors_are_advisory_and_do_not_echo_source(self):
        payload = self.payload()
        for failure in (OSError("private content"), ValueError("private content"),
                        KeyError("private content"), TypeError("private content")):
            with self.subTest(failure=type(failure)), patch.object(hook, "lint", side_effect=failure):
                message = self.context(self.in_process(payload))
                self.assertIn("remains unchecked", message)
                self.assertNotIn("private content", message)

    def test_invalid_cli_results_are_never_clean(self):
        path = self.project / "a.md"
        good = {"schema": "deai-result-v1", "success": True, "command": "lint", "register": "default",
                "clean": True, "files": [{"path": str(path), "clean": True, "findings": []}]}
        cases = [(2, json.dumps(good)), (0, "bad JSON"), (0, "{}"),
                 (0, json.dumps({**good, "success": False})),
                 (0, json.dumps({**good, "register": "essay"})),
                 (0, json.dumps({**good, "clean": False})),
                 (1, json.dumps(good)),
                 (0, json.dumps({**good, "files": [{"path": "other.md", "clean": True, "findings": []}]}))]
        for code, stdout in cases:
            with self.subTest(code=code, stdout=stdout), patch.object(hook.subprocess, "Popen") as popen:
                process = popen.return_value.__enter__.return_value
                process.returncode = code
                process.communicate.return_value = (stdout, None)
                with self.assertRaises(ValueError):
                    hook.lint(path, "default")

    def test_timeout_kills_and_reaps_only_the_owned_process_group(self):
        with patch.object(hook.subprocess, "Popen") as popen, patch.object(hook.os, "killpg") as killpg:
            process = popen.return_value.__enter__.return_value
            process.pid = 23456
            process.communicate.side_effect = [subprocess.TimeoutExpired("deai", 3), ("", None)]
            with self.assertRaisesRegex(ValueError, "time budget"):
                hook.lint(self.project / "a.md", "default")
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
            killpg.assert_called_once_with(process.pid, hook.signal.SIGKILL)
            self.assertEqual(process.communicate.call_count, 2)

    def test_bounded_feedback_accounts_for_omissions(self):
        payload = self.payload(content="\n".join(["Delve into this robust, seamless tapestry."] * 3))
        message = self.context(self.invoke(payload))
        self.assertIn("3 occurrences; first location shown", message)
        findings = [{"rule": f"rule-{n}", "label": "a tell", "occurrences": [{"line": n + 1, "column": 1}]}
                    for n in range(hook.MAX_FINDINGS_REPORTED + 2)]
        message = hook.render("a.md", "essay", findings, "agent-do deai lint a.md")
        self.assertIn("2 additional rules flagged", message)
        self.assertIn("Complete findings:", message)

    def test_install_spec_registers_all_supported_write_verbs_once(self):
        source = (ROOT / "install.sh").read_text(encoding="utf-8")
        # Execute only the installer's pure settings serializer. The installer
        # itself is never run; no wrappers, config, or dependencies are written.
        specs = re.search(r"CLAUDE_SETTINGS_SPECS=\(\n.*?\n\)", source, re.S).group(0)
        stream = re.search(r"^claude_settings_stream\(\) \{\n.*?^\}", source, re.S | re.M).group(0)
        result = subprocess.run(["bash", "-c", specs + "\n" + stream + "\nclaude_settings_stream"],
                                env={**self.env, "CLAUDE_HOOKS_DIR": str(self.root / "hook fixtures")},
                                capture_output=True, text=True, check=True)
        rows = [row.split("|") for row in result.stdout.splitlines() if HOOK.name in row]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "PostToolUse")
        self.assertEqual(set(rows[0][1:-2]), {"Write", "Edit", "MultiEdit"})
        self.assertEqual(rows[0][-2], str(self.root / "hook fixtures" / HOOK.name))
        self.assertGreater(int(rows[0][-1]), hook.DEAI_TIMEOUT_SECONDS)


if __name__ == "__main__":
    unittest.main()
