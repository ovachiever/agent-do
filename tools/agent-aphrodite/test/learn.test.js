import test from 'node:test';
import assert from 'node:assert/strict';
import {projectSimplex,lossGradient,fit,adopt} from '../src/learn.js';
import {loadModel} from '../src/contracts.js';
import {digest,clone} from '../src/core.js';

function record(model,choice='left',group='training') {
  const evaluation=values=>({status:'measured',eligible:true,conditions:[{active:Object.fromEntries(model.families.map(f=>[f.id,true])),features:Object.fromEntries(model.families.map((f,i)=>[f.id,values[i]]))}]});
  const r={schema:1,author:'Synthetic test harness; not a human',source:'fabricated algebra fixture',quote:'Synthetic label, no human judgment',group,choice,modelDigest:digest(model),left:{evaluation:evaluation([.9,.5,.5,.5,.5,.5,.5,.5,.5])},right:{evaluation:evaluation([.1,.5,.5,.5,.5,.5,.5,.5,.5])}};return {...r,id:digest(r)};
}
test('projection supplies nonnegative normalized weights',()=>{const w=projectSimplex([-.2,.7,1.1]);assert.ok(w.every(v=>v>=0));assert.ok(Math.abs(w.reduce((a,b)=>a+b,0)-1)<1e-12);});
test('analytic fitting gradient agrees with finite differences',()=>{
  const model=loadModel(),records=[record(model)],weights=model.families.map(f=>f.weight),ids=model.families.map(f=>f.id),result=lossGradient(records,weights,weights,ids),epsilon=1e-6;
  for(let i=0;i<weights.length;i++){const plus=[...weights],minus=[...weights];plus[i]+=epsilon;minus[i]-=epsilon;const derivative=(lossGradient(records,plus,weights,ids).loss-lossGradient(records,minus,weights,ids).loss)/(2*epsilon);assert.ok(Math.abs(derivative-result.gradient[i])<1e-6);}
});
test('fitting proposes a version and does not silently adopt it',()=>{
  const prior=loadModel(),original=digest(prior),result=fit([record(prior)],{prior,iterations:100});assert.ok(result.model.families[0].weight>prior.families[0].weight);assert.equal(result.model.status,'fitted');assert.equal(result.model.support.calibration,null);assert.equal(digest(prior),original);
});
test('held-out groups cannot influence the fitted weights',()=>{
  const prior=loadModel(),training=record(prior),a=record(prior,'left','holdout'),b=record(prior,'right','holdout');
  const x=fit([training,a],{prior,holdoutGroups:['holdout']}),y=fit([training,b],{prior,holdoutGroups:['holdout']});assert.deepEqual(x.model.families,y.model.families);assert.equal(x.diagnostics.heldOut.length,1);
});
test('neither is retained and cannot become a fabricated pairwise rejection',()=>{
  const prior=loadModel(),result=fit([record(prior),record(prior,'neither','absolute')],{prior});assert.equal(result.diagnostics.neither.length,1);assert.equal(result.diagnostics.comparisons,1);
});
test('adoption requires a source, exact model binding and contextual domain',()=>{
  const m=loadModel();assert.throws(()=>adopt(m,{}));const adoption={modelDigest:digest(m),domainDigest:'a'.repeat(64),author:'Synthetic harness',source:'test fixture only',quote:'Synthetic acceptance',minimum:.4};const a=adopt(m,adoption);assert.equal(a.status,'adopted');assert.equal(m.status,'proposed');assert.equal(a.support.calibration.domainDigest,adoption.domainDigest);
});
