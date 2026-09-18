"""Render the predeclared four-page comparison, with no score-based choices."""
from html import escape
from pathlib import Path

from bench import read


def render(out):
    spec = read(out / "source/comparison.json")
    target = out / "comparison"
    target.mkdir(parents=True, exist_ok=True)
    c, p = spec["copy"], spec["palette"]
    base = f"""
*{{box-sizing:border-box}}html{{background:{p['paper']};color:{p['ink']}}}body{{margin:0;font:18px/1.6 Arial,sans-serif}}
a{{color:inherit}}a:focus-visible{{outline:3px solid #184f8e;outline-offset:5px}}
header{{max-width:1240px;margin:auto;padding:26px 0;display:flex;justify-content:space-between;align-items:center}}
.brand{{font:700 20px Georgia,serif}}header a{{font-size:14px}}
main{{max-width:1240px;margin:0 auto}}.hero{{padding:66px 62px 56px;min-height:670px;background:{p['field']};position:relative;overflow:hidden}}
.hero h1{{font-family:{spec['family']};font-weight:400;line-height:1.05;letter-spacing:-.035em;margin:0;position:relative;z-index:1}}
.description{{font-size:{spec['body_size']}px;line-height:1.65;width:490px;max-width:100%;margin-bottom:0;position:relative;z-index:1}}
.action{{display:inline-block;margin-top:30px;padding:12px 20px;border-radius:4px;background:{p['ink']};color:{p['paper']};font-size:15px;text-decoration:none;position:relative;z-index:1}}
.materials{{position:absolute;right:35px;bottom:30px;width:43%;height:330px;pointer-events:none}}
.details{{display:flex;justify-content:space-between;gap:24px;padding:22px 0;font-size:14px}}
.about{{display:grid;grid-template-columns:1fr 1fr;gap:60px;padding:30px 0 44px;border-top:1px solid #afc0bb}}
.about h2{{font:400 28px Georgia,serif;margin:0}}.about p{{font-size:{spec['body_size']}px;margin:0;max-width:520px}}
@media(max-width:800px){{header,main{{margin:0 20px}}.hero{{padding:38px 24px;min-height:780px}}.materials{{width:80%;height:260px;bottom:10px}}.details,.about{{display:block}}.details span{{display:block}}.about p{{margin-top:20px}}}}
"""
    art = f"""<svg class="materials" viewBox="0 0 480 330" aria-hidden="true">
<path d="M25 214L204 171 352 213 168 296Z" fill="{p['paper']}"/>
<path d="M44 221L165 269 165 279 44 232Z" fill="#d6dfd7"/>
<path d="M137 108L324 68 393 216 202 260Z" fill="{p['accent']}"/>
<path d="M185 96L274 190 393 216 324 68Z" fill="#eff7bc"/>
<ellipse cx="340" cy="270" rx="71" ry="20" fill="#638f91"/>
<path d="M299 265C254 201 319 176 355 197C393 219 392 279 347 279C313 279 306 258 323 246C343 232 361 251 347 260" fill="none" stroke="{p['ink']}" stroke-width="9" stroke-linecap="round"/>
<path d="M49 71C91 49 127 73 105 103C82 138 52 140 46 176" fill="none" stroke="#f0f3ef" stroke-width="4" stroke-linecap="round"/>
</svg>"""
    for label, values in spec["variants"].items():
        details = "".join(f"<span>{escape(t)}</span>" for t in c["details"])
        html = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(c['brand'])}, variant {label}</title><style>{base}
.hero h1{{font-size:{values['heading_size']}px}}.description{{margin-top:{values['gap']}px}}
</style><header><span class="brand">{escape(c['brand'])}</span><a href="#workshop">The workshop</a></header>
<main><section class="hero"><h1 data-measure="heading">{escape(c['title'])}</h1><p class="description" data-measure="support">{escape(c['description'])}</p>
<a class="action" href="#workshop">{escape(c['action'])}</a>{art}</section>
<div class="details">{details}</div><section class="about" id="workshop"><h2>{escape(c['support_title'])}</h2><p>{escape(c['support'])}</p></section></main></html>"""
        (target / f"{label}.html").write_text(html)
    # The observer sees neutral letters and can inspect the full-size pages.
    # No response is stored or attributed without an explicit user submission.
    pairs = "".join(f"<section><h2>Comparison {index}</h2><div class='pair'>" + "".join(
        f"<article><a href='{v}.html' target='_blank' rel='noopener'>Open {v} at full size</a><a href='{v}.html' target='_blank' rel='noopener'><img src='../captures/{v}.png' alt='Variant {v}'></a></article>" for v in pair) + "</div></section>"
        for index, pair in enumerate(spec["pairs"], 1))
    (target / "index.html").write_text(f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Space and type comparison</title>
<style>*{{box-sizing:border-box}}body{{margin:36px auto;padding:0 24px;max-width:1600px;font:17px/1.6 system-ui;color:#16383c;background:#f0f3ef}}h1{{font:42px Georgia,serif}}h2{{font-size:20px}}.pair{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}img{{width:100%;display:block;border:1px solid #9baea5;margin-top:12px}}a{{color:inherit}}@media(max-width:760px){{.pair{{grid-template-columns:1fr}}}}</style>
<h1>Space and type</h1><p>One fictional workshop, four arrangements. Open each page at full size before choosing.</p>
<p>In comparison 1, which feels better: A, B, or a tie? In comparison 2: C, D, or a tie?</p>{pairs}
<p>Reply with your two choices and, if useful, what affected them. No choice is recorded automatically.</p></html>""")
    return {"variants": list(spec["variants"]), "path": str(target / "index.html")}
