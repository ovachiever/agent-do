#!/usr/bin/env python3
"""Analytic and falsification-path checks, independent of corpus score outcomes."""
import unittest
import json
from pathlib import Path
import tempfile
import numpy as np
from PIL import Image
import metrics as m
from capture import parse_reply
from evaluate import gates, holm
from catalog import write_json
from recover import ROOT


class ResearchChecks(unittest.TestCase):
    def test_independent_variables_have_zero_complexity(self):
        score, detail = m.complexity_matrix(np.eye(m.REGIONS))
        self.assertEqual(score, 0)
        self.assertTrue(all(v == 0 for v in detail["curve"]))

    def test_integrated_modules_have_positive_complexity(self):
        matrix = np.eye(m.REGIONS)
        for start in range(0, m.REGIONS, m.COLS):
            matrix[start:start + m.COLS, start:start + m.COLS] = 0.5
        np.fill_diagonal(matrix, 1)
        self.assertGreater(m.complexity_matrix(matrix)[0], 0)

    def test_constant_raster_stays_finite(self):
        score, _ = m.tse(Image.new("RGB", (m.REGIONS, m.REGIONS), "white"))
        self.assertTrue(np.isfinite(score))

    def test_partition_identities_and_independence(self):
        self.assertAlmostEqual(m.nmi([0, 0, 1, 1], [4, 4, 7, 7])[0], 1)
        self.assertAlmostEqual(m.nmi([0, 0, 1, 1], [0, 1, 0, 1])[0], 0)
        self.assertIsNone(m.nmi([0, 0], [3, 3])[0])

    def test_repeated_prefix_beats_unrelated_bytes(self):
        rng = np.random.default_rng(m.SEED)
        n = m.REGIONS * m.CONFIG["region_samples"] ** 2
        a, b = [rng.integers(0, 256, n, dtype=np.uint8).tobytes() for _ in range(2)]
        self.assertGreater(m.compression_gain(a, a)[0], m.compression_gain(a, b)[0])
        self.assertIsNone(m.compression_gain(a, b"")[0])

    def test_no_missing_pin_passes_vacuously(self):
        scores = {"fixtures/canon-today": 2, "fixtures/canon-dossier": 2, "fixtures/barf": 0, "fixtures/broken": 0}
        result = gates(scores, [], 0.01)
        self.assertEqual(result["A"]["status"], "PASS")
        self.assertEqual(result["D"]["status"], "INCOMPLETE")
        self.assertEqual(result["C"]["status"], "INCOMPLETE")

    def test_tie_is_not_pairwise_success_and_missing_not_omitted(self):
        pairs = [{"winner": "a", "rejected": "b", "round": "one", "conditional": False}, {"winner": "c", "rejected": "d", "round": "two", "conditional": False}]
        result = gates({"a": 1, "b": 1, "c": 1}, pairs, 0.01)["B"]
        self.assertEqual(result["wins"], 0)
        self.assertEqual(result["required_pairs"], 2)
        self.assertEqual(result["measured_pairs"], 1)
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_holm_keeps_missing_tests_in_family(self):
        result = holm({"a": 0.01, "missing": 1, "c": 0.04})
        self.assertAlmostEqual(result["a"], 0.03)
        self.assertAlmostEqual(result["c"], 0.08)
        self.assertEqual(result["missing"], 1)

    def test_browse_close_text_contract_does_not_accept_arbitrary_text(self):
        self.assertTrue(parse_reply("close", "Browser closed\n")["success"])
        with self.assertRaises(ValueError):
            parse_reply("eval", "Browser closed\n")

    def test_scientific_scalars_preserve_json_types_and_reject_nan(self):
        parent = ROOT / ".dev/dpt-wildhunt/tests"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            target = Path(folder) / "scalar.json"
            write_json(target, {"count": np.int64(2), "pass": np.bool_(False), "score": np.float64(0.5)})
            self.assertEqual(json.loads(target.read_text()), {"count": 2, "pass": False, "score": 0.5})
            with self.assertRaises(ValueError):
                write_json(target, {"score": np.float64(float("nan"))})


if __name__ == "__main__":
    unittest.main()
