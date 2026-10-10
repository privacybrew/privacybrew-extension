importScripts('lib/psl.js', 'lib/disconnect.js', 'lib/report.js');

const STORE_PREFIX = 'tab:';
const WRITE_DELAY_MS = 150;
const supportedProtocols = new Set(['http:', 'https:']);
let dataReady = null;
let psl = null;
let disconnect = null;
const memory = new Map();
const timers = new Map();

async function loadJson(path) {
  const response = await fetch(chrome.runtime.getURL(path));
  return response.json();
}

async function ensureData() {
  if (!dataReady) {
    dataReady = Promise.all([loadJson('data/psl.json'), loadJson('data/disconnect.json')]).then(([pslData, disconnectData]) => {
      psl = PB.PSL.initPsl(pslData);
      disconnect = PB.Disconnect.initDisconnect(disconnectData, psl);
    });
  }
  return dataReady;
}

function key(tabId) {
  return STORE_PREFIX + String(tabId);
}

function isSupportedUrl(url) {
  try {
    return supportedProtocols.has(new URL(url).protocol);
  } catch (_) {
    return false;
  }
}

function isBrowserStoreUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.hostname === 'chromewebstore.google.com' || (parsed.hostname === 'chrome.google.com' && parsed.pathname.startsWith('/webstore'));
  } catch (_) {
    return false;
  }
}

function siteDomainFor(url) {
  if (!isSupportedUrl(url) || isBrowserStoreUrl(url)) return '';
  return psl.registrableDomain(new URL(url).hostname);
}

async function getState(tabId) {
  if (memory.has(tabId)) return memory.get(tabId);
  const obj = await chrome.storage.session.get(key(tabId));
  const state = obj[key(tabId)] || null;
  if (state) memory.set(tabId, state);
  return state;
}

function scheduleSave(tabId, state) {
  memory.set(tabId, state);
  clearTimeout(timers.get(tabId));
  timers.set(tabId, setTimeout(async () => {
    timers.delete(tabId);
    await chrome.storage.session.set({ [key(tabId)]: state });
  }, WRITE_DELAY_MS));
}

async function saveNow(tabId, state) {
  memory.set(tabId, state);
  clearTimeout(timers.get(tabId));
  timers.delete(tabId);
  await chrome.storage.session.set({ [key(tabId)]: state });
}

async function updateBadge(tabId, state) {
  const summary = PB.Report.summarize(state || {});
  await chrome.action.setBadgeBackgroundColor({ tabId, color: '#9b6dd1' });
  await chrome.action.setBadgeText({ tabId, text: summary.trackerCount ? String(summary.trackerCount) : '' });
}

async function resetTab(tabId, url) {
  await ensureData();
  const siteDomain = siteDomainFor(url);
  const state = PB.Report.emptyState(tabId, url || '', siteDomain);
  state.status = siteDomain ? 'ok' : 'unsupported';
  await saveNow(tabId, state);
  await updateBadge(tabId, state);
}

async function ensureTabState(tabId, fallbackUrl) {
  await ensureData();
  let state = await getState(tabId);
  if (!state && fallbackUrl) {
    const siteDomain = siteDomainFor(fallbackUrl);
    state = PB.Report.emptyState(tabId, fallbackUrl, siteDomain);
    state.status = siteDomain ? 'ok' : 'needReload';
    await saveNow(tabId, state);
  }
  return state;
}

function hasSetCookie(headers) {
  return (headers || []).some((header) => header.name && header.name.toLowerCase() === 'set-cookie');
}

async function observeRequest(details) {
  if (details.tabId < 0 || !details.url || !isSupportedUrl(details.url)) return;
  const state = await ensureTabState(details.tabId, null);
  if (!state || state.status !== 'ok' || !state.siteDomain) return;
  const requestHost = psl.cleanHost(new URL(details.url).hostname);
  const requestDomain = psl.registrableDomain(requestHost);
  if (!requestDomain || requestDomain === state.siteDomain) return;
  const match = disconnect.find(requestHost);
  if (match && !disconnect.sameCompanyAsSite(match, state.siteDomain)) {
    PB.Report.addTracker(state, match, requestHost);
  } else if (!match) {
    PB.Report.addUnknown(state, requestDomain);
  }
  scheduleSave(details.tabId, state);
  await updateBadge(details.tabId, state);
}

async function observeHeaders(details) {
  if (details.tabId < 0 || !hasSetCookie(details.responseHeaders) || !details.url || !isSupportedUrl(details.url)) return;
  const state = await ensureTabState(details.tabId, null);
  if (!state || state.status !== 'ok' || !state.siteDomain) return;
  const responseHost = psl.cleanHost(new URL(details.url).hostname);
  const responseDomain = psl.registrableDomain(responseHost);
  if (responseDomain && responseDomain !== state.siteDomain) {
    PB.Report.addCookie(state, responseHost);
    scheduleSave(details.tabId, state);
  }
}

function resetOnTopFrame(details) {
  if (details.frameId === 0 && details.tabId >= 0) {
    resetTab(details.tabId, details.url).catch(console.error);
  }
}

chrome.webNavigation.onCommitted.addListener(resetOnTopFrame);
chrome.webNavigation.onHistoryStateUpdated.addListener(resetOnTopFrame);

chrome.webRequest.onBeforeRequest.addListener((details) => {
  observeRequest(details).catch(console.error);
}, { urls: ['<all_urls>'] });

chrome.webRequest.onHeadersReceived.addListener((details) => {
  observeHeaders(details).catch(console.error);
}, { urls: ['<all_urls>'] }, ['responseHeaders', 'extraHeaders']);

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    await ensureData();
    if (message && message.type === 'fingerprint' && sender.tab && sender.tab.id >= 0) {
      const state = await ensureTabState(sender.tab.id, sender.url || null);
      if (state && state.status === 'ok') {
        PB.Report.addFingerprint(state, message.technique, message.origin || 'Unknown script');
        scheduleSave(sender.tab.id, state);
        await updateBadge(sender.tab.id, state);
      }
      sendResponse({ ok: true });
      return;
    }
    if (message && message.type === 'getReport') {
      const state = await ensureTabState(message.tabId, null);
      sendResponse({ ok: true, report: state ? PB.Report.summarize(state) : { status: 'needReload' } });
      return;
    }
    if (message && message.type === 'debugGetReport') {
      const state = await ensureTabState(message.tabId, null);
      sendResponse({ ok: true, state, report: state ? PB.Report.summarize(state) : null });
      return;
    }
    sendResponse({ ok: false });
  })().catch((error) => sendResponse({ ok: false, error: String(error) }));
  return true;
});

chrome.tabs && chrome.tabs.onRemoved && chrome.tabs.onRemoved.addListener((tabId) => {
  memory.delete(tabId);
  chrome.storage.session.remove(key(tabId));
});

ensureData().catch(console.error);
