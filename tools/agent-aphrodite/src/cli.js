#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import {parseArgs} from 'node:util';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {check,read,write,directory,seal,verify,digest,Fault} from './core.js';
import {ROOT,loadModel,validateBrief,materializeAssets,bind,validateContext} from './contracts.js';
import {productionCatalog} from './construct.js';
import {compose,revise,loadRun,exportRun,packet,select} from './engine.js';
import {evaluate} from './evaluate.js';
import {feedback,fit,adopt} from './learn.js';
import {nativePacket,nativeRevision,parseAssignments} from './native.js';
import {resolveRelations} from './relations.js';

const HELP=`agent-aphrodite - Contextual relational design instrument

Commands:
  doctor        Check Node, model and the existing browse transport (no launch)
  perspectives  Read the named perspectives, equations, controls and provenance
  init          Bind a real brief and materials, or copy an original example
  describe      Read an open relationship graph or a legacy bound context
  compose       Generate, render, measure and select within a fixed perspective
  vary          Generate a structurally distinct alternative within an affinity tolerance
  revise        Propagate native design relationships, or remeasure a legacy run
  observe       Remeasure a selected program in the current browser environment
  evaluate      Recompute saved observed values under full, pairs or parts objectives
  study         Compare all three objectives on an identical frozen proposal pool
  feedback      Record an explicit attributed human comparison
  fit           Propose new model weights from grouped preference records
  adopt         Adopt a model only with explicit attributable context acceptance
  export        Export a selected functional page and its construction receipt
  packet        Equip a native frontend AI session; --mode engine keeps legacy replay
  verify        Verify an immutable artifact bundle

Inputs: --brief <json> or --context <json>; optional --model <json>
Native design: packet [--brief <text-or-json>] [--relations <json>] --out <path>
               describe --relations <json>
               revise --relations <json> --set inputName=1.2 --out <path>
Packet mode: --mode native (default) | engine (legacy generator)
Artifacts: --run <directory>, --out <new path>, --candidate <id>
Construction: --seed <string>, --budget <1..48>, --steps <0..budget-1>
Perspectives: --objective full|pairs|parts; --set presence=1.2 (repeatable)
Variation: --distance <0..1>, --tolerance <0..1>
Examples: --example tideline|objects|assembly
Feedback: --left <id> --right <id> --choice left|right|tie|neither
          --quote <exact response> --source <reference> --author <name> --group <source group>
Learning: --records <json> (repeatable), --holdout <group> (repeatable)
          --iterations <number>; adoption requires --acceptance <json>
Export: --release requires a calibrated, explicitly adopted context

Every output path must be new. No external publishing or model calls occur.
Current seed perspectives are proposals. Values compare alternatives within one
context; they are not absolute beauty scores. Browser operations use agent-do browse.
`;
const OPTIONS=Object.fromEntries(['brief','context','model','run','out','candidate','seed','budget','steps','objective','distance','tolerance','example','left','right','choice','quote','source','author','group','iterations','acceptance','mode','relations'].map(k=>[k,{type:'string'}]));
OPTIONS.set={type:'string',multiple:true};OPTIONS.records={type:'string',multiple:true};OPTIONS.holdout={type:'string',multiple:true};OPTIONS.release={type:'boolean'};OPTIONS.help={type:'boolean',short:'h'};
const required=(o,key)=>{check(o[key],'ARGUMENT',`--${key} is required.`);return o[key];};
function contextFrom(o) {
  check(!(o.context&&o.brief),'INPUT','Choose a bound context or an unbound brief.');
  if(o.context){check(!o.model,'MODEL_CHANGED','A bound context already freezes its model.');return validateContext(read(o.context));}
  const file=required(o,'brief'),model=loadModel(o.model),brief=validateBrief(read(file),model);return bind(brief,model,materializeAssets(brief,path.dirname(path.resolve(file))));
}
const progress=event=>process.stderr.write(JSON.stringify(event)+'\n');
function numeric(o,key,fallback){const n=o[key]===undefined?fallback:Number(o[key]);check(Number.isFinite(n),'NUMBER',`--${key} must be numeric.`);return n;}
function searchOptions(o) {return {out:required(o,'out'),seed:o.seed??'0',budget:numeric(o,'budget',6),steps:numeric(o,'steps',0),objective:o.objective??'full',minimumDistance:numeric(o,'distance',0),tolerance:numeric(o,'tolerance',.05),progress};}
function changes(o) {
  const result={};check(o.set?.length,'ARGUMENT','Supply at least one --set relationship=value.');
  for(const value of o.set){const m=value.match(/^([a-z]+)=([+-]?(?:\d+\.?\d*|\.\d+))$/);check(m,'CHANGE','Use --set presence=1.2, tempo=0.9, balance=0.5, character=0.4, or scale=1.');check(!(m[1] in result),'CHANGE','Do not assign one control twice.');result[m[1]]=Number(m[2]);}return result;
}
export async function main(argv=process.argv.slice(2)) {
  const command=argv[0]??'help';if(['help','--help','-h'].includes(command)){process.stdout.write(HELP);return;}
  const {values:o}=parseArgs({args:argv.slice(1),options:OPTIONS,allowPositionals:false});if(o.help){process.stdout.write(HELP);return;}
  let result;
  switch(command) {
    case 'doctor': {
      const model=loadModel(o.model),probe=spawnSync(process.env.APHRODITE_AGENT_DO||'agent-do',['browse','--help'],{encoding:'utf8',timeout:10000});
      result={node:process.version,nodeSupported:Number(process.versions.node.split('.')[0])>=20,model:model.id,modelValid:true,browse:probe.status===0,dependencies:'Node built-ins only',browserLaunched:false};break;
    }
    case 'perspectives':result=loadModel(o.model);break;
    case 'init': {
      let input=o.brief;
      if(o.example){check(['tideline','objects','assembly'].includes(o.example),'EXAMPLE','Unknown example.');check(!o.brief,'INPUT','Choose example or brief.');input=path.join(ROOT,'examples',`${o.example}.json`);}
      const context=contextFrom({...o,brief:input}),out=directory(required(o,'out'));
      write(path.join(out,'context.json'),context);write(path.join(out,'brief.json'),context.brief);seal(out);result={directory:out,context:path.join(out,'context.json'),contextDigest:context.digest,domainDigest:context.domainDigest};break;
    }
    case 'describe': {
      if(o.relations){check(!o.brief&&!o.context&&!o.model,'INPUT','An open relationship graph does not use an engine context or scoring model.');result=resolveRelations(read(o.relations));break;}
      if(!o.brief&&!o.context){check(!o.model,'INPUT','A scoring model needs a legacy brief or context.');result={mode:'native',entry:path.join(ROOT,'native','START-HERE.md'),relationships:path.join(ROOT,'native','RELATIONSHIPS.md'),workflow:'The host AI designs in the existing frontend. Aphrodite carries the intention and executes open numerical relationships. Render and use normal visual judgment; no affinity ranking governs native designs.',start:'agent-do aphrodite packet --brief BRIEF.md --out .dev/design-session'};break;}
      const c=contextFrom(o);result={contextDigest:c.digest,domainDigest:c.domainDigest,title:c.brief.title,perspective:c.brief.intent,model:c.model.id,support:c.model.support,nodes:c.brief.nodes,relations:c.brief.relations,constellations:c.brief.constellations,controls:c.model.controls,grammar:productionCatalog,conditions:{viewports:c.brief.viewports,states:c.brief.states}};break;
    }
    case 'compose':result=await compose(contextFrom(o),searchOptions(o));break;
    case 'vary': {
      const {context,result:previous}=loadRun(required(o,'run'));check(previous.selection.selected,'NO_SELECTION','The source run has no selected design.');
      result=await compose(context,{...searchOptions(o),minimumDistance:numeric(o,'distance',.25),archive:[previous.candidates.find(c=>c.id===previous.selection.selected).signature]});break;
    }
    case 'revise': {
      if(o.relations){check(!o.run&&!o.context&&!o.brief&&!o.model,'INPUT','Choose native relationships or a legacy run.');result=nativeRevision(read(o.relations),parseAssignments(o.set),required(o,'out'));}
      else result=await revise(required(o,'run'),{changes:changes(o),out:required(o,'out'),progress});
      break;
    }
    case 'observe':result=await revise(required(o,'run'),{out:required(o,'out'),progress});break;
    case 'evaluate': {
      const {context,result:run}=loadRun(required(o,'run'));const selected=o.candidate??run.selection.selected;check(selected&&run.candidates.some(c=>c.id===selected),'CANDIDATE','No such candidate.');
      const p=path.join(o.run,'candidates',selected);result=evaluate(context,read(path.join(p,'program.json')),read(path.join(p,'observed','observations.json')),{objective:o.objective??'full'});break;
    }
    case 'study': {
      const {context,result:run}=loadRun(required(o,'run'));check(run.request.steps===0,'MATCHED_BUDGET','Use a run without adaptive refinement for a fixed-pool ablation.');
      const comparisons={};
      for(const objective of ['full','pairs','parts']) {
        const rows=run.candidates.map(c=>{const p=path.join(o.run,'candidates',c.id),program=read(path.join(p,'program.json'));return {...c,program,evaluation:evaluate(context,program,read(path.join(p,'observed','observations.json')),{objective})};});
        comparisons[objective]={selection:select(rows),rows:rows.map(c=>({id:c.id,eligible:c.evaluation.eligible,value:c.evaluation.selectionValue}))};
      }
      const out=directory(required(o,'out'));result={schema:1,sourceManifest:verify(o.run).digest,contextDigest:context.digest,modelDigest:context.modelDigest,proposalCount:run.attempted,comparisons,humanResponse:null,scope:'Matched frozen proposal pool; no host-baseline experiment or human validation is implied.'};write(path.join(out,'study.json'),result);seal(out);result.directory=out;break;
    }
    case 'feedback':result=feedback({...o,run:required(o,'run'),out:required(o,'out')});break;
    case 'fit': {
      check(o.records?.length,'ARGUMENT','Supply --records for each attributed comparison.');const prior=loadModel(o.model),fitted=fit(o.records.map(read),{prior,holdoutGroups:o.holdout??[],iterations:numeric(o,'iterations',400)}),out=directory(required(o,'out'));write(path.join(out,'model.json'),fitted.model);write(path.join(out,'diagnostics.json'),fitted.diagnostics);seal(out);result={directory:out,model:fitted.model.id,...fitted.diagnostics};break;
    }
    case 'adopt': {
      const model=adopt(loadModel(required(o,'model')),read(required(o,'acceptance')));write(required(o,'out'),model);result={model:model.id,path:o.out,support:model.support};break;
    }
    case 'export':result=exportRun(required(o,'run'),required(o,'out'),{release:o.release??false});break;
    case 'packet': {
      const mode=o.mode??'native';check(['native','engine'].includes(mode),'MODE','Choose native or engine packet mode.');
      if(mode==='engine'){check(!o.relations,'INPUT','Open relationships belong to native mode.');result=packet(contextFrom(o),required(o,'out'));}
      else {check(!o.model,'INPUT','Native design does not use a scoring model.');check(!(o.brief&&o.context),'INPUT','Choose a plain brief or an existing engine context.');result=nativePacket({brief:o.brief,context:o.context?validateContext(read(o.context)):null,relations:o.relations,out:required(o,'out')});}
      break;
    }
    case 'verify':result=verify(required(o,'run'));break;
    default:throw new Fault('COMMAND',`Unknown command: ${command}`);
  }
  process.stdout.write(JSON.stringify({success:!result.errors?.length,tool:'aphrodite',data:result},null,2)+'\n');
  if(result.selection&&!result.selection.selected)process.exitCode=2;
  if(command==='doctor'&&(!result.nodeSupported||!result.browse))process.exitCode=1;
  if(result.errors?.length)process.exitCode=1;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(error=>{process.stderr.write(JSON.stringify({success:false,tool:'aphrodite',error:{code:error.code??'ERROR',message:error.message,detail:error.detail??{}}},null,2)+'\n');process.exitCode=1;});
