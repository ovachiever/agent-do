import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { BrowserManager } from './browser.js';
describe('BrowserManager', () => {
    let browser;
    beforeAll(async () => {
        browser = new BrowserManager();
        await browser.launch({ headless: true });
    });
    afterAll(async () => {
        await browser.close();
    });
    describe('launch and close', () => {
        it('should report as launched', () => {
            expect(browser.isLaunched()).toBe(true);
        });
        it('should have a page', () => {
            const page = browser.getPage();
            expect(page).toBeDefined();
        });
    });
    describe('navigation', () => {
        it('should navigate to URL', async () => {
            const page = browser.getPage();
            await page.goto('https://example.com');
            expect(page.url()).toBe('https://example.com/');
        });
        it('should get page title', async () => {
            const page = browser.getPage();
            const title = await page.title();
            expect(title).toBe('Example Domain');
        });
    });
    describe('element interaction', () => {
        it('should find element by selector', async () => {
            const page = browser.getPage();
            const heading = await page.locator('h1').textContent();
            expect(heading).toBe('Example Domain');
        });
        it('should check element visibility', async () => {
            const page = browser.getPage();
            const isVisible = await page.locator('h1').isVisible();
            expect(isVisible).toBe(true);
        });
        it('should count elements', async () => {
            const page = browser.getPage();
            const count = await page.locator('p').count();
            expect(count).toBeGreaterThan(0);
        });
    });
    describe('screenshots', () => {
        it('should take screenshot as buffer', async () => {
            const page = browser.getPage();
            const buffer = await page.screenshot();
            expect(buffer).toBeInstanceOf(Buffer);
            expect(buffer.length).toBeGreaterThan(0);
        });
    });
    describe('evaluate', () => {
        it('should evaluate JavaScript', async () => {
            const page = browser.getPage();
            const result = await page.evaluate(() => document.title);
            expect(result).toBe('Example Domain');
        });
        it('should evaluate with arguments', async () => {
            const page = browser.getPage();
            const result = await page.evaluate((x) => x * 2, 5);
            expect(result).toBe(10);
        });
    });
    describe('tabs', () => {
        it('should create new tab', async () => {
            const result = await browser.newTab();
            expect(result.index).toBe(1);
            expect(result.total).toBe(2);
        });
        it('should list tabs', async () => {
            const tabs = await browser.listTabs();
            expect(tabs.length).toBe(2);
        });
        it('should close tab', async () => {
            // Switch to second tab and close it
            const page = browser.getPage();
            const tabs = await browser.listTabs();
            if (tabs.length > 1) {
                const result = await browser.closeTab(1);
                expect(result.remaining).toBe(1);
            }
        });
    });
    describe('context operations', () => {
        it('should get cookies from context', async () => {
            const page = browser.getPage();
            const cookies = await page.context().cookies();
            expect(Array.isArray(cookies)).toBe(true);
        });
        it('should set and get cookies', async () => {
            const page = browser.getPage();
            const context = page.context();
            await context.addCookies([{ name: 'test', value: 'value', url: 'https://example.com' }]);
            const cookies = await context.cookies();
            const testCookie = cookies.find((c) => c.name === 'test');
            expect(testCookie?.value).toBe('value');
        });
        it('should clear cookies', async () => {
            const page = browser.getPage();
            const context = page.context();
            await context.clearCookies();
            const cookies = await context.cookies();
            expect(cookies.length).toBe(0);
        });
    });
    describe('storage via evaluate', () => {
        it('should set and get localStorage', async () => {
            const page = browser.getPage();
            await page.evaluate(() => localStorage.setItem('testKey', 'testValue'));
            const value = await page.evaluate(() => localStorage.getItem('testKey'));
            expect(value).toBe('testValue');
        });
        it('should clear localStorage', async () => {
            const page = browser.getPage();
            await page.evaluate(() => localStorage.clear());
            const value = await page.evaluate(() => localStorage.getItem('testKey'));
            expect(value).toBeNull();
        });
    });
    describe('viewport', () => {
        it('should set viewport', async () => {
            await browser.setViewport(1920, 1080);
            const page = browser.getPage();
            const size = page.viewportSize();
            expect(size?.width).toBe(1920);
            expect(size?.height).toBe(1080);
        });
    });
});
//# sourceMappingURL=browser.test.js.map