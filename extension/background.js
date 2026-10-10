importScripts('lib/psl.js', 'lib/disconnect.js', 'lib/report.js');

const STORE_PREFIX = 'tab:';
const WRITE_DELAY_MS = 150;
const supportedProtocols = new Set(['http:', 'https:']);
const BLOCK_RULESETS = ['allow_same_company', 'block_advertising', 'block_analytics', 'block_social', 'block_fingerprinting', 'block_cryptomining'];
const GPC_RULESET = 'gpc_headers';
const GPC_SCRIPT_ID = 'privacybrew-gpc-main';
const PAUSE_RULE_BASE = 100000;
const SAME_COMPANY_SESSION_BASE = 2000000;
const SAME_COMPANY_RULES_PER_TAB = 1000;
const RESOURCE_TYPES_WITHOUT_MAIN = ['sub_frame', 'stylesheet', 'script', 'image', 'font', 'object', 'xmlhttprequest', 'ping', 'csp_report', 'media', 'websocket', 'webtransport', 'webbundle', 'other'];
const BLOCKED_CATEGORIES = new Set(['Advertising', 'Analytics', 'Social', 'Fingerprinting', 'Cryptomining']);
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

async function getSettings() {
  const stored = await chrome.storage.local.get({ blockingEnabled: true, gpcEnabled: true, pausedSites: {} });
  return {
    blockingEnabled: stored.blockingEnabled !== false,
    gpcEnabled: stored.gpcEnabled !== false,
    pausedSites: stored.pausedSites || {}
  };
}

function pauseRuleId(siteDomain) {
  let hash = 0;
  for (const ch of siteDomain) hash = ((hash * 31) + ch.charCodeAt(0)) >>> 0;
  return PAUSE_RULE_BASE + (hash % 1000000);
}

async function applyPauseRules(pausedSites) {
  const existing = await chrome.declarativeNetRequest.getDynamicRules();
  const removeRuleIds = existing.filter((rule) => rule.id >= PAUSE_RULE_BASE).map((rule) => rule.id);
  const addRules = Object.keys(pausedSites || {}).sort().map((siteDomain) => ({
    id: pauseRuleId(siteDomain),
    priority: 10000,
    action: { type: 'allowAllRequests' },
    condition: {
      requestDomains: [siteDomain],
      resourceTypes: ['main_frame', 'sub_frame']
    }
  }));
  await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds, addRules });
}

async function applyRulesetSettings(settings) {
  const enableRulesetIds = [];
  const disableRulesetIds = [];
  if (settings.blockingEnabled) enableRulesetIds.push(...BLOCK_RULESETS);
  else disableRulesetIds.push(...BLOCK_RULESETS);
  if (settings.gpcEnabled) enableRulesetIds.push(GPC_RULESET);
  else disableRulesetIds.push(GPC_RULESET);
  await chrome.declarativeNetRequest.updateEnabledRulesets({ enableRulesetIds, disableRulesetIds });
  await applyPauseRules(settings.pausedSites);
}

async function applyGpcScript(enabled) {
  const registered = await chrome.scripting.getRegisteredContentScripts({ ids: [GPC_SCRIPT_ID] });
  const isRegistered = registered.length > 0;
  if (enabled && !isRegistered) {
    try {
      await chrome.scripting.registerContentScripts([{
        id: GPC_SCRIPT_ID,
        matches: ['<all_urls>'],
        js: ['gpc-main.js'],
        runAt: 'document_start',
        allFrames: true,
        matchOriginAsFallback: true,
        world: 'MAIN'
      }]);
    } catch (error) {
      // Another update registered it first. That is the state we want.
      if (!String(error && error.message).includes('Duplicate script ID')) throw error;
    }
  } else if (!enabled && isRegistered) {
    await chrome.scripting.unregisterContentScripts({ ids: [GPC_SCRIPT_ID] });
  }
}

// Runs one settings update at a time. On install or reload, Chrome can start
// several updates at once (onInstalled plus worker start). Two parallel
// updates can both try to register the GPC script and fail with
// "Duplicate script ID".
let settingsQueue = Promise.resolve();
function applySettings() {
  const run = settingsQueue.then(async () => {
    const settings = await getSettings();
    await applyRulesetSettings(settings);
    await applyGpcScript(settings.gpcEnabled);
    return settings;
  });
  settingsQueue = run.catch(() => {});
  return run;
}


function companyIdsForSite(siteDomain) {
  const ids = [];
  const companies = (disconnect && disconnect.data && disconnect.data.companies) || {};
  for (const [companyId, company] of Object.entries(companies)) {
    const props = company.properties || [];
    if (props.some((property) => psl.registrableDomain(property) === siteDomain || property === siteDomain)) ids.push(companyId);
  }
  return ids;
}

