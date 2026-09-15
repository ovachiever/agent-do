import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {ROOT} from '../src/contracts.js';
import {read,verify} from '../src/core.js';
import {resolveRelations,reviseRelations,applyRelations} from '../src/relations.js';
import {temp} from './helpers.js';

const example=()=>read(path.join(ROOT,'native/EXAMPLE.json'));
const call=(args)=>spawnSync(process.execPath,[path.join(ROOT,'src/cli.js'),...args],{encoding:'utf8',timeout:10000});

test('one authored relationship can compensate or expand without changing the frontend vocabulary',()=>{
  const graph=example(),original=JSON.stringify(graph);
  const contracted=reviseRelations(graph,{presence:2});
  assert.equal(contracted.resolved.values.headingSize,8);
  assert.equal(contracted.resolved.values.supportGap,1);
  const expanded=reviseRelations(graph,{presence:2,elasticity:1});
  assert.equal(expanded.resolved.values.supportGap,4);
  assert.equal(JSON.stringify(graph),original,'The previous design relationship stays intact.');
  assert.deepEqual(contracted.revision.affected,['presence','headingSize','supportGap']);
  assert.equal(contracted.revision.renderStatus,'unobserved');
  assert.equal(contracted.revision.qualityVerdict,null);
});

test('transitive changes include dependent but clamped nodes and leave unrelated nodes alone',()=>{
  const graph=example();
  graph.inputs.unrelated={value:7,why:'An independent part of this fixture.'};
  graph.relations.bounded={expr:{op:'clamp',args:['headingSize',0,4]},why:'A declared bound in the test.'};
  graph.relations.double={expr:{op:'multiply',args:['bounded',2]},why:'A second dependency level.'};
  const result=reviseRelations(graph,{presence:1.5});
  assert.ok(result.revision.affected.includes('double'));
  assert.ok(!result.revision.changedValues.some(row=>row.node==='double'));
  assert.ok(!result.revision.affected.includes('unrelated'));
});

test('cycles, missing references, arithmetic failures and derived overrides fail before any page mutation',()=>{
  const variants=[];
  let graph=example();graph.relations.headingSize.expr='supportGap';graph.relations.supportGap.expr='headingSize';variants.push([graph,{}]);
  graph=example();graph.relations.headingSize.expr='missing';variants.push([graph,{}]);
  graph=example();graph.relations.supportGap.expr={op:'divide',args:[1,0]};variants.push([graph,{}]);
  graph=example();graph.relations.supportGap.expr={op:'power',args:[-1,0.5]};variants.push([graph,{}]);
  variants.push([example(),{headingSize:8}],[example(),{presence:10}]);
  for(const [invalid,overrides] of variants) {
    let mutations=0;
    assert.throws(()=>applyRelations({style:{setProperty(){mutations++;}}},invalid,overrides));
    assert.equal(mutations,0);
  }
});

test('native packets accept real prose without an engine schema or a renderer',()=>{
  const dir=temp(),brief=path.join(dir,'brief.md'),out=path.join(dir,'packet');
  const text='A working piano archive. Preserve the existing score viewer, audio controls, and dense catalog rows.\n';
  fs.writeFileSync(brief,text);
  const result=call(['packet','--brief',brief,'--out',out]);assert.equal(result.status,0,result.stderr);
  assert.equal(fs.readFileSync(path.join(out,'BRIEF.txt'),'utf8'),text);
  const metadata=read(path.join(out,'packet.json'));
  assert.equal(metadata.rendererIncluded,false);assert.equal(metadata.scoringModelIncluded,false);
  assert.deepEqual(read(path.join(out,'relations.json')).inputs,{});
  assert.ok(!fs.existsSync(path.join(out,'engine')));
  assert.ok(verify(out).verified);
  assert.equal(call(['packet','--out',out]).status,1,'An existing packet must not be overwritten.');
});

test('a copied native packet executes the same revision path without the installed engine or browser',()=>{
  const dir=temp(),packet=path.join(dir,'packet'),portable=path.join(dir,'copied'),out=path.join(dir,'revision');
  const result=call(['packet','--relations',path.join(ROOT,'native/EXAMPLE.json'),'--out',packet]);assert.equal(result.status,0,result.stderr);
  fs.cpSync(packet,portable,{recursive:true});
  const revised=spawnSync(process.execPath,[path.join(portable,'runtime/relation-cli.js'),'--relations',path.join(portable,'relations.json'),'--out',out,'--set','presence=2'],{cwd:portable,encoding:'utf8',timeout:10000,env:{PATH:'/nonexistent'}});
  assert.equal(revised.status,0,revised.stderr);
  assert.equal(read(path.join(out,'resolution.json')).variables['--support-gap'],'1rem');
  assert.equal(read(path.join(out,'relations.json')).inputs.presence.value,2);
  assert.ok(verify(out).verified);assert.ok(verify(portable).verified);
});

test('native CLI refuses mixed modes and invalid graphs before writing output',()=>{
  const dir=temp(),graph=path.join(dir,'bad.json');
  const invalid=example();invalid.relations.headingSize.expr='missing';fs.writeFileSync(graph,JSON.stringify(invalid));
  for(const [i,args] of [
    ['packet','--mode','unknown'],
    ['packet','--relations',graph],
    ['revise','--relations',graph,'--set','presence=1.5'],
    ['revise','--relations',path.join(ROOT,'native/EXAMPLE.json'),'--run','legacy']
  ].entries()) {
    const out=path.join(dir,`failed-${i}`);const result=call([...args,'--out',out]);
    assert.equal(result.status,1,result.stdout);assert.ok(!fs.existsSync(out));
  }
});

test('default discovery is native; explicit engine packets remain available and self contained',()=>{
  const description=call(['describe']);assert.equal(description.status,0,description.stderr);assert.equal(JSON.parse(description.stdout).data.mode,'native');
  const out=path.join(temp(),'legacy');
  const result=call(['packet','--mode','engine','--brief',path.join(ROOT,'examples/tideline.json'),'--out',out]);
  assert.equal(result.status,0,result.stderr);assert.ok(fs.existsSync(path.join(out,'engine/src/render.js')));assert.ok(verify(out).verified);
  const nested=path.join(temp(),'new-native');
  const copied=spawnSync(process.execPath,[path.join(out,'engine/src/cli.js'),'packet','--out',nested],{encoding:'utf8',timeout:10000});
  assert.equal(copied.status,0,copied.stderr);assert.ok(verify(nested).verified);
});

test('binding names and arithmetic are data, not injected CSS or executable expressions',()=>{
  const graph=example();graph.bindings['--x; color: red']={node:'presence',unit:''};assert.throws(()=>resolveRelations(graph));
  const second=example();second.relations.supportGap.expr={op:'constructor',args:[1,2]};assert.throws(()=>resolveRelations(second));
});
