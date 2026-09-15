import test from 'node:test';
import assert from 'node:assert/strict';
import {clone} from '../src/core.js';
import {evaluate} from '../src/evaluate.js';
import {select} from '../src/engine.js';
import {fixture,observationFixture} from './helpers.js';

test('all nine families compute from explicit observed relationships',()=>{
  const {context,program}=fixture(),obs=observationFixture(context,program),result=evaluate(context,program,obs);
  assert.equal(result.status,'measured');assert.equal(Object.keys(result.conditions[0].features).length,9);
  assert.ok(result.conditions[0].voids.length>0);assert.equal(result.conditions[0].detail['APH-08'].arity,3);
});
test('missing content, missing paint, and clipped conditions cannot be selected',()=>{
  const {context,program}=fixture();
  for(const mutate of [o=>o.observations[0].nodes.find(n=>n.id==='intro').visible=false,o=>o.observations[0].nodes.find(n=>n.id==='intro').unsupported=['opaque paint'],o=>o.observations.pop(),o=>o.observations[0].groups=[]]){
    const obs=observationFixture(context,program);mutate(obs);const result=evaluate(context,program,obs);assert.equal(result.eligible,false);assert.equal(result.selectionValue,null);
  }
  const obs=observationFixture(context,program);obs.observations[2].nodes.find(n=>n.id==='intro').clipped=true;assert.equal(evaluate(context,program,obs).eligible,false);
});
test('actual relationships change a joint prediction while intact node inventory remains fixed',()=>{
  const {context,program}=fixture(),original=observationFixture(context,program),changed=clone(original);
  for(const o of changed.observations){const node=o.nodes.find(n=>n.id==='intro');node.box.y+=400;node.fragments.forEach(f=>f.y+=400);}
  const a=evaluate(context,program,original),b=evaluate(context,program,changed);assert.notEqual(a.selectionValue,b.selectionValue);assert.equal(a.conditions[0].partBaseline,b.conditions[0].partBaseline);
});
test('a common translation and unbound wrapper data do not manufacture affinity',()=>{
  const {context,program}=fixture(),original=observationFixture(context,program),moved=clone(original);
  for(const o of moved.observations){for(const n of o.nodes.filter(n=>n.visible)){n.box.x+=33;n.box.y+=45;n.fragments.forEach(f=>{f.x+=33;f.y+=45;});}for(const g of o.groups){g.box.x+=33;g.box.y+=45;}o.metadata={unpainted:'wrapper'};}
  const a=evaluate(context,program,original),b=evaluate(context,program,moved);assert.ok(Math.abs(a.selectionValue-b.selectionValue)<1e-12);
});
test('each condition and duplicate bound node is verified, not only the envelope',()=>{
  const {context,program}=fixture(),a=observationFixture(context,program);a.observations[0].programDigest='wrong';assert.throws(()=>evaluate(context,program,a));
  const b=observationFixture(context,program);b.observations[0].nodes.push(clone(b.observations[0].nodes[0]));assert.equal(evaluate(context,program,b).status,'incomplete');
  const c=observationFixture(context,program);c.observations[0].viewport.width=12;assert.throws(()=>evaluate(context,program,c));
});
test('strong desktop affinity cannot average away a required narrow-view failure',()=>{
  const {context,program}=fixture(),obs=observationFixture(context,program);obs.observations[2].document.width=5000;
  const result=evaluate(context,program,obs);assert.equal(result.status,'measured');assert.equal(result.eligible,false);
});
test('distinctness is a constraint inside an affinity tolerance, never a novelty reward',()=>{
  const c=(id,value,shape)=>({id,program:{digest:id},signature:[shape],evaluation:{eligible:true,selectionValue:value,meanValue:value}});
  const candidates=[c('best',.8,'same'),c('bizarre',.1,'different')];
  assert.equal(select(candidates).selected,'best');assert.equal(select(candidates,{archive:[['same']],minimumDistance:.5,tolerance:.05}).selected,null);
  candidates.push(c('good-distinct',.78,'different'));assert.equal(select(candidates,{archive:[['same']],minimumDistance:.5,tolerance:.05}).selected,'good-distinct');
});
