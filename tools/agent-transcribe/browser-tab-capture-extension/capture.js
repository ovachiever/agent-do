async function postBlob(port, path, blob) {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    method: 'POST',
    body: blob,
  });
  if (!response.ok) {
    throw new Error(`localhost ${path} returned ${response.status}`);
  }
}

async function postJson(port, path, payload) {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`localhost ${path} returned ${response.status}`);
  }
}

function postEvent(port, event, detail) {
  postJson(port, '/event', { event, detail }).catch(() => {});
}

function findTargetTab(tabs, urlNeedle, titleNeedle) {
  const urlMatch = tabs.find((tab) => tab.url && urlNeedle && tab.url.includes(urlNeedle));
  if (urlMatch) return urlMatch;
  const titleMatch = tabs.find((tab) => tab.title && titleNeedle && tab.title.includes(titleNeedle));
  if (titleMatch) return titleMatch;
  return tabs.find((tab) => tab.url && !tab.url.startsWith('chrome-extension://'));
}

function chooseDesktopStream(targetTab) {
  return new Promise((resolve, reject) => {
    let requestId;
    const timeout = setTimeout(() => {
      if (requestId) chrome.desktopCapture.cancelChooseDesktopMedia(requestId);
      reject(new Error('chrome.desktopCapture did not return a stream id'));
    }, 20000);

    requestId = chrome.desktopCapture.chooseDesktopMedia(
      ['tab', 'audio'],
      targetTab,
      (streamId, options) => {
        clearTimeout(timeout);
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        if (!streamId) {
          reject(new Error('chrome.desktopCapture returned no stream id'));
          return;
        }
        resolve({ streamId, options: options || {} });
      },
    );
  });
}

async function requestDesktopStream(streamId) {
  const mandatory = {
    chromeMediaSource: 'desktop',
    chromeMediaSourceId: streamId,
  };
  const constraints = [
    { audio: { mandatory }, video: { mandatory } },
    { audio: { mandatory }, video: false },
  ];
  let lastError;
  for (const item of constraints) {
    try {
      return await navigator.mediaDevices.getUserMedia(item);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

globalThis.agentDoStartDesktopCapture = async function agentDoStartDesktopCapture(options) {
  let stream;
  let recorder;
  let stopTimer;
  const pending = [];
  try {
    const tabs = await chrome.tabs.query({});
    const target = findTargetTab(tabs, options.urlNeedle, options.titleNeedle);
    if (!target?.id) {
      throw new Error('could not find target tab for desktop capture');
    }

    postEvent(options.port, 'capture-page-target', target.title || target.url || String(target.id));
    const selfTab = await chrome.tabs.getCurrent();
    const chosen = await chooseDesktopStream(target);
    postEvent(options.port, 'desktop-stream-id', JSON.stringify(chosen.options || {}));
    if (selfTab?.id) {
      await chrome.tabs.update(selfTab.id, { active: true }).catch(() => {});
    }
    stream = await Promise.race([
      requestDesktopStream(chosen.streamId),
      new Promise((_, reject) => {
        setTimeout(() => reject(new Error('getUserMedia timed out in capture page')), 15000);
      }),
    ]);
    postEvent(options.port, 'stream-ready', `${stream.getAudioTracks().length} audio / ${stream.getVideoTracks().length} video`);

    const audioTracks = stream.getAudioTracks();
    if (!audioTracks.length) {
      throw new Error('desktop capture returned no audio track');
    }
    const audioStream = new MediaStream(audioTracks);
    const mimeCandidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'video/webm;codecs=opus',
      'video/webm',
    ];
    const mimeType = mimeCandidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) || '';
    recorder = new MediaRecorder(audioStream, mimeType ? { mimeType } : undefined);

    recorder.ondataavailable = (event) => {
      if (!event.data || !event.data.size) return;
      pending.push(postBlob(options.port, '/chunk', event.data));
    };
    recorder.onerror = (event) => {
      postJson(options.port, '/error', {
        error: event.error?.message || 'MediaRecorder failed',
        mediaSource: 'desktop',
        sourceApi: 'chrome.desktopCapture',
      }).catch(() => {});
    };
    recorder.onstop = async () => {
      try {
        postEvent(options.port, 'recorder-stopped');
        clearTimeout(stopTimer);
        stream.getTracks().forEach((track) => track.stop());
        audioStream.getTracks().forEach((track) => track.stop());
        await Promise.all(pending);
        await postJson(options.port, '/done', {
          mimeType: recorder.mimeType,
          audioTracks: audioTracks.length,
          durationMs: options.durationMs,
          mediaSource: 'desktop',
          sourceApi: 'chrome.desktopCapture',
          target: {
            id: target.id,
            title: target.title,
            url: target.url,
          },
        });
      } catch (error) {
        await postJson(options.port, '/error', {
          error: error?.message || String(error),
          mediaSource: 'desktop',
          sourceApi: 'chrome.desktopCapture',
        }).catch(() => {});
      }
    };

    recorder.start(options.chunkMs || 5000);
    postEvent(options.port, 'recorder-started', recorder.mimeType);
    stopTimer = setTimeout(() => {
      postEvent(options.port, 'recorder-timeout-stop');
      if (recorder && recorder.state === 'recording') recorder.stop();
    }, options.durationMs);
    return {
      started: true,
      sourceApi: 'chrome.desktopCapture',
      target: {
        id: target.id,
        title: target.title,
        url: target.url,
      },
    };
  } catch (error) {
    if (stream) stream.getTracks().forEach((track) => track.stop());
    await postJson(options.port, '/error', {
      error: [error?.name, error?.message || String(error)].filter(Boolean).join(': '),
      mediaSource: 'desktop',
      sourceApi: 'chrome.desktopCapture',
    }).catch(() => {});
    throw error;
  }
};
