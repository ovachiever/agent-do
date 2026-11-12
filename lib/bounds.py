"""Bounds — the caps a command ships, and where each one came from.

The contracts layer already holds one abstract property across every registry tool without
anyone remembering to: every verb declares which beats it performs. This module
adds the second property. A command that caps its output declares where the cap
came from, and the declaration is checked against the quantity authority rather
than believed.

Four sources, and the source picks which enforcement applies:

  registry   the cap IS a published ceiling; `ref` is an authority key and the
             shipped literal must equal it exactly. A copy that differs is stale.
  derived    the cap is computed from a ceiling; `ref` is an expression over
             authority keys and the shipped literal must equal what it computes.
             The factor in the expression is the explanation.
  measured   the cap is counted at runtime; no literal may be shipped at all,
             because a counted quantity is true only now.
  none       no ceiling governs this number — it is a caller-facing default.
             Exempt from the capacity checks, and only from those: the audit
             still requires the output to carry its total, and any truncation
             marker to carry magnitude.

Detection is evidence-based, never prose-based. A command is bounding because a
numeric literal sits in a bounding position in its implementation, at a file and
line this module will print — not because its description sounded like it might
return a lot of rows. The same scanner runs outward over any project, which is
the point: one detector, two directions.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Callable, Iterable

# ── what counts as a bounding parameter ───────────────────────────────────
#
# Curated rather than pattern-guessed: every name here bounds *how much* comes
# back, and the unit is recorded so a bound can be compared to a ceiling in the
# same unit. Names that bound something other than quantity (`timeout`,
# `retries`, `port`) are deliberately absent — they are not what an agent
# invents when it should have measured.
BOUND_PARAMETERS: dict[str, dict[str, str]] = {
    # token budgets
    "max_tokens": {"unit": "tokens", "what": "output token ceiling"},
    "maxtokens": {"unit": "tokens", "what": "output token ceiling"},
    "max_output_tokens": {"unit": "tokens", "what": "output token ceiling"},
    "max_completion_tokens": {"unit": "tokens", "what": "output token ceiling"},
    "max_tokens_to_sample": {"unit": "tokens", "what": "output token ceiling"},
    "max_input_tokens": {"unit": "tokens", "what": "input token ceiling"},
    "context_window": {"unit": "tokens", "what": "context window"},
    "token_budget": {"unit": "tokens", "what": "token budget"},
    "max_context_tokens": {"unit": "tokens", "what": "context budget"},
    # row and record counts
    "limit": {"unit": "rows", "what": "row cap"},
    "max_results": {"unit": "rows", "what": "result cap"},
    "maxresults": {"unit": "rows", "what": "result cap"},
    "max_items": {"unit": "rows", "what": "item cap"},
    "max_rows": {"unit": "rows", "what": "row cap"},
    "page_size": {"unit": "rows", "what": "page size"},
    "pagesize": {"unit": "rows", "what": "page size"},
    "per_page": {"unit": "rows", "what": "page size"},
    "perpage": {"unit": "rows", "what": "page size"},
    "page_limit": {"unit": "rows", "what": "page ceiling"},
    "top_k": {"unit": "rows", "what": "nearest-neighbour cap"},
    "topk": {"unit": "rows", "what": "nearest-neighbour cap"},
    "n_results": {"unit": "rows", "what": "result cap"},
    "num_results": {"unit": "rows", "what": "result cap"},
    "batch_size": {"unit": "rows", "what": "batch size"},
    "max_depth": {"unit": "levels", "what": "walk depth"},
    "max_pages": {"unit": "pages", "what": "page cap"},
    # character and byte budgets
    "max_chars": {"unit": "chars", "what": "character budget"},
    "max_length": {"unit": "chars", "what": "length cap"},
    "maxlength": {"unit": "chars", "what": "length cap"},
    "max_bytes": {"unit": "bytes", "what": "byte budget"},
    "chunk_size": {"unit": "chars", "what": "chunk size"},
    "max_chunk_chars": {"unit": "chars", "what": "chunk budget"},
}

# Case-insensitive lookup: MAX_TOKENS, maxTokens, and max_tokens are one name.
def canonical_parameter(name: str) -> str | None:
    key = re.sub(r"[^a-z0-9]", "_", name.strip().lower()).strip("_")
    if key in BOUND_PARAMETERS:
        return key
    flattened = key.replace("_", "")
    for candidate in BOUND_PARAMETERS:
        if candidate.replace("_", "") == flattened:
            return candidate
    return None


_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_INT = r"\d[\d_]*"

# Syntaxes that put a literal in a bounding position. Each carries an id so a
# finding can say how it was recognized instead of just asserting it was.
_SYNTAX_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # name = 123 / name: 123 / name="123" — Python kwargs, JS/YAML/JSON objects,
    # and shell locals, where the number is a string and just as binding.
    ("assignment", re.compile(rf"\b(?P<name>{_NAME})\s*[:=]\s*[\"']?(?P<value>{_INT})\b")),
    # bash defaults: ${LIMIT:-20}, ${2:-10} guarded by an assignment to a name
    ("shell_default", re.compile(rf"\b(?P<name>{_NAME})\s*=\s*[\"']?\$\{{[^}}]*:-\s*(?P<value>{_INT})")),
    # fallback defaults: `max_tokens: request.max_tokens || 1024`, `?? 1024`,
    # `or 1024`. The literal is the cap whenever the caller passes nothing,
    # which is most of the time — the assignment pattern cannot see it because
    # the value position starts with an expression.
    ("or_default", re.compile(
        rf"\b(?P<name>{_NAME})\s*[:=]\s*[^,;\n]*?(?:\|\||\?\?|\bor\b)\s*(?P<value>{_INT})\b")),
    # SQL: LIMIT 123
    ("sql_limit", re.compile(rf"\b(?P<name>LIMIT)\s+(?P<value>{_INT})\b")),
    # argparse / click: default=123 on a flag whose name is bounding
    ("flag_default", re.compile(
        rf"--(?P<name>[a-z][a-z0-9-]*)[^\n]*?\bdefault\s*[:=]\s*(?P<value>{_INT})\b", re.I)),
    # head -n 123 / tail -n 123
    ("head_tail", re.compile(rf"\b(?P<name>head|tail)\s+-n\s+(?P<value>{_INT})\b")),
    # .slice(0, 123)
    ("slice", re.compile(rf"\.(?P<name>slice)\(\s*0\s*,\s*(?P<value>{_INT})\s*\)")),
]

# `head`/`tail`/`slice` bound rows but are not parameter names, so they get
# their own units rather than living in BOUND_PARAMETERS (where they would
# match bare identifiers everywhere).
_SYNTAX_UNITS = {"head": "rows", "tail": "rows", "slice": "rows", "limit": "rows"}

# ── what makes a literal worth reporting outward ──────────────────────────
#
# Outward, a bare `limit = 50` beside nothing is a preference. Beside a model
# call it is a shipped ceiling somebody guessed. The family signals are what
# separate the two, and they are file-scoped because imports are file-scoped in
# every language this scans.
CONTEXT_FAMILIES: dict[str, re.Pattern[str]] = {
    "llm": re.compile(
        r"anthropic|openai|claude|gpt-[0-9]|messages\.create|chat\.completions|"
        r"ANTHROPIC_API_KEY|OPENAI_API_KEY|langchain|litellm|ollama|bedrock",
        re.I,
    ),
    "db": re.compile(
        r"\bSELECT\b|\bFROM\b\s+[a-z_]|sqlite3|psycopg|pymysql|supabase|prisma|"
        r"cursor\.execute|\.query\(|knex|drizzle|FTS5",
        re.I,
    ),
    "http": re.compile(
        r"requests\.(get|post|put|delete)|\bfetch\(|axios|urllib|httpx|"
        r"\bcurl\b|http[s]?://[a-z0-9.-]+/(v\d|api)",
        re.I,
    ),
}

_SCAN_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".rs", ".go", ".rb", ".sh", ".bash", ".sql"}
# A bound asserted inside a test is the test's fixture, not a shipped cap.
_TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)(/|$)|[._-](test|spec)\.[a-z]+$|^test_", re.I)
_SCAN_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "target", "dist",
    "build", ".next", ".cache", "vendor", ".mypy_cache", ".pytest_cache", "fixtures",
}
# A megabyte of one file is a bundle or a data blob, not hand-written bounds.
# Sized to admit every source file in this repo (the largest is well under it)
# while excluding minified and generated payloads.
_MAX_SCAN_BYTES = 1_000_000

_DOC_LINE = re.compile(r"^\s*(#|//|\*|--\s|\"\"\"|'''|<!--)")
_EXAMPLE_LINE = re.compile(r"^\s*(agent-do|agent-|\$ |>>> )")


def _is_doc_line(line: str) -> bool:
    """A bound quoted in help text or a comment documents a cap; it is not one."""
    return bool(_DOC_LINE.match(line) or _EXAMPLE_LINE.match(line))


def _families_in(text: str) -> list[str]:
    return sorted(name for name, pattern in CONTEXT_FAMILIES.items() if pattern.search(text))


def scan_text(path: str, text: str, require_family: bool = True) -> list[dict[str, Any]]:
    """Every bounding literal in one file, with how it was recognized.

    `require_family` is the difference between the outward scan and the inward
    gate. Outward, a literal only matters near an LLM/DB/HTTP call, because
    nothing else establishes that the number bounds a fetched set. Inward, the
    registry has already established that every scanned file is a command
    surface, so the family signal is corroboration rather than a precondition.
    """
    families = _families_in(text)
    if require_family and not families:
        return []
    findings: list[dict[str, Any]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        doc = _is_doc_line(line)
        seen_spans: set[tuple[int, int]] = set()
        for syntax, pattern in _SYNTAX_PATTERNS:
            for match in pattern.finditer(line):
                span = match.span("value")
                if span in seen_spans:
                    continue
                raw_name = match.group("name")
                name = canonical_parameter(raw_name)
                unit = None
                if name:
                    unit = BOUND_PARAMETERS[name]["unit"]
                elif raw_name.lower() in _SYNTAX_UNITS:
                    name = raw_name.lower()
                    unit = _SYNTAX_UNITS[name]
                else:
                    continue
                value = int(match.group("value").replace("_", ""))
                if value <= 0:
                    # Zero and negatives are sentinels ("no limit", "unset"),
                    # not caps. Reporting them would be noise with no ceiling
                    # to compare against.
                    continue
                seen_spans.add(span)
                findings.append(
                    {
                        "file": path,
                        "line": index,
                        "parameter": name,
                        "raw_parameter": raw_name,
                        "value": value,
                        "unit": unit,
                        "syntax": syntax,
                        "site_kind": "doc" if doc else "code",
                        "families": families,
                        "text": line.strip()[:200],
                    }
                )
    return findings


def _looks_like_script(text: str) -> bool:
    return text.startswith("#!")


# ── attributing a literal to the verb that ships it ───────────────────────

_DEFINITION_PATTERNS = [
    # bash: cmd_search() { … }  /  search_cmd() { … }  /  do_search() { … }
    re.compile(rf"^\s*(?:function\s+)?(?P<name>{_NAME})\s*\(\s*\)\s*\{{"),
    # python / js: def cmd_search(…)  /  function cmdSearch(…)
    re.compile(rf"^\s*(?:async\s+)?(?:def|function)\s+(?P<name>{_NAME})\b"),
]
# bash case arms: `search)` or `"search"|"find")`
_CASE_ARM = re.compile(r"^\s*\"?(?P<name>[a-z][a-z0-9-]*)\"?(?:\s*\|\s*\"?[a-z][a-z0-9-]*\"?)*\s*\)")


def attribute_verb(text: str, line_number: int, verbs: Iterable[str]) -> str | None:
    """Name the declared verb whose implementation encloses this line.

    Walks upward to the nearest function definition or case arm and matches its
    name against the tool's declared commands. Returns None rather than
    guessing — an unattributed site is reported as unattributed, because a wrong
    attribution would send a reviewer to the wrong verb.
    """
    candidates = {str(verb).split()[0] for verb in verbs if str(verb).strip()}
    if not candidates:
        return None
    lines = text.splitlines()
    for index in range(min(line_number, len(lines)) - 1, -1, -1):
        line = lines[index]
        for pattern in _DEFINITION_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            name = match.group("name")
            token = re.sub(r"^(cmd_|do_|handle_|run_)|(_cmd|_command)$", "", name.lower())
            token = token.replace("_", "-")
            if token in candidates:
                return token
            if name.lower() in candidates:
                return name.lower()
            return None  # nearest enclosing definition is not a verb; stop here
        arm = _CASE_ARM.match(line)
        if arm and arm.group("name") in candidates:
            return arm.group("name")
    return None


def is_test_path(path: str) -> bool:
    return bool(_TEST_PATH.search(str(path)))


# ── declarations ──────────────────────────────────────────────────────────

BOUND_SOURCES = ("registry", "derived", "measured", "none")
# One declaration may stand for every site in a tool that belongs to no single
# verb — a cap inside shared library code is implementation detail of all of
# them, and keying it to an arbitrary verb would send a reviewer to the wrong
# place. It is not an escape hatch: it carries the same source/ref/why and is
# drift-checked identically.
TOOL_WIDE_KEY = "*"


def get_tool_bounds(info: dict) -> dict[str, dict[str, Any]]:
    """Normalized bound declarations for one tool, keyed by verb (or `*`)."""
    raw = info.get("bounds")
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for verb, declaration in raw.items():
        if isinstance(declaration, dict):
            normalized[str(verb)] = dict(declaration)
    return normalized


def validate_bound_shape(tool: str, verb: str, declaration: dict[str, Any]) -> list[dict[str, str]]:
    """Shape errors in one declaration. The source decides what `ref` must be."""
    errors: list[dict[str, str]] = []

    def bad(code: str, message: str) -> None:
        errors.append({"code": code, "tool": tool, "verb": verb, "message": message})

    source = str(declaration.get("source") or "").strip()
    if source not in BOUND_SOURCES:
        bad("unknown_bound_source",
            f"bound source must be one of {', '.join(BOUND_SOURCES)}, got: {source or '(missing)'}")
    why = str(declaration.get("why") or "").strip()
    if not why:
        bad("bound_without_why", "bound declares no `why`; an exemption without a reason is silence")
    ref = declaration.get("ref")
    if source in ("registry", "derived", "measured"):
        if not str(ref or "").strip():
            bad("bound_without_ref", f"source: {source} requires a `ref`")
    elif source == "none" and str(ref or "").strip():
        bad("bound_ref_on_none", "source: none carries a ref; a bound governed by nothing cannot cite one")
    unknown = sorted(set(declaration) - {"source", "ref", "why"})
    if unknown:
        bad("unknown_bound_field", f"unknown field(s) in bound declaration: {', '.join(unknown)}")
    return errors


# ── the derived floor ─────────────────────────────────────────────────────


def authority_delivery_floor(config: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """The smallest delivery-to-capacity ratio the authority itself publishes.

    THE DERIVATION, because a threshold invented for a checker is the exact
    defect this checker exists to prevent:

    Every model record pairs a capacity (`max_input_tokens`, everything the
    model may hold) with a delivery ceiling (`max_tokens`, the most it may hand
    back in one response). That pair is a published statement, by the people who
    built the system, about how small a single delivery is allowed to be
    relative to the space it is drawn from. Take the minimum over every record
    and you have the tightest such ratio anyone in the authority has committed
    to in writing.

    A declared bound that *claims a ceiling governs it* and lands below that
    ratio is smaller than any delivery ceiling any provider considered worth
    publishing — so its stated factor is doing no work, and the number came from
    somewhere other than the ceiling it cites. That is the `inject at 6000 chars
    against a 200k-token window` shape, and it is what this floor catches.

    The number is READ, never written: it is recomputed from models.yaml on
    every run and moves when the authority moves. Nothing in this repo stores
    it. It applies only to bounds whose declaration asserts a ceiling
    relationship (`registry`, `derived`) — a `source: none` bound claims no
    relationship, so there is no ratio to judge, and the audit holds it to
    carrying its totals instead.

    Returns None when no record publishes both numbers: with no evidence there
    is no floor, and a checker with no evidence must not invent one.
    """
    from quantities import load_config as _load

    config = config if config is not None else _load()
    records = config.get("models")
    if not isinstance(records, dict):
        return None
    best: tuple[float, str] | None = None
    for name, record in sorted(records.items()):
        if not isinstance(record, dict):
            continue
        delivery = record.get("max_tokens")
        capacity = record.get("max_input_tokens")
        if not _positive_number(delivery) or not _positive_number(capacity):
            continue
        ratio = delivery / capacity
        if best is None or ratio < best[0]:
            best = (ratio, str(name))
    if best is None:
        return None
    ratio, record_name = best
    return {
        "ratio": ratio,
        "from_record": record_name,
        "derivation": (
            f"min(max_tokens / max_input_tokens) over every model record in models.yaml; "
            f"tightest is {record_name}. Recomputed each run — never stored."
        ),
    }


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


# The only other tolerance in this module, and it is a property of integers
# rather than a preference: rounding a real number to an integer moves it by at
# most 0.5, so 0.5 is the unique tolerance that admits exactly the rounding a
# correct expression performs and admits no second number beyond it.
INTEGER_ROUNDING_TOLERANCE = 0.5


# ── resolving a ref against the authority ─────────────────────────────────

_ARITH_OK = re.compile(r"^[0-9eE+\-*/(). _]*$")

# A ref is arithmetic over authority keys ("...max_input_tokens * 0.5"), so
# literal_eval cannot evaluate it — it rejects every BinOp. Instead the parsed
# tree is walked and every node type is checked against this whitelist before
# anything runs: no Name, no Call, no Attribute, no Subscript, no comprehension
# can survive, and constants must be numbers. What reaches compile() is
# therefore arithmetic over numeric literals and nothing else. Whitelist rather
# than sanitization because a ref is data read out of registry.yaml, and data
# does not get an evaluator with a denylist.
_ARITH_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Pow,
    ast.USub, ast.UAdd,
)


def _arithmetic(expression: str) -> Any:
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ARITH_NODES):
            raise ValueError(f"{type(node).__name__} is not arithmetic")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ValueError(f"{node.value!r} is not a number")
    return eval(compile(tree, "<ref>", "eval"), {"__builtins__": {}}, {})  # noqa: S307


def resolve_ref(ref: str, lookup: Callable[[str], Any], keys: Iterable[str]) -> dict[str, Any]:
    """Turn a ref into a number, or say exactly why it could not be turned.

    A ref is either a bare authority key or an arithmetic expression over keys.
    Keys are matched longest-first because subjects carry dots of their own, and
    everything that survives substitution must be plain arithmetic — no names,
    no calls, no attribute access.
    """
    text = str(ref or "").strip()
    if not text:
        return {"ok": False, "reason": "empty ref"}
    known = sorted(keys, key=len, reverse=True)
    used: list[dict[str, Any]] = []
    expression = text
    for key in known:
        if key not in expression:
            continue
        value = lookup(key)
        used.append({"key": key, "value": value})
        expression = expression.replace(key, f"({value})")
    if not used:
        return {"ok": False, "reason": f"ref names no authority key: {text}",
                "hint": "list them with: agent-do harness quantity keys"}
    if not _ARITH_OK.match(expression):
        leftover = "".join(sorted(set(re.findall(r"[A-Za-z_][A-Za-z0-9_.-]*", expression))))
        return {"ok": False,
                "reason": f"ref is not plain arithmetic once keys are substituted: {expression}",
                "unresolved": leftover}
    try:
        value = _arithmetic(expression)
    except Exception as exc:  # noqa: BLE001 - any arithmetic failure is a caller error
        return {"ok": False, "reason": f"could not evaluate ref: {exc}"}
    if not _positive_number(value):
        return {"ok": False, "reason": f"ref evaluates to {value!r}, which is not a positive quantity"}
    return {"ok": True, "value": value, "keys": used, "expanded": expression}


# ── collecting this repo's own bounding sites ─────────────────────────────


def tool_source_files(repo_root: Path, name: str) -> list[Path]:
    base = Path(repo_root) / "tools" / f"agent-{name}"
    if not base.exists():
        return []
    if base.is_file():
        return [base]
    files: list[Path] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or any(part in _SCAN_SKIP_DIRS for part in path.parts):
            continue
        if path.suffix and path.suffix not in _SCAN_SUFFIXES:
            continue
        files.append(path)
    return files


def collect_tool_sites(repo_root: Path, name: str, info: dict) -> list[dict[str, Any]]:
    """Every shipped bounding literal in one tool, attributed to a verb if it can be."""
    repo_root = Path(repo_root)
    verbs = list((info.get("commands") or {}).keys())
    sites: list[dict[str, Any]] = []
    for path in tool_source_files(repo_root, name):
        try:
            if path.stat().st_size > _MAX_SCAN_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not path.suffix and not _looks_like_script(text):
            continue
        label = str(path.relative_to(repo_root))
        if is_test_path(label):
            continue
        for finding in scan_text(label, text, require_family=False):
            if finding["site_kind"] != "code":
                continue
            finding["tool"] = name
            finding["verb"] = attribute_verb(text, finding["line"], verbs)
            sites.append(finding)
    return sites


def authority_units(config: dict[str, Any] | None = None) -> set[str]:
    """Which units the authority can currently answer in."""
    from quantities import authority_entries

    return {entry["unit"] for entry in authority_entries(config) if entry.get("unit")}


def mark_gate_eligible(sites: list[dict[str, Any]], units: set[str]) -> list[dict[str, Any]]:
    """Split sites into what the gate may demand a receipt for, and what it may not.

    THE REACH RULE: the gate demands a receipt only where a receipt is
    obtainable — that is, where the authority holds at least one ceiling in the
    site's own unit. Demanding a citation the authority cannot supply would push
    the next agent toward inventing one, which is the defect, not the fix.

    This is computed from the authority on every run, never listed here. When
    the authority learns a unit, every site in that unit becomes gated the same
    day, with no change to this file and nothing to remember. The ungated
    remainder is not suppressed: it is printed on every run as the ceilings this
    repo is owed.
    """
    for site in sites:
        site["gate_eligible"] = site["unit"] in units
    return sites


def covering_key(site: dict[str, Any], declarations: dict[str, dict[str, Any]]) -> str | None:
    verb = site.get("verb")
    if verb and verb in declarations:
        return verb
    if TOOL_WIDE_KEY in declarations:
        return TOOL_WIDE_KEY
    return None


def validate_tool_bounds(
    tool: str, info: dict, sites: list[dict[str, Any]]
) -> dict[str, Any]:
    """Gate one tool: every gate-eligible site is covered by a valid declaration."""
    declarations = get_tool_bounds(info)
    commands = info.get("commands") or {}
    errors: list[dict[str, Any]] = []
    gated = [site for site in sites if site.get("gate_eligible")]

    for verb, declaration in sorted(declarations.items()):
        if verb != TOOL_WIDE_KEY and not _verb_declared(verb, commands):
            errors.append({
                "code": "bound_unknown_command", "tool": tool, "verb": verb,
                "message": f"bound declared for a verb the tool does not have: {verb}",
            })
        errors.extend(validate_bound_shape(tool, verb, declaration))

    for site in gated:
        if covering_key(site, declarations) is None:
            where = f"{site['file']}:{site['line']}"
            errors.append({
                "code": "undeclared_bound", "tool": tool, "verb": site.get("verb"),
                "site": where,
                "message": (
                    f"{where} ships {site['parameter']}={site['value']} ({site['unit']}) "
                    f"with no bound declaration. Declare it under "
                    f"`bounds: {site.get('verb') or TOOL_WIDE_KEY}:` in registry.yaml "
                    f"with source/ref/why, or say `source: none` and mean it."
                ),
            })

    unused = sorted(
        verb for verb in declarations
        if not any(covering_key(site, declarations) == verb for site in gated)
    )
    return {
        "tool": tool,
        "declared": len(declarations),
        "sites": len(sites),
        "gated_sites": len(gated),
        "ungated_sites": len(sites) - len(gated),
        "errors": errors,
        "unused_declarations": unused,
    }


def _verb_declared(verb: str, commands: dict) -> bool:
    if not commands:
        return True
    return verb in commands or verb.split()[0] in commands


SHARED_CODE_DIRS = ("lib", "bin")


def collect_shared_sites(repo_root: Path) -> list[dict[str, Any]]:
    """Caps in code that belongs to no tool, and so has nowhere to declare.

    `lib/ai_router.py` and `bin/intent-router` ship real caps, but the
    declaration surface is a tool's registry entry and they have none. Rather
    than inventing a second declaration home or pretending the sites are not
    there, they are counted and printed on every gate run. Naming what the gate
    cannot reach is the difference between a boundary and a blind spot.
    """
    repo_root = Path(repo_root)
    sites: list[dict[str, Any]] = []
    for directory in SHARED_CODE_DIRS:
        base = repo_root / directory
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or any(part in _SCAN_SKIP_DIRS for part in path.parts):
                continue
            if path.suffix and path.suffix not in _SCAN_SUFFIXES:
                continue
            try:
                if path.stat().st_size > _MAX_SCAN_BYTES:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if not path.suffix and not _looks_like_script(text):
                continue
            label = str(path.relative_to(repo_root))
            if is_test_path(label):
                continue
            sites.extend(item for item in scan_text(label, text, require_family=False)
                         if item["site_kind"] == "code")
    return sites


def validate_bounds(registry: dict, repo_root: Path) -> dict[str, Any]:
    """The gate, over the whole registry."""
    tools = registry.get("tools") or {}
    units = authority_units()
    results = []
    owed: list[dict[str, Any]] = []
    for name, info in sorted(tools.items()):
        if not isinstance(info, dict):
            continue
        sites = mark_gate_eligible(collect_tool_sites(repo_root, name, info), units)
        result = validate_tool_bounds(name, info, sites)
        owed.extend(site for site in sites if not site["gate_eligible"])
        if result["errors"] or result["declared"] or result["sites"]:
            results.append(result)
    shared = collect_shared_sites(repo_root)
    return {
        "authority_units": sorted(units),
        "errors": sum(len(item["errors"]) for item in results),
        "tools_with_sites": sum(1 for item in results if item["sites"]),
        "gated_sites": sum(item["gated_sites"] for item in results),
        "ceilings_owed": len(owed),
        "ceilings_owed_units": sorted({site["unit"] for site in owed}),
        "owed": owed,
        "shared_code_sites": len(shared),
        "shared_code": shared,
        "results": [item for item in results if item["errors"] or item["gated_sites"]],
    }


# ── drift: a declared bound against the number it cites ───────────────────


def drift_bounds(registry: dict, repo_root: Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check every declared bound against the authority value it references."""
    from quantities import authority_entries, lookup

    entries = authority_entries(config)
    values = {entry["key"]: entry["value"] for entry in entries}
    floor = authority_delivery_floor(config)
    units = authority_units(config)
    tools = registry.get("tools") or {}
    findings: list[dict[str, Any]] = []

    for name, info in sorted(tools.items()):
        if not isinstance(info, dict):
            continue
        declarations = get_tool_bounds(info)
        if not declarations:
            continue
        sites = mark_gate_eligible(collect_tool_sites(repo_root, name, info), units)
        for verb, declaration in sorted(declarations.items()):
            source = str(declaration.get("source") or "")
            covered = [site for site in sites
                       if site.get("gate_eligible") and covering_key(site, declarations) == verb]
            if source == "none":
                continue
            ref = str(declaration.get("ref") or "")
            if source == "measured":
                for site in covered:
                    findings.append(_finding(
                        "measured_bound_ships_literal", name, verb, site,
                        f"declared source: measured, but {site['file']}:{site['line']} ships the "
                        f"literal {site['value']}. A counted quantity is true only now; "
                        f"measure it at call time or change the source.",
                    ))
                continue
            resolved = resolve_ref(ref, lambda key: values[key], values)
            if not resolved["ok"]:
                findings.append(_finding(
                    "dangling_ref", name, verb, None,
                    f"ref {ref!r} does not resolve: {resolved['reason']}",
                ))
                continue
            expected = resolved["value"]
            for site in covered:
                actual = site["value"]
                if source == "registry" and actual != expected:
                    findings.append(_finding(
                        "stale_copy", name, verb, site,
                        f"declared source: registry against {ref} = {expected}, but "
                        f"{site['file']}:{site['line']} ships {actual} "
                        f"({actual / expected:.4g} of it). A copy of a published number that "
                        f"differs from it is stale by definition.",
                        expected=expected, actual=actual, ratio=actual / expected,
                    ))
                elif source == "derived" and abs(actual - expected) > INTEGER_ROUNDING_TOLERANCE:
                    findings.append(_finding(
                        "expression_mismatch", name, verb, site,
                        f"declared source: derived as {ref} = {expected:g}, but "
                        f"{site['file']}:{site['line']} ships {actual}. Tolerance is "
                        f"{INTEGER_ROUNDING_TOLERANCE} — the most integer rounding can move a "
                        f"real number, and nothing more.",
                        expected=expected, actual=actual,
                    ))
            if floor and source in ("registry", "derived") and resolved["keys"]:
                ceiling = max(item["value"] for item in resolved["keys"])
                ratio = expected / ceiling if ceiling else None
                if ratio is not None and ratio < floor["ratio"]:
                    findings.append(_finding(
                        "below_authority_floor", name, verb, None,
                        f"declared bound resolves to {expected:g}, {ratio:.4g} of the ceiling it "
                        f"cites ({ceiling:g}). The smallest delivery-to-capacity ratio the "
                        f"authority itself publishes is {floor['ratio']:.4g} "
                        f"({floor['from_record']}), so this bound is "
                        f"{floor['ratio'] / ratio:.4g}x below the tightest ratio anyone in the "
                        f"authority committed to. Cite something that justifies it, or declare "
                        f"`source: none` and let the audit hold it to carrying its totals.",
                        expected=expected, ratio=ratio, floor=floor["ratio"],
                    ))

    coverage = check_router_coverage(config)
    return {
        "ok": not findings and coverage["ok"],
        "floor": floor,
        "findings": findings,
        "coverage": coverage,
    }


