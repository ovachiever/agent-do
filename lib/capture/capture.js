/**
 * CaptureSession — attaches to Playwright page and records XHR/fetch traffic.
 * Correlates request/response pairs, caps body at 1MB.
 */

const MAX_BODY_SIZE = 1024 * 1024; // 1MB

export class CaptureSession {
    constructor() {
        this.entries = [];           // correlated {request, response} pairs
        this.pendingRequests = new Map(); // requestId -> request data
        this.startTime = null;
        this.isCapturing = false;
        this._onRequest = null;
        this._onResponse = null;
    }

    start(page) {
        if (this.isCapturing) return;
        this.isCapturing = true;
        this.startTime = Date.now();

        this._onRequest = (request) => {
            this.pendingRequests.set(request, {
                url: request.url(),
                method: request.method(),
                headers: request.headers(),
                postData: request.postData() || null,
                resourceType: request.resourceType(),
                timestamp: Date.now(),
            });
        };

        this._onResponse = async (response) => {
            const request = response.request();
            const reqData = this.pendingRequests.get(request);
            if (!reqData) return;
            this.pendingRequests.delete(request);

            let body = null;
            let contentType = '';
            try {
                contentType = response.headers()['content-type'] || '';
                const buf = await response.body();
                if (buf.length <= MAX_BODY_SIZE) {
                    // Only store text-like bodies
                    if (isTextContent(contentType)) {
                        body = buf.toString('utf8');
                    }
                }
            } catch {
                // Some responses can't be read (e.g. redirects, aborted)
            }

            this.entries.push({
                request: reqData,
                response: {
                    status: response.status(),
                    headers: response.headers(),
                    contentType,
                    body,
                },
            });
        };

        page.on('request', this._onRequest);
        page.on('response', this._onResponse);
    }

    stop(page) {
        if (!this.isCapturing) return;
        this.isCapturing = false;
        if (this._onRequest) {
            page.removeListener('request', this._onRequest);
            this._onRequest = null;
        }
        if (this._onResponse) {
            page.removeListener('response', this._onResponse);
            this._onResponse = null;
        }
    }

    getEntries() {
        return this.entries;
    }

    getStatus() {
        const domains = new Set();
        for (const e of this.entries) {
            try {
                domains.add(new URL(e.request.url).hostname);
            } catch { /* ignore */ }
        }
        return {
            capturing: this.isCapturing,
            requestCount: this.entries.length,
            domains: [...domains],
            elapsed: this.startTime ? Math.round((Date.now() - this.startTime) / 1000) : 0,
        };
    }
}

function isTextContent(contentType) {
    if (!contentType) return false;
    return (
        contentType.includes('json') ||
        contentType.includes('xml') ||
        contentType.includes('text') ||
        contentType.includes('javascript') ||
        contentType.includes('html') ||
        contentType.includes('css') ||
        contentType.includes('form-urlencoded')
    );
}
