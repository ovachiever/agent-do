/**
 * Session persistence module for agent-browse.
 * Phase 3: Save/load complete browser state including:
 * - Cookies (all domains)
 * - localStorage per origin
 * - IndexedDB per origin
 * - sessionStorage per origin
 * - Current URL and scroll position
 * - Viewport size
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync, readdirSync, rmSync } from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';

const SESSIONS_DIR = path.join(os.homedir(), '.agent-browse', 'sessions');

/**
 * Ensure sessions directory exists
 */
function ensureSessionsDir() {
    if (!existsSync(SESSIONS_DIR)) {
        mkdirSync(SESSIONS_DIR, { recursive: true });
    }
}

/**
 * Get session directory path
 */
function getSessionPath(name) {
    if (!name || name === '.' || name === '..' || /[/\\\0]/.test(name)) {
        throw new Error('[INVALID_SESSION_NAME] Session name must be a single directory name.');
    }
    ensureSessionsDir();
    return path.join(SESSIONS_DIR, name);
}

const SESSION_FILES = ['storage.json', 'session-storage.json', 'state.json', 'meta.json'];
const BOUND_FILES = ['storage.json', 'session-storage.json', 'state.json'];

/** Read one completed import generation. Failed or interrupted refreshes block
 * stale credentials even when a caller ignores import-browser's exit status. */
function readSessionFiles(name) {
    const sessionDir = getSessionPath(name);
    const statusPath = path.join(sessionDir, 'import-status.json');
    const readStatus = () => existsSync(statusPath) ? readFileSync(statusPath, 'utf8') : null;
    const before = readStatus();
    let receipt;
    if (before !== null) {
        try { receipt = JSON.parse(before); } catch {
            throw new Error('[BROWSER_IMPORT_STALE] Invalid import receipt; re-import this session.');
        }
        if (receipt?.status !== 'ready' || !receipt.files) {
            throw new Error('[BROWSER_IMPORT_STALE] The latest browser import failed or is incomplete; re-import before loading or exporting.');
        }
    }
    const files = {};
    for (const name of SESSION_FILES) {
        const file = path.join(sessionDir, name);
        if (existsSync(file)) {
            const bytes = readFileSync(file);
            if (receipt && BOUND_FILES.includes(name) &&
                createHash('sha256').update(bytes).digest('hex') !== receipt.files[name]) {
                throw new Error('[BROWSER_IMPORT_STALE] Saved data differs from the completed import; re-import this session.');
            }
            files[name] = JSON.parse(bytes.toString('utf8'));
        } else if (receipt && BOUND_FILES.includes(name)) {
            throw new Error('[BROWSER_IMPORT_STALE] Imported session is incomplete; re-import this session.');
        }
    }
    if (readStatus() !== before) {
        throw new Error('[BROWSER_IMPORT_STALE] Import changed while reading; retry after it completes.');
    }
    return files;
}

function clearImportReceipt(sessionDir) {
    // A complete explicit save or portable import establishes new state.
    rmSync(path.join(sessionDir, 'import-status.json'), { force: true });
}

/**
 * Save complete browser session state
 */
export async function saveSession(page, context, name, description = '') {
    const sessionDir = getSessionPath(name);
    if (!existsSync(sessionDir)) {
        mkdirSync(sessionDir, { recursive: true });
    }
    
    // 1. Save Playwright storage state (cookies + localStorage + IndexedDB)
    const storageState = await context.storageState({ indexedDB: true });
    writeFileSync(
        path.join(sessionDir, 'storage.json'),
        JSON.stringify(storageState, null, 2)
    );
    
    // 2. Save sessionStorage (not included in Playwright's storageState)
    const sessionStorage = await page.evaluate(() => {
        const data = {};
        for (let i = 0; i < sessionStorage.length; i++) {
            const key = sessionStorage.key(i);
            if (key) data[key] = sessionStorage.getItem(key);
        }
        return data;
    }).catch(() => ({}));
    
    writeFileSync(
        path.join(sessionDir, 'session-storage.json'),
        JSON.stringify(sessionStorage, null, 2)
    );
    
    // 3. Save page state (URL, scroll, viewport)
    const viewport = page.viewportSize() || { width: 1920, height: 1080 };
    const scrollPosition = await page.evaluate(() => ({
        x: window.scrollX,
        y: window.scrollY,
    })).catch(() => ({ x: 0, y: 0 }));
    
    const pageState = {
        url: page.url(),
        viewport,
        scroll: scrollPosition,
    };
    
    writeFileSync(
        path.join(sessionDir, 'state.json'),
        JSON.stringify(pageState, null, 2)
    );
    
    // 4. Save metadata
    const meta = {
        name,
        description,
        created: new Date().toISOString(),
        lastUsed: new Date().toISOString(),
        url: page.url(),
        cookieCount: storageState.cookies?.length || 0,
        originsCount: storageState.origins?.length || 0,
        indexedDbCount: (storageState.origins || []).reduce((count, origin) => count + ((origin.indexedDB || []).length), 0),
    };
    
    writeFileSync(
        path.join(sessionDir, 'meta.json'),
        JSON.stringify(meta, null, 2)
    );
    clearImportReceipt(sessionDir);
    
    return {
        path: sessionDir,
        meta,
    };
}

