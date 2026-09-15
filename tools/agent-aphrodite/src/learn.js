import path from 'node:path';
import {check,read,write,digest,clone,finite,unique} from './core.js';
import {loadRun} from './engine.js';
import {validateModel} from './contracts.js';

export function feedback({run,left,right,choice,quote,source,author,group,out}) {
  const {context,result}=loadRun(run);
  check(left!==right&&[left,right].every(id=>result.candidates.some(c=>c.id===id&&c.eligible)),'COMPARISON','Choose two different measured, eligible candidates.');
  check(['left','right','tie','neither'].includes(choice),'PREFERENCE','Choice must be left, right, tie, or neither.');
  check([quote,source,author,group].every(x=>typeof x==='string'&&x.trim()),'ATTRIBUTION','Exact quote, source, author and source group are required.');
  const evaluations=[left,right].map(id=>read(path.join(run,'candidates',id,'evaluation.json')));
  const record={schema:1,kind:'attributed preference',author,source,group,quote,choice,runManifest:read(path.join(run,'manifest.json')),contextDigest:context.digest,modelDigest:context.modelDigest,model:context.model,left:{id:left,evaluation:evaluations[0]},right:{id:right,evaluation:evaluations[1]},authority:'supplied human response; authenticity remains with the attributed source'};
  record.id=digest(record);write(out,record);return {file:out,id:record.id,choice,author};
}
export function projectSimplex(values) {
  const sorted=[...values].sort((a,b)=>b-a);let sum=0,rho=0;
  for(let i=0;i<sorted.length;i++){sum+=sorted[i];if(sorted[i]+(1-sum)/(i+1)>0)rho=i+1;}
  const threshold=(sorted.slice(0,rho).reduce((a,b)=>a+b,0)-1)/rho;
  return values.map(v=>Math.max(0,v-threshold));
}
export function scoreGradient(evaluation,weights,ids) {
  const rows=evaluation.conditions.map(c=>{
    const active=ids.map(id=>c.active[id]===true),denom=weights.reduce((s,w,i)=>s+(active[i]?w:0),0);
    check(denom>0,'FIT_DOMAIN','The proposed weights erase an eligible family set.');
    const features=ids.map((id,i)=>active[i]?c.features[id]:0);
    const score=weights.reduce((s,w,i)=>s+w*features[i],0)/denom;
    return {score,gradient:features.map((f,i)=>active[i]?(f-score)/denom:0)};
  }).sort((a,b)=>a.score-b.score);
  check(rows.length>0,'FIT_OBSERVATION','No measured conditions.');return rows[0];
}
const sigmoid=x=>x>=0?1/(1+Math.exp(-x)):Math.exp(x)/(1+Math.exp(x));
export function lossGradient(records,weights,prior,ids,{temperature=4,regularization=.5}={}) {
  const groups=new Map();for(const r of records)groups.set(r.group,(groups.get(r.group)||0)+1);
  let loss=0;const gradient=weights.map((w,i)=>2*regularization*(w-prior[i]));
  loss+=regularization*weights.reduce((s,w,i)=>s+(w-prior[i])**2,0);
  for(const r of records) {
    const a=scoreGradient(r.left.evaluation,weights,ids),b=scoreGradient(r.right.evaluation,weights,ids),x=temperature*(a.score-b.score),target=r.choice==='left'?1:r.choice==='right'?0:.5;
    const weight=1/(groups.size*groups.get(r.group)),probability=sigmoid(x);
    loss+=weight*(Math.max(x,0)-x*target+Math.log1p(Math.exp(-Math.abs(x))));
    for(let i=0;i<weights.length;i++)gradient[i]+=weight*temperature*(probability-target)*(a.gradient[i]-b.gradient[i]);
  }
  return {loss,gradient};
}
export function fit(records,{prior,holdoutGroups=[],iterations=400,rate=.08,regularization=.5,temperature=4}={}) {
  validateModel(prior);check(records.length>0,'FIT_DATA','No preference records.');unique(records);
  check(Number.isInteger(iterations)&&iterations>=1&&iterations<=10000,'FIT_BUDGET','Use 1 to 10000 fit iterations.');
  finite(rate,'learning rate',.00001,1);finite(regularization,'regularization',.00001,100);finite(temperature,'temperature',.1,100);
  const ratifiers=new Set(records.map(r=>r.author));check(ratifiers.size===1,'RATIFIER','Fit one explicitly attributed taste target at a time.');
  for(const r of records) {
    check(r.schema===1&&r.quote?.trim()&&r.source?.trim()&&r.group?.trim(),'FIT_PROVENANCE','Preference lacks source attribution.');
    const {id,...data}=r;check(digest(data)===id,'PREFERENCE_CHANGED','Preference record has changed.');
    check(r.modelDigest===digest(prior),'FIT_MODEL','Records must use the exact proposed starting model.');
    check(['left','right','tie','neither'].includes(r.choice),'FIT_LABEL','Invalid preference label.');
    for(const side of ['left','right'])check(r[side].evaluation.status==='measured'&&r[side].evaluation.eligible,'FIT_OBSERVATION','Only complete eligible render evidence enters this fit.');
  }
  const usable=records.filter(r=>r.choice!=='neither'),train=usable.filter(r=>!holdoutGroups.includes(r.group)),held=usable.filter(r=>holdoutGroups.includes(r.group));
  check(train.length>0,'FIT_TRAIN','No training comparisons remain.');
  const ids=prior.families.map(f=>f.id),original=prior.families.map(f=>f.weight);let weights=[...original];
  const options={temperature,regularization};let previous=lossGradient(train,weights,original,ids,options).loss,completed=0;
  for(let i=0;i<iterations;i++) {
    const {gradient}=lossGradient(train,weights,original,ids,options);let step=rate,candidate,next;
    for(let j=0;j<20;j++){candidate=projectSimplex(weights.map((w,k)=>w-step*gradient[k]));next=lossGradient(train,candidate,original,ids,options).loss;if(next<=previous+1e-12)break;step/=2;}
    if(next>previous+1e-12)break;weights=candidate;completed++;
    if(Math.abs(previous-next)<1e-12){previous=next;break;}previous=next;
  }
  const diagnostics=rows=>rows.map(r=>{const a=scoreGradient(r.left.evaluation,weights,ids).score,b=scoreGradient(r.right.evaluation,weights,ids).score;return {id:r.id,group:r.group,choice:r.choice,margin:a-b,probability:sigmoid(temperature*(a-b))};});
  const spec={iterations,rate,regularization,temperature,holdoutGroups};
  const proposal=clone(prior);proposal.status='fitted';proposal.id=`${prior.id}-fit-${digest({records:train.map(r=>r.id),spec}).slice(0,10)}`;
  proposal.families.forEach((f,i)=>f.weight=weights[i]);
  proposal.support={claim:'model-guided exploration',population:'unvalidated transfer',calibration:null};
  proposal.fit={parentDigest:digest(prior),ratifier:[...ratifiers][0],training:train.map(r=>r.id),heldOut:held.map(r=>r.id),spec,adopted:false};
  proposal.development.push({kind:'group-weighted offline preference fit',knownFailure:'Small or overlapping preference sets do not establish generalization.'});
  validateModel(proposal);
  return {model:proposal,diagnostics:{training:diagnostics(train),heldOut:diagnostics(held),neither:records.filter(r=>r.choice==='neither').map(r=>r.id),groups:new Set(train.map(r=>r.group)).size,comparisons:train.length,freeWeightParameters:weights.length-1,iterations:completed,loss:previous,fitSpecFrozen:digest(spec),claim:'development fit, not adopted taste or independent scientific validation'}};
}
export function adopt(model,acceptance) {
  validateModel(model);check(acceptance.modelDigest===digest(model),'ADOPTION_MODEL','Acceptance must identify this exact proposed model.');
  check(acceptance.author?.trim()&&acceptance.source?.trim()&&acceptance.quote?.trim(),'ADOPTION_SOURCE','Explicit adoption requires attributable acceptance.');
  check(acceptance.domainDigest?.match(/^[a-f0-9]{64}$/),'ADOPTION_DOMAIN','Acceptance must bind the intended semantic/material domain.');
  finite(acceptance.minimum,'calibrated minimum',0,1);
  const result=clone(model);result.id=`${model.id}-adopt-${digest(acceptance).slice(0,8)}`;result.status='adopted';
  result.support={claim:'calibrated domain',population:acceptance.author,calibration:{domainDigest:acceptance.domainDigest,minimum:acceptance.minimum,acceptance:clone(acceptance)}};
  result.development.push({kind:'explicit context adoption',parent:digest(model),acceptance:digest(acceptance)});validateModel(result);return result;
}
