/**
 * Smart traffic filtering pipeline.
 * Removes static assets, CDN/analytics noise, and deduplicates API calls.
 */

// Static file extensions to drop
const STATIC_EXTENSIONS = new Set([
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp', '.avif',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.css', '.map', '.br', '.gz',
    '.mp3', '.mp4', '.webm', '.ogg', '.wav',
    '.pdf', '.zip', '.tar',
]);

// CDN/analytics/tracking domains to blocklist
const BLOCKED_DOMAINS = new Set([
    // Analytics
    'www.google-analytics.com', 'analytics.google.com', 'www.googletagmanager.com',
    'googletagmanager.com', 'stats.g.doubleclick.net', 'ssl.google-analytics.com',
    'www.googleadservices.com', 'googleads.g.doubleclick.net',
    // Facebook
    'connect.facebook.net', 'www.facebook.com', 'pixel.facebook.com',
    'graph.facebook.com', 'www.facebook.com',
    // Tracking/analytics services
    'bat.bing.com', 'ct.pinterest.com', 'snap.licdn.com',
    'analytics.tiktok.com', 'sc-static.net',
    'cdn.segment.com', 'api.segment.io', 'cdn.mxpnl.com',
    'api-js.mixpanel.com', 'rs.fullstory.com', 'edge.fullstory.com',
    'heapanalytics.com', 'cdn.heapanalytics.com',
    'js.intercomcdn.com', 'widget.intercom.io', 'api-iam.intercom.io',
    'static.hotjar.com', 'script.hotjar.com', 'vars.hotjar.com',
    'cdn.amplitude.com', 'api.amplitude.com', 'api2.amplitude.com',
    'js.hs-scripts.com', 'js.hsforms.net', 'js.hs-analytics.net',
    'track.hubspot.com', 'forms.hubspot.com', 'js.hs-banner.com',
    'sentry.io', 'browser.sentry-cdn.com', 'o0.ingest.sentry.io',
    'rum.browser-intake-datadoghq.com', 'browser-intake-datadoghq.com',
    'static.datadog-agent.com',
    'cdn.lr-in-prod.com', 'cdn.logrocket.io', 'r.lr-in-prod.com',
    'plausible.io', 'cdn.usefathom.com',
    'js.driftt.com', 'event.api.drift.com',
    'fast.appcues.com', 'api.appcues.net',
    'cdn.pendo.io', 'app.pendo.io',
    'static.zdassets.com', 'ekr.zdassets.com',
    'www.clarity.ms', 'js.monitor.azure.com',
    // CDNs (general static)
    'fonts.googleapis.com', 'fonts.gstatic.com',
    'cdnjs.cloudflare.com', 'cdn.jsdelivr.net',
    'unpkg.com', 'ajax.googleapis.com',
]);

// Resource types to drop
const BLOCKED_RESOURCE_TYPES = new Set([
    'image', 'media', 'font', 'stylesheet', 'manifest', 'other',
]);

// Content types we care about (API responses)
const API_CONTENT_TYPES = [
    'application/json',
    'application/xml',
    'text/xml',
    'application/x-www-form-urlencoded',
    'text/plain', // some APIs return text/plain for JSON
];

/**
 * Filter captured entries to API-only traffic.
 * @param {Array} entries - Raw capture entries from CaptureSession
 * @returns {Array} Filtered, deduplicated API entries
 */
export function filterEntries(entries) {
    let filtered = entries;

    // 1. Remove by resource type
    filtered = filtered.filter(e => !BLOCKED_RESOURCE_TYPES.has(e.request.resourceType));

    // 2. Remove static file extensions
    filtered = filtered.filter(e => {
        try {
            const pathname = new URL(e.request.url).pathname;
            const ext = pathname.substring(pathname.lastIndexOf('.')).toLowerCase();
            return !STATIC_EXTENSIONS.has(ext);
        } catch {
            return true;
        }
    });

    // 3. Remove blocked domains (CDN/analytics)
    filtered = filtered.filter(e => {
        try {
            const hostname = new URL(e.request.url).hostname;
            return !BLOCKED_DOMAINS.has(hostname);
        } catch {
            return true;
        }
    });

    // 4. Filter by content type — keep API-like responses
    filtered = filtered.filter(e => {
        const ct = (e.response.contentType || '').toLowerCase();
        // If no content type, keep it (might be interesting)
        if (!ct) return true;
        // Keep if it matches API content types
        return API_CONTENT_TYPES.some(t => ct.includes(t));
    });

    // 5. Remove internal infrastructure paths
    filtered = filtered.filter(e => {
        try {
            const pathname = new URL(e.request.url).pathname;
            // Cloudflare internal
            if (pathname.startsWith('/cdn-cgi/')) return false;
            // Service workers, manifests
            if (pathname === '/sw.js' || pathname === '/manifest.json') return false;
            return true;
        } catch {
            return true;
        }
    });

    // 6. Remove OPTIONS preflight requests
    filtered = filtered.filter(e => e.request.method !== 'OPTIONS');

    // 6. Remove failed requests (4xx/5xx might still be useful, keep >=200 <500)
    // Actually keep all — error responses are still valid API endpoints

    // 7. Templatize paths and dedup
    filtered = dedup(filtered);

    return filtered;
}

/**
 * Templatize path segments that look like IDs.
 * /users/123/posts → /users/{id}/posts
 * /items/550e8400-e29b-41d4-a716-446655440000 → /items/{id}
 */
export function templatizePath(pathname) {
    return pathname.split('/').map(seg => {
        if (!seg) return seg;
        // UUID pattern
        if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(seg)) return '{id}';
        // Numeric ID
        if (/^\d+$/.test(seg)) return '{id}';
        // MongoDB ObjectId
        if (/^[0-9a-f]{24}$/i.test(seg)) return '{id}';
        // Short hash / base64 ID (8+ hex chars or alphanumeric that looks like an ID)
        if (/^[0-9a-f]{8,}$/i.test(seg) && seg.length <= 40) return '{id}';
        return seg;
    }).join('/');
}

/**
 * Deduplicate entries by method + templatized path.
 * Keeps the first occurrence of each unique endpoint.
 */
function dedup(entries) {
    const seen = new Set();
    const result = [];

    for (const entry of entries) {
        try {
            const url = new URL(entry.request.url);
            const template = templatizePath(url.pathname);
            const key = `${entry.request.method}:${url.hostname}:${template}`;
            if (!seen.has(key)) {
                seen.add(key);
                result.push(entry);
            }
        } catch {
            result.push(entry);
        }
    }

    return result;
}
