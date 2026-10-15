(function () {
  'use strict';

  const DEBUG_POPUP_TAB_OVERRIDE = true;
  const $ = (id) => document.getElementById(id);

  let currentTabId = null;
  let currentReport = null;
  let currentView = 'home';
  let hasHostAccess = true;
  const ALL_SITES = { origins: ['*://*/*'] };

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

  function setSubmenuOpen(open) {
    $('forAWhileSubmenu').hidden = !open;
    $('forAWhileButton').setAttribute('aria-expanded', open ? 'true' : 'false');
    text($('forAWhileButton'), open ? 'Turn off for a while ▾' : 'Turn off for a while ▸');
  }

  function togglePowerMenu() {
    const menu = $('powerMenu');
    menu.hidden = !menu.hidden;
    $('powerButton').setAttribute('aria-expanded', menu.hidden ? 'false' : 'true');
    if (!menu.hidden && $('forAWhileButton').classList.contains('selected')) setSubmenuOpen(true);
  }

  function markSelected(button, selected) {
    button.classList.toggle('selected', selected);
    button.setAttribute('aria-pressed', selected ? 'true' : 'false');
  }

  function renderPowerMenu(report) {
    const settings = report.settings || {};
    const tempOn = Boolean(settings.tempOffUntil && Date.now() < settings.tempOffUntil);
    markSelected($('sitePowerButton'), Boolean(report.sitePaused));
    markSelected($('globalOffButton'), Boolean(settings.globalOff));
    for (const button of document.querySelectorAll('[data-temp]')) {
      const value = button.dataset.temp;
      markSelected(button, value === 'restart' ? Boolean(settings.restartOff) : tempOn && Number(value) === settings.tempOffMinutes);
    }
    $('forAWhileButton').classList.toggle('selected', tempOn || Boolean(settings.restartOff));
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

    // Without host access PrivacyBrew cannot see or block anything, so this notice replaces the other banners.
    const needsAccess = !hasHostAccess;
    $('accessBanner').hidden = !needsAccess;
    $('statusBar').hidden = !status || needsAccess;
    text($('statusText'), status);

    const showWall = !status && !needsAccess && (report.adWall === 'detected' || report.adWall === 'hidden');
    if (showWall && report.adWall === 'detected') {
      $('wallBanner').hidden = false;
      text($('wallText'), 'This website asks you to turn off ad blocking.');
    } else if (showWall && report.adWall === 'hidden') {
      $('wallBanner').hidden = false;
      text($('wallText'), 'PrivacyBrew hid an ad blocker message.');
    } else {
      $('wallBanner').hidden = true;
    }
    document.querySelector('.app').classList.toggle('compact-home', Boolean(status || showWall || needsAccess));

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
    renderPowerMenu(report);
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
    const firefox = navigator.userAgent.match(/Firefox\/(\d+)/);
    if (firefox) return `Firefox ${firefox[1]}`;
    const match = navigator.userAgent.match(/Chrome\/(\d+)/);
    return match ? `Chrome ${match[1]}` : 'Browser';
  }

  function renderFeedback() {
    // Feedback never includes the page address. The user can type it in the form if they want.
  }

  // Firefox users can take away access to websites after install. Chrome users can limit it too.
  async function checkHostAccess() {
    try {
      return await chrome.permissions.contains(ALL_SITES);
    } catch (error) {
      return true;
    }
  }

  async function refresh() {
    hasHostAccess = await checkHostAccess();
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
      setSubmenuOpen($('forAWhileSubmenu').hidden);
    });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closePowerMenu(); });

    // Show the choice at once; refresh() then confirms it from the saved settings.
    function showChoice(button) {
      for (const other of document.querySelectorAll('#powerMenu [data-temp], #globalOffButton')) markSelected(other, other === button);
      $('forAWhileButton').classList.toggle('selected', Boolean(button.dataset.temp));
    }
    $('sitePowerButton').addEventListener('click', async () => {
      markSelected($('sitePowerButton'), !currentReport.sitePaused);
      await chrome.runtime.sendMessage({ type: 'setSitePaused', tabId: currentTabId, paused: !currentReport.sitePaused });
      await chrome.runtime.sendMessage({ type: 'reloadTab', tabId: currentTabId });
      await refresh();
    });
    for (const button of document.querySelectorAll('[data-temp]')) {
      button.addEventListener('click', async () => {
        showChoice(button);
        if (button.dataset.temp === 'restart') await chrome.runtime.sendMessage({ type: 'setOffUntilRestart', enabled: true });
        else await chrome.runtime.sendMessage({ type: 'setTemporaryOff', minutes: Number(button.dataset.temp) });
        await refresh();
      });
    }
    $('globalOffButton').addEventListener('click', async () => { showChoice($('globalOffButton')); await chrome.runtime.sendMessage({ type: 'setGlobalOff', enabled: true }); await refresh(); });
    $('statusTurnOn').addEventListener('click', async () => {
      await chrome.runtime.sendMessage({ type: 'setGlobalOff', enabled: false });
      await chrome.runtime.sendMessage({ type: 'setTemporaryOff', minutes: 0 });
      await chrome.runtime.sendMessage({ type: 'setOffUntilRestart', enabled: false });
      if (currentReport.sitePaused) await chrome.runtime.sendMessage({ type: 'setSitePaused', tabId: currentTabId, paused: false });
      await refresh();
    });
    $('accessAllow').addEventListener('click', async () => {
      // Call request first, while the click still counts as a user action.
      const granted = await chrome.permissions.request(ALL_SITES).catch(() => false);
      if (granted) await refresh();
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
