// Transport and completeness tests with fake pages. No browser is launched.
import { describe, expect, it, vi } from 'vitest';
import { createRestoredContext, recordBatches } from './storage-restore.js';

describe('bounded full-state restoration', () => {
    it('preserves order and every record across bounded batches', () => {
        const records = Array.from({ length: 10 }, (_, key) => ({ key, value: 'x'.repeat(30) }));
        const batches = [...recordBatches(records, 130)];
        expect(batches.length).toBeGreaterThan(1);
        expect(batches.flat()).toEqual(records);
        for (const batch of batches) expect(batch.reduce((size, record) => size + Buffer.byteLength(JSON.stringify(record)), 0)).toBeLessThanOrEqual(130);
        expect(() => [...recordBatches([{ value: 'x'.repeat(131) }], 130)]).toThrow('SESSION_STORAGE_RECORD_TOO_LARGE');
    });

    function fixture() {
        const page = { route: vi.fn().mockResolvedValue(undefined), goto: vi.fn().mockResolvedValue(undefined),
            evaluate: vi.fn().mockResolvedValue(undefined), close: vi.fn().mockResolvedValue(undefined) };
        const context = { newPage: vi.fn().mockResolvedValue(page), close: vi.fn().mockResolvedValue(undefined) };
        const browser = { newContext: vi.fn().mockResolvedValue(context) };
        const records = [{ key: 'one', valueEncoded: { ta: { k: 'ui8', b: 'AQI=' } } }, { key: 'two', value: false }];
        const state = { cookies: [{ name: 'SID', value: 'synthetic' }], origins: [{
            origin: 'https://example.com', localStorage: [{ name: 'fixture', value: 'yes' }],
            indexedDB: [{ name: 'db', version: 2, stores: [{ name: 'store', autoIncrement: false, indexes: [], records }] }],
        }] };
        return { page, context, browser, records, state };
    }

    it('restores schemas and all records before returning a usable context', async () => {
        const { page, context, browser, records, state } = fixture();
        expect(await createRestoredContext(browser, state)).toBe(context);
        expect(browser.newContext.mock.calls[0][0].storageState).toEqual({ cookies: state.cookies,
            origins: [{ origin: 'https://example.com', localStorage: state.origins[0].localStorage }] });
        expect(page.evaluate.mock.calls[1][1].indexedDB[0].stores[0].records).toEqual([]);
        expect(page.evaluate.mock.calls[2][1]).toEqual({ name: 'db', version: 2, store: 'store', records });
        expect(page.close).toHaveBeenCalledOnce();
        expect(context.close).not.toHaveBeenCalled();
        expect(state.origins[0].indexedDB[0].stores[0].records).toEqual(records);
    });

    it('closes and refuses a partial context if any batch fails', async () => {
        const { page, context, browser, state } = fixture();
        page.evaluate.mockResolvedValueOnce(undefined).mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('write failed'));
        await expect(createRestoredContext(browser, state)).rejects.toThrow('write failed');
        expect(context.close).toHaveBeenCalledOnce();
        expect(browser.newContext).toHaveBeenCalledOnce();
    });
});
