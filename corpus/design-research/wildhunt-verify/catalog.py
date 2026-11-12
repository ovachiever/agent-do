#!/usr/bin/env python3
"""Exact verdicts and explicit comparison policy; no metric-dependent labels."""
import hashlib
import json
from pathlib import Path
from recover import CORPUS, HERE, ROOT, RECORD


def write_json(path, obj):
    def scalar(value):
        # Preserve NumPy scalar values as JSON's corresponding native types.
        # Arrays and arbitrary objects still fail instead of becoming strings.
        if type(value).__module__ == "numpy" and getattr(value, "ndim", None) == 0:
            return value.item()
        raise TypeError(f"Not a JSON scalar: {type(value).__name__}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False, default=scalar) + "\n")


def main():
    rows = json.loads((HERE / "gallery-corpus.json").read_text())
    for r in rows:
        r["label"] = "quoted_unclassified" if r["quote"] else "unnoted"
        r["kind"] = "round"
        if r["round"] == "eng7":
            r["exclude_reason"] = "Unresolved E2 chat / E3 page-note winner conflict; excluded from every evaluation"
    # These are comparison roles, not rewritten verdicts. Verbatim quotes stay beside them.
    positives = {"concept2/library-B": "winner", "lib3/paneldock": "provisional_winner", "eng3/oneline": "advanced", "eng3/timetable2": "advanced", "eng6/M1": "advanced", "eng6/D1": "conditional_winner"}
    negatives = {"concept2/library-D", "concept2/library-A", "lib3/market", "lib3/deltas", "lib3/statled", "lib3/quiet", "eng3/ledgerfirst", "eng5/L2", "eng5/L3", "eng5/T2", "eng5/T3", "eng5/T4", "eng5/B1", "eng6/MC1"}
    for r in rows:
        if r["id"] in positives:
            r["label"] = positives[r["id"]]
        elif r["id"] in negatives:
            r["label"] = "rejected_structure" if r["id"] in {"eng6/MC1", "eng5/B1"} else "rejected"
    # The human choice and the original gallery's IMG placeholders jointly bind these IDs.
    quote = "for today I like the paper broadsheet and then for dossier I like the auction lot, and I dont' mind switching from paper broadsheet light to dossier dark, where just today is light mode; next, let's do designs for library and engine room, both should be only dark ground as only today would be warm paper (is it ok to do this?)"
    maps = {"today": {"A": "dispatch", "B": "null", "C": "paper", "D": "broadsheet", "E": "almanac"}, "dossier": {"A": "paper", "B": "legal", "C": "null", "D": "auction", "E": "notebook"}}
    for surface, names in maps.items():
        for letter, name in names.items():
            stem = surface + "-" + letter
            winner = (surface, letter) in {("today", "C"), ("dossier", "D")}
            rows.append({"id": "concept/" + stem, "round": "concept", "kind": "round", "name": stem,
                         "image": str((CORPUS / "concept/renders" / (stem + ".png")).relative_to(ROOT)),
                         "html": str((CORPUS / "concept" / surface / (name + ".html")).relative_to(ROOT)),
                         "label": "winner" if winner else "unselected", "quote": quote if winner else None,
                         "source": {"transcript": str(RECORD), "line": 2500, "gallery": "corpus/design/rounds/concept/gallery.html", "mapping": "gallery card title and IMG placeholder, cross-checked blind_key"}})
    for name in ["canon-today", "canon-dossier", "barf", "broken"]:
        rows.append({"id": "fixtures/" + name, "name": name, "round": "fixtures", "kind": "fixture", "html": f"tools/agent-dpt/fixtures/{name}.html", "label": "liked_direction" if name.startswith("canon") else "negative_control", "source": "tools/agent-dpt/fixtures/README.md", "image": f".dev/dpt-wildhunt/captures/fixtures/{name}.png"})
    pins = [("001", "recognitionoracle-2026-09-06.png"), ("002", None), ("003", "pangram-2026-09-06.png"), ("004", "petespasta-2026-09-06.png"), ("005", "sneakenergy-2026-09-07.png")]
    for number, shot in pins:
        pin = next((ROOT / "corpus/design/pins").glob(number + "-*.md"))
        r = {"id": "pins/" + number, "name": pin.stem, "round": "pins", "kind": "pin", "label": "pinned", "source": str(pin.relative_to(ROOT)), "quote_source_verbatim": pin.read_text(), "dom_absent_reason": "No matched historic DOM/computed-style capture; live replacement would be a different specimen"}
        if shot:
            r["image"] = "corpus/design/shots/" + shot
        else:
            r["image_absent_reason"] = "Pin 002 has no saved shot; documented headless block. No substitute."
        rows.append(r)
    for letter in "ABC":
        for surface in ["today", "engine"]:
            rows.append({"id": f"reground/{letter}-{surface}", "name": f"{letter}-{surface}", "round": "reground", "kind": "round", "html": f"corpus/design/rounds/reground/{letter}/{surface}.html", "label": "unruled", "quote": None, "exclude_reason": "No recovered human ruling on this specimen; retained, not scored"})
    for name in ["trainline", "timetable3"]:
        rows.append({"id": f"eng4/{name}", "name": name, "round": "eng4", "kind": "round", "html": f"corpus/design/rounds/eng4/{name}.html", "image": f"corpus/design/rounds/eng4/renders/{name}.png", "label": "unclassified", "quote": None, "exclude_reason": "No exact specimen-level ruling bound here; both refinements retained outside evaluation"})
    for r in rows:
        for field in ["image", "html"]:
            if r.get(field) and (ROOT / r[field]).exists():
                r[field + "_sha256"] = hashlib.sha256((ROOT / r[field]).read_bytes()).hexdigest()
    pairs = []
    for r in rows:
        if r["id"] not in positives:
            continue
        for n in rows:
            if n["id"] in negatives and n["round"] == r["round"]:
                pairs.append({"winner": r["id"], "rejected": n["id"], "round": r["round"], "conditional": r["label"] in {"provisional_winner", "conditional_winner"}})
    for group in sorted({r["round"] for r in rows}):
        path = CORPUS / group / "labels.yaml"
        write_json(path, {"format": "JSON is valid YAML 1.2", "label_authority": "Exact human quotes; comparison roles explicitly selected before scoring in PROTOCOL.md", "specimens": [r for r in rows if r["round"] == group], "primary_pairs": [p for p in pairs if p["round"] == group]})
    write_json(HERE / "corpus.json", {"specimens": rows, "primary_pairs": pairs})
    print(json.dumps({"specimens": len(rows), "primary_pairs": len(pairs), "pairs_by_round": {g: sum(p["round"] == g for p in pairs) for g in sorted({p["round"] for p in pairs})}}))


if __name__ == "__main__":
    main()
