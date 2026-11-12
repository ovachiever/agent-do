#!/usr/bin/env python3
"""One-line digests for board rows.

A manna title is a name; the dense list needs a sentence that says what the
item delivers, short enough for one line. The same move agent-sessions makes
for session titles: a fast model writes it once, a content hash keeps it
until the title or description changes, and the raw title stays available
(in the inspector). Digests are display only: they live under
$AGENT_DO_HOME/manna/serve/digests/, never in the board. No agent reads them;
human-facing clients may consume hash-current values through `manna state`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SERVE_DIR = Path(__file__).resolve().parent
REPO_LIB = SERVE_DIR.parents[2] / "lib"
if str(REPO_LIB) not in sys.path:
    sys.path.insert(0, str(REPO_LIB))

# The title column at finish A holds one line of 10px mono: measured on the
# ratified wireframe (round four, A) the column is 288px wide at a 960px
# frame, i.e. 48 characters at the 6px advance of 10px SFMono; the built
# page gives the list the width the inspector and chrome leave at 1280px
# and up, which measured at 432px = 72 characters. Longer lines ellipsize.
DIGEST_MAX_CHARS = 72

FLAG_NAME = "AGENT_DO_SERVE_AI"
_MN_ID = re.compile(r"\bmn-[0-9a-f]{6,}\b")

# Items per model call. Measured 2026-08-24 on this board: 12 digests came
# back in 5.0s through lib/ai_router (client timeout 30s, its
# DEFAULT_CLIENT_TIMEOUT_SECONDS); 122 in one call ran past that timeout.
# Forty keeps a batch under half the timeout at the measured rate; the byte
# budget below still bounds the prompt against the model's input window.
DIGESTS_PER_CALL = 40

SYSTEM = (
    "You write one-line digests for software work items on a project board. "
    "Each digest says what the item delivers when it is done: imperative, verb first, "
    "specific to the item, plain words, no hedging, no item ids, no trailing period, "
    f"at most {DIGEST_MAX_CHARS} characters. A digest must be usable as the only line a "
    "person sees while scanning a dense list. Never restate the title verbatim; say the thing."
)

EXAMPLES = f"""Examples of good digests (each counted, all under {DIGEST_MAX_CHARS} characters):
- Add gh issue verbs and pr create --declare to the gh tool  (57)
- Render the board as a live read-only page on the local port  (51)
- Refuse batch promotion to global; one lesson per call  (52)
- Warn at install when a hook wrapper has no registration  (55)
- Stop the write-nudge misreading a bound worktree  (49)