/**
 * Load session storage state for browser context creation
 */
export function loadStorageState(name) {
    return loadSessionSnapshot(name).storageState;
}

/** Read storage and per-origin sessionStorage from the same import generation. */
export function loadSessionSnapshot(name) {
    const files = readSessionFiles(name);
    if (!files['storage.json']) {
        throw new Error(`Session '${name}' not found`);
    }
    let sessionOrigins = files['session-storage.json']?.origins;
    if (!sessionOrigins) {
        sessionOrigins = {};
        const url = files['state.json']?.url;
        if (url && /^https?:/.test(url)) {
            sessionOrigins[new URL(url).origin] = files['session-storage.json'] || {};
        }
    }
    return { storageState: files['storage.json'], sessionOrigins };
}

/**
 * Restore session state to a page (after context creation)
 */
export async function restoreSession(page, name) {
    const sessionDir = getSessionPath(name);
    
    // 1. Restore sessionStorage
    const sessionStoragePath = path.join(sessionDir, 'session-storage.json');
    if (existsSync(sessionStoragePath)) {
        const sessionStorage = JSON.parse(readFileSync(sessionStoragePath, 'utf-8'));
        if (Object.keys(sessionStorage).length > 0) {
            await page.evaluate((data) => {
                for (const [key, value] of Object.entries(data)) {
                    sessionStorage.setItem(key, value);
                }
            }, sessionStorage).catch(() => {});
        }
    }
    
    // 2. Navigate to saved URL and restore scroll
    const statePath = path.join(sessionDir, 'state.json');
    if (existsSync(statePath)) {
        const state = JSON.parse(readFileSync(statePath, 'utf-8'));
        
        if (state.url && state.url !== 'about:blank') {
            await page.goto(state.url, { waitUntil: 'domcontentloaded' }).catch(() => {});
        }
        
        if (state.scroll && (state.scroll.x > 0 || state.scroll.y > 0)) {
            await page.evaluate((scroll) => {
                window.scrollTo(scroll.x, scroll.y);
            }, state.scroll).catch(() => {});
        }
    }
    
    // 3. Update lastUsed in meta
    const metaPath = path.join(sessionDir, 'meta.json');
    if (existsSync(metaPath)) {
        const meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
        meta.lastUsed = new Date().toISOString();
        writeFileSync(metaPath, JSON.stringify(meta, null, 2));
    }
    
    return { restored: true, path: sessionDir };
}

/**
 * List all saved sessions
 */
export function listSessions() {
    ensureSessionsDir();
    const sessions = [];
    
    try {
        const dirs = readdirSync(SESSIONS_DIR, { withFileTypes: true });
        for (const dir of dirs) {
            if (dir.isDirectory()) {
                const metaPath = path.join(SESSIONS_DIR, dir.name, 'meta.json');
                if (existsSync(metaPath)) {
                    const meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
                    sessions.push(meta);
                } else {
                    sessions.push({ name: dir.name, description: '(no metadata)' });
                }
            }
        }
    } catch (e) {
        // Directory doesn't exist or can't be read
    }
    
    return sessions;
}

/**
 * Delete a saved session
 */
