// Real production-path integration. No browser mocks or fabricated preferences.
// Evidence is retained under the ignored package .dev directory.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import {ROOT} from '../src/contracts.js';
import {read,write,verify,seal} from '../src/core.js';
import {Browser} from '../src/browser.js';
import {separation} from '../src/math.js';
import {temp} from './helpers.js';

const dir=temp(),repo=path.resolve(ROOT,'../..'),owner=path.join(repo,'agent-do');
const receipts=[];
function cli(args,{executable=owner,prefix=['aphrodite'],expect=0,cwd=repo}={}) {
  process.stdout.write(`Aphrodite integration: ${args[0]}\n`);
  const result=spawnSync(executable,[...prefix,...args],{cwd,encoding:'utf8',timeout:240000,maxBuffer:8*1024*1024,env:{...process.env,APHRODITE_AGENT_DO:owner}});
  receipts.push({command:args[0],exit:result.status,stderr:result.stderr});
  assert.equal(result.status,expect,result.stderr||result.error?.message);
  return JSON.parse(expect===0?result.stdout:result.stderr||result.stdout);
}
try {
  cli(['doctor']);
  const contextDir=path.join(dir,'context');
  cli(['init','--example','tideline','--out',contextDir]);
  const context=read(path.join(contextDir,'context.json'));
  const run=path.join(dir,'run');
  const first=cli(['compose','--context',path.join(contextDir,'context.json'),'--out',run,'--seed','integration','--budget','2']).data;
  assert.equal(first.errors.length,0);assert.equal(first.attempted,2);assert.ok(first.selection.selected);
  const selected=path.join(run,'candidates',first.selection.selected);
  const evaluation=read(path.join(selected,'evaluation.json'));
  assert.ok(evaluation.eligible);assert.equal(evaluation.conditions.length,4);
  for(const c of evaluation.conditions)for(let i=1;i<=9;i++)assert.ok(Number.isFinite(c.features[`APH-0${i}`]));
  const prior=read(path.join(selected,'program.json'));
  const presence=prior.z.presence>1.4?1.1:prior.z.presence+.15;
  const revisedDir=path.join(dir,'revision');
  const revised=cli(['revise','--run',run,'--out',revisedDir,'--set',`presence=${presence}`]).data;
  assert.ok(revised.selection.selected);assert.ok(revised.revision.invalidated.includes('evaluation'));
  const changed=path.join(revisedDir,'candidates','c000'),program=read(path.join(changed,'program.json'));
  for(const view of context.brief.viewports) {
    const observed=read(path.join(changed,'observed',`${view.id}-base.json`));
    const relation=context.brief.relations.find(r=>r.kind==='supports'&&context.brief.nodes.find(n=>n.id===r.nodes[0]).role==='display'&&context.brief.nodes.find(n=>n.id===r.nodes[1]).role==='body');
    const [lead,support]=relation.nodes.map(id=>observed.nodes.find(n=>n.id===id));
    assert.ok(Math.abs(lead.font.size-program.frames[view.id].display)<.05);
    assert.ok(Math.abs(separation(lead.box,support.box)-program.frames[view.id].gap)<.1,'Real rendered gap must follow the coupled equation.');
    const expanded=read(path.join(changed,'observed',`${view.id}-expanded.json`));
    for(const group of context.brief.groups.filter(g=>g.kind==='disclosure'))assert.equal(expanded.groups.find(g=>g.id===group.id).open,true);
  }
  const study=path.join(dir,'study');cli(['study','--run',run,'--out',study]);
  assert.equal(read(path.join(study,'study.json')).humanResponse,null);
  const site=path.join(dir,'site');cli(['export','--run',revisedDir,'--out',site]);
  assert.equal(read(path.join(site,'construction-receipt.json')).humanBeautyGuarantee,false);
  cli(['export','--run',revisedDir,'--out',path.join(dir,'unearned-release'),'--release'],{expect:1});
  assert.ok(!fs.existsSync(path.join(dir,'unearned-release')));
  const packet=path.join(dir,'packet');cli(['packet','--context',path.join(contextDir,'context.json'),'--out',packet]);
  const frozen=path.join(packet,'engine','src','cli.js');
  const again=cli(['evaluate','--run',run],{executable:process.execPath,prefix:[frozen],cwd:packet}).data;
  assert.deepEqual(again,evaluation,'The independent frozen package must reproduce the complete evaluation.');
  const packetRun=path.join(dir,'packet-run');
  const fresh=cli(['compose','--context',path.join(packet,'context.json'),'--out',packetRun,'--seed','fresh','--budget','1'],{executable:process.execPath,prefix:[frozen],cwd:packet}).data;
  assert.ok(fresh.selection.selected);assert.equal(fresh.errors.length,0);
  const browser=new Browser(dir+'-interaction');
  try {
    await browser.launch();await browser.call('open',pathToFileURL(path.join(site,'page.html')).href);
    await browser.call('press','Tab');
    const focus=(await browser.call('eval','({tag:document.activeElement.tagName,text:document.activeElement.textContent,outline:getComputedStyle(document.activeElement).outlineStyle})')).result;
    assert.equal(focus.text,'Skip to content');assert.notEqual(focus.outline,'none');
    const disclosure=context.brief.groups.find(g=>g.kind==='disclosure');
    await browser.call('focus',`#${disclosure.id}>summary`);await browser.call('press','Enter');
    assert.equal((await browser.call('eval',`document.getElementById(${JSON.stringify(disclosure.id)}).open`)).result,true);
    const action=context.brief.nodes.find(n=>n.kind==='action'&&n.href.startsWith('#'));
    await browser.call('click',`#${action.id}`);
    assert.equal((await browser.call('eval','location.hash')).result,action.href);
  } finally {await browser.close();}
  const bundles=[contextDir,run,revisedDir,study,site,packet,packetRun].map(p=>({path:p,...verify(p)}));
  write(path.join(dir,'validation.json'),{success:true,bundles,receipts,claims:['all nine computed on actual renders','four viewport/state conditions','coupled change matches actual dimensions','native pointer and keyboard actions','fresh package generates and replays','unadopted release refused'],humanTasteValidation:false});
  seal(dir);process.stdout.write(`Aphrodite browser integration passed. Evidence: ${dir}\n`);
} catch(error) {
  write(path.join(dir,'failure.json'),{success:false,message:error.message,stack:error.stack,receipts});
  process.stderr.write(`Aphrodite evidence retained: ${dir}\n`);throw error;
}
