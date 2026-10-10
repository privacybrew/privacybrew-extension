(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);

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
  }

  function renderTrackers(report) {
    const wrap = $('trackers');
    wrap.textContent = '';
    text($('trackerSummary'), report.trackerCount ? `${report.trackerCount} known tracker ${plural(report.trackerCount, 'company', 'companies')} found.` : 'No known tracker companies found.');
    for (const tracker of report.trackers || []) {
      const box = make('article', undefined, 'company');
      const head = make('div', undefined, 'company-head');
      head.appendChild(make('span', tracker.company, 'company-name'));
      const chips = make('span', undefined, 'chips');
      for (const category of tracker.categories || [tracker.category]) chips.appendChild(make('span', category, 'chip'));
      head.appendChild(chips);
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
    const label = report.label || 'No report yet';
    text($('overall'), label);
    $('overall').classList.remove('low', 'some', 'high');
    if (label === 'Little tracking found') $('overall').classList.add('low');
    if (label === 'Some tracking') $('overall').classList.add('some');
    if (label === 'A lot of tracking') $('overall').classList.add('high');
    if (report.status === 'unsupported') {
      showMessage('PrivacyBrew cannot check this page.', 'Open a website to check it.');
    } else if (report.status === 'needReload') {
      showMessage('Reload the page to check it.', 'PrivacyBrew did not see this page load.');
    }
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
