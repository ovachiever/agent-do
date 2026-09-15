import test from 'node:test';
import assert from 'node:assert/strict';
import {kernel,modes,affinity,product,geometric,affineSpace,instantiate,residual,unionArea,circular} from '../src/math.js';

test('affinities peak at the relation target, rather than at a maximal ingredient',()=>{
  assert.equal(affinity(2,2,.3),1);assert.ok(affinity(1,2,.3)<1);assert.ok(affinity(3,2,.3)<1);
  assert.throws(()=>kernel([1],[1],[0]));assert.throws(()=>kernel([NaN],[1],[1]));
});
test('alternative modes keep both arrangements rather than averaging them',()=>{
  const options=[{target:[-2],scale:[.3]},{target:[2],scale:[.3]}];
  assert.equal(modes([-2],options),1);assert.equal(modes([2],options),1);assert.ok(modes([0],options)<.01);
});
test('a three-relation conjunction has a nonzero mixed difference',()=>{
  let mixed=0;for(const a of [0,1])for(const b of [0,1])for(const c of [0,1])mixed+=(-1)**(3-a-b-c)*product([a?.9:.2,b?.9:.2,c?.9:.2]);
  assert.ok(Math.abs(mixed-.7**3)<1e-12);assert.equal(product([0,.8,.9]),0);assert.throws(()=>product([]));assert.equal(geometric([.25,1]),.5);
});
test('the elastic relation is invariant to common scale and can reverse preference',()=>{
  const score=(h,g,b)=>affinity(Math.log(g/b),Math.log(5.5)-.55*Math.log(h/b),.7);
  assert.ok(Math.abs(score(96,24,18)-score(192,48,36))<1e-12);
  assert.ok(score(120,24,18)>score(120,72,18));assert.ok(score(32,72,18)>score(32,24,18));
});
test('affine constructors preserve coupled constraints across their free coordinates',()=>{
  const A=[[1,2,-1,0],[0,1,1,-1]],b=[.5,-.25],space=affineSpace(A,b);
  for(let i=-10;i<=10;i++)assert.ok(residual(A,b,instantiate(space,[i*.13,i*.31]))<1e-10);
  assert.throws(()=>affineSpace([[1],[1]],[1,2]));
});
test('foreground union accounts for overlap and is translation invariant',()=>{
  const boxes=[{x:0,y:0,width:10,height:10},{x:5,y:5,width:10,height:10}];
  assert.equal(unionArea(boxes),175);assert.equal(unionArea(boxes.map(b=>({...b,x:b.x+600,y:b.y-70}))),175);
  assert.equal(circular(1,359),2);
});
