/**
 * Auth helpers module for agent-browse.
 * Phase 5: TOTP/2FA, OAuth flows, credential management.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createCipheriv, createDecipheriv, randomBytes, scryptSync, createHmac } from 'node:crypto';
import path from 'node:path';
import os from 'node:os';

const AUTH_DIR = path.join(os.homedir(), '.agent-browse', 'auth');
const CREDS_FILE = path.join(AUTH_DIR, 'credentials.enc');

/**
 * TOTP (Time-based One-Time Password) generator
 * RFC 6238 compliant
 */
export function generateTOTP(secret, options = {}) {
    const {
        digits = 6,
        period = 30,
        algorithm = 'SHA1',
        timestamp = Date.now(),
    } = options;

    // Decode base32 secret
    const key = base32Decode(secret.replace(/\s/g, '').toUpperCase());
    
    // Calculate time counter
    const counter = Math.floor(timestamp / 1000 / period);
    
    // Convert counter to 8-byte buffer (big-endian)
    const counterBuffer = Buffer.alloc(8);
    counterBuffer.writeBigUInt64BE(BigInt(counter));
    
    // HMAC-SHA1 (or SHA256/SHA512)
    const hmac = createHmac(algorithm.toLowerCase().replace('-', ''), key);
    hmac.update(counterBuffer);
    const hash = hmac.digest();
    
    // Dynamic truncation
    const offset = hash[hash.length - 1] & 0x0f;
    const binary = (
        ((hash[offset] & 0x7f) << 24) |
        ((hash[offset + 1] & 0xff) << 16) |
        ((hash[offset + 2] & 0xff) << 8) |
        (hash[offset + 3] & 0xff)
    );
    
    // Generate OTP
    const otp = binary % Math.pow(10, digits);
    return otp.toString().padStart(digits, '0');
}

/**
 * Synchronous TOTP generation (for CLI use)
 */
export function generateTOTPSync(secret, options = {}) {
    const {
        digits = 6,
        period = 30,
        timestamp = Date.now(),
    } = options;

    const key = base32Decode(secret.replace(/\s/g, '').toUpperCase());
    const counter = Math.floor(timestamp / 1000 / period);
    
    const counterBuffer = Buffer.alloc(8);
    counterBuffer.writeBigUInt64BE(BigInt(counter));
    
    const hmac = createHmac('sha1', key);
    hmac.update(counterBuffer);
    const hash = hmac.digest();
    
    const offset = hash[hash.length - 1] & 0x0f;
    const binary = (
        ((hash[offset] & 0x7f) << 24) |
        ((hash[offset + 1] & 0xff) << 16) |
        ((hash[offset + 2] & 0xff) << 8) |
        (hash[offset + 3] & 0xff)
    );
    
    const otp = binary % Math.pow(10, digits);
    return otp.toString().padStart(digits, '0');
}

/**
 * Get time remaining until next TOTP code
 */
export function getTOTPTimeRemaining(period = 30) {
    const now = Math.floor(Date.now() / 1000);
    return period - (now % period);
}

/**
 * Base32 decode (RFC 4648)
 */
function base32Decode(encoded) {
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
    const cleanedInput = encoded.replace(/=+$/, '');
    
    let bits = '';
    for (const char of cleanedInput) {
        const val = alphabet.indexOf(char);
        if (val === -1) throw new Error(`Invalid base32 character: ${char}`);
        bits += val.toString(2).padStart(5, '0');
    }
    
    const bytes = [];
    for (let i = 0; i + 8 <= bits.length; i += 8) {
        bytes.push(parseInt(bits.slice(i, i + 8), 2));
    }
    
    return Buffer.from(bytes);
}

/**
 * Parse otpauth:// URI (from QR codes)
 */
export function parseOTPAuthURI(uri) {
    const url = new URL(uri);
    if (url.protocol !== 'otpauth:') {
        throw new Error('Invalid OTP auth URI');
    }
    
    const type = url.hostname; // totp or hotp
    const label = decodeURIComponent(url.pathname.slice(1));
    const params = Object.fromEntries(url.searchParams);
    
    return {
        type,
        label,
        secret: params.secret,
        issuer: params.issuer || label.split(':')[0],
        algorithm: params.algorithm || 'SHA1',
        digits: parseInt(params.digits) || 6,
        period: parseInt(params.period) || 30,
    };
}

