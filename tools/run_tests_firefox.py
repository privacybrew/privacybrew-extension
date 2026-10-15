#!/usr/bin/env python3
"""Firefox end-to-end tests for the PACKAGED Firefox build.

Usage: python3 tools/run_tests_firefox.py [--headed] [--slow] [--no-build]

- Builds dist/privacybrew-extension-firefox-<version>.zip (tools/package.py --target firefox),
  unpacks it to artifacts/firefox-ext and installs it with WebDriver BiDi webExtension.install.
- Firefox runs headless with software rendering by default (see tools/firefox_bidi.py).
  --headed shows the browser window on the screen. --slow adds pauses so a person can watch.
- Uses the local fixture server from tools/run_tests.py (port 8796). A dead proxy blocks
  all other network traffic.
"""
import contextlib, importlib.util, json, shutil, subprocess, sys, time, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from firefox_bidi import Firefox, POPUP_ORIGIN, GECKO_ID, BiDiError  # noqa: E402

spec = importlib.util.spec_from_file_location('run_tests', str(ROOT / 'tools/run_tests.py'))
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

ART = ROOT / 'artifacts'
EXT_DIR = ART / 'firefox-ext'
HEADED = '--headed' in sys.argv
SLOW = '--slow' in sys.argv
PORT = rt.PORT
TIME_LIMIT = 900 if SLOW else 600
POPUP = POPUP_ORIGIN + '/popup.html'
DEAD_PROXY = 9  # discard port: nothing listens, so any non-fixture request fails

# Test-only code that runs inside the background page (through runtime.getBackgroundPage).
# It records console.error calls, uncaught errors and unhandled rejections.
HOOK = """if (!b.__pbHooked) { b.__pbHooked = true; b.__pbErrors = [];
const ce = b.console.error.bind(b.console);
b.console.error = (...a) => { b.__pbErrors.push(a.map((x) => x && x.stack ? String(x) + ' ' + x.stack : String(x)).join(' ')); ce(...a); };
b.addEventListener('error', (e) => b.__pbErrors.push('error: ' + e.message));
b.addEventListener('unhandledrejection', (e) => b.__pbErrors.push('rejection: ' + String(e.reason))); }"""

LAYOUT_JS = """(() => {
  const clipped = [...document.querySelectorAll('body *:not(script):not(style)')].filter((e) => {
    const r = e.getBoundingClientRect();
    return r.bottom > 581 && !e.closest('.detail-scroll') && !e.closest('#settingsView') && e.id !== 'homeView';
  }).map((e) => e.id || e.className || e.tagName);
  const f = document.querySelector('.home-footer');
  const footer = !f || f.offsetParent === null || [...f.querySelectorAll('a,button')].every((e) => e.getBoundingClientRect().bottom <= 580);
  const de = document.documentElement;
  const body = document.body.getBoundingClientRect();
  return { clipped, footer, width: Math.round(body.width), height: Math.round(body.height),
    // popup.css sets overflow: hidden on html and body, so the popup never shows a page scroll bar.
    pageScroll: [de, document.body].some((e) => getComputedStyle(e).overflow !== 'hidden') &&
      (document.body.scrollHeight > 581 || document.body.scrollWidth > 381) };
})()"""


def pause(seconds=0.0):
    time.sleep(seconds + (0.8 if SLOW else 0))


def build_and_unpack(skip_build):
    if not skip_build:
        subprocess.run([sys.executable, str(ROOT / 'tools/package.py'), '--target', 'firefox'], check=True, stdout=subprocess.DEVNULL)
    version = json.loads((ROOT / 'extension/manifest.json').read_text())['version']
    zip_path = ROOT / 'dist' / f'privacybrew-extension-firefox-{version}.zip'
    shutil.rmtree(EXT_DIR, ignore_errors=True)
    EXT_DIR.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(EXT_DIR)
    return zip_path


