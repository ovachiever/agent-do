// Controlled browser interventions. These are model diagnostics, not human verdicts.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {derive} from '../src/construct.js';
import {bind} from '../src/contracts.js';
import {render} from '../src/render.js';
import {Browser,observe} from '../src/browser.js';
import {evaluate} from '../src/evaluate.js';
import {clone,write,seal} from '../src/core.js';
import {fixture,temp} from './helpers.js';

const dir=temp(),{context}=fixture(),browser=new Browser(dir),rows=[];
async function measure(id,c,topology,mutate=null) {
  const dest=path.join(dir,id);fs.mkdirSync(dest);
  const program=derive(c,'controlled',0,{},topology),file=path.join(dest,'page.html');
  let html=render(c,program);if(mutate)html=mutate(html);
  fs.writeFileSync(file,html);write(path.join(dest,'context.json'),c);write(path.join(dest,'program.json'),program);
  const observed=await observe(browser,c,program,file,path.join(dest,'observed'),{progress:e=>process.stdout.write(`${id}: ${e.condition}\n`)});
  const result=evaluate(c,program,observed);write(path.join(dest,'evaluation.json'),result);
  assert.ok(result.eligible,JSON.stringify({id,absent:result.absent,functional:result.functional}));
  rows.push({id,value:result.selectionValue,parts:result.conditions.map(c=>c.partBaseline),features:result.conditions.map(c=>c.features)});
  return {result,observed};
}
try {
  await browser.launch();
  const a=await measure('aligned-sequence',context,{opening:'partition',field:'sequence'});
  const b=await measure('partitioned-sequence',context,{opening:'partition',field:'partition'});
  assert.deepEqual(a.result.conditions.map(c=>c.partBaseline),b.result.conditions.map(c=>c.partBaseline));
  assert.notEqual(a.result.selectionValue,b.result.selectionValue);
  // A neutral wrapper changes neither semantic bindings nor actual layout/paint.
  const wrapped=await measure('neutral-wrapper',context,{opening:'partition',field:'sequence'},html=>html.replace(/(<p class="ap-terminal ap-body" id="body1"[^>]*>[^<]*<\/p>)/,'<div style="display:contents">$1</div>'));
  assert.deepEqual(a.result.conditions.map(c=>c.features),wrapped.result.conditions.map(c=>c.features));
  const brief=clone(context.brief);[brief.frame.bodyFont,brief.frame.displayFont]=[brief.frame.displayFont,brief.frame.bodyFont];
  brief.nodes.find(n=>n.id==='intro').text+=' The same reading must remain intact when a longer thought changes the rhythm of the page, including its supporting material and the spaces between them.';
  brief.copyBudget=600;brief.viewports.push({id:'small',width:320,height:640});
  const extended=bind(brief,context.model,context.assets);
  const changed=await measure('new-type-and-content',extended,{opening:'partition',field:'sequence'});
  assert.equal(changed.result.conditions.length,6);
  const oldType=a.observed.observations[0].nodes.find(n=>n.id==='title').font.fingerprint;
  const newType=changed.observed.observations[0].nodes.find(n=>n.id==='title').font.fingerprint;
  assert.notDeepEqual(oldType,newType,'The probe must see the actual changed font shape.');
  write(path.join(dir,'diagnostics.json'),{success:true,rows,claims:['placement changes full model while part baseline is identical','neutral wrapper preserves all nine family values','longer content and reassigned type measured at three widths'],humanPreference:null});
} catch(error) {write(path.join(dir,'failure.json'),{message:error.message,rows});throw error;}
finally {await browser.close();write(path.join(dir,'browser-receipts.json'),browser.receipts);seal(dir);process.stdout.write(`Relational browser diagnostics retained: ${dir}\n`);}