/**
 * Credential storage with encryption
 */
class CredentialStore {
    constructor(masterPassword = null) {
        this.masterPassword = masterPassword;
        this.credentials = {};
        this.loaded = false;
    }

    ensureDir() {
        if (!existsSync(AUTH_DIR)) {
            mkdirSync(AUTH_DIR, { recursive: true, mode: 0o700 });
        }
    }

    deriveKey(password) {
        const salt = 'agent-browse-creds-v1';
        return scryptSync(password, salt, 32);
    }

    encrypt(data, password) {
        const key = this.deriveKey(password);
        const iv = randomBytes(16);
        const cipher = createCipheriv('aes-256-gcm', key, iv);
        
        let encrypted = cipher.update(JSON.stringify(data), 'utf8', 'hex');
        encrypted += cipher.final('hex');
        const authTag = cipher.getAuthTag();
        
        return {
            iv: iv.toString('hex'),
            authTag: authTag.toString('hex'),
            data: encrypted,
        };
    }

    decrypt(encrypted, password) {
        const key = this.deriveKey(password);
        const iv = Buffer.from(encrypted.iv, 'hex');
        const authTag = Buffer.from(encrypted.authTag, 'hex');
        
        const decipher = createDecipheriv('aes-256-gcm', key, iv);
        decipher.setAuthTag(authTag);
        
        let decrypted = decipher.update(encrypted.data, 'hex', 'utf8');
        decrypted += decipher.final('utf8');
        
        return JSON.parse(decrypted);
    }

    load(password) {
        this.ensureDir();
        this.masterPassword = password;
        
        if (!existsSync(CREDS_FILE)) {
            this.credentials = {};
            this.loaded = true;
            return { loaded: true, count: 0 };
        }
        
        try {
            const encrypted = JSON.parse(readFileSync(CREDS_FILE, 'utf8'));
            this.credentials = this.decrypt(encrypted, password);
            this.loaded = true;
            return { loaded: true, count: Object.keys(this.credentials).length };
        } catch (e) {
            throw new Error('Failed to decrypt credentials. Wrong password?');
        }
    }

    save() {
        if (!this.masterPassword) {
            throw new Error('No master password set. Call load() first.');
        }
        
        this.ensureDir();
        const encrypted = this.encrypt(this.credentials, this.masterPassword);
        writeFileSync(CREDS_FILE, JSON.stringify(encrypted, null, 2), { mode: 0o600 });
    }

    set(site, username, password, extra = {}) {
        if (!this.loaded) {
            throw new Error('Credential store not loaded. Call load() first.');
        }
        
        this.credentials[site] = {
            username,
            password,
            ...extra,
            updatedAt: new Date().toISOString(),
        };
        this.save();
        return { saved: true, site };
    }

    get(site) {
        if (!this.loaded) {
            throw new Error('Credential store not loaded. Call load() first.');
        }
        return this.credentials[site] || null;
    }

    list() {
        if (!this.loaded) {
            throw new Error('Credential store not loaded. Call load() first.');
        }
        return Object.keys(this.credentials).map(site => ({
            site,
            username: this.credentials[site].username,
            hasTotp: !!this.credentials[site].totpSecret,
            updatedAt: this.credentials[site].updatedAt,
        }));
    }

    delete(site) {
        if (!this.loaded) {
            throw new Error('Credential store not loaded. Call load() first.');
        }
        
        if (this.credentials[site]) {
            delete this.credentials[site];
            this.save();
            return { deleted: true, site };
        }
        return { deleted: false, error: `Site '${site}' not found` };
    }
}

// Global credential store instance
let credStore = null;

export function getCredentialStore() {
    if (!credStore) {
        credStore = new CredentialStore();
    }
    return credStore;
}

/**
 * OAuth flow helpers
 */
export const OAUTH_PROVIDERS = {
    google: {
        authUrl: 'https://accounts.google.com/o/oauth2/v2/auth',
        tokenUrl: 'https://oauth2.googleapis.com/token',
        scopes: ['openid', 'email', 'profile'],
    },
    github: {
        authUrl: 'https://github.com/login/oauth/authorize',
        tokenUrl: 'https://github.com/login/oauth/access_token',
        scopes: ['user:email'],
    },
    microsoft: {
        authUrl: 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
        tokenUrl: 'https://login.microsoftonline.com/common/oauth2/v2.0/token',
        scopes: ['openid', 'email', 'profile'],
    },
};

