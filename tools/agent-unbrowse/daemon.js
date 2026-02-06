/**
 * agent-unbrowse daemon — Unix socket server for browser capture sessions.
 * Follows agent-browse daemon pattern: socket → parse → execute → respond.
 */

import * as net from 'net';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { chromium } from 'playwright-core';
import { parseCommand, successResponse, errorResponse, serializeResponse } from './protocol.js';
import { CaptureSession } from './capture.js';
import { filterEntries } from './filter.js';
import { extractAuth } from './auth.js';
import { generateSkill } from './generator.js';

const SESSION = process.env.AGENT_UNBROWSE_SESSION || 'default';
const SOCKET_PATH = path.join(os.tmpdir(), `agent-unbrowse-${SESSION}.sock`);
const PID_FILE = path.join(os.tmpdir(), `agent-unbrowse-${SESSION}.pid`);

let browser = null;
let page = null;
let capture = null;
let shuttingDown = false;

function cleanup() {
    try { if (fs.existsSync(PID_FILE)) fs.unlinkSync(PID_FILE); } catch {}
    try { if (fs.existsSync(SOCKET_PATH)) fs.unlinkSync(SOCKET_PATH); } catch {}
}

async function handleCommand(cmd) {
    switch (cmd.action) {
        case 'capture_start': {
            if (browser) {
                return errorResponse(cmd.id, 'Capture already running. Stop first or close.');
            }

            const headless = cmd.headless ?? false; // headed by default
            const execPath = process.env.AGENT_BROWSER_EXECUTABLE_PATH || undefined;

            browser = await chromium.launch({
                headless,
                executablePath: execPath,
            });

            const context = await browser.newContext();
            page = await context.newPage();
            capture = new CaptureSession();
            capture.start(page);

            await page.goto(cmd.url, { waitUntil: 'domcontentloaded' });

            return successResponse(cmd.id, {
                message: 'Capture started',
                url: cmd.url,
                headed: !headless,
            });
        }

        case 'capture_stop': {
            if (!capture || !page) {
                return errorResponse(cmd.id, 'No active capture session.');
            }

            capture.stop(page);
            const raw = capture.getEntries();
            const filtered = filterEntries(raw);
            const auth = extractAuth(filtered);
            const result = generateSkill(cmd.name, filtered, auth);

            return successResponse(cmd.id, {
                message: `Skill "${cmd.name}" generated`,
                rawRequests: raw.length,
                filteredEndpoints: filtered.length,
                authType: auth.type,
                ...result,
            });
        }

        case 'capture_status': {
            if (!capture) {
                return successResponse(cmd.id, {
                    capturing: false,
                    requestCount: 0,
                    domains: [],
                    elapsed: 0,
                });
            }
            return successResponse(cmd.id, capture.getStatus());
        }

        case 'close': {
            if (browser) {
                try { await browser.close(); } catch {}
                browser = null;
                page = null;
                capture = null;
            }
            return successResponse(cmd.id, { message: 'Closed' });
        }

        default:
            return errorResponse(cmd.id, `Unknown action: ${cmd.action}`);
    }
}

// Start server
const server = net.createServer((socket) => {
    let buffer = '';

    socket.on('data', async (data) => {
        buffer += data.toString();

        while (buffer.includes('\n')) {
            const idx = buffer.indexOf('\n');
            const line = buffer.substring(0, idx);
            buffer = buffer.substring(idx + 1);

            if (!line.trim()) continue;

            try {
                const parsed = parseCommand(line);
                if (!parsed.success) {
                    socket.write(serializeResponse(errorResponse(parsed.id ?? 'unknown', parsed.error)) + '\n');
                    continue;
                }

                const response = await handleCommand(parsed.command);
                socket.write(serializeResponse(response) + '\n');

                // Shutdown after close
                if (parsed.command.action === 'close' && !shuttingDown) {
                    shuttingDown = true;
                    setTimeout(() => {
                        server.close();
                        cleanup();
                        process.exit(0);
                    }, 100);
                }
            } catch (err) {
                const msg = err instanceof Error ? err.message : String(err);
                socket.write(serializeResponse(errorResponse('error', msg)) + '\n');
            }
        }
    });

    socket.on('error', () => {});
});

// Write PID
cleanup();
fs.writeFileSync(PID_FILE, process.pid.toString());

server.listen(SOCKET_PATH, () => {
    // Daemon ready
});

server.on('error', (err) => {
    console.error('Server error:', err);
    cleanup();
    process.exit(1);
});

// Signal handlers
const shutdown = async () => {
    if (shuttingDown) return;
    shuttingDown = true;
    if (browser) {
        try { await browser.close(); } catch {}
    }
    server.close();
    cleanup();
    process.exit(0);
};

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
process.on('SIGHUP', shutdown);
process.on('uncaughtException', (err) => {
    console.error('Uncaught exception:', err);
    cleanup();
    process.exit(1);
});
process.on('unhandledRejection', (reason) => {
    console.error('Unhandled rejection:', reason);
    cleanup();
    process.exit(1);
});
process.on('exit', () => cleanup());
process.stdin.resume();
