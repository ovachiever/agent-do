import {check, finite, mean} from './core.js';

export function kernel(values, targets, scales) {
  check(values.length === targets.length && targets.length === scales.length && values.length, 'KERNEL_SHAPE', 'Kernel dimensions differ.');
  return Math.exp(-0.5 * values.reduce((sum, x, i) => {
    finite(x, 'descriptor'); finite(targets[i], 'target'); finite(scales[i], 'scale', Number.MIN_VALUE);
    return sum + ((x - targets[i]) / scales[i]) ** 2;
  }, 0));
}
export const affinity = (x, target, scale) => kernel([x], [target], [scale]);
export function modes(values, alternatives) {
  check(alternatives.length > 0, 'NO_MODES', 'A kernel needs at least one declared mode.');
  return Math.max(...alternatives.map(mode => kernel(values, mode.target, mode.scale)));
}
export function geometric(values) {
  check(values.length > 0, 'EMPTY_PRODUCT', 'An empty relation set is inapplicable.');
  values.forEach(x => finite(x, 'affinity', 0, 1));
  return values.some(x => x === 0) ? 0 : Math.exp(mean(values.map(Math.log)));
}
export function product(values) {
  check(values.length > 0, 'EMPTY_PRODUCT', 'A constellation must have relations.');
  values.forEach(x => finite(x, 'affinity', 0, 1));
  return values.some(x => x === 0) ? 0 : Math.exp(values.reduce((s, x) => s + Math.log(x), 0));
}
export const circular = (a, b) => ((a - b + 540) % 360) - 180;
export const separation = (a, b) => Math.hypot(Math.max(0, a.x - b.x - b.width, b.x - a.x - a.width), Math.max(0, a.y - b.y - b.height, b.y - a.y - a.height));
export const intersection = (a, b) => Math.max(0, Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x)) * Math.max(0, Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y));
export const area = b => b.width * b.height;
export const center = b => [b.x+b.width/2,b.y+b.height/2];

// Exact union area of axis-aligned observed rectangles. No pixel occupancy claim.
export function unionArea(rectangles) {
  const xs = [...new Set(rectangles.flatMap(r => [r.x, r.x+r.width]))].sort((a,b)=>a-b);
  let total = 0;
  for (let i=0;i<xs.length-1;i++) {
    const ranges = rectangles.filter(r => r.x < xs[i+1] && r.x+r.width > xs[i]).map(r => [r.y,r.y+r.height]).sort((a,b)=>a[0]-b[0]);
    let length=0, end=-Infinity;
    for (const [lo,hi] of ranges) { length += Math.max(0,hi-Math.max(lo,end)); end=Math.max(end,hi); }
    total += length*(xs[i+1]-xs[i]);
  }
  return total;
}
// RREF supplies x0 and a null-space basis: all generated x satisfy A*x=b.
export function affineSpace(matrix, rhs) {
  check(matrix.length > 0 && matrix.length === rhs.length, 'AFFINE_SHAPE', 'Invalid affine block.');
  const n=matrix[0].length;
  check(n>0 && matrix.every(row=>row.length===n), 'AFFINE_SHAPE', 'Ragged affine block.');
  matrix.flat().forEach(x=>finite(x,'matrix')); rhs.forEach(x=>finite(x,'rhs'));
  const a=matrix.map((r,i)=>[...r,rhs[i]]), pivots=[];
  let row=0;
  for(let col=0;col<n && row<a.length;col++) {
    let p=row;
    for(let j=row+1;j<a.length;j++) if(Math.abs(a[j][col])>Math.abs(a[p][col])) p=j;
    if(Math.abs(a[p][col])<1e-12) continue;
    [a[row],a[p]]=[a[p],a[row]];
    const divisor=a[row][col]; a[row]=a[row].map(x=>x/divisor);
    for(let j=0;j<a.length;j++) if(j!==row) {const f=a[j][col]; a[j]=a[j].map((x,k)=>x-f*a[row][k]);}
    pivots.push(col); row++;
  }
  check(a.every(r=>r.slice(0,n).some(x=>Math.abs(x)>1e-10)||Math.abs(r[n])<1e-10), 'IMPOSSIBLE_RELATION', 'Affine constraints are inconsistent.');
  const free=Array.from({length:n},(_,i)=>i).filter(i=>!pivots.includes(i));
  const x0=Array(n).fill(0); pivots.forEach((c,r)=>x0[c]=a[r][n]);
  const basis=free.map(c=>{const v=Array(n).fill(0);v[c]=1;pivots.forEach((pc,r)=>v[pc]=-a[r][c]);return v;});
  return {x0,basis,free,rank:pivots.length};
}
export function instantiate(space, z) {
  check(z.length===space.basis.length, 'AFFINE_COORDINATES', 'Wrong number of free coordinates.');
  return space.x0.map((x,i)=>x+z.reduce((s,v,j)=>s+v*space.basis[j][i],0));
}
export function residual(matrix, rhs, x) {return Math.max(...matrix.map((r,i)=>Math.abs(r.reduce((s,v,j)=>s+v*x[j],0)-rhs[i])));}

// Linear sRGB is a declared geometric color descriptor, not a perception model.
export function luminance(rgb) {
  const c=rgb.slice(0,3).map(v=>{const x=v/255; return x<=0.04045?x/12.92:((x+0.055)/1.055)**2.4;});
  return c[0]*0.2126+c[1]*0.7152+c[2]*0.0722;
}
export const contrast = (a,b) => (Math.max(luminance(a),luminance(b))+.05)/(Math.min(luminance(a),luminance(b))+.05);
export function rgb(hex) {check(/^#[0-9a-f]{6}$/i.test(hex),'COLOR','Use six-digit sRGB hex colors.');return [1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));}
export function mix(a,b,t) {const x=rgb(a),y=rgb(b);return '#'+x.map((v,i)=>Math.round(v+(y[i]-v)*t).toString(16).padStart(2,'0')).join('');}
export function colorDistance(a,b) {return Math.hypot(...a.slice(0,3).map((v,i)=>(v-b[i])/255))/Math.sqrt(3);}
