#!/usr/bin/env python3
"""Focused offline tests for the prose engine, evidence gate, and public CLI."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "agent-deai"))
import deai
import guard


class DeaiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.packs = deai.load()

    def lint(self, text, register="essay"):
        return deai.lint_text(text, self.catalog, self.packs[register])

    def ids(self, text, register="essay"):
        return {f["rule"] for f in self.lint(text, register)["findings"]}

    def cli(self, *args, stdin=None):
        with tempfile.TemporaryDirectory() as home:
            return subprocess.run([str(ROOT / "agent-do"), "deai", *args], input=stdin,
                                  text=True, capture_output=True, check=False,
                                  env={**os.environ, "AGENT_DO_HOME": home})

    def test_complete_migration_and_lexicon_receipt(self):
        self.assertEqual([sum(r["tier"] == t for r in self.catalog["rules"]) for t in (1, 2, 3)], [49, 46, 12])
        source = ROOT / "tools/agent-deai/ai-speak-lexicon.md"
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         self.catalog["provenance"]["files"]["voice/ai-speak-lexicon.md"])
        self.assertEqual(self.catalog["measurements"]["human-2026-09-08"]["words"], 110977)
        self.assertEqual(self.catalog["measurements"]["erik-2026-09-11"]["words"], 120102)

    def test_default_permits_literal_technical_words_and_instructions(self):
        text = ("The architecture uses structural typing and robust regression. "
                "Unpack the archive. An underscore separates names. Ensure the check passes.\n"
                "- **Inputs**: red, green, and blue\nThe adapter acts as a bridge.")
        for register in ("default", "product-answer"):
            with self.subTest(register=register):
                self.assertTrue(self.lint(text, register)["clean"])
        self.assertTrue({"architecture", "structural", "robust", "unpack", "underscore"} <= self.ids(text))

    def test_email_allows_technical_terms_and_scheduling(self):
        self.assertTrue(self.lint("Please review the robust architecture from Monday to Friday. Let me know.", "email")["clean"])

    def test_high_signal_prose_still_flags_in_every_pack(self):
        for register in deai.REGISTERS:
            with self.subTest(register=register):
                self.assertTrue({"delve", "tapestry", "worth-noting"} <= self.ids(
                    "We delve into a tapestry. It is worth noting the result.", register))

    def test_recent_tells_keep_their_own_resolution_floor(self):
        cases = {"tour-guide": "Let me explain the result.",
                 "personified-labor": "The clause is doing quiet work.",
                 "knowing-wink": "And I would know."}
        for rule, text in cases.items():
            for register in deai.REGISTERS:
                with self.subTest(rule=rule, register=register):
                    finding = next(f for f in self.lint(text, register)["findings"] if f["rule"] == rule)
                    self.assertEqual(finding["baseline_words"], 120102)
                    self.assertAlmostEqual(finding["effective_ceiling_per_10k"], 10000 / 120102)

    def test_rate_rules_allow_measured_usage_and_flag_excess(self):
        self.assertNotIn("ensure", self.ids("ensure " + "stone " * 9999))
        self.assertIn("ensure", self.ids("ensure " * 100 + "stone " * 9900))

    def test_masking_preserves_lines_columns_and_denominator(self):
        text = "---\ntitle: delve\n---\n```python\nrobust = 'tapestry'\n```\nA plain line.\n  delve here.\n"
        result = self.lint(text)
        self.assertEqual(result["words"], 5)
        self.assertEqual(result["findings"][0]["occurrences"], [{"line": 8, "column": 3, "text": "delve"}])
        self.assertEqual(deai.mask_nonprose(text).count("\n"), text.count("\n"))
        self.assertEqual(len(deai.mask_nonprose(text)), len(text))

    def test_code_comments_urls_and_buttons_are_not_prose(self):
        for text in ("`delve`", "``delve``", "Use ``robust `delve` inside`` here.",
                     "~~~python\ndelve\n~~~", "```\ndelve",
                     "<!-- delve -->", "<!-- delve", "https://example.org/delve", "[subscribe]"):
            with self.subTest(text=text):
                self.assertTrue(self.lint(text)["clean"])

    def test_tilde_and_long_fences_do_not_close_on_shorter_fence(self):
        self.assertTrue(self.lint("````\n```\ndelve\n````\nplain")["clean"])
        self.assertTrue(self.lint("~~~\n```\ndelve\n~~~\nplain")["clean"])
        self.assertEqual(self.ids("```plain``` then delve"), {"delve"})

    def test_excluded_content_cannot_join_a_construction(self):
        self.assertNotIn("not-only-but", self.ids("not only `code` but also true."))

    def test_curly_apostrophes_preserve_source_occurrences(self):
        result = self.lint("I’m going to show you.")
        finding = next(f for f in result["findings"] if f["rule"] == "tour-guide")
        self.assertEqual(finding["occurrences"][0]["text"], "I’m going to show")

    def test_empty_prose_and_punctuation_only_policy(self):
        self.assertTrue(self.lint("")["clean"])
        self.assertIn("em-dash", self.ids("—"))

    def test_poisson_small_probability_does_not_cancel(self):
        self.assertAlmostEqual(deai.poisson_tail(1, 1e-20) / 1e-20, 1)
        self.assertAlmostEqual(deai.poisson_tail(1, 2), -math.expm1(-2))
        self.assertAlmostEqual(deai.poisson_tail(2, 2), 1 - 3 * math.exp(-2))

    def test_poisson_large_lambda_does_not_underflow_to_one(self):
        self.assertAlmostEqual(deai.poisson_tail(1000, 1000), 0.5042052441802155, places=10)
        self.assertGreater(deai.poisson_tail(1500, 1000), 0)
        self.assertLess(deai.poisson_tail(1500, 1000), 1e-40)
        self.assertEqual(deai.poisson_tail(0, 10), 1)
        self.assertEqual(deai.poisson_tail(1, 0), 0)

    def test_each_pack_carries_complete_sourced_ceilings(self):
        rate_ids = {r["id"] for r in self.catalog["rules"] if r["tier"] > 1}
        for pack in self.packs.values():
            self.assertEqual(set(pack["ceilings"]), rate_ids)
            self.assertIn("Inherited", pack["provenance"]["calibration"])

    def test_bare_missing_invalid_and_unmeasured_ceilings_fail_closed(self):
        for replacement in (0.2, {}, {"per_10k": -1, "measurement": "human-2026-09-08"},
                            {"per_10k": float("nan"), "measurement": "human-2026-09-08"},
                            {"per_10k": 0.2, "measurement": "invented"},
                            {"per_10k": 999, "measurement": "human-2026-09-08"}):
            with self.subTest(replacement=replacement):
                packs = copy.deepcopy(self.packs)
                packs["essay"]["ceilings"]["ensure"] = replacement
                with self.assertRaises((ValueError, KeyError)):
                    deai.validate_data(self.catalog, packs)

    def test_missing_denominator_and_changed_pattern_require_evidence(self):
        for change in ("words", "pattern"):
            catalog = copy.deepcopy(self.catalog)
            if change == "words":
                catalog["measurements"]["human-2026-09-08"]["words"] = 0
            else:
                next(r for r in catalog["rules"] if r["id"] == "ensure")["pattern"] = "a different tell"
            with self.assertRaises(ValueError):
                deai.validate_data(catalog, self.packs)

    def test_unattributed_whitelist_and_unknown_rule_are_rejected(self):
        for entry in ({"rules": ["robust"], "source": "", "reason": "because"},
                      {"rules": ["typo"], "source": "policy", "reason": "because"}):
            packs = copy.deepcopy(self.packs)
            packs["essay"]["whitelist"] = [entry]
            with self.assertRaises(ValueError):
                deai.validate_data(self.catalog, packs)

    def test_measurement_is_reusable_for_a_new_data_only_rule(self):
        catalog, packs = copy.deepcopy((self.catalog, self.packs))
        pattern = r"\bnew tell\b"
        record = deai.measure([("fixture", "new tell and plain words")], "new-tell", pattern, "synthetic test only", catalog)
        self.assertEqual(record["words"], 5)
        self.assertEqual(record["counts"], {"new-tell": 1})
        catalog["measurements"]["fixture"] = record
        catalog["rules"].append({"id": "new-tell", "tier": 3, "label": "new tell",
                                 "pattern": pattern, "evidence": "synthetic test"})
        for pack in packs.values():
            pack["ceilings"]["new-tell"] = {"per_10k": record["ceilings"]["new-tell"], "measurement": "fixture"}
        deai.validate_data(catalog, packs)
        record["files"][0]["words"] += 1
        with self.assertRaises(ValueError):
            deai.validate_data(catalog, packs)

    def test_measurement_rejects_empty_and_duplicate_corpora(self):
        for inputs in ([("empty", "```\ndelve\n```")], [("a", "one word"), ("b", "one word")]):
            with self.assertRaises(ValueError):
                deai.measure(inputs, "tell", "word", "test", self.catalog)

    def test_public_dispatch_help_validate_and_pack_contract(self):
        for command in (("--help",), ("validate", "--json"), ("packs", "--register", "essay", "--json")):
            with self.subTest(command=command):
                result = self.cli(*command)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["total_packs"], 1)
        self.assertEqual(len(payload["rules"]), 107)

    def test_public_stdin_defaults_to_technical_safe_pack(self):
        result = self.cli("lint", "-", "--json", stdin="A robust architecture with structural typing.")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["clean"])

    def test_public_findings_are_complete_and_inputs_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            prose = Path(folder) / "draft.md"
            prose.write_text("delve\ndelve\n", encoding="utf-8")
            before = prose.read_bytes()
            result = self.cli("lint", str(prose), "--register", "essay", "--json")
            self.assertEqual(prose.read_bytes(), before)
        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["success"])
        self.assertFalse(payload["clean"])
        self.assertEqual(payload["files"][0]["findings"][0]["count"], 2)
        self.assertEqual([x["line"] for x in payload["files"][0]["findings"][0]["occurrences"]], [1, 2])

    def test_public_errors_are_machine_readable_and_never_clean(self):
        for args in (("lint", "/missing/deai.md"), ("lint", "-", "--register", "typo"), ("lint", "-", "-")):
            result = self.cli(*args, "--json", stdin="plain")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertFalse(json.loads(result.stdout)["success"])

    def test_public_measure_exposes_denominator_pattern_and_hash(self):
        result = self.cli("measure", "-", "--rule-id", "new-tell", "--pattern", "word", "--source", "test", "--json", stdin="one word")
        self.assertEqual(result.returncode, 0, result.stderr)
        measurement = json.loads(result.stdout)["measurement"]
        self.assertEqual(measurement["words"], 2)
        self.assertEqual(measurement["files"][0]["sha256"], hashlib.sha256(b"one word").hexdigest())

    def test_crlf_file_measurement_hashes_actual_bytes_and_masks_fences(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "windows.md"
            raw = b"```\r\ndelve\r\n```\r\none word\r\n"
            p.write_bytes(raw)
            inputs = deai.read_inputs([str(p)])
            measurement = deai.measure(inputs, "tell", "word", "test", self.catalog)
        self.assertEqual(measurement["files"][0]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(measurement["words"], 2)
        self.assertTrue(self.lint(inputs[0][1])["clean"])

    def test_zero_width_pattern_is_an_error(self):
        with self.assertRaises(ValueError):
            deai.measure([("fixture", "word")], "tell", r"\b", "test", self.catalog)

    def test_malformed_rule_documents_are_errors(self):
        with self.assertRaises(ValueError):
            deai.validate_data(None, self.packs)
        for value in (None, [], "invalid"):
            packs = copy.deepcopy(self.packs)
            packs["essay"] = value
            with self.assertRaises(ValueError):
                deai.validate_data(self.catalog, packs)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="deai-guard-")
        self.addCleanup(self.folder.cleanup)
        self.repo = Path(self.folder.name) / "repo with spaces"
        self.repo.mkdir()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(AGENT_DO_HOME=str(Path(self.folder.name) / "agent-state"),
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        PYTHONDONTWRITEBYTECODE="1")
        self.git("init", "-q", "--template=")
        self.git("config", "user.name", "Prose Guard Test")
        self.git("config", "user.email", "guard@example.invalid")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args, check=True):
        return subprocess.run(["git", *args], cwd=self.repo, env=self.env,
                              text=True, capture_output=True, check=check)

    def cli(self, *args, cwd=None):
        return subprocess.run([str(ROOT / "agent-do"), "deai", "guard", *args],
                              cwd=cwd or self.repo, env=self.env, text=True,
                              capture_output=True, check=False)

    def check(self, **kwargs):
        result = self.cli("check", "--json", **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def stage(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.git("add", "--", name)
        return path

    def install(self, *args, cwd=None):
        result = self.cli("install", *args, "--json", cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_unborn_index_and_partial_staging_use_blob_not_worktree(self):
        name = "docs/-a spaced\nprose.MD"
        path = self.stage(name, "delve\ndelve\n")
        path.write_text("A plain sentence.\n")
        self.stage("clean.md", "A plain sentence.\n").write_text("delve\n")
        (self.repo / "untracked.md").write_text("delve\n")
        self.stage("script.py", "delve\n")
        staged_before = self.git("diff", "--cached", "--binary").stdout
        worktree_before = self.git("diff", "--binary").stdout
        payload = self.check(cwd=path.parent)
        self.assertTrue(payload["success"])
        self.assertFalse(payload["clean"])
        files = {item["path"]: item for item in payload["files"]}
        self.assertEqual(set(files), {name, "clean.md"})
        self.assertTrue(files["clean.md"]["clean"])
        findings = files[name]["findings"]
        self.assertEqual([hit["line"] for hit in findings[0]["occurrences"]], [1, 2])
        self.assertEqual(files[name]["blob"], self.git("rev-parse", ":" + name).stdout.strip())
        self.assertEqual(self.git("diff", "--cached", "--binary").stdout, staged_before)
        self.assertEqual(self.git("diff", "--binary").stdout, worktree_before)

    def test_modified_renamed_and_deleted_paths(self):
        for name in ("rename.md", "deleted.md", "unchanged.md", "edit.txt"):
            self.stage(name, "delve\n")
        self.git("commit", "-qm", "fixture baseline")
        self.git("mv", "rename.md", "renamed.md")
        self.git("rm", "deleted.md")
        self.stage("edit.txt", "delve\ndelve\n")
        payload = self.check()
        self.assertEqual({item["path"] for item in payload["files"]}, {"renamed.md", "edit.txt"})

    def test_binary_and_symlink_are_skipped_invalid_utf8_is_visible(self):
        (self.repo / "binary.md").write_bytes(b"delve\0")
        (self.repo / "invalid.txt").write_bytes(b"\xff")
        outside = Path(self.folder.name) / "outside.txt"
        outside.write_text("delve\n")
        (self.repo / "linked.md").symlink_to(outside)
        self.git("add", "--", "binary.md", "invalid.txt", "linked.md")
        payload = self.check()
        self.assertFalse(payload["success"])
        self.assertFalse(payload["clean"])
        self.assertEqual(payload["total_files"], 0)
        self.assertEqual({item["path"] for item in payload["skipped"]}, {"binary.md", "linked.md"})
        self.assertEqual(payload["errors"][0]["path"], "invalid.txt")

    def test_missing_repo_and_invalid_rules_warn_without_blocking(self):
        payload = self.check(cwd=Path(self.folder.name))
        self.assertFalse(payload["success"])
        self.assertFalse(payload["clean"])
        warning = self.cli("check", cwd=Path(self.folder.name))
        self.assertEqual(warning.returncode, 0)
        self.assertIn("WARN", warning.stdout)
        with patch.object(deai, "load", side_effect=deai.re.error("invalid fixture rule")):
            payload = guard.check("default")
        self.assertFalse(payload["success"])
        self.assertIn("invalid fixture rule", payload["errors"][0]["error"])

    def test_default_pack_matches_engine_and_explicit_register(self):
        self.stage("README.md", "A robust architecture with structural typing.\n")
        self.assertTrue(self.check()["clean"])
        result = self.cli("check", "--register", "essay", "--json")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stdout)["clean"])
        self.stage("code.md", "```\ndelve\n```\nA plain sentence.\n")
        self.assertTrue(self.check()["clean"])

    def test_installed_hook_executes_for_all_harnesses_and_preserves_exit(self):
        hook = self.repo / ".git/hooks/pre-commit"
        hook.parent.mkdir(parents=True)
        original = "#!/bin/sh\nprintf '%s\\n' existing-hook-ran\nexit 0\n"
        hook.write_text(original)
        self.install()
        first = hook.read_bytes()
        self.assertTrue(self.install()["already_installed"])
        self.assertEqual(hook.read_bytes(), first)
        self.assertEqual(first.decode().count(guard.START), 1)
        self.assertTrue(first.decode().endswith(original.split("\n", 1)[1]))
        self.assertTrue(os.access(hook, os.X_OK))
        for harness in ("codex", "droid", "cursor"):
            with self.subTest(harness=harness):
                self.env["AGENT_HARNESS"] = harness
                self.stage("draft.md", f"delve\n{harness}\n")
                before = (self.repo / "draft.md").read_bytes()
                result = self.git("commit", "-qm", "fixture " + harness, check=False)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertIn("deai guard WARN", result.stderr)
                self.assertIn("existing-hook-ran", result.stderr)
                self.assertEqual((self.repo / "draft.md").read_bytes(), before)
        hook.write_bytes(hook.read_bytes().replace(b"exit 0\n", b"exit 9\n"))
        self.stage("draft.md", "delve\nblocked by existing gate\n")
        before = self.git("rev-parse", "HEAD").stdout
        result = self.git("commit", "-qm", "must stay blocked", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("deai guard WARN", result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD").stdout, before)

    def test_custom_hook_path_and_register_update(self):
        self.git("config", "core.hooksPath", "custom hooks")
        nested = self.repo / "nested"
        nested.mkdir()
        payload = self.install(cwd=nested)
        hook = Path(payload["hook"])
        self.assertEqual(hook.resolve(), (self.repo / "custom hooks/pre-commit").resolve())
        self.assertFalse(self.install("--register", "essay")["already_installed"])
        self.assertEqual(hook.read_text().count(guard.START), 1)
        self.stage("draft.md", "The architecture uses structural typing.\n")
        result = self.git("commit", "-qm", "fixture custom hook")
        self.assertIn("deai guard WARN", result.stderr)

    def test_linked_worktree_hook_and_alternate_index(self):
        self.stage("plain.md", "A plain sentence.\n")
        self.git("commit", "-qm", "fixture baseline")
        worktree = Path(self.folder.name) / "linked worktree"
        self.git("worktree", "add", "--detach", str(worktree))
        result = self.cli("install", "--json", cwd=worktree)
        self.assertEqual(result.returncode, 0, result.stderr)
        hook = Path(json.loads(result.stdout)["hook"])
        self.assertEqual(hook.resolve(), (self.repo / ".git/hooks/pre-commit").resolve())
        self.env["GIT_INDEX_FILE"] = str(Path(self.folder.name) / "alternate-index")
        self.git("read-tree", "HEAD")
        self.stage("alternate.md", "delve\n")
        self.assertFalse(self.check()["clean"])
        self.env.pop("GIT_INDEX_FILE")
        self.assertTrue(self.check()["clean"])

    def test_unsupported_hooks_are_refused_without_changes(self):
        hook = self.repo / ".git/hooks/pre-commit"
        hook.parent.mkdir(parents=True)
        outside = Path(self.folder.name) / "owned-hook"
        outside.write_text("#!/bin/sh\nexit 0\n")
        hook.symlink_to(outside)
        result = self.cli("install", "--json")
        self.assertEqual(result.returncode, 2)
        self.assertTrue(hook.is_symlink())
        self.assertEqual(outside.read_text(), "#!/bin/sh\nexit 0\n")
        hook.unlink()
        for content in ("#!/usr/bin/env python3\nprint('existing hook')\n",
                        "#!/bin/sh\n" + guard.START):
            hook.write_text(content)
            before = hook.read_bytes()
            result = self.cli("install", "--json")
            self.assertEqual(result.returncode, 2)
            self.assertFalse(json.loads(result.stdout)["success"])
            self.assertEqual(hook.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
