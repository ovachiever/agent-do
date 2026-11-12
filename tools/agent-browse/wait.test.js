// Native wait adapter tests. No BrowserManager, daemon, or app is launched.
import { describe, expect, it, vi } from 'vitest';
import { executeCommand } from './actions.js';
import { parseCommand } from './protocol.js';

describe('bounded readiness waits', () => {
    it('passes the predicate timeout as Playwright options, not as the page argument', async () => {
        const page = { waitForFunction: vi.fn().mockResolvedValue(undefined) };
        const command = { id: 'ready', action: 'waitforfunction', expression: 'window.ready === true', timeout: 1234 };
        const result = await executeCommand(command, { getPage: () => page });
        expect(result.success).toBe(true);
        expect(page.waitForFunction).toHaveBeenCalledWith(command.expression, undefined, { timeout: 1234 });
    });

    it('passes the remaining budget to network idle', async () => {
        const page = { waitForLoadState: vi.fn().mockResolvedValue(undefined) };
        const result = await executeCommand({ id: 'idle', action: 'wait', state: 'networkidle', timeout: 4321 }, { getPage: () => page });
        expect(result.success).toBe(true);
        expect(page.waitForLoadState).toHaveBeenCalledWith('networkidle', { timeout: 4321 });
    });

    it('keeps literal text and its timeout separate from the predicate', async () => {
        const page = { waitForFunction: vi.fn().mockResolvedValue(undefined) };
        const text = 'Ready "now"\\next\nline';
        const result = await executeCommand({ id: 'text', action: 'wait', text, timeout: 2222 }, { getPage: () => page });
        expect(result.success).toBe(true);
        expect(page.waitForFunction).toHaveBeenCalledWith(expect.any(Function), text, { timeout: 2222 });
    });

    it('returns a failed response when the native predicate times out', async () => {
        const page = { waitForFunction: vi.fn().mockRejectedValue(new Error('Timeout 1234ms exceeded')) };
        const result = await executeCommand({ id: 'fail', action: 'waitforfunction', expression: 'false', timeout: 1234 }, { getPage: () => page });
        expect(result.success).toBe(false);
        expect(result.error).toContain('Timeout');
    });

    it('accepts the bounded wait protocol shapes', () => {
        for (const command of [
            { id: 'idle', action: 'wait', state: 'networkidle', timeout: 1 },
            { id: 'text', action: 'wait', text: 'Ready', timeout: 2 },
            { id: 'js', action: 'waitforfunction', expression: 'true', timeout: 3 },
        ]) {
            expect(parseCommand(JSON.stringify(command)).success).toBe(true);
        }
    });
});