function blockedDomainsForCompanies(companyIds) {
  const ids = new Set(companyIds);
  const domains = [];
  const domainData = (disconnect && disconnect.data && disconnect.data.domains) || {};
  for (const [domain, rec] of Object.entries(domainData)) {
    if (ids.has(rec.companyId) && BLOCKED_CATEGORIES.has(rec.category)) domains.push(domain);
  }
  return domains.sort();
}

function sameCompanyRuleBase(tabId) {
  return SAME_COMPANY_SESSION_BASE + (tabId % 1000) * SAME_COMPANY_RULES_PER_TAB;
}

async function applySameCompanySessionRules(tabId, siteDomain) {
  const existing = await chrome.declarativeNetRequest.getSessionRules();
  const base = sameCompanyRuleBase(tabId);
  const removeRuleIds = existing.filter((rule) => rule.id > base && rule.id < base + SAME_COMPANY_RULES_PER_TAB).map((rule) => rule.id);
  const companyIds = siteDomain ? companyIdsForSite(siteDomain) : [];
  const domains = blockedDomainsForCompanies(companyIds);
  const addRules = domains.slice(0, SAME_COMPANY_RULES_PER_TAB - 1).map((domain, index) => ({
    id: base + index + 1,
    priority: 3,
    action: { type: 'allow' },
    condition: {
      tabIds: [tabId],
      requestDomains: [domain],
      resourceTypes: RESOURCE_TYPES_WITHOUT_MAIN
    }
  }));
  await chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds, addRules });
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
  await chrome.action.setBadgeText({ tabId, text: summary.blockedCompanyCount ? String(summary.blockedCompanyCount) : '' });
}

