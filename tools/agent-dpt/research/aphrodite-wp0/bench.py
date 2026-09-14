#!/usr/bin/env python3
"""Freeze and evaluate an owned research bundle. Never modify historic evidence."""
import argparse
import datetime
import hashlib
import json
import shutil
from pathlib import Path
from statistics import median

from model import bind, score

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DEFAULT = ROOT / ".dev/aphrodite-wp0"
HISTORY = ROOT / "tools/agent-dpt/research/wildhunt-verify"
COLUMNS = ["F01", "F02", "F03", "F08", "B", "additive"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def freeze(out):
    manifest_path = out / "FREEZE.json"
    if manifest_path.exists():
        raise ValueError("Freeze exists; verify it instead of overwriting an experiment")
    corpus = read(HISTORY / "corpus-measured.json")
    historic = read(HISTORY / "scores.json")
    model = read(HERE / "model.json")
    pairs = corpus["primary_pairs"]
    traps = [{"surface": x["surface"], "null_id": x["null_id"], "members": sorted(x["values"])}
             for x in historic["gates"]["18_trees"]["C"]["surfaces"]]
    fixtures = ["fixtures/" + x for x in ("canon-today", "canon-dossier", "barf", "broken")]
    primary = sorted({x[k] for x in pairs for k in ("winner", "rejected")} | set(fixtures) | {i for t in traps for i in t["members"]})
    sources = {}
    owned = {}
    for name in ("model.json", "model.py", "bench.py", "capture.py", "render.py", "probe.js", "PROTOCOL.md", "comparison.json"):
        target = out / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HERE / name, target)
        owned[str(target.relative_to(out))] = sha(target)
        sources[str((HERE / name).relative_to(ROOT))] = sha(HERE / name)
    for name in ("scores.json", "corpus-measured.json", "PROTOCOL.md", "probe.js"):
        sources[str((HISTORY / name).relative_to(ROOT))] = sha(HISTORY / name)
    for path in sorted((ROOT / "tools/agent-dpt/corpus/pins").glob("*.md")):
        sources[str(path.relative_to(ROOT))] = sha(path)
    for relative in (".handoff/aphrodite-plan/REVIEW-2026-09-14.md", "tools/agent-dpt/corpus/README.md"):
        sources[relative] = sha(ROOT / relative)
    specimens = []
    for row in sorted(corpus["specimens"], key=lambda r: r["id"]):
        if not row.get("probe") or row.get("exclude_reason"):
            continue
        original = ROOT / row["probe"]
        if sha(original) != row["probe_sha256"]:
            raise ValueError(f"Historic manifest mismatch: {row['id']}")
        relative = "inputs/" + row["id"] + ".json"
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        sources[row["probe"]] = sha(original)
        owned[relative] = sha(target)
        for variant in ("local_then_following", "local_only"):
            graph_path = out / "graphs" / variant / (row["id"] + ".json")
            write(graph_path, bind(read(target), model, variant))
            owned[str(graph_path.relative_to(out))] = sha(graph_path)
        specimens.append({"id": row["id"], "input": relative, "original_probe": row["probe"],
                          "probe_sha256": sha(target), "label": row.get("label"),
                          "quote": row.get("quote"), "quote_source": row.get("source"),
                          "html_provenance": row.get("html_provenance"), "html": row.get("html"),
                          "historical_image": row.get("image")})
    ids = {r["id"] for r in specimens}
    if not set(primary).issubset(ids):
        raise ValueError("Primary observations missing")
    labels_path = out / "labels.json"
    write(labels_path, {"pairs": pairs, "traps": traps, "fixtures": fixtures, "primary": primary,
                       "historical_comparator": "Original scores.json is hashed in FREEZE.json; no historical score is rewritten or treated as a commensurable effect size."})
    owned["labels.json"] = sha(labels_path)
    write(manifest_path, {"model": model["id"], "frozen_at": stamp(), "source_files": sources,
                          "frozen_files": owned, "specimens": specimens,
                          "counts": {"observations": len(ids), "pairs": len(pairs), "paired_unique": len({p[k] for p in pairs for k in ("winner", "rejected")}), "primary_union": len(primary)}})
    return read(manifest_path)["counts"]


def verify(out, check_originals=True):
    manifest = read(out / "FREEZE.json")
    for name, expected in manifest["frozen_files"].items():
        if sha(out / name) != expected:
            raise ValueError("Frozen input changed: " + name)
    if check_originals:
        for name, expected in manifest["source_files"].items():
            if sha(ROOT / name) != expected:
                raise ValueError("Source changed after freeze: " + name)
    return manifest


def sign(value):
    return (value > 0) - (value < 0)


