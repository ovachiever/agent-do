import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {check, keys, text, finite, unique, clone, digest, read, fileHash, bytesHash} from './core.js';
import {rgb, contrast} from './math.js';

export const ROOT=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
export const engineIdentity=()=>digest(Object.fromEntries(fs.readdirSync(path.join(ROOT,'src')).filter(n=>n.endsWith('.js')).sort().map(n=>[n,fileHash(path.join(ROOT,'src',n))])));
export const ROLES=['brand','display','heading','body','caption','label','value','action','media'];
export const RELATIONS=['supports','same-role','contrasts','aligns','sequence','counterweight'];
export const PRODUCTIONS=['partition','sequence','cluster','field','overlay'];
const id=(v,label)=>{text(v,label,100);check(/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(v),'ID',`${label} must be a stable CSS-safe ID.`);};
export function loadModel(file=path.join(ROOT,'models/perspectives-v1.json')) {
  const m=read(file); validateModel(m); return m;
}
export function validateModel(m) {
  keys(m,['schema','id','status','authority','descriptorVersion','knownFailures','families','perspectives','scales','controls','support','development','fit'],'model');
  check(m.schema===1 && m.descriptorVersion==='aphrodite-observation-1','MODEL_VERSION','Unsupported model.');
  id(m.id,'model.id'); text(m.authority,'model.authority');
  check(['proposed','fitted','adopted'].includes(m.status),'MODEL_STATUS','Unknown model status.');
  check(m.families?.length===9,'FAMILIES','All nine family definitions are required.'); unique(m.families);
  for(let i=1;i<=9;i++) {
    const f=m.families.find(x=>x.id===`APH-0${i}`);check(f,'FAMILY','Missing law family.');finite(f.weight,'family weight',0,1);text(f.operator,'family operator');
  }
  check(Math.abs(m.families.reduce((s,f)=>s+f.weight,0)-1)<1e-8,'WEIGHTS','Family weights must sum to one.');
  const required=['gapBase','elasticity','gapScale','hierarchy','hierarchyScale','grouping','groupingScale','clearance','clearanceScale','counterweight','counterweightScale','recurrenceScale','surfaceMix','typeContrast','curvature','materialDistance','massRatio','massScale','continuityScale','typeInkDensity','inkTextureOffset'];
  check(Object.keys(m.perspectives??{}).length>0,'PERSPECTIVES','No perspectives.');
  for(const [name,p] of Object.entries(m.perspectives)) {
    id(name,'perspective');keys(p,['reading','source',...required],name);text(p.reading,'perspective reading');text(p.source,'perspective source');
    required.forEach(k=>finite(p[k],k,k==='elasticity'?-2:0,k==='elasticity'?2:20));
    required.filter(k=>k.endsWith('Scale')||['gapBase','hierarchy','grouping','massRatio'].includes(k)).forEach(k=>finite(p[k],k,Number.MIN_VALUE));
  }
  for(const name of ['identitySize','identityColor','identityWeight','alignment','material','shape']) finite(m.scales[name],name,Number.MIN_VALUE,10);
  check(Object.keys(m.controls).sort().join(',')==='balance,character,presence,scale,tempo','CONTROLS','Use the supported shared controls.');
  for(const c of Object.values(m.controls)) {finite(c.min,'control minimum');finite(c.max,'control maximum',c.min);finite(c.default,'control default',c.min,c.max);}
  check(m.support && ['model-guided exploration','calibrated domain'].includes(m.support.claim),'SUPPORT','Declare model support.');
  return m;
}
export function validateBrief(input, model) {
  const b=clone(input);
  keys(b,['schema','id','title','lang','author','intent','frame','groups','nodes','relations','constellations','assets','viewports','states','copyBudget'],'brief');
  check(b.schema===1,'BRIEF_VERSION','Brief schema must be 1.');id(b.id,'brief.id');text(b.title,'title',200);text(b.author,'author',300);
  b.lang??='en';check(/^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$/.test(b.lang),'LANGUAGE','Invalid document language.');
  keys(b.intent,['perspective','reading','source'],'intent');check(model.perspectives[b.intent.perspective],'UNBOUND_PERSPECTIVE','Choose an implemented perspective.');text(b.intent.reading,'intent reading');text(b.intent.source,'intent source');
  keys(b.frame,['paper','ink','accent','displayFont','bodyFont','bodySize','maxWidth','border','radius'],'frame');
  for(const k of ['paper','ink','accent']) rgb(b.frame[k]);
  for(const k of ['displayFont','bodyFont']) {text(b.frame[k],k,160);check(/^[A-Za-z0-9 ,'-]+$/.test(b.frame[k]),'FONT','Supply CSS family names, not CSS declarations.');}
  finite(b.frame.bodySize,'bodySize',16,24);finite(b.frame.maxWidth,'maxWidth',640,1920);
  b.frame.border??=1;b.frame.radius??=8;finite(b.frame.border,'border',0,8);finite(b.frame.radius,'radius',0,64);
  check(contrast(rgb(b.frame.paper),rgb(b.frame.ink))>=4.5,'TEXT_CONTRAST','The supplied body ink and paper need readable contrast.');
  check(Array.isArray(b.groups)&&b.groups.length>0&&b.groups.length<=80,'GROUPS','Supply 1 to 80 semantic groups.');unique(b.groups);
  const groups=new Map(b.groups.map(g=>[g.id,g]));
  for(const g of b.groups) {
    keys(g,['id','parent','kind','title','productions','surface','order','trajectory','anchor'],'group');id(g.id,'group.id');g.parent??=null;
    check(g.parent===null||groups.has(g.parent),'GROUP_PARENT','Unknown group parent.');
    g.kind??='section';check(['section','header','footer','article','disclosure','nav'].includes(g.kind),'GROUP_KIND','Unsupported semantic group kind.');
    if(g.kind==='disclosure') text(g.title,'disclosure summary',200);
    g.productions??=['cluster','sequence','partition'];check(Array.isArray(g.productions)&&g.productions.length>0&&g.productions.every(x=>PRODUCTIONS.includes(x)),'PRODUCTION','Unknown production.');
    g.surface??='paper';check(['paper','tint','accent','ink'].includes(g.surface),'SURFACE','Unsupported surface relation.');
    g.order??=0;finite(g.order,'group order');
    g.trajectory??=1;finite(g.trajectory,'trajectory',0.5,1.6);
    const seen=new Set([g.id]);let p=g.parent;
    while(p!==null) {check(!seen.has(p),'GROUP_CYCLE','Group containment must be acyclic.');seen.add(p);p=groups.get(p).parent??null;}
  }
  check(Array.isArray(b.nodes)&&b.nodes.length>1&&b.nodes.length<=200,'NODES','Supply 2 to 200 meaningful nodes.');unique(b.nodes);
  const nodes=new Map(b.nodes.map(n=>[n.id,n]));
  check(b.nodes.every(n=>!groups.has(n.id)),'ID_COLLISION','Node and group IDs must differ.');
  b.assets??=[]; unique(b.assets); const assets=new Map(b.assets.map(a=>[a.id,a]));
  for(const a of b.assets) {keys(a,['id','path','alt','source','sha256'],'asset');id(a.id,'asset.id');text(a.path,'asset.path');text(a.source,'asset.source');text(a.alt,'asset.alt');}
  for(const n of b.nodes) {
    keys(n,['id','kind','role','group','text','href','asset','priority','order','required','level'],'node');id(n.id,'node.id');
    check(['text','image','action'].includes(n.kind),'NODE_KIND','Use text, image or action terminals.');
    check(ROLES.includes(n.role),'ROLE','Unknown role; explicitly bind it to a supported visual role.');
    check(groups.has(n.group),'NODE_GROUP','Node has no semantic group.');n.priority??=n.role==='display'?1:n.role==='heading'?0.65:0.25;finite(n.priority,'priority',0,1);
    n.order??=0;finite(n.order,'node order');n.required??=true;check(typeof n.required==='boolean','REQUIRED','required is boolean.');
    if(n.kind==='image') {check(assets.has(n.asset),'ASSET_BINDING','Image needs an existing material asset.');check(n.role==='media','MEDIA_ROLE','Image role is media.');}
    else text(n.text,`node ${n.id} content`);
    if(n.kind==='action') {text(n.href,'action href');check(/^(https?:\/\/|mailto:|tel:|#[A-Za-z][\w-]*)/.test(n.href),'ACTION','Action must bind a real destination.');check(!/[\s"<>]/.test(n.href),'ACTION','Invalid action URL.');}
    if(n.href?.startsWith('#')) check(nodes.has(n.href.slice(1))||groups.has(n.href.slice(1)),'ACTION_TARGET','Internal action target does not exist.');
    if(n.level!==undefined) finite(n.level,'heading level',1,6);
  }
  check(b.nodes.some(n=>n.required&&['display','heading','value'].includes(n.role)),'LEAD','A composition needs an explicit meaningful lead.');
  for(const g of b.groups) {check(b.nodes.some(n=>n.group===g.id)||b.groups.some(x=>x.parent===g.id),'EMPTY_GROUP','Empty aesthetic groups are not scoring nodes.');if(g.anchor) check(nodes.get(g.anchor)?.group===g.id,'ANCHOR','Field anchor must be a direct member.');}
  check(Array.isArray(b.relations)&&b.relations.length>0,'RELATIONS','Supply explicit typed relationships.');unique(b.relations);
  const signatures=new Set();
  for(const r of b.relations) {
    keys(r,['id','kind','nodes','source','transition'],'relation');id(r.id,'relation.id');check(RELATIONS.includes(r.kind),'RELATION_KIND','Unknown relation kind.');
    check(r.nodes?.length===2&&r.nodes[0]!==r.nodes[1]&&r.nodes.every(x=>nodes.has(x)),'RELATION_NODES','A typed pair needs two distinct existing nodes.');
    text(r.source,'relation source'); const signature=`${r.kind}:${['same-role','aligns','counterweight'].includes(r.kind)?[...r.nodes].sort().join(','):r.nodes.join(',')}`;
    check(!signatures.has(signature),'DUPLICATE_RELATION','Duplicated relationships cannot inflate the objective.');signatures.add(signature);
    if(r.kind==='same-role') check(nodes.get(r.nodes[0]).role===nodes.get(r.nodes[1]).role,'ROLE_CONTRACT','same-role requires equal roles.');
    r.transition??=1;finite(r.transition,'sequence transition',0.25,4);
  }
  b.constellations??=[];unique(b.constellations); const relationMap=new Map(b.relations.map(r=>[r.id,r]));const hyperSignatures=new Set();
  for(const h of b.constellations) {
    keys(h,['id','relations','source'],'constellation');id(h.id,'constellation.id');text(h.source,'constellation source');
    check(h.relations?.length===3&&new Set(h.relations).size===3&&h.relations.every(x=>relationMap.has(x)),'CONSTELLATION','Exactly three distinct declared relations are required.');
    const members=new Set(h.relations.flatMap(x=>relationMap.get(x).nodes));check(members.size>=3,'CONSTELLATION_ARITY','A constellation needs at least three parts.');
    const signature=[...h.relations].sort().join(',');check(!hyperSignatures.has(signature),'DUPLICATE_CONSTELLATION','Do not duplicate a constellation.');hyperSignatures.add(signature);
  }
  b.viewports??=[{id:'wide',width:1440,height:1000},{id:'narrow',width:390,height:844}];unique(b.viewports);
  check(b.viewports.length>=2&&b.viewports.length<=5,'VIEWPOINTS','Declare 2 to 5 viewports for continuity.');
  for(const v of b.viewports) {keys(v,['id','width','height'],'viewport');id(v.id,'viewport.id');finite(v.width,'width',320,2560);finite(v.height,'height',480,1600);}
  b.states??=['base',...(b.groups.some(g=>g.kind==='disclosure')?['expanded']:[])];
  check(b.states.includes('base')&&b.states.every(s=>['base','expanded'].includes(s))&&new Set(b.states).size===b.states.length,'STATES','States are base and expanded.');
  check(!b.groups.some(g=>g.kind==='disclosure')||b.states.includes('expanded'),'DISCLOSURE_STATE','Disclosures require an expanded observation.');
  if(b.copyBudget!==undefined) {finite(b.copyBudget,'copyBudget',1,30000); const words=b.nodes.filter(n=>n.kind!=='image').map(n=>n.text).concat(b.groups.filter(g=>g.kind==='disclosure').map(g=>g.title)).join(' ').trim().split(/\s+/).length;check(words<=b.copyBudget,'COPY_BUDGET','Required content exceeds the declared word budget.',{words,budget:b.copyBudget});}
  return b;
}
function validateMaterial(bytes,mime) {
  const svg=bytes.toString('utf8');
  const valid=mime==='image/svg+xml'?/<svg[\s>]/i.test(svg):mime==='image/png'?bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])):mime==='image/jpeg'?bytes[0]===255&&bytes[1]===216&&bytes[2]===255:mime==='image/webp'?bytes.subarray(0,4).toString()==='RIFF'&&bytes.subarray(8,12).toString()==='WEBP':false;
  check(valid,'ASSET_TYPE','Material bytes must match their declared image format.');
  if(mime==='image/svg+xml') check(!/<(?:script|style|foreignObject|iframe|image|use|animate\w*|set)\b|\bon\w+\s*=|(?:href|url)\s*[=(]|<!ENTITY|<!DOCTYPE|@import/i.test(svg.replace(/url\(#[A-Za-z][\w-]*\)/g,'')),'ACTIVE_SVG','SVG material must be self-contained passive shapes.');
}
export function materializeAssets(brief, base) {
  return brief.assets.map(a=>{
    const file=path.resolve(base,a.path);check(fs.existsSync(file)&&fs.statSync(file).isFile(),'MISSING_ASSET','Supply the real material file.',{asset:a.id,path:file});
    check(fs.statSync(file).size<=16*1024*1024,'ASSET_SIZE','Assets are limited to 16 MiB.');
    const ext=path.extname(file).toLowerCase(), mime={'.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}[ext];
    check(mime,'ASSET_TYPE','Use local SVG, PNG, JPEG or WebP material.');
    const bytes=fs.readFileSync(file);
    validateMaterial(bytes,mime);
    const hash=fileHash(file);if(a.sha256) check(a.sha256===hash,'ASSET_CHANGED','Asset hash does not match its declared binding.',{asset:a.id});
    return {id:a.id,source:a.source,alt:a.alt,sha256:hash,mime,data:bytes.toString('base64')};
  });
}
export function bind(input,model,assets) {
  validateModel(model);
  const brief=validateBrief(input,model);
  const expected=new Set(brief.assets.map(a=>a.id));check(assets.length===expected.size&&assets.every(a=>expected.has(a.id)),'ASSETS','Material inventory mismatch.');unique(assets);
  for(const asset of assets) {
    const declared=brief.assets.find(a=>a.id===asset.id);
    check(typeof asset.data==='string'&&asset.data.length<=Math.ceil(16*1024*1024/3)*4,'ASSET_SIZE','Embedded material is missing or exceeds 16 MiB.');
    const bytes=Buffer.from(asset.data,'base64');validateMaterial(bytes,asset.mime);
    check(bytes.toString('base64')===asset.data&&bytesHash(bytes)===asset.sha256,'ASSET_CHANGED','Embedded material must match its content hash.');
    check(asset.source===declared.source&&asset.alt===declared.alt&&(!declared.sha256||declared.sha256===asset.sha256),'ASSET_BINDING','Embedded material must match its declared meaning and source.');
  }
  const domainDigest=digest({brief,assets:assets.map(a=>({id:a.id,sha256:a.sha256}))});
  const context={schema:1,brief,assets,domainDigest,model:clone(model),modelDigest:digest(model),descriptorVersion:model.descriptorVersion};
  context.digest=digest(context);return context;
}
export function validateContext(c) {
  const {digest:stored,...payload}=c;check(digest(payload)===stored,'CONTEXT_CHANGED','Context has changed. Bind a new context.');
  check(digest(c.model)===c.modelDigest,'MODEL_CHANGED','Frozen model changed.');
  check(bind(c.brief,c.model,c.assets).digest===c.digest,'CONTEXT_BINDING','Context must exactly bind its model, semantic domain and material bytes.');return c;
}
