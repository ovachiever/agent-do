// Filesystem-only session tests. No daemon, browser, or app is launched.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

let home, saved, sessions;
const storage = { cookies: [{ name: 'SID', value: 'synthetic-only', domain: '.youtube.com', path: '/' }], origins: [] };
function write(name, value) { writeFileSync(path.join(saved, name), JSON.stringify(value)); }
function ready() {
    const files = {};
    for (const file of ['storage.json', 'session-storage.json', 'state.json']) {
        files[file] = createHash('sha256').update(readFileSync(path.join(saved, file))).digest('hex');
    }
    write('import-status.json', { status: 'ready', attempt: 'test', files });
}

beforeEach(async () => {
    home = mkdtempSync(path.join(os.tmpdir(), 'browse-session-test-'));
    saved = path.join(home, '.agent-browse', 'sessions', 'fixture');
    mkdirSync(saved, { recursive: true });
    write('storage.json', storage);
    write('state.json', { url: 'https://www.youtube.com' });
    write('session-storage.json', {});
    write('meta.json', { name: 'fixture' });
    vi.spyOn(os, 'homedir').mockReturnValue(home);
    vi.resetModules();
    sessions = await import('./session.js');
});

afterEach(() => { vi.restoreAllMocks(); rmSync(home, { recursive: true, force: true }); });

describe('browser import freshness', () => {
    it.each(['failed', 'importing'])('blocks load and export after a %s attempt', (status) => {
        write('import-status.json', { status });
        const output = path.join(home, 'export.json');
        writeFileSync(output, 'untouched');
        expect(() => sessions.loadStorageState('fixture')).toThrow('BROWSER_IMPORT_STALE');
        expect(() => sessions.exportSession('fixture', output)).toThrow('BROWSER_IMPORT_STALE');
        expect(readFileSync(output, 'utf8')).toBe('untouched');
    });

    it('exports a complete generation and tolerates lastUsed updates', () => {
        ready();
        sessions.updateSessionLastUsed('fixture');
        const output = path.join(home, 'export.json');
        sessions.exportSession('fixture', output);
        expect(JSON.parse(readFileSync(output, 'utf8')).storage).toEqual(storage);
        expect(sessions.loadStorageState('fixture')).toEqual(storage);
    });

    it.each(['storage.json', 'session-storage.json', 'state.json'])('refuses changed generation data in %s', (file) => {
        ready();
        write(file, { changed: true });
        expect(() => sessions.exportSession('fixture', path.join(home, 'export.json'))).toThrow('BROWSER_IMPORT_STALE');
    });

    it('refuses malformed receipts and missing generation files', () => {
        writeFileSync(path.join(saved, 'import-status.json'), '{');
        expect(() => sessions.loadStorageState('fixture')).toThrow('BROWSER_IMPORT_STALE');
        ready();
        rmSync(path.join(saved, 'state.json'));
        expect(() => sessions.loadStorageState('fixture')).toThrow('BROWSER_IMPORT_STALE');
    });

    it('keeps legacy sessions usable before any browser refresh attempt', () => {
        expect(sessions.loadStorageState('fixture')).toEqual(storage);
    });

    it('only clears refusal after a complete explicit portable import', () => {
        write('import-status.json', { status: 'failed' });
        const portable = path.join(home, 'portable.json');
        writeFileSync(portable, JSON.stringify({ name: 'fixture', meta: {} }));
        expect(() => sessions.importSession(portable)).toThrow('complete storage state');
        expect(() => sessions.loadStorageState('fixture')).toThrow('BROWSER_IMPORT_STALE');
        writeFileSync(portable, JSON.stringify({ name: 'fixture', storage: { cookies: [], origins: [] } }));
        sessions.importSession(portable);
        expect(sessions.loadStorageState('fixture')).toEqual({ cookies: [], origins: [] });
        expect(existsSync(path.join(saved, 'import-status.json'))).toBe(false);
        expect(JSON.parse(readFileSync(path.join(saved, 'state.json'), 'utf8'))).toEqual({});
    });

    it('clears refusal after a complete explicit browser save', async () => {
        write('import-status.json', { status: 'failed' });
        const page = { evaluate: vi.fn().mockResolvedValue({}), viewportSize: () => null, url: () => 'https://example.com' };
        const context = { storageState: vi.fn().mockResolvedValue({ cookies: [], origins: [] }) };
        await sessions.saveSession(page, context, 'fixture');
        expect(sessions.loadStorageState('fixture')).toEqual({ cookies: [], origins: [] });
    });

    it.each(['..', '../escape', 'a/b', 'a\\b'])('refuses an escaping name: %s', (name) => {
        expect(() => sessions.loadStorageState(name)).toThrow('INVALID_SESSION_NAME');
    });
});
