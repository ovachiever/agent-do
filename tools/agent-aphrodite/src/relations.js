// Open, host-authored relationships. No renderer, preferred values, or taste model.
// This module runs unchanged in Node and in the browser.
const own=(object,key)=>Object.prototype.hasOwnProperty.call(object,key);
function require(condition,message) {if(!condition)throw new Error(message);}
function record(value,label) {require(value&&typeof value==='object'&&!Array.isArray(value),`${label} must be an object.`);}
function finite(value,label) {require(typeof value==='number'&&Number.isFinite(value),`${label} must be finite.`);return value;}
function words(value,label) {require(typeof value==='string'&&value.trim(),`${label} needs an explanation.`);}
const units=new Set(['','px','rem','em','vw','vh','vmin','vmax','%','deg','s','ms']);
const operators={
  add:{min:2,run:a=>a.reduce((x,y)=>x+y)},
  multiply:{min:2,run:a=>a.reduce((x,y)=>x*y)},
  subtract:{size:2,run:([a,b])=>a-b},
  divide:{size:2,run:([a,b])=>{require(b!==0,'Division by zero.');return a/b;}},
  power:{size:2,run:([a,b])=>a**b},
  min:{min:2,run:a=>Math.min(...a)},
  max:{min:2,run:a=>Math.max(...a)},
  clamp:{size:3,run:([value,low,high])=>{require(low<=high,'Clamp bounds are reversed.');return Math.max(low,Math.min(high,value));}},
  mix:{size:3,run:([a,b,t])=>a+(b-a)*t}
};

export function resolveRelations(graph,overrides={}) {
  record(graph,'Relationship graph');record(overrides,'Overrides');
  require(graph.schema===1&&graph.kind==='native-design-relations','Expected native-design-relations schema 1.');
  words(graph.intent,'Design intention');
  for(const key of ['inputs','relations','bindings'])record(graph[key],key);
  const ids=[...Object.keys(graph.inputs),...Object.keys(graph.relations)];
  require(new Set(ids).size===ids.length,'Inputs and derived relationships must have distinct names.');
  for(const id of ids)require(/^[A-Za-z][A-Za-z0-9_-]*$/.test(id),`Invalid node name: ${id}`);
  for(const id of Object.keys(overrides))require(own(graph.inputs,id),`Only declared inputs may be changed: ${id}`);
  const values=new Map(),dependencies=new Map(),visiting=new Set(),order=[];
  function expression(expr,refs,depth=0) {
    require(depth<64,'Expression nesting exceeds 64 levels.');
    if(typeof expr==='number')return finite(expr,'Literal');
    if(typeof expr==='string'){refs.add(expr);return visit(expr);}
    record(expr,'Expression');
    require(own(operators,expr.op),`Unknown relationship operator: ${expr.op}`);
    const operation=operators[expr.op];
    require(Array.isArray(expr.args)&&((operation.size&&expr.args.length===operation.size)||(operation.min&&expr.args.length>=operation.min)),`Invalid arguments for ${expr.op}.`);
    return finite(operation.run(expr.args.map(arg=>expression(arg,refs,depth+1))),`Result of ${expr.op}`);
  }
  function visit(id) {
    if(values.has(id))return values.get(id);
    require(!visiting.has(id),`Cyclic relationship at ${id}.`);
    require(own(graph.inputs,id)||own(graph.relations,id),`Unknown relationship node: ${id}`);
    visiting.add(id);
    let value;const refs=new Set();
    if(own(graph.inputs,id)) {
      const input=graph.inputs[id];record(input,id);words(input.why,`${id}.why`);
      finite(input.value,`${id}.value`);value=finite(own(overrides,id)?overrides[id]:input.value,id);
      if(input.range!==undefined) {
        require(Array.isArray(input.range)&&input.range.length===2,`${id}.range needs two bounds.`);
        const [low,high]=input.range.map(bound=>finite(bound,`${id}.range`));
        require(low<=high&&value>=low&&value<=high,`${id} is outside its authored range.`);
      }
    } else {
      const relation=graph.relations[id];record(relation,id);words(relation.why,`${id}.why`);
      value=expression(relation.expr,refs);
    }
    visiting.delete(id);values.set(id,value);dependencies.set(id,[...refs]);order.push(id);return value;
  }
  for(const id of ids)visit(id);
  const variables={};
  for(const [name,binding] of Object.entries(graph.bindings)) {
    require(/^--[A-Za-z][A-Za-z0-9_-]*$/.test(name),`Invalid CSS custom property: ${name}`);
    record(binding,name);require(typeof binding.node==='string',`${name} needs a node.`);
    require(units.has(binding.unit),`Unsupported CSS unit for ${name}.`);
    variables[name]=`${visit(binding.node)}${binding.unit}`;
  }
  return {values:Object.fromEntries(values),variables,dependencies:Object.fromEntries(dependencies),order,
    intent:graph.intent,authority:'Host-authored design relationships; no aesthetic score or layout prescription.'};
}

export function relationStylesheet(resolved) {
  return `:root {\n${Object.entries(resolved.variables).map(([name,value])=>`  ${name}: ${value};`).join('\n')}\n}\n`;
}

export function applyRelations(element,graph,overrides={}) {
  require(element?.style?.setProperty,'Apply relationships to an element with a style declaration.');
  const resolved=resolveRelations(graph,overrides); // Validate everything before touching the page.
  for(const [name,value] of Object.entries(resolved.variables))element.style.setProperty(name,value);
  return resolved;
}

export function reviseRelations(graph,overrides={}) {
  const before=resolveRelations(graph),after=resolveRelations(graph,overrides);
  const inputs=Object.fromEntries(Object.entries(graph.inputs).map(([id,input])=>[id,{...input,value:own(overrides,id)?overrides[id]:input.value}]));
  const changed=Object.keys(overrides).filter(id=>before.values[id]!==after.values[id]);
  const affected=new Set(changed);
  for(const id of after.order)if(after.dependencies[id].some(ref=>affected.has(ref)))affected.add(id);
  return {graph:{...graph,inputs},resolved:after,revision:{
    changedInputs:changed,affected:[...affected],
    changedValues:after.order.filter(id=>before.values[id]!==after.values[id]).map(id=>({node:id,from:before.values[id],to:after.values[id]})),
    bindings:Object.entries(graph.bindings).filter(([,binding])=>affected.has(binding.node)).map(([name])=>name),
    renderStatus:'unobserved',qualityVerdict:null
  }};
}
