#!/usr/bin/env python3
"""Predeclared TSE limiting-case diagnostics; never used to tune a score."""
import numpy as np
from PIL import Image
import metrics as m
from catalog import write_json
from recover import HERE

rng = np.random.default_rng(m.SEED)
size = m.CONFIG["region_samples"]
channels = Image.getmodebands("RGB")
maximum = np.iinfo(np.uint8).max + 1
tile = rng.integers(0, maximum, (size, size, channels), dtype=np.uint8)
independent = rng.integers(0, maximum, (m.ROWS * size, m.COLS * size, channels), dtype=np.uint8)
cloned = np.tile(tile, (m.ROWS, m.COLS, 1))
modular = np.concatenate([np.tile(rng.integers(0, maximum, tile.shape, dtype=np.uint8), (1, m.COLS, 1)) for _ in range(m.ROWS)])
data = {"authority": "PROTOCOL.md #17 checks; same fixed issue-derived RNG, grid and sampling. No outcome tuning.", "scores": {}}
for name, array in {"independent_noise": independent, "cloned_texture": cloned, "modular_texture": modular, "white": np.full_like(independent, maximum - 1)}.items():
    score, details = m.tse(Image.fromarray(array, "RGB"))
    data["scores"][name] = {"score": score, "details": details}
write_json(HERE / "controls.json", data)
print({name: row["score"] for name, row in data["scores"].items()})
