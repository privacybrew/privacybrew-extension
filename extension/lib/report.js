(function (global) {
  'use strict';
  const CATEGORY_LINES = {
    Advertising: 'Ad companies use your visits to show you ads on other websites.',
    Analytics: 'These companies measure how you use the website.',
    Social: 'Social networks can connect this visit to your account.',
    Content: 'Content companies help show page parts from other websites.',
    Fingerprinting: 'Fingerprint companies can help identify your browser without cookies.',
    Cryptomining: 'Mining scripts can use your device to make digital coins.',
    Other: 'This company is on a tracker list, but the type is not clear.'
  };
  const CATEGORY_PRIORITY = ['Advertising', 'Social', 'Analytics', 'Cryptomining', 'Fingerprinting', 'Content', 'Other'];
  const CATEGORY_RANK = CATEGORY_PRIORITY.reduce((out, name, index) => { out[name] = index; return out; }, {});
  const FINGERPRINT_LABELS = {
    canvas: 'Canvas readout',
    webgl: 'WebGL graphics card readout',
    audio: 'Audio readout',
    fonts: 'Font probing'
  };
  const SAMPLE_LIMIT = 10;

  function cleanUrl(value) {
    try {
      const url = new URL(value);
      let path = url.pathname || '/';
      if (path.length > 80) path = path.slice(0, 80);
      return url.origin + path;
    } catch (_) {
      return String(value || '').split('?')[0].split('#')[0].slice(0, 120);
    }
  }

  function hashText(value) {
    let hash = 2166136261;
    const text = String(value || '');
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(36);
  }

  function addSample(list, value) {
    if (!Array.isArray(list)) list = [];
    if (list.length < SAMPLE_LIMIT && !list.includes(value)) list.push(value);
    return list;
  }

  function emptyState(tabId, url, siteDomain) {
    return {
      version: 1,
      tabId,
      url: url || '',
      siteDomain: siteDomain || '',
      status: siteDomain ? 'ok' : 'unsupported',
      trackers: {},
      unknownDomains: {},
      cookieDomains: {},
      fingerprints: {},
      outsideScripts: { urls: {}, blockedUrls: {} },
      updatedAt: Date.now()
    };
  }

  function addTracker(state, match, requestDomain, status, requestUrl) {
    if (!match || !match.companyId) return state;
    const key = match.companyId;
    if (!state.trackers[key]) {
      state.trackers[key] = { company: match.company, category: match.category || 'Other', categories: {}, domains: {}, blockedDomainCounts: {}, allowedDomainCounts: {}, requestHashes: {}, requestCategories: {}, requestSamples: [], blockedRequestHashes: {}, allowedRequestHashes: {}, blockedSamples: [], allowedSamples: [] };
    }
    const category = match.category || 'Other';
    state.trackers[key].categories = state.trackers[key].categories || {};
    state.trackers[key].categories[category] = true;
    if (CATEGORY_RANK[category] < CATEGORY_RANK[state.trackers[key].category || 'Other']) {
      state.trackers[key].category = category;
    }
    state.trackers[key].domains[requestDomain] = true;
    const tracker = state.trackers[key];
    tracker.blockedDomainCounts = tracker.blockedDomainCounts || {};
    tracker.allowedDomainCounts = tracker.allowedDomainCounts || {};
    tracker.requestHashes = tracker.requestHashes || {};
    tracker.requestCategories = tracker.requestCategories || {};
    tracker.requestSamples = tracker.requestSamples || [];
    tracker.blockedRequestHashes = tracker.blockedRequestHashes || {};
    tracker.allowedRequestHashes = tracker.allowedRequestHashes || {};
    tracker.blockedSamples = tracker.blockedSamples || [];
    tracker.allowedSamples = tracker.allowedSamples || [];
    const requestKey = cleanUrl(requestUrl || requestDomain);
    const requestHash = hashText(requestKey);
    tracker.requestHashes[requestHash] = true;
    tracker.requestCategories[requestHash] = category;
    tracker.requestSamples = addSample(tracker.requestSamples, requestKey);
    if (status === 'blocked') {
      tracker.blockedDomainCounts[requestDomain] = (tracker.blockedDomainCounts[requestDomain] || 0) + 1;
      tracker.blockedRequestHashes[requestHash] = true;
      tracker.blockedSamples = addSample(tracker.blockedSamples, requestKey);
    } else if (!tracker.blockedRequestHashes[requestHash]) {
      tracker.allowedDomainCounts[requestDomain] = (tracker.allowedDomainCounts[requestDomain] || 0) + 1;
      tracker.allowedRequestHashes[requestHash] = true;
      tracker.allowedSamples = addSample(tracker.allowedSamples, requestKey);
    }
    state.updatedAt = Date.now();
    return state;
  }


  function addOutsideScript(state, url, status) {
    if (!url) return state;
    const key = cleanUrl(url);
    const hash = hashText(key);
    state.outsideScripts = state.outsideScripts || { hashes: {}, blockedHashes: {}, samples: [], blockedSamples: [] };
    state.outsideScripts.hashes = state.outsideScripts.hashes || {};
    state.outsideScripts.blockedHashes = state.outsideScripts.blockedHashes || {};
    state.outsideScripts.samples = state.outsideScripts.samples || [];
    state.outsideScripts.blockedSamples = state.outsideScripts.blockedSamples || [];
    state.outsideScripts.hashes[hash] = true;
    state.outsideScripts.samples = addSample(state.outsideScripts.samples, key);
    if (status === 'blocked') {
      state.outsideScripts.blockedHashes[hash] = true;
      state.outsideScripts.blockedSamples = addSample(state.outsideScripts.blockedSamples, key);
    } else {
      delete state.outsideScripts.blockedHashes[hash];
    }
    state.updatedAt = Date.now();
    return state;
  }

  function addUnknown(state, domain) {
    if (domain) state.unknownDomains[domain] = true;
    state.updatedAt = Date.now();
    return state;
  }

  function addCookie(state, domain) {
    if (domain) state.cookieDomains[domain] = true;
    state.updatedAt = Date.now();
    return state;
  }

  function addFingerprint(state, technique, origin) {
    if (!FINGERPRINT_LABELS[technique]) return state;
    if (!state.fingerprints[technique]) state.fingerprints[technique] = {};
    state.fingerprints[technique][origin || 'Unknown script'] = true;
    state.updatedAt = Date.now();
    return state;
  }

  function bump(label) {
    if (label === 'Little tracking found') return 'Some tracking';
    if (label === 'Some tracking') return 'A lot of tracking';
    return label;
  }

  function overallLabel(companyCount, hasFingerprinting) {
    let label = 'Little tracking found';
    if (companyCount >= 3 && companyCount <= 5) label = 'Some tracking';
    if (companyCount >= 6) label = 'A lot of tracking';
    return hasFingerprinting ? bump(label) : label;
  }

  function orderedCategories(categories) {
    const names = Object.keys(categories || {});
    return names.sort((a, b) => (CATEGORY_RANK[a] ?? 99) - (CATEGORY_RANK[b] ?? 99) || a.localeCompare(b));
  }

  function plural(count, singular, pluralText) {
    return count === 1 ? singular : (pluralText || singular + 's');
  }

  function summarize(state) {
    const trackers = Object.entries(state.trackers || {}).map(([companyId, value]) => {
      const categories = orderedCategories(value.categories || { [value.category || 'Other']: true });
      return {
        companyId,
        company: value.company,
        category: categories[0] || 'Other',
        categories,
        domains: Object.keys(value.domains || {}).sort(),
        blockedDomains: Object.keys(value.blockedDomainCounts || value.blockedDomains || {}).sort(),
        allowedDomains: Object.keys(value.allowedDomainCounts || value.allowedDomains || {}).sort(),
        requestHashes: Object.keys(value.requestHashes || value.requestUrls || value.domains || {}).sort(),
        requestSamples: (Array.isArray(value.requestSamples) ? value.requestSamples : Object.keys(value.requestUrls || {})).slice(0, SAMPLE_LIMIT).sort(),
        requestCategories: Object.assign({}, value.requestCategories || {}),
        blockedRequestHashes: Object.keys(value.blockedRequestHashes || value.blockedRequestUrls || {}).sort(),
        allowedRequestHashes: Object.keys(value.allowedRequestHashes || value.allowedRequestUrls || {}).sort(),
        blockedSamples: (Array.isArray(value.blockedSamples) ? value.blockedSamples : Object.keys(value.blockedRequestUrls || {})).slice(0, SAMPLE_LIMIT).sort(),
        allowedSamples: (Array.isArray(value.allowedSamples) ? value.allowedSamples : Object.keys(value.allowedRequestUrls || {})).slice(0, SAMPLE_LIMIT).sort(),
        status: Object.keys(value.blockedRequestHashes || value.blockedRequestUrls || {}).length ? 'Blocked' : 'Allowed'
      };
    }).sort((a, b) => (CATEGORY_RANK[a.category] ?? 99) - (CATEGORY_RANK[b.category] ?? 99) || a.company.localeCompare(b.company));
    const trackerRequestCount = trackers.reduce((sum, tracker) => sum + tracker.requestHashes.length, 0);
    const blockedTrackerCount = trackers.reduce((sum, tracker) => sum + tracker.blockedRequestHashes.length, 0);
    const allowedTrackerCount = Math.max(0, trackerRequestCount - blockedTrackerCount);
    const blockedCompanyCount = trackers.filter((tracker) => tracker.blockedRequestHashes.length > 0).length;
    const adTrackerCount = trackers.reduce((sum, tracker) => sum + tracker.requestHashes.filter((hash) => tracker.requestCategories[hash] === 'Advertising').length, 0);
    const adBlockedCount = trackers.reduce((sum, tracker) => sum + tracker.blockedRequestHashes.filter((hash) => tracker.requestCategories[hash] === 'Advertising').length, 0);
    const adAllowedCount = Math.max(0, adTrackerCount - adBlockedCount);
    const outsideScripts = state.outsideScripts || {};
    const outsideScriptUrls = Object.keys(outsideScripts.hashes || outsideScripts.urls || {}).sort();
    const outsideScriptBlockedUrls = Object.keys(outsideScripts.blockedHashes || outsideScripts.blockedUrls || {}).sort();
    const fingerprints = Object.entries(state.fingerprints || {}).map(([technique, origins]) => ({
      technique,
      label: FINGERPRINT_LABELS[technique] || technique,
      origins: Object.keys(origins || {}).sort()
    })).sort((a, b) => a.label.localeCompare(b.label));
    return {
      status: state.status || 'ok',
      url: state.url || '',
      siteDomain: state.siteDomain || '',
      label: overallLabel(trackers.length, fingerprints.length > 0),
      trackerCount: trackers.length,
      trackerRequestCount,
      blockedTrackerCount,
      allowedTrackerCount,
      blockedCompanyCount,
      adTrackerCount,
      adBlockedCount,
      adAllowedCount,
      outsideScriptCount: outsideScriptUrls.length,
      outsideScriptBlockedCount: outsideScriptBlockedUrls.length,
      trackers,
      unknownDomains: Object.keys(state.unknownDomains || {}).sort(),
      cookieDomains: Object.keys(state.cookieDomains || {}).sort(),
      fingerprints,
      categoryLines: CATEGORY_LINES,
      updatedAt: state.updatedAt || 0
    };
  }

  global.PB = global.PB || {};
  global.PB.Report = { CATEGORY_LINES, CATEGORY_PRIORITY, FINGERPRINT_LABELS, cleanUrl, emptyState, addTracker, addOutsideScript, addUnknown, addCookie, addFingerprint, overallLabel, orderedCategories, plural, summarize };
})(typeof globalThis !== 'undefined' ? globalThis : self);