class Suite:
    def __init__(self, ff):
        self.ff = ff
        self.ctl = None
        self.checks = []
        self.bg_errors = []
        self.shots = []

    def check(self, name, ok, detail=None):
        self.checks.append((name, bool(ok)))
        print(('PASS ' if ok else 'FAIL ') + name + ('' if ok or detail is None else f'  [{detail}]'), flush=True)

    # Control page: an extension tab used to reach the background page.
    def control(self):
        if self.ctl is None or self.ctl not in self.ff.content_contexts():
            self.ctl = self.ff.open_extension_tab(POPUP, select=False)
        return self.ctl

    def bg(self, expr, timeout=60):
        code = f"(async () => {{ const b = await browser.runtime.getBackgroundPage(); {HOOK}; return JSON.stringify(await ({expr})); }})()"
        out = self.ff.eval(self.control(), code, timeout)
        return None if out is None else json.loads(out)

    def collect_bg_errors(self):
        with contextlib.suppress(Exception):
            errs = self.bg('(() => { const e = b.__pbErrors.slice(); b.__pbErrors.length = 0; return e; })()')
            self.bg_errors.extend(errs or [])

    def tab(self, url):
        ctx = self.ff.new_tab()
        self.go(ctx, url)
        return ctx

    def go(self, ctx, url):
        self.ff.navigate(ctx, url)
        pause(2.5)

    def page(self, ctx, expr):
        return self.ff.evalj(ctx, expr)

    def latest(self, url_prefix):
        """Tab id and stored state of the newest tab whose URL starts with url_prefix."""
        end = time.time() + 8
        last = {}
        while time.time() < end:
            obj = self.bg('b.chrome.storage.session.get(null)') or {}
            last = obj
            tabs = {k: v for k, v in obj.items() if k.startswith('tab:') and str(v.get('url', '')).startswith(url_prefix)}
            if tabs:
                k = sorted(tabs, key=lambda key: tabs[key].get('updatedAt', 0))[-1]
                return int(k.split(':')[1]), tabs[k]
            time.sleep(0.25)
        raise RuntimeError('No tab state for ' + url_prefix + ': ' + json.dumps(last)[:400])

    def summary(self, tab_id):
        return self.bg(f'(async () => {{ const s = await b.getState({tab_id}); const set = await b.getSettings(); return s ? b.applySettingsToSummary(b.PB.Report.summarize(s), set) : null; }})()') or {}

    def scripts(self, script_id):
        return len(self.bg(f"b.chrome.scripting.getRegisteredContentScripts({{ids: ['{script_id}']}})"))

    def popup_for(self, target_ctx):
        """Open popup.html the way the toolbar button does: the target tab is the active tab.

        BiDi cannot set the viewport of an extension tab. popup.css fixes html and body
        at 380x580, so the layout check measures the body and the screenshot clips to it.
        """
        self.ff.activate(target_ctx)
        pop = self.ff.open_extension_tab(POPUP, select=False)
        self.ff.wait(pop, "document.querySelector('#overall').textContent !== 'Loading report'", 15)
        self.ff.activate(pop)
        pause(0.3)
        return pop

    def layout(self, pop, name):
        res = self.ff.evalj(pop, LAYOUT_JS)
        path = ART / f'firefox-{name}.png'
        self.ff.screenshot(pop, path, clip=(0, 0, 380, 580))
        self.shots.append(str(path))
        self.check(f'layout {name}: 380x580, nothing clipped, footer visible, no page scroll',
                   res['width'] == 380 and res['height'] == 580 and not res['clipped'] and res['footer'] and not res['pageScroll'], res)

    def text(self, ctx, selector):
        return self.ff.eval(ctx, f"document.querySelector({json.dumps(selector)}).textContent")


