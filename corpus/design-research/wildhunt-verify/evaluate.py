#!/usr/bin/env python3
"""Freeze inputs, execute the registered waves, and report every gate and pair."""
import argparse
import datetime
import hashlib
import itertools
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import PIL
import scipy
from PIL import Image
from scipy.stats import binomtest

from catalog import write_json
from recover import HERE, ROOT
import metrics as M


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(target):
    if target.exists() or (HERE / "scores.json").exists():
        raise RuntimeError("Existing freeze/results cannot be replaced")
    prereg = json.loads((HERE / "preregistration.json").read_text())
    for path, expected in prereg["files"].items():
        if digest(ROOT / path) != expected:
            raise RuntimeError("Preregistered/protected file changed: " + path)
    corpus = json.loads((HERE / "corpus-measured.json").read_text())
    files = set(HERE.glob("*.py")) | set(HERE.glob("*.js"))
    files.update(HERE / name for name in ["PROTOCOL.md", "config.json", "preregistration.json", "corpus-measured.json", "capture-receipts.json", "corpus.json", "gallery-corpus.json", "recovery.json"])
    files.update((ROOT / "corpus/design/rounds").glob("*/labels.yaml"))
    widths = []
    for row in corpus["specimens"]:
        for key in ["image", "html", "probe"]:
            if row.get(key):
                path = ROOT / row[key]
                if not path.exists():
                    raise RuntimeError("Declared input absent: " + row[key])
                files.add(path)
                if row.get(key + "_sha256") and digest(path) != row[key + "_sha256"]:
                    raise RuntimeError("Corpus hash mismatch: " + row[key])
        if row.get("image") and not row.get("exclude_reason"):
            widths.append(Image.open(ROOT / row["image"]).width)
    write_json(target, {"frozen_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "scores_exist": False,
                        "analysis_width": min(widths) // M.COLS, "width_authority": "minimum measured evaluation image width / preregistered grid columns",
                        "files": {str(p.relative_to(ROOT)): digest(p) for p in sorted(files)}})
    print("Frozen", len(files), "inputs/code files before candidate scoring")


def verify_freeze(freeze_file):
    frozen = json.loads(freeze_file.read_text())
    for path, expected in frozen["files"].items():
        if digest(ROOT / path) != expected:
            raise RuntimeError("Frozen file drift: " + path)
    prereg = json.loads((HERE / "preregistration.json").read_text())
    for path, expected in prereg["files"].items():
        if digest(ROOT / path) != expected:
            raise RuntimeError("Protected/preregistered file drift: " + path)
    return frozen


def sign_flip(rounds):
    values = [r["wins"] - r["pairs"] / 2 for r in rounds.values()]
    observed = sum(values)
    permutations = [sum(s * x for s, x in zip(signs, values)) for signs in itertools.product([-1, 1], repeat=len(values))]
    return sum(v >= observed - M.EPS for v in permutations) / len(permutations)


def holm(pvalues):
    ordered = sorted(pvalues, key=pvalues.get)
    adjusted, running = {}, 0
    for i, name in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - i) * pvalues[name]))
        adjusted[name] = running
    return adjusted


