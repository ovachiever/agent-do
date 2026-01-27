import { describe, it, expect } from 'vitest';
import { parseCommand } from './protocol.js';
// Helper to create command JSON string
const cmd = (obj) => JSON.stringify(obj);
describe('parseCommand', () => {
    describe('navigation', () => {
        it('should parse navigate command', () => {
            const result = parseCommand(cmd({ id: '1', action: 'navigate', url: 'https://example.com' }));
            expect(result.success).toBe(true);
            if (result.success) {
                expect(result.command.action).toBe('navigate');
                expect(result.command.url).toBe('https://example.com');
            }
        });
        it('should reject navigate without url', () => {
            const result = parseCommand(cmd({ id: '1', action: 'navigate' }));
            expect(result.success).toBe(false);
        });
    });
    describe('click', () => {
        it('should parse click command', () => {
            const result = parseCommand(cmd({ id: '1', action: 'click', selector: '#btn' }));
            expect(result.success).toBe(true);
            if (result.success) {
                expect(result.command.action).toBe('click');
                expect(result.command.selector).toBe('#btn');
            }
        });
        it('should reject click without selector', () => {
            const result = parseCommand(cmd({ id: '1', action: 'click' }));
            expect(result.success).toBe(false);
        });
    });
    describe('type', () => {
        it('should parse type command', () => {
            const result = parseCommand(cmd({ id: '1', action: 'type', selector: '#input', text: 'hello' }));
            expect(result.success).toBe(true);
            if (result.success) {
                expect(result.command.action).toBe('type');
                expect(result.command.selector).toBe('#input');
                expect(result.command.text).toBe('hello');
            }
        });
    });
    describe('fill', () => {
        it('should parse fill command', () => {
            const result = parseCommand(cmd({ id: '1', action: 'fill', selector: '#input', value: 'hello' }));
            expect(result.success).toBe(true);
            if (result.success) {
                expect(result.command.action).toBe('fill');
                expect(result.command.value).toBe('hello');
            }
        });
    });
    describe('wait', () => {
        it('should parse wait with selector', () => {
            const result = parseCommand(cmd({ id: '1', action: 'wait', selector: '#loading' }));
            expect(result.success).toBe(true);
        });
        it('should parse wait with timeout', () => {
            const result = parseCommand(cmd({ id: '1', action: 'wait', timeout: 5000 }));
            expect(result.success).toBe(true);
        });
        it('should parse wait with text', () => {
            const result = parseCommand(cmd({ id: '1', action: 'wait', text: 'Welcome' }));
            expect(result.success).toBe(true);
        });
    });
    describe('screenshot', () => {
        it('should parse screenshot command', () => {
            const result = parseCommand(cmd({ id: '1', action: 'screenshot', path: 'test.png' }));
            expect(result.success).toBe(true);
        });
        it('should parse screenshot with fullPage', () => {
            const result = parseCommand(cmd({ id: '1', action: 'screenshot', fullPage: true }));
            expect(result.success).toBe(true);
        });
    });
    describe('cookies', () => {
        it('should parse cookies_get', () => {
            const result = parseCommand(cmd({ id: '1', action: 'cookies_get' }));
            expect(result.success).toBe(true);
        });
        it('should parse cookies_set', () => {
            const result = parseCommand(cmd({
                id: '1',
                action: 'cookies_set',
                cookies: [{ name: 'session', value: 'abc123' }],
            }));
            expect(result.success).toBe(true);
        });
        it('should parse cookies_clear', () => {
            const result = parseCommand(cmd({ id: '1', action: 'cookies_clear' }));
            expect(result.success).toBe(true);
        });
    });
    describe('storage', () => {
        it('should parse storage_get', () => {
            const result = parseCommand(cmd({ id: '1', action: 'storage_get', type: 'local' }));
            expect(result.success).toBe(true);
        });
        it('should parse storage_set', () => {
            const result = parseCommand(cmd({
                id: '1',
                action: 'storage_set',
                type: 'local',
                key: 'test',
                value: 'value',
            }));
            expect(result.success).toBe(true);
        });
    });
    describe('semantic locators', () => {
        it('should parse getbyrole', () => {
            const result = parseCommand(cmd({
                id: '1',
                action: 'getbyrole',
                role: 'button',
                subaction: 'click',
            }));
            expect(result.success).toBe(true);
        });
        it('should parse getbytext', () => {
            const result = parseCommand(cmd({
                id: '1',
                action: 'getbytext',
                text: 'Submit',
                subaction: 'click',
            }));
            expect(result.success).toBe(true);
        });
        it('should parse getbylabel', () => {
            const result = parseCommand(cmd({
                id: '1',
                action: 'getbylabel',
                label: 'Email',
                subaction: 'fill',
                value: 'test@test.com',
            }));
            expect(result.success).toBe(true);
        });
    });
    describe('tabs', () => {
        it('should parse tab_new', () => {
            const result = parseCommand(cmd({ id: '1', action: 'tab_new' }));
            expect(result.success).toBe(true);
        });
        it('should parse tab_list', () => {
            const result = parseCommand(cmd({ id: '1', action: 'tab_list' }));
            expect(result.success).toBe(true);
        });
        it('should parse tab_switch', () => {
            const result = parseCommand(cmd({ id: '1', action: 'tab_switch', index: 0 }));
            expect(result.success).toBe(true);
        });
        it('should parse tab_close', () => {
            const result = parseCommand(cmd({ id: '1', action: 'tab_close' }));
            expect(result.success).toBe(true);
        });
    });
    describe('invalid commands', () => {
        it('should reject unknown action', () => {
            const result = parseCommand(cmd({ id: '1', action: 'unknown' }));
            expect(result.success).toBe(false);
        });
        it('should reject missing id', () => {
            const result = parseCommand(cmd({ action: 'click', selector: '#btn' }));
            expect(result.success).toBe(false);
        });
        it('should reject invalid JSON', () => {
            const result = parseCommand('not json');
            expect(result.success).toBe(false);
        });
    });
});
//# sourceMappingURL=protocol.test.js.map