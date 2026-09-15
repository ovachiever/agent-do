import fs from 'node:fs';
import path from 'node:path';
import {directory,write,read,seal,verify,check,digest,clone,clamp} from './core.js';
import {validateContext,ROOT} from './contracts.js';
import {proposals,transform,signature,distance,validateProgram,topologyBeam} from './construct.js';
import {render} from './render.js';
import {Browser,observe} from './browser.js';
import {evaluate} from './evaluate.js';

export function select(candidates,{archive=[],minimumDistance=0,tolerance=.05}={}) {
  check(minimumDistance>=0&&minimumDistance<=1&&tolerance>=0&&tolerance<=1,'DIVERSITY','Invalid diversity request.');
  const eligible=candidates.filter(c=>c.evaluation.eligible).sort((a,b)=>b.evaluation.selectionValue-a.evaluation.selectionValue||b.evaluation.meanValue-a.evaluation.meanValue||a.program.digest.localeCompare(b.program.digest));
  if(!eligible.length)return {selected:null,reason:'no fully measured functionally eligible candidate'};
  const best=eligible[0].evaluation.selectionValue;
  const near=eligible.filter(c=>c.evaluation.selectionValue>=best-tolerance);
  const distinct=near.filter(c=>archive.every(old=>distance(c.signature,old)>=minimumDistance));
  if(!distinct.length)return {selected:null,reason:'no requested structural distinction inside the declared affinity tolerance',best,eligible:eligible.length};
  return {selected:distinct[0].id,reason:'maximum measured perspective affinity within fixed feasibility and diversity conditions',best,eligible:eligible.length,
    diversity:{minimumDistance,tolerance,archiveEntries:archive.length,distances:archive.map(old=>distance(distinct[0].signature,old))}};
}
export async function compose(context,options) {
  validateContext(context);
  const {out,seed='0',budget=6,steps=0,objective='full',archive=[],minimumDistance=0,tolerance=.05,progress=()=>{}}=options;
  check(Number.isInteger(budget)&&budget>=1&&budget<=48,'BUDGET','The complete run budget must be an integer from 1 to 48.');
  check(['full','pairs','parts'].includes(objective),'OBJECTIVE','Choose full, pairs or parts before observation.');
  check(Number.isFinite(minimumDistance)&&minimumDistance>=0&&minimumDistance<=1&&Number.isFinite(tolerance)&&tolerance>=0&&tolerance<=1,'DIVERSITY','Declare valid diversity conditions before observation.');
  check(Number.isInteger(steps)&&steps>=0&&steps<budget,'STEPS','Refinement steps must be nonnegative and below the total candidate budget.');
  const dir=directory(out),initial=proposals(context,{seed,budget:budget-steps});
  freezeEngine(dir);
  write(path.join(dir,'context.json'),context);
  const request={schema:1,contextDigest:context.digest,modelDigest:context.modelDigest,seed:String(seed),budget,steps,objective,archive,minimumDistance,tolerance};
  write(path.join(dir,'request.json'),request);
  write(path.join(dir,'derivation-beam.json'),topologyBeam(context,seed,budget-steps));
  const browser=new Browser(dir),candidates=[],errors=[];let launched=false;
  async function candidate(program,revision=null) {
    check(digest(context.model)===request.modelDigest,'MODEL_CHANGED','Active model changed during selection.');
    const id=`c${String(candidates.length).padStart(3,'0')}`,dest=path.join(dir,'candidates',id);fs.mkdirSync(dest,{recursive:true});
    write(path.join(dest,'program.json'),program);if(revision)write(path.join(dest,'revision.json'),revision);
    fs.writeFileSync(path.join(dest,'page.html'),render(context,program),{flag:'wx'});
    const observed=await observe(browser,context,program,path.join(dest,'page.html'),path.join(dest,'observed'),{progress:event=>progress({candidate:id,...event})});
    const evaluation=evaluate(context,program,observed,{objective});write(path.join(dest,'evaluation.json'),evaluation);
    const entry={id,program,evaluation,signature:signature(context,program),revision};candidates.push(entry);
    progress({candidate:id,status:evaluation.status,eligible:evaluation.eligible,value:evaluation.selectionValue});
  }
  try {
    await browser.launch();launched=true;
    for(const program of initial)await candidate(program);
    const names=Object.keys(context.model.controls).sort();
    for(let i=0;i<steps;i++) {
      const ranked=candidates.filter(c=>c.evaluation.eligible).sort((a,b)=>b.evaluation.selectionValue-a.evaluation.selectionValue);
      if(!ranked.length){errors.push({code:'NO_REFINEMENT_BASE',message:'No measured candidate exists for a relational move.'});break;}
      const parent=ranked[0],control=names[i%names.length],domain=context.model.controls[control];
      const direction=Math.floor(i/names.length)%2===0?1:-1;
      const value=clamp(parent.program.z[control]+direction*(domain.max-domain.min)*.12,domain.min,domain.max);
      if(value===parent.program.z[control])continue;
      const revised=transform(context,parent.program,{[control]:value});await candidate(revised.program,revised.receipt);
    }
  }catch(error){errors.push({code:error.code??'RUN',message:error.message,detail:error.detail??{}});}
  finally {if(launched)try{await browser.close();}catch(error){errors.push({code:'BROWSER_CLOSE',message:error.message});}}
  const selection=errors.length?{selected:null,reason:'run failed; partial evidence is retained without a selected output'}:select(candidates,{archive,minimumDistance,tolerance});
  const result={schema:1,request,selection,candidates:candidates.map(c=>({id:c.id,programDigest:c.program.digest,signature:c.signature,status:c.evaluation.status,eligible:c.evaluation.eligible,value:c.evaluation.selectionValue,objective,conditions:c.evaluation.conditions.length})),errors,attempted:candidates.length,planned:budget,
    claim:context.model.support.claim,beautyValidation:context.model.support.population,search:'bounded structural proposals and measured shared-coordinate pattern moves; no global-optimum claim'};
  write(path.join(dir,'result.json'),result);write(path.join(dir,'browser-receipts.json'),{session:browser.session,operations:browser.receipts});
  fs.writeFileSync(path.join(dir,'index.html'),gallery(context,result),{flag:'wx'});seal(dir);
  return {...result,directory:dir};
}
export function loadRun(dir) {verify(dir);const context=read(path.join(dir,'context.json')),result=read(path.join(dir,'result.json'));validateContext(context);return {context,result};}
export async function revise(dir,{changes,out,progress=()=>{}}) {
  const {context,result}=loadRun(dir);check(result.selection.selected,'NO_SELECTION','This run has no selected candidate.');
  const previous=read(path.join(dir,'candidates',result.selection.selected,'program.json'));
  const revised=changes?transform(context,previous,changes):{program:previous,receipt:{parent:previous.digest,successor:previous.digest,changes:[],invalidated:['observation','evaluation'],observation:'new environment measurement',selection:'stale until observed'}};
  const dest=directory(out);freezeEngine(dest);write(path.join(dest,'context.json'),context);write(path.join(dest,'request.json'),{parent:path.resolve(dir),changes:changes??{}});
  const id='c000',candidateDir=path.join(dest,'candidates',id);fs.mkdirSync(candidateDir,{recursive:true});write(path.join(candidateDir,'program.json'),revised.program);write(path.join(candidateDir,'revision.json'),revised.receipt);fs.writeFileSync(path.join(candidateDir,'page.html'),render(context,revised.program),{flag:'wx'});
  const browser=new Browser(dest);let observations,error;
  try{await browser.launch();observations=await observe(browser,context,revised.program,path.join(candidateDir,'page.html'),path.join(candidateDir,'observed'),{progress});}catch(e){error={code:e.code??'REVISION',message:e.message};}
  finally {try{await browser.close();}catch(e){error??={code:'BROWSER_CLOSE',message:e.message};}}
  const evaluation=observations?evaluate(context,revised.program,observations):{status:'incomplete',eligible:false,selectionValue:null,meanValue:null,conditions:[]};
  write(path.join(candidateDir,'evaluation.json'),evaluation);
  const candidate={id,program:revised.program,evaluation,signature:signature(context,revised.program)};
  const record={schema:1,request:{contextDigest:context.digest,modelDigest:context.modelDigest,budget:1,objective:'full'},selection:error?{selected:null,reason:'revision failed; partial evidence retained'}:select([candidate]),candidates:[{id,programDigest:revised.program.digest,signature:candidate.signature,status:evaluation.status,eligible:evaluation.eligible,value:evaluation.selectionValue,conditions:evaluation.conditions.length}],revision:revised.receipt,errors:error?[error]:[],attempted:1,planned:1,claim:context.model.support.claim};
  write(path.join(dest,'result.json'),record);write(path.join(dest,'browser-receipts.json'),{session:browser.session,operations:browser.receipts});fs.writeFileSync(path.join(dest,'index.html'),gallery(context,record),{flag:'wx'});seal(dest);return {...record,directory:dest};
}
export function exportRun(dir,out,{release=false}={}) {
  const {context,result}=loadRun(dir);check(result.selection.selected,'NO_SELECTION','No eligible candidate is available for export.');
  check(!result.errors?.length,'FAILED_RUN','A failed run cannot be exported as a selected result.');
  if(release)check(context.model.status==='adopted'&&context.model.support.claim==='calibrated domain'&&context.model.support.calibration?.domainDigest===context.domainDigest,'UNCALIBRATED','A calibrated release requires adoption evidence for this exact semantic/material domain.');
  const from=path.join(dir,'candidates',result.selection.selected),program=read(path.join(from,'program.json')),observations=read(path.join(from,'observed','observations.json'));
  validateProgram(context,program);const evaluation=evaluate(context,program,observations,{objective:result.request.objective??'full'});
  check(evaluation.eligible,'STALE_SELECTION','Selected result is no longer eligible.');
  if(release)check(evaluation.selectionValue>=context.model.support.calibration.minimum,'BELOW_PROFILE','Result is below the adopted context threshold.');
  const dest=directory(out);for(const name of ['page.html','program.json','evaluation.json'])fs.copyFileSync(path.join(from,name),path.join(dest,name));write(path.join(dest,'context.json'),context);
  write(path.join(dest,'construction-receipt.json'),{schema:1,sourceManifest:verify(dir).digest,contextDigest:context.digest,programDigest:program.digest,modelDigest:context.modelDigest,claim:release?'constructed and evaluated in the adopted context':context.model.support.claim,conditions:observations.observations.map(o=>o.condition),exactRelations:Object.values(program.frames).map(f=>f.exact),evaluation: {value:evaluation.selectionValue,scope:evaluation.claim},humanBeautyGuarantee:false});
  seal(dest);return {directory:dest,page:path.join(dest,'page.html'),claim:release?'calibrated context':context.model.support.claim};
}
export function packet(context,out) {
  validateContext(context);const dest=directory(out);write(path.join(dest,'context.json'),context);
  fs.cpSync(path.join(ROOT,'src'),path.join(dest,'engine','src'),{recursive:true});fs.cpSync(path.join(ROOT,'models'),path.join(dest,'engine','models'),{recursive:true});fs.copyFileSync(path.join(ROOT,'package.json'),path.join(dest,'engine','package.json'));
  fs.writeFileSync(path.join(dest,'START-HERE.md'),`# Aphrodite fresh-session entry\n\nThe executable relationships own selection. Read the bound content and perspective in context.json. Public copy belongs only to brief.nodes and disclosure titles. The intent reading is internal.\n\n1. Run \`node engine/src/cli.js describe --context context.json\`.\n2. Run \`node engine/src/cli.js compose --context context.json --out run --seed 1 --budget 6\`.\n3. Inspect run/index.html, the selected page, observed images, and per-relation values.\n4. Make a relationship change with \`node engine/src/cli.js revise --run run --set presence=1.2 --out revision\`. It invalidates dependent measurements and observes the successor.\n5. Export with \`node engine/src/cli.js export --run revision --out site\`.\n\nPrerequisites: Node 20 or newer and the existing agent-do browse installation. There are no npm dependencies. Preserve this manifest and the model. Each run uses a new directory. A human preference needs its exact source; never turn a critic's prose into a human label. Current support: ${context.model.support.claim}. Interpret each rule through its declared perspective and domain. Generalize corrections through relationships instead of page-specific CSS.\n`,{flag:'wx'});
  seal(dest);return {directory:dest,entry:path.join(dest,'START-HERE.md'),contextDigest:context.digest};
}
function freezeEngine(dest) {
  fs.cpSync(path.join(ROOT,'src'),path.join(dest,'engine','src'),{recursive:true});
  fs.cpSync(path.join(ROOT,'models'),path.join(dest,'engine','models'),{recursive:true});
  fs.copyFileSync(path.join(ROOT,'package.json'),path.join(dest,'engine','package.json'));
}
function gallery(context,result) {
  const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(context.brief.title)} | Aphrodite</title><style>body{margin:0;padding:32px;background:#f6f7f8;color:#20323a;font:16px/1.5 system-ui}main{max-width:1280px;margin:auto}h1{font-size:32px;line-height:1.1}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:24px}article{background:white;padding:16px;border:1px solid #d0d7dc}iframe{width:100%;height:420px;border:0}a{color:#145d75}code{word-break:break-all}</style><main><h1>${escape(context.brief.title)}</h1><p>Perspective: ${escape(context.brief.intent.perspective)}. ${escape(context.model.support.claim)}.</p><p>${escape(result.selection.reason)}. Selected: ${escape(result.selection.selected??'none')}.</p><section>${result.candidates.map(c=>`<article><h2><a href="candidates/${c.id}/page.html">${c.id}${c.id===result.selection.selected?' · Selected':''}</a></h2><p>${c.eligible?'Measured and usable':'Incomplete or failed functional conditions'} · ${c.value===null?'No value':c.value.toFixed(4)}</p><iframe title="Candidate ${c.id}" src="candidates/${c.id}/page.html" loading="lazy"></iframe><p><a href="candidates/${c.id}/evaluation.json">Relationships and evidence</a></p></article>`).join('')}</section></main></html>`;
}