def gates(values, pairs, margin):
    def all_values(ids):
        return all(values.get(i) is not None and math.isfinite(values[i]) for i in ids)
    canon = ["fixtures/canon-today", "fixtures/canon-dossier"]
    bad = ["fixtures/barf", "fixtures/broken"]
    a = {"status": "INCOMPLETE", "margin": margin, "values": {i: values.get(i) for i in canon + bad}}
    if all_values(canon + bad):
        gap = min(values[i] for i in canon) - max(values[i] for i in bad)
        a.update(status="PASS" if gap + M.EPS >= margin else "FAIL", gap=gap)
    pair_rows, rounds = [], {}
    for pair in pairs:
        w, r = pair["winner"], pair["rejected"]
        delta = values[w] - values[r] if all_values([w, r]) else None
        success = delta > M.EPS if delta is not None else None
        pair_rows.append(dict(pair, gap=delta, success=success))
        if delta is not None:
            rr = rounds.setdefault(pair["round"], {"wins": 0, "pairs": 0})
            rr["pairs"] += 1
            rr["wins"] += int(success)
    measured = [r for r in pair_rows if r["success"] is not None]
    wins = sum(r["success"] for r in measured)
    complete = len(measured) == len(pairs)
    b = {"status": "PENDING_HOLM" if complete else "INCOMPLETE", "wins": wins, "measured_pairs": len(measured), "required_pairs": len(pairs), "pair_rows": pair_rows, "by_round": rounds}
    if measured:
        result = binomtest(wins, len(measured), M.CONFIG["null_success_probability"], alternative="greater")
        interval = result.proportion_ci(confidence_level=1 - M.CONFIG["alpha"], method="exact")
        b.update(accuracy=wins / len(measured), p_raw=float(result.pvalue), exact_one_sided_interval=[float(interval.low), float(interval.high)], round_sign_flip_p=sign_flip(rounds), rank_biserial=2 * wins / len(measured) - 1)
    unconditional = [r for r in measured if not r["conditional"]]
    b["nonconditional"] = {"wins": sum(r["success"] for r in unconditional), "pairs": len(unconditional)}
    traps = []
    for surface, null in [("library", "B"), ("engine", "C")]:
        names = ["concept2/" + surface + "-" + letter for letter in "ABCDE"]
        null_id = "concept2/" + surface + "-" + null
        trap = {"surface": surface, "status": "INCOMPLETE", "null_id": null_id, "values": {i: values.get(i) for i in names}}
        if all_values(names):
            median = float(np.median([values[i] for i in names if i != null_id]))
            trap.update(status="PASS" if values[null_id] + M.EPS >= median else "FAIL", null_score=values[null_id], heavy_median=median, gap=values[null_id] - median)
        traps.append(trap)
    c = {"status": "FAIL" if any(t["status"] == "FAIL" for t in traps) else ("PASS" if all(t["status"] == "PASS" for t in traps) else "INCOMPLETE"), "surfaces": traps}
    pins = ["pins/001", "pins/003", "pins/004", "pins/005"]
    d = {"status": "INCOMPLETE", "declared_pins": 5, "available_shots": len(pins), "measurable_pins": sum(values.get(i) is not None for i in pins), "values": {i: values.get(i) for i in pins}, "missing_shot": "pins/002", "margin": margin}
    if all_values(pins + bad):
        gaps = {i: values[i] - max(values[j] for j in bad) for i in pins}
        d.update(status="PASS" if min(gaps.values()) + M.EPS >= margin else "FAIL", gaps=gaps)
    return {"A": a, "B": b, "C": c, "D": d}


def adjudicate(corpus, scores):
    result = {}
    for name, config in M.CONFIG["metrics"].items():
        values = {key: row[name]["score"] for key, row in scores.items()}
        candidate = gates(values, corpus["primary_pairs"], config["margin"])
        if name in {"1_raster", "1_html"}:
            d1, b1 = values.get("eng6/D1"), values.get("eng5/B1")
            candidate["targeted_D1_B1"] = {"status": "INCOMPLETE" if d1 is None or b1 is None else ("PASS" if d1 > b1 + M.EPS else "FAIL"), "D1": d1, "B1": b1, "confound": "Different rounds and native capture extents; outside the primary pair pool"}
        result[name] = candidate
    adjusted = holm({name: row["B"].get("p_raw", 1) if row["B"]["status"] == "PENDING_HOLM" else 1 for name, row in result.items()})
    for name, row in result.items():
        row["B"]["p_holm"] = adjusted[name]
        if row["B"]["status"] == "PENDING_HOLM":
            row["B"]["status"] = "PASS" if adjusted[name] < M.CONFIG["alpha"] else "FAIL"
        statuses = [r["status"] for r in row.values() if isinstance(r, dict) and "status" in r]
        row["status"] = "KILLED" if "FAIL" in statuses else ("SURVIVED SCREENING" if all(s == "PASS" for s in statuses) else "INCOMPLETE")
    return result


