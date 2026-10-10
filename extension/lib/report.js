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
      updatedAt: Date.now()
    };
  }

  function addTracker(state, match, requestDomain) {
    if (!match || !match.companyId) return state;
    const key = match.companyId;
    if (!state.trackers[key]) {
      state.trackers[key] = { company: match.company, category: match.category || 'Other', categories: {}, domains: {} };
    }
    const category = match.category || 'Other';
    state.trackers[key].categories = state.trackers[key].categories || {};
    state.trackers[key].categories[category] = true;
    if (CATEGORY_RANK[category] < CATEGORY_RANK[state.trackers[key].category || 'Other']) {
      state.trackers[key].category = category;
    }
    state.trackers[key].domains[requestDomain] = true;
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
        domains: Object.keys(value.domains || {}).sort()
      };
    }).sort((a, b) => (CATEGORY_RANK[a.category] ?? 99) - (CATEGORY_RANK[b.category] ?? 99) || a.company.localeCompare(b.company));
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
      trackers,
      unknownDomains: Object.keys(state.unknownDomains || {}).sort(),
      cookieDomains: Object.keys(state.cookieDomains || {}).sort(),
      fingerprints,
      categoryLines: CATEGORY_LINES,
      updatedAt: state.updatedAt || 0
    };
  }

  global.PB = global.PB || {};
  global.PB.Report = { CATEGORY_LINES, CATEGORY_PRIORITY, FINGERPRINT_LABELS, emptyState, addTracker, addUnknown, addCookie, addFingerprint, overallLabel, orderedCategories, plural, summarize };
})(typeof globalThis !== 'undefined' ? globalThis : self);
