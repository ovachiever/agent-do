#!/usr/bin/env python3
"""install.sh spec-array coherence.

The failure this pins down (found by Chris, 2026-08-31): a hook can be
REGISTERED in settings.json (CLAUDE_SETTINGS_SPECS) without its wrapper
ever being INSTALLED (CLAUDE_HOOK_SPECS). Nothing errors — Claude Code
silently skips the missing file — so the hook looks installed and never
runs. Registration and installation are two arrays edited by hand; this
test holds them coherent.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = (ROOT / "install.sh").read_text(encoding="utf-8")


def array_lines(name: str) -> list[str]:
    match = re.search(rf"{name}=\(\n(.*?)\n\)", INSTALL, re.DOTALL)
    if not match:
        raise AssertionError(f"install.sh no longer declares {name}")
    return re.findall(r'"([^"]+)"', match.group(1))


class InstallSpecCoherence(unittest.TestCase):
    def test_every_registered_claude_hook_has_an_installed_wrapper(self) -> None:
        registered = {line.split("|")[-2] for line in array_lines("CLAUDE_SETTINGS_SPECS")}
        installed = {line.split("|")[0] for line in array_lines("CLAUDE_HOOK_SPECS")}
        missing = sorted(registered - installed)
        self.assertEqual(
            missing, [],
            f"registered in settings.json but no wrapper is installed: {missing}",
        )

    def test_every_installed_wrapper_source_exists(self) -> None:
        for line in array_lines("CLAUDE_HOOK_SPECS"):
            _, rel, _, requirement = (line.split("|") + [""])[:4]
            if requirement != "optional":
                self.assertTrue((ROOT / rel).is_file(), f"wrapper source missing: {rel}")

    def test_uninstall_covers_every_installed_wrapper(self) -> None:
        installed = {line.split("|")[0] for line in array_lines("CLAUDE_HOOK_SPECS")}
        uninstall_match = re.search(
            r"# Remove Claude hooks[^\n]*\n\s*local hooks=\(\n(.*?)\n\s*\)", INSTALL, re.DOTALL
        )
        self.assertIsNotNone(uninstall_match, "Claude uninstall array not found in install.sh")
        removed = set(re.findall(r'"([^"]+)"', uninstall_match.group(1)))
        self.assertEqual(sorted(installed - removed), [],
                         "installed but never uninstalled")

    def test_python_dependencies_and_runtime_pin_share_one_interpreter(self) -> None:
        self.assertIn('"$PYTHON_BIN" -m pip install', INSTALL)
        self.assertIn('"$PYTHON_BIN" -c \'import yaml\'', INSTALL)
        self.assertIn("PYTHON_PIN_PATH=", INSTALL)
        self.assertIn('mv -f "$python_pin_pending" "$PYTHON_PIN_PATH"', INSTALL)

    def test_uninstall_removes_the_python_runtime_pin(self) -> None:
        uninstall = INSTALL[INSTALL.index("uninstall() {"):INSTALL.index("# 1. Symlink")]
        self.assertIn('rm "$PYTHON_PIN_PATH"', uninstall)


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