def run(s):
    ff = s.ff
    gpc_id, dnt_id = 'privacybrew-gpc-main', 'privacybrew-dnt-main'
    s.collect_bg_errors()

    # Environment facts.
    rulesets = s.bg('b.chrome.declarativeNetRequest.getEnabledRulesets()')
    s.check('DNR static rulesets enabled', {'ads_easylist', 'block_advertising', 'allow_same_company', 'gpc_headers'} <= set(rulesets), rulesets)
    available = s.bg('b.chrome.declarativeNetRequest.getAvailableStaticRuleCount()')
    s.check('DNR static rule count within Firefox limit', isinstance(available, int) and available >= 0, available)
    print('INFO available static rule count', available)
    s.check('host access granted at install', s.bg("b.chrome.permissions.contains({origins: ['*://*/*']})") is True)
    s.check('storage.session works', s.bg("b.chrome.storage.session.set({pbProbe: 1}).then(() => b.chrome.storage.session.get('pbProbe')).then((r) => r.pbProbe)") == 1)
    s.bg("b.chrome.storage.session.remove('pbProbe')")

    # MAIN world registered scripts: one GPC script, also after extension reloads.
    s.check('one GPC script registered at start', s.scripts(gpc_id) == 1)
    for i in range(2):
        with contextlib.suppress(Exception):
            s.bg('(b.chrome.runtime.reload(), true)', timeout=10)
        s.ctl = None
        time.sleep(2)
        s.collect_bg_errors()
        s.check(f'one GPC script registered after reload {i + 1}', s.scripts(gpc_id) == 1)
    s.bg('Promise.all([b.setGpc(false), b.setGpc(true), b.setGpc(false), b.setGpc(true)])')
    s.check('one GPC script after rapid toggles', s.scripts(gpc_id) == 1)
    s.bg('b.setGpc(false)')
    s.check('no GPC script when off', s.scripts(gpc_id) == 0)
    s.bg('b.setGpc(true)')
    s.check('one GPC script when on again', s.scripts(gpc_id) == 1)

    # DNT header (DNR modifyHeaders) and navigator value (MAIN world script with matchOriginAsFallback).
    s.bg('b.setDnt(false)')
    before = len(rt.HEADER_LOG)
    t = s.tab(f'http://site.test:{PORT}/dnt.html')
    s.check('DNT off sends no header', not any(h.get('dnt') == '1' for h in rt.HEADER_LOG[before:]))
    s.check('DNT off navigator not one', s.page(t, 'navigator.doNotTrack') != '1')
    ff.close_tab(t)
    s.bg('Promise.all([b.setDnt(true), b.setDnt(false), b.setDnt(true)])')
    s.check('one DNT script when on', s.scripts(dnt_id) == 1)
    before = len(rt.HEADER_LOG)
    t = s.tab(f'http://site.test:{PORT}/dnt.html')
    hdrs = rt.HEADER_LOG[before:]
    s.check('DNT on sends document and subresource headers',
            any(h.get('path') == '/dnt.html' and h.get('dnt') == '1' for h in hdrs) and any(h.get('path') == '/dnt-sub.js' and h.get('dnt') == '1' for h in hdrs), hdrs)
    s.check('DNT on navigator top and iframe', s.page(t, "navigator.doNotTrack === '1' && document.querySelector('#dntFrame').contentWindow.navigator.doNotTrack === '1'") is True)
    ff.close_tab(t)
    s.bg('b.setDnt(false)')
    s.check('no DNT script when off again', s.scripts(dnt_id) == 0)

    # Cookie pop-ups: autoconsent bundle and the eval allowlist bridge.
    cfg = s.bg('b.autoconsentConfig(true)')
    s.check('autoconsent config opt out', cfg.get('autoAction') == 'optOut')
    s.check('autoconsent config never opt in', cfg.get('autoAction') != 'optIn')
    t = s.tab(f'http://site.test:{PORT}/cookiebot.html')
    pause(1)
    tab_id, _ = s.latest(f'http://site.test:{PORT}/cookiebot.html')
    rep = s.summary(tab_id)
    s.check('cookie reject clicked', s.page(t, 'window.__rejectClicked === true') is True)
    s.check('cookie accept not clicked', s.page(t, 'window.__acceptClicked === true') is not True)
    s.check('cookie report handled', rep.get('cookiePopup', {}).get('status') in ['rejected', 'answered'], rep.get('cookiePopup'))
    s.page(t, 'window.__pbEvalMark = 41')
    snippet = s.bg("b.ensureAutoconsentEvalSnippets().then((x) => Object.entries(x).find(([k, v]) => v.length < 200))")
    allowed = s.bg(f"b.evalForAutoconsent({{tab: {{id: {tab_id}}}, frameId: 0}}, {{snippetId: {json.dumps(snippet[0])}, code: {json.dumps(snippet[1])}}}).then((r) => r === undefined ? 'undefined' : r)")
    s.check('autoconsent allowlisted eval runs in MAIN world', allowed is not False, allowed)
    s.check('autoconsent non-allowlisted eval refused',
            s.bg(f"b.evalForAutoconsent({{tab: {{id: {tab_id}}}, frameId: 0}}, {{snippetId: {json.dumps(snippet[0])}, code: '(() => window.__pbEvalMark = 7)()'}})") is False
            and s.page(t, 'window.__pbEvalMark') == 41)
    main_world = s.bg(f"b.chrome.scripting.executeScript({{target: {{tabId: {tab_id}}}, world: 'MAIN', func: () => window.__pbEvalMark}}).then((r) => r[0].result)")
    s.check('scripting.executeScript world MAIN sees page variables', main_world == 41, main_world)
    ff.close_tab(t)
    t = s.tab(f'http://site.test:{PORT}/acceptonly.html')
    tab_id, _ = s.latest(f'http://site.test:{PORT}/acceptonly.html')
    rep = s.summary(tab_id)
    s.check('accept only hidden', s.page(t, "getComputedStyle(document.querySelector('#acceptOnly')).display") == 'none')
    s.check('accept only not accepted', s.page(t, 'window.__acceptClicked === true') is not True)
    s.check('hidden cookie report', rep.get('cookiePopup', {}).get('status') == 'hidden', rep.get('cookiePopup'))
    ff.close_tab(t)
    s.bg('b.setCookiePopupHandling(false)')
    t = s.tab(f'http://site.test:{PORT}/acceptonly.html')
    s.check('cookie switch off leaves banner', s.page(t, "getComputedStyle(document.querySelector('#acceptOnly')).display") != 'none')
    ff.close_tab(t)
    s.bg('b.setCookiePopupHandling(true)')
    s.bg("b.setPaused('site.test', true)")
    t = s.tab(f'http://site.test:{PORT}/acceptonly.html')
    s.check('paused site leaves cookie banner', s.page(t, "getComputedStyle(document.querySelector('#acceptOnly')).display") != 'none')
    ff.close_tab(t)
    s.bg("b.setPaused('site.test', false)")

    # Ad-blocker walls.
    wall = s.tab(f'http://site.test:{PORT}/wall.html')
    pause(4)
    wall_id, _ = s.latest(f'http://site.test:{PORT}/wall.html')
    s.check('ad wall detected', s.summary(wall_id).get('adWall') == 'detected')
    pop = s.popup_for(wall)
    s.ff.wait(pop, "!document.querySelector('#wallBanner').hidden", 10)
    s.check('ad wall banner shown', s.text(pop, '#wallText') == 'This website asks you to turn off ad blocking.')
    s.layout(pop, 'wall')
    ff.close_tab(pop)
    ff.close_tab(wall)
    t = s.tab(f'http://site.test:{PORT}/wall-hidden.html')
    pause(4)
    hid_id, _ = s.latest(f'http://site.test:{PORT}/wall-hidden.html')
    # ad-wall.js reports 'hidden' only when the page locks scroll with an inline style. This
    # fixture locks it with a style sheet, so the report can stay 'none'. The wall must stay hidden.
    print('INFO wall-hidden report adWall =', s.summary(hid_id).get('adWall'))
    s.check('ad wall hidden by cosmetic rules', s.page(t, "getComputedStyle(document.querySelector('#ADbox')).display") == 'none')
    s.check('ad wall hidden restores scroll', s.page(t, "document.body.style.overflow === '' && document.documentElement.style.overflow === ''") is True)
    ff.close_tab(t)

    # Off until the browser restarts (storage.session flag).
    s.bg('b.setOffUntilRestart(true)')
    s.check('restart off setting enabled', s.bg('b.getSettings()').get('restartOff') is True)
    s.bg('b.chrome.storage.session.set({restartOff: false}).then(() => b.applySettings())')
    s.check('restart off clears on restart', s.bg('b.getSettings()').get('restartOff') is False)

    # Trackers, ads, cosmetic hiding, fingerprinting, report counts and badge.
    page = s.tab(f'http://site.test:{PORT}/tracker.html')
    v = s.page(page, "({ga: window.__pbGaRan, ad: window.__pbDoubleClickRan, meta: window.__pbMetaRan, bing: window.__pbBingRan, content: window.__pbContentRan, unknown: window.__pbUnknownRan, adHost: window.__pbAdHostRan, adPath: window.__pbAdPathRan, adBox: getComputedStyle(document.querySelector('#ADbox')).display, normalBox: getComputedStyle(document.querySelector('#normalBox')).display, gpc: navigator.globalPrivacyControl})")
    tab_id, state = s.latest(f'http://site.test:{PORT}/tracker.html')
    rep = s.summary(tab_id)
    companies = sorted(x['company'] for x in state.get('trackers', {}).values())
    by_company = {x['company']: x for x in state.get('trackers', {}).values()}
    fps = sorted(state.get('fingerprints', {}).keys())
    fp_origins = sorted({o for origins in state.get('fingerprints', {}).values() for o in origins.keys()})
    badge = s.bg(f'b.chrome.action.getBadgeText({{tabId: {tab_id}}})')
    s.check('tracker company count', len(companies) >= 3, companies)
    s.check('advertising tracker scripts blocked', not v.get('ga') and not v.get('ad') and not v.get('bing'), v)
    s.check('social tracker script blocked', not v.get('meta'))
    s.check('content category script allowed', v.get('content') is True)
    s.check('unknown script allowed', v.get('unknown') is True)
    s.check('navigator GPC true', v.get('gpc') is True)
    s.check('ad host blocked', not v.get('adHost'))
    s.check('cosmetic ad hidden', v.get('adBox') == 'none' and v.get('normalBox') != 'none', v)
    s.check('Google detected', 'Google' in companies)
    s.check('Google advertising chip', 'Advertising' in by_company.get('Google', {}).get('categories', {}))
    s.check('Google analytics chip', 'Analytics' in by_company.get('Google', {}).get('categories', {}))
    s.check('Meta social or advertising chip', bool({'Social', 'Advertising'} & set(by_company.get('Meta', {}).get('categories', {}).keys())))
    s.check('Microsoft advertising chip', 'Advertising' in by_company.get('Microsoft', {}).get('categories', {}))
    s.check('unknown domain', 'some-unknown-thirdparty.example' in state.get('unknownDomains', {}))
    s.check('summary tracker requests', rep.get('trackerRequestCount', 0) >= 5, rep.get('trackerRequestCount'))
    s.check('summary blocked requests (NS_ERROR_ABORT counted)', rep.get('blockedTrackerCount', 0) >= 4, rep.get('blockedTrackerCount'))
    s.check('summary allowed requests', rep.get('allowedTrackerCount') == 1, rep.get('allowedTrackerCount'))
    s.check('summary invariant blocked + allowed = found', rep.get('trackerRequestCount') == rep.get('blockedTrackerCount', 0) + rep.get('allowedTrackerCount', 0))
    s.check('summary ad split', rep.get('adTrackerCount', 0) >= 2 and rep.get('adBlockedCount', 0) >= 2)
    s.check('summary outside scripts', rep.get('outsideScriptCount', 0) >= 6 and rep.get('outsideScriptBlockedCount', 0) >= 4, (rep.get('outsideScriptCount'), rep.get('outsideScriptBlockedCount')))
    s.check('ads blocked count', rep.get('adBlockedRequestCount', 0) >= 2, rep.get('adBlockedRequestCount'))
    for technique in ['canvas', 'webgl', 'audio', 'fonts']:
        s.check(f'{technique} fingerprint', technique in fps, fps)
    s.check('fingerprint source is page script', f'http://site.test:{PORT}/fp.js' in fp_origins, fp_origins)
    s.check('fingerprint source is not extension', not any(o.startswith('moz-extension://') for o in fp_origins))
    blocked_companies = [x for x in rep.get('trackers', []) if x.get('blockedRequestHashes')]
    s.check('badge text', badge == str(len(blocked_companies)), (badge, len(blocked_companies)))
    s.check('report has blocked status', any(x.get('status') == 'Blocked' for x in rep.get('trackers', [])))

    # tabs.reload through runtime messaging (the popup uses this).
    s.page(page, 'window.__pbReloadMark = 1')
    s.bg(f"browser.runtime.sendMessage({{type: 'reloadTab', tabId: {tab_id}}})")
    pause(2.5)
    s.check('messaging + tabs.reload reloads the tab', s.page(page, 'window.__pbReloadMark') is None)

    # Popup on the tracker page: numbers, feedback link, layout of all views.
    pop = s.popup_for(page)
    s.ff.wait(pop, "document.querySelector('#homeTrackersNumber').textContent !== '0'", 10)
    s.check('popup tracker tile', int(s.text(pop, '#homeTrackersNumber')) >= 5)
    s.check('popup blocked tile', '5 blocked' in s.text(pop, '#homeTrackersSub'), s.text(pop, '#homeTrackersSub'))
    s.check('popup allowed tile', 'allowed' in s.text(pop, '#homeTrackersSub'))
    s.check('popup outside script tile', s.text(pop, '#homeScriptsSub').endswith('blocked'))
    s.check('popup fingerprint tile', s.text(pop, '#homeFingerprintNumber') == '4')
    s.check('popup access notice hidden when access granted', s.ff.eval(pop, "document.querySelector('#accessBanner').hidden") is True)
    s.layout(pop, 'home')
    feedback = s.ff.evalj(pop, """(async () => {
      const urls = [];
      const real = chrome.tabs.create;
      chrome.tabs.create = async (opts) => { urls.push(opts.url); return {}; };
      document.querySelector('#feedbackButton').click();
      const hasPageBox = !!document.querySelector('#feedbackPage');
      document.querySelector('#openFeedback').click();
      await new Promise((r) => setTimeout(r, 200));
      document.querySelector('#feedbackVersion').checked = false;
      document.querySelector('#openFeedback').click();
      await new Promise((r) => setTimeout(r, 200));
      chrome.tabs.create = real;
      return { hasPageBox, urls };
    })()""")
    urls = (feedback or {}).get('urls', [])
    s.check('feedback has no page address option', (feedback or {}).get('hasPageBox') is False)
    s.check('feedback link never includes page', len(urls) == 2 and all('page=' not in u and 'site.test' not in u for u in urls), urls)
    s.check('feedback link has version and Firefox when ticked', len(urls) == 2 and 'v=' in urls[0] and 'browser=Firefox' in urls[0], urls)
    s.check('feedback link has no details when unticked', len(urls) == 2 and urls[1].endswith('feedback.html?'), urls)
    s.layout(pop, 'feedback')
    for name, action in [
        ('detail-trackers', "document.querySelector('#backButton').click(); document.querySelector('[data-detail=trackers]').click(); setTimeout(() => { const d = document.querySelector('details'); if (d) d.open = true; }, 50)"),
        ('settings', "document.querySelector('#backButton').click(); document.querySelector('#settingsButton').click()"),
        ('power-menu', "document.querySelector('#backButton').click(); document.querySelector('#powerButton').click()"),
        ('power-menu-while', "document.querySelector('#forAWhileButton').click()"),
    ]:
        s.ff.eval(pop, action + '; true')
        pause(0.4)
        s.layout(pop, name)
        if name == 'settings':
            s.check('Firefox scroll bar style applies', s.ff.eval(pop, "getComputedStyle(document.querySelector('#settingsView')).scrollbarWidth") == 'thin')
    ff.close_tab(pop)

    # Ad blocking switch.
    s.bg('b.setAdBlocking(false)')
    s.go(page, f'http://site.test:{PORT}/tracker.html')
    v = s.page(page, "({adPath: window.__pbAdPathRan, adBox: getComputedStyle(document.querySelector('#ADbox')).display})")
    s.check('ad switch off allows ads', v.get('adPath') is True and v.get('adBox') != 'none', v)
    s.bg('b.setAdBlocking(true)')

    # Pause on this website (dynamic allowAllRequests rule).
    s.bg("b.setPaused('site.test', true)")
    s.go(page, f'http://site.test:{PORT}/tracker.html')
    v = s.page(page, '({ga: window.__pbGaRan, ad: window.__pbDoubleClickRan, meta: window.__pbMetaRan, bing: window.__pbBingRan, adHost: window.__pbAdHostRan, adPath: window.__pbAdPathRan})')
    s.check('paused site allows trackers', all(v.get(k) for k in ['ga', 'ad', 'meta', 'bing', 'adHost', 'adPath']), v)
    rep = s.summary(tab_id)
    s.check('paused blocked count is zero', rep.get('blockedTrackerCount') == 0)
    s.check('paused allowed equals found', rep.get('allowedTrackerCount') == rep.get('trackerRequestCount'))
    s.check('paused rows are allowed', all(x.get('status') == 'Allowed' for x in rep.get('trackers', [])))
    pop = s.popup_for(page)
    s.check('paused header text', s.text(pop, '#statusText') == 'PrivacyBrew is off on this website')
    s.check('paused blocked tile', '0 blocked' in s.text(pop, '#homeTrackersSub'))
    s.layout(pop, 'paused')
    ff.close_tab(pop)
    s.bg("b.setPaused('site.test', false)")

    # Off for a while (alarms).
    s.bg('b.setTemporaryOff(15)')
    alarm = s.bg("b.chrome.alarms.get('privacybrew-temp-off')")
    s.check('temp off creates alarm', bool(alarm) and alarm.get('scheduledTime', 0) > time.time() * 1000 + 14 * 60000, alarm)
    s.go(page, f'http://site.test:{PORT}/tracker.html')
    v = s.page(page, '({ga: window.__pbGaRan, ad: window.__pbDoubleClickRan})')
    s.check('temp off allows trackers', v.get('ga') is True and v.get('ad') is True, v)
    pop = s.popup_for(page)
    s.check('temp off status bar shown', s.ff.eval(pop, "document.querySelector('#statusBar').hidden") is False, s.text(pop, '#statusText'))
    s.layout(pop, 'temp-off')
    ff.close_tab(pop)
    s.bg('b.setTemporaryOff(0)')
    s.check('temp off cleared removes alarm', not s.bg("b.chrome.alarms.get('privacybrew-temp-off')"))

    # Global off and the block switch.
    s.bg('b.setGlobalOff(true)')
    s.go(page, f'http://site.test:{PORT}/tracker.html')
    v = s.page(page, '({ga: window.__pbGaRan, ad: window.__pbDoubleClickRan, meta: window.__pbMetaRan, bing: window.__pbBingRan})')
    s.check('global off allows trackers', all(v.get(k) for k in ['ga', 'ad', 'meta', 'bing']), v)
    rep = s.summary(tab_id)
    s.check('global off blocked count is zero', rep.get('blockedTrackerCount') == 0)
    s.check('global off allowed equals found', rep.get('allowedTrackerCount') == rep.get('trackerRequestCount'))
    pop = s.popup_for(page)
    s.layout(pop, 'global-off')
    ff.close_tab(pop)
    s.bg('b.setGlobalOff(false)')
    s.bg('b.setGlobalBlocking(false)')
    s.go(page, f'http://site.test:{PORT}/tracker.html')
    v = s.page(page, '({ga: window.__pbGaRan, ad: window.__pbDoubleClickRan, meta: window.__pbMetaRan, bing: window.__pbBingRan})')
    s.check('block switch off allows trackers', all(v.get(k) for k in ['ga', 'ad', 'meta', 'bing']), v)
    rep = s.summary(tab_id)
    s.check('block switch off rows are allowed', all(x.get('status') == 'Allowed' for x in rep.get('trackers', [])))
    s.bg('b.setGlobalBlocking(true)')

    # GPC header (DNR modifyHeaders) on and off.
    s.check('GPC header sent when on', any(h['host'] == 'site.test' and h['secGpc'] == '1' for h in rt.HEADER_LOG))
    s.bg('b.setGpc(false)')
    before = len(rt.HEADER_LOG)
    s.go(page, f'http://clean.test:{PORT}/clean.html')
    s.check('GPC header absent when off', not any(h['secGpc'] == '1' for h in rt.HEADER_LOG[before:]))
    s.check('navigator GPC not true when off', s.page(page, 'navigator.globalPrivacyControl') is not True)
    s.bg('b.setGpc(true)')

    # Clean page.
    s.go(page, f'http://clean.test:{PORT}/clean.html')
    clean_id, clean_state = s.latest(f'http://clean.test:{PORT}/clean.html')
    rep = s.summary(clean_id)
    s.check('reset on clean navigation', not clean_state.get('trackers') and not clean_state.get('unknownDomains'))
    s.check('clean summary zeros', all(rep.get(k, 0) == 0 for k in ['trackerRequestCount', 'blockedTrackerCount', 'allowedTrackerCount', 'adTrackerCount', 'outsideScriptCount']))
    pop = s.popup_for(page)
    s.check('clean tracker tile zero', s.text(pop, '#homeTrackersNumber') == '0')
    s.check('clean fingerprint tile none', s.text(pop, '#homeFingerprintNumber') == 'None')
    ff.close_tab(pop)

    # SPA history changes keep counts; a new document resets them.
    spa = s.tab(f'http://site.test:{PORT}/spa.html')
    spa_id, _ = s.latest(f'http://site.test:{PORT}/spa')
    rep = s.summary(spa_id)
    s.check('SPA history keeps tracker counts', rep.get('trackerRequestCount', 0) >= 1 and rep.get('blockedTrackerCount', 0) >= 1, rep.get('trackerRequestCount'))
    s.go(spa, f'http://site.test:{PORT}/newpage.html')
    s.check('new document navigation resets tracker counts', s.summary(spa_id).get('trackerRequestCount', 0) == 0)
    ff.close_tab(spa)

    # Same company: doubleclick.net is Google, youtube.com is Google (session rules + allow_same_company).
    prop = s.tab(f'http://youtube.com:{PORT}/property.html')
    s.go(prop, f'http://youtube.com:{PORT}/property.html')
    # Same as tools/run_tests.py: not asserted. EasyList rules (priority 100) block doubleclick.net
    # ads on every site, which wins over the same-company allow rules (priority 2 and 3).
    print('INFO same-company doubleclick script ran on youtube.com:', s.page(prop, 'window.__pbDoubleClickRan') is True)
    prop_id, _ = s.latest(f'http://youtube.com:{PORT}/')
    session_rules = s.bg('b.chrome.declarativeNetRequest.getSessionRules()')
    s.check('same-company session rules created', any(r['id'] > 2000000 for r in session_rules), len(session_rules))
    ff.close_tab(prop)

    # Host access: Firefox users can take it away in about:addons.
    s.bg("b.chrome.permissions.remove({origins: ['*://*/*']})")
    s.check('host access can be removed', s.bg("b.chrome.permissions.contains({origins: ['*://*/*']})") is False)
    pop = s.popup_for(page)
    s.check('access notice shown without host access', s.ff.eval(pop, "document.querySelector('#accessBanner').hidden") is False)
    s.check('access notice text', s.text(pop, '#accessText') == 'PrivacyBrew needs access to websites to protect you.')
    s.layout(pop, 'no-access')
    granted = click_allow_and_accept(s, pop)
    s.check('Allow access button asks Firefox and gets access', granted is True)
    s.ff.wait(pop, "document.querySelector('#accessBanner').hidden", 10)
    s.check('access notice gone after access granted', s.ff.eval(pop, "document.querySelector('#accessBanner').hidden") is True)
    ff.close_tab(pop)
    s.go(page, f'http://site.test:{PORT}/tracker.html')
    s.check('blocking works again after access granted', not s.page(page, 'window.__pbGaRan'))

    s.collect_bg_errors()
    page_errors = [l for l in ff.lines if POPUP_ORIGIN in l and ('Error' in l or 'error' in l)]
    manifest_warnings = [l for l in ff.lines if 'Reading manifest' in l]
    s.check('Firefox reads the manifest without warnings', not manifest_warnings, manifest_warnings[:5])
    s.check('background has no errors', not s.bg_errors, s.bg_errors[:5])
    s.check('no extension script errors on stdout', not page_errors, page_errors[:5])


