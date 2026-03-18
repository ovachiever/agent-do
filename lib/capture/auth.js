/**
 * Auth header extraction and classification.
 * Scans API entries for authentication patterns.
 */

// Auth header patterns in priority order
const AUTH_PATTERNS = [
    { type: 'bearer',  header: 'authorization', match: /^Bearer\s+/i },
    { type: 'api_key', header: 'x-api-key',     match: null },
    { type: 'api_key', header: 'api-key',        match: null },
    { type: 'api_key', header: 'apikey',         match: null },
    { type: 'basic',   header: 'authorization', match: /^Basic\s+/i },
    { type: 'csrf',    header: 'x-csrf-token',  match: null },
    { type: 'csrf',    header: 'x-xsrf-token',  match: null },
];

// Cookie names that typically carry auth
const AUTH_COOKIE_NAMES = [
    'session', 'sid', 'token', 'auth', 'jwt',
    'access_token', 'id_token', '_session',
    'connect.sid', 'PHPSESSID', 'JSESSIONID',
];

/**
 * Extract authentication info from captured API entries.
 * @param {Array} entries - Filtered API entries
 * @returns {Object} Auth descriptor: { type, headers, cookies, notes }
 */
export function extractAuth(entries) {
    const headerCounts = new Map(); // "header:value" -> count
    const cookieValues = new Map(); // cookie name -> value

    for (const entry of entries) {
        const headers = entry.request.headers || {};

        // Check each auth pattern
        for (const pattern of AUTH_PATTERNS) {
            const value = headers[pattern.header];
            if (!value) continue;
            if (pattern.match && !pattern.match.test(value)) continue;
            const key = `${pattern.type}:${pattern.header}`;
            headerCounts.set(key, (headerCounts.get(key) || 0) + 1);
        }

        // Check for custom auth headers (x-* that aren't standard)
        for (const [name] of Object.entries(headers)) {
            const lower = name.toLowerCase();
            if (lower.startsWith('x-') &&
                !lower.startsWith('x-requested') &&
                !lower.startsWith('x-forwarded') &&
                (lower.includes('auth') || lower.includes('token') || lower.includes('key'))) {
                const key = `custom:${lower}`;
                headerCounts.set(key, (headerCounts.get(key) || 0) + 1);
            }
        }

        // Extract auth cookies
        const cookieHeader = headers['cookie'] || '';
        if (cookieHeader) {
            parseCookies(cookieHeader).forEach((value, name) => {
                const lower = name.toLowerCase();
                if (AUTH_COOKIE_NAMES.some(c => lower.includes(c))) {
                    cookieValues.set(name, value);
                }
            });
        }
    }

    // Determine primary auth type
    let primaryType = 'none';
    let authHeaders = {};
    let notes = [];

    if (headerCounts.size > 0) {
        // Sort by count (most common auth header wins)
        const sorted = [...headerCounts.entries()].sort((a, b) => b[1] - a[1]);
        const [topKey] = sorted[0];
        const [type] = topKey.split(':');
        primaryType = type;

        // Collect the actual header values from the last entry that had them
        for (const entry of entries) {
            const headers = entry.request.headers || {};
            for (const [key] of sorted) {
                const [, hName] = key.split(':');
                if (headers[hName]) {
                    authHeaders[hName] = headers[hName];
                }
            }
            if (Object.keys(authHeaders).length > 0) break;
        }

        if (sorted.length > 1) {
            notes.push(`Multiple auth patterns detected: ${sorted.map(([k, c]) => `${k} (${c}x)`).join(', ')}`);
        }
    }

    const cookies = {};
    for (const [name, value] of cookieValues) {
        cookies[name] = value;
    }

    if (Object.keys(cookies).length > 0 && primaryType === 'none') {
        primaryType = 'cookie';
    }

    if (Object.keys(cookies).length > 0) {
        notes.push(`Auth cookies found: ${Object.keys(cookies).join(', ')}`);
    }

    return {
        type: primaryType,
        headers: authHeaders,
        cookies,
        notes,
    };
}

/**
 * Parse a Cookie header string into a Map of name -> value
 */
function parseCookies(cookieStr) {
    const map = new Map();
    for (const pair of cookieStr.split(';')) {
        const eq = pair.indexOf('=');
        if (eq === -1) continue;
        const name = pair.substring(0, eq).trim();
        const value = pair.substring(eq + 1).trim();
        map.set(name, value);
    }
    return map;
}
