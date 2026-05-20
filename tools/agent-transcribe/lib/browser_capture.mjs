#!/usr/bin/env node
/**
 * Browser-authenticated tab audio capture for agent-transcribe.
 *
 * This intentionally captures the tab, not the YouTube <video> element.
 * Element capture is unreliable for MSE-backed cross-origin media. Tab capture
 * lets Chromium's renderer keep doing the authenticated playback while
 * MediaRecorder records the tab audio stream to a local WebM file.
 */

import { createRequire } from 'node:module';
import http from 'node:http';
import { appendFile, mkdtemp, readFile, rm, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require('../../agent-browse/node_modules/playwright-core');
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const EXTENSION_DIR = path.resolve(SCRIPT_DIR, '..', 'browser-tab-capture-extension');

function debug(message) {
  if (process.env.AGENT_TRANSCRIBE_BROWSER_CAPTURE_DEBUG) {
    process.stderr.write(`[browser-capture] ${message}\n`);
  }
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith('--')) {
      throw new Error(`unexpected argument: ${arg}`);
    }
    const key = arg.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    const value = argv[i + 1];
    if (!value || value.startsWith('--')) {
      throw new Error(`missing value for ${arg}`);
    }
    args[key] = value;
    i += 1;
  }
  return args;
}

function sessionStoragePath(name) {
  return path.join(os.homedir(), '.agent-browse', 'sessions', name, 'session-storage.json');
}

function storageStatePath(name) {
  return path.join(os.homedir(), '.agent-browse', 'sessions', name, 'storage.json');
}

async function loadJson(file, fallback = null) {
  try {
    return JSON.parse(await readFile(file, 'utf8'));
  } catch {
    return fallback;
  }
}

async function waitForVideoMetadata(page, timeoutMs) {
  let lastError;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      await page.waitForLoadState('domcontentloaded', { timeout: timeoutMs }).catch(() => {});
      await page.waitForTimeout(attempt ? 1500 : 250);
      return await page.evaluate(
        ({ timeout }) => new Promise((resolve) => {
          const video = document.querySelector('video');
          if (!video) {
            resolve({ found: false });
            return;
          }
          const done = () => resolve({
            found: true,
            duration: Number.isFinite(video.duration) ? video.duration : null,
            currentTime: Number.isFinite(video.currentTime) ? video.currentTime : 0,
            paused: video.paused,
            muted: video.muted,
            volume: video.volume,
            readyState: video.readyState,
            src: video.currentSrc || video.src || '',
          });
          if (video.readyState >= 1) {
            done();
            return;
          }
          const timer = setTimeout(done, timeout);
          video.addEventListener('loadedmetadata', () => {
            clearTimeout(timer);
            done();
          }, { once: true });
        }),
        { timeout: timeoutMs },
      );
    } catch (error) {
      lastError = error;
      const message = error?.message || String(error);
      if (!message.includes('Execution context was destroyed') && !message.includes('Cannot find context')) {
        throw error;
      }
    }
  }
  throw lastError;
}

function requestBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (chunk) => chunks.push(Buffer.from(chunk)));
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