def _finding(code: str, tool: str, verb: str, site: dict | None, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"code": code, "tool": tool, "verb": verb, "message": message}
    if site:
        payload["site"] = f"{site['file']}:{site['line']}"
        payload["parameter"] = site["parameter"]
    payload.update(extra)
    return payload


def check_router_coverage(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every model the router can reach must have an authority record.

    Filed as mn-b7cb18: a correct lookup refuses when the authority has no
    record, and the tempting next move is the forbidden literal. The refusal is
    right; the gap is the bug. Reachability is exactly what `roles.*.chain`
    declares — a model no chain names cannot be selected, so nothing is owed for
    it — which keeps this check inside what the registry can prove and leaves
    the data fix with whoever maintains models.yaml.
    """
    from quantities import load_config

    config = config if config is not None else load_config()
    records = config.get("models") or {}
    missing: list[dict[str, str]] = []
    reachable: list[str] = []
    for role, spec in sorted((config.get("roles") or {}).items()):
        for model in (spec or {}).get("chain") or []:
            name = str(model)
            if name not in reachable:
                reachable.append(name)
            if name not in records:
                missing.append({"role": role, "model": name})
    return {
        "ok": not missing,
        "reachable": sorted(reachable),
        "missing": missing,
        "message": (
            "every model a role chain can select has an authority record"
            if not missing
            else "role chains can select models the authority cannot answer for: "
            + ", ".join(f"{item['model']} (role {item['role']})" for item in missing)
        ),
    }


# ── audit: does the output carry its own total? ───────────────────────────
#
# A cap is tolerable when the caller can see it happened and how much was left
# behind. `[truncated: 30 of 197 shown]` is a receipt; a bare "truncated" is the
# bare fact of a cut, which tells a caller nothing and reads to an agent as
# completeness. This is what `source: none` is held to in exchange for its
# exemption from the capacity checks.

TOTAL_KEYS = ("total", "total_count", "totalCount", "count", "matched", "available", "found")
MAGNITUDE = re.compile(r"\b(\d[\d,_]*)\s*(?:of|/)\s*(\d[\d,_]*)\b", re.I)
BARE_CUT = re.compile(
    r"\btruncat\w*|\bshowing first\b|\bmore results\b|\band more\b|\.{3}\s*more\b|\bcapped\b", re.I
)


def audit_payload(payload: Any, path: str | None = None) -> dict[str, Any]:
    """Verdict on one JSON response: does it let a caller tell capped from complete?"""
    rows, source = _find_rows(payload, path)
    if rows is None:
        return {"outcome": "skip", "reason": source}
    counted = len(rows)
    totals = {}
    if isinstance(payload, dict):
        totals = {key: payload[key] for key in TOTAL_KEYS
                  if key in payload and _positive_number(payload[key])}
    cut_declared = isinstance(payload, dict) and any(
        payload.get(marker) is True for marker in ("truncated", "has_more", "is_truncated")
    )
    if not totals:
        if cut_declared:
            return {"outcome": "fail", "rows": counted, "array": source,
                    "reason": "declares a cut but carries no total: the bare fact of a cut, "
                              "without the magnitude a caller needs to ask for the rest"}
        return {"outcome": "fail", "rows": counted, "array": source,
                "reason": f"returns {counted} rows in `{source}` and no total; a caller cannot "
                          f"tell a complete set from a capped one"}
    total = max(totals.values())
    if total < counted:
        return {"outcome": "fail", "rows": counted, "total": total, "array": source,
                "reason": f"declares total {total} but returned {counted} rows"}
    return {"outcome": "ok", "rows": counted, "total": total, "array": source,
            "total_keys": sorted(totals),
            "reason": f"{counted} of {total} — the cut, if any, carries its magnitude"}


def _find_rows(payload: Any, path: str | None) -> tuple[list | None, str]:
    if path:
        current = payload
        for segment in path.split("."):
            if not isinstance(current, dict) or segment not in current:
                return None, f"no value at --path {path}"
            current = current[segment]
        if not isinstance(current, list):
            return None, f"value at {path} is not an array"
        return current, path
    if isinstance(payload, list):
        return payload, "$"
    if not isinstance(payload, dict):
        return None, "payload is a scalar; nothing to audit"
    arrays = sorted(key for key, value in payload.items() if isinstance(value, list))
    if not arrays:
        return None, "payload contains no array; nothing was bounded"
    if len(arrays) > 1:
        return None, f"payload contains {len(arrays)} arrays ({', '.join(arrays)}); name one with --path"
    return payload[arrays[0]], arrays[0]


def audit_text(text: str) -> dict[str, Any]:
    """Verdict on human-readable output: any truncation marker must carry magnitude."""
    body = str(text or "")
    cuts = [line.strip() for line in body.splitlines() if BARE_CUT.search(line)]
    if not cuts:
        return {"outcome": "skip", "reason": "no truncation marker in output"}
    naked = [line for line in cuts if not MAGNITUDE.search(line)]
    if naked:
        return {"outcome": "fail", "markers": cuts[:5],
                "reason": f"{len(naked)} truncation marker(s) carry no magnitude, e.g. "
                          f"{naked[0][:120]!r}; a marker must say N of M"}
    return {"outcome": "ok", "markers": cuts[:5],
            "reason": "every truncation marker carries its magnitude"}


def audit_bounds(registry: dict, repo_root: Path, runner: Callable[..., Any],
                 only_tool: str | None = None) -> dict[str, Any]:
    """Probe every declared bound's verb and grade what comes back.

    Only declared read verbs are probed, and only ones the registry says are
    read-only: the same safety source the census uses, so a probe can never
    reach a write. A `*` declaration names no verb to run and is reported as
    unprobeable rather than guessed at.
    """
    import json as _json
    from quantities import _read_only_verb, QuantityError

    tools = registry.get("tools") or {}
    results: list[dict[str, Any]] = []
    for name, info in sorted(tools.items()):
        if not isinstance(info, dict) or (only_tool and name != only_tool):
            continue
        for verb, declaration in sorted(get_tool_bounds(info).items()):
            if verb == TOOL_WIDE_KEY:
                results.append({"tool": name, "verb": verb, "outcome": "skip",
                                "reason": "tool-wide declaration names no single verb to probe"})
                continue
            try:
                _read_only_verb(name, verb.split())
            except QuantityError as exc:
                results.append({"tool": name, "verb": verb, "outcome": "skip",
                                "reason": str(exc).splitlines()[0]})
                continue
            completed = runner(name, *verb.split(), "--json")
            stdout = getattr(completed, "stdout", "") or ""
            if getattr(completed, "returncode", 1) != 0:
                results.append({"tool": name, "verb": verb, "outcome": "skip",
                                "reason": f"probe exited {completed.returncode}; nothing to grade"})
                continue
            try:
                payload = _json.loads(stdout)
            except _json.JSONDecodeError:
                verdict = audit_text(stdout)
            else:
                verdict = audit_payload(payload)
            results.append({"tool": name, "verb": verb, "source": declaration.get("source"),
                            **verdict})
    summary = {outcome: sum(1 for item in results if item["outcome"] == outcome)
               for outcome in ("ok", "fail", "skip")}
    return {"ok": summary["fail"] == 0, "summary": summary, "results": results}


# ── the outward scan ──────────────────────────────────────────────────────

_MODEL_IN_TEXT = re.compile(r"\b(claude-[a-z0-9][a-z0-9.\-]*|gpt-[0-9][a-z0-9.\-]*)", re.I)
_PROVIDER_OF = (("claude", "anthropic"), ("gpt", "openai"))


def annotate_ceiling(finding: dict[str, Any], file_text: str,
                     values: dict[str, Any]) -> dict[str, Any]:
    """Attach the published ceiling for this literal, or name the one that is missing.

    A model the file names but the authority has no record for is reported as
    exactly that. It is the honest half of the same refusal `quantity lookup`
    makes: no record means no number, and the next line of code must not be a
    literal standing in for one.
    """
    if finding["unit"] != "tokens":
        return finding
    models = []
    for match in _MODEL_IN_TEXT.finditer(file_text):
        name = match.group(1).rstrip(".,;:'\"")
        if name not in models:
            models.append(name)
    if not models:
        return finding
    parameter = "max_tokens" if finding["parameter"] in ("max_tokens", "maxtokens") else finding["parameter"]
    for model in models:
        provider = next((p for token, p in _PROVIDER_OF if model.lower().startswith(token)), None)
        if not provider:
            continue
        key = f"{provider}.{model}.{parameter}"
        if key in values:
            finding["ceiling"] = {"key": key, "value": values[key],
                                  "ratio": finding["value"] / values[key]}
        else:
            finding.setdefault("ceiling_owed", []).append(key)
    return finding


def scan_project(root: Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Report bare bounding literals in someone else's project. Never rewrites."""
    from quantities import authority_entries

    root = Path(root).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"no such path: {root}")
    values = {entry["key"]: entry["value"] for entry in authority_entries(config)}
    findings: list[dict[str, Any]] = []
    files_scanned = 0
    targets = [root] if root.is_file() else [
        path for path in sorted(root.rglob("*"))
        if path.is_file()
        and not any(part in _SCAN_SKIP_DIRS for part in path.parts)
        and (not path.suffix or path.suffix in _SCAN_SUFFIXES)
    ]
    for path in targets:
        try:
            if path.stat().st_size > _MAX_SCAN_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not path.suffix and not _looks_like_script(text):
            continue
        files_scanned += 1
        label = path.name if root.is_file() else str(path.relative_to(root))
        for finding in scan_text(label, text, require_family=True):
            if finding["site_kind"] != "code":
                continue
            findings.append(annotate_ceiling(finding, text, values))
    by_family: dict[str, int] = {}
    for finding in findings:
        for family in finding["families"]:
            by_family[family] = by_family.get(family, 0) + 1
    return {
        "root": str(root),
        "files_scanned": files_scanned,
        "total": len(findings),
        "with_ceiling": sum(1 for item in findings if "ceiling" in item),
        "ceilings_owed": sorted({key for item in findings for key in item.get("ceiling_owed", [])}),
        "by_family": dict(sorted(by_family.items())),
        "findings": findings,
    }
