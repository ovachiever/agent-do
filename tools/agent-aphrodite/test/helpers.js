import fs from 'node:fs';
import path from 'node:path';
import {ROOT,loadModel,validateBrief,materializeAssets,bind} from '../src/contracts.js';
import {read,clone,digest} from '../src/core.js';
import {derive} from '../src/construct.js';
import {scope} from '../src/evaluate.js';
import {rgb} from '../src/math.js';
export function fixture(name='tideline') {
  const model=loadModel(),file=path.join(ROOT,'examples',name+'.json'),brief=validateBrief(read(file),model);
  const context=bind(brief,model,materializeAssets(brief,path.dirname(file))),program=derive(context,'unit',0);
  return {context,program};
}
// Fabricated rectangles for algebra/contracts tests only. Never human or browser evidence.
export function observationFixture(context,program) {
  const b=context.brief,observations=[];
  for(const viewport of b.viewports)for(const state of b.states) {
    const s=scope(context,state),visible=new Set(s.nodes.map(n=>n.id));
    const nodes=b.nodes.map((n,i)=>{
      if(!visible.has(n.id))return {id:n.id,visible:false};
      const font=n.role==='display'?60:n.role==='heading'?28:18;
      const box={x:30+(i%2)*300,y:40+i*80,width:270,height:n.kind==='image'?150:52};
      return {id:n.id,visible:true,box,text:n.kind==='image'?context.assets.find(a=>a.id===n.asset).alt:n.text,tag:n.kind==='action'?'a':'div',font:{family:'Fixture serif',size:font,weight:400,lineHeight:font*1.2,letterSpacing:0,advance:250,ascent:font*.8,descent:font*.2,fingerprint:[12,.8,.2],inkDensity:.3},fragments:[{...box,height:font}],color:rgb(b.frame.ink).concat(255),background:rgb(b.frame.paper).concat(255),unsupported:[],radius:2,stroke:1,
      material:n.kind==='image'?{status:'measured',mean:[80,100,80],variance:[1000,1200,900],edge:.1,coverage:1,palette:[{rgb:[80,100,80],share:1}],natural:[1200,1000]}:null,href:n.href??null,clipped:false};
    });
    const groups=b.groups.map(g=>({id:g.id,visible:!s.hidden.includes(g.id),box:{x:0,y:0,width:640,height:1400},padding:[20,20,20,20],open:g.kind==='disclosure'?state==='expanded':null}));
    observations.push({schema:1,method:'aphrodite-observation-1',fixtureAuthority:'fabricated unit-test geometry; not real observation',condition:{id:`${viewport.id}-${state}`,viewport:viewport.id,state},viewport:{width:viewport.width,height:viewport.height},document:{width:viewport.width,height:1600},programDigest:program.digest,contextDigest:context.digest,fontsStatus:'loaded',nodes,groups,diagnostics:{allImagesLoaded:true}});
  }
  return {schema:1,programDigest:program.digest,contextDigest:context.digest,observations,failures:[]};
}
export function temp() {const root=path.join(ROOT,'.dev');fs.mkdirSync(root,{recursive:true});return fs.mkdtempSync(path.join(root,'test-'));}
export const rehash=value=>{delete value.digest;value.digest=digest(value);return value;};