/**
 * Build OAuth authorization URL
 */
export function buildOAuthUrl(provider, clientId, redirectUri, state = null) {
    const config = OAUTH_PROVIDERS[provider];
    if (!config) {
        throw new Error(`Unknown OAuth provider: ${provider}`);
    }
    
    const params = new URLSearchParams({
        client_id: clientId,
        redirect_uri: redirectUri,
        response_type: 'code',
        scope: config.scopes.join(' '),
        state: state || randomBytes(16).toString('hex'),
    });
    
    return `${config.authUrl}?${params.toString()}`;
}

/**
 * Extract OAuth callback parameters
 */
export function parseOAuthCallback(url) {
    const urlObj = new URL(url);
    return {
        code: urlObj.searchParams.get('code'),
        state: urlObj.searchParams.get('state'),
        error: urlObj.searchParams.get('error'),
        errorDescription: urlObj.searchParams.get('error_description'),
    };
}

/**
 * Detect login form on page
 */
export async function detectLoginForm(page) {
    return await page.evaluate(() => {
        const forms = Array.from(document.querySelectorAll('form'));
        
        for (const form of forms) {
            const inputs = Array.from(form.querySelectorAll('input'));
            const hasPassword = inputs.some(i => i.type === 'password');
            const hasUsername = inputs.some(i => 
                i.type === 'text' || i.type === 'email' || 
                i.name?.toLowerCase().includes('user') ||
                i.name?.toLowerCase().includes('email')
            );
            
            if (hasPassword && hasUsername) {
                const usernameInput = inputs.find(i => 
                    i.type === 'text' || i.type === 'email' ||
                    i.name?.toLowerCase().includes('user') ||
                    i.name?.toLowerCase().includes('email')
                );
                const passwordInput = inputs.find(i => i.type === 'password');
                const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
                
                return {
                    found: true,
                    usernameSelector: usernameInput ? buildSelector(usernameInput) : null,
                    passwordSelector: passwordInput ? buildSelector(passwordInput) : null,
                    submitSelector: submitButton ? buildSelector(submitButton) : null,
                };
            }
        }
        
        return { found: false };
        
        function buildSelector(el) {
            if (el.id) return `#${el.id}`;
            if (el.name) return `[name="${el.name}"]`;
            return null;
        }
    });
}

/**
 * Auto-fill login form
 */
export async function autoFillLogin(page, username, password) {
    const form = await detectLoginForm(page);
    if (!form.found) {
        return { filled: false, error: 'No login form detected' };
    }
    
    const results = { filled: true, fields: [] };
    
    if (form.usernameSelector) {
        await page.fill(form.usernameSelector, username);
        results.fields.push('username');
    }
    
    if (form.passwordSelector) {
        await page.fill(form.passwordSelector, password);
        results.fields.push('password');
    }
    
    results.submitSelector = form.submitSelector;
    return results;
}

/**
 * Detect CAPTCHA on page
 */
export async function detectCaptcha(page) {
    return await page.evaluate(() => {
        const indicators = {
            recaptcha: !!document.querySelector('.g-recaptcha, [data-sitekey], iframe[src*="recaptcha"]'),
            hcaptcha: !!document.querySelector('.h-captcha, iframe[src*="hcaptcha"]'),
            cloudflare: !!document.querySelector('#cf-challenge-running, .cf-browser-verification'),
            funcaptcha: !!document.querySelector('[data-pkey], iframe[src*="funcaptcha"]'),
            textCaptcha: !!document.querySelector('img[src*="captcha"], input[name*="captcha"]'),
        };
        
        const detected = Object.entries(indicators).filter(([, v]) => v).map(([k]) => k);
        
        return {
            hasCaptcha: detected.length > 0,
            types: detected,
        };
    });
}

/**
 * Wait for CAPTCHA to be solved (manual)
 */
export async function waitForCaptchaSolved(page, timeout = 120000) {
    const startTime = Date.now();
    
    while (Date.now() - startTime < timeout) {
        const captcha = await detectCaptcha(page);
        if (!captcha.hasCaptcha) {
            return { solved: true, duration: Date.now() - startTime };
        }
        await page.waitForTimeout(1000);
    }
    
    return { solved: false, timeout: true };
}
