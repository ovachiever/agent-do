/* Mechanical layout audit. Every tolerance is a measured browser quantity.
 * Policy: corpus/design/rounds/home1/round2, Erik's 2026-09-18 polish ruling.
 * This function is evaluated by agent-do browse in the rendered page. */
async function designPolish(config = {}) {
  for (const a of config.alignments || []) {
    if (!a.source || !['top','center','bottom'].includes(a.mode)) throw new Error('alignment relationships require a source and top, center or bottom mode');
  }
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
      // Closed details can retain client rects. Only their first summary is exposed,
      // and a nested summary does not escape a closed outer disclosure.
      if (p.matches('details:not([open])')) {
        const summary=[...p.children].find(child=>child.localName==='summary');
        if (!summary?.contains(el)) return false;
      }
    }
    return true;
  };
  const paddingBounds = el => {
    const b=el.getBoundingClientRect(), s=getComputedStyle(el);
    return {left:b.left+parseFloat(s.borderLeftWidth),right:b.right-parseFloat(s.borderRightWidth),
      top:b.top+parseFloat(s.borderTopWidth),bottom:b.bottom-parseFloat(s.borderBottomWidth)};
  };
  const clamps=new Map();
  const controls=[...document.querySelectorAll('[aria-expanded="false"]')].filter(el=>
    el.matches('button,[role="button"],input[type="button"]') && visible(el) && el.getClientRects().length &&
    !el.matches(':disabled') && !el.closest('[inert],[aria-disabled="true"]'));
  for (const el of document.querySelectorAll('[data-polish-clamp]')) {
    if (!visible(el) || !['hidden','clip'].includes(getComputedStyle(el).overflowY)) continue;
    const control=controls.find(c=>{
      // An explicit relationship wins. Without one, accept only an unambiguous
      // local disclosure, not an unrelated collapsed control elsewhere on the page.
      if (c.hasAttribute('aria-controls')) return el.id && c.getAttribute('aria-controls').split(/\s+/u).includes(el.id);
      const container=el.parentElement;
      return container && container.contains(c) && container.querySelectorAll('[data-polish-clamp]').length===1 &&
        container.querySelectorAll('[aria-expanded]').length===1;
    });
    if (control) clamps.set(el,control);
  }
  const excluded = el => !!el.closest('script,style,noscript,template,head,svg defs,svg title,svg desc');
  const owner = el => {
    if (el.closest('svg text')) return el.closest('svg text');
    for (let p=el; p && p!==document.body; p=p.parentElement) {
      // Inline provenance spans must not split a paragraph's wrapping/duplicate analysis.
      if (p.matches('button,label,legend,figcaption,summary,[data-polish-phrase]')) return p;
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
  const unsupportedClips=new Set();
  const clipBounds=el=>{
    const style=getComputedStyle(el),value=style.clipPath;
    if (style.maskImage && style.maskImage!=='none') unsupportedClips.add(selector(el)+' mask');
    if (!value || value==='none') return null;
    const match=value.match(/url\(["']?(?:[^#]*)#([^"')]+)["']?\)/u);
    const clip=match?document.getElementById(match[1]):null;
    if (!(el instanceof SVGGraphicsElement) || !clip || clip.children.length!==1 || clip.children[0].localName!=='rect') {
      unsupportedClips.add(selector(el)+' '+value);return null;
    }
    const shape=clip.children[0],box=shape.getBBox();
    if (shape.rx.baseVal.value || shape.ry.baseVal.value) {unsupportedClips.add(selector(el)+' rounded clip');return null;}
    let matrix=el.getScreenCTM();
    if (clip.clipPathUnits.baseVal===SVGUnitTypes.SVG_UNIT_TYPE_OBJECTBOUNDINGBOX) {
      const target=el.getBBox();matrix=matrix.translate(target.x,target.y).scaleNonUniform(target.width,target.height);
    }
    const clipTransform=clip.transform.baseVal.consolidate();if (clipTransform) matrix=matrix.multiply(clipTransform.matrix);
    const shapeTransform=shape.transform.baseVal.consolidate();if (shapeTransform) matrix=matrix.multiply(shapeTransform.matrix);
    // A rotated clipping rectangle cannot be verified by its axis-aligned bounds alone.
    if (matrix.b!==0 || matrix.c!==0) {unsupportedClips.add(selector(el)+' rotated clip');return null;}
    const a=new DOMPoint(box.x,box.y).matrixTransform(matrix),b=new DOMPoint(box.x+box.width,box.y+box.height).matrixTransform(matrix);
    return {left:Math.min(a.x,b.x),right:Math.max(a.x,b.x),top:Math.min(a.y,b.y),bottom:Math.max(a.y,b.y)};
  };
  const groups=new Map(), ordered=[];
  const walker=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node=walker.currentNode, el=node.parentElement;
    if (!el || excluded(el) || !visible(el)) continue;
    const style=getComputedStyle(el);
    if (/rgba\([^)]*,\s*0(?:\.0+)?\s*\)$/u.test(style.color) || style.webkitTextFillColor==='transparent') continue;
    const range=document.createRange(); range.selectNodeContents(node);
    const boxes=[...range.getClientRects()].filter(r=>r.width>0 && r.height>0);
    if (!boxes.length && !node.textContent.trim()) continue;
    if (!boxes.length) continue;
    if (boxes.every(b=>b.right<=0 || b.bottom<=0)) continue;
    const block=owner(el);
    if (!groups.has(block)) groups.set(block,{el:block,nodes:[],words:[],text:''});
    const previous=ordered.at(-1);
    let separator='';
    if (previous) {
      const between=document.createRange();between.setStartAfter(previous.node);between.setEndBefore(node);
      if (between.cloneContents().querySelector('br')) separator='\n';
    }
    const g=groups.get(block); g.nodes.push(node); g.text+=separator+node.textContent;
    ordered.push({node,el,block,text:separator+node.textContent,boxes});
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
    const disclosureBounds=[];
    for (let p=g.el;p;p=p.parentElement) if (clamps.has(p)) disclosureBounds.push(paddingBounds(p));
    // A deliberately collapsed tail must not manufacture a last-line orphan.
    const layoutWords=words.filter(word=>disclosureBounds.every(b=>word.bottom>b.top && word.top<b.bottom));
    for (const word of layoutWords) {
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
      const reachable={x:[],y:[]};
      for (let p=g.el;p;p=p.parentElement) {
        const style=getComputedStyle(p), b=p.getBoundingClientRect();
        const clipping=clipBounds(p);
        if (clipping && (word.left<clipping.left-pixel || word.right>clipping.right+pixel || word.top<clipping.top-pixel || word.bottom>clipping.bottom+pixel)) {
          if (!findings.clipped_text.some(f=>f.selector===sel && f.clipped_by===selector(p)+' clipPath')) findings.clipped_text.push({selector:sel,text,clipped_by:selector(p)+' clipPath',text_rect:word,clip_rect:clipping,tolerance_px:pixel,threshold_source:'one physical pixel converted through devicePixelRatio'});
        }
        const clipX=['hidden','clip'].includes(style.overflowX), clipY=['hidden','clip'].includes(style.overflowY) && !clamps.has(p);
        const {left,right,top,bottom}=paddingBounds(p);
        // Scrolling only protects the axis it can move, and only while its
        // viewport fits inside this clip. Inner clips and cut-off scrollports
        // remain findings; a sibling scroller cannot shelter inaccessible text.
        const reachableX=reachable.x.some(port=>port.left>=left-pixel && port.right<=right+pixel);
        const reachableY=reachable.y.some(port=>port.top>=top-pixel && port.bottom<=bottom+pixel);
        if ((clipX && !reachableX && (word.left<left-pixel || word.right>right+pixel)) ||
            (clipY && !reachableY && (word.top<top-pixel || word.bottom>bottom+pixel))) {
          if (!findings.clipped_text.some(f=>f.selector===sel && f.clipped_by===selector(p))) findings.clipped_text.push({selector:sel,text,clipped_by:selector(p),text_rect:word,clip_rect:rect(b),tolerance_px:pixel,threshold_source:'one physical pixel converted through devicePixelRatio'});
        }
        const port={left,right,top,bottom};
        const horizontal=style.writingMode==='horizontal-tb';
        let reverseX=horizontal ? style.direction==='rtl' : style.writingMode.endsWith('-rl');
        let reverseY=!horizontal && (style.direction==='rtl') !== (style.writingMode==='sideways-lr');
        if (['flex','inline-flex'].includes(style.display)) {
          if (style.flexDirection===(horizontal?'row-reverse':'column-reverse')) reverseX=!reverseX;
          if (style.flexDirection===(horizontal?'column-reverse':'row-reverse')) reverseY=!reverseY;
        }
        const startX=reverseX ? right-p.scrollWidth : left, endX=reverseX ? right : left+p.scrollWidth;
        const startY=reverseY ? bottom-p.scrollHeight : top, endY=reverseY ? bottom : top+p.scrollHeight;
        // Content before the scroll origin is unreachable, even with a scrollbar.
        // Existing inner scrollports may represent words already reachable there.
        const inScrollX=[word,...reachable.x].some(r=>r.left+p.scrollLeft>=startX-pixel && r.right+p.scrollLeft<=endX+pixel);
        const inScrollY=[word,...reachable.y].some(r=>r.top+p.scrollTop>=startY-pixel && r.bottom+p.scrollTop<=endY+pixel);
        if (['auto','scroll'].includes(style.overflowX) && p.scrollWidth>p.clientWidth+pixel && inScrollX) reachable.x.push(port);
        if ((['auto','scroll'].includes(style.overflowY) && p.scrollHeight>p.clientHeight+pixel && inScrollY) || clamps.has(p)) reachable.y.push(port);
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
    if (['hidden','clip'].includes(style.overflowY) && !clamps.has(el) && el.scrollHeight>el.clientHeight+pixel) findings.overflow.push({selector:selector(el),axis:'y',scroll:el.scrollHeight,client:el.clientHeight,hidden:true,tolerance_px:pixel,threshold_source:'one physical pixel converted through devicePixelRatio'});
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
    bindings.push({text:row.text,selector:selector(row.el),node_id:node?.dataset.nodeId || null,node_instance:node?selector(node):null,fact_id:fact?.dataset.factId || null,copy_id:cp?.dataset.copyId || null});
  }
  for (const key of Object.keys(copies)) copies[key]=norm(copies[key]);
  const fontFailures=[...document.fonts].filter(f=>f.status==='error').map(f=>f.family);
  const generated=all.flatMap(e=>['::before','::after'].flatMap(p=>{
    const s=getComputedStyle(e,p),content=s.content;
    return s.display!=='none' && content && !['none','normal','""','\'\''].includes(content)?[{selector:selector(e)+p,content}]:[];
  }));
  const frames=[...document.querySelectorAll('iframe')],verifiedFrames=[];
  for (const frame of frames) {
    const proof=(config.verified_frames || []).find(p=>frame.matches(p.selector));
    if (!proof || frame.clientWidth!==proof.width || frame.clientHeight!==proof.height) continue;
    const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(frame.srcdoc));
    const hash=[...new Uint8Array(bytes)].map(b=>b.toString(16).padStart(2,'0')).join('');
    if (hash===proof.sha256) verifiedFrames.push({selector:proof.selector,source_sha256:hash,audit_sha256:proof.audit_sha256,viewport:{width:proof.width,height:proof.height}});
  }
  const coverage={text_runs:runs.length,svg_text_runs:runs.filter(r=>r.selector.includes('text')).length,fonts:document.fonts.status,font_failures:fontFailures,uninspected_frames:frames.length-verifiedFrames.length,independently_verified_frames:verifiedFrames,shadow_roots:all.filter(e=>e.shadowRoot).length,
    intentional_clamps:[...clamps].map(([el,control])=>({selector:selector(el),control:selector(control),axis:'y',source:'data-polish-clamp with a related enabled aria-expanded=false control'})),
    uninspected_generated_content:generated,uninspected_canvas:all.filter(e=>e.localName==='canvas').length,
    uninspected_clipping:[...unsupportedClips],uninspected_control_values:all.filter(e=>e.matches('input:not([type=hidden]),textarea') && (e.value || e.getAttribute('placeholder'))).map(e=>selector(e))};
  const complete=fontFailures.length===0 && coverage.uninspected_frames===0 && coverage.shadow_roots===0 && generated.length===0 && coverage.uninspected_canvas===0 && coverage.uninspected_control_values.length===0 && unsupportedClips.size===0;
  return {schema:1,url:location.href,viewport:{width:innerWidth,height:innerHeight,device_pixel_ratio:devicePixelRatio},coverage,complete,
    clean:complete && Object.values(findings).every(a=>a.length===0),findings,runs,text:{rendered,copies,bindings},
    fact_marks:[...document.querySelectorAll('[data-fact-id][data-value]')].map(e=>({selector:selector(e),fact_id:e.dataset.factId,value:e.dataset.value,visible:visible(e)})),
    document:{width:root.scrollWidth,height:root.scrollHeight}};
}
