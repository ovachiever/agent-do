// Polish audit — run inside the page via `agent-do browse eval`. Measures, never eyeballs.
// Reports: (1) orphans: block text whose last line holds a single word; (2) short-tail wraps:
// short labels/captions/figure lines (<= 60 chars) that wrap onto a 2nd line; (3) duplicated
// sentences (same sentence in two elements); (4) grid siblings whose vertical centres differ by
// > 24px (a control block "floating" against its neighbour); (5) horizontal overflow.
(function(){
  const out = {orphans:[], shortWraps:[], duplicates:[], floating:[], overflow:null};
  out.overflow = document.documentElement.scrollWidth > document.documentElement.clientWidth ? document.documentElement.scrollWidth : null;
  const isText = el => el.children.length === 0 && el.textContent.trim().length > 0;
  const lineCount = el => { const r = document.createRange(); r.selectNodeContents(el); const tops = new Set(); for (const b of r.getClientRects()) { if (b.width < 1) continue; tops.add(Math.round(b.top/4)); } return tops.size || 1; };
  const els = [...document.querySelectorAll('body *')].filter(e => { const t = e.tagName.toLowerCase(); return !['script','style','svg','path','g','circle','rect','line','text','tspan'].includes(t) && isText(e); });
  for (const el of els) {
    const txt = el.textContent.trim().replace(/\s+/g,' ');
    const lines = lineCount(el);
    if (lines >= 2) {
      // last-line word count via range measurement
      const range = document.createRange(); const node = el.firstChild;
      if (node && node.nodeType === 3) {
        const words = txt.split(' '); const lastWord = words[words.length-1];
        const idx = node.textContent.lastIndexOf(lastWord);
        if (idx >= 0) {
          range.setStart(node, idx); range.setEnd(node, idx + lastWord.length);
          const r = range.getBoundingClientRect(); const box = el.getBoundingClientRect();
          // find how many words share the last line
          let onLast = 0;
          for (let i = words.length-1, pos = node.textContent.length; i >= 0; i--) {
            const w = words[i]; const j = node.textContent.lastIndexOf(w, pos); if (j < 0) break;
            range.setStart(node, j); range.setEnd(node, j + w.length);
            const rr = range.getBoundingClientRect();
            if (Math.abs(rr.top - r.top) < 2) onLast++; else break;
            pos = j - 1;
          }
          if (onLast === 1 && words.length >= 4) out.orphans.push({text: txt , lastWord});
        }
      }
      if (txt.length <= 60) out.shortWraps.push({text: txt, lines});
    }
  }
  // duplicates: sentence-level
  const seen = new Map();
  for (const el of els) {
    const txt = el.textContent.trim().replace(/\s+/g,' ');
    for (const s of txt.split(/(?<=[.!?])\s+/)) { if (s.split(' ').length < 4) continue; const k = s.toLowerCase(); seen.set(k, (seen.get(k)||0)+1); }
  }
  for (const [k,v] of seen) if (v > 1) out.duplicates.push({sentence: k , count: v});
  // floating: grid/flex containers with 2 children whose vertical centres differ
  for (const c of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(c); if (!(cs.display === 'grid' || cs.display === 'flex')) continue;
    const kids = [...c.children].filter(k => k.getBoundingClientRect().height > 0); if (kids.length !== 2) continue;
    if (cs.display === 'flex' && cs.flexDirection.startsWith('column')) continue;
    const [a,b] = kids.map(k => k.getBoundingClientRect());
    if (Math.abs(a.left - b.left) < 8) continue; // stacked, not side by side
    const ca = a.top + a.height/2, cb = b.top + b.height/2;
    const hasControl = kids.some(k => k.querySelector('a,button') && k.getBoundingClientRect().height < 120);
    if (hasControl && Math.abs(ca - cb) > 24) out.floating.push({container: (c.className||c.tagName).toString() , delta: Math.round(ca - cb)});
  }
  return JSON.stringify(out);
})()
