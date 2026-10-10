(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  let currentTabId = null;
  let currentReport = null;

  function text(el, value) { el.textContent = value; }
  function plural(count, singular, pluralText) {
    if (globalThis.PB && PB.Report && PB.Report.plural) return PB.Report.plural(count, singular, pluralText);
    return count === 1 ? singular : (pluralText || singular + 's');
  }
  function make(tag, value, className) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (value !== undefined) el.textContent = value;
    return el;
  }
  function list(items, parent) {
    parent.textContent = '';
    for (const item of items) parent.appendChild(make('li', item));
  }

  async function activeTabId() {
    const params = new URLSearchParams(location.search);
    const debug = Number(params.get('tabId'));
    if (debug > 0) return debug;
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs && tabs[0] ? tabs[0].id : null;
  }

  function showMessage(title, body) {
    $('messageCard').hidden = false;
    text($('messageTitle'), title);
    text($('messageText'), body);
    $('trackersCard').hidden = true;
    $('controlsCard').hidden = true;
    $('summaryCard').hidden = true;
  }

  function setToggle(button, on) {
    button.textContent = on ? 'On' : 'Off';
    button.setAttribute('aria-pressed', on ? 'true' : 'false');
  }

  function showReloadHint() {
    $('reloadHint').hidden = false;
  }


  function setNumberClass(el, mode) {
    el.classList.remove('good', 'warn');
    if (mode) el.classList.add(mode);
  }

  function scrollToCard(id) {
    const el = $(id);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    const details = el.querySelector('details');
    if (details) details.open = true;
    el.focus({ preventScroll: true });
  }

  function renderSummary(report) {
    const blockingOff = report.sitePaused || (report.settings && !report.settings.blockingEnabled);
    const trackerRequests = report.trackerRequestCount || 0;
    const blocked = blockingOff ? 0 : (report.blockedTrackerCount || 0);
    const allowed = blockingOff ? trackerRequests : (report.allowedTrackerCount || 0);
    text($('statTrackers'), String(trackerRequests));
    text($('statTrackersSub'), (report.trackerCount || 0) ? `from ${report.trackerCount} ${plural(report.trackerCount, 'company', 'companies')}` : 'No companies');
    text($('statBlocked'), String(blocked));
    text($('statBlockedSub'), blockingOff ? 'Blocking is off' : 'tracker requests');
    setNumberClass($('statBlocked'), blocked > 0 ? 'good' : '');
    text($('statAllowed'), String(allowed));
    text($('statAllowedSub'), 'tracker requests');
    setNumberClass($('statAllowed'), allowed > 0 && !blockingOff ? 'warn' : '');
    text($('statAds'), String(report.adTrackerCount || 0));
    text($('statAdsSub'), `${blockingOff ? 0 : (report.adBlockedCount || 0)} blocked · ${blockingOff ? (report.adTrackerCount || 0) : (report.adAllowedCount || 0)} allowed`);
    setNumberClass($('statAds'), (report.adAllowedCount || 0) > 0 && !blockingOff ? 'warn' : '');
    text($('statScripts'), String(report.outsideScriptCount || 0));
    text($('statScriptsSub'), `${blockingOff ? 0 : (report.outsideScriptBlockedCount || 0)} blocked`);
    const fpCount = (report.fingerprints || []).length;
    text($('statFingerprint'), fpCount ? `${fpCount} ${plural(fpCount, 'method')}` : 'None found');
    setNumberClass($('statFingerprint'), fpCount ? 'warn' : 'good');
    text($('statFingerprintSub'), 'on this page');
    const cookieCount = (report.cookieDomains || []).length;
    text($('statCookies'), String(cookieCount));
    setNumberClass($('statCookies'), cookieCount ? 'warn' : '');
    text($('statCookiesSub'), plural(cookieCount, 'website'));
  }

  function renderControls(report) {
    const settings = report.settings || { blockingEnabled: true, gpcEnabled: true, pausedSites: {} };
    const siteOn = settings.blockingEnabled && !report.sitePaused;
    setToggle($('siteBlockToggle'), siteOn);
    setToggle($('globalBlockToggle'), settings.blockingEnabled);
    setToggle($('gpcToggle'), settings.gpcEnabled);
    $('controlsCard').hidden = report.status !== 'ok';
  }

  function renderTrackers(report) {
    const wrap = $('trackers');
    wrap.textContent = '';
    const blockingOff = report.sitePaused || (report.settings && !report.settings.blockingEnabled);
    if (blockingOff) {
      text($('trackerSummary'), 'PrivacyBrew did not block trackers on this website.');
    } else if (report.blockedTrackerCount) {
      text($('trackerSummary'), `PrivacyBrew blocked ${report.blockedTrackerCount} tracker ${plural(report.blockedTrackerCount, 'request')} from ${report.blockedCompanyCount} ${plural(report.blockedCompanyCount, 'company', 'companies')}.`);
    } else {
      text($('trackerSummary'), report.trackerCount ? `${report.trackerCount} known tracker ${plural(report.trackerCount, 'company', 'companies')} found.` : 'No known tracker companies found.');
    }
    for (const tracker of report.trackers || []) {
      const box = make('article', undefined, 'company');
      const head = make('div', undefined, 'company-head');
      head.appendChild(make('span', tracker.company, 'company-name'));
      const chips = make('span', undefined, 'chips');
      for (const category of tracker.categories || [tracker.category]) chips.appendChild(make('span', category, 'chip'));
      head.appendChild(chips);
      box.appendChild(head);
      const status = make('p', tracker.status, 'company-status ' + tracker.status.toLowerCase());
      box.appendChild(status);
      box.appendChild(make('p', report.categoryLines[tracker.category] || report.categoryLines.Other, 'muted'));
      const details = make('details');
      const summary = make('summary', 'Show details');
      summary.setAttribute('aria-expanded', 'false');
      details.addEventListener('toggle', () => summary.setAttribute('aria-expanded', details.open ? 'true' : 'false'));
      details.appendChild(summary);
      const ul = make('ul');
      list(tracker.domains, ul);
      details.appendChild(ul);
      box.appendChild(details);
      wrap.appendChild(box);
    }
  }

  function render(report) {
    currentReport = report;
    text($('siteName'), report.siteDomain || 'This page');
    let label = report.label || 'No report yet';
    if (report.sitePaused) label = 'Blocking is off for this website';
    else if (report.settings && !report.settings.blockingEnabled) label = 'Blocking is off';
    text($('overall'), label);
    $('overall').classList.remove('low', 'some', 'high');
    if (label === 'Little tracking found') $('overall').classList.add('low');
    else if (label === 'A lot of tracking') $('overall').classList.add('high');
    else $('overall').classList.add('some');
    if (report.status === 'unsupported') {
      showMessage('PrivacyBrew cannot check this page.', 'Open a website to check it.');
    } else if (report.status === 'needReload') {
      showMessage('Reload the page to check it.', 'PrivacyBrew did not see this page load.');
    }
    renderSummary(report);
    renderControls(report);
    renderTrackers(report);
    const unknownCount = (report.unknownDomains || []).length;
    text($('unknownSummary'), unknownCount ? `${unknownCount} ${plural(unknownCount, 'other website was', 'other websites were')} contacted. ${unknownCount === 1 ? 'It is' : 'They are'} not on our tracker list.` : 'No other websites contacted.');
    list(report.unknownDomains || [], $('unknownList'));
    $('unknownDetails').hidden = !(report.unknownDomains || []).length;
    const cookieCount = (report.cookieDomains || []).length;
    text($('cookieSummary'), cookieCount ? `${cookieCount} third-party ${plural(cookieCount, 'website tried', 'websites tried')} to set a cookie.` : 'No third-party websites tried to set a cookie.');
    list(report.cookieDomains || [], $('cookieList'));
    const fps = report.fingerprints || [];
    text($('fingerprintSummary'), fps.length ? `This page used ${fps.length} fingerprint ${plural(fps.length, 'method')}.` : 'No fingerprint methods found.');
    const fpList = $('fingerprintList');
    fpList.textContent = '';
    for (const fp of fps) {
      const li = make('li');
      li.appendChild(make('strong', fp.label));
      li.appendChild(document.createTextNode(': ' + fp.origins.join(', ')));
      fpList.appendChild(li);
    }
  }

  async function refresh() {
    const response = await chrome.runtime.sendMessage({ type: 'getReport', tabId: currentTabId });
    render(response && response.report ? response.report : { status: 'needReload' });
  }

  function bindControls() {
    $('siteBlockToggle').addEventListener('click', async () => {
      if (!currentReport || !currentReport.siteDomain) return;
      const makePaused = !currentReport.sitePaused;
      await chrome.runtime.sendMessage({ type: 'setSitePaused', tabId: currentTabId, paused: makePaused });
      showReloadHint();
      await refresh();
    });
    $('globalBlockToggle').addEventListener('click', async () => {
      const enabled = !(currentReport && currentReport.settings && currentReport.settings.blockingEnabled);
      await chrome.runtime.sendMessage({ type: 'setGlobalBlocking', enabled });
      showReloadHint();
      await refresh();
    });
    $('gpcToggle').addEventListener('click', async () => {
      const enabled = !(currentReport && currentReport.settings && currentReport.settings.gpcEnabled);
      await chrome.runtime.sendMessage({ type: 'setGpc', enabled });
      showReloadHint();
      await refresh();
    });
    for (const tile of document.querySelectorAll('.stat-tile[data-target]')) {
      tile.addEventListener('click', () => scrollToCard(tile.dataset.target));
    }
    $('reloadButton').addEventListener('click', async () => {
      await chrome.runtime.sendMessage({ type: 'reloadTab', tabId: currentTabId });
      window.close();
    });
  }

  async function main() {
    bindControls();
    try {
      currentTabId = await activeTabId();
      if (!currentTabId) throw new Error('No active tab');
      await refresh();
    } catch (_) {
      showMessage('PrivacyBrew cannot check this page.', 'Open a website and reload it to check it.');
      text($('overall'), 'No report yet');
    }
  }
  main();
})();
