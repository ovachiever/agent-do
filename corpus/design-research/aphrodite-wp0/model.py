"""An explicit, untrained relational hypothesis. No I/O, labels, or model calls."""
import math
import re
from collections import defaultdict
from html.parser import HTMLParser
from statistics import mean


class Markup(HTMLParser):
    def __init__(self, value):
        super().__init__(convert_charrefs=True)
        self.attrs = None
        self.parts = []
        self.feed(value)

    def handle_starttag(self, tag, attrs):
        if self.attrs is None:
            self.attrs = dict(attrs)

    def handle_data(self, data):
        self.parts.append(data)


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def kernel(residual, sigma):
    if not math.isfinite(residual) or not positive(sigma):
        raise ValueError("Finite residual and positive kernel scale required")
    return math.exp(-0.5 * (residual / sigma) ** 2)


def chord(gap, heading_size, body_size, parameters):
    if not positive(heading_size) or not positive(body_size) or not math.isfinite(gap) or gap < 0:
        raise ValueError("Invalid chord observation")
    residual = (gap - parameters["chord_gap_display_ratio"] * heading_size) / body_size
    return kernel(residual, parameters["chord_residual_body_sigma"])


def classify(node, binding):
    markup = Markup(node["markup"])
    attrs = markup.attrs or {}
    classes = set((attrs.get("class") or "").split())
    text = " ".join("".join(markup.parts).split())
    if classes.intersection(binding["hidden_classes"]) or attrs.get("aria-hidden") == "true":
        return "hidden"
    if node.get("visual"):
        return "visual"
    if node.get("heading"):
        return "display" if node["heading"] == binding["display_heading_level"] else "section"
    if classes.intersection(binding["title_classes"]):
        return "section"
    if classes.intersection(binding["brand_classes"]):
        return "brand"
    if node["tag"] in binding["action_tags"]:
        return "action"
    if re.fullmatch(binding["value_pattern"], text):
        return "value"
    if node["tag"] in binding["label_tags"] or classes.intersection(binding["label_classes"]):
        return "label"
    if node["tag"] in binding["prose_tags"]:
        return "prose"
    return "detail"


def bind(probe, model, variant=None):
    """Output the complete inferred graph before any feature is evaluated."""
    if not isinstance(probe.get("nodes"), list):
        raise ValueError("Observation must contain a nodes array")
    binding = model["role_binding"]
    variant = variant or binding["main_variant"]
    if variant not in {"local_then_following", "local_only"}:
        raise ValueError("Unknown graph variant")
    nodes, excluded = [], []
    for i, raw in enumerate(probe["nodes"]):
        if not all(positive(raw.get(k)) for k in ("width", "height", "font_size", "font_weight")):
            raise ValueError(f"Invalid dimensions/type at node {i}")
        if not all(isinstance(raw.get(k), (int, float)) and math.isfinite(raw[k]) for k in ("x", "y")):
            raise ValueError(f"Invalid position at node {i}")
        color = raw.get("color")
        if not isinstance(color, list) or len(color) < 3 or not all(isinstance(x, (int, float)) and math.isfinite(x) and 0 <= x <= 255 for x in color):
            raise ValueError(f"Invalid color at node {i}")
        role = classify(raw, binding)
        if role in {"hidden", "visual", "brand"}:
            excluded.append({"node": i, "reason": role})
            continue
        fields = ("x", "y", "width", "height", "font_size", "font_weight", "font_family", "color", "semantic")
        nodes.append({"id": i, "role": role, **{k: raw[k] for k in fields}})
    by_role = defaultdict(list)
    for node in nodes:
        by_role[node["role"]].append(node["id"])
    same = [{"kind": "same_role", "role": role, "a": a, "b": b}
            for role, ids in sorted(by_role.items()) for a, b in zip(ids, ids[1:])]
    dominant = {"display", "section", "value"}
    support = {"label", "prose", "detail"}
    belongs = []
    for index, node in enumerate(nodes):
        if node["role"] not in dominant:
            continue
        match = None
        for after in nodes[index + 1:]:
            if after["semantic"] != node["semantic"]:
                continue
            if after["role"] in dominant:
                break
            if after["role"] in support:
                match = after
                break
        basis = "recorded_container"
        if match is None and variant == "local_then_following":
            for after in nodes[index + 1:]:
                if after["role"] in dominant:
                    break
                if after["role"] in support:
                    match = after
                    basis = "following_fallback"
                    break
        if match is not None:
            belongs.append({"kind": "belongs_to", "a": node["id"], "b": match["id"], "basis": basis})
    constellations = []
    lookup = {n["id"]: n for n in nodes}
    for edge in belongs:
        peers = [x for x in by_role[lookup[edge["b"]]["role"]] if x != edge["b"]]
        if peers:
            peer = min(peers, key=lambda x: (abs(x - edge["b"]), x))
            constellations.append({"a": edge["a"], "b": edge["b"], "peer": peer})
    return {"author": binding["author"], "variant": variant, "nodes": nodes, "excluded": excluded,
            "same_role": same, "belongs_to": belongs, "constellations": constellations}


