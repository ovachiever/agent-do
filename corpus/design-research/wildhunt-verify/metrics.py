#!/usr/bin/env python3
"""Fixed research proxies. All design parameters are owned by PROTOCOL.md."""
import hashlib
import io
import itertools
import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.cluster.hierarchy import cut_tree, linkage
from scipy.ndimage import gaussian_filter, uniform_filter
from scipy.optimize import linprog
from scipy.spatial.distance import jensenshannon

from recover import HERE

CONFIG = json.loads((HERE / "config.json").read_text())
COLS, ROWS = CONFIG["grid_columns"], CONFIG["grid_rows"]
REGIONS = COLS * ROWS
EPS = CONFIG["float_epsilon_multiplier"] * np.finfo(float).eps
SEED = int.from_bytes(hashlib.sha256(b"mn-c2d546").digest(), "big")


def raster(path, width):
    image = Image.open(path).convert("RGBA")
    ground = Image.new("RGBA", image.size, "white")
    ground.alpha_composite(image)
    image = ground.convert("RGB")
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def pooled(array):
    return np.array([cell.sum() for band in np.array_split(array, ROWS, axis=0) for cell in np.array_split(band, COLS, axis=1)])


def probability(values):
    total = values.sum()
    if not np.isfinite(total) or total < 0:
        raise ValueError("Invalid probability mass")
    return values / total if total > EPS else np.ones(len(values)) / len(values)


def complexity_matrix(correlation):
    n = len(correlation)
    sign, logdet = np.linalg.slogdet(correlation)
    if sign <= 0:
        raise ValueError("Correlation matrix must be positive definite")
    integration = -logdet / 2
    rng = np.random.default_rng(SEED)
    curve = []
    for k in range(1, n):
        subsets = np.array([rng.permutation(n)[:k] for _ in range(n)])
        matrices = correlation[subsets[:, :, None], subsets[:, None, :]]
        signs, logs = np.linalg.slogdet(matrices)
        if np.any(signs <= 0):
            raise ValueError("Nonpositive subset determinant")
        curve.append(float(k / n * integration + np.mean(logs) / 2))
    return float(np.mean(curve)), {"integration": float(integration), "curve": curve, "subsets_per_size": n, "region_count": n}


def tse(image):
    size = CONFIG["region_samples"]
    array = np.asarray(image)
    vectors = []
    for band in np.array_split(array, ROWS, axis=0):
        for region in np.array_split(band, COLS, axis=1):
            rgb = np.asarray(Image.fromarray(region).resize((size, size), Image.Resampling.BILINEAR), dtype=float) / np.iinfo(np.uint8).max
            gx, gy = np.gradient(rgb.mean(axis=2))
            gradient = np.hypot(gx, gy) / math.sqrt(2)
            vectors.append(np.concatenate([rgb[:, :, c].ravel() for c in range(rgb.shape[2])] + [gradient.ravel()]))
    features = np.array(vectors)
    centered = features - features.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(centered, axis=1)
    scale = np.outer(norms, norms)
    correlation = np.divide(centered @ centered.T, scale, out=np.zeros_like(scale), where=scale > EPS)
    np.fill_diagonal(correlation, 1)
    shrinkage = 1 / features.shape[1]
    correlation = (1 - shrinkage) * correlation + shrinkage * np.eye(REGIONS)
    score, details = complexity_matrix(correlation)
    return score, dict(details, descriptor_length=features.shape[1], shrinkage=shrinkage, zero_variance_regions=int(np.sum(norms <= EPS)))


def nmi(a, b):
    _, ai = np.unique(a, return_inverse=True)
    _, bi = np.unique(b, return_inverse=True)
    counts = np.zeros((ai.max() + 1, bi.max() + 1))
    np.add.at(counts, (ai, bi), 1)
    p = counts / counts.sum()
    pa, pb = p.sum(axis=1), p.sum(axis=0)
    expected = np.outer(pa, pb)
    positive = p > 0
    mi = float(np.sum(p[positive] * np.log(p[positive] / expected[positive])))
    ha = float(-np.sum(pa[pa > 0] * np.log(pa[pa > 0])))
    hb = float(-np.sum(pb[pb > 0] * np.log(pb[pb > 0])))
    return (2 * mi / (ha + hb) if ha + hb > EPS else None), {"mi": mi, "entropy_a": ha, "entropy_b": hb}


