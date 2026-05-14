"""Deterministic issue triage: classify, suggest labels, find related, draft first response."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ..refs import parse_issue
from ..snapshot import envelope
from ..transport import run_gh


_BUG = (r"\berror\b", r"\bexception\b", r"\bstack\s?trace\b", r"\bcrash(es|ed)?\b",
        r"\bbroke(n)?\b", r"\bdoes\s?n[o']?t\s+work\b", r"\bfail(s|ed|ure)?\b",
        r"\bregression\b", r"\bbug\b")
_FEATURE = (r"\bfeature\s+request\b", r"\bwould\s+be\s+(great|nice|cool)\b",
            r"\bcan\s+you\s+add\b", r"\bplease\s+(add|support)\b",
            r"\bproposal\b", r"\bsuggestion\b", r"\benhancement\b")
_QUESTION = (r"\?\s*$", r"\bhow\s+(do|can)\s+i\b", r"\bwhat('s|\s+is)\b",
             r"\bis\s+it\s+possible\b", r"\bwhy\s+(does|is)\b")
_DOCS = (r"\bdocs?\b", r"\bdocumentation\b", r"\btypo\b", r"\breadme\b")


@dataclass
class TriageResult:
    classification: str
    confidence: float
    signals: list[str]
    suggested_labels: list[str]
    related_issues: list[dict[str, Any]]
    first_response_draft: str
    needs_repro: bool
    needs_version: bool


def triage(ref: str) -> dict[str, Any]:
    """Classify an issue, suggest labels, and draft a first response without LLM."""
    from ..groups.issue import view_issue

    iref = parse_issue(ref)
    issue_data = view_issue(ref)["data"]
    body = (issue_data.get("body") or "") + "\n\n" + (issue_data.get("title") or "")

    signals: list[str] = []
    scores: dict[str, int] = {"bug": 0, "feature": 0, "question": 0, "docs": 0}

    def hit(patterns: tuple[str, ...], key: str) -> None:
        for p in patterns:
            if re.search(p, body, re.IGNORECASE | re.MULTILINE):
                signals.append(p)
                scores[key] += 1

    hit(_BUG, "bug")
    hit(_FEATURE, "feature")
    hit(_QUESTION, "question")
    hit(_DOCS, "docs")

    total = sum(scores.values()) or 1
    top = max(scores, key=lambda k: scores[k])
    confidence = scores[top] / total if scores[top] > 0 else 0.0
    classification = top if confidence >= 0.4 else "unknown"

    label_map = {
        "bug": ["bug", "needs-triage"],
        "feature": ["enhancement"],
        "question": ["question"],
        "docs": ["documentation"],
        "unknown": ["needs-triage"],
    }

    needs_repro = classification == "bug" and not re.search(
        r"\b(steps\s+to\s+reproduce|repro|how\s+to\s+reproduce)\b", body, re.I
    )
    needs_version = classification == "bug" and not re.search(
        r"\b(version|v\d+\.\d+|commit\s+[0-9a-f]{7,})\b", body, re.I
    )

    author = (issue_data.get("author") or {}).get("login")
    draft = _draft(classification, needs_repro, needs_version, author)
    related = _search_related(iref.repo_ref.slug, issue_data.get("title") or "")

    result = TriageResult(
        classification=classification,
        confidence=round(confidence, 2),
        signals=signals,
        suggested_labels=label_map[classification],
        related_issues=related,
        first_response_draft=draft,
        needs_repro=needs_repro,
        needs_version=needs_version,
    )
    return envelope("issue triage", ref=iref.slug, data=asdict(result))


def _draft(classification: str, needs_repro: bool, needs_version: bool,
           author: str | None) -> str:
    greeting = f"Thanks for the report{', @' + author if author else ''}."
    if classification == "bug":
        asks = []
        if needs_repro:
            asks.append("a minimal set of steps to reproduce")
        if needs_version:
            asks.append("the version (or commit hash) you're running")
        if asks:
            return f"{greeting} To dig in, could you share {' and '.join(asks)}?"
        return f"{greeting} Looks reproducible — I'll take a closer look."
    if classification == "feature":
        return f"{greeting} Interesting idea — could you describe the use case it would unblock?"
    if classification == "question":
        return f"{greeting} Happy to help. Quick question — which version are you on, and which command surfaced this?"
    if classification == "docs":
        return f"{greeting} Good catch — could you point to the exact file / section?"
    return f"{greeting} I'll route this to triage."


def _search_related(repo_slug: str, title: str) -> list[dict[str, Any]]:
    keywords = " ".join(w for w in title.split() if len(w) > 3)[:60]
    if not keywords:
        return []
    res = run_gh(
        ["search", "issues", keywords, "--repo", repo_slug,
         "--limit", "5", "--json", "number,title,state,url"],
    )
    import json
    try:
        return json.loads(res) or []
    except Exception:
        return []