def diagnostics(rows, labels):
    report = {"fixtures": {}, "pairs": {}, "traps": {}}
    for field in COLUMNS:
        values = {i: rows[i][field] for i in labels["fixtures"]}
        margin = min(list(values.values())[:2]) - max(list(values.values())[2:]) if all(v is not None for v in values.values()) else None
        report["fixtures"][field] = {"values": values, "margin": margin}
        pairs = []
        for pair in labels["pairs"]:
            a, b = rows[pair["winner"]][field], rows[pair["rejected"]][field]
            gap = a-b if a is not None and b is not None else None
            pairs.append({**pair, "gap": gap, "win": gap > 0 if gap is not None else None})
        groups = sorted({p["round"] for p in pairs})
        report["pairs"][field] = {"rows": pairs, "wins": sum(p["win"] is True for p in pairs),
                                  "evaluable": sum(p["gap"] is not None for p in pairs), "denominator": len(pairs),
                                  "unconditional_wins": sum(p["win"] is True for p in pairs if not p["conditional"]),
                                  "unconditional_denominator": sum(not p["conditional"] for p in pairs),
                                  "groups": {g: {"wins": sum(p["win"] is True for p in pairs if p["round"] == g), "pairs": sum(p["round"] == g for p in pairs)} for g in groups}}
        report["traps"][field] = []
        for trap in labels["traps"]:
            vals = {i: rows[i][field] for i in trap["members"]}
            others = [v for i, v in vals.items() if i != trap["null_id"]]
            middle = median(others) if all(v is not None for v in others) else None
            null = vals[trap["null_id"]]
            report["traps"][field].append({**trap, "values": vals, "median": middle,
                                            "gap": null-middle if null is not None and middle is not None else None})
    changes = []
    for p, a in zip(report["pairs"]["B"]["rows"], report["pairs"]["additive"]["rows"]):
        changes.append({"winner": p["winner"], "rejected": p["rejected"],
                        "changed": sign(p["gap"]) != sign(a["gap"]) if p["gap"] is not None and a["gap"] is not None else None})
    report["product_ablation"] = {"rows": changes, "changed": sum(r["changed"] is True for r in changes), "evaluable": sum(r["changed"] is not None for r in changes), "denominator": len(changes)}
    missing = [i for i in labels["primary"] if rows[i]["B"] is None]
    margin = report["fixtures"]["B"]["margin"]
    failures = []
    if missing:
        failures.append({"clause": "primary_coverage", "specimens": missing})
    if margin is None or margin <= 0:
        failures.append({"clause": "fixture_separation", "margin": margin})
    for trap in report["traps"]["B"]:
        if trap["gap"] is None or trap["gap"] < 0:
            failures.append({"clause": "null_trap", "surface": trap["surface"], "gap": trap["gap"]})
    report["decision"] = {"status": "CANDIDATE_FAILED" if failures else "HISTORICAL_DIAGNOSTICS_PASSED_ONLY", "failures": failures, "engine_authorized": False, "targets_changed": False}
    return report


def evaluate(out, check_originals=True):
    manifest = verify(out, check_originals)
    for name in ("model.py", "bench.py"):
        if sha(HERE / name) != sha(out / "source" / name):
            raise ValueError("Evaluator differs from frozen executable: " + name)
    model = read(out / "source/model.json")
    labels = read(out / "labels.json")
    all_scores = {}
    for variant in ("local_then_following", "local_only"):
        rows = {r["id"]: score(read(out / "graphs" / variant / (r["id"] + ".json")), model) for r in manifest["specimens"]}
        all_scores[variant] = rows
    report = diagnostics(all_scores["local_then_following"], labels)
    report["binding_sensitivity"] = diagnostics(all_scores["local_only"], labels)
    report["coverage"] = {v: {"computed": sum(r["B"] is not None for r in rows.values()), "observations": len(rows), "fallback_edges": sum(r["fallback_edges"] for r in rows.values())} for v, rows in all_scores.items()}
    report["manifest_sha256"] = sha(out / "FREEZE.json")
    report["counts"] = manifest["counts"]
    report["evaluated_at"] = stamp()
    # Raw values are deterministic; timestamps are separate observational metadata.
    write(out / "scores.json", all_scores)
    write(out / "diagnostics.json", report)
    return {"decision": report["decision"], "counts": report["counts"], "pairs": {k: report["pairs"][k]["wins"] for k in COLUMNS}, "fixture_margin": report["fixtures"]["B"]["margin"], "coverage": report["coverage"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["freeze", "verify", "evaluate"])
    parser.add_argument("--out", type=Path, default=DEFAULT)
    parser.add_argument("--frozen-only", action="store_true", help="Portable bundle: verify frozen files but do not require the original checkout")
    args = parser.parse_args()
    if args.command == "freeze":
        if args.frozen_only:
            parser.error("--frozen-only does not apply to freeze")
        result = freeze(args.out)
    else:
        result = {"verify": verify, "evaluate": evaluate}[args.command](args.out, not args.frozen_only)
    print(json.dumps(result if args.command != "verify" else {"verified": True, "counts": result["counts"]}, indent=2))


if __name__ == "__main__":
    main()