def run(out, freeze_file):
    frozen = verify_freeze(freeze_file)
    if out.exists():
        raise RuntimeError("Refusing to replace an existing run: " + str(out))
    corpus = json.loads((HERE / "corpus-measured.json").read_text())
    eligible = [r for r in corpus["specimens"] if not r.get("exclude_reason")]
    scores = {r["id"]: {} for r in eligible}
    # Explicit order: all three Wave-1 bets before Wave-2 calculations.
    for wave in [1, 2]:
        for row in eligible:
            image = M.raster(ROOT / row["image"], frozen["analysis_width"]) if row.get("image") else None
            probe = json.loads((ROOT / row["probe"]).read_text()) if row.get("probe") else None
            operations = ({"17_tse": (image is not None, lambda: M.tse(image)),
                           "18_trees": (probe is not None, lambda: M.trees(probe)),
                           "1_raster": (image is not None, lambda: M.self_teaching(image)),
                           "1_html": (probe is not None, lambda: M.html_teaching(probe))} if wave == 1 else
                          {"10_squint": (image is not None, lambda: M.squint(image)),
                           "23_transport": (image is not None and probe is not None, lambda: M.transport(image, probe)),
                           "13_loom": (probe is not None, lambda: M.loom(probe)),
                           "14_chord": (probe is not None, lambda: M.chord(probe))})
            for name, (available, operation) in operations.items():
                if available:
                    score, detail = operation()
                    if score is not None and not math.isfinite(score):
                        raise ValueError(f"Nonfinite score: {row['id']} {name}")
                else:
                    score, detail = None, {"reason": "Required archived raster or matched HTML/DOM absent; no substitute"}
                scores[row["id"]][name] = {"score": score, "details": detail}
            print("wave", wave, row["id"], flush=True)
    bands = {}
    for base in ["17_tse", "1_raster", "10_squint"]:
        pins = [scores["pins/" + n][base]["score"] for n in ["001", "003", "004", "005"]]
        valid = all(p is not None for p in pins) and max(pins) - min(pins) > M.EPS
        low, high = (min(pins), max(pins)) if valid else (None, None)
        name = "27_band_" + base
        bands[name] = {"low": low, "high": high, "calibration": "four pins only", "rounds_used_for_fit": 0}
        for row in scores.values():
            value = row[base]["score"]
            score = -max(low - value, value - high, 0) / (high - low) if valid and value is not None else None
            row[name] = {"score": score, "details": bands[name]}
    decisions = adjudicate(corpus, scores)
    # Independent analytic diagnostics; never used to select or tune a candidate.
    block = np.eye(M.REGIONS)
    for start in range(0, M.REGIONS, M.COLS):
        block[start:start + M.COLS, start:start + M.COLS] = 0.5
    np.fill_diagonal(block, 1)
    clones = np.full((M.REGIONS, M.REGIONS), 1 - 1 / (M.CONFIG["region_samples"] ** 2 * 4))
    np.fill_diagonal(clones, 1)
    controls = {name: M.complexity_matrix(matrix)[0] for name, matrix in {"independent_identity": np.eye(M.REGIONS), "modular_blocks": block, "near_cloned_variables": clones}.items()}
    result = {"created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "freeze_sha256": digest(freeze_file), "freeze_file": str(freeze_file.relative_to(ROOT)), "analysis_width": frozen["analysis_width"],
              "environment": {"python": sys.version, "executable": sys.executable, "platform": platform.platform(), "numpy": np.__version__, "scipy": scipy.__version__, "pillow": PIL.__version__, "zstd": subprocess.run(["zstd", "--version"], capture_output=True, text=True, check=True).stdout.strip()},
              "total_specimens": len(corpus["specimens"]), "eligible_specimens": len(eligible), "scores": scores, "gates": decisions, "bands": bands, "tse_analytic_diagnostics": controls}
    verify_freeze(freeze_file)
    write_json(out, result)
    print(json.dumps({name: {"status": r["status"], "gates": {g: r[g]["status"] for g in "ABCD"}, "wins": int(r["B"]["wins"]), "p": r["B"].get("p_raw")} for name, r in decisions.items()}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--freeze-record", type=Path, default=HERE / "freeze.json", help="Explicit immutable freeze record; amendments never overwrite an earlier record")
    parser.add_argument("--out", type=Path, default=HERE / "scores.json")
    args = parser.parse_args()
    if args.freeze:
        freeze(args.freeze_record)
    elif args.verify:
        data = verify_freeze(args.freeze_record)
        print("Verified", len(data["files"]), "frozen files and all protected paths")
    else:
        run(args.out, args.freeze_record)
