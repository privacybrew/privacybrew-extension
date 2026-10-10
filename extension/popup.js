(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);

  function text(el, value) { el.textContent = value; }
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
  }

  function renderTrackers(report) {
    const wrap = $('trackers');
    wrap.textContent = '';
    text($('trackerSummary'), report.trackerCount ? `${report.trackerCount} known tracker companies found.` : 'No known tracker companies found.');
    for (const tracker of report.trackers || []) {
      const box = make('article', undefined, 'company');
      const head = make('div', undefined, 'company-head');
      head.appendChild(make('span', tracker.company, 'company-name'));
      head.appendChild(make('span', tracker.category, 'chip'));
      box.appendChild(head);
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
    text($('siteName'), report.siteDomain || 'This page');
    text($('overall'), report.label || 'No report yet');
    if (report.status === 'unsupported') {
      showMessage('PrivacyBrew cannot check this page.', 'Open a website to check it.');
    } else if (report.status === 'needReload') {
      showMessage('Reload the page to check it.', 'PrivacyBrew did not see this page load.');
    }
    renderTrackers(report);
    text($('unknownCount'), String((report.unknownDomains || []).length));
    list(report.unknownDomains || [], $('unknownList'));
    $('unknownDetails').hidden = !(report.unknownDomains || []).length;
    text($('cookieCount'), String((report.cookieDomains || []).length));
    list(report.cookieDomains || [], $('cookieList'));
    const fps = report.fingerprints || [];
    text($('fingerprintSummary'), fps.length ? `${fps.length} fingerprinting signals found.` : 'No fingerprinting signals found.');
    const fpList = $('fingerprintList');
    fpList.textContent = '';
    for (const fp of fps) {
      const li = make('li');
      li.appendChild(make('strong', fp.label));
      li.appendChild(document.createTextNode(': ' + fp.origins.join(', ')));
      fpList.appendChild(li);
    }
  }

  async function main() {
    try {
      const tabId = await activeTabId();
      if (!tabId) throw new Error('No active tab');
      const response = await chrome.runtime.sendMessage({ type: 'getReport', tabId });
      render(response && response.report ? response.report : { status: 'needReload' });
    } catch (_) {
      showMessage('PrivacyBrew cannot check this page.', 'Open a website and reload it to check it.');
      text($('overall'), 'No report yet');
    }
  }
  main();
})();