def click_allow_and_accept(s, pop):
    """Click 'Allow access' with a real mouse click (user action), then accept the Firefox prompt."""
    ff = s.ff
    box = ff.evalj(pop, "(() => { const r = document.querySelector('#accessAllow').getBoundingClientRect(); return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)}; })()")
    ff.call('input.performActions', {'context': pop, 'actions': [{'type': 'pointer', 'id': 'mouse', 'parameters': {'pointerType': 'mouse'}, 'actions': [
        {'type': 'pointerMove', 'x': box['x'], 'y': box['y']}, {'type': 'pointerDown', 'button': 0}, {'type': 'pointerUp', 'button': 0}]}]})
    chrome = ff.chrome_context()
    accept = """(() => { const n = PopupNotifications.getNotification('addon-webext-permissions', gBrowser.selectedBrowser)
      || PopupNotifications._currentNotifications.find((x) => x.id === 'addon-webext-permissions');
      if (!n) return false; n.mainAction.callback({}); PopupNotifications.remove(n); return true; })()"""
    with contextlib.suppress(Exception):
        ff.wait(chrome, accept, 10)
    end = time.time() + 10
    while time.time() < end:
        if s.bg("b.chrome.permissions.contains({origins: ['*://*/*']})") is True:
            return True
        time.sleep(0.3)
    return False