async function resetTab(tabId, url) {
  await ensureData();
  const siteDomain = siteDomainFor(url);
  const state = PB.Report.emptyState(tabId, url || '', siteDomain);
  state.status = siteDomain ? 'ok' : 'unsupported';
  await applySameCompanySessionRules(tabId, siteDomain);
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

async function isSitePaused(siteDomain) {
  const settings = await getSettings();
  return Boolean(settings.pausedSites[siteDomain]);
}

async function observeTrackerUrl(tabId, url, status) {
  if (tabId < 0 || !url || !isSupportedUrl(url)) return;
  const state = await ensureTabState(tabId, null);
  if (!state || state.status !== 'ok' || !state.siteDomain) return;
  const requestHost = psl.cleanHost(new URL(url).hostname);
  const requestDomain = psl.registrableDomain(requestHost);
  if (!requestDomain || requestDomain === state.siteDomain) return;
  const match = disconnect.find(requestHost);
  if (match && !disconnect.sameCompanyAsSite(match, state.siteDomain)) {
    const settings = await getSettings();
    const paused = Boolean(settings.pausedSites[state.siteDomain]);
    const blocked = status === 'blocked' && settings.blockingEnabled && !paused;
    PB.Report.addTracker(state, match, requestHost, blocked ? 'blocked' : 'allowed', url);
  } else if (!match) {
    PB.Report.addUnknown(state, requestDomain);
  }
  scheduleSave(tabId, state);
  await updateBadge(tabId, state);
}


async function observeResourceUrl(tabId, url, status) {
  if (tabId < 0 || !url || !isSupportedUrl(url)) return;
  const state = await ensureTabState(tabId, null);
  if (!state || state.status !== 'ok' || !state.siteDomain) return;
  const requestDomain = psl.registrableDomain(new URL(url).hostname);
  if (requestDomain && requestDomain !== state.siteDomain) {
    PB.Report.addOutsideScript(state, url, status);
    scheduleSave(tabId, state);
  }
  await observeTrackerUrl(tabId, url, status);
}

async function observeRequest(details) {
  await observeTrackerUrl(details.tabId, details.url, 'allowed');
}

async function observeBlocked(details) {
  if (details.error === 'net::ERR_BLOCKED_BY_CLIENT') {
    await observeTrackerUrl(details.tabId, details.url, 'blocked');
  }
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


function applySettingsToSummary(summary, settings) {
  if (!summary || !settings) return summary;
  const offForSite = Boolean(summary.siteDomain && settings.pausedSites[summary.siteDomain]);
  if (!settings.blockingEnabled || offForSite) {
    summary.blockedTrackerCount = 0;
    summary.allowedTrackerCount = summary.trackerRequestCount || 0;
    summary.blockedCompanyCount = 0;
    summary.adBlockedCount = 0;
    summary.adAllowedCount = summary.adTrackerCount || 0;
    summary.outsideScriptBlockedCount = 0;
    summary.sitePaused = offForSite;
    summary.trackers = (summary.trackers || []).map((tracker) => Object.assign({}, tracker, {
      status: 'Allowed',
      allowedDomains: Array.from(new Set([...(tracker.allowedDomains || []), ...(tracker.blockedDomains || [])])).sort(),
      allowedRequestUrls: Array.from(new Set([...(tracker.allowedRequestUrls || []), ...(tracker.blockedRequestUrls || [])])).sort(),
      blockedDomains: [],
      blockedRequestUrls: []
    }));
  }
  return summary;
}

async function setPaused(siteDomain, paused) {
  const settings = await getSettings();
  const pausedSites = Object.assign({}, settings.pausedSites);
  if (paused) pausedSites[siteDomain] = true;
  else delete pausedSites[siteDomain];
  await chrome.storage.local.set({ pausedSites });
  return applySettings();
}

async function setGlobalBlocking(enabled) {
  await chrome.storage.local.set({ blockingEnabled: Boolean(enabled) });
  return applySettings();
}

async function setGpc(enabled) {
  await chrome.storage.local.set({ gpcEnabled: Boolean(enabled) });
  return applySettings();
}

chrome.runtime.onInstalled.addListener(() => {
  applySettings().catch(console.error);
});
chrome.runtime.onStartup.addListener(() => {
  applySettings().catch(console.error);
});
chrome.webNavigation.onCommitted.addListener(resetOnTopFrame);
chrome.webNavigation.onHistoryStateUpdated.addListener(resetOnTopFrame);

chrome.webRequest.onBeforeRequest.addListener((details) => {
  observeRequest(details).catch(console.error);
}, { urls: ['<all_urls>'] });

chrome.webRequest.onErrorOccurred.addListener((details) => {
  observeBlocked(details).catch(console.error);
}, { urls: ['<all_urls>'] });

chrome.webRequest.onHeadersReceived.addListener((details) => {
  observeHeaders(details).catch(console.error);
}, { urls: ['<all_urls>'] }, ['responseHeaders', 'extraHeaders']);

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    await ensureData();
    if (message && message.type === 'resource' && sender.tab && sender.tab.id >= 0) {
      await observeResourceUrl(sender.tab.id, message.url || '', message.status || 'allowed');
      sendResponse({ ok: true });
      return;
    }
    if (message && message.type === 'fingerprint' && sender.tab && sender.tab.id >= 0) {
      const state = await ensureTabState(sender.tab.id, sender.url || null);
      if (state && state.status === 'ok') {
        PB.Report.addFingerprint(state, message.technique, message.origin || 'Script not known');
        scheduleSave(sender.tab.id, state);
        await updateBadge(sender.tab.id, state);
      }
      sendResponse({ ok: true });
      return;
    }
    if (message && message.type === 'getReport') {
      const state = await ensureTabState(message.tabId, null);
      const settings = await getSettings();
      const summary = applySettingsToSummary(state ? PB.Report.summarize(state) : { status: 'needReload' }, settings);
      summary.settings = settings;
      summary.sitePaused = Boolean(summary.siteDomain && settings.pausedSites[summary.siteDomain]);
      sendResponse({ ok: true, report: summary });
      return;
    }
    if (message && message.type === 'getSettings') {
      sendResponse({ ok: true, settings: await getSettings() });
      return;
    }
    if (message && message.type === 'setSitePaused') {
      const state = await getState(message.tabId);
      if (!state || !state.siteDomain) throw new Error('No website report');
      const settings = await setPaused(state.siteDomain, Boolean(message.paused));
      sendResponse({ ok: true, settings });
      return;
    }
    if (message && message.type === 'setGlobalBlocking') {
      sendResponse({ ok: true, settings: await setGlobalBlocking(message.enabled) });
      return;
    }
    if (message && message.type === 'setGpc') {
      sendResponse({ ok: true, settings: await setGpc(message.enabled) });
      return;
    }
    if (message && message.type === 'reloadTab') {
      await chrome.tabs.reload(message.tabId);
      sendResponse({ ok: true });
      return;
    }
    if (message && message.type === 'debugGetReport') {
      const state = await ensureTabState(message.tabId, null);
      const settings = await getSettings();
      sendResponse({ ok: true, state, report: state ? applySettingsToSummary(PB.Report.summarize(state), settings) : null, settings });
      return;
    }
    sendResponse({ ok: false });
  })().catch((error) => sendResponse({ ok: false, error: String(error) }));
  return true;
});

chrome.tabs && chrome.tabs.onRemoved && chrome.tabs.onRemoved.addListener((tabId) => {
  memory.delete(tabId);
  chrome.storage.session.remove(key(tabId));
  chrome.declarativeNetRequest.getSessionRules().then((rules) => {
    const base = sameCompanyRuleBase(tabId);
    const removeRuleIds = rules.filter((rule) => rule.id > base && rule.id < base + SAME_COMPANY_RULES_PER_TAB).map((rule) => rule.id);
    if (removeRuleIds.length) chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds });
  });
});

ensureData().then(applySettings).catch(console.error);
