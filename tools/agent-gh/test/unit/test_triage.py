#!/usr/bin/env python3
"""Unit tests for agent_gh.triage.issue_triage: classification logic."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_gh.triage import issue_triage as triage_mod


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _make_issue(title: str, body: str, author: str = "reporter") -> dict:
    return {
        "number": 1,
        "title": title,
        "body": body,
        "author": {"login": author},
        "labels": [],
    }


def _triage(title: str, body: str, author: str = "reporter") -> dict:
    """Call triage() with mocked view_issue and empty related search."""
    issue = _make_issue(title, body, author)
    # view_issue is locally imported inside triage() so patch it at its source module.
    # run_gh is imported at module level in issue_triage so patch it there, not in transport.
    with (
        patch("agent_gh.groups.issue.view_issue", return_value={"data": issue}),
        patch("agent_gh.triage.issue_triage.run_gh", return_value="[]"),
    ):
        return triage_mod.triage("ovachiever/agent-do#1")


# ── classification ─────────────────────────────────────────────────────────────

def test_classifies_bug() -> None:
    result = _triage("App crashes on startup", "The app fails with an error on startup.")
    d = result["data"]
    require(d["classification"] == "bug", f"expected bug, got: {d['classification']}")
    require("bug" in d["suggested_labels"], f"expected bug label: {d}")


def test_classifies_feature() -> None:
    result = _triage("Feature request: add dark mode", "It would be great if you could add dark mode. Enhancement proposal.")
    d = result["data"]
    require(d["classification"] == "feature", f"expected feature, got: {d['classification']}")
    require("enhancement" in d["suggested_labels"], f"expected enhancement label: {d}")


def test_classifies_question() -> None:
    result = _triage("How do I configure the timeout?", "How can I set a custom timeout? Is it possible?")
    d = result["data"]
    require(d["classification"] == "question", f"expected question, got: {d['classification']}")
    require("question" in d["suggested_labels"], f"expected question label: {d}")


def test_classifies_docs() -> None:
    result = _triage("Typo in README", "There is a typo in the docs.")
    d = result["data"]
    require(d["classification"] == "docs", f"expected docs, got: {d['classification']}")
    require("documentation" in d["suggested_labels"], f"expected documentation label: {d}")


def test_needs_repro_when_no_steps() -> None:
    result = _triage("App crashes", "It just fails. Bug definitely.")
    d = result["data"]
    require(d["needs_repro"] is True, f"expected needs_repro=true: {d}")


def test_no_needs_repro_when_steps_present() -> None:
    result = _triage("App crashes", "Bug. Steps to reproduce:\n1. Run the app\n2. Click X")
    d = result["data"]
    require(d["needs_repro"] is False, f"expected needs_repro=false: {d}")


def test_needs_version_when_absent() -> None:
    result = _triage("App crashes", "It just fails with an error. Bug confirmed.")
    d = result["data"]
    require(d["needs_version"] is True, f"expected needs_version=true: {d}")


def test_no_needs_version_when_present() -> None:
    result = _triage("App crashes", "Bug on version v1.2.3")
    d = result["data"]
    require(d["needs_version"] is False, f"expected needs_version=false: {d}")


# ── first_response_draft ───────────────────────────────────────────────────────

def test_draft_bug_with_asks() -> None:
    result = _triage("App crashes", "It just fails. Bug.", "alice")
    d = result["data"]
    draft = d["first_response_draft"]
    require("@alice" in draft, f"expected author mention: {draft}")
    require("steps to reproduce" in draft or "version" in draft, f"expected ask in draft: {draft}")


def test_draft_feature() -> None:
    result = _triage("Add dark mode", "Enhancement: would be great to have dark mode.")
    d = result["data"]
    draft = d["first_response_draft"]
    require("use case" in draft, f"expected use-case ask in feature draft: {draft}")


def test_draft_question() -> None:
    result = _triage("How to configure?", "How can I set the timeout?")
    d = result["data"]
    draft = d["first_response_draft"]
    require("version" in draft.lower(), f"expected version ask in question draft: {draft}")


# ── envelope ──────────────────────────────────────────────────────────────────

def test_envelope_shape() -> None:
    result = _triage("App crashes", "Bug fails error.")
    require("command" in result, f"missing command key: {result}")
    require("timestamp" in result, f"missing timestamp key: {result}")
    require("ref" in result, f"missing ref key: {result}")
    require("data" in result, f"missing data key: {result}")
    require(result["command"] == "issue triage", f"bad command: {result}")
    require(result["ref"] == "ovachiever/agent-do#1", f"bad ref: {result}")


# ── _draft helper (direct) ────────────────────────────────────────────────────

def test_draft_unknown_classification() -> None:
    draft = triage_mod._draft("unknown", False, False, "bob")
    require("triage" in draft.lower(), f"expected triage mention: {draft}")


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    tests = [
        test_classifies_bug,
        test_classifies_feature,
        test_classifies_question,
        test_classifies_docs,
        test_needs_repro_when_no_steps,
        test_no_needs_repro_when_steps_present,
        test_needs_version_when_absent,
        test_no_needs_version_when_present,
        test_draft_bug_with_asks,
        test_draft_feature,
        test_draft_question,
        test_envelope_shape,
        test_draft_unknown_classification,
    ]
    failures = []
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failures.append(f"  FAIL {t.__name__}: {exc}")
        except Exception as exc:
            failures.append(f"  ERROR {t.__name__}: {type(exc).__name__}: {exc}")
    if failures:
        for f in failures:
            print(f)
        return 1
    print(f"triage unit tests passed ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
