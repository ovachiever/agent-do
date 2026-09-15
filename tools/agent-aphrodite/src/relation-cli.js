#!/usr/bin/env node
// The same revision implementation used by agent-do, portable with a native packet.
import {parseArgs} from 'node:util';
import {read} from './core.js';
import {nativeRevision,parseAssignments} from './native.js';
try {
  const {values}=parseArgs({options:{relations:{type:'string'},out:{type:'string'},set:{type:'string',multiple:true}},allowPositionals:false});
  if(!values.relations||!values.out)throw new Error('Use --relations graph.json --out new-directory [--set input=value].');
  process.stdout.write(JSON.stringify(nativeRevision(read(values.relations),parseAssignments(values.set),values.out),null,2)+'\n');
} catch(error) {process.stderr.write(JSON.stringify({success:false,error:error.message})+'\n');process.exitCode=1;}
