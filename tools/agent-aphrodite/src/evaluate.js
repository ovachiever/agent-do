import {check, mean, digest, clamp, finite} from './core.js';
import {validateContext} from './contracts.js';
import {validateProgram} from './construct.js';
import {affinity, geometric, product, separation, unionArea, center, area, contrast, colorDistance, rgb} from './math.js';

function hiddenGroups(brief,state) {
  const hidden=new Set();
  if(state==='base') {
    let changed=true;
    while(changed){changed=false;for(const g of brief.groups)if((g.kind==='disclosure'||hidden.has(g.parent))&&!hidden.has(g.id)){hidden.add(g.id);changed=true;}}
  }
  return hidden;
}
// Eligibility is fixed from the semantic brief and declared state, before a candidate is seen.
export function scope(context,state) {
  const b=context.brief,hidden=hiddenGroups(b,state),nodes=b.nodes.filter(n=>!hidden.has(n.group));
  const ids=new Set(nodes.map(n=>n.id)),relations=b.relations.filter(r=>r.nodes.every(id=>ids.has(id)));
  const relationIDs=new Set(relations.map(r=>r.id));
  const constellations=b.constellations.filter(h=>h.relations.every(id=>relationIDs.has(id)));
  const same=relations.filter(r=>r.kind==='same-role'),support=relations.filter(r=>r.kind==='supports'&&r.nodes.every(id=>b.nodes.find(n=>n.id===id).kind!=='image'));
  const sequence=relations.filter(r=>r.kind==='sequence');
  const active={
    'APH-01':relations.length>0,'APH-02':same.length>0&&relations.some(r=>['supports','contrasts'].includes(r.kind)),
    'APH-03':support.length>0,'APH-04':nodes.length>1,'APH-05':relations.some(r=>['supports','counterweight'].includes(r.kind)),
    'APH-06':sequence.length>0||same.length>0,'APH-07':nodes.length>0,'APH-08':constellations.length>0,'APH-09':true
  };
  return {nodes,relations,constellations,same,support,sequence,active,hidden:[...hidden]};
}
function textMass(node) {
  if(node.material) return area(node.box)*(0.25+Math.sqrt(mean(node.material.variance))/255);
  const advanceArea=unionArea(node.fragments.length?node.fragments:[node.box]);
  return Math.max(1,advanceArea*(node.font.weight/400)**.35*Math.log1p(contrast(node.color,node.background)));
}
function pairBounds(a,b){const x=Math.min(a.box.x,b.box.x),y=Math.min(a.box.y,b.box.y);return {x,y,width:Math.max(a.box.x+a.box.width,b.box.x+b.box.width)-x,height:Math.max(a.box.y+a.box.height,b.box.y+b.box.height)-y};}
function counterweight(a,b) {
  const m=textMass(a),n=textMass(b),ac=center(a.box),bc=center(b.box),bounds=pairBounds(a,b),mid=center(bounds);
  return Math.hypot((ac[0]*m+bc[0]*n)/(m+n)-mid[0],(ac[1]*m+bc[1]*n)/(m+n)-mid[1])/Math.max(1,Math.hypot(bounds.width,bounds.height));
}
function cue(relation,nodes,semantic,p,scales) {
  const [a,b]=relation.nodes.map(id=>nodes.get(id)),[sa,sb]=relation.nodes.map(id=>semantic.get(id));
  const gap=separation(a.box,b.box),unit=Math.min(a.font.size,b.font.size),sizeRatio=Math.log(a.font.size/b.font.size);
  const priority=sa.priority-sb.priority,paint=colorDistance(a.material?.mean??a.color,b.material?.mean??b.color);
  const typeShape=geometric(a.font.fingerprint.map((x,i)=>affinity(x,b.font.fingerprint[i],scales.identitySize)));
  const identity=geometric([affinity(sizeRatio,0,scales.identitySize),affinity(Math.log(a.font.weight/b.font.weight),0,scales.identityWeight),affinity(paint,0,scales.identityColor),typeShape]);
  const target=Math.log(p.hierarchy)*priority;
  const distinction=affinity(sizeRatio,target,p.hierarchyScale);
  let channels;
  switch(relation.kind) {
    case 'same-role':channels={identity};break;
    case 'supports':channels={grouping:affinity(Math.log1p(gap/unit),Math.log1p(p.grouping),p.groupingScale),distinction,paint:affinity(paint,a.material||b.material?p.materialDistance:0,scales.material)};break;
    case 'contrasts':channels={distinction:affinity(Math.abs(sizeRatio),Math.log(p.hierarchy)*Math.max(.4,Math.abs(priority)),p.hierarchyScale),paint:affinity(paint,p.materialDistance,scales.material)};break;
    case 'aligns': {
      const distances=[Math.abs(a.box.x-b.box.x),Math.abs(a.box.x+a.box.width-b.box.x-b.box.width),Math.abs(center(a.box)[0]-center(b.box)[0])];
      channels={alignment:affinity(Math.min(...distances)/Math.max(1,a.box.width,b.box.width),0,scales.alignment)};break;
    }
    case 'sequence': {
      const ac=center(a.box),bc=center(b.box),axis=Math.abs(bc[0]-ac[0])>Math.abs(bc[1]-ac[1])?0:1;
      channels={order:bc[axis]>=ac[axis]?1:0,interval:affinity(Math.log1p(gap/unit),Math.log1p(p.grouping*relation.transition),p.recurrenceScale)};break;
    }
    case 'counterweight':channels={counterweight:affinity(counterweight(a,b),p.counterweight,p.counterweightScale),material:affinity(paint,p.materialDistance,scales.material)};break;
    default:check(false,'CUE','Unsupported cue contract.');
  }
  return {id:relation.id,kind:relation.kind,nodes:relation.nodes,value:geometric(Object.values(channels)),channels,descriptors:{gap,unit,sizeRatio,paint,identity,distinction,counterweight:counterweight(a,b)},method:'typed geometry and declared optical-mass proxy; no perceptual model'};
}
function conditionFeatures(context,program,observation) {
  const p=context.model.perspectives[context.brief.intent.perspective],s=scope(context,observation.condition.state);
  const semantic=new Map(context.brief.nodes.map(n=>[n.id,n])),nodes=new Map(observation.nodes.map(n=>[n.id,n]));
  const missing=[],functional=[];
  if(new Set(observation.nodes.map(n=>n.id)).size!==observation.nodes.length) missing.push('duplicated bound node');
  if(observation.document.width>observation.viewport.width+1)functional.push('horizontal overflow');
  if(observation.fontsStatus!=='loaded')missing.push('fonts not ready');
  for(const g of context.brief.groups.filter(g=>!s.hidden.includes(g.id)))if(!observation.groups.some(a=>a.id===g.id&&a.visible))missing.push(`${g.id}: semantic region missing`);
  for(const n of s.nodes) {
    const actual=nodes.get(n.id);
    if(!actual?.visible){missing.push(`${n.id}: absent visible content`);continue;}
    if(actual.unsupported.length)missing.push(`${n.id}: ${actual.unsupported.join(', ')}`);
    if(n.kind==='image'&&actual.material?.status!=='measured')missing.push(`${n.id}: material pixels unavailable`);
    if(!Array.isArray(actual.font.fingerprint)||actual.font.fingerprint.length!==3||!Number.isFinite(actual.font.inkDensity))missing.push(`${n.id}: type-shape observation unavailable`);
    if(n.kind==='image'&&actual.text!==context.assets.find(a=>a.id===n.asset).alt)missing.push(`${n.id}: material meaning/alt text changed`);
    if(n.kind!=='image'&&actual.text!==n.text)missing.push(`${n.id}: content changed`);
    if(n.kind==='action'&&actual.href!==n.href)functional.push(`${n.id}: action binding changed`);
    if(actual.clipped)functional.push(`${n.id}: clipped content`);
    if(n.kind!=='image'&&contrast(actual.color,actual.background)<(actual.font.size>=24||actual.font.size>=18.66&&actual.font.weight>=700?3:4.5))functional.push(`${n.id}: text contrast`);
    if(n.kind==='action'&&actual.box.height<44)functional.push(`${n.id}: action target below declared 44px minimum`);
    for(const v of [actual.box.x,actual.box.y,actual.box.width,actual.box.height,actual.font.size,actual.font.weight])finite(v,'observed descriptor');
  }
  if(missing.length)return {condition:observation.condition,active:s.active,status:'incomplete',missing,functional,features:null};
  const rows=s.relations.map(r=>cue(r,nodes,semantic,p,context.model.scales)),byID=new Map(rows.map(r=>[r.id,r]));
  const features={},detail={};
  const store=(id,value,description)=>{if(s.active[id]){check(value!==null&&Number.isFinite(value),'FEATURE',`${id} could not be computed.`);features[id]=value;detail[id]=description;}};
  store('APH-01',mean(rows.map(r=>r.value)),{relations:rows.map(r=>r.id)});
  const identity=mean(rows.filter(r=>r.kind==='same-role').map(r=>r.value)),distinct=mean(rows.filter(r=>['supports','contrasts'].includes(r.kind)).map(r=>r.descriptors.distinction));
  store('APH-02',identity!==null&&distinct!==null?identity*distinct:null,{identity,distinction:distinct});
  const chords=s.support.map(r=>{
    const [a,b]=r.nodes.map(id=>nodes.get(id)),gap=separation(a.box,b.box),h=a.font.size,body=b.font.size;
    const observed=Math.log(Math.max(gap,1e-6)/body),target=Math.log(p.gapBase)+p.elasticity*Math.log(h/body);
    return {relation:r.id,observed,target,residual:observed-target,value:affinity(observed,target,p.gapScale)};
  });
  store('APH-03',mean(chords.map(x=>x.value)),{chords});
  const groups=[];
  for(const g of context.brief.groups.filter(g=>!s.hidden.includes(g.id))) {
    const observationGroup=observation.groups.find(x=>x.id===g.id);if(!observationGroup?.visible)continue;
    const inside=n=>{let id=n.group;while(id){if(id===g.id)return true;id=context.brief.groups.find(x=>x.id===id)?.parent;}return false;};
    const members=s.nodes.filter(inside).map(n=>nodes.get(n.id));if(members.length<2)continue;
    const foreground=unionArea(members.flatMap(n=>n.material?[n.box]:n.fragments.length?n.fragments:[n.box]));
    const ground=clamp(1-foreground/Math.max(1,area(observationGroup.box)),0,1);
    const inner=rows.filter(r=>r.nodes.every(id=>members.some(n=>n.id===id))).map(r=>r.value);
    groups.push({group:g.id,foreground,boxArea:area(observationGroup.box),clearance:ground,value:affinity(ground,p.clearance,p.clearanceScale)*(mean(inner)??1)});
  }
  // A multi-region page with only singleton groups uses its semantic page field.
  if(s.active['APH-04']&&!groups.length){const rects=s.nodes.flatMap(n=>{const v=nodes.get(n.id);return v.material?[v.box]:v.fragments.length?v.fragments:[v.box];});const foreground=unionArea(rects),ground=1-foreground/(observation.viewport.width*observation.document.height);groups.push({group:'page',foreground,clearance:ground,value:affinity(ground,p.clearance,p.clearanceScale)*mean(rows.map(r=>r.value))});}
  store('APH-04',mean(groups.map(g=>g.value)),{groups,method:'exact rectangle-union complement; text fragments approximate occupied shape'});
  const counter=rows.filter(r=>['supports','counterweight'].includes(r.kind)).map(r=>{const [a,b]=r.nodes.map(id=>nodes.get(id));const mass=Math.log(textMass(a)/textMass(b));const priority=semantic.get(r.nodes[0]).priority-semantic.get(r.nodes[1]).priority;return {relation:r.id,mass,weight:r.descriptors.counterweight,value:geometric([affinity(mass,Math.log(p.massRatio)*Math.sign(priority),p.massScale),affinity(r.descriptors.counterweight,p.counterweight,p.counterweightScale)])};});
  store('APH-05',mean(counter.map(x=>x.value)),{counter,method:'fragment area, font weight, contrast and raster variance proxy'});
  const recurrence=rows.filter(r=>['same-role','sequence'].includes(r.kind));
  store('APH-06',mean(recurrence.map(x=>x.value)),{trajectory:recurrence.map(x=>({id:x.id,value:x.value}))});
  const materials=s.nodes.map(n=>{
    const a=nodes.get(n.id),palette=a.material?.palette;
    const materialAffinity=palette?Math.max(...palette.map(bin=>affinity(colorDistance(bin.rgb,rgb(context.brief.frame.accent)),p.materialDistance,context.model.scales.material))):affinity(colorDistance(a.color,a.background),colorDistance(rgb(context.brief.frame.ink),rgb(context.brief.frame.paper)),context.model.scales.material);
    const curve=a.radius/Math.max(1,a.font.size),stroke=a.stroke/Math.max(1,a.font.size);
    const shape=n.kind==='action'||n.kind==='image'?affinity(curve,p.curvature,context.model.scales.shape):1;
    const connectedMaterial=s.relations.filter(r=>r.nodes.includes(n.id)).flatMap(r=>r.nodes.filter(id=>id!==n.id)).map(id=>nodes.get(id)).find(x=>x.material);
    const ink=affinity(a.font.inkDensity,p.typeInkDensity,context.model.scales.shape);
    const texture=connectedMaterial?affinity(a.font.inkDensity-connectedMaterial.material.edge,p.inkTextureOffset,context.model.scales.material):1;
    return {node:n.id,palette:materialAffinity,curvature:curve,stroke,inkDensity:a.font.inkDensity,texture:a.material?.edge??null,textureRelation:texture,value:product([materialAffinity,shape,ink,texture])};
  });
  store('APH-07',mean(materials.map(x=>x.value)),{materials,semanticSource:context.brief.intent.source,intention:context.brief.intent.perspective});
  const hyper=s.constellations.map(h=>({id:h.id,relations:h.relations,values:h.relations.map(id=>byID.get(id).value)})).map(h=>({...h,value:product(h.values)}));
  store('APH-08',mean(hyper.map(x=>x.value)),{configurations:hyper,arity:3});
  const voids=rows.map(r=>{const [a,b]=r.nodes.map(id=>nodes.get(id));return {id:`void-${r.id}`,kind:'void',adjacent:r.nodes,clearance:separation(a.box,b.box),scope:r.id};});
  const baseline=mean(s.nodes.map(n=>{const a=nodes.get(n.id);if(n.kind==='image')return affinity(a.box.width/a.box.height,a.material.natural[0]/a.material.natural[1],.8);return affinity(Math.log(a.font.size/context.brief.frame.bodySize),Math.log(1+2*n.priority),.8);}));
  return {condition:observation.condition,active:s.active,status:'measured',missing,functional,features,detail,relations:rows,voids,partBaseline:baseline};
}
function continuity(context,observations) {
  const p=context.model.perspectives[context.brief.intent.perspective],records=[];
  for(const state of context.brief.states) {
    const relevant=observations.filter(o=>o.condition.state===state),s=scope(context,state);
    if(relevant.length!==context.brief.viewports.length)return {value:null,missing:['missing viewpoint'],records};
    const ref=relevant[0];
    for(const observed of relevant.slice(1)) {
      const ratios=s.relations.filter(r=>['supports','contrasts','same-role'].includes(r.kind)).map(r=>{
        const [ra,rb]=r.nodes.map(id=>ref.nodes.find(n=>n.id===id)),[a,b]=r.nodes.map(id=>observed.nodes.find(n=>n.id===id));
        if(![ra,rb,a,b].every(n=>n?.visible))return null;
        const original=Math.log(ra.font.size/rb.font.size),current=Math.log(a.font.size/b.font.size);
        return {relation:r.id,from:original,to:current,value:affinity(current-original,0,p.continuityScale)};
      });
      if(ratios.some(x=>x===null))return {value:null,missing:['required correspondence missing'],records};
      const membership=s.nodes.every(n=>observed.nodes.some(a=>a.id===n.id&&a.visible));
      const regions=context.brief.groups.filter(g=>!s.hidden.includes(g.id)).map(g=>{
        const members=s.nodes.filter(n=>n.group===g.id);if(!members.length)return null;
        const fraction=o=>{const all=s.nodes.map(n=>o.nodes.find(a=>a.id===n.id)),selected=members.map(n=>o.nodes.find(a=>a.id===n.id));return selected.reduce((sum,n)=>sum+textMass(n),0)/all.reduce((sum,n)=>sum+textMass(n),0);};
        const before=fraction(ref),after=fraction(observed);return {group:g.id,from:before,to:after,value:affinity(Math.log(after/before),0,p.continuityScale)};
      }).filter(Boolean);
      records.push({from:ref.condition.id,to:observed.condition.id,membership,ratios,regions,value:membership?geometric([mean(ratios.map(r=>r.value))??1,mean(regions.map(r=>r.value))??1]):0});
    }
  }
  return {value:mean(records.map(r=>r.value)),missing:[],records};
}
export function evaluate(context,program,observationSet,{objective='full'}={}) {
  validateContext(context);validateProgram(context,program);check(['full','pairs','parts'].includes(objective),'OBJECTIVE','Choose full, pairs, or parts.');
  check(observationSet.programDigest===program.digest&&observationSet.contextDigest===context.digest,'STALE_OBSERVATION','Observation belongs to a different program.');
  const expected=context.brief.viewports.flatMap(v=>context.brief.states.map(s=>`${v.id}-${s}`));
  const ids=observationSet.observations.map(o=>o.condition.id);
  check(new Set(ids).size===ids.length&&ids.every(id=>expected.includes(id)),'CONDITIONS','Duplicate or undeclared conditions.');
  for(const o of observationSet.observations) {
    check(o.method===context.descriptorVersion&&o.programDigest===program.digest&&o.contextDigest===context.digest,'OBSERVATION_PROVENANCE','A condition has a different method or provenance.');
    const v=context.brief.viewports.find(v=>v.id===o.condition.viewport);
    check(v&&o.condition.id===`${v.id}-${o.condition.state}`&&o.viewport.width===v.width&&o.viewport.height===v.height,'CONDITION_BINDING','A condition does not match its declared viewport.');
  }
  const absent=expected.filter(id=>!ids.includes(id));
  const conditions=observationSet.observations.map(o=>conditionFeatures(context,program,o));
  const continuityResult=continuity(context,observationSet.observations);
  const incomplete=absent.length>0||conditions.some(c=>c.status==='incomplete')||continuityResult.value===null;
  if(!incomplete)for(const c of conditions) {
    c.features['APH-09']=continuityResult.value;c.detail['APH-09']=continuityResult;
    const eligible=context.model.families.filter(f=>c.active[f.id]);
    const denominator=eligible.reduce((s,f)=>s+f.weight,0);check(denominator>0,'WEIGHTS','No active weighted family.');
    c.weights=Object.fromEntries(eligible.map(f=>[f.id,f.weight/denominator]));
    c.full=eligible.reduce((s,f)=>s+c.features[f.id]*f.weight/denominator,0);
    const pairIDs=['APH-01','APH-03','APH-05'];c.pairs=mean(pairIDs.filter(id=>c.active[id]).map(id=>c.features[id]));
    c.selectedValue=objective==='full'?c.full:objective==='pairs'?c.pairs:c.partBaseline;
    if(c.selectedValue===null)c.status='incomplete';
  }
  const functional=conditions.flatMap(c=>c.functional.map(message=>({condition:c.condition.id,message})));
  const ready=!incomplete&&conditions.every(c=>c.selectedValue!==null&&c.status==='measured');
  return {schema:1,contextDigest:context.digest,modelDigest:context.modelDigest,programDigest:program.digest,observationDigest:digest(observationSet),
    status:ready?'measured':'incomplete',objective,selectionValue:ready?Math.min(...conditions.map(c=>c.selectedValue)):null,
    meanValue:ready?mean(conditions.map(c=>c.selectedValue)):null,eligible:ready&&functional.length===0,
    support:context.model.support,claim:'within-context perspective prediction; no absolute beauty scale',absent,functional,conditions,continuity:continuityResult};
}