def trees(probe):
    nodes = probe["nodes"]
    n = len(nodes)
    if n < 2:
        return None, {"reason": "Too few visible leaves", "nodes": n}
    sem = [node["semantic"] for node in nodes]
    groups = len(set(sem))
    if groups in {1, n}:
        return None, {"reason": "Uninformative DOM partition", "nodes": n, "semantic_groups": groups}
    width, height = probe["historical_extent"]
    geometry = np.array([[(x["x"] + x["width"] / 2) / width, (x["y"] + x["height"] / 2) / height] for x in nodes])
    families = sorted({x["font_family"] for x in nodes})
    style = np.array([[x["font_size"], x["font_weight"], *x["color"][:3], *x["background"], *[int(x["font_family"] == f) for f in families]] for x in nodes])
    std = style.std(axis=0)
    style = (style - style.mean(axis=0)) / np.where(std > EPS, std, 1)
    k = round(math.sqrt(n))
    geo_labels = cut_tree(linkage(geometry, method="ward"), n_clusters=k).ravel()
    style_labels = cut_tree(linkage(style, method="ward"), n_clusters=k).ravel()
    pairs = [nmi(geo_labels, style_labels), nmi(geo_labels, sem), nmi(style_labels, sem)]
    if any(value is None for value, _ in pairs):
        return None, {"reason": "Degenerate partition pair"}
    return min(value for value, _ in pairs), {"nodes": n, "k": k, "semantic_groups": groups, "agreements": {name: dict(detail, nmi=value) for name, (value, detail) in zip(["geometry_style", "geometry_dom", "style_dom"], pairs)}}


def compression_gain(top, bottom):
    if not top or not bottom:
        return None, {"reason": "Empty strip"}
    # Library-owned bound, read from the installed header instead of invented.
    header = Path("/opt/homebrew/include/zstd.h").read_text()
    minimum = int(re.search(r"#define\s+ZSTD_WINDOWLOG_MIN\s+(\d+)", header).group(1))
    window = max(minimum, math.ceil(math.log2(len(top) + len(bottom))))
    sizes = []
    for value in [top, bottom, top + bottom]:
        proc = subprocess.run(["zstd", "-q", "-c", "--single-thread", f"--long={window}"], input=value, capture_output=True, timeout=CONFIG["browser_timeout_seconds"])
        if proc.returncode:
            raise RuntimeError(proc.stderr.decode())
        sizes.append(len(proc.stdout))
    gain = (sizes[0] + sizes[1] - sizes[2]) / sizes[1]
    return gain, {"source_lengths": [len(top), len(bottom)], "compressed_lengths": sizes, "window_log": window}


def self_teaching(image):
    height = image.height // 2
    top = image.crop((0, 0, image.width, height))
    bottom = image.crop((0, height, image.width, height * 2))
    score, detail = compression_gain(top.tobytes(), bottom.tobytes())
    buffers = [io.BytesIO(), io.BytesIO()]
    for strip, buffer in zip([top, bottom], buffers):
        strip.save(buffer, format="PNG")
    encoded_score, encoded_detail = compression_gain(*(b.getvalue() for b in buffers))
    return score, dict(detail, dropped_rows=image.height - height * 2, png_encoded_diagnostic={"score": encoded_score, **encoded_detail})


def html_teaching(probe):
    midpoint = probe["historical_extent"][1] / 2
    top, bottom = [], []
    for node in probe["nodes"]:
        (top if node["y"] + node["height"] / 2 < midpoint else bottom).append(node["markup"])
    return compression_gain("\n".join(top).encode(), "\n".join(bottom).encode())


def squint(image):
    gray = np.asarray(image, dtype=float).mean(axis=2) / np.iinfo(np.uint8).max
    stop = CONFIG["region_samples"] // 2
    scales = [0] + [2 ** exponent for exponent in range(int(math.log2(stop)) + 1)]
    distributions = []
    for sigma in scales:
        smooth = gaussian_filter(gray, sigma=sigma) if sigma else gray
        dy, dx = np.gradient(smooth)
        distributions.append(probability(pooled(np.hypot(dx, dy))))
    divergences = [float(jensenshannon(a, b, base=2) ** 2) for a, b in zip(distributions, distributions[1:])]
    return 1 - float(np.mean(divergences)), {"scales": scales, "divergences": divergences}


