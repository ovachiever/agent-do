import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import {ROOT} from './contracts.js';
import {check, Fault, digest, write} from './core.js';

export class Browser {
  constructor(label) {this.session=`aphrodite-${digest([label,process.pid]).slice(0,18)}`;this.receipts=[];}
  async call(verb,...args) {
    const executable=process.env.APHRODITE_AGENT_DO||'agent-do';
    const result=await new Promise((resolve,reject)=>{
      const child=spawn(executable,['browse',verb,...args.map(String)],{env:{...process.env,AGENT_BROWSER_SESSION:this.session},stdio:['ignore','pipe','pipe']});
      let stdout='',stderr='';const timer=setTimeout(()=>{child.kill('SIGTERM');reject(new Fault('BROWSER_TIMEOUT',`browse ${verb} exceeded 55 seconds.`));},55000);
      child.stdout.on('data',x=>stdout+=x);child.stderr.on('data',x=>stderr+=x);
      child.on('error',error=>{clearTimeout(timer);reject(new Fault('BROWSER_TRANSPORT',error.message));});
      child.on('close',code=>{clearTimeout(timer);resolve({code,stdout,stderr});});
    });
    let response;
    try {response=JSON.parse(result.stdout);}catch{if(verb==='close'&&result.stdout.trim()==='Browser closed')response={success:true,data:{closed:true}};else throw new Fault('BROWSER_RESPONSE',`Invalid browse ${verb} response.`,{code:result.code,stdout:result.stdout.slice(0,500),stderr:result.stderr.slice(0,500)});}
    this.receipts.push({verb,code:result.code,success:response.success===true,error:response.error??null});
    check(result.code===0&&response.success===true,'BROWSER_FAILED',`browse ${verb} failed.`,{response});
    return response.data;
  }
  async launch(){return this.call('launch');}
  async close(){return this.call('close');}
}
export async function observe(browser,context,program,file,out,{screenshots=true,progress=()=>{}}={}) {
  fs.mkdirSync(out,{recursive:true});const observations=[],failures=[];
  const source=fs.readFileSync(path.join(ROOT,'src/probe.js'),'utf8'),url=pathToFileURL(path.resolve(file)).href;
  for(const viewport of context.brief.viewports) {
    for(const state of context.brief.states) {
      const condition=`${viewport.id}-${state}`;
      progress({condition,status:'observing'});
      try {
        await browser.call('viewport',viewport.width,viewport.height);
        await browser.call('open',url);
        if(state==='expanded') {
          // Exercise native disclosure actions through the owner browser interface.
          for(const g of context.brief.groups.filter(g=>g.kind==='disclosure')) await browser.call('click',`#${g.id} > summary`);
        }
        await browser.call('eval','window.scrollTo(0,0)');
        const probe=(await browser.call('eval',source)).result;
        check(probe.url===url,'UNEXPECTED_NAVIGATION','Observation navigated away from the rendered candidate.');
        check(probe.programDigest===program.digest&&probe.contextDigest===context.digest,'STALE_RENDER','Page provenance does not match the candidate.');
        check(probe.viewport.width===viewport.width&&probe.viewport.height===viewport.height,'VIEWPORT','The observed viewport differs from its declaration.');
        probe.condition={id:condition,viewport:viewport.id,state};
        observations.push(probe);write(path.join(out,`${condition}.json`),probe);
        if(screenshots)await browser.call('screenshot',path.join(out,`${condition}.png`),'--full');
      }catch(error){failures.push({condition,code:error.code??'OBSERVATION',message:error.message});}
    }
  }
  const result={schema:1,programDigest:program.digest,contextDigest:context.digest,observations,failures};
  write(path.join(out,'observations.json'),result);return result;
}
