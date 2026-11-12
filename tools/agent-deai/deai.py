"""Measured prose rules and register policy, with no network or input writes."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
REGISTERS = ("essay", "email", "default", "product-answer")
WORD_RE = re.compile(r"[A-Za-z']+")
PREPROCESSING = "deai-prose-v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def validate_data(catalog, packs):
    """Every ceiling resolves to a measured value, denominator, and pattern."""
    require(isinstance(catalog, dict) and isinstance(packs, dict), "rule data must be objects")
    require(catalog.get("schema") == "deai-rules-v1", "unsupported rule schema")
    require(catalog["rate_basis_words"] == 10_000, "rates must be per 10,000 words")
    require(number(catalog["test"]["alpha"]) and 0 < catalog["test"]["alpha"] < 1
            and catalog["test"]["source"], "missing test policy provenance")
    rules = catalog["rules"]
    by_id = {r["id"]: r for r in rules}
    require(len(rules) == len(by_id) and bool(rules), "duplicate or empty rule inventory")
    for rule in rules:
        require(re.fullmatch(r"[a-z][a-z0-9-]*", rule["id"]), "invalid rule id")
        require(rule["tier"] in (1, 2, 3) and rule["label"] and rule["evidence"],
                f"{rule['id']}: missing tier, label, or evidence")
        regex = re.compile(rule["pattern"], re.I)
        require(not regex.search(""), f"{rule['id']}: empty-match pattern")
    rate_ids = {r["id"] for r in rules if r["tier"] != 1}
    require(set(packs) == set(REGISTERS), "register pack inventory is incomplete")
    for name, pack in packs.items():
        require(isinstance(pack, dict), f"{name}: pack must be an object")
        require(pack.get("schema") == "deai-pack-v1" and pack["register"] == name,
                f"{name}: invalid pack identity")
        require(isinstance(pack["provenance"], dict), f"{name}: missing pack provenance")
        require(all(pack["provenance"].get(k) for k in ("source", "calibration", "policy")),
                f"{name}: missing pack provenance")
        require(set(pack["ceilings"]) == rate_ids, f"{name}: missing or unknown rule ceilings")
        for rule_id, ceiling in pack["ceilings"].items():
            require(isinstance(ceiling, dict), f"{name}/{rule_id}: bare ceiling has no measurement")
            rate = ceiling["per_10k"]
            require(number(rate), f"{name}/{rule_id}: invalid ceiling")
            measurement = catalog["measurements"][ceiling["measurement"]]
            require(measurement["kind"] in ("reported", "computed"), "unknown measurement kind")
            require(type(measurement["words"]) is int and measurement["words"] > 0,
                    f"{rule_id}: missing measured denominator")
            require(measurement["source"] and measurement["method"] and
                    re.fullmatch(r"\d{4}-\d{2}-\d{2}", measurement["measured_on"]),
                    f"{rule_id}: missing measurement provenance")
            require(rate == measurement["ceilings"][rule_id],
                    f"{rule_id}: ceiling differs from measurement")
            require(by_id[rule_id]["pattern"] == measurement["patterns"][rule_id],
                    f"{rule_id}: pattern changed without measurement")
            if measurement["kind"] == "computed":
                require(measurement["preprocessing"] == PREPROCESSING,
                        f"{rule_id}: incompatible measurement preprocessing")
                files = measurement["files"]
                require(files and all(re.fullmatch(r"[a-f0-9]{64}", f["sha256"]) and
                                      type(f["words"]) is int and f["words"] >= 0 and
                                      type(f["count"]) is int and f["count"] >= 0 for f in files),
                        f"{rule_id}: missing measurement file receipts")
                require(sum(f["words"] for f in files) == measurement["words"] and
                        sum(f["count"] for f in files) == measurement["counts"][rule_id],
                        f"{rule_id}: measurement totals disagree")
                expected = measurement["counts"][rule_id] * catalog["rate_basis_words"] / measurement["words"]
                require(rate == expected, f"{rule_id}: measured rate disagrees with counts")
        allowed = set()
        for entry in pack["whitelist"]:
            require(entry["source"] and entry["reason"] and entry["rules"],
                    f"{name}: whitelist needs provenance and reason")
            ids = set(entry["rules"])
            require(ids <= by_id.keys() and not ids & allowed and len(ids) == len(entry["rules"]),
                    f"{name}: unknown or repeated whitelist rule")
            allowed.update(ids)


def load(root=HERE):
    catalog = json.loads((root / "rules.json").read_text(encoding="utf-8"))
    packs = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (root / "packs").glob("*.json")}
    validate_data(catalog, packs)
    return catalog, packs


def mask_nonprose(raw):
    """Keep offsets/newlines; NUL spans cannot contribute words or matches."""
    text = raw.replace("\u2019", "'").replace("\u2018", "'").replace("\r", " ")

    def mask(match):
        return re.sub(r"[^\n]", "\0", match.group(0))

    text = re.sub(r"\A---[^\S\n]*\n.*?\n(?:---|\.\.\.)[^\S\n]*(?:\n|$)", mask, text, flags=re.S)
    lines = text.splitlines(keepends=True)
    fence = None
    for i, line in enumerate(lines):
        if fence:
            closing = re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}[ \t]*\n?", line)
            lines[i] = re.sub(r"[^\n]", "\0", line)
            if closing:
                fence = None
        else:
            opening = re.match(r" {0,3}(`{3,}|~{3,})([^\n]*)", line)
            if opening and not (opening[1][0] == "`" and "`" in opening[2]):
                fence = (opening[1][0], len(opening[1]))
                lines[i] = re.sub(r"[^\n]", "\0", line)
    text = "".join(lines)
    for pattern in (r"<!--.*?(?:-->|\Z)", r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)", r"https?://[^\s\x00]+",
                    r"\[(?:subscribe|share|comment)\]"):
        text = re.sub(pattern, mask, text, flags=re.S)
    return text


def matches(pattern, text):
    hits = list(re.finditer(pattern, text, re.I))
    require(all(m.end() > m.start() for m in hits), "rule patterns must consume text")
    return [m for m in hits if "\0" not in m[0]]


def poisson_tail(k, lam):
    """P(X >= k), summing from the boundary to avoid underflow at large lambda."""
    if k <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    index = k if k > lam else k - 1
    term = math.exp(-lam + index * math.log(lam) - math.lgamma(index + 1))
    total = term
    if k > lam:
        while term > total * sys.float_info.epsilon:
            index += 1
            term *= lam / index
            total += term
        return min(1.0, total)
    while index > 0 and term > total * sys.float_info.epsilon:
        term *= index / lam
        index -= 1
        total += term
    return max(0.0, min(1.0, 1.0 - total))


def lint_text(raw, catalog, pack):
    text = mask_nonprose(raw)
    words = len(WORD_RE.findall(text))
    line_starts = [0] + [m.end() for m in re.finditer("\n", raw)]
    allowed = {rule_id for entry in pack["whitelist"] for rule_id in entry["rules"]}
    findings = []
    for rule in catalog["rules"]:
        if rule["id"] in allowed:
            continue
        hits = matches(rule["pattern"], text)
        if not hits:
            continue
        finding = {"rule": rule["id"], "tier": rule["tier"], "label": rule["label"],
                   "count": len(hits), "evidence": rule["evidence"]}
        if rule["tier"] != 1:
            ceiling = pack["ceilings"][rule["id"]]
            measurement = catalog["measurements"][ceiling["measurement"]]
            effective = max(ceiling["per_10k"], catalog["rate_basis_words"] / measurement["words"])
            p = poisson_tail(len(hits), effective * words / catalog["rate_basis_words"])
            if p >= catalog["test"]["alpha"]:
                continue
            finding.update(ceiling=ceiling, effective_ceiling_per_10k=effective,
                           baseline_words=measurement["words"], p_value=p,
                           rate_per_10k=len(hits) * catalog["rate_basis_words"] / max(words, 1))
        finding["occurrences"] = []
        for hit in hits:
            line = bisect_right(line_starts, hit.start())
            finding["occurrences"].append({"line": line, "column": hit.start() - line_starts[line - 1] + 1,
                                           "text": raw[hit.start():hit.end()]})
        findings.append(finding)
    return {"words": words, "clean": not findings, "findings": findings}


def read_inputs(paths):
    require(paths.count("-") <= 1, "stdin may be read only once")
    # Decode raw bytes so the receipt is the file's hash, including CRLFs.
    return [(name, sys.stdin.read() if name == "-" else Path(name).read_bytes().decode("utf-8")) for name in paths]


def measure(inputs, rule_id, pattern, source, catalog):
    require(re.fullmatch(r"[a-z][a-z0-9-]*", rule_id), "invalid rule id")
    require(source.strip(), "measurement source must be explicit")
    require(not re.compile(pattern, re.I).search(""), "empty-match pattern")
    files = []
    for name, raw in inputs:
        text = mask_nonprose(raw)
        files.append({"path": name, "sha256": hashlib.sha256(raw.encode()).hexdigest(),
                      "words": len(WORD_RE.findall(text)), "count": len(matches(pattern, text))})
    require(len({f["sha256"] for f in files}) == len(files), "duplicate corpus content would inflate the denominator")
    words = sum(f["words"] for f in files)
    count = sum(f["count"] for f in files)
    require(words > 0, "measurement requires a nonempty prose corpus")
    return {"kind": "computed", "measured_on": datetime.now(timezone.utc).date().isoformat(),
            "source": source, "method": "Exact matches / prose words; caller attests corpus provenance.",
            "preprocessing": PREPROCESSING, "words": words, "counts": {rule_id: count},
            "patterns": {rule_id: pattern}, "ceilings": {rule_id: count * catalog["rate_basis_words"] / words},
            "files": files}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = Parser(prog="agent-deai", description="Offline prose-tell lint with measured register packs.",
                    epilog="Exit: 0 clean/success; 1 prose findings; 2 input or rule-data error. "
                           "Guard check always exits 0 (advisory). Never rewrites prose input.")
    sub = parser.add_subparsers(dest="command", required=True)
    lint = sub.add_parser("lint", help="Lint files (or - for stdin); default register permits technical language")
    lint.add_argument("paths", nargs="+")
    lint.add_argument("--register", choices=REGISTERS, default="default")
    packs_parser = sub.add_parser("packs", help="Show rules, ceilings, whitelists, and provenance")
    packs_parser.add_argument("--register", choices=REGISTERS)
    validation = sub.add_parser("validate", help="Validate all rule measurements and register packs")
    measurement = sub.add_parser("measure", help="Measure a proposed rule on an explicitly sourced local corpus")
    measurement.add_argument("paths", nargs="+")
    measurement.add_argument("--rule-id", required=True)
    measurement.add_argument("--pattern", required=True)
    measurement.add_argument("--source", required=True)
    guard_parser = sub.add_parser("guard", help="Warn on staged prose or install the advisory Git pre-commit hook")
    guard_sub = guard_parser.add_subparsers(dest="guard_command", required=True)
    for verb in ("check", "install"):
        child = guard_sub.add_parser(verb, help="Check staged prose" if verb == "check" else "Install the advisory hook")
        child.add_argument("--register", choices=REGISTERS, default="default")
        child.add_argument("--json", action="store_true")
    for child in (lint, packs_parser, validation, measurement):
        child.add_argument("--json", action="store_true", help="Emit the complete machine-readable result")
    try:
        args = parser.parse_args(argv)
        if args.command == "guard":
            from guard import run
            return run(args)
        catalog, packs = load()
        code = 0
        payload = {"schema": "deai-result-v1", "tool": "deai", "command": args.command, "success": True}
        if args.command == "lint":
            results = [{"path": name, **lint_text(raw, catalog, packs[args.register])}
                       for name, raw in read_inputs(args.paths)]
            clean = all(result["clean"] for result in results)
            payload.update(register=args.register, provenance=packs[args.register]["provenance"],
                           clean=clean, files=results, total_files=len(results),
                           total_findings=sum(len(r["findings"]) for r in results))
            code = 0 if clean else 1
        elif args.command == "packs":
            selected = {args.register: packs[args.register]} if args.register else packs
            payload.update(packs=selected, rules=catalog["rules"], measurements=catalog["measurements"],
                           test=catalog["test"], provenance=catalog["provenance"], total_packs=len(selected))
        elif args.command == "validate":
            payload.update(total_rules=len(catalog["rules"]), total_packs=len(packs))
        else:
            payload["measurement"] = measure(read_inputs(args.paths), args.rule_id, args.pattern, args.source, catalog)
        if args.json or args.command in ("packs", "measure"):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        elif args.command == "validate":
            print(f"deai: {len(catalog['rules'])} rules, {len(packs)} packs; measurements and policy valid")
        else:
            for result in payload["files"]:
                print(f"== {result['path']} ({result['words']} words; {args.register}) ==")
                if result["clean"]:
                    print("  clean: no prose-tell flags")
                for finding in result["findings"]:
                    for hit in finding["occurrences"]:
                        print(f"  TIER{finding['tier']} line {hit['line']}:{hit['column']}: {hit['text']!r} [{finding['rule']}]")
        return code
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, re.error) as exc:
        if "--json" in argv:
            print(json.dumps({"schema": "deai-result-v1", "tool": "deai", "success": False, "error": str(exc)}))
        else:
            print(f"deai: {exc}", file=sys.stderr)
        return 2
