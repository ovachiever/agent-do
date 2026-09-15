import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {validateBrief,validateModel,validateContext,bind,materializeAssets} from '../src/contracts.js';
import {clone,digest,directory,write,seal,verify} from '../src/core.js';
import {derive,transform,proposals,validateProgram,signature,distance} from '../src/construct.js';
import {render} from '../src/render.js';
import {fixture,temp,rehash} from './helpers.js';

test('semantic contracts reject cycles, empty content and duplicated evidence',()=>{
  const {context}=fixture();
  for(const mutate of [b=>b.groups[0].parent=b.groups[0].id,b=>b.nodes[0].text='',b=>b.relations.push({...b.relations[0],id:'duplicate'}),b=>b.constellations[0].relations[2]=b.constellations[0].relations[0],b=>b.nodes[0].role='secret-critic',b=>b.nodes[0].css='color:red',b=>b.nodes.find(n=>n.kind==='action').href='javascript:alert(1)']){
    const brief=clone(context.brief);mutate(brief);assert.throws(()=>validateBrief(brief,context.model));
  }
});
test('model definitions require explicit scales, weights and all nine families',()=>{
  const {context}=fixture();
  for(const mutate of [m=>m.families.pop(),m=>m.families[0].weight=.8,m=>m.perspectives.counterbalance.gapScale=0,m=>m.scales.material=NaN]){const m=clone(context.model);mutate(m);assert.throws(()=>validateModel(m));}
});
test('changed model or context cannot be disguised as the same bound objective',()=>{
  const {context}=fixture();const changed=clone(context);changed.model.families[0].weight=.2;assert.throws(()=>validateContext(changed));
  rehash(changed);assert.throws(()=>validateContext(changed));
});
test('grammar terminates, preserves nodes, and produces multiple semantic structures',()=>{
  const {context}=fixture(),ps=proposals(context,{seed:'repeat',budget:8});
  assert.equal(ps.length,8);assert.ok(new Set(ps.map(p=>JSON.stringify(signature(context,p)))).size>1);
  assert.deepEqual(ps.map(p=>p.digest),proposals(context,{seed:'repeat',budget:8}).map(p=>p.digest));
  for(const p of ps){assert.equal(p.termination.terminals,context.brief.nodes.length);assert.equal(p.termination.expandedRegions,context.brief.groups.length);const html=render(context,p);for(const n of context.brief.nodes)assert.equal(html.split(`data-ap-node="${n.id}"`).length-1,1);}
});
test('relationship transforms rederive multiple dimensions and invalidate descendants',()=>{
  const {context,program}=fixture(),next=transform(context,program,{presence:1.3});
  assert.notEqual(next.program.frames.wide.display,program.frames.wide.display);assert.notEqual(next.program.frames.wide.gap,program.frames.wide.gap);
  assert.ok(next.receipt.invalidated.includes('evaluation'));assert.ok(next.receipt.invalidated.some(x=>x.startsWith('constellation:')));assert.ok(next.program.frames.wide.exact.residual<1e-10);
  assert.throws(()=>transform(context,program,{marginTop:12}));assert.throws(()=>transform(context,program,{presence:99}));
});
test('a candidate cannot change targets or topology outside the typed grammar',()=>{
  const {context,program}=fixture();const bad=clone(program);bad.topology.regions[0].production='invented';rehash(bad);assert.throws(()=>validateProgram(context,bad));
});
test('content is escaped and internal perspectives never become public copy',()=>{
  const {context}=fixture(),brief=clone(context.brief);brief.nodes[0].text='<script>alert("x")</script>';
  brief.intent.reading='A SECRET THEORY THAT MUST NEVER BE PUBLIC';const c=bind(brief,context.model,context.assets),p=derive(c);
  const html=render(c,p);assert.ok(!html.includes('<script>alert'));assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes(brief.intent.reading));
});
test('active or external SVG material is refused while passive internal paint is allowed',()=>{
  const folder=temp(),file=path.join(folder,'bad.svg'),brief={assets:[{id:'x',path:'bad.svg',alt:'x',source:'synthetic test'}]};
  fs.writeFileSync(file,'<svg><script>alert(1)</script></svg>');assert.throws(()=>materializeAssets(brief,folder));
  fs.writeFileSync(file,'<svg><path fill="url(https://example.com/x)"/></svg>');assert.throws(()=>materializeAssets(brief,folder));
  fs.writeFileSync(file,'<svg><defs><linearGradient id="g"/></defs><path fill="url(#g)"/></svg>');assert.equal(materializeAssets(brief,folder).length,1);
});
test('manifests preserve evidence and refuse overwrite or stale files',()=>{
  const dir=path.join(temp(),'run');directory(dir);write(path.join(dir,'test.json'),{x:1});seal(dir);assert.equal(verify(dir).files,1);
  assert.throws(()=>directory(dir));fs.writeFileSync(path.join(dir,'test.json'),'{}');assert.throws(()=>verify(dir));
});
test('structural distance ignores content and names in the signature',()=>{
  assert.equal(distance(['cluster:heading,body'],['cluster:heading,body']),0);assert.equal(distance(['cluster:heading,body'],['field:heading,body']),1);
});
test('a rehashed context cannot counterfeit the material or its semantic domain',()=>{
  const {context}=fixture();
  for(const mutate of [c=>c.domainDigest='0'.repeat(64),c=>c.assets[0].data=Buffer.from('<svg/>').toString('base64'),c=>c.assets[0].alt='changed meaning']) {
    const c=clone(context);mutate(c);rehash(c);assert.throws(()=>validateContext(c));
  }
});
test('an intermediate symlink cannot make external content part of an artifact',()=>{
  const outside=temp(),dir=path.join(temp(),'run');directory(dir);
  write(path.join(outside,'a.json'),{x:1});fs.symlinkSync(outside,path.join(dir,'linked'),'dir');
  write(path.join(dir,'manifest.json'),{schema:1,algorithm:'sha256',files:{'linked/a.json':'forged'}});
  assert.throws(()=>verify(dir),/inside their bundle/);
});
