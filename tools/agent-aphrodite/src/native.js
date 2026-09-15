import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {check,read,write,directory,digest,seal} from './core.js';
import {resolveRelations,reviseRelations,relationStylesheet} from './relations.js';

const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
export function parseAssignments(assignments=[]) {
  const entries=assignments.map(assignment=>{
    const at=assignment.indexOf('='),name=assignment.slice(0,at),raw=assignment.slice(at+1),value=Number(raw);
    check(at>0&&/^[A-Za-z][A-Za-z0-9_-]*$/.test(name)&&raw.trim()&&Number.isFinite(value),'CHANGE','Use --set inputName=number.');
    return [name,value];
  });
  check(new Set(entries.map(([name])=>name)).size===entries.length,'CHANGE','Do not assign an input twice.');
  return Object.fromEntries(entries);
}

export function nativeRevision(graph,changes,out) {
  const result=reviseRelations(graph,changes); // Refuse invalid graphs before creating an output.
  const dest=directory(out),revision={...result.revision,parent:digest(graph),successor:digest(result.graph)};
  write(path.join(dest,'relations.json'),result.graph);
  write(path.join(dest,'resolution.json'),result.resolved);
  write(path.join(dest,'revision.json'),revision);
  fs.writeFileSync(path.join(dest,'relations.css'),relationStylesheet(result.resolved),{flag:'wx'});
  seal(dest);
  return {directory:dest,stylesheet:path.join(dest,'relations.css'),...revision,
    next:'Load the CSS variables in your own frontend, render, and inspect the composition. The tool has not changed or judged your page.'};
}

export function nativePacket({brief,context,relations,out}) {
  check(!(brief&&context),'INPUT','Choose a plain brief or an existing engine context.');
  const content=brief?fs.readFileSync(brief,'utf8'):null;
  if(brief)check(content.trim(),'BRIEF','The brief must contain content.');
  const graph=relations?read(relations):{schema:1,kind:'native-design-relations',
    intent:'Author the design in the native frontend. Encode the relationships that serve its particular intention.',inputs:{},relations:{},bindings:{}};
  const resolved=resolveRelations(graph);
  const source=path.join(root,'native');
  const files=['START-HERE.md','RELATIONSHIPS.md','EXAMPLE.json'];
  const contents=files.map(name=>[name,fs.readFileSync(path.join(source,name))]);
  const dest=directory(out);
  for(const [name,bytes] of contents)fs.writeFileSync(path.join(dest,name),bytes,{flag:'wx'});
  if(content!==null)fs.writeFileSync(path.join(dest,'BRIEF.txt'),content,{flag:'wx'});
  if(context)write(path.join(dest,'SOURCE-CONTEXT.json'),context);
  write(path.join(dest,'relations.json'),graph);write(path.join(dest,'resolution.json'),resolved);
  fs.writeFileSync(path.join(dest,'relations.css'),relationStylesheet(resolved),{flag:'wx'});
  const runtime=path.join(dest,'runtime');fs.mkdirSync(runtime);
  for(const name of ['core.js','relations.js','native.js','relation-cli.js'])fs.copyFileSync(path.join(root,'src',name),path.join(runtime,name));
  write(path.join(runtime,'package.json'),{type:'module',private:true});
  write(path.join(dest,'packet.json'),{schema:1,mode:'native',authorship:'host AI in the existing frontend',
    sourceBrief:brief?path.resolve(brief):null,contextDigest:context?.digest??null,relationshipDigest:digest(graph),
    rendererIncluded:false,scoringModelIncluded:false,qualityValidation:'not yet demonstrated against normal AI frontend design',
    externalInputs:'Repository code, assets, and links named in a plain brief stay in their original locations. Context assets, if supplied, remain embedded in SOURCE-CONTEXT.json.'});
  seal(dest);
  return {directory:dest,entry:path.join(dest,'START-HERE.md'),mode:'native',rendererIncluded:false,scoringModelIncluded:false};
}