Budget: at most {DIGEST_MAX_CHARS} characters per digest, at most 10 words; aim for 40 to 65 characters. Count before you answer.
Drop parentheticals, lists of sub-parts, and program names; keep the one concrete thing delivered."""


def safe_error(error: BaseException, where: str) -> str:
    """A fixed code for clients and caches; the full exception goes to the
    daemon log only. Provider errors can echo request detail, which must
    never leave the process."""
    text = str(error).lower()
    if "not available" in text or "credential" in text:
        code = "no_credential"
    elif "timed out" in text or "timeout" in text:
        code = "timeout"
    elif "rate" in text and "limit" in text:
        code = "rate_limited"
    else:
        code = "provider_error"
    sys.stderr.write(f"{where}: {code}: {error!r}\n")
    sys.stderr.flush()
    return code


def content_hash(issue: dict[str, Any]) -> str:
    material = json.dumps(
        {"t": issue.get("title", ""), "d": issue.get("description") or "", "k": issue.get("type") or "item"},
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def digest_dir() -> Path:
    home = Path(os.environ.get("AGENT_DO_HOME", str(Path.home() / ".agent-do")))
    path = home / "manna" / "serve" / "digests"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_path(slug: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", slug) or "board"
    return digest_dir() / f"{safe}.json"


def load_cache(slug: str) -> dict[str, dict[str, Any]]:
    path = cache_path(slug)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = data.get("digests") if isinstance(data, dict) else None
    return rows if isinstance(rows, dict) else {}


def save_cache(slug: str, rows: dict[str, dict[str, Any]]) -> None:
    path = cache_path(slug)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"version": 1, "digests": rows}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def validate(text: Any, issue: dict[str, Any]) -> str | None:
    """A digest is one line, within the column, not the title, not a fragment of one."""
    if not isinstance(text, str):
        return None
    line = " ".join(text.strip().strip('"\'').split())
    line = line.rstrip(".")
    if not line or "\n" in text.strip():
        return None
    if len(line) > DIGEST_MAX_CHARS:
        return None
    title = " ".join(str(issue.get("title", "")).split()).strip().rstrip(".")
    if line.lower() == title.lower():
        return None
    if re.search(r"\bmn-[0-9a-f]{6,}\b", line):
        return None
    return line


def _cooldown_seconds() -> float:
    """A transient failure (timeout, network) waits one client-timeout window
    before it is asked again, so a dead provider costs one attempt per window."""
    try:
        from ai_router import DEFAULT_CLIENT_TIMEOUT_SECONDS  # type: ignore
        return float(DEFAULT_CLIENT_TIMEOUT_SECONDS)
    except Exception:
        return 0.0


def _retry_due(entry: dict[str, Any]) -> bool:
    if not entry.get("transient"):
        return False
    try:
        failed_at = datetime.fromisoformat(str(entry.get("failed_at")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    return (datetime.now(timezone.utc) - failed_at).total_seconds() >= _cooldown_seconds()


def _digest_state(
    cache: dict[str, dict[str, Any]], row: dict[str, Any]
) -> tuple[str | None, bool]:
    """Return (current digest, generation due) without changing the row."""
    if row.get("kind") == "track":
        return None, False
    entry = cache.get(row["id"])
    h = content_hash(row)
    if entry and entry.get("hash") == h and entry.get("digest"):
        return str(entry["digest"]), False
    permanent = bool(
        entry and entry.get("hash") == h and entry.get("failed") and not entry.get("transient")
    )
    cooling = bool(
        entry and entry.get("hash") == h and entry.get("transient") and not _retry_due(entry)
    )
    return None, not permanent and not cooling


def _report(
    slug: str, rows: list[dict[str, Any]], *, attach: bool
) -> dict[str, Any]:
    cache = load_cache(slug)
    missing: list[dict[str, Any]] = []
    ready = 0
    for row in rows:
        digest, generation_due = _digest_state(cache, row)
        ready += int(bool(digest))
        if attach:
            row["digest"] = digest
        if generation_due:
            missing.append(row)
    return {
        "ready": ready,
        "missing": len(missing),
        "missing_rows": missing,
        "model": next((entry.get("model") for entry in cache.values() if entry.get("model")), None),
    }


def apply(slug: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compatibility helper: attach cached digests and report gaps."""
    return _report(slug, rows, attach=True)


