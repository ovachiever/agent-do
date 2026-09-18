/* Mechanical layout audit. Every tolerance is a measured browser quantity.
 * Policy: corpus/design/rounds/home1/round2, Erik's 2026-09-18 polish ruling.
 * This function is evaluated by agent-do browse in the rendered page. */
async function designPolish(config = {}) {
  await document.fonts.ready;
  await new Promise(requestAnimationFrame);
  const pixel = 1 / devicePixelRatio; // CSSOM physical-pixel resolution, not a taste threshold.
  const norm = s => s.replace(/\s+/gu, ' ').trim();
  const rect = r => ({x:r.x, y:r.y, width:r.width, height:r.height, left:r.left, right:r.right, top:r.top, bottom:r.bottom});
  const selector = el => {
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    while (el && el !== document.body) {
      const tag = el.localName;
      const siblings = [...el.parentElement?.children || []].filter(e => e.localName === tag);
      parts.unshift(tag + (siblings.length > 1 ? ':nth-of-type(' + (siblings.indexOf(el)+1) + ')' : ''));
      el = el.parentElement;
    }
    return ['body', ...parts].join(' > ');
  };
  const visible = el => {
    for (let p=el; p; p=p.parentElement) {
      const s=getComputedStyle(p);
      if (s.display==='none' || s.visibility==='hidden' || s.visibility==='collapse' || Number(s.opacity)===0 || p.hidden) return false;
    }
    return true;
  };
  const excluded = el => !!el.closest('script,style,noscript,template,head,svg defs,svg title,svg desc');
  const owner = el => {
    if (el.closest('svg text')) return el.closest('svg text');
    for (let p=el; p && p!==document.body; p=p.parentElement) {
      if (p.matches('button,label,legend,figcaption,summary,[data-copy-id],[data-node-id],[data-fact-id]')) return p;
      const d=getComputedStyle(p).display;
      if (!['inline','contents'].includes(d)) return p;
    }
    return document.body;
  };
  const lh = (el, ranges=[]) => {
    const value=parseFloat(getComputedStyle(el).lineHeight);
    if (Number.isFinite(value)) return value;
    const measured=ranges.filter(r=>r.height>0).map(r=>r.height);
    if (measured.length) return Math.max(...measured);
    const range=document.createRange(); range.selectNodeContents(el);
    const boxes=[...range.getClientRects()].filter(r=>r.height>0);
    return boxes.length ? Math.max(...boxes.map(r=>r.height)) : parseFloat(getComputedStyle(el).fontSize);
  };
  const findings={orphans:[],phrase_wraps:[],duplicates:[],floating_controls:[],clipped_text:[],overflow:[]};
  const groups=new Map(), ordered=[];
  const walker=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node=walker.currentNode, el=node.parentElement;
    if (!el || excluded(el) || !visible(el)) continue;
    const range=document.createRange(); range.selectNodeContents(node);
    const boxes=[...range.getClientRects()].filter(r=>r.width>0 && r.height>0);
    if (!boxes.length && !node.textContent.trim()) continue;
    if (!boxes.length) continue;
    const block=owner(el);
    if (!groups.has(block)) groups.set(block,{el:block,nodes:[],words:[],text:''});
    const g=groups.get(block); g.nodes.push(node); g.text+=node.textContent;
    ordered.push({node,el,block,text:node.textContent,boxes});
    for (const match of node.textContent.matchAll(/\S+/gu)) {
      range.setStart(node,match.index); range.setEnd(node,match.index+match[0].length);
      for (const box of range.getClientRects()) if (box.width>0 && box.height>0) g.words.push({text:match[0],...rect(box)});
    }
  }
  const runs=[];
  const sentenceGroups=new Map();
  const segmenter=new Intl.Segmenter(document.documentElement.lang || 'en',{granularity:'sentence'});
  for (const g of groups.values()) {
    const words=g.words, lines=[];
    for (const word of words) {
      let line=lines.find(l=>Math.min(l.bottom,word.bottom)-Math.max(l.top,word.top)>0);
      if (!line) {line={top:word.top,bottom:word.bottom,words:[]};lines.push(line);}
      line.words.push(word);
      line.top=Math.max(line.top,word.top); line.bottom=Math.min(line.bottom,word.bottom);
    }
    lines.sort((a,b)=>a.top-b.top);
    const text=norm(g.text), sel=selector(g.el), lineHeight=lh(g.el,words);
    const record={selector:sel,text,rect:rect(g.el.getBoundingClientRect()),lines:lines.map(l=>({top:l.top,bottom:l.bottom,words:l.words})),line_height:lineHeight,
      role:g.el.dataset.role || g.el.dataset.designRole || null,node_id:g.el.closest('[data-node-id]')?.dataset.nodeId || null,
      copy_id:g.el.closest('[data-copy-id]')?.dataset.copyId || null,fact_id:g.el.closest('[data-fact-id]')?.dataset.factId || null,
      font:{family:getComputedStyle(g.el).fontFamily,size_px:parseFloat(getComputedStyle(g.el).fontSize),weight:getComputedStyle(g.el).fontWeight}};
    runs.push(record);
    if (lines.length>1 && lines.at(-1).words.length===1) findings.orphans.push({selector:sel,text,last_word:lines.at(-1).words[0].text,lines:lines.length,rect:record.rect,source:'Home polish ruling: no orphan last words'});
    const protectedRole=g.el.matches('button,label,legend,[data-polish-phrase]') || ['label','figure','caption','action'].includes(record.role);
    const phraseMatches=(config.phrases || []).filter(p=>text.includes(typeof p==='string'?p:p.text));
    if (protectedRole && lines.length>1) findings.phrase_wraps.push({selector:sel,text,lines:lines.length,source:'semantic label/action/figure role, no character-count cutoff'});
    for (const phrase of phraseMatches) {
      const value=typeof phrase==='string'?phrase:phrase.text;
      const tokens=norm(value).split(' ');
      const flat=lines.flatMap((line,index)=>line.words.map(w=>({text:w.text,line:index})));
      for (let start=0;start<=flat.length-tokens.length;start++) {
        if (tokens.every((t,i)=>flat[start+i].text===t) && flat[start].line!==flat[start+tokens.length-1].line)
          findings.phrase_wraps.push({selector:sel,text:value,lines:flat[start+tokens.length-1].line-flat[start].line+1,source:typeof phrase==='string'?'brief protected phrase':phrase.source});
      }
    }
    for (const item of segmenter.segment(text)) {
      const sentence=norm(item.segment);
      if (!/[.!?]["'”’)]?$/u.test(sentence)) continue; // Sentences, not repeated interface labels.
      if (!sentenceGroups.has(sentence)) sentenceGroups.set(sentence,[]);
      sentenceGroups.get(sentence).push(sel);
    }
    for (const word of words) {
      for (let p=g.el;p;p=p.parentElement) {
        const style=getComputedStyle(p), b=p.getBoundingClientRect();
        const clipX=['hidden','clip'].includes(style.overflowX), clipY=['hidden','clip'].includes(style.overflowY);
        if (!(clipX || clipY)) continue;
        const left=b.left+parseFloat(style.borderLeftWidth),right=b.right-parseFloat(style.borderRightWidth);
        const top=b.top+parseFloat(style.borderTopWidth),bottom=b.bottom-parseFloat(style.borderBottomWidth);
        if ((clipX && (word.left<left-pixel || word.right>right+pixel)) || (clipY && (word.top<top-pixel || word.bottom>bottom+pixel))) {
          if (!findings.clipped_text.some(f=>f.selector===sel && f.clipped_by===selector(p))) findings.clipped_text.push({selector:sel,text,clipped_by:selector(p),text_rect:word,clip_rect:rect(b),tolerance_px:pixel,threshold_source:'one physical pixel converted through devicePixelRatio'});
        }
      }
    }
  }
  for (const [sentence,selectors] of sentenceGroups) if (selectors.length>1) findings.duplicates.push({sentence,count:selectors.length,selectors,source:'Home copy contract: each approved sentence once'});
  const all=[document.body,...document.body.querySelectorAll('*')].filter(e=>visible(e) && !excluded(e));
  for (const container of all) {
    const style=getComputedStyle(container);
    if (!['flex','grid','inline-flex','inline-grid'].includes(style.display)) continue;
    const children=[...container.children].filter(e=>visible(e) && e.getBoundingClientRect().height>0);
    if (children.length!==2) continue; // The observed relationship is a paired control and content group.
    const [a,b]=children.map(e=>e.getBoundingClientRect());
    if (Math.min(a.bottom,b.bottom)<=Math.max(a.top,b.top) || Math.min(a.right,b.right)>Math.max(a.left,b.left)+pixel) continue;
    const isControl=e=>{const text=norm(e.innerText || e.textContent);const controls=e.matches('button,a,input,select')?[e]:[...e.querySelectorAll('button,a,input,select')];return controls.length>0 && controls.map(c=>norm(c.innerText || c.textContent)).join(' ')===text;};
    if (children.filter(isControl).length!==1) continue;
    const declared=(config.alignments || []).find(r=>container.matches(r.selector));
    const mode=declared?.mode || 'center';
    const position=r=>mode==='top'?r.top:mode==='bottom'?r.bottom:(r.top+r.bottom)/2;
    const delta=Math.abs(position(a)-position(b)), tolerance=Math.max(...children.map(e=>lh(e)));
    if (delta>tolerance) findings.floating_controls.push({selector:selector(container),mode,delta_px:delta,tolerance_px:tolerance,threshold_source:'maximum computed line-height of the paired siblings',relationship_source:declared?.source || 'Home polish ruling: controls centered beside their neighboring content',rects:[rect(a),rect(b)]});
  }
  const root=document.documentElement;
  if (root.scrollWidth>root.clientWidth+pixel) findings.overflow.push({selector:'html',axis:'x',scroll:root.scrollWidth,client:root.clientWidth,tolerance_px:pixel,threshold_source:'one physical pixel converted through devicePixelRatio'});
  for (const el of all) {
    if (!(el instanceof HTMLElement)) continue;
    const style=getComputedStyle(el);
    if (['hidden','clip'].includes(style.overflowX) && el.scrollWidth>el.clientWidth+pixel) findings.overflow.push({selector:selector(el),axis:'x',scroll:el.scrollWidth,client:el.clientWidth,hidden:true,tolerance_px:pixel,threshold_source:'one physical pixel converted through devicePixelRatio'});
    if (['hidden','clip'].includes(style.overflowY) && el.scrollHeight>el.clientHeight+pixel) findings.overflow.push({selector:selector(el),axis:'y',scroll:el.scrollHeight,client:el.clientHeight,hidden:true,tolerance_px:pixel,threshold_source:'one physical pixel converted through devicePixelRatio'});
  }
  let rendered='', lastBlock=null;
  const copies={},copyBlocks={},bindings=[];
  for (const row of ordered) {
    if (lastBlock && lastBlock!==row.block) rendered+='\n';
    rendered+=row.text;lastBlock=row.block;
    const cp=row.el.closest('[data-copy-id]');
    if (cp) {
      const key=cp.dataset.copyId;
      copies[key]=(copies[key] || '')+(copyBlocks[key] && copyBlocks[key]!==row.block?'\n':'')+row.text;
      copyBlocks[key]=row.block;
    }
    const node=row.el.closest('[data-node-id]'), fact=row.el.closest('[data-fact-id]');
    bindings.push({text:row.text,selector:selector(row.el),node_id:node?.dataset.nodeId || null,fact_id:fact?.dataset.factId || null,copy_id:cp?.dataset.copyId || null});
  }
  for (const key of Object.keys(copies)) copies[key]=norm(copies[key]);
  const fontFailures=[...document.fonts].filter(f=>f.status==='error').map(f=>f.family);
  const coverage={text_runs:runs.length,svg_text_runs:runs.filter(r=>r.selector.includes('text')).length,fonts:document.fonts.status,font_failures:fontFailures,uninspected_frames:document.querySelectorAll('iframe').length,shadow_roots:all.filter(e=>e.shadowRoot).length};
  const complete=fontFailures.length===0 && coverage.uninspected_frames===0 && coverage.shadow_roots===0;
  return {schema:1,url:location.href,viewport:{width:innerWidth,height:innerHeight,device_pixel_ratio:devicePixelRatio},coverage,complete,
    clean:complete && Object.values(findings).every(a=>a.length===0),findings,runs,text:{rendered,copies,bindings},
    fact_marks:[...document.querySelectorAll('[data-fact-id][data-value]')].map(e=>({selector:selector(e),fact_id:e.dataset.factId,value:e.dataset.value,visible:visible(e)})),
    document:{width:root.scrollWidth,height:root.scrollHeight}};
}
