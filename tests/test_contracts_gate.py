#!/usr/bin/env python3
"""Contracts gate: schema validation, verb attributes, baseline ratchet, CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from registry import (  # noqa: E402
    CONTRACT_ATTRIBUTES,
    CONTRACT_BEATS,
    get_tool_contract_attributes,
    get_tool_contracts,
    validate_registry_contracts,
    validate_tool_contracts,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_agent_do(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("AGENT_DO_HOME", str(ROOT / ".dev" / "test-home"))
    return subprocess.run(
        [str(ROOT / "agent-do"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def warning_codes(result: dict) -> list[str]:
    return [item["code"] for item in result["warnings"]]


def error_codes(result: dict) -> list[str]:
    return [item["code"] for item in result["errors"]]


def check_attribute_schema() -> None:
    """Verb attributes: vocabulary, command existence, multi-beat suppression."""
    info = {
        "commands": {"query": "...", "delete": "...", "shell": "...", "list": "..."},
        "contracts": {
            "snapshot": ["list", "query"],
            "interact": ["query", "delete"],
            "attributes": {
                "query": ["polymorphic"],
                "delete": ["destructive"],
                "shell": ["passthrough"],
            },
        },
    }
    result = validate_tool_contracts("demo", info)
    require(result["ok"], f"attributed contracts should validate: {result}")
    require(
        "multi_beat_verb" not in warning_codes(result),
        f"polymorphic verb must not warn on multi-beat: {result['warnings']}",
    )
    attrs = get_tool_contract_attributes(info)
    require(attrs["query"] == ["polymorphic"], f"attributes accessor broken: {attrs}")
    beats = get_tool_contracts(info)
    require("attributes" not in beats, f"attributes must not leak into beats: {beats}")

    unattributed = {
        "commands": {"query": "..."},
        "contracts": {"snapshot": ["query"], "interact": ["query"]},
    }
    result = validate_tool_contracts("demo", unattributed)
    require(
        "multi_beat_verb" in warning_codes(result),
        f"unattributed multi-beat verb must still warn: {result}",
    )

    bad_vocab = {
        "commands": {"x": "..."},
        "contracts": {"interact": ["x"], "attributes": {"x": ["explosive"]}},
    }
    result = validate_tool_contracts("demo", bad_vocab)
    require("unknown_attribute" in error_codes(result), f"unknown attribute must error: {result}")

    ghost_verb = {
        "commands": {"x": "..."},
        "contracts": {"interact": ["x"], "attributes": {"ghost": ["destructive"]}},
    }
    result = validate_tool_contracts("demo", ghost_verb)
    require(
        "unknown_command" in error_codes(result),
        f"attribute on undeclared command must error: {result}",
    )

    beatless_passthrough = {
        "commands": {"shell": "...", "x": "..."},
        "contracts": {"interact": ["x"], "attributes": {"shell": ["passthrough"]}},
    }
    result = validate_tool_contracts("demo", beatless_passthrough)
    require(result["ok"], f"beat-less passthrough verb is legal: {result}")
    require(
        "attribute_without_beat" not in warning_codes(result),
        f"passthrough needs no beat: {result['warnings']}",
    )

    beatless_destructive = {
        "commands": {"nuke": "...", "x": "..."},
        "contracts": {"interact": ["x"], "attributes": {"nuke": ["destructive"]}},
    }
    result = validate_tool_contracts("demo", beatless_destructive)
    require(
        "attribute_without_beat" in warning_codes(result),
        f"destructive without a beat should warn: {result}",
    )

    require(
        set(CONTRACT_ATTRIBUTES)
        == {"destructive", "long_running", "polymorphic", "composite",
            "sensitive", "passthrough", "own_state"},
        f"unexpected attribute vocabulary: {CONTRACT_ATTRIBUTES}",
    )
    require(
        CONTRACT_BEATS == ("connect", "snapshot", "interact", "verify", "save"),
        f"beats changed unexpectedly: {CONTRACT_BEATS}",
    )


def check_registry_gate() -> None:
    """Real registry: zero shape errors; baseline ratchet holds exactly."""
    registry = yaml.safe_load((ROOT / "registry.yaml").read_text(encoding="utf-8"))
    report = validate_registry_contracts(registry)
    require(report["errors"] == 0, f"contract shape errors in registry.yaml: {report['errors']}")
    require(report["ok"], "registry contract validation must pass")

    tools = registry["tools"]
    undeclared = {
        name
        for name, info in tools.items()
        if isinstance(info, dict) and not isinstance(info.get("contracts"), dict)
    }

    baseline_path = ROOT / "lib" / "contracts-baseline.yaml"
    if baseline_path.exists():
        baseline_doc = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
        baseline = set(baseline_doc["grandfathered"])
        new_without_contracts = sorted(undeclared - baseline)
        require(
            not new_without_contracts,
            "tools without contracts that are not grandfathered "
            f"(new tools MUST declare contracts): {new_without_contracts}",
        )
        stale_baseline = sorted(baseline - undeclared)
        require(
            not stale_baseline,
            "baseline entries that now declare contracts or no longer exist "
            f"(remove them — the ratchet only tightens): {stale_baseline}",
        )
    else:
        # Strict era: the baseline emptied on 2026-06-11 and was deleted.
        # Every registry tool declares contracts; there is no grandfather list.
        require(
            not undeclared,
            f"every registry tool must declare contracts: {sorted(undeclared)}",
        )
        require(report["warnings"] == 0, f"contract warnings must stay zero: {report['warnings']}")


def check_cli_gate() -> None:
    """agent-do harness contracts validate honors the baseline and --strict."""
    result = run_agent_do("harness", "contracts", "validate", "--json")
    require(result.returncode == 0, f"contracts validate should pass: {result.stdout}{result.stderr}")
    payload = json.loads(result.stdout)
    require(payload["ok"] is True, f"expected ok payload: {payload}")
    require(payload["errors"] == 0, f"expected zero errors: {payload}")
    require("missing" in payload and "declared" in payload, f"coverage fields missing: {payload}")

    strict = run_agent_do("harness", "contracts", "validate", "--strict", "--json")
    strict_payload = json.loads(strict.stdout)
    if payload["missing"] > 0:
        require(
            strict.returncode != 0 and strict_payload["ok"] is False,
            f"--strict must fail while tools lack contracts: {strict_payload}",
        )
    else:
        require(strict.returncode == 0, f"--strict should pass at full coverage: {strict_payload}")


def check_cli_propose() -> None:
    """agent-do harness contracts propose emits proposals + exceptions."""
    result = run_agent_do("harness", "contracts", "propose", "--json")
    require(result.returncode == 0, f"contracts propose failed: {result.stdout}{result.stderr}")
    payload = json.loads(result.stdout)
    require(payload["ok"] is True, f"expected ok payload: {payload}")
    require("proposals" in payload and "exceptions" in payload, f"missing keys: {list(payload)}")
    proposals = payload["proposals"]
    require(len(proposals) >= 90, f"expected near-registry-wide proposals: {len(proposals)}")
    declared = [p for p in proposals.values() if p["source"] == "declared"]
    require(len(declared) >= 3, f"existing blocks must be preserved verbatim: {len(declared)}")
    api = proposals.get("api")
    require(api is not None and api["source"] == "declared", f"api block must be preserved: {api}")
    require(
        api["contracts"].get("save") == ["save"],
        f"api existing contracts must survive propose untouched: {api}",
    )


class _DupKeyLoader(yaml.SafeLoader):
    pass


def _no_dup_construct(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict:
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in mapping:
            raise AssertionError(
                f"duplicate YAML key {key!r} at line {key_node.start_mark.line + 1} "
                "— PyYAML silently keeps only the last, losing data"
            )
        mapping[key] = loader.construct_object(value_node)
    return mapping


_DupKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dup_construct
)


def check_no_duplicate_keys() -> None:
    """Lexicon files must not contain duplicate mapping keys."""
    for name in ("contracts-lexicon.yaml", "contracts-lexicon-learned.yaml"):
        path = ROOT / "lib" / name
        if path.exists():
            # _DupKeyLoader extends SafeLoader: safe_load semantics + dup detection.
            yaml.load(path.read_text(encoding="utf-8"), Loader=_DupKeyLoader)


def check_concurrency_alignment() -> None:
    """Tool-level concurrency must agree with the declared write surface."""
    read_with_write = {
        "commands": {"list": "...", "set": "..."},
        "concurrency": "read",
        "contracts": {"snapshot": ["list"], "interact": ["set"]},
    }
    result = validate_tool_contracts("demo", read_with_write)
    require(
        "concurrency_mismatch" in error_codes(result),
        f"read tool with interact verb must error: {result}",
    )

    read_with_own_state = {
        "commands": {"list": "...", "save": "..."},
        "concurrency": "read",
        "contracts": {
            "snapshot": ["list"],
            "save": ["save"],
            "attributes": {"save": ["own_state"]},
        },
    }
    result = validate_tool_contracts("demo", read_with_own_state)
    require(
        result["ok"] and "concurrency_mismatch" not in error_codes(result),
        f"own_state writes must not force mixed: {result}",
    )

    write_without_writes = {
        "commands": {"list": "..."},
        "concurrency": "write",
        "contracts": {"snapshot": ["list"]},
    }
    result = validate_tool_contracts("demo", write_without_writes)
    require(
        "concurrency_overdeclared" in warning_codes(result),
        f"write tool with zero write verbs should warn: {result}",
    )

    mixed_all_read = {
        "commands": {"list": "..."},
        "concurrency": "mixed",
        "contracts": {"snapshot": ["list"]},
    }
    result = validate_tool_contracts("demo", mixed_all_read)
    require(
        "concurrency_overdeclared" in warning_codes(result),
        f"mixed tool with all-read verbs should warn: {result}",
    )

    mixed_proper = {
        "commands": {"list": "...", "set": "..."},
        "concurrency": "mixed",
        "contracts": {"snapshot": ["list"], "interact": ["set"]},
    }
    result = validate_tool_contracts("demo", mixed_proper)
    require(
        "concurrency_overdeclared" not in warning_codes(result)
        and "concurrency_mismatch" not in error_codes(result),
        f"honest mixed tool must pass clean: {result}",
    )


def check_cli_surface() -> None:
    """harness contracts surface emits machine-readable safety buckets."""
    result = run_agent_do("harness", "contracts", "surface", "--json")
    require(result.returncode == 0, f"surface failed: {result.stdout}{result.stderr}")
    payload = json.loads(result.stdout)
    for key in (
        "read_only", "write", "destructive", "sensitive",
        "long_running", "passthrough", "polymorphic", "composite", "own_state",
    ):
        require(key in payload, f"surface missing bucket {key}: {list(payload)}")
    require(
        {"tool": "manna", "verb": "delete"} in payload["destructive"],
        f"known destructive verb missing: {payload['destructive'][:5]}",
    )
    require(
        {"tool": "brief", "verb": "holy"} in payload["own_state"],
        f"known own_state verb missing: {payload['own_state'][:5]}",
    )
    require(len(payload["read_only"]) > 400, "read surface implausibly small")
    require(len(payload["write"]) > 300, "write surface implausibly small")


def check_registry_context_safety() -> None:
    """The LLM catalog carries compact per-tool safety markers, token-capped."""
    from registry import build_registry_context, load_registry

    catalog = build_registry_context(load_registry())
    require("destructive=[" in catalog, "catalog missing destructive markers")
    require("sensitive=[" in catalog, "catalog missing sensitive markers")
    require("Safety: read-only" in catalog, "read-only tools should say so")
    require(
        len(catalog) < 42_000,
        f"catalog grew past budget: {len(catalog)} chars "
        f"(was ~29.6k pre-safety; the bundled catalog was 40,133 at 103 tools "
        f"when agent-appstore landed against a 40k guard — trim entries "
        f"before raising again)",
    )


def check_lexicon_merge(tmp_dir: Path) -> None:
    """Learned classifications merge under the hand lexicon; hand overrides win."""
    from contracts import classify_verb, load_lexicon

    base = tmp_dir / "lexicon.yaml"
    learned = tmp_dir / "learned.yaml"
    base.write_text(
        yaml.safe_dump(
            {
                "exact": {},
                "patterns": [],
                "overrides": {"demo": {"query": {"beats": ["snapshot"]}}},
            }
        ),
        encoding="utf-8",
    )
    learned.write_text(
        yaml.safe_dump(
            {
                "overrides": {
                    "demo": {
                        "query": {"beats": ["interact"], "confidence": "high"},
                        "flush": {"beats": ["interact"], "attributes": ["destructive"]},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    lexicon = load_lexicon(base, learned)
    hand = classify_verb("demo", "query", lexicon)
    require(
        hand is not None and hand["beats"] == ["snapshot"],
        f"hand-written override must beat learned: {hand}",
    )
    machine = classify_verb("demo", "flush", lexicon)
    require(
        machine is not None and machine.get("attributes") == ["destructive"],
        f"learned-only verb must classify: {machine}",
    )


def main() -> int:
    import tempfile

    check_no_duplicate_keys()
    check_attribute_schema()
    check_concurrency_alignment()
    check_registry_gate()
    check_cli_gate()
    check_cli_propose()
    check_cli_surface()
    check_registry_context_safety()
    with tempfile.TemporaryDirectory() as tmp:
        check_lexicon_merge(Path(tmp))
    print("contracts gate tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
