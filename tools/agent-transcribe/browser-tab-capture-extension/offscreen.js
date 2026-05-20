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

function getUserMediaCompat(constraints) {
  if (navigator.mediaDevices?.getUserMedia) {
    return navigator.mediaDevices.getUserMedia(constraints);
  }
  return new Promise((resolve, reject) => {
    navigator.webkitGetUserMedia(constraints, resolve, reject);
  });
}

async function requestChromeMediaStream(mediaSource, streamId) {
  const mandatory = {
    chromeMediaSource: mediaSource,
    chromeMediaSourceId: streamId,
  };
  const candidates = mediaSource === 'desktop'
    ? [
        { audio: { mandatory }, video: { mandatory } },
        { audio: { mandatory }, video: false },
      ]
    : [
        { audio: { mandatory }, video: false },
        { audio: { mandatory }, video: { mandatory } },
      ];
  let lastError;
  for (const constraints of candidates) {
    try {
      return await getUserMediaCompat(constraints);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

async function startCapture(message) {
  let stream;
  let recorder;
  let stopTimer;
  const pending = [];
  try {
    const mediaSource = message.mediaSource || 'tab';
    postEvent(message.port, 'offscreen-start', `${message.sourceApi || 'unknown'}/${mediaSource}`);
    stream = await Promise.race([
      requestChromeMediaStream(mediaSource, message.streamId),
      new Promise((_, reject) => {
        setTimeout(() => reject(new Error('getUserMedia timed out in offscreen document')), 15000);
      }),
    ]);
    postEvent(message.port, 'stream-ready', `${stream.getAudioTracks().length} audio / ${stream.getVideoTracks().length} video`);
    const audioTracks = stream.getAudioTracks();
    if (!audioTracks.length) {
      throw new Error('tabCapture returned no audio track');
    }

    const mimeCandidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'video/webm;codecs=opus',
      'video/webm',
    ];
    const mimeType = mimeCandidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) || '';
    const audioStream = new MediaStream(audioTracks);
    recorder = new MediaRecorder(audioStream, mimeType ? { mimeType } : undefined);

    recorder.ondataavailable = (event) => {
      if (!event.data || !event.data.size) return;
      pending.push(postBlob(message.port, '/chunk', event.data));
    };
    recorder.onerror = (event) => {
      postJson(message.port, '/error', {
        error: event.error?.message || 'MediaRecorder failed',
      }).catch(() => {});
    };
    recorder.onstop = async () => {
      try {
        postEvent(message.port, 'recorder-stopped');
        clearTimeout(stopTimer);
        stream.getTracks().forEach((track) => track.stop());
        audioStream.getTracks().forEach((track) => track.stop());
        await Promise.all(pending);
        await postJson(message.port, '/done', {
          mimeType: recorder.mimeType,
          audioTracks: audioTracks.length,
          durationMs: message.durationMs,
          mediaSource,
        });
      } catch (error) {
        await postJson(message.port, '/error', {
          error: error?.message || String(error),
        }).catch(() => {});
      }
    };

    recorder.start(message.chunkMs || 5000);
    postEvent(message.port, 'recorder-started', recorder.mimeType);
    stopTimer = setTimeout(() => {
      postEvent(message.port, 'recorder-timeout-stop');
      if (recorder && recorder.state === 'recording') recorder.stop();
    }, message.durationMs);
  } catch (error) {
    if (stream) stream.getTracks().forEach((track) => track.stop());
    await postJson(message.port, '/error', {
      error: [error?.name, error?.message || String(error)].filter(Boolean).join(': '),
      mediaSource: message.mediaSource || 'tab',
      sourceApi: message.sourceApi,
    }).catch(() => {});
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== 'agent-do-start-tab-capture') return false;
  startCapture(message);
  sendResponse({ started: true });
  return true;
});
