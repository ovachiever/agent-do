/**
 * Session persistence module for agent-browse.
 * Phase 3: Save/load complete browser state including:
 * - Cookies (all domains)
 * - localStorage per origin
 * - sessionStorage per origin
 * - Current URL and scroll position
 * - Viewport size
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync, readdirSync, rmSync } from 'node:fs';
import path from 'node:path';
import os from 'node:os';

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
    ensureSessionsDir();
    return path.join(SESSIONS_DIR, name);
}

/**
 * Save complete browser session state
 */
export async function saveSession(page, context, name, description = '') {
    const sessionDir = getSessionPath(name);
    if (!existsSync(sessionDir)) {
        mkdirSync(sessionDir, { recursive: true });
    }
    
    // 1. Save Playwright storage state (cookies + localStorage)
    const storageState = await context.storageState();
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
    const viewport = page.viewportSize() || { width: 1280, height: 720 };
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
    };
    
    writeFileSync(
        path.join(sessionDir, 'meta.json'),
        JSON.stringify(meta, null, 2)
    );
    
    return {
        path: sessionDir,
        meta,
    };
}

/**
 * Load session storage state for browser context creation
 */
export function loadStorageState(name) {
    const sessionDir = getSessionPath(name);
    const storagePath = path.join(sessionDir, 'storage.json');
    
    if (!existsSync(storagePath)) {
        throw new Error(`Session '${name}' not found`);
    }
    
    return JSON.parse(readFileSync(storagePath, 'utf-8'));
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
    
    // Read all session files
    for (const file of ['storage.json', 'session-storage.json', 'state.json', 'meta.json']) {
        const filePath = path.join(sessionDir, file);
        if (existsSync(filePath)) {
            exported[file.replace('.json', '')] = JSON.parse(readFileSync(filePath, 'utf-8'));
        }
    }
    
    writeFileSync(outputPath, JSON.stringify(exported, null, 2));
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
    const sessionName = name || data.name || `imported-${Date.now()}`;
    const sessionDir = getSessionPath(sessionName);
    
    if (!existsSync(sessionDir)) {
        mkdirSync(sessionDir, { recursive: true });
    }
    
    // Write session files
    if (data.storage) {
        writeFileSync(path.join(sessionDir, 'storage.json'), JSON.stringify(data.storage, null, 2));
    }
    if (data['session-storage']) {
        writeFileSync(path.join(sessionDir, 'session-storage.json'), JSON.stringify(data['session-storage'], null, 2));
    }
    if (data.state) {
        writeFileSync(path.join(sessionDir, 'state.json'), JSON.stringify(data.state, null, 2));
    }
    
    // Update meta
    const meta = data.meta || {};
    meta.name = sessionName;
    meta.importedAt = new Date().toISOString();
    meta.importedFrom = inputPath;
    writeFileSync(path.join(sessionDir, 'meta.json'), JSON.stringify(meta, null, 2));
    
    return { name: sessionName, path: sessionDir };
}

/**
 * Check if session exists
 */
export function sessionExists(name) {
    const sessionDir = getSessionPath(name);
    return existsSync(path.join(sessionDir, 'storage.json'));
}