def separation(a, b):
    dx = max(a["x"] - b["x"] - b["width"], b["x"] - a["x"] - a["width"], 0)
    dy = max(a["y"] - b["y"] - b["height"], b["y"] - a["y"] - a["height"], 0)
    return math.hypot(dx, dy)


def identity(a, b, p):
    color_distance = math.sqrt(mean(((x-y)/255) ** 2 for x, y in zip(a["color"][:3], b["color"][:3])))
    return mean((kernel(math.log(a["font_size"] / b["font_size"]), p["same_size_log_sigma"]),
                 kernel(math.log(a["font_weight"] / b["font_weight"]), p["same_weight_log_sigma"]),
                 kernel(color_distance, p["same_rgb_sigma"]),
                 float(a["font_family"] == b["font_family"])))


def edge_values(a, b, p):
    gap, h, base = separation(a, b), a["font_size"], b["font_size"]
    target = p[{"display": "display_body_ratio", "section": "section_body_ratio", "value": "value_label_ratio"}[a["role"]]]
    return {"gap": gap, "heading_size": h, "support_size": base,
            "grouping": kernel(gap/base - p["belongs_gap_body_target"], p["belongs_gap_body_sigma"]),
            "distinction": kernel(math.log(h/base/target), p["distinction_log_sigma"]),
            "chord": chord(gap, h, base, p)}


def avg(values):
    return mean(values) if values else None


def score(graph, model):
    p = model["parameters"]
    nodes = {n["id"]: n for n in graph["nodes"]}
    role_values = defaultdict(list)
    for edge in graph["same_role"]:
        role_values[edge["role"]].append(identity(nodes[edge["a"]], nodes[edge["b"]], p))
    u = avg([mean(values) for values in role_values.values()])
    observed = [{**edge, **edge_values(nodes[edge["a"]], nodes[edge["b"]], p)} for edge in graph["belongs_to"]]
    g = avg([e["grouping"] for e in observed])
    d = avg([e["distinction"] for e in observed])
    joint, summed = [], []
    constellation_rows = []
    for row in graph["constellations"]:
        values = edge_values(nodes[row["a"]], nodes[row["b"]], p)
        repeat = identity(nodes[row["b"]], nodes[row["peer"]], p)
        factors = [values["chord"], values["distinction"], repeat]
        joint.append(math.prod(factors))
        summed.append(mean(factors))
        constellation_rows.append({**row, "factors": factors})
    features = {"F01": mean((u, g)) if u is not None and g is not None else None,
                "F02": u*d if u is not None and d is not None else None,
                "F03": avg([e["chord"] for e in observed]), "F08": avg(joint)}
    additive_features = {**features, "F02": mean((u, d)) if u is not None and d is not None else None, "F08": avg(summed)}
    missing = [k for k, v in features.items() if v is None]
    combined = lambda fs: sum(model["feature_weights"][k] * v for k, v in fs.items())
    return {**features, "B": None if missing else combined(features),
            "additive": None if missing else combined(additive_features),
            "status": "inapplicable" if missing else "computed", "missing": missing,
            "nodes": len(nodes), "excluded_nodes": len(graph["excluded"]),
            "same_role_edges": len(graph["same_role"]), "belongs_edges": len(observed),
            "fallback_edges": sum(e["basis"] == "following_fallback" for e in observed),
            "constellations": len(joint), "role_unity": {k: mean(v) for k, v in role_values.items()},
            "edges": observed, "joint_factors": constellation_rows}
