async function ensureOffscreenDocument() {
  if (chrome.offscreen?.hasDocument && await chrome.offscreen.hasDocument()) {
    return;
  }
  try {
    await chrome.offscreen.createDocument({
      url: 'offscreen.html',
      reasons: ['USER_MEDIA'],
      justification: 'Record authenticated tab audio for agent-do transcription.',
    });
  } catch (error) {
    if (!String(error?.message || error).includes('Only a single offscreen document')) {
      throw error;
    }
  }
}

function getStreamId(targetTabId) {
  return new Promise((resolve, reject) => {
    chrome.tabCapture.getMediaStreamId({ targetTabId }, (streamId) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!streamId) {
        reject(new Error('chrome.tabCapture returned no stream id'));
        return;
      }
      resolve(streamId);
    });
  });
}

function getDesktopStreamId(targetTab) {
  return new Promise((resolve, reject) => {
    let requestId;
    const timeout = setTimeout(() => {
      if (requestId) chrome.desktopCapture.cancelChooseDesktopMedia(requestId);
      reject(new Error('chrome.desktopCapture did not return a stream id'));
    }, 20000);

    requestId = chrome.desktopCapture.chooseDesktopMedia(
      ['tab', 'audio'],
      targetTab,
      (streamId) => {
        clearTimeout(timeout);
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        if (!streamId) {
          reject(new Error('chrome.desktopCapture returned no stream id'));
          return;
        }
        resolve(streamId);
      },
    );
  });
}

function findTargetTab(tabs, urlNeedle, titleNeedle) {
  const urlMatch = tabs.find((tab) => tab.url && urlNeedle && tab.url.includes(urlNeedle));
  if (urlMatch) return urlMatch;
  const titleMatch = tabs.find((tab) => tab.title && titleNeedle && tab.title.includes(titleNeedle));
  if (titleMatch) return titleMatch;
  const active = tabs.find((tab) => tab.active && tab.url && !tab.url.startsWith('chrome-extension://'));
  if (active) return active;
  return tabs.find((tab) => tab.url && !tab.url.startsWith('chrome-extension://'));
}

globalThis.agentDoCaptureStart = async function agentDoCaptureStart(options) {
  const tabs = await chrome.tabs.query({});
  const target = findTargetTab(tabs, options.urlNeedle, options.titleNeedle);
  if (!target?.id) {
    throw new Error('could not find target tab for capture');
  }

  await chrome.tabs.update(target.id, { active: true });
  let streamId;
  let mediaSource = 'tab';
  let sourceApi = 'chrome.tabCapture';
  try {
    streamId = await getStreamId(target.id);
  } catch (error) {
    streamId = await getDesktopStreamId(target);
    mediaSource = 'desktop';
    sourceApi = 'chrome.desktopCapture';
  }
  await ensureOffscreenDocument();
  await chrome.runtime.sendMessage({
    type: 'agent-do-start-tab-capture',
    streamId,
    mediaSource,
    sourceApi,
    port: options.port,
    durationMs: options.durationMs,
    chunkMs: options.chunkMs,
  });
  return {
    started: true,
    tab: {
      id: target.id,
      title: target.title,
      url: target.url,
    },
    sourceApi,
  };
};
