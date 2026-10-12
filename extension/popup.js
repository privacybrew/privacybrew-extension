(function () {
  'use strict';

  const DEBUG_POPUP_TAB_OVERRIDE = true;
  const $ = (id) => document.getElementById(id);

  let currentTabId = null;
  let currentReport = null;
  let currentView = 'home';

  function text(el, value) {
    el.textContent = value;
  }

  function plural(count, singular, pluralText) {
    return count === 1 ? singular : (pluralText || singular + 's');
  }

  function make(tag, value, className) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (value !== undefined) el.textContent = value;
    return el;
  }

  async function activeTabId() {
    const params = new URLSearchParams(location.search);
    const debug = DEBUG_POPUP_TAB_OVERRIDE ? Number(params.get('tabId')) : 0;
    if (debug > 0) return debug;
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs && tabs[0] ? tabs[0].id : null;
  }

  function setToggle(button, on) {
    button.textContent = on ? 'On' : 'Off';
    button.setAttribute('aria-pressed', on ? 'true' : 'false');
  }

  function showView(name) {
    for (const id of ['homeView', 'detailView', 'settingsView', 'feedbackView']) {
      $(id).hidden = true;
    }
    $(name + 'View').hidden = false;
    $('backButton').hidden = name === 'home';
    currentView = name;
    closePowerMenu();
  }

  function closePowerMenu() {
    $('powerMenu').hidden = true;
    $('powerButton').setAttribute('aria-expanded', 'false');
  }

  function togglePowerMenu() {
    const menu = $('powerMenu');
    menu.hidden = !menu.hidden;
    $('powerButton').setAttribute('aria-expanded', menu.hidden ? 'false' : 'true');
  }

  function protectionOff(report) {
    const settings = report.settings || {};
    return Boolean(report.sitePaused || settings.globalOff || settings.restartOff || (settings.tempOffUntil && Date.now() < settings.tempOffUntil) || !settings.blockingEnabled);
  }

  function statusText(report) {
    const settings = report.settings || {};
    if (report.sitePaused) return 'PrivacyBrew is off on this website';
    if (settings.restartOff) return 'PrivacyBrew is off until the browser restarts';
    if (settings.globalOff) return 'PrivacyBrew is off';
    if (settings.tempOffUntil && Date.now() < settings.tempOffUntil) {
      const minutes = Math.max(1, Math.round((settings.tempOffUntil - Date.now()) / 60000));
      return `PrivacyBrew is off for ${minutes} more ${plural(minutes, 'minute')}`;
    }
    return '';
  }

  function setOverallClass(label) {
    const el = $('overall');
    el.classList.remove('low', 'some', 'high');
    if (label === 'Little tracking found') el.classList.add('low');
    else if (label === 'A lot of tracking') el.classList.add('high');
    else el.classList.add('some');
  }

  function renderHome(report) {
    const settings = report.settings || {};
    const off = protectionOff(report);
    const status = statusText(report);
    const trackerCount = report.trackerRequestCount || 0;
    const blocked = off ? 0 : (report.blockedTrackerCount || 0);
    const allowed = off ? trackerCount : (report.allowedTrackerCount || 0);
    const cookiePopup = report.cookiePopup || { status: 'none', label: 'No pop-up found' };
    const fingerprintCount = (report.fingerprints || []).length;

    text($('siteName'), report.siteDomain || 'This page');
    text($('overall'), report.label || 'No report yet');
    setOverallClass(report.label || '');

    $('statusBar').hidden = !status;
    text($('statusText'), status);

    const showWall = !status && (report.adWall === 'detected' || report.adWall === 'hidden');
    if (showWall && report.adWall === 'detected') {
      $('wallBanner').hidden = false;
      text($('wallText'), 'This website asks you to turn off ad blocking.');
    } else if (showWall && report.adWall === 'hidden') {
      $('wallBanner').hidden = false;
      text($('wallText'), 'PrivacyBrew hid an ad blocker message.');
    } else {
      $('wallBanner').hidden = true;
    }
    document.querySelector('.app').classList.toggle('compact-home', Boolean(status || showWall));

    text($('homeTrackersNumber'), String(trackerCount));
    text($('homeTrackersSub'), `${blocked} blocked · ${allowed} allowed · from ${report.trackerCount || 0} ${plural(report.trackerCount || 0, 'company', 'companies')}`);
    text($('homeAdsNumber'), String(off ? 0 : (report.adBlockedRequestCount || 0)));
    text($('homeAdsSub'), `${report.adTrackerCount || 0} ad trackers`);
    text($('homeScriptsNumber'), String(report.outsideScriptCount || 0));
    text($('homeScriptsSub'), `${off ? 0 : (report.outsideScriptBlockedCount || 0)} blocked`);
    const cookieWords = { rejected: 'Rejected', hidden: 'Hidden', error: 'Could not handle', none: 'No pop-up' };
    text($('homeCookiesValue'), cookieWords[cookiePopup.status] || cookiePopup.label || 'No pop-up');
    text($('homeCookiesSub'), `${(report.cookieDomains || []).length} third-party cookie ${plural((report.cookieDomains || []).length, 'website')}`);
    text($('homeFingerprintNumber'), fingerprintCount ? String(fingerprintCount) : 'None');
    text($('homeFingerprintWord'), fingerprintCount ? plural(fingerprintCount, 'method') : '');
    text($('privacyRequestsRow'), `${settings.gpcEnabled ? 'GPC sent' : 'GPC off'} · ${settings.dntEnabled ? 'DNT sent' : 'DNT off'}`);
    $('powerButton').classList.toggle('off', off);
    text($('sitePowerButton'), report.sitePaused ? 'Turn on on this website' : 'Turn off on this website');
  }

  function trackerDetail(report) {
    const wrap = make('div');
    wrap.appendChild(make('p', report.blockedTrackerCount ? `PrivacyBrew blocked ${report.blockedTrackerCount} tracker ${plural(report.blockedTrackerCount, 'request')}.` : 'No known tracker companies found.', 'muted'));
    for (const tracker of report.trackers || []) {
      const card = make('section', undefined, 'detail-card');
      const head = make('div');
      head.appendChild(make('strong', tracker.company));
      for (const category of tracker.categories || []) head.appendChild(make('span', category, 'chip'));
      card.appendChild(head);
      card.appendChild(make('p', tracker.status, tracker.status === 'Blocked' ? 'blocked' : 'allowed'));
      card.appendChild(make('p', (report.categoryLines && report.categoryLines[tracker.category]) || '', 'muted'));
      const details = make('details');
      details.appendChild(make('summary', 'Show details'));
      const list = make('ul');
      for (const domain of tracker.domains || []) list.appendChild(make('li', domain));
      details.appendChild(list);
      card.appendChild(details);
      wrap.appendChild(card);
    }
    return wrap;
  }

  function simpleDetail(children) {
    const wrap = make('div');
    for (const child of children) wrap.appendChild(child);
    return wrap;
  }

  function renderDetail(kind) {
    const report = currentReport;
    let title = 'Details';
    let node;
    if (kind === 'trackers') {
      title = 'Trackers';
      node = trackerDetail(report);
    } else if (kind === 'ads') {
      title = 'Ads';
      node = simpleDetail([
        make('p', `${report.adBlockedRequestCount || 0} ad requests blocked.`),
        make('p', "It's not a sign. It's a targeted ad.", 'muted'),
        make('p', 'PrivacyBrew counts requests to ad companies. It does not count the ads that you see.', 'muted')
      ]);
    } else if (kind === 'scripts') {
      title = 'Outside scripts';
      node = simpleDetail([make('p', `${report.outsideScriptCount || 0} outside scripts. ${report.outsideScriptBlockedCount || 0} blocked.`)]);
    } else if (kind === 'cookies') {
      title = 'Cookies';
      const popup = report.cookiePopup || { label: 'No pop-up found' };
      node = simpleDetail([
        make('p', `Cookie pop-up: ${popup.label}.`),
        make('p', `${(report.cookieDomains || []).length} third-party cookie ${plural((report.cookieDomains || []).length, 'website')}.`, 'muted')
      ]);
    } else {
      title = 'Fingerprinting';
      if ((report.fingerprints || []).length) {
        const list = make('ul');
        for (const item of report.fingerprints) list.appendChild(make('li', `${item.label}: ${item.origins.join(', ')}`));
        node = simpleDetail([list]);
      } else {
        node = simpleDetail([make('p', 'No fingerprint methods found.')]);
      }
    }
    text($('detailTitle'), title);
    $('detailContent').textContent = '';
    $('detailContent').appendChild(node);
    showView('detail');
  }

  function renderSettings(report) {
    const settings = report.settings || {};
    setToggle($('globalBlockToggle'), settings.blockingEnabled);
    setToggle($('adBlockToggle'), settings.adBlockingEnabled && settings.blockingEnabled);
    setToggle($('cookiePopupToggle'), settings.cookiePopupEnabled && !report.sitePaused);
    setToggle($('gpcToggle'), settings.gpcEnabled);
    setToggle($('dntToggle'), settings.dntEnabled);
    const list = $('pausedList');
    list.textContent = '';
    for (const site of Object.keys(settings.pausedSites || {})) {
      const item = make('li', site + ' ');
      const button = make('button', 'Remove');
      button.addEventListener('click', async () => {
        await chrome.runtime.sendMessage({ type: 'setSitePaused', tabId: currentTabId, paused: false });
        await refresh();
      });
      item.appendChild(button);
      list.appendChild(item);
    }
    if (!list.children.length) list.appendChild(make('li', 'No websites are off.'));
  }

  function browserLabel() {
    const brands = navigator.userAgentData && navigator.userAgentData.brands;
    const brand = brands && brands.find((item) => /Chrome/i.test(item.brand));
    if (brand) return `${brand.brand.replace('Google ', '')} ${brand.version}`;
    const match = navigator.userAgent.match(/Chrome\/(\d+)/);
    return match ? `Chrome ${match[1]}` : 'Browser';
  }

  function renderFeedback() {
    // Feedback never includes the page address. The user can type it in the form if they want.
  }

  async function refresh() {
    const response = await chrome.runtime.sendMessage({ type: 'getReport', tabId: currentTabId });
    currentReport = response && response.report ? response.report : { status: 'needReload' };
    renderHome(currentReport);
    renderSettings(currentReport);
    if (currentView === 'feedback') renderFeedback();
  }

  function bind() {
    for (const button of document.querySelectorAll('[data-detail]')) button.addEventListener('click', () => renderDetail(button.dataset.detail));
    $('settingsButton').addEventListener('click', () => showView('settings'));
    $('feedbackButton').addEventListener('click', () => { renderFeedback(); showView('feedback'); });
    $('backButton').addEventListener('click', () => showView('home'));
    $('privacyRequestsRow').addEventListener('click', () => showView('settings'));
    $('powerButton').addEventListener('click', togglePowerMenu);
    $('forAWhileButton').addEventListener('click', () => {
      const submenu = $('forAWhileSubmenu');
      submenu.hidden = !submenu.hidden;
      $('forAWhileButton').setAttribute('aria-expanded', submenu.hidden ? 'false' : 'true');
      text($('forAWhileButton'), submenu.hidden ? 'Turn off for a while ▸' : 'Turn off for a while ▾');
    });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closePowerMenu(); });

    $('sitePowerButton').addEventListener('click', async () => {
      await chrome.runtime.sendMessage({ type: 'setSitePaused', tabId: currentTabId, paused: !currentReport.sitePaused });
      await chrome.runtime.sendMessage({ type: 'reloadTab', tabId: currentTabId });
    });
    for (const button of document.querySelectorAll('[data-temp]')) {
      button.addEventListener('click', async () => {
        if (button.dataset.temp === 'restart') await chrome.runtime.sendMessage({ type: 'setOffUntilRestart', enabled: true });
        else await chrome.runtime.sendMessage({ type: 'setTemporaryOff', minutes: Number(button.dataset.temp) });
        await refresh();
      });
    }
    $('globalOffButton').addEventListener('click', async () => { await chrome.runtime.sendMessage({ type: 'setGlobalOff', enabled: true }); await refresh(); });
    $('statusTurnOn').addEventListener('click', async () => {
      await chrome.runtime.sendMessage({ type: 'setGlobalOff', enabled: false });
      await chrome.runtime.sendMessage({ type: 'setTemporaryOff', minutes: 0 });
      await chrome.runtime.sendMessage({ type: 'setOffUntilRestart', enabled: false });
      if (currentReport.sitePaused) await chrome.runtime.sendMessage({ type: 'setSitePaused', tabId: currentTabId, paused: false });
      await refresh();
    });
    $('wallPause').addEventListener('click', async () => {
      await chrome.runtime.sendMessage({ type: 'setSitePaused', tabId: currentTabId, paused: true });
      await chrome.runtime.sendMessage({ type: 'reloadTab', tabId: currentTabId });
    });

    const toggles = [
      ['globalBlockToggle', 'setGlobalBlocking', 'blockingEnabled'],
      ['adBlockToggle', 'setAdBlocking', 'adBlockingEnabled'],
      ['cookiePopupToggle', 'setCookiePopupHandling', 'cookiePopupEnabled'],
      ['gpcToggle', 'setGpc', 'gpcEnabled'],
      ['dntToggle', 'setDnt', 'dntEnabled']
    ];
    for (const [id, message, key] of toggles) {
      $(id).addEventListener('click', async () => {
        await chrome.runtime.sendMessage({ type: message, enabled: !(currentReport.settings && currentReport.settings[key]) });
        await refresh();
      });
    }
    $('openFeedback').addEventListener('click', async () => {
      const params = new URLSearchParams();
      if ($('feedbackVersion').checked) {
        params.set('v', chrome.runtime.getManifest().version);
        params.set('browser', browserLabel());
      }
      await chrome.tabs.create({ url: 'https://privacybrew.app/feedback.html?' + params.toString() });
    });
  }

  (async () => {
    bind();
    currentTabId = await activeTabId();
    await refresh();
  })().catch(() => {});
})();
