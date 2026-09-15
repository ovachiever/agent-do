import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {ROOT} from '../src/contracts.js';
import {read,verify} from '../src/core.js';
import {temp} from './helpers.js';

const cli=path.join(ROOT,'src/cli.js'),brief=path.join(ROOT,'examples/tideline.json');
function call(args,env={}) {return spawnSync(process.execPath,[cli,...args],{encoding:'utf8',timeout:10000,env:{...process.env,...env}});}
test('the complete candidate budget and objective are checked before any output or browser launch',()=>{
  for(const args of [['--budget','100','--steps','60'],['--objective','invented']]) {
    const out=path.join(temp(),'run'),result=call(['compose','--brief',brief,'--out',out,...args]);
    assert.equal(result.status,1);assert.equal(fs.existsSync(out),false);
  }
});
test('a real unavailable transport leaves a sealed failure and no selected export',()=>{
  const dir=temp(),run=path.join(dir,'failed'),site=path.join(dir,'site');
  const result=call(['compose','--brief',brief,'--out',run,'--budget','1'],{APHRODITE_AGENT_DO:path.join(dir,'nonexistent-owner')});
  assert.equal(result.status,1);assert.equal(JSON.parse(result.stdout).success,false);
  const stored=read(path.join(run,'result.json'));assert.equal(stored.selection.selected,null);assert.equal(stored.errors[0].code,'BROWSER_TRANSPORT');
  assert.ok(verify(run).verified);assert.equal(call(['export','--run',run,'--out',site]).status,1);assert.equal(fs.existsSync(site),false);
});
