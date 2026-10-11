importScripts('lib/psl.js', 'lib/disconnect.js', 'lib/report.js');

const STORE_PREFIX = 'tab:';
const WRITE_DELAY_MS = 150;
const supportedProtocols = new Set(['http:', 'https:']);
const AD_RULESETS = ['ads_easylist'];
const BLOCK_RULESETS = ['allow_same_company', 'block_advertising', 'block_analytics', 'block_social', 'block_fingerprinting', 'block_cryptomining'];
const GPC_RULESET = 'gpc_headers';
const GPC_SCRIPT_ID = 'privacybrew-gpc-main';
let cosmeticData = null;
let adIndexData = null;
let autoconsentRules = null;
let autoconsentEvalSnippets = null;
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
const cookiePopupTimers = new Map();

async function loadJson(path) {
  const response = await fetch(chrome.runtime.getURL(path));
  return response.json();
}

async function ensureCosmeticData() {
  if (!cosmeticData) cosmeticData = await loadJson('data/easylist_cosmetic.json');
  return cosmeticData;
}

async function ensureAdIndex() {
  if (!adIndexData) adIndexData = await loadJson('data/easylist_ad_index.json');
  return adIndexData;
}

async function ensureAutoconsentRules() {
  if (!autoconsentRules) autoconsentRules = await loadJson('vendor/autoconsent/compact-rules.json');
  return autoconsentRules;
}

async function ensureAutoconsentEvalSnippets() {
  if (!autoconsentEvalSnippets) autoconsentEvalSnippets = await loadJson('vendor/autoconsent/eval-snippets.json');
  return autoconsentEvalSnippets;
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
  const stored = await chrome.storage.local.get({ blockingEnabled: true, adBlockingEnabled: true, cookiePopupEnabled: true, gpcEnabled: true, pausedSites: {} });
  return {
    blockingEnabled: stored.blockingEnabled !== false,
    adBlockingEnabled: stored.adBlockingEnabled !== false,
    cookiePopupEnabled: stored.cookiePopupEnabled !== false,
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
  if (settings.blockingEnabled && settings.adBlockingEnabled) enableRulesetIds.push(...AD_RULESETS);
  else disableRulesetIds.push(...AD_RULESETS);
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
  if (status === 'blocked') await observeAdBlocked(tabId, url);
  await observeTrackerUrl(tabId, url, status);
}

async function observeRequest(details) {
  if (!details.url || !isSupportedUrl(details.url) || details.tabId < 0) return;
  const state = await ensureTabState(details.tabId, null);
  if (!state || state.status !== 'ok' || !state.siteDomain) return;
  const requestDomain = psl.registrableDomain(new URL(details.url).hostname);
  if (requestDomain && requestDomain !== state.siteDomain && !disconnect.find(new URL(details.url).hostname)) {
    PB.Report.addUnknown(state, requestDomain);
    scheduleSave(details.tabId, state);
  }
}


function filterToRegex(filter) {
  let out = '';
  const text = String(filter);
  for (const ch of text) {
    if (ch === '*') out += '.*';
    else if (ch === '^') out += '[^A-Za-z0-9_.%-]';
    else if ('\\.+?${}()|[]'.includes(ch)) out += '\\' + ch;
    else out += ch;
  }
  if (out.startsWith('\\|')) out = '^' + out.slice(2);
  return new RegExp(out);
}

async function looksLikeAdUrl(url) {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname;
    const index = await ensureAdIndex();
    if ((index.domains || []).some((domain) => host === domain || host.endsWith('.' + domain))) return true;
    return (index.urlFilters || []).some((filter) => filterToRegex(filter).test(url));
  } catch (_) {
    return false;
  }
}

async function observeAdBlocked(tabId, url) {
  if (tabId < 0 || !url || !isSupportedUrl(url) || !(await looksLikeAdUrl(url))) return;
  const state = await ensureTabState(tabId, null);
  if (!state || state.status !== 'ok') return;
  PB.Report.addAdBlocked(state, url);
  scheduleSave(tabId, state);
}

async function observeBlocked(details) {
  if (details.error === 'net::ERR_BLOCKED_BY_CLIENT') {
    await observeTrackerUrl(details.tabId, details.url, 'blocked');
    await observeAdBlocked(details.tabId, details.url);
  }
}