def plan(slug: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Report generation gaps without reattaching the core's row fields."""
    return _report(slug, rows, attach=False)


# ---------------------------------------------------------------- generation


def _budget_bytes() -> int:
    """Prompt bytes the fast model can take. Bytes bound tokens from above (no
    token is shorter than a byte), so the authority's input window in tokens
    is a safe byte budget; the system text and examples come off the top."""
    from models import resolve  # type: ignore

    window = int(resolve("fast")["capabilities"]["max_input_tokens"])
    return window - len(SYSTEM.encode("utf-8")) - len(EXAMPLES.encode("utf-8"))


def _item_block(issue: dict[str, Any]) -> str:
    desc = " ".join(str(issue.get("description") or "").split())
    track = issue.get("track_title") or ""
    parts = [f"id: {issue['id']}", f"title: {issue.get('title', '')}"]
    if track:
        parts.append(f"program: {track}")
    if desc:
        parts.append(f"description: {desc}")
    return "\n".join(parts)


def chunk_by_bytes(issues: list[dict[str, Any]], budget: int, per_call: int = DIGESTS_PER_CALL) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    used = 0
    for issue in issues:
        size = len(_item_block(issue).encode("utf-8")) + 2
        if current and (used + size > budget or len(current) >= per_call):
            chunks.append(current)
            current, used = [], 0
        current.append(issue)
        used += size
    if current:
        chunks.append(current)
    return chunks


def default_caller(prompt: str) -> tuple[dict[str, str], str | None]:
    """Ask the fast role for {id: digest}; returns (mapping, model)."""
    from ai_router import ai_max_tokens, ai_requested, llm_call, _extract_json  # type: ignore

    if not ai_requested(FLAG_NAME):
        raise RuntimeError("model call not available (flag off or no provider credential)")
    response = llm_call(
        "fast",
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=ai_max_tokens(),
    )
    payload = _extract_json(response.text) or {}
    return {k: v for k, v in payload.items() if isinstance(k, str) and isinstance(v, str)}, response.model


def _prompt(issues: list[dict[str, Any]], strict: bool = False, previous: dict[str, str] | None = None) -> str:
    head = EXAMPLES + "\n\n"
    if strict:
        head += (
            "These digests came back too long or restated the title. Rewrite each in at most 8 words "
            f"(never more than {DIGEST_MAX_CHARS - 12} characters): keep the one concrete thing delivered, drop everything else.\n\n"
        )
        if previous:
            head += "Previous answers:\n" + "\n".join(f"- {k}: {v}" for k, v in previous.items()) + "\n\n"
    body = "\n\n".join(_item_block(i) for i in issues)
    return head + "Return one JSON object mapping each id to its digest, nothing else.\n\nITEMS:\n\n" + body


def generate(slug: str, issues: list[dict[str, Any]], caller: Callable[[str], tuple[dict[str, str], str | None]] = default_caller) -> dict[str, Any]:
    """Write digests for `issues` into the cache. One retry per failed item."""
    if not issues:
        return {"written": 0, "failed": 0}
    cache = load_cache(slug)
    written = failed = 0
    model_used: str | None = None
    budget = _budget_bytes()
    retry: list[dict[str, Any]] = []
    for chunk in chunk_by_bytes(issues, budget):
        try:
            mapping, model_used = caller(_prompt(chunk))
        except Exception as error:  # a failed call leaves rows on their titles; nothing is invented
            stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            code = safe_error(error, "digest batch")
            for issue in chunk:
                cache[issue["id"]] = {"hash": content_hash(issue), "digest": None, "failed": code, "transient": True, "failed_at": stamp}
                failed += 1
            continue
        for issue in chunk:
            line = validate(mapping.get(issue["id"]), issue)
            if line:
                cache[issue["id"]] = {"hash": content_hash(issue), "digest": line, "model": model_used}
                written += 1
            else:
                issue["_previous"] = mapping.get(issue["id"]) if isinstance(mapping.get(issue["id"]), str) else None
                retry.append(issue)
        save_cache(slug, cache)  # progress lands as it happens; the page fills in chunk by chunk
    for issue in retry:
        try:
            prev = {issue["id"]: issue["_previous"]} if issue.get("_previous") else None
            mapping, model_used = caller(_prompt([issue], strict=True, previous=prev))
            line = validate(mapping.get(issue["id"]), issue)
        except Exception as error:
            line = None
            mapping = {"_error": safe_error(error, "digest retry"), "_transient": True}
        if line:
            cache[issue["id"]] = {"hash": content_hash(issue), "digest": line, "model": model_used}
            written += 1
        else:
            entry = {"hash": content_hash(issue), "digest": None, "failed": mapping.get("_error", "no valid digest after retry")}
            if mapping.get("_transient"):
                entry["transient"] = True
                entry["failed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            cache[issue["id"]] = entry
            failed += 1
    save_cache(slug, cache)
    return {"written": written, "failed": failed, "model": model_used}


_JOBS: dict[str, threading.Thread] = {}
_JOBS_LOCK = threading.Lock()


def _run(slug: str, issues: list[dict[str, Any]], caller: Callable) -> None:
    try:
        generate(slug, issues, caller)
    except Exception as error:  # a thread's exception would otherwise vanish
        sys.stderr.write(f"digest job for {slug} failed: {error!r}\n")
        sys.stderr.flush()


def schedule(slug: str, issues: list[dict[str, Any]], caller: Callable = default_caller) -> bool:
    """Generate in the background, one job per board at a time. True while a job runs."""
    if not issues:
        return False
    with _JOBS_LOCK:
        job = _JOBS.get(slug)
        if job and job.is_alive():
            return True
        snapshot = [dict(i) for i in issues]
        thread = threading.Thread(target=_run, args=(slug, snapshot, caller), name=f"digest:{slug}", daemon=True)
        _JOBS[slug] = thread
        thread.start()
        return True


# ---------------------------------------------------------------- summaries
# A digest is a line; a summary is the paragraph a reader wants when they
# open the item: what it is, why it exists, what has to happen, what done
# looks like. Written once per content hash by a human-facing presentation
# layer, cached beside the digest, and never stored in the board.

SUMMARY_SYSTEM = (
    "You explain software work items on a project board to the person who runs the project. "
    "Write one short paragraph in plain, direct language: what the item is about, why it exists "
    "(the problem or the decision behind it), what has to be done, and what done looks like. "
    "Use only what the item says; if something is unknown, say so in a few words rather than inventing it. "
    "No headings, no bullet lists, no ids, no preamble, no restating the title."
)

# One paragraph the inspector holds above the title without pushing it out of
# view: measured on the built page (300px column, 12px mono, ~36 characters a
# line) 450 characters is about twelve lines. The cap is part of the cache key,
# so changing it regenerates every summary on its next view.
SUMMARY_MAX_CHARS = 450
# Models hold a word count far better than a character count; 65 words of
# this register measured 400–450 characters on the summaries written so far.
SUMMARY_MAX_WORDS = 65


def summary_prompt(issue: dict[str, Any]) -> str:
    parts = [f"title: {issue.get('title', '')}"]
    if issue.get("track_title"):
        parts.append(f"program: {issue['track_title']}")
    if issue.get("status"):
        parts.append(f"status: {issue['status']}")
    if issue.get("description"):
        parts.append(f"description: {' '.join(str(issue['description']).split())}")
    blockers = [b.get("title") or b.get("id") for b in issue.get("blockers") or [] if isinstance(b, dict)]
    if blockers:
        parts.append("waits on: " + "; ".join(str(b) for b in blockers))
    if issue.get("source"):
        parts.append(f"source: {issue['source']}")
    return f"Explain this item in one paragraph of at most {SUMMARY_MAX_WORDS} words (under {SUMMARY_MAX_CHARS} characters).\n\n" + "\n".join(parts)


def default_summary_caller(prompt: str) -> tuple[str, str | None]:
    from ai_router import ai_max_tokens, ai_requested, llm_call  # type: ignore

    if not ai_requested(FLAG_NAME):
        raise RuntimeError("model call not available (flag off or no provider credential)")
    response = llm_call("fast", [{"role": "system", "content": SUMMARY_SYSTEM}, {"role": "user", "content": prompt}], max_tokens=ai_max_tokens())
    return response.text.strip(), response.model


def validate_summary(text: Any) -> str | None:
    if not isinstance(text, str):
        return None
    body = text.strip()
    if not body or body.lower().startswith(("#", "- ", "* ")):
        return None
    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not paragraphs:
        return None
    return "\n\n".join(paragraphs)


def fit_summary(text: str) -> str:
    """Never longer than the cap: cut at the last sentence end inside it."""
    if len(text) <= SUMMARY_MAX_CHARS:
        return text
    head = text[:SUMMARY_MAX_CHARS]
    cut = max(head.rfind(". "), head.rfind("."), head.rfind("; "))
    if cut > SUMMARY_MAX_CHARS // 2:
        return head[: cut + 1].rstrip()
    return head.rsplit(" ", 1)[0].rstrip() + "…"


def summarize(slug: str, issue: dict[str, Any], caller: Callable[[str], tuple[str, str | None]] | None = None) -> dict[str, Any]:
    """Return {summary, model, cached} for one item, generating on a cache miss."""
    caller = caller or default_summary_caller  # resolved at call time, so a test can stand in for the model
    cache = load_cache(slug)
    h = f"{content_hash(issue)}:{SUMMARY_MAX_CHARS}:{SUMMARY_MAX_WORDS}"
    entry = cache.get(issue["id"]) or {}
    if entry.get("summary") and entry.get("summary_hash") == h:
        return {"summary": entry["summary"], "model": entry.get("summary_model"), "cached": True}
    try:
        text, model = caller(summary_prompt(issue))
    except Exception as error:
        return {"summary": None, "error": safe_error(error, f"summary {issue.get('id')}"), "cached": False}
    body = validate_summary(text)
    if body and len(body) > SUMMARY_MAX_CHARS:
        try:  # one shorten pass, then the trim guarantees the cap
            text2, model2 = caller(f"Shorten this to at most {SUMMARY_MAX_WORDS // 2 + 15} words, keeping the point:\n\n{body}")
            body2 = validate_summary(text2)
            if body2:
                body, model = body2, model2 or model
        except Exception as error:
            safe_error(error, f"summary shorten {issue.get('id')}")
        body = fit_summary(body)
    if not body:
        return {"summary": None, "error": "no usable summary", "cached": False}
    cache = load_cache(slug)  # re-read: the digest job may have written meanwhile
    merged = dict(cache.get(issue["id"]) or {})
    merged.update({"summary": body, "summary_hash": h, "summary_model": model})
    if "hash" not in merged:
        merged["hash"] = content_hash(issue)
    cache[issue["id"]] = merged
    save_cache(slug, cache)
    return {"summary": body, "model": model, "cached": False}


# ---------------------------------------------------------------- ask
# A question answered from the board's own rows, nothing else, citing ids.
# Receipts-only: every claim names an item; "nothing on the board covers
# this" is a valid answer.

ASK_SYSTEM = (
    "You answer questions about a software project board using only the rows you are given. "
    "Read every row before answering, including rows marked done: a done item that covers the question "
    "means the board covers it and the work is finished; say which state each cited item is in. "
    "Cite the item id (mn-xxxxxx) inline for every item you mention, and never cite an id that is not in the rows. "
    "If nothing on the board covers the question, say so plainly. "
    "Two short paragraphs at most; no headings, no bullet lists, no preamble."
)

# Questions are rare and read by a person deciding something; the deep role
# (the router's most capable chain) is worth its latency here. Digests and
# summaries stay on the fast role because they run in bulk.
ASK_ROLE = "deep"


def _ask_rows(rows: list[dict[str, Any]]) -> list[str]:
    out = []
    for r in rows:
        if r.get("kind") == "track":
            continue
        desc = " ".join(str(r.get("description") or "").split())
        out.append(f"{r['id']} [{r.get('effective') or r.get('status')}] {r.get('digest') or r.get('title')}" + (f" — {desc}" if desc else ""))
    return out


def _ask_budget_bytes() -> int:
    from models import resolve  # type: ignore

    window = int(resolve(ASK_ROLE)["capabilities"]["max_input_tokens"])
    return window - len(ASK_SYSTEM.encode("utf-8"))


def ask_prompt(rows: list[dict[str, Any]], question: str) -> str:
    budget = _ask_budget_bytes() - len(question.encode("utf-8"))
    lines, used, dropped = [], 0, 0
    for line in _ask_rows(rows):
        size = len(line.encode("utf-8")) + 1
        if used + size > budget:
            dropped += 1
            continue
        lines.append(line); used += size
    note = f"\n\n({dropped} rows did not fit the model's input window and were left out.)" if dropped else ""
    return f"QUESTION: {question}\n\nBOARD ROWS:\n" + "\n".join(lines) + note


def default_ask_caller(prompt: str) -> tuple[str, str | None]:
    from ai_router import ai_max_tokens, ai_requested, llm_call  # type: ignore

    if not ai_requested(FLAG_NAME):
        raise RuntimeError("model call not available (flag off or no provider credential)")
    from ai_router import DEFAULT_CLIENT_TIMEOUT_SECONDS  # type: ignore

    # One deep answer over this 122-row board measured 22.6s against the
    # router's default client timeout; twice that default leaves room for a
    # board twice the size before the answer is lost to the clock.
    response = llm_call(
        ASK_ROLE, [{"role": "system", "content": ASK_SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=ai_max_tokens(), timeout_seconds=DEFAULT_CLIENT_TIMEOUT_SECONDS * 2,
    )
    return response.text.strip(), response.model


def ask(rows: list[dict[str, Any]], question: str, caller: Callable[[str], tuple[str, str | None]] | None = None) -> dict[str, Any]:
    caller = caller or default_ask_caller
    question = " ".join(question.split())
    if not question:
        return {"answer": None, "cited": [], "error": "empty question"}
    try:
        text, model = caller(ask_prompt(rows, question))
    except Exception as error:
        return {"answer": None, "cited": [], "error": safe_error(error, "ask")}
    known = {r["id"] for r in rows}
    cited = [i for i in dict.fromkeys(_MN_ID.findall(text)) if i in known]
    return {"answer": text.strip(), "cited": cited, "model": model}
