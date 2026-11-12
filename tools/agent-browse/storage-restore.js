import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { source } = require(path.join(path.dirname(require.resolve('playwright-core')), 'lib/generated/storageScriptSource.js'));
const BATCH_BYTES = 8 * 1024 * 1024;

// Use the exact installed Playwright decoder for every record. Only the
// transport is batched; schema, keys, values and typed arrays are unchanged.
const installRestorer = `(() => {
    const module = { exports: {} };
    ${source}
    const script = new StorageScript(globalThis);
    globalThis.__agentBrowseRestore = {
        initialize: (state) => script.restore(state),
        async writeBatch({ name, version, store, records }) {
            const db = await new Promise((resolve, reject) => {
                const request = indexedDB.open(name, version);
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
            });
            try {
                const transaction = db.transaction([store], 'readwrite');
                const complete = new Promise((resolve, reject) => {
                    transaction.oncomplete = resolve;
                    transaction.onabort = () => reject(transaction.error || new Error('IndexedDB transaction aborted'));
                    transaction.onerror = () => reject(transaction.error);
                });
                const target = transaction.objectStore(store);
                try {
                    for (const record of records) {
                        const value = record.value ?? parseEvaluationResultValue(record.valueEncoded);
                        const key = record.key ?? parseEvaluationResultValue(record.keyEncoded);
                        target.add(value, key);
                    }
                } catch (error) {
                    transaction.abort();
                    await complete.catch(() => {});
                    throw error;
                }
                await complete;
            } finally { db.close(); }
        }
    };
})()`;

export function* recordBatches(records, limit = BATCH_BYTES) {
    let batch = [], bytes = 0;
    for (const record of records) {
        const size = Buffer.byteLength(JSON.stringify(record));
        if (size > limit) throw new Error('[SESSION_STORAGE_RECORD_TOO_LARGE] One IndexedDB record exceeds the browser transfer limit.');
        if (batch.length && bytes + size > limit) {
            yield batch;
            batch = [];
            bytes = 0;
        }
        batch.push(record);
        bytes += size;
    }
    if (batch.length) yield batch;
}

export async function createRestoredContext(browser, storageState, viewport = { width: 1920, height: 1080 }) {
    const origins = storageState.origins || [];
    const context = await browser.newContext({ viewport, storageState: {
        cookies: storageState.cookies || [],
        origins: origins.map(({ origin, localStorage }) => ({ origin, localStorage: localStorage || [] })),
    } });
    let page;
    try {
        for (const origin of origins) {
            if (!origin.indexedDB?.length) continue;
            page = await context.newPage();
            // Match Playwright's own storage initialization: a blank page at
            // the origin, with no request to the site until restoration ends.
            await page.route('**/*', (route) => route.fulfill({ body: '', contentType: 'text/html' }));
            await page.goto(origin.origin, { waitUntil: 'domcontentloaded', timeout: 15000 });
            await page.evaluate(installRestorer);
            const schema = { ...origin, indexedDB: origin.indexedDB.map((db) => ({
                ...db, stores: db.stores.map((store) => ({ ...store, records: [] })),
            })) };
            await page.evaluate((state) => globalThis.__agentBrowseRestore.initialize(state), schema);
            for (const db of origin.indexedDB) {
                for (const store of db.stores) {
                    for (const records of recordBatches(store.records)) {
                        await page.evaluate((batch) => globalThis.__agentBrowseRestore.writeBatch(batch), {
                            name: db.name, version: db.version, store: store.name, records,
                        });
                    }
                }
            }
            await page.close();
            page = null;
        }
        return context;
    } catch (error) {
        await context.close().catch(() => {});
        // Never return a partial context or navigate to the account on failure.
        throw error;
    }
}
