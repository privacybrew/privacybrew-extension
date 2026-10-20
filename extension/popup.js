(function () {
  'use strict';

  const DEBUG_POPUP_TAB_OVERRIDE = true;
  const $ = (id) => document.getElementById(id);

  let currentTabId = null;
  let currentReport = null;
  let currentView = 'home';
  let hasHostAccess = true;
  const ALL_SITES = { origins: ['*://*/*'] };
  const reduceMotion = Boolean(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const COUNT_MS = 320;
  let countedUp = false;

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

  // The real number stays in the DOM. Only a hidden copy counts up, so tests and screen readers get the final value.
  function countUp(el, target) {
    const box = el.parentElement;
    const ghost = box && box.querySelector('.count-ghost');
    if (!ghost || reduceMotion || !(target >= 2)) return;
    const start = performance.now();
    box.classList.add('counting');
    const step = (now) => {
      const t = Math.min(1, (now - start) / COUNT_MS);
      ghost.textContent = String(Math.round(target * (1 - Math.pow(1 - t, 3))));
      if (t < 1 && el.textContent === String(target)) {
        requestAnimationFrame(step);
      } else {
        box.classList.remove('counting');
        ghost.textContent = '';
      }
    };
    ghost.textContent = '0';
    requestAnimationFrame(step);
  }

  function svgIcon(path) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    const shape = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    shape.setAttribute('d', path);
    svg.appendChild(shape);
    return svg;
  }

  const ICONS = {
    page: 'M5 2h9l5 5v15H5V2Zm8 1.5V8h4.5L13 3.5ZM7 11v2h10v-2H7Zm0 4v2h7v-2H7Z',
    request: 'M12 5c5 0 9 4.5 10 7-1 2.5-5 7-10 7S3 14.5 2 12c1-2.5 5-7 10-7Zm0 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0 2.2a1.8 1.8 0 1 1 0 3.6 1.8 1.8 0 0 1 0-3.6Z',
    blocked: 'M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3Zm-1.2 13.6-3.5-3.5 1.4-1.4 2.1 2.1 4.6-4.6 1.4 1.4-6 6Z',
    allowed: 'M4 11h12.2l-5.6-5.6L12 4l8 8-8 8-1.4-1.4 5.6-5.6H4v-2Z'
  };

  // A small picture: the page sends a request, and PrivacyBrew blocks it (or lets it go when off).
  function flowDiagram(requestLabel, blocked, summary) {
    const flow = make('div', undefined, 'flow');
    flow.setAttribute('role', 'img');
    flow.setAttribute('aria-label', summary);
    const node = (label, icon, className) => {
      const item = make('div', undefined, 'flow-node ' + className);
      const badge = make('span', undefined, 'flow-icon');
      badge.appendChild(svgIcon(ICONS[icon]));
      item.appendChild(badge);
      item.appendChild(make('span', label));
      return item;
    };
    flow.appendChild(node('This page', 'page', 'source'));
    flow.appendChild(make('span', undefined, 'flow-link'));
    flow.appendChild(node(requestLabel, 'request', 'request'));
    flow.appendChild(make('span', undefined, 'flow-link ' + (blocked ? 'stop' : 'pass')));
    flow.appendChild(node(blocked ? 'Blocked' : 'Allowed', blocked ? 'blocked' : 'allowed', 'result' + (blocked ? '' : ' open')));
    return flow;
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
    // Home slides in only when the user comes back to it.
    document.querySelector('.app').classList.toggle('returning', name === 'home' && currentView !== 'home');
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
    // The report started after the page loaded (for example, the tab was open before install).
    const needsReload = !needsAccess && !status && (report.status === 'needReload' || (report.partial && report.status === 'ok'));
    $('reloadBanner').hidden = !needsReload;
    if (report.status === 'needReload') {
      text($('overall'), 'No report yet');
      setOverallClass('');
    }
    $('statusBar').hidden = !status || needsAccess;
    text($('statusText'), status);

    const showWall = !status && !needsAccess && !needsReload && (report.adWall === 'detected' || report.adWall === 'hidden');
    if (showWall && report.adWall === 'detected') {
      $('wallBanner').hidden = false;
      text($('wallText'), 'This website asks you to turn off ad blocking.');
    } else if (showWall && report.adWall === 'hidden') {
      $('wallBanner').hidden = false;
      text($('wallText'), 'PrivacyBrew hid an ad blocker message.');
    } else {
      $('wallBanner').hidden = true;
    }
    document.querySelector('.app').classList.toggle('compact-home', Boolean(status || showWall || needsAccess || needsReload));

    const adCount = off ? 0 : (report.adBlockedRequestCount || 0);
    text($('homeTrackersNumber'), String(trackerCount));
    text($('homeTrackersSub'), `${blocked} blocked · ${allowed} allowed · from ${report.trackerCount || 0} ${plural(report.trackerCount || 0, 'company', 'companies')}`);
    text($('homeAdsNumber'), String(adCount));
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
    renderPowerMenu(report);
    if (!countedUp && currentView === 'home') {
      countedUp = true;
      countUp($('homeTrackersNumber'), trackerCount);
      countUp($('homeAdsNumber'), adCount);
      countUp($('homeScriptsNumber'), report.outsideScriptCount || 0);
      countUp($('homeFingerprintNumber'), fingerprintCount);
    }
  }

  function trackerDetail(report) {
    const wrap = make('div');
    const blocking = !protectionOff(report);
    wrap.appendChild(flowDiagram('Tracker request', blocking, blocking
      ? 'The page sends a tracker request. PrivacyBrew blocks it.'
      : 'The page sends a tracker request. PrivacyBrew is off, so it does not block the request.'));
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
      const blockingAds = !protectionOff(report) && Boolean(report.settings && report.settings.adBlockingEnabled);
      node = simpleDetail([
        flowDiagram('Ad request', blockingAds, blockingAds
          ? 'The page sends an ad request. PrivacyBrew blocks it.'
          : 'The page sends an ad request. PrivacyBrew does not block it now.'),
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

    // Only one way to turn off can be active. Tapping the active option turns PrivacyBrew on again.
    const offOptions = () => [$('sitePowerButton'), ...document.querySelectorAll('#powerMenu [data-temp]'), $('globalOffButton')];
    function showChoice(button) {
      for (const other of offOptions()) markSelected(other, other === button);
      $('forAWhileButton').classList.toggle('selected', Boolean(button && button.dataset.temp));
    }
    async function turnOnEverywhere() {
      const wasSitePaused = Boolean(currentReport.sitePaused);
      await chrome.runtime.sendMessage({ type: 'setGlobalOff', enabled: false });
      await chrome.runtime.sendMessage({ type: 'setTemporaryOff', minutes: 0 });
      await chrome.runtime.sendMessage({ type: 'setOffUntilRestart', enabled: false });
      if (wasSitePaused) {
        await chrome.runtime.sendMessage({ type: 'setSitePaused', tabId: currentTabId, paused: false });
        await chrome.runtime.sendMessage({ type: 'reloadTab', tabId: currentTabId });
      }
    }
    async function chooseOff(button, turnOff) {
      const active = button.classList.contains('selected');
      showChoice(active ? null : button);
      await turnOnEverywhere();
      if (!active) await turnOff();
      await refresh();
    }
    $('sitePowerButton').addEventListener('click', () => chooseOff($('sitePowerButton'), async () => {
      await chrome.runtime.sendMessage({ type: 'setSitePaused', tabId: currentTabId, paused: true });
      await chrome.runtime.sendMessage({ type: 'reloadTab', tabId: currentTabId });
    }));
    for (const button of document.querySelectorAll('[data-temp]')) {
      button.addEventListener('click', () => chooseOff(button, () => button.dataset.temp === 'restart'
        ? chrome.runtime.sendMessage({ type: 'setOffUntilRestart', enabled: true })
        : chrome.runtime.sendMessage({ type: 'setTemporaryOff', minutes: Number(button.dataset.temp) })));
    }
    $('globalOffButton').addEventListener('click', () => chooseOff($('globalOffButton'), () => chrome.runtime.sendMessage({ type: 'setGlobalOff', enabled: true })));
    $('statusTurnOn').addEventListener('click', async () => {
      showChoice(null);
      await turnOnEverywhere();
      await refresh();
    });
    $('reloadPage').addEventListener('click', async () => {
      await chrome.runtime.sendMessage({ type: 'reloadTab', tabId: currentTabId });
      window.close();
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

  // The rise-in plays only when the popup opens, not each time the home view comes back.
  setTimeout(() => document.querySelector('.app').classList.remove('intro'), reduceMotion ? 0 : 600);

  (async () => {
    bind();
    currentTabId = await activeTabId();
    await refresh();
  })().catch(() => {});
})();