async function observeHeaders(details) {
  if (details.tabId < 0 || !details.url || !isSupportedUrl(details.url)) return;
  await observeTrackerUrl(details.tabId, details.url, 'allowed');
  if (!hasSetCookie(details.responseHeaders)) return;
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
    summary.adBlockedRequestCount = 0;
    summary.sitePaused = offForSite;
    summary.trackers = (summary.trackers || []).map((tracker) => Object.assign({}, tracker, {
      status: 'Allowed',
      allowedDomains: Array.from(new Set([...(tracker.allowedDomains || []), ...(tracker.blockedDomains || [])])).sort(),
      allowedRequestHashes: Array.from(new Set([...(tracker.allowedRequestHashes || []), ...(tracker.blockedRequestHashes || [])])).sort(),
      blockedDomains: [],
      blockedRequestHashes: []
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

async function setAdBlocking(enabled) {
  await chrome.storage.local.set({ adBlockingEnabled: Boolean(enabled) });
  return applySettings();
}

async function setCookiePopupHandling(enabled) {
  await chrome.storage.local.set({ cookiePopupEnabled: Boolean(enabled) });
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

chrome.webRequest.onBeforeRequest.addListener((details) => {
  observeRequest(details).catch(console.error);
}, { urls: ['<all_urls>'] });

chrome.webRequest.onErrorOccurred.addListener((details) => {
  observeBlocked(details).catch(console.error);
}, { urls: ['<all_urls>'] });

chrome.webRequest.onHeadersReceived.addListener((details) => {
  observeHeaders(details).catch(console.error);
}, { urls: ['<all_urls>'] }, ['responseHeaders', 'extraHeaders']);


function autoconsentConfig(enabled) {
  return {
    enabled,
    autoAction: 'optOut',
    disabledCmps: [],
    enablePrehide: true,
    enableCosmeticRules: true,
    detectRetries: 20,
    enableFilterList: true,
    logs: { lifecycle: false, errors: false, evals: false, rules: false }
  };
}

async function updateCookiePopup(tabId, status, details) {
  const state = await ensureTabState(tabId, null);
  if (!state || state.status !== 'ok') return;
  if (status !== 'found') {
    clearTimeout(cookiePopupTimers.get(tabId));
    cookiePopupTimers.delete(tabId);
  }
  PB.Report.setCookiePopup(state, status, details || {});
  scheduleSave(tabId, state);
  if (status === 'found') {
    clearTimeout(cookiePopupTimers.get(tabId));
    cookiePopupTimers.set(tabId, setTimeout(async () => {
      cookiePopupTimers.delete(tabId);
      const latest = await getState(tabId);
      if (latest && latest.cookiePopup && latest.cookiePopup.status === 'found') {
        PB.Report.setCookiePopup(latest, 'hidden', { cmp: latest.cookiePopup.cmp || 'Cookie pop-up', detail: 'Timed out after detection' });
        scheduleSave(tabId, latest);
      }
    }, 15000));
  }
}

async function evalForAutoconsent(sender, msg) {
  const tabId = sender.tab && sender.tab.id;
  if (tabId == null || tabId < 0) return false;
  const snippets = await ensureAutoconsentEvalSnippets();
  const snippetId = String(msg.snippetId || '');
  const code = String(msg.code || '');
  if (!snippetId || snippets[snippetId] !== code) return false;
  const results = await chrome.scripting.executeScript({
    target: { tabId, frameIds: [sender.frameId || 0] },
    world: 'MAIN',
    func: (body) => {
      try { return (new Function(`return ${body}`))(); } catch (_) { return false; }
    },
    args: [code]
  });
  return results && results[0] ? results[0].result : false;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    await ensureData();
    if (message && message.type === 'getCookiePopupEnabled' && sender.tab && sender.tab.id >= 0) {
      const state = await ensureTabState(sender.tab.id, sender.url || null);
      const settings = await getSettings();
      const paused = Boolean(state && state.siteDomain && settings.pausedSites[state.siteDomain]);
      sendResponse({ ok: true, enabled: settings.cookiePopupEnabled && !paused });
      return;
    }
    if (message && message.type === 'cookiePopupFallbackHidden' && sender.tab && sender.tab.id >= 0) {
      await updateCookiePopup(sender.tab.id, 'hidden', { cmp: 'Fallback' });
      sendResponse({ ok: true });
      return;
    }
    if (message && message.type === 'init' && sender.tab && sender.tab.id >= 0) {
      const state = await ensureTabState(sender.tab.id, sender.url || null);
      const settings = await getSettings();
      const paused = Boolean(state && state.siteDomain && settings.pausedSites[state.siteDomain]);
      const enabled = settings.cookiePopupEnabled && !paused;
      const rules = enabled ? await ensureAutoconsentRules() : { v: 1, s: [], c: [] };
      chrome.tabs.sendMessage(sender.tab.id, { type: 'initResp', rules: { autoconsent: [], compact: rules }, config: autoconsentConfig(enabled) }, { frameId: sender.frameId || 0 });
      sendResponse({ ok: true });
      return;
    }
    if (message && message.type === 'eval' && sender.tab && sender.tab.id >= 0) {
      const result = await evalForAutoconsent(sender, message);
      chrome.tabs.sendMessage(sender.tab.id, { type: 'evalResp', id: message.id, result }, { frameId: sender.frameId || 0 });
      sendResponse({ ok: true });
      return;
    }
    if (message && message.type === 'popupFound' && sender.tab && sender.tab.id >= 0) {
      await updateCookiePopup(sender.tab.id, 'hidden', { cmp: message.cmp });
      sendResponse({ ok: true });
      return;
    }
    if (message && message.type === 'optOutResult' && sender.tab && sender.tab.id >= 0) {
      await updateCookiePopup(sender.tab.id, message.result ? 'answered' : 'error', { cmp: message.cmp, selfTest: '' });
      sendResponse({ ok: true });
      return;
    }
    if (message && message.type === 'optInResult' && sender.tab && sender.tab.id >= 0) {
      await updateCookiePopup(sender.tab.id, 'error', { cmp: message.cmp, detail: 'Unexpected accept result' });
      sendResponse({ ok: true });
      return;
    }
    if (message && message.type === 'selfTestResult' && sender.tab && sender.tab.id >= 0) {
      await updateCookiePopup(sender.tab.id, message.result ? 'rejected' : 'answered', { cmp: message.cmp, selfTest: message.result ? 'passed' : 'failed' });
      sendResponse({ ok: true });
      return;
    }
    if (message && message.type === 'autoconsentDone' && sender.tab && sender.tab.id >= 0) {
      await updateCookiePopup(sender.tab.id, message.isCosmetic ? 'hidden' : 'rejected', { cmp: message.cmp, duration: message.duration, selfTest: '' });
      sendResponse({ ok: true });
      return;
    }
    if (message && message.type === 'autoconsentError' && sender.tab && sender.tab.id >= 0) {
      await updateCookiePopup(sender.tab.id, 'error', { detail: message.details });
      sendResponse({ ok: true });
      return;
    }
    if (message && message.type === 'getAdCss' && sender.tab && sender.tab.id >= 0) {
      const state = await ensureTabState(sender.tab.id, sender.url || null);
      const settings = await getSettings();
      const paused = Boolean(state && state.siteDomain && settings.pausedSites[state.siteDomain]);
      if (!settings.blockingEnabled || !settings.adBlockingEnabled || paused) { sendResponse({ ok: true, css: '' }); return; }
      const data = await ensureCosmeticData();
      const host = String(message.host || '').toLowerCase();
      const selectors = new Set(data.generic || []);
      selectors.add('#ADbox');
      const parts = host.split('.');
      for (let i = 0; i < parts.length; i += 1) {
        const domain = parts.slice(i).join('.');
        for (const selector of (data.sites && data.sites[domain]) || []) selectors.add(selector);
      }
      const chunks = [];
      let current = [];
      for (const selector of selectors) {
        current.push(selector);
        if (current.length >= 80) { chunks.push(current.join(',') + '{display:none!important;}'); current = []; }
      }
      if (current.length) chunks.push(current.join(',') + '{display:none!important;}');
      sendResponse({ ok: true, genericUrl: chrome.runtime.getURL('data/easylist_generic.css'), css: chunks.join('\n') });
      return;
    }
    if (message && message.type === 'adCosmeticApplied' && sender.tab && sender.tab.id >= 0) {
      const state = await ensureTabState(sender.tab.id, sender.url || null);
      if (state) { PB.Report.addCosmeticTime(state, message.durationMs); scheduleSave(sender.tab.id, state); }
      sendResponse({ ok: true });
      return;
    }
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
    if (message && message.type === 'setAdBlocking') {
      sendResponse({ ok: true, settings: await setAdBlocking(message.enabled) });
      return;
    }
    if (message && message.type === 'setCookiePopupHandling') {
      sendResponse({ ok: true, settings: await setCookiePopupHandling(message.enabled) });
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
  clearTimeout(cookiePopupTimers.get(tabId));
  cookiePopupTimers.delete(tabId);
  chrome.storage.session.remove(key(tabId));
  chrome.declarativeNetRequest.getSessionRules().then((rules) => {
    const base = sameCompanyRuleBase(tabId);
    const removeRuleIds = rules.filter((rule) => rule.id > base && rule.id < base + SAME_COMPANY_RULES_PER_TAB).map((rule) => rule.id);
    if (removeRuleIds.length) chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds });
  });
});

ensureData().then(applySettings).catch(console.error);