def transport(image, probe):
    gray = np.asarray(image, dtype=float).mean(axis=2) / np.iinfo(np.uint8).max
    spectrum = np.fft.fft2(gray)
    log_amplitude = np.log(np.maximum(np.abs(spectrum), EPS))
    residual = log_amplitude - uniform_filter(log_amplitude, size=CONFIG["spectral_mean_kernel"])
    saliency = np.abs(np.fft.ifft2(np.exp(residual + 1j * np.angle(spectrum)))) ** 2
    saliency = gaussian_filter(saliency, CONFIG["spectral_smooth_sigma"])
    source = pooled(saliency)
    target = np.zeros(REGIONS)
    width, height = probe["historical_extent"]
    heading_levels = len(range(1, 7))  # HTML h1 through h6 specification; not a data cap.
    for n in probe["nodes"]:
        x = np.clip(n["x"] + n["width"] / 2, 0, width - EPS)
        y = np.clip(n["y"] + n["height"] / 2, 0, height - EPS)
        col = min(COLS - 1, int(x / width * COLS))
        row = min(ROWS - 1, int(y / height * ROWS))
        area = max(0, min(width, n["x"] + n["width"]) - max(0, n["x"])) * max(0, min(height, n["y"] + n["height"]) - max(0, n["y"]))
        target[row * COLS + col] += area / (n["heading"] or (heading_levels + 1))
    if source.sum() <= EPS or target.sum() <= EPS:
        return None, {"reason": "Empty saliency or importance mass"}
    a, b = probability(source), probability(target)
    centers = np.array([[(c + 0.5) / COLS * width, (r + 0.5) / ROWS * height] for r in range(ROWS) for c in range(COLS)])
    cost = np.linalg.norm(centers[:, None, :] - centers[None, :, :], axis=2) / math.hypot(width, height)
    constraints = np.concatenate([np.kron(np.eye(REGIONS), np.ones((1, REGIONS))), np.kron(np.ones((1, REGIONS)), np.eye(REGIONS))])
    result = linprog(cost.ravel(), A_eq=constraints, b_eq=np.r_[a, b], bounds=(0, None), method="highs")
    if not result.success:
        raise RuntimeError("Optimal transport failed: " + result.message)
    return 1 - float(result.fun), {"transport_cost": float(result.fun), "saliency_mass": a.tolist(), "importance_mass": b.tolist(), "solver": result.message}


def loom(probe):
    nodes = probe["nodes"]
    if not nodes:
        return None, {"reason": "No visible leaves"}
    ys = sorted({round(n["y"]) for n in nodes})
    xs = sorted({round(n["x"]) for n in nodes})
    yi, xi = {v: i for i, v in enumerate(ys)}, {v: i for i, v in enumerate(xs)}
    incidence = np.zeros((len(ys), len(xs)))
    for n in nodes:
        incidence[yi[round(n["y"])] , xi[round(n["x"])]] = 1
    singular = np.linalg.svd(incidence, compute_uv=False)
    p = singular[singular > EPS] / singular.sum()
    rank = math.exp(-float(np.sum(p * np.log(p))))
    return -rank / math.sqrt(len(nodes)), {"effective_rank": rank, "matrix_shape": list(incidence.shape), "nodes": len(nodes)}


def chord(probe):
    values = [n["font_size"] for n in probe["nodes"] if not n["visual"] and n["font_size"] > 0]
    if not values:
        return None, {"reason": "No text sizes"}
    sizes, counts = np.unique(values, return_counts=True)
    if len(sizes) == 1:
        return 0.0, {"sizes": sizes.tolist(), "pairs": 0, "note": "Monotony confound: one size has zero roughness"}
    harmonics = np.array([math.log2(p / q) for p in range(1, CONFIG["max_harmonic"] + 1) for q in range(1, CONFIG["max_harmonic"] + 1)])
    weighted, total = 0.0, 0
    for i, j in itertools.combinations(range(len(sizes)), 2):
        weight = int(counts[i] * counts[j])
        weighted += weight * float(np.min(np.abs(math.log2(sizes[i] / sizes[j]) - harmonics)))
        total += weight
    return -weighted / total, {"sizes": sizes.tolist(), "counts": counts.tolist(), "weighted_pairs": total}