export function deleteSession(name) {
    const sessionDir = getSessionPath(name);
    if (existsSync(sessionDir)) {
        rmSync(sessionDir, { recursive: true });
        return { deleted: true, name };
    }
    return { deleted: false, error: `Session '${name}' not found` };
}

/**
 * Export session to a portable file
 */
export function exportSession(name, outputPath) {
    const sessionDir = getSessionPath(name);
    if (!existsSync(sessionDir)) {
        throw new Error(`Session '${name}' not found`);
    }
    
    const exported = {
        version: 1,
        exportedAt: new Date().toISOString(),
        name,
    };
    
    const files = readSessionFiles(name);
    if (!files['storage.json']) {
        throw new Error(`Session '${name}' has no storage state`);
    }
    for (const [file, content] of Object.entries(files)) {
        exported[file.replace('.json', '')] = content;
    }
    writeFileSync(outputPath, JSON.stringify(exported, null, 2), { mode: 0o600 });
    return { path: outputPath, name };
}

/**
 * Import session from a portable file
 */
export function importSession(inputPath, name = null) {
    if (!existsSync(inputPath)) {
        throw new Error(`Import file not found: ${inputPath}`);
    }
    
    const data = JSON.parse(readFileSync(inputPath, 'utf-8'));
    if (!data.storage || !Array.isArray(data.storage.cookies) || !Array.isArray(data.storage.origins)) {
        throw new Error('Import file must contain a complete storage state (cookies and origins).');
    }
    const sessionName = name || data.name || `imported-${Date.now()}`;
    const sessionDir = getSessionPath(sessionName);
    
    if (!existsSync(sessionDir)) {
        mkdirSync(sessionDir, { recursive: true });
    }
    
    // Write session files
    if (data.storage) {
        writeFileSync(path.join(sessionDir, 'storage.json'), JSON.stringify(data.storage, null, 2));
    }
    writeFileSync(path.join(sessionDir, 'session-storage.json'), JSON.stringify(data['session-storage'] || {}, null, 2));
    writeFileSync(path.join(sessionDir, 'state.json'), JSON.stringify(data.state || {}, null, 2));
    
    // Update meta
    const meta = data.meta || {};
    meta.name = sessionName;
    meta.importedAt = new Date().toISOString();
    meta.importedFrom = inputPath;
    writeFileSync(path.join(sessionDir, 'meta.json'), JSON.stringify(meta, null, 2));
    clearImportReceipt(sessionDir);
    
    return { name: sessionName, path: sessionDir };
}

/**
 * Check if session exists
 */
export function sessionExists(name) {
    const sessionDir = getSessionPath(name);
    return existsSync(path.join(sessionDir, 'storage.json'));
}

/**
 * Get the saved URL from a session's state.json
 */
export function getSessionUrl(name) {
    const statePath = path.join(getSessionPath(name), 'state.json');
    if (existsSync(statePath)) {
        try {
            const state = JSON.parse(readFileSync(statePath, 'utf-8'));
            return state.url || null;
        } catch { return null; }
    }
    return null;
}

/**
 * Restore only sessionStorage to a page (without re-navigating)
 */
export async function restoreSessionStorage(page, name) {
    const sessionStoragePath = path.join(getSessionPath(name), 'session-storage.json');
    if (existsSync(sessionStoragePath)) {
        const data = JSON.parse(readFileSync(sessionStoragePath, 'utf-8'));
        let items = data;
        if (data && typeof data === 'object' && data.origins && !Array.isArray(data.origins)) {
            try {
                const origin = new URL(page.url()).origin;
                items = data.origins[origin] || {};
            } catch {
                items = {};
            }
        }
        if (items && Object.keys(items).length > 0) {
            await page.evaluate((items) => {
                for (const [key, value] of Object.entries(items)) {
                    sessionStorage.setItem(key, value);
                }
            }, items).catch(() => {});
        }
    }
}

/**
 * Update lastUsed timestamp in session metadata
 */
export function updateSessionLastUsed(name) {
    const metaPath = path.join(getSessionPath(name), 'meta.json');
    if (existsSync(metaPath)) {
        try {
            const meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
            meta.lastUsed = new Date().toISOString();
            writeFileSync(metaPath, JSON.stringify(meta, null, 2));
        } catch {}
    }
}
