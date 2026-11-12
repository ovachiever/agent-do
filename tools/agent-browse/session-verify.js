import { chromium } from 'playwright-core';
import { loadSessionSnapshot } from './session.js';
import { createRestoredContext } from './storage-restore.js';

export const YOUTUBE_ACCOUNT_URL = 'https://www.youtube.com/account';

async function bounded(promise, milliseconds) {
    let timer;
    try {
        return await Promise.race([promise, new Promise((_, reject) => {
            timer = setTimeout(() => reject(Object.assign(new Error('Verification timeout'), { name: 'TimeoutError' })), milliseconds);
        })]);
    } finally { clearTimeout(timer); }
}

async function closeOwnedBrowser(browser, server) {
    try {
        if (browser) await bounded(browser.close(), 3000);
        if (server) await bounded(server.close(), 3000);
    } catch {
        // BrowserServer.kill terminates only the process tree it launched.
        // A stuck renderer must not leave a hidden process after a refusal.
        if (server) await server.kill();
    }
}

// Runs in the page. Return evidence flags only, never account text or tokens.
export function youtubeAccountEvidence() {
    const visible = (selector) => [...document.querySelectorAll(selector)].some((element) => {
        const style = getComputedStyle(element);
        return element.getClientRects().length > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    });
    return {
        host: location.hostname,
        pathname: location.pathname,
        loggedIn: window.ytcfg?.get?.('LOGGED_IN') ?? null,
        avatar: visible('#avatar-btn'),
        signIn: visible('a[href*="accounts.google.com/ServiceLogin"], a[href*="accounts.google.com/v3/signin"], ytd-button-renderer[is-sign-in-button]'),
    };
}

export function classifyYouTubeAccount(evidence) {
    const youtube = ['www.youtube.com', 'youtube.com'].includes(evidence.host);
    if (evidence.host === 'accounts.google.com' ||
        (youtube && (evidence.signIn || evidence.loggedIn === false))) {
        return { status: 'signed_out', signedIn: false, code: 'SESSION_SIGNED_OUT' };
    }
    if (youtube && evidence.pathname === '/account' && evidence.loggedIn === true && evidence.avatar === true) {
        return { status: 'signed_in', signedIn: true };
    }
    return { status: 'unverified', signedIn: null, code: 'SESSION_AUTH_UNVERIFIED' };
}

/** A fresh headless context proves server acceptance independently of the
 * saved cookie names and any already-running browse daemon. */
export async function verifySession(name, site = 'youtube') {
    if (site !== 'youtube') throw new Error('[UNSUPPORTED_VERIFY_SITE] Supported site: youtube.');
    const { storageState, sessionOrigins } = loadSessionSnapshot(name); // Refuse stale imports before launching.
    let browser;
    let server;
    let stage = 'launch';
    try {
        server = await chromium.launchServer({
            headless: true,
            host: '127.0.0.1',
            executablePath: process.env.AGENT_BROWSER_EXECUTABLE_PATH,
            timeout: 20000,
        });
        browser = await chromium.connect(server.wsEndpoint(), { timeout: 20000 });
        stage = 'restore';
        const context = await bounded(createRestoredContext(browser, storageState), 120000);
        await context.addInitScript((origins) => {
            for (const [key, value] of Object.entries(origins[location.origin] || {})) {
                sessionStorage.setItem(key, value);
            }
        }, sessionOrigins);
        const page = await context.newPage();
        stage = 'navigate';
        const response = await page.goto(YOUTUBE_ACCOUNT_URL, { waitUntil: 'domcontentloaded', timeout: 20000 });
        if (!response || response.status() >= 400) {
            return { session: name, site, status: 'unverified', signedIn: null, code: 'SESSION_AUTH_HTTP_ERROR' };
        }
        // The DOM may hydrate after navigation. A timeout is an unverified
        // result, never permission to infer authentication from cookies.
        stage = 'observe';
        try {
            await page.waitForFunction(() => {
                const loggedIn = window.ytcfg?.get?.('LOGGED_IN');
                return location.hostname === 'accounts.google.com' || loggedIn === false ||
                    (loggedIn === true && document.querySelector('#avatar-btn')?.getClientRects().length > 0) ||
                    [...document.querySelectorAll('a[href*="accounts.google.com/ServiceLogin"], a[href*="accounts.google.com/v3/signin"], ytd-button-renderer[is-sign-in-button]')]
                        .some((element) => element.getClientRects().length > 0);
            }, undefined, { timeout: 15000 });
        } catch (error) {
            if (error.name !== 'TimeoutError') throw error;
        }
        const evidence = await page.evaluate(youtubeAccountEvidence);
        return { session: name, site, ...classifyYouTubeAccount(evidence), evidence, checkedAt: new Date().toISOString() };
    } catch (error) {
        // Browser errors can contain page data, URLs or local credential paths.
        const message = error.message || '';
        const reason = /Invalid string length|Cannot create a string|too large|Maximum call stack/i.test(message) ? 'storage_size_limit'
            : /Object reference chain/i.test(message) ? 'storage_reference_limit'
            : /Unable to restore IndexedDB|IDBObjectStore|IndexedDB/i.test(message) ? 'indexeddb_restore_failed'
            : /storageState\.cookies|cookie/i.test(message) ? 'cookie_state_rejected'
            : /Target.*closed|browser.*closed|has been closed/i.test(message) ? 'browser_closed'
            : /Timeout|timed out/i.test(message) ? 'timeout'
            : 'browser_error';
        return { session: name, site, status: 'unverified', signedIn: null, code: 'SESSION_AUTH_CHECK_FAILED', stage, reason, errorType: error.name };
    } finally {
        await closeOwnedBrowser(browser, server);
    }
}
