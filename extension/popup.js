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
  }

  function setToggle(button, on) {
    button.textContent = on ? 'On' : 'Off';
    button.setAttribute('aria-pressed', on ? 'true' : 'false');
  }

  function showReloadHint() {
    $('reloadHint').hidden = false;
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
    if (report.blockedTrackerCount) {
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
    const label = report.blockedTrackerCount ? `Blocked ${report.blockedTrackerCount} tracker ${plural(report.blockedTrackerCount, 'request')}` : (report.label || 'No report yet');
    text($('overall'), label);
    $('overall').classList.remove('low', 'some', 'high');
    if (report.blockedTrackerCount) $('overall').classList.add('high');
    else if (label === 'Little tracking found') $('overall').classList.add('low');
    else if (label === 'Some tracking') $('overall').classList.add('some');
    else if (label === 'A lot of tracking') $('overall').classList.add('high');
    if (report.status === 'unsupported') {
      showMessage('PrivacyBrew cannot check this page.', 'Open a website to check it.');
    } else if (report.status === 'needReload') {
      showMessage('Reload the page to check it.', 'PrivacyBrew did not see this page load.');
    }
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
