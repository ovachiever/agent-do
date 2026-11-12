// Verification adapter tests. Playwright is mocked, so no browser can launch.
import { beforeEach, describe, expect, it, vi } from 'vitest';
vi.mock('playwright-core', () => ({ chromium: { launchServer: vi.fn(), connect: vi.fn() } }));
vi.mock('./session.js', () => ({ loadSessionSnapshot: vi.fn() }));
vi.mock('./storage-restore.js', () => ({ createRestoredContext: vi.fn() }));
import { chromium } from 'playwright-core';
import { loadSessionSnapshot } from './session.js';
import { createRestoredContext } from './storage-restore.js';
import { classifyYouTubeAccount, verifySession, YOUTUBE_ACCOUNT_URL } from './session-verify.js';

const signedIn = { host: 'www.youtube.com', pathname: '/account', loggedIn: true, avatar: true, signIn: false };
let page, browser, context, server;
beforeEach(() => {
    vi.resetAllMocks();
    page = {
        goto: vi.fn().mockResolvedValue({ status: () => 200 }),
        waitForFunction: vi.fn().mockResolvedValue(undefined),
        evaluate: vi.fn().mockResolvedValue(signedIn),
    };
    context = { newPage: vi.fn().mockResolvedValue(page), addInitScript: vi.fn().mockResolvedValue(undefined) };
    browser = { newContext: vi.fn().mockResolvedValue(context), close: vi.fn().mockResolvedValue(undefined) };
    server = { wsEndpoint: () => 'ws://127.0.0.1/fixture', close: vi.fn().mockResolvedValue(undefined), kill: vi.fn().mockResolvedValue(undefined) };
    chromium.launchServer.mockResolvedValue(server);
    chromium.connect.mockResolvedValue(browser);
    createRestoredContext.mockResolvedValue(context);
    loadSessionSnapshot.mockReturnValue({ storageState: { cookies: [], origins: [] }, sessionOrigins: {} });
});

describe('YouTube account evidence', () => {
    it('requires the account page, a positive login flag, and visible avatar', () => {
        expect(classifyYouTubeAccount(signedIn).signedIn).toBe(true);
        for (const changed of [
            { host: 'youtube.com.evil.test' }, { pathname: '/' }, { avatar: false }, { loggedIn: null },
        ]) expect(classifyYouTubeAccount({ ...signedIn, ...changed }).status).toBe('unverified');
    });

    it('reports sign-in UI or an account login redirect as signed out', () => {
        for (const changed of [{ host: 'accounts.google.com' }, { loggedIn: false }, { signIn: true }]) {
            expect(classifyYouTubeAccount({ ...signedIn, ...changed }).status).toBe('signed_out');
        }
    });

    it('cookie names and an unrecognized page never establish authentication', () => {
        expect(classifyYouTubeAccount({ cookies: ['SID', 'SAPISID', 'LOGIN_INFO'] }).signedIn).toBeNull();
        expect(classifyYouTubeAccount({ ...signedIn, host: 'consent.youtube.com' }).signedIn).toBeNull();
    });
});

describe('headless verification lane', () => {
    it('loads current storage, checks the account page and closes the isolated browser', async () => {
        const state = { cookies: [{ name: 'SID', value: 'synthetic-only' }], origins: [] };
        const sessionOrigins = { 'https://www.youtube.com': { fixture: 'synthetic-session' } };
        loadSessionSnapshot.mockReturnValue({ storageState: state, sessionOrigins });
        const result = await verifySession('fixture');
        expect(result.status).toBe('signed_in');
        expect(chromium.launchServer).toHaveBeenCalledWith(expect.objectContaining({ headless: true, host: '127.0.0.1', timeout: 20000 }));
        expect(createRestoredContext).toHaveBeenCalledWith(browser, state);
        expect(context.addInitScript).toHaveBeenCalledWith(expect.any(Function), sessionOrigins);
        expect(page.goto).toHaveBeenCalledWith(YOUTUBE_ACCOUNT_URL, expect.objectContaining({ timeout: 20000 }));
        expect(browser.close).toHaveBeenCalledOnce();
        expect(server.close).toHaveBeenCalledOnce();
        expect(JSON.stringify(result)).not.toContain('synthetic-only');
    });

    it('refuses stale imports before launching anything', async () => {
        loadSessionSnapshot.mockImplementation(() => { throw new Error('[BROWSER_IMPORT_STALE] failed import'); });
        await expect(verifySession('fixture')).rejects.toThrow('BROWSER_IMPORT_STALE');
        expect(chromium.launchServer).not.toHaveBeenCalled();
    });

    it('does not launch for unsupported verification sites', async () => {
        await expect(verifySession('fixture', 'unknown')).rejects.toThrow('UNSUPPORTED_VERIFY_SITE');
        expect(chromium.launchServer).not.toHaveBeenCalled();
    });

    it('reports signed-out pages even when storage contains login-looking cookies', async () => {
        page.evaluate.mockResolvedValue({ ...signedIn, loggedIn: false, signIn: true });
        expect((await verifySession('fixture')).code).toBe('SESSION_SIGNED_OUT');
        expect(browser.close).toHaveBeenCalledOnce();
    });

    it('fails closed on HTTP errors', async () => {
        page.goto.mockResolvedValue({ status: () => 429 });
        expect((await verifySession('fixture')).code).toBe('SESSION_AUTH_HTTP_ERROR');
        expect(page.evaluate).not.toHaveBeenCalled();
        expect(browser.close).toHaveBeenCalledOnce();
    });

    it('reports an unrecognized page after a readiness timeout', async () => {
        page.waitForFunction.mockRejectedValue(Object.assign(new Error('timeout'), { name: 'TimeoutError' }));
        page.evaluate.mockResolvedValue({ host: 'consent.youtube.com' });
        expect((await verifySession('fixture')).code).toBe('SESSION_AUTH_UNVERIFIED');
    });

    it.each(['restore', 'goto'])('refuses %s failure without dropping storage or leaking errors', async (method) => {
        (method === 'restore' ? createRestoredContext : page.goto).mockRejectedValue(new Error('secret-page-content'));
        const result = await verifySession('fixture');
        expect(result.code).toBe('SESSION_AUTH_CHECK_FAILED');
        expect(JSON.stringify(result)).not.toContain('secret-page-content');
        expect(browser.close).toHaveBeenCalledOnce();
        expect(createRestoredContext).toHaveBeenCalledTimes(1);
    });

    it('kills only its own server when normal browser cleanup fails', async () => {
        browser.close.mockRejectedValue(new Error('disconnected'));
        await verifySession('fixture');
        expect(server.kill).toHaveBeenCalledOnce();
    });

    it('bounds a stalled restore and still closes its owned server', async () => {
        vi.useFakeTimers();
        try {
            createRestoredContext.mockReturnValue(new Promise(() => {}));
            const pending = verifySession('fixture');
            await vi.advanceTimersByTimeAsync(120001);
            expect((await pending).reason).toBe('timeout');
            expect(server.close).toHaveBeenCalledOnce();
        } finally { vi.useRealTimers(); }
    });
});
