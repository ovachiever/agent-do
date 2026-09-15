import {check, escapeHTML as e, digest} from './core.js';
import {validateContext} from './contracts.js';
import {validateProgram} from './construct.js';
import {rgb, contrast} from './math.js';

export function render(context,program) {
  validateContext(context);validateProgram(context,program);
  const b=context.brief, f=b.frame,wide=program.frames.wide,narrow=program.frames.narrow;
  const assets=new Map(context.assets.map(a=>[a.id,a]));
  const nodes=new Map(b.nodes.map(n=>[n.id,n])),groups=new Map(b.groups.map(g=>[g.id,g]));
  const inkOnAccent=contrast(rgb(f.accent),rgb(f.ink))>=contrast(rgb(f.accent),rgb(f.paper))?f.ink:f.paper;
  function node(id) {
    const n=nodes.get(id);if(!n)return group(id);
    const attr=`id="${e(id)}" data-ap-node="${e(id)}" data-role="${e(n.role)}"`;
    if(n.kind==='image') {const a=assets.get(n.asset);return `<figure class="ap-terminal ap-media" ${attr}><img src="data:${a.mime};base64,${a.data}" alt="${e(a.alt)}" data-ap-asset="${e(a.id)}" loading="eager"></figure>`;}
    if(n.kind==='action') return `<a class="ap-terminal ap-action" ${attr} href="${e(n.href)}">${e(n.text)}</a>`;
    const tag=n.role==='display'?'h1':n.role==='heading'?`h${n.level??2}`:n.role==='body'?'p':'div';
    return `<${tag} class="ap-terminal ap-${n.role}" ${attr}>${e(n.text)}</${tag}>`;
  }
  function group(id) {
    const g=groups.get(id),r=program.topology.regions.find(v=>v.id===id);
    const tag=g.kind==='disclosure'?'details':g.kind;
    const content=r.lanes.map((lane,i)=>`<div class="ap-lane" data-lane="${i}">${lane.map(node).join('')}</div>`).join('');
    const summary=g.kind==='disclosure'?`<summary>${e(g.title)}</summary>`:'';
    return `<${tag} id="${e(id)}" class="ap-region ap-surface-${g.surface}" data-ap-group="${e(id)}" data-production="${r.production}" data-kind="${g.kind}" style="--trajectory:${g.trajectory}">${summary}<div class="ap-layout">${content}</div></${tag}>`;
  }
  const vars=t=>`--body:${t.body}px;--display:${t.display}px;--heading:${t.heading}px;--gap:${t.gap}px;--interval:${t.interval}px;--outer:${t.outer}px;--radius:${t.radius}px;--stroke:${t.stroke}px;--display-weight:${t.displayWeight};`;
  const css=`
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:${f.paper};color:${f.ink};font-family:${f.bodyFont};font-size:var(--body);line-height:1.55;${vars(wide)}--paper:${f.paper};--ink:${f.ink};--accent:${f.accent};--tint:${wide.tint}}
button,input,select,textarea{font:inherit}a{color:inherit}a:focus-visible,summary:focus-visible{outline:3px solid ${f.accent};outline-offset:5px}img{display:block;max-width:100%;width:100%;height:100%;object-fit:cover}h1,h2,h3,h4,h5,h6,p,figure{margin:0}h1,h2,h3,h4,h5,h6{font-family:${f.displayFont};font-weight:var(--display-weight);line-height:1.04;text-wrap:balance}p{max-width:65ch}main{display:block}.ap-region{min-width:0}.ap-region[data-root]{max-width:${f.maxWidth}px;margin-inline:auto;padding:var(--outer) var(--interval)}.ap-region[data-kind=header],.ap-region[data-kind=footer]{padding-block:var(--interval)}
.ap-layout,.ap-lane{min-width:0}.ap-layout{display:grid;gap:var(--interval)}.ap-lane{display:flex;flex-direction:column;gap:calc(var(--interval)*var(--trajectory));align-items:flex-start}.ap-terminal{min-width:0;max-width:100%;overflow-wrap:anywhere}.ap-display{font-size:var(--display);letter-spacing:-.035em}.ap-heading{font-size:var(--heading);letter-spacing:-.025em}.ap-body{font-size:var(--body)}.ap-caption,.ap-label{font-size:max(0.8em,14px);line-height:1.45}.ap-brand{font-family:${f.displayFont};font-size:1.25em;font-weight:600}.ap-value{font-family:${f.displayFont};font-size:calc(var(--heading)*1.3);line-height:1.05}.ap-display+.ap-body{margin-top:calc(var(--gap) - var(--interval)*var(--trajectory))}
.ap-action{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:.65em 1.15em;background:${f.accent};color:${inkOnAccent};font-size:.88em;font-weight:650;line-height:1.25;text-decoration:none;border:var(--stroke) solid currentColor;border-radius:var(--radius);transition:transform .15s}.ap-action:hover{transform:translateY(-2px)}.ap-media{width:100%;align-self:stretch;border-radius:var(--radius);overflow:hidden;aspect-ratio:1.2}.ap-media img{object-position:center}.ap-surface-tint{background:var(--tint)}.ap-surface-accent{background:${f.accent};color:${inkOnAccent}}.ap-surface-ink{background:${f.ink};color:${f.paper}}.ap-region:not([data-root])[class*=ap-surface-]:not(.ap-surface-paper){padding:var(--interval);border-radius:var(--radius)}
.ap-region[data-production=partition]>.ap-layout{grid-template-columns:minmax(0,${program.z.balance}fr) minmax(0,${1-program.z.balance}fr);align-items:center;column-gap:calc(var(--interval)*1.6)}
.ap-region[data-production=sequence]>.ap-layout>.ap-lane{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));align-items:start;gap:calc(var(--interval)*var(--trajectory));width:100%}
.ap-region[data-kind=header]>.ap-layout>.ap-lane,.ap-region[data-kind=nav]>.ap-layout>.ap-lane,.ap-region[data-kind=footer]>.ap-layout>.ap-lane{display:flex;flex-direction:row;flex-wrap:wrap;align-items:center;justify-content:space-between;width:100%}
.ap-region[data-production=field]>.ap-layout>.ap-lane{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);align-items:center;width:100%}.ap-region[data-production=field]>.ap-layout>.ap-lane>:first-child{grid-column:1/-1}.ap-region[data-production=field]>.ap-layout>.ap-lane>:nth-child(2n){margin-block-start:var(--interval)}
.ap-region[data-production=overlay]>.ap-layout{display:grid;isolation:isolate}.ap-region[data-production=overlay]>.ap-layout>.ap-lane{grid-area:1/1}.ap-region[data-production=overlay]>.ap-layout>.ap-lane:first-child{background:var(--paper);color:var(--ink);padding:calc(var(--interval)*1.5);margin:var(--interval);z-index:1;align-self:center;max-width:65%;border-radius:var(--radius)}.ap-region[data-production=overlay]>.ap-layout>.ap-lane:last-child{min-height:360px}.ap-region[data-production=overlay] .ap-media{height:100%;aspect-ratio:auto}
details{border-block-start:var(--stroke) solid currentColor;padding-block:var(--interval)}summary{cursor:pointer;font-family:${f.displayFont};font-size:var(--heading);line-height:1.2}details[open]>.ap-layout{margin-top:var(--interval)}.ap-skip{position:absolute;left:1rem;top:-100px;background:var(--paper);padding:1rem;z-index:10}.ap-skip:focus{top:1rem}
@media(max-width:700px){body{${vars(narrow)}}.ap-region[data-root]{padding-inline:var(--interval)}.ap-region[data-production=partition]>.ap-layout{grid-template-columns:minmax(0,1fr)}.ap-region[data-production=field]>.ap-layout>.ap-lane{grid-template-columns:minmax(0,1fr)}.ap-region[data-production=field]>.ap-layout>.ap-lane>:nth-child(2n){margin-block-start:0}.ap-region[data-production=overlay]>.ap-layout>.ap-lane:first-child{max-width:calc(100% - 2*var(--interval));margin-top:calc(var(--outer)*2)}.ap-display{max-width:100%}.ap-media{aspect-ratio:1.2}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*::before,*::after{transition:none!important;animation:none!important}}
`;
  const content=program.topology.roots.map(group).join('').replace(/class="ap-region/g,'data-root class="ap-region');
  // Only actual roots carry root layout. Nested regions keep their containment.
  const rootSet=new Set(program.topology.roots);
  const marked=content.replace(/id="([^"]+)" data-root class="ap-region/g,(all,id)=>rootSet.has(id)?all:`id="${id}" class="ap-region`);
  return `<!doctype html><html lang="${e(b.lang)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="aphrodite-program" content="${program.digest}"><meta name="aphrodite-context" content="${context.digest}"><title>${e(b.title)}</title><style>${css}</style></head><body><a class="ap-skip" href="#ap-main">Skip to content</a><main id="ap-main">${marked}</main></body></html>`;
}
export const renderDigest=(context,program)=>digest(render(context,program));
