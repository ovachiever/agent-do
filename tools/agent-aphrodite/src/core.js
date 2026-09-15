import {createHash} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export class Fault extends Error {
  constructor(code, message, detail = {}) { super(message); this.code = code; this.detail = detail; }
}
export function check(condition, code, message, detail) {
  if (!condition) throw new Fault(code, message, detail);
}
export function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
  check(value !== undefined && !(typeof value === 'number' && !Number.isFinite(value)), 'INVALID_JSON', 'Values must be finite JSON.');
  return JSON.stringify(value);
}
export const digest = value => createHash('sha256').update(canonical(value)).digest('hex');
export const fileHash = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
export const bytesHash = bytes => createHash('sha256').update(bytes).digest('hex');
export const clone = value => JSON.parse(canonical(value));
export function read(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch (e) { throw new Fault('READ_JSON', `Cannot read JSON: ${file}`, {reason: e.message}); }
}
export function write(file, value) {
  fs.mkdirSync(path.dirname(file), {recursive: true});
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, {flag: 'wx'});
}
export function directory(target) {
  check(!fs.existsSync(target), 'OUTPUT_EXISTS', 'Use a new output directory; existing evidence is immutable.', {target});
  fs.mkdirSync(target, {recursive: true});
  return path.resolve(target);
}
export function seal(dir) {
  const files = {};
  function visit(base) {
    for (const name of fs.readdirSync(base).sort()) {
      const p = path.join(base, name), s = fs.lstatSync(p);
      check(!s.isSymbolicLink(), 'SYMLINK', 'Artifact bundles cannot contain symlinks.');
      if (s.isDirectory()) visit(p);
      else if (p !== path.join(dir, 'manifest.json')) files[path.relative(dir, p).split(path.sep).join('/')] = fileHash(p);
    }
  }
  visit(dir);
  write(path.join(dir, 'manifest.json'), {schema: 1, algorithm: 'sha256', files});
  return digest(files);
}
export function verify(dir) {
  const manifest = read(path.join(dir, 'manifest.json'));
  check(manifest.schema === 1 && manifest.algorithm === 'sha256', 'MANIFEST', 'Unsupported artifact manifest.');
  for (const [name, expected] of Object.entries(manifest.files)) {
    const file = within(dir, name);
    const root = fs.realpathSync(dir);
    check(fs.existsSync(file) && fs.realpathSync(file).startsWith(root + path.sep), 'PATH_ESCAPE', 'Manifest entries must resolve inside their bundle.', {name});
    check(fs.existsSync(file) && !fs.lstatSync(file).isSymbolicLink() && fileHash(file) === expected, 'STALE_ARTIFACT', `Artifact changed or missing: ${name}`);
  }
  return {verified: true, files: Object.keys(manifest.files).length, digest: digest(manifest.files)};
}
export function within(base, name) {
  const root = path.resolve(base), result = path.resolve(root, name);
  check(result.startsWith(root + path.sep), 'PATH_ESCAPE', 'Artifact path must remain inside its bundle.', {name});
  return result;
}
export function unique(items, key = 'id') {
  check(new Set(items.map(v => v[key])).size === items.length, 'DUPLICATE_ID', `Duplicate ${key}.`);
}
export const mean = values => values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
export const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
export const almost = (a, b, eps = 1e-8) => Math.abs(a - b) <= eps * Math.max(1, Math.abs(a), Math.abs(b));
export const keyed = (...parts) => Number.parseInt(digest(parts).slice(0, 13), 16) / 0x10000000000000;
export const escapeHTML = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function finite(value, label, min = -Infinity, max = Infinity) {
  check(typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max, 'NUMBER', `${label} must be finite in [${min}, ${max}].`);
  return value;
}
export function keys(value, allowed, name) {
  check(value && typeof value === 'object' && !Array.isArray(value), 'OBJECT', `${name} must be an object.`);
  const unknown = Object.keys(value).filter(k => !allowed.includes(k));
  check(!unknown.length, 'UNKNOWN_FIELD', `Unknown fields in ${name}.`, {unknown});
}
export function text(value, label, max = 30000) {
  check(typeof value === 'string' && value.trim().length > 0 && value.length <= max, 'TEXT', `${label} must be nonempty text (maximum ${max} characters).`);
  return value;
}
