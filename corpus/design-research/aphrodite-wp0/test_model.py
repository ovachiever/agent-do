import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

from bench import diagnostics, sha, verify, write
from model import bind, chord, score

HERE = Path(__file__).resolve().parent
MODEL = json.loads((HERE / "model.json").read_text())


def node(tag, text, y, size=16, heading=None):
    return {"tag": tag, "markup": f"<{tag}>{text}</{tag}>", "x": 40, "y": y,
            "width": 400, "height": size, "font_size": size, "font_weight": 400,
            "font_family": "Georgia", "color": [20, 30, 40, 255], "semantic": 1,
            "heading": heading, "visual": False}


def specimen():
    return {"nodes": [node("h1", "Make room.", 0, 48, 1),
                      node("p", "First useful sentence.", 72),
                      node("p", "Another useful sentence.", 110)]}


class RelationalModelTests(unittest.TestCase):
    def test_uniform_scale_and_translation_preserve_every_feature(self):
        probe = specimen()
        expected = score(bind(probe, MODEL), MODEL)
        scaled = copy.deepcopy(probe)
        for n in scaled["nodes"]:
            for k in ("x", "y", "width", "height", "font_size"):
                n[k] *= 2.75
            n["x"] -= 300
            n["y"] += 1000
        actual = score(bind(scaled, MODEL), MODEL)
        for key in ("F01", "F02", "F03", "F08", "B", "additive"):
            self.assertAlmostEqual(expected[key], actual[key])

    def test_crossover_survives_increasing_log_transform(self):
        p = MODEL["parameters"]
        tight = [chord(24, h, 18, p) for h in (48, 96)]
        loose = [chord(48, h, 18, p) for h in (48, 96)]
        self.assertGreater(tight[0], tight[1])
        self.assertLess(loose[0], loose[1])
        self.assertGreater(math.log(tight[0]), math.log(tight[1]))
        self.assertLess(math.log(loose[0]), math.log(loose[1]))

    def test_blank_is_not_perfect_and_minimal_has_named_missing_relations(self):
        blank = score(bind({"nodes": []}, MODEL), MODEL)
        self.assertIsNone(blank["B"])
        minimal = score(bind({"nodes": specimen()["nodes"][:2]}, MODEL), MODEL)
        self.assertIsNone(minimal["B"])
        self.assertIn("F08", minimal["missing"])
        # Repeated minimal content IS eligible. No claim that content poverty is solved.
        self.assertIsNotNone(score(bind(specimen(), MODEL), MODEL)["B"])

    def test_human_labels_and_specimen_names_cannot_enter_features(self):
        probe = specimen()
        graph = bind(probe, MODEL)
        probe.update(id="fixtures/barf", label="winner", quote="beautiful", judge_score=0)
        self.assertEqual(graph, bind(probe, MODEL))

    def test_same_role_can_cross_containers_without_proximity_penalty(self):
        probe = specimen()
        probe["nodes"][2].update(semantic=99, x=5000, y=8000)
        graph = bind(probe, MODEL)
        self.assertIn({"kind": "same_role", "role": "prose", "a": 1, "b": 2}, graph["same_role"])
        self.assertAlmostEqual(score(graph, MODEL)["role_unity"]["prose"], 1)

    def test_unsupported_semantic_binding_cannot_silently_gain_a_relation(self):
        probe = specimen()
        probe["nodes"][0]["semantic"] = 9
        main = bind(probe, MODEL)
        strict = bind(probe, MODEL, "local_only")
        self.assertEqual(main["belongs_to"][0]["basis"], "following_fallback")
        self.assertEqual(strict["belongs_to"], [])
        self.assertIsNone(score(strict, MODEL)["B"])

    def test_bad_observations_fail_closed(self):
        for field, value in (("font_size", 0), ("x", float("nan")), ("font_weight", -1), ("color", [300, 0, 0])):
            probe = specimen()
            probe["nodes"][0][field] = value
            with self.assertRaises(ValueError):
                bind(probe, MODEL)

    def test_changed_frozen_input_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write(root / "input.json", {"nodes": []})
            write(root / "FREEZE.json", {"frozen_files": {"input.json": sha(root / "input.json")}})
            verify(root, False)
            write(root / "input.json", {"nodes": [1]})
            with self.assertRaisesRegex(ValueError, "Frozen input changed"):
                verify(root, False)

    def test_diagnostic_denominators_keep_conditional_and_missing_pairs(self):
        columns = ["F01", "F02", "F03", "F08", "B", "additive"]
        rows = {k: {f: v for f in columns} for k, v in {"c1": .9, "c2": .8, "bad": .7, "broken": .1, "missing": None}.items()}
        labels = {"fixtures": ["c1", "c2", "bad", "broken"], "primary": list(rows),
                  "pairs": [{"winner": "c1", "rejected": "bad", "round": "r", "conditional": False},
                            {"winner": "c2", "rejected": "missing", "round": "r", "conditional": True}],
                  "traps": [{"surface": "s", "null_id": "c1", "members": ["c1", "c2", "bad"]}]}
        report = diagnostics(rows, labels)
        self.assertEqual(report["pairs"]["B"]["denominator"], 2)
        self.assertEqual(report["pairs"]["B"]["evaluable"], 1)
        self.assertEqual(report["pairs"]["B"]["unconditional_denominator"], 1)
        self.assertEqual(report["decision"]["status"], "CANDIDATE_FAILED")


if __name__ == "__main__":
    unittest.main()