async function startChunkServer(outputPath) {
  let resolveDone;
  let rejectDone;
  let chunks = 0;
  let bytes = 0;
  const done = new Promise((resolve, reject) => {
    resolveDone = resolve;
    rejectDone = reject;
  });

  const server = http.createServer(async (req, res) => {
    try {
      if (req.method !== 'POST') {
        res.writeHead(405);
        res.end('method not allowed');
        return;
      }

      if (req.url === '/chunk') {
        const body = await requestBody(req);
        if (body.length) {
          await appendFile(outputPath, body);
          chunks += 1;
          bytes += body.length;
        }
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ ok: true }));
        return;
      }

      if (req.url === '/done') {
        const body = await requestBody(req);
        const payload = body.length ? JSON.parse(body.toString('utf8')) : {};
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ ok: true }));
        resolveDone({
          ...payload,
          chunks,
          bytes,
        });
        return;
      }

      if (req.url === '/error') {
        const body = await requestBody(req);
        const payload = body.length ? JSON.parse(body.toString('utf8')) : {};
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ ok: true }));
        const source = [payload.sourceApi, payload.mediaSource].filter(Boolean).join('/');
        rejectDone(new Error(`${payload.error || 'tab capture extension failed'}${source ? ` (${source})` : ''}`));
        return;
      }

      if (req.url === '/event') {
        const body = await requestBody(req);
        const payload = body.length ? JSON.parse(body.toString('utf8')) : {};
        debug(`extension event: ${payload.event || 'unknown'}${payload.detail ? ` (${payload.detail})` : ''}`);
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ ok: true }));
        return;
      }

      res.writeHead(404);
      res.end('not found');
    } catch (error) {
      res.writeHead(500, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ error: error?.message || String(error) }));
      rejectDone(error);
    }
  });

  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      server.off('error', reject);
      resolve();
    });
  });

  const address = server.address();
  const port = typeof address === 'object' && address ? address.port : null;
  if (!port) {
    throw new Error('could not allocate local chunk server port');
  }

  return {
    port,
    done,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

async function withTimeout(promise, timeoutMs, label) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${label} timed out`)), timeoutMs);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

function failureHint(failures) {
  const text = failures.map((item) => item.error || '').join(' ');
  if (text.includes('desktop capture start timed out') || text.includes('getUserMedia timed out')) {
    return ' Grant Screen & System Audio Recording permission to the browser used by agent-do transcribe, then retry.';
  }
  return '';
}

async function startCaptureAndWait(page, options) {
  const {
    captureTitle,
    durationMs,
    chunkMs,
  } = options;

  await page.exposeBinding('__agentDoRecorderChunk', async (_source, payload) => {
    await appendFile(options.outputPath, Buffer.from(payload.base64, 'base64'));
  });

  await page.evaluate(({ title }) => {
    let button = document.getElementById('__agent_do_capture_button');
    if (!button) {
      button = document.createElement('button');
      button.id = '__agent_do_capture_button';
      button.textContent = 'Start agent-do capture';
      button.style.position = 'fixed';
      button.style.zIndex = '2147483647';
      button.style.top = '8px';
      button.style.left = '8px';
      button.style.opacity = '0.01';
      document.documentElement.appendChild(button);
    }
    document.title = title;
  }, { title: captureTitle });

  const capturePromise = page.evaluate(
    ({ title, duration, timeslice, requestTimeout }) => new Promise((resolve, reject) => {
      const button = document.getElementById('__agent_do_capture_button');
      if (!button) {
        reject(new Error('capture button was not installed'));
        return;
      }

      button.onclick = async () => {
        const pendingWrites = [];
        let stream;
        let recorder;
        let stopTimer;
        try {
          document.title = title;
          const displayRequest = navigator.mediaDevices.getDisplayMedia({
            video: true,
            audio: true,
            preferCurrentTab: true,
            selfBrowserSurface: 'include',
            systemAudio: 'include',
            surfaceSwitching: 'exclude',
          });
          const timeoutRequest = new Promise((_, timeoutReject) => {
            setTimeout(() => timeoutReject(new Error('getDisplayMedia timed out waiting for tab capture approval')), requestTimeout);
          });
          stream = await Promise.race([displayRequest, timeoutRequest]);

          const audioTracks = stream.getAudioTracks();
          if (!audioTracks.length) {
            stream.getTracks().forEach((track) => track.stop());
            reject(new Error('tab capture returned no audio track'));
            return;
          }

          const audioStream = new MediaStream(audioTracks);
          const mimeCandidates = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'video/webm;codecs=opus',
            'video/webm',
          ];
          const mimeType = mimeCandidates.find((m) => MediaRecorder.isTypeSupported(m)) || '';
          recorder = new MediaRecorder(audioStream, mimeType ? { mimeType } : undefined);

          recorder.ondataavailable = (event) => {
            if (!event.data || !event.data.size) return;
            const writePromise = new Promise((writeResolve, writeReject) => {
              const reader = new FileReader();
              reader.onloadend = () => {
                const value = String(reader.result || '');
                const base64 = value.includes(',') ? value.split(',').pop() : value;
                window.__agentDoRecorderChunk({ base64 }).then(writeResolve, writeReject);
              };
              reader.onerror = () => writeReject(reader.error || new Error('failed to read media chunk'));
              reader.readAsDataURL(event.data);
            });
            pendingWrites.push(writePromise);
          };

          recorder.onerror = (event) => {
            reject(new Error(event.error?.message || 'MediaRecorder failed'));
          };

          recorder.onstop = async () => {
            try {
              clearTimeout(stopTimer);
              stream.getTracks().forEach((track) => track.stop());
              await Promise.all(pendingWrites);
              resolve({
                mimeType: recorder.mimeType,
                audioTracks: audioTracks.length,
                durationMs: duration,
              });
            } catch (error) {
              reject(error);
            }
          };

          recorder.start(timeslice);

          const video = document.querySelector('video');
          if (video) {
            video.muted = false;
            video.volume = 1;
            video.playbackRate = 1;
            await video.play().catch(() => {});
            video.addEventListener('ended', () => {
              if (recorder && recorder.state === 'recording') recorder.stop();
            }, { once: true });
          }

          stopTimer = setTimeout(() => {
            if (recorder && recorder.state === 'recording') recorder.stop();
          }, duration);
        } catch (error) {
          if (stream) stream.getTracks().forEach((track) => track.stop());
          reject(error);
        }
      };
    }),
    { title: captureTitle, duration: durationMs, timeslice: chunkMs, requestTimeout: Number(options.requestTimeoutMs || 20_000) },
  );

  await page.click('#__agent_do_capture_button', { timeout: 10_000 });
  return capturePromise;
}

async function computeCaptureTiming(page, args) {
  const videoInfo = await waitForVideoMetadata(page, 15_000);
  if (!videoInfo.found) {
    throw new Error('no <video> element found after navigation');
  }

  const explicitSeconds = args.durationSeconds ? Number(args.durationSeconds) : null;
  const bufferSeconds = args.bufferSeconds ? Number(args.bufferSeconds) : 5;
  const remaining = videoInfo.duration ? Math.max(1, videoInfo.duration - (videoInfo.currentTime || 0)) : null;
  const captureSeconds = explicitSeconds || (remaining ? remaining + bufferSeconds : null);
  if (!captureSeconds || !Number.isFinite(captureSeconds) || captureSeconds <= 0) {
    throw new Error('could not determine capture duration; pass --capture-seconds');
  }
  return { videoInfo, captureSeconds };
}

async function restoreSessionStorage(context, sessionStorage) {
  await context.addInitScript((savedSessionStorage) => {
    try {
      for (const [key, value] of Object.entries(savedSessionStorage || {})) {
        window.sessionStorage.setItem(key, String(value));
      }
    } catch {
      // Some origins disallow sessionStorage during early init. Cookies and
      // localStorage from storageState are still the important auth layer.
    }
  }, sessionStorage);
}

async function captureWithDisplayMedia(args, shared) {
  const { outputPath, captureTitle, storageState, sessionStorage, executablePath } = shared;
  debug('starting getDisplayMedia backend');
  const browser = await chromium.launch({
    headless: false,
    executablePath,
    args: [
      '--use-fake-ui-for-media-stream',
      '--enable-usermedia-screen-capturing',
      '--auto-accept-this-tab-capture',
      `--auto-select-tab-capture-source-by-title=${captureTitle}`,
      `--auto-select-desktop-capture-source=${captureTitle}`,
      '--disable-blink-features=AutomationControlled',
    ],
  });

  try {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 900 },
      storageState,
    });
    await context.grantPermissions(['camera', 'microphone']).catch(() => {});
    await context.grantPermissions(['display-capture']).catch(() => {});
    await restoreSessionStorage(context, sessionStorage);

    const page = await context.newPage();
    page.setDefaultTimeout(Number(args.timeoutMs || 60_000));
    debug('navigating target page for getDisplayMedia backend');
    await page.goto(args.url, { waitUntil: 'domcontentloaded', timeout: Number(args.timeoutMs || 60_000) });
    await page.waitForSelector('video', { timeout: Number(args.videoTimeoutMs || 90_000) });

    const { videoInfo, captureSeconds } = await computeCaptureTiming(page, args);
    debug(`getDisplayMedia capture timing: ${captureSeconds}s`);

    const result = await startCaptureAndWait(page, {
      captureTitle,
      outputPath,
      durationMs: Math.ceil(captureSeconds * 1000),
      chunkMs: Number(args.chunkMs || 5000),
      requestTimeoutMs: Number(args.requestTimeoutMs || 20_000),
    });
    await context.close().catch(() => {});

    return {
      success: true,
      path: outputPath,
      capture_seconds: captureSeconds,
      video: videoInfo,
      backend: 'getDisplayMedia',
      recorder: result,
    };
  } finally {
    await browser.close().catch(() => {});
  }
}

async function waitForExtensionWorker(context) {
  let worker = context.serviceWorkers().find((item) => item.url().startsWith('chrome-extension://'));
  if (worker) return worker;
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    const next = await context.waitForEvent('serviceworker', { timeout: Math.max(1000, deadline - Date.now()) });
    if (next.url().startsWith('chrome-extension://')) return next;
  }
  throw new Error('extension service worker did not start');
}

async function captureWithTabCaptureExtension(args, shared) {
  const {
    outputPath,
    captureTitle,
    storageState,
    sessionStorage,
    executablePath,
  } = shared;
  if (!existsSync(EXTENSION_DIR)) {
    throw new Error(`tab capture extension missing: ${EXTENSION_DIR}`);
  }

  debug('starting chrome.tabCapture extension backend');
  const userDataDir = await mkdtemp(path.join(os.tmpdir(), 'agent-transcribe-chrome-'));
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    executablePath,
    ignoreDefaultArgs: ['--disable-extensions'],
    viewport: { width: 1280, height: 900 },
    args: [
      `--disable-extensions-except=${EXTENSION_DIR}`,
      `--load-extension=${EXTENSION_DIR}`,
      '--use-fake-ui-for-media-stream',
      '--enable-usermedia-screen-capturing',
      '--auto-accept-this-tab-capture',
      `--auto-select-tab-capture-source-by-title=${captureTitle}`,
      `--auto-select-desktop-capture-source=${captureTitle}`,
      '--autoplay-policy=no-user-gesture-required',
      '--disable-blink-features=AutomationControlled',
    ],
  });
  let chunkServer;

  try {
    if (Array.isArray(storageState?.cookies) && storageState.cookies.length) {
      await context.addCookies(storageState.cookies);
    }
    await restoreSessionStorage(context, sessionStorage);

    const page = await context.newPage();
    page.setDefaultTimeout(Number(args.timeoutMs || 60_000));
    debug('navigating target page for chrome.tabCapture backend');
    await page.goto(args.url, { waitUntil: 'domcontentloaded', timeout: Number(args.timeoutMs || 60_000) });
    await page.waitForSelector('video', { timeout: Number(args.videoTimeoutMs || 90_000) });
    await page.evaluate(({ title }) => {
      document.title = title;
      const video = document.querySelector('video');
      if (video) {
        video.muted = false;
        video.volume = 1;
        video.playbackRate = 1;
      }
    }, { title: captureTitle });
    await page.click('video', { timeout: 10_000 }).catch(() => {});
    await page.evaluate(() => {
      const video = document.querySelector('video');
      if (video) {
        video.muted = false;
        video.volume = 1;
        video.playbackRate = 1;
        const playPromise = video.play();
        if (playPromise?.catch) playPromise.catch(() => {});
      }
    });

    const { videoInfo, captureSeconds } = await computeCaptureTiming(page, args);
    debug(`chrome.tabCapture capture timing: ${captureSeconds}s`);
    const durationMs = Math.ceil(captureSeconds * 1000);
    const chunkMs = Number(args.chunkMs || 5000);
    chunkServer = await startChunkServer(outputPath);
    debug(`chunk server listening on ${chunkServer.port}`);
    const worker = await waitForExtensionWorker(context);
    debug('extension service worker ready');
    const extensionId = new URL(worker.url()).host;
    const capturePage = await context.newPage();
    await capturePage.goto(`chrome-extension://${extensionId}/capture.html`, { waitUntil: 'domcontentloaded' });
    const parsedUrl = new URL(args.url);
    const urlNeedle = parsedUrl.searchParams.get('v') || parsedUrl.pathname || args.url;
    const started = await withTimeout(
      capturePage.evaluate(
        async ({ needle, title, port, duration, timeslice }) => globalThis.agentDoStartDesktopCapture({
          urlNeedle: needle,
          titleNeedle: title,
          port,
          durationMs: duration,
          chunkMs: timeslice,
        }),
        {
          needle: urlNeedle,
          title: captureTitle,
          port: chunkServer.port,
          duration: durationMs,
          timeslice: chunkMs,
        },
      ),
      Number(args.captureStartTimeoutMs || 45_000),
      'desktop capture start',
    );
    debug('extension reported capture start');
    const recorder = await withTimeout(chunkServer.done, durationMs + 30_000, 'tab capture extension recording');
    debug('extension reported capture done');

    return {
      success: true,
      path: outputPath,
      capture_seconds: captureSeconds,
      video: videoInfo,
      backend: 'chrome.tabCapture',
      extension: started,
      recorder,
    };
  } finally {
    if (chunkServer) {
      await chunkServer.close().catch(() => {});
    }
    await context.close().catch(() => {});
    await rm(userDataDir, { recursive: true, force: true }).catch(() => {});
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.url) throw new Error('--url is required');
  if (!args.session) throw new Error('--session is required');
  if (!args.output) throw new Error('--output is required');

  const storagePath = storageStatePath(args.session);
  if (!existsSync(storagePath)) {
    throw new Error(`browse session not found: ${args.session}`);
  }

  const outputPath = path.resolve(args.output);
  await rm(outputPath, { force: true }).catch(() => {});

  const parsedUrl = new URL(args.url);
  const captureTitle = args.captureTitle || (parsedUrl.hostname.includes('youtube.com') || parsedUrl.hostname.includes('youtu.be')
    ? 'YouTube'
    : `agent-do-transcribe-${Date.now()}`);
  const storageState = await loadJson(storagePath);
  const sessionStorage = await loadJson(sessionStoragePath(args.session), {});
  const executablePath = process.env.AGENT_BROWSER_EXECUTABLE_PATH || undefined;
  const backend = args.backend || 'auto';
  const isYouTube = parsedUrl.hostname.includes('youtube.com') || parsedUrl.hostname.includes('youtu.be');
  const shared = {
    outputPath,
    captureTitle,
    storageState,
    sessionStorage,
    executablePath,
  };

  let result;
  const failures = [];
  if (backend === 'getdisplaymedia' || (backend === 'auto' && !isYouTube)) {
    try {
      result = await captureWithDisplayMedia(args, shared);
    } catch (error) {
      failures.push({
        backend: 'getDisplayMedia',
        error: error?.message || String(error),
      });
      await rm(outputPath, { force: true }).catch(() => {});
      if (backend === 'getdisplaymedia') {
        throw new Error(`${error?.message || String(error)}.${failureHint(failures)}`);
      }
    }
  }

  if (!result && (backend === 'auto' || backend === 'tabcapture')) {
    try {
      result = await captureWithTabCaptureExtension(args, shared);
    } catch (error) {
      failures.push({
        backend: 'chrome.tabCapture',
        error: error?.message || String(error),
      });
      await rm(outputPath, { force: true }).catch(() => {});
      if (backend === 'tabcapture') {
        throw new Error(`${error?.message || String(error)}.${failureHint(failures)}`);
      }
    }
  }

  if (!result) {
    throw new Error(`all browser capture backends failed: ${failures.map((f) => `${f.backend}: ${f.error}`).join(' | ')}.${failureHint(failures)}`);
  }

  const fileStat = await stat(outputPath);
  process.stdout.write(JSON.stringify({
    ...result,
    size_bytes: fileStat.size,
    attempted_backends: failures.length ? failures : undefined,
  }) + '\n');
}

main().catch((error) => {
  process.stdout.write(JSON.stringify({
    success: false,
    error: error?.message || String(error),
  }) + '\n');
  process.exit(1);
});
