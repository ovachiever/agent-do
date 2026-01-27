/**
 * Network intelligence module for agent-browse.
 * Phase 4: HAR export, request mocking, throttling.
 */

import { writeFileSync } from 'node:fs';

/**
 * HAR (HTTP Archive) format generator
 */
export function generateHar(requests, responses = {}) {
    const entries = requests.map(req => {
        const resp = responses[req.url] || {};
        return {
            startedDateTime: new Date(req.timestamp).toISOString(),
            time: resp.duration || 0,
            request: {
                method: req.method,
                url: req.url,
                httpVersion: 'HTTP/1.1',
                headers: Object.entries(req.headers || {}).map(([name, value]) => ({ name, value })),
                queryString: parseQueryString(req.url),
                cookies: [],
                headersSize: -1,
                bodySize: req.postData?.length || 0,
                postData: req.postData ? {
                    mimeType: req.headers?.['content-type'] || 'application/octet-stream',
                    text: req.postData,
                } : undefined,
            },
            response: {
                status: resp.status || 0,
                statusText: resp.statusText || '',
                httpVersion: 'HTTP/1.1',
                headers: Object.entries(resp.headers || {}).map(([name, value]) => ({ name, value })),
                cookies: [],
                content: {
                    size: resp.bodySize || 0,
                    mimeType: resp.mimeType || 'application/octet-stream',
                    text: resp.body,
                },
                redirectURL: resp.redirectURL || '',
                headersSize: -1,
                bodySize: resp.bodySize || -1,
            },
            cache: {},
            timings: {
                blocked: -1,
                dns: -1,
                connect: -1,
                send: 0,
                wait: resp.duration || 0,
                receive: 0,
                ssl: -1,
            },
            serverIPAddress: '',
            connection: '',
        };
    });

    return {
        log: {
            version: '1.2',
            creator: {
                name: 'agent-browse',
                version: '1.0.0',
            },
            entries,
        },
    };
}

function parseQueryString(url) {
    try {
        const urlObj = new URL(url);
        return Array.from(urlObj.searchParams.entries()).map(([name, value]) => ({ name, value }));
    } catch {
        return [];
    }
}

/**
 * Enhanced request tracker with response data
 */
export class RequestTracker {
    constructor() {
        this.requests = [];
        this.responses = {};
        this.isTracking = false;
        this.requestHandler = null;
        this.responseHandler = null;
    }

    start(page) {
        if (this.isTracking) return;
        this.isTracking = true;

        this.requestHandler = async (request) => {
            const entry = {
                id: `req-${Date.now()}-${Math.random().toString(36).slice(2)}`,
                url: request.url(),
                method: request.method(),
                headers: request.headers(),
                postData: request.postData(),
                resourceType: request.resourceType(),
                timestamp: Date.now(),
            };
            this.requests.push(entry);
        };

        this.responseHandler = async (response) => {
            const request = response.request();
            const url = request.url();
            const startTime = this.requests.find(r => r.url === url)?.timestamp || Date.now();
            
            this.responses[url] = {
                status: response.status(),
                statusText: response.statusText(),
                headers: await response.allHeaders(),
                mimeType: response.headers()['content-type'] || 'application/octet-stream',
                duration: Date.now() - startTime,
                bodySize: 0, // Can't easily get without buffering
            };
        };

        page.on('request', this.requestHandler);
        page.on('response', this.responseHandler);
    }

    stop(page) {
        if (!this.isTracking) return;
        this.isTracking = false;

        if (this.requestHandler) {
            page.removeListener('request', this.requestHandler);
            this.requestHandler = null;
        }
        if (this.responseHandler) {
            page.removeListener('response', this.responseHandler);
            this.responseHandler = null;
        }
    }

    getRequests(filter) {
        if (!filter) return this.requests;
        return this.requests.filter(r => 
            r.url.includes(filter) || 
            r.resourceType === filter ||
            r.method === filter.toUpperCase()
        );
    }

    getFailedRequests() {
        return this.requests.filter(r => {
            const resp = this.responses[r.url];
            return resp && (resp.status >= 400 || resp.status === 0);
        });
    }

    clear() {
        this.requests = [];
        this.responses = {};
    }

    toHar() {
        return generateHar(this.requests, this.responses);
    }

    saveHar(path) {
        const har = this.toHar();
        writeFileSync(path, JSON.stringify(har, null, 2));
        return { path, requestCount: this.requests.length };
    }

    getStats() {
        const total = this.requests.length;
        const byType = {};
        const byStatus = {};
        
        for (const req of this.requests) {
            byType[req.resourceType] = (byType[req.resourceType] || 0) + 1;
            const resp = this.responses[req.url];
            if (resp) {
                const statusGroup = `${Math.floor(resp.status / 100)}xx`;
                byStatus[statusGroup] = (byStatus[statusGroup] || 0) + 1;
            }
        }

        return { total, byType, byStatus };
    }
}

/**
 * Network throttling presets (based on Chrome DevTools)
 */
export const THROTTLE_PRESETS = {
    'offline': { offline: true, downloadThroughput: 0, uploadThroughput: 0, latency: 0 },
    'slow-3g': { offline: false, downloadThroughput: 500 * 1024 / 8, uploadThroughput: 500 * 1024 / 8, latency: 2000 },
    '3g': { offline: false, downloadThroughput: 1.5 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8, latency: 300 },
    '4g': { offline: false, downloadThroughput: 4 * 1024 * 1024 / 8, uploadThroughput: 3 * 1024 * 1024 / 8, latency: 100 },
    'fast': { offline: false, downloadThroughput: -1, uploadThroughput: -1, latency: 0 },
};

/**
 * Apply network throttling via CDP
 */
export async function setThrottle(page, preset) {
    const client = await page.context().newCDPSession(page);
    const config = typeof preset === 'string' ? THROTTLE_PRESETS[preset] : preset;
    
    if (!config) {
        throw new Error(`Unknown throttle preset: ${preset}. Available: ${Object.keys(THROTTLE_PRESETS).join(', ')}`);
    }

    await client.send('Network.enable');
    await client.send('Network.emulateNetworkConditions', config);
    
    return config;
}

/**
 * Remove network throttling
 */
export async function clearThrottle(page) {
    const client = await page.context().newCDPSession(page);
    await client.send('Network.disable');
}

/**
 * Route builder for request mocking
 */
export function buildMockResponse(options) {
    return {
        status: options.status || 200,
        contentType: options.contentType || 'application/json',
        body: typeof options.body === 'string' ? options.body : JSON.stringify(options.body),
        headers: options.headers || {},
    };
}

/**
 * Create a route handler that delays responses
 */
export function createDelayHandler(delay) {
    return async (route) => {
        await new Promise(resolve => setTimeout(resolve, delay));
        await route.continue();
    };
}

/**
 * Create a route handler that modifies headers
 */
export function createHeaderModifier(headerMods) {
    return async (route, request) => {
        const headers = { ...request.headers(), ...headerMods };
        await route.continue({ headers });
    };
}