def main():
    skip_build = '--no-build' in sys.argv
    if HEADED and not (__import__('os').environ.get('DISPLAY') or __import__('os').environ.get('WAYLAND_DISPLAY')):
        raise SystemExit('--headed needs DISPLAY or WAYLAND_DISPLAY')
    ART.mkdir(exist_ok=True)
    zip_path = build_and_unpack(skip_build)
    server = rt.start_server()
    ff = None
    suite = None
    error = None
    try:
        hosts = rt.HOSTS
        proxy_prefs = {
            'network.proxy.type': 1, 'network.proxy.http': '127.0.0.1', 'network.proxy.http_port': DEAD_PROXY,
            'network.proxy.ssl': '127.0.0.1', 'network.proxy.ssl_port': DEAD_PROXY, 'network.proxy.share_proxy_settings': True,
            'network.proxy.no_proxies_on': ','.join(hosts) + ',localhost,127.0.0.1',
            'privacy.globalprivacycontrol.enabled': False,
        }
        ff = Firefox('e2e', hosts, headed=HEADED, time_limit=TIME_LIMIT, extra_prefs=proxy_prefs, window=(1280, 900))
        ext_id = ff.install(EXT_DIR)
        assert ext_id == GECKO_ID, ext_id
        time.sleep(2)
        suite = Suite(ff)
        run(suite)
    except Exception as e:  # report and fail, never retry
        error = e
        import traceback
        traceback.print_exc()
    finally:
        if ff:
            ff.close()
        server.shutdown()
        shutil.rmtree(EXT_DIR, ignore_errors=True)
    checks = suite.checks if suite else []
    failed = [n for n, ok in checks if not ok]
    print(json.dumps({'zip': str(zip_path.relative_to(ROOT)), 'pass': len(checks) - len(failed), 'fail': len(failed) + (1 if error else 0),
                      'failed': failed + ([f'harness error: {error}'] if error else []),
                      'screenshots': [str(Path(p).relative_to(ROOT)) for p in (suite.shots if suite else [])]}, indent=2))
    print(f'FIREFOX E2E: {len(checks) - len(failed)} passed, {len(failed) + (1 if error else 0)} failed')
    if failed or error:
        sys.exit(1)


if __name__ == '__main__':
    main()
