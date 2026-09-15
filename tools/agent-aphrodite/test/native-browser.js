// Functional fixture for unrestricted frontend code, not an aesthetic demonstration.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {ROOT} from '../src/contracts.js';
import {read,write,fileHash,seal,verify} from '../src/core.js';
import {Browser} from '../src/browser.js';
import {temp} from './helpers.js';

export async function nativeBrowserTest() {
  const dir=temp(),owner=path.resolve(ROOT,'../../agent-do'),packet=path.join(dir,'packet'),revision=path.join(dir,'revision');
  const commands=[];
  function cli(args) {
    const result=spawnSync(owner,['aphrodite',...args],{encoding:'utf8',timeout:15000});
    commands.push({args,exit:result.status,stderr:result.stderr});assert.equal(result.status,0,result.stderr);
    return JSON.parse(result.stdout).data;
  }
  cli(['packet','--relations',path.join(ROOT,'native/EXAMPLE.json'),'--out',packet]);
  cli(['revise','--relations',path.join(packet,'relations.json'),'--set','presence=1.5','--out',revision]);
  const page=path.join(dir,'native.html');
  fs.writeFileSync(page,`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Native frontend contract fixture</title>
<style>
:root{--heading-size:4rem;--support-gap:2rem}html{font-size:16px}body{margin:0;color:#243733;background:#eaf0ed;font-family:Arial,sans-serif}main{padding:clamp(20px,4vw,64px);display:grid;grid-template-columns:minmax(0,3fr) minmax(180px,1fr);gap:32px}h1{font:var(--heading-size)/1 Georgia,serif;margin:0;overflow-wrap:anywhere}.support{margin:var(--support-gap) 0 32px}aside{align-self:start;background:#153c35;color:white;padding:20px;position:sticky;top:20px}aside h2{font-size:18px}.catalog{border-collapse:collapse;width:100%}td{border-top:1px solid #a5b5af;padding:12px 0}td:last-child{text-align:right}button{font:inherit;padding:12px;border:1px solid currentColor;background:transparent;color:inherit;cursor:pointer}svg{width:100%;height:80px}canvas{width:100%;height:30px;background:repeating-linear-gradient(90deg,#cee4d8 0 8px,transparent 8px 16px)}@media(max-width:600px){main{grid-template-columns:1fr}aside{position:static}}button:focus-visible{outline:3px solid #d4a867}
</style><main><section><h1>Native composition</h1><p class="support">A functional test of coupled variables in independently authored markup.</p><table class="catalog"><tbody><tr><td>Score viewer</td><td>Open</td></tr><tr><td>Audio controls</td><td>Ready</td></tr><tr><td>Catalog</td><td>Three entries</td></tr></tbody></table><svg viewBox="0 0 400 80" aria-label="Native vector material" role="img"><path d="M0 65 Q80 -20 160 40 T400 15" fill="none" stroke="currentColor" stroke-width="3"/></svg><canvas aria-label="Native canvas surface"></canvas></section><aside><h2>Independent controls</h2><button id="play" type="button" aria-pressed="false">Play</button><details><summary>Technical notes</summary>Native disclosures remain interactive.</details></aside></main><script>document.getElementById('play').addEventListener('click',e=>{const playing=e.currentTarget.getAttribute('aria-pressed')==='true';e.currentTarget.setAttribute('aria-pressed',String(!playing));e.currentTarget.textContent=playing?'Play':'Pause';});</script></html>`,{flag:'wx'});
  const original=fileHash(page),graph=read(path.join(packet,'relations.json'));
  const moduleURL='data:text/javascript;base64,'+fs.readFileSync(path.join(packet,'runtime/relations.js')).toString('base64');
  const measurements=[],browser=new Browser(dir+'-native');
  const probe=`(()=>{const h=document.querySelector('h1'),p=document.querySelector('.support'),aside=document.querySelector('aside');return {heading:parseFloat(getComputedStyle(h).fontSize),gap:parseFloat(getComputedStyle(p).marginTop),ink:getComputedStyle(h).color,asideInk:getComputedStyle(aside).color,asideTitle:getComputedStyle(aside.querySelector('h2')).fontSize,grid:getComputedStyle(document.querySelector('main')).gridTemplateColumns,rows:[...document.querySelectorAll('tr')].map(n=>n.textContent),svg:document.querySelector('svg').outerHTML,canvas:document.querySelectorAll('canvas').length,pressed:document.querySelector('#play').getAttribute('aria-pressed'),disclosure:document.querySelector('details').open}})()`;
  try {
    await browser.launch();
    for(const width of [1280,390]) {
      await browser.call('viewport',width,900);await browser.call('open',pathToFileURL(page).href);
      await browser.call('click','#play');await browser.call('click','summary');
      const before=(await browser.call('eval',probe)).result;
      const result=(await browser.call('eval',`(async()=>{const {applyRelations}=await import(${JSON.stringify(moduleURL)});return applyRelations(document.querySelector('main'),${JSON.stringify(graph)},{presence:1.5});})()`)).result;
      const after=(await browser.call('eval',probe)).result;
      assert.equal(result.values.headingSize,6);assert.equal(after.heading,96);assert.ok(Math.abs(after.gap-32/1.5)<0.01);
      for(const key of ['ink','asideInk','asideTitle','grid','rows','svg','canvas','pressed','disclosure'])assert.deepEqual(after[key],before[key],`Native ${key} must survive relationship application.`);
      await browser.call('focus','#play');await browser.call('press','Enter');
      assert.equal((await browser.call('eval',probe)).result.pressed,'false','The original event listener still handles keyboard activation.');
      await browser.call('screenshot',path.join(dir,`native-${width}.png`),'--full');
      measurements.push({width,before,after});
    }
    await browser.call('open',pathToFileURL(page).href);
    const css=fs.readFileSync(path.join(revision,'relations.css'),'utf8');
    await browser.call('eval',`(()=>{const style=document.createElement('style');style.textContent=${JSON.stringify(css)};document.head.append(style);})()`);
    const compiled=(await browser.call('eval',probe)).result;
    assert.equal(compiled.heading,96);assert.ok(Math.abs(compiled.gap-32/1.5)<0.01);
    assert.equal(fileHash(page),original,'Neither path rewrites the native frontend source.');
    write(path.join(dir,'validation.json'),{success:true,measurements,compiled,sourceHash:original,commands,
      bundles:[{path:packet,...verify(packet)},{path:revision,...verify(revision)}],
      claims:['open graph executes in a native browser frontend','coupled changes reach CSS','markup, material, layout, unrelated treatments and interactions survive','portable graph and CLI stylesheet agree'],aestheticImprovementValidated:false});
  } catch(error) {
    write(path.join(dir,'failure.json'),{success:false,message:error.message,commands,measurements});throw error;
  } finally {await browser.close();write(path.join(dir,'browser-receipts.json'),browser.receipts);seal(dir);}
  process.stdout.write(`Native Aphrodite browser contract passed. Evidence: ${dir}\n`);return dir;
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))await nativeBrowserTest();
