// Execute Playwright's actual in-page storage decoder in a VM, with no browser.
import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import path from 'node:path';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const { source } = require(path.join(path.dirname(require.resolve('playwright-core')), 'lib/generated/storageScriptSource.js'));
function decode(payload) {
    return vm.runInNewContext(`${source}\nparseEvaluationResultValue(payload)`, {
        payload, atob: globalThis.atob, module: { exports: {} },
    });
}

describe('imported IndexedDB typed-array encoding', () => {
    it('restores the exact Uint8Array view emitted by the real binary fixture', () => {
        const result = decode({ ta: { k: 'ui8', b: 'Af4=' } });
        expect(result.constructor.name).toBe('Uint8Array');
        expect(Array.from(result)).toEqual([1, 254]);
    });

    it('preserves nested typed arrays, primitives, and object references', () => {
        const result = decode({ o: [
            { k: 'bytes', v: { ta: { k: 'ui16', b: 'AQD/AA==' } } },
            { k: 'plain', v: { a: ['text', 3, false, { v: 'null' }], id: 2 } },
            { k: 'same', v: { ref: 2 } },
        ], id: 1 });
        expect(result.bytes.constructor.name).toBe('Uint16Array');
        expect(Array.from(result.bytes)).toEqual([1, 255]);
        expect(Array.from(result.plain)).toEqual(['text', 3, false, null]);
        expect(result.same).toBe(result.plain);
    });
});
