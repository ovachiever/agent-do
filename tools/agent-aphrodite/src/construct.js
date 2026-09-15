import {check, clone, digest, keyed, clamp, finite} from './core.js';
import {validateContext,engineIdentity} from './contracts.js';
import {affineSpace, instantiate, residual, mix} from './math.js';

export const GRAMMAR_VERSION='aphrodite-grammar-1';
export const productionCatalog=[
  ['GR-01','Page -> semantic regions'],['GR-02','Region -> complementary partition'],
  ['GR-03','Region -> ordered sequence'],['GR-04','Region -> lead and support cluster'],
  ['GR-05','Region -> anchor and satellites'],['GR-06','Region -> material and foreground overlay'],
  ['GR-07','Role -> real content terminal'],['GR-08','Identity -> coordinated role treatments'],
  ['GR-09','Condition -> content-preserving reflow']
];
export function controls(context, supplied={}) {
  const declared=context.model.controls, out={};
  check(Object.keys(supplied).every(k=>declared[k]),'INDEPENDENT_CSS','Change a named relationship control, not an independent CSS property.');
  for(const [k,c] of Object.entries(declared)) out[k]=finite(supplied[k]??c.default,k,c.min,c.max);
  return out;
}
export function frame(context, z, narrow=false) {
  const p=context.model.perspectives[context.brief.intent.perspective], f=context.brief.frame;
  const body=f.bodySize*z.scale, display=body*p.hierarchy*z.presence*(narrow?0.78:1.3);
  // log(g/b) = log(gapBase*tempo) + elasticity*log(h/b).
  // Body and display are free coordinates; the gap follows the affine family.
  const matrix=[[p.elasticity-1,-p.elasticity,1]], rhs=[Math.log(p.gapBase*z.tempo)];
  const space=affineSpace(matrix,rhs);
  // RREF may choose any pivot; derive the complete solution then verify its coordinates.
  const x=[Math.log(body),Math.log(display),Math.log(body*p.gapBase*z.tempo*(display/body)**p.elasticity)];
  const recovered=instantiate(space,space.free.map(i=>x[i]));
  check(residual(matrix,rhs,recovered)<1e-9,'CONSTRUCTION','Shared chord is inconsistent.');
  const gap=Math.exp(recovered[2]), heading=body*(1.25+z.presence*.5), interval=body*(1.1+z.tempo*.8);
  return {body,display,gap,heading,interval,outer:interval*(narrow?2:3.2),
    radius:f.radius*(0.25+z.character*1.5),stroke:f.border*(0.6+z.character*1.2),
    displayWeight:Math.round(400+300*z.character*p.typeContrast),
    tint:mix(f.paper,f.accent,clamp(p.surfaceMix*(0.6+z.character),0,0.25)),
    exact:{matrix,rhs,coordinates:x,space,residual:residual(matrix,rhs,x),claim:'affine log-dimension relation only'}};
}
function children(context, group) {
  return [...context.brief.groups.filter(g=>g.parent===group.id).map(g=>({id:g.id,kind:'group',order:g.order})),
    ...context.brief.nodes.filter(n=>n.group===group.id).map(n=>({id:n.id,kind:n.kind,order:n.order}))]
    .sort((a,b)=>a.order-b.order||a.id.localeCompare(b.id));
}
function applicable(group, parts) {
  if(['header','footer','nav'].includes(group.kind)) return ['sequence'];
  return group.productions.filter(p=>{
    if(p==='overlay') return parts.some(x=>x.kind==='image')&&parts.some(x=>x.kind!=='image')&&!parts.some(x=>x.kind==='group');
    if(p==='field') return parts.length>=3;
    if(p==='partition') return parts.length>=2;
    return true;
  });
}
export function derive(context, seed='0', index=0, supplied={}, overrides={}) {
  validateContext(context);const z=controls(context,supplied),choices=[],regions=[];
  check(Object.keys(overrides).every(id=>context.brief.groups.some(g=>g.id===id)),'TOPOLOGY_BINDING','Topology proposal names an unknown group.');
  for(const g of context.brief.groups) {
    const parts=children(context,g), options=applicable(g,parts);
    check(options.length>0,'NO_DERIVATION','No production meets this group\'s obligations.',{group:g.id});
    const stream=keyed(context.modelDigest,context.digest,String(seed),GRAMMAR_VERSION,g.id,'production');
    const chosen=overrides[g.id]??options[(Math.floor(stream*options.length)+index)%options.length];
    check(options.includes(chosen),'PRODUCTION','Proposed topology cannot satisfy this region\'s obligations.');
    let lanes=[parts.map(x=>x.id)];
    if(['partition','overlay'].includes(chosen)) {
      const material=parts.filter(x=>x.kind==='image'), others=parts.filter(x=>x.kind!=='image');
      if(material.length && others.length) lanes=[others.map(x=>x.id),material.map(x=>x.id)];
      else {const split=Math.max(1,Math.min(parts.length-1,Math.round(parts.length*z.balance)));lanes=[parts.slice(0,split).map(x=>x.id),parts.slice(split).map(x=>x.id)];}
    }
    if(chosen==='field'&&g.anchor) lanes=[[g.anchor,...parts.map(x=>x.id).filter(id=>id!==g.anchor)]];
    choices.push({id:`${g.id}/production`,options,chosen,source:'bounded grammar expansion'});
    regions.push({id:g.id,production:chosen,lanes,children:parts.map(x=>x.id),anchor:g.anchor??parts[0].id});
  }
  const topology={regions,roots:context.brief.groups.filter(g=>g.parent===null).sort((a,b)=>a.order-b.order||a.id.localeCompare(b.id)).map(g=>g.id)};
  const frames={wide:frame(context,z),narrow:frame(context,z,true)};
  const program={schema:1,version:GRAMMAR_VERSION,engineDigest:engineIdentity(),contextDigest:context.digest,modelDigest:context.modelDigest,seed:String(seed),index,z,overrides,topology,frames,choices,
    termination:{expandedRegions:regions.length,terminals:context.brief.nodes.length,maxDepth:context.brief.groups.length,decorationExpansions:0},
    dependencies:dependencyGraph(context)};
  program.digest=digest(program);return program;
}
export function validateProgram(context,p) {
  const {digest:hash,...rest}=p;check(digest(rest)===hash,'PROGRAM_CHANGED','Program changed outside the relationship transform.');
  check(p.engineDigest===engineIdentity(),'ENGINE_CHANGED','Use the frozen engine included with this run to replay it; this engine version differs.');
  check(p.contextDigest===context.digest && p.modelDigest===context.modelDigest,'STALE_PROGRAM','Program does not belong to this context/model.');
  const reconstructed=derive(context,p.seed,p.index,p.z,p.overrides);
  check(reconstructed.digest===p.digest,'INVALID_DERIVATION','The saved program is not a valid derivation under this engine.');
  return p;
}
export function dependencyGraph(context) {
  const tokens={presence:['display','heading','gap','partition'],tempo:['gap','interval','outer'],balance:['partition','counterweight'],character:['radius','stroke','tint','displayWeight'],scale:['body','display','heading','gap','interval','outer','radius']};
  const graph={};for(const [key,names] of Object.entries(tokens)) graph[`control:${key}`]=names.map(n=>`token:${n}`);
  for(const names of Object.values(tokens)) for(const name of names) graph[`token:${name}`]=context.brief.nodes.map(n=>`node:${n.id}`);
  for(const n of context.brief.nodes) graph[`node:${n.id}`]=context.brief.relations.filter(r=>r.nodes.includes(n.id)).map(r=>`relation:${r.id}`).concat(['geometry','material','viewpoints']);
  for(const r of context.brief.relations) graph[`relation:${r.id}`]=['evaluation',...context.brief.constellations.filter(h=>h.relations.includes(r.id)).map(h=>`constellation:${h.id}`)];
  for(const h of context.brief.constellations) graph[`constellation:${h.id}`]=['evaluation'];
  graph.geometry=['evaluation'];graph.material=['evaluation'];graph.viewpoints=['evaluation'];return graph;
}
export function descendants(graph,roots) {
  const seen=new Set(),pending=[...roots];while(pending.length){const id=pending.shift();if(seen.has(id))continue;seen.add(id);pending.push(...(graph[id]??[]));}return [...seen].sort();
}
export function transform(context,program,changes) {
  validateProgram(context,program);const z=controls(context,{...program.z,...changes});
  const changed=Object.keys(z).filter(k=>z[k]!==program.z[k]);check(changed.length,'NO_CHANGE','No shared relationship control changed.');
  const next=derive(context,program.seed,program.index,z,program.overrides);
  return {program:next,receipt:{parent:program.digest,successor:next.digest,changes:changed.map(k=>({control:k,from:program.z[k],to:z[k]})),invalidated:descendants(program.dependencies,changed.map(k=>`control:${k}`)),observation:'required',selection:'stale until observed'}};
}
export function signature(context,program) {
  const groupById=new Map(context.brief.groups.map(g=>[g.id,g]));
  const nodeById=new Map(context.brief.nodes.map(n=>[n.id,n]));
  const shape=id=>nodeById.has(id)?nodeById.get(id).role:`group(${program.topology.regions.find(g=>g.id===id).children.map(shape).join(',')})`;
  return program.topology.regions.map(r=>[groupById.get(r.id).kind,r.production,r.lanes.map(l=>l.map(shape).join(',')).join('|')].join(':')).sort();
}
export function distance(a,b) {const x=new Set(a),y=new Set(b);return 1-[...x].filter(v=>y.has(v)).length/new Set([...x,...y]).size;}
export function proposals(context,{seed='0',budget=8}={}) {
  check(Number.isInteger(budget)&&budget>=1&&budget<=48,'BUDGET','Candidate budget must be 1 to 48.');
  const out=[],seen=new Set(),beam=topologyBeam(context,seed,budget);
  for(let i=0;i<budget;i++) {
    const z={};for(const [key,c] of Object.entries(context.model.controls)) z[key]=i===0?c.default:c.min+keyed(context.digest,String(seed),i,key)*(c.max-c.min);
    const p=derive(context,seed,i,z,beam.choices[i%beam.choices.length]);const h=digest({topology:p.topology,z:p.z});if(!seen.has(h)){seen.add(h);out.push(p);}
  }
  return out;
}
export function topologyBeam(context,seed,width) {
  let beam=[{}];const trace=[];
  for(const g of context.brief.groups) {
    const options=applicable(g,children(context,g));
    const expanded=beam.flatMap(prefix=>options.map(value=>({...prefix,[g.id]:value})));
    // Seeded proposal priority is explicit exploration, never a beauty prediction.
    expanded.sort((a,b)=>keyed(context.digest,seed,'beam',a)-keyed(context.digest,seed,'beam',b));
    beam=expanded.slice(0,width);trace.push({group:g.id,expanded:expanded.length,retained:beam.length,priority:'seeded exploration; not an emission score'});
  }
  return {choices:beam,trace,width};
}
