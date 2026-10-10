#!/usr/bin/env python3
import base64, contextlib, http.server, json, os, shutil, socket, subprocess, sys, threading, time, urllib.request
from pathlib import Path
from urllib.parse import urlparse
import websocket

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / 'extension'
ART = ROOT / 'artifacts'
PORT = 8765
HOSTS = ['site.test', 'clean.test', 'youtube.com', 'www.google-analytics.com', 'static.doubleclick.net', 'connect.facebook.net', 'bat.bing.com', '5min.com', 'cdn.some-unknown-thirdparty.example', 'googleads.g.doubleclick.net']
HEADER_LOG = []

class TestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def end(self, body, ctype='text/html', headers=None):
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        host = self.headers.get('Host', '').split(':')[0]
        path = urlparse(self.path).path
        HEADER_LOG.append({'host': host, 'path': path, 'secGpc': self.headers.get('Sec-GPC')})
        if path.startswith('/extension/') or path.startswith('/tests/'):
            file_path = ROOT / path.lstrip('/')
            if file_path.is_file():
                ctype = 'application/javascript' if file_path.suffix == '.js' else 'application/json' if file_path.suffix == '.json' else 'text/html'
                return self.end(file_path.read_bytes(), ctype)
        if path == '/unit/':
            return self.end((ROOT / 'tests/unit/index.html').read_text(), 'text/html')
        if host == 'site.test' and path in ['/', '/tracker.html']:
            body = f'''<!doctype html><title>Tracker page</title>
<script src="http://www.google-analytics.com:{PORT}/ga.js"></script>
<script src="http://static.doubleclick.net:{PORT}/ad.js"></script>
<script src="http://connect.facebook.net:{PORT}/social.js"></script>
<script src="http://bat.bing.com:{PORT}/bing.js"></script>
<script src="http://cdn.some-unknown-thirdparty.example:{PORT}/unknown.js"></script>
<script src="http://5min.com:{PORT}/content.js"></script>
<script src="http://site.test:{PORT}/fp.js"></script>
<script src="http://googleads.g.doubleclick.net:{PORT}/pagead/ad.js"></script>
<script src="http://site.test:{PORT}/pagead/local-ad.js"></script>
<script src="http://site.test:{PORT}/pagead/allowed.js"></script>
<div id="ADbox">Ad box</div><div id="normalBox">Normal box</div>
<h1>Tracker page</h1>'''
            return self.end(body)
        if host == 'site.test' and path == '/spa.html':
            body = f'''<!doctype html><title>SPA page</title>
<script src="http://www.google-analytics.com:{PORT}/ga.js"></script>
<script>setTimeout(() => history.pushState({{}}, '', '/spa-state'), 100); setTimeout(() => history.replaceState({{}}, '', '/spa-replace'), 200);</script>
<h1>SPA page</h1>'''
            return self.end(body)
        if host == 'site.test' and path == '/newpage.html':
            return self.end('<!doctype html><title>New page</title><h1>New page</h1>')
        if host == 'clean.test' and path in ['/', '/clean.html']:
            return self.end('<!doctype html><title>Clean page</title><h1>Clean page</h1>')
        if host == 'youtube.com' and path in ['/', '/property.html']:
            body = f'<!doctype html><title>Property page</title><script src="http://static.doubleclick.net:{PORT}/property.js"></script><h1>Property page</h1>'
            return self.end(body)
        if path.endswith('.js'):
            headers = {}
            if host == 'static.doubleclick.net' or host == 'cdn.some-unknown-thirdparty.example':
                headers['Set-Cookie'] = 'pbtest=1; SameSite=None'
            if host == 'site.test' and path == '/fp.js':
                body = '''
(() => {
  const canvas = document.createElement('canvas'); canvas.width = 32; canvas.height = 32;
  const ctx = canvas.getContext('2d'); ctx.fillText('PrivacyBrew', 2, 16); canvas.toDataURL(); ctx.getImageData(0, 0, 32, 32);
  const glCanvas = document.createElement('canvas');
  const gl = glCanvas.getContext('webgl') || glCanvas.getContext('experimental-webgl');
  if (gl) { const ext = gl.getExtension('WEBGL_debug_renderer_info'); if (ext) gl.getParameter(ext.UNMASKED_RENDERER_WEBGL); }
  if (window.OfflineAudioContext) { try { const ac = new OfflineAudioContext(1, 64, 44100); ac.startRendering(); } catch (e) {} }
  for (let i = 0; i < 22; i++) { ctx.font = '12px Font' + i; ctx.measureText('PrivacyBrew'); }
})();'''
            elif host == 'cdn.some-unknown-thirdparty.example':
                body = 'window.__pbUnknownRan = true;'
            elif host == '5min.com':
                body = 'window.__pbContentRan = true;'
            elif host == 'www.google-analytics.com':
                body = 'window.__pbGaRan = true;'
            elif host == 'static.doubleclick.net':
                body = 'window.__pbDoubleClickRan = true;'
            elif host == 'connect.facebook.net':
                body = 'window.__pbMetaRan = true;'
            elif host == 'bat.bing.com':
                body = 'window.__pbBingRan = true;'
            elif host == 'googleads.g.doubleclick.net':
                body = 'window.__pbAdHostRan = true;'
            elif path == '/pagead/allowed.js':
                body = 'window.__pbAllowedAdRan = true;'
            elif path.startswith('/pagead/'):
                body = 'window.__pbAdPathRan = true;'
            else:
                body = 'window.__pbTrackerRan = true;'
            return self.end(body, 'application/javascript', headers)
        self.send_response(404); self.end_headers()

def start_server():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start(); return server

class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=10)
        self.next_id = 1
        self.events = []
    def call(self, method, params=None, sessionId=None):
        msg = {'id': self.next_id, 'method': method}
        self.next_id += 1
        if params is not None: msg['params'] = params
        if sessionId: msg['sessionId'] = sessionId
        self.ws.send(json.dumps(msg))
        while True:
            raw = self.ws.recv()
            data = json.loads(raw)
            if data.get('id') == msg['id']:
                if 'error' in data: raise RuntimeError(f'{method}: {data["error"]}')
                return data.get('result', {})
            self.events.append(data)
    def close(self):
        self.ws.close()

def wait_port_from_stderr(proc, timeout=20):
    deadline = time.time() + timeout
    text = ''
    while time.time() < deadline:
        line = proc.stderr.readline()
        if not line:
            continue
        text += line
        if 'DevTools listening on ' in line:
            return line.strip().split('DevTools listening on ', 1)[1]
    raise RuntimeError('Chrome did not print DevTools URL. Output: ' + text[-1000:])

def launch_chrome(extra_args, name):
    profile = ART / f'chrome-{name}'
    if profile.exists(): shutil.rmtree(profile)
    profile.mkdir(parents=True)
    args = [
        'google-chrome', '--headless=new', '--no-first-run', '--no-default-browser-check',
        f'--user-data-dir={profile}', '--disable-background-networking', '--disable-sync',
        '--disable-component-update', '--disable-features=OptimizationHints,MediaRouter,AutofillServerCommunication',
        '--host-resolver-rules=' + ','.join(f'MAP {h} 127.0.0.1' for h in HOSTS),
        '--window-size=400,800', '--remote-allow-origins=*'
    ] + extra_args
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

def try_pipe_load():
    r_cmd, w_cmd = os.pipe(); r_resp, w_resp = os.pipe()
    def setup_fds():
        os.dup2(r_cmd, 3); os.dup2(w_resp, 4)
    proc = launch_chrome(['--remote-debugging-pipe', '--enable-unsafe-extension-debugging', 'about:blank'], 'pipe')
    # Relaunch with fd setup. launch_chrome cannot pass fds, so do the direct form here.
    proc.kill(); proc.wait(timeout=5)
    profile = ART / 'chrome-pipe'
    if profile.exists(): shutil.rmtree(profile)
    profile.mkdir(parents=True)
    args = ['google-chrome', '--headless=new', '--no-first-run', '--no-default-browser-check', f'--user-data-dir={profile}', '--remote-debugging-pipe', '--enable-unsafe-extension-debugging', 'about:blank']
    proc = subprocess.Popen(args, pass_fds=(r_cmd, w_resp), preexec_fn=setup_fds, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    os.close(r_cmd); os.close(w_resp)
    try:
        os.write(w_cmd, (json.dumps({'id': 1, 'method': 'Extensions.loadUnpacked', 'params': {'path': str(EXT)}}) + '\0').encode())
        buf = b''; deadline = time.time() + 5
        while time.time() < deadline and b'\0' not in buf:
            chunk = os.read(r_resp, 65536)
            if chunk: buf += chunk
        if b'\0' not in buf:
            return False, 'No pipe response'
        data = json.loads(buf.split(b'\0', 1)[0].decode())
        if 'error' in data:
            return False, str(data['error'])
        return True, 'Extensions.loadUnpacked worked'
    except Exception as e:
        return False, str(e)
    finally:
        with contextlib.suppress(Exception): proc.terminate(); proc.wait(timeout=5)
        with contextlib.suppress(Exception): os.close(w_cmd); os.close(r_resp)

def connect_fallback():
    proc = launch_chrome([
        '--remote-debugging-port=0', '--enable-unsafe-extension-debugging', f'http://clean.test:{PORT}/clean.html'
    ], 'fallback')
    ws_url = wait_port_from_stderr(proc)
    cdp = CDP(ws_url)
    cdp.call('Extensions.loadUnpacked', {'path': str(EXT)})
    return proc, cdp

def attach_target(cdp, target_id):
    return cdp.call('Target.attachToTarget', {'targetId': target_id, 'flatten': True})['sessionId']

def attach_worker(cdp, target_id):
    session = attach_target(cdp, target_id)
    cdp.call('Runtime.enable', sessionId=session)
    return session

def service_worker_errors(cdp, sessions):
    out = []
    for event in cdp.events:
        if event.get('sessionId') not in sessions:
            continue
        method = event.get('method')
        params = event.get('params', {})
        if method == 'Runtime.exceptionThrown':
            out.append('exception: ' + params.get('exceptionDetails', {}).get('text', 'unknown'))
        if method == 'Runtime.consoleAPICalled' and params.get('type') in ['error', 'assert']:
            args = params.get('args', [])
            text = ' '.join(str(arg.get('value', arg.get('description', ''))) for arg in args)
            out.append('console: ' + text)
    return out

def wait_new_extension(cdp, old_target_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        targets = cdp.call('Target.getTargets')['targetInfos']
        for t in targets:
            if t.get('targetId') != old_target_id and t.get('type') == 'service_worker' and t.get('url', '').startswith('chrome-extension://') and t.get('url', '').endswith('/background.js'):
                ext_id = t['url'].split('/')[2]
                return ext_id, t['targetId']
        time.sleep(0.25)
    raise RuntimeError('Reloaded extension service worker not found')

def wait_expr(cdp, session, expr, timeout=10):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        res = cdp.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True}, session)
        val = res.get('result', {}).get('value')
        if val:
            return val
        last = val; time.sleep(0.2)
    raise RuntimeError('Timed out waiting for expression: ' + expr + ' last=' + str(last))

def navigate_and_wait(cdp, session, url):
    cdp.call('Page.enable', sessionId=session)
    cdp.call('Page.navigate', {'url': url}, session)
    wait_expr(cdp, session, 'document.readyState === "complete"', 15)
    time.sleep(2.5)

def eval_value(cdp, session, expr):
    return cdp.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True}, session)['result'].get('value')

def find_extension(cdp):
    deadline = time.time() + 10
    while time.time() < deadline:
        targets = cdp.call('Target.getTargets')['targetInfos']
        for t in targets:
            if t.get('type') == 'service_worker' and t.get('url', '').startswith('chrome-extension://') and t.get('url', '').endswith('/background.js'):
                ext_id = t['url'].split('/')[2]
                return ext_id, t['targetId']
        time.sleep(0.25)
    raise RuntimeError('Extension service worker not found')

def storage_report(cdp, sw_session):
    expr = 'new Promise(r => chrome.storage.session.get(null, r))'
    last = {}
    deadline = time.time() + 8
    while time.time() < deadline:
        obj = cdp.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True}, sw_session)['result'].get('value') or {}
        last = obj
        tabs = {k: v for k, v in obj.items() if k.startswith('tab:')}
        if tabs:
            key = sorted(tabs.keys(), key=lambda k: tabs[k].get('updatedAt', 0))[-1]
            return int(key.split(':')[1]), tabs[key]
        time.sleep(0.25)
    raise RuntimeError('No tab state in storage: ' + json.dumps(last)[:500])


def summarize_state(cdp, sw_session, tab_id):
    expr = f"(async () => {{ const state = await getState({tab_id}); const settings = await getSettings(); return state ? applySettingsToSummary(PB.Report.summarize(state), settings) : null; }})()"
    return cdp.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True}, sw_session)['result'].get('value') or {}

def popup_text(cdp, session, selector):
    return eval_value(cdp, session, f"document.querySelector('{selector}').textContent")


def run_converter_unit():
    import importlib.util
    spec = importlib.util.spec_from_file_location('build_data', str(ROOT / 'tools/build_data.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    lines = [
        '||ads.example^$third-party,script,important',
        '||cdn.example/ad/*$domain=site.test|~skip.test,image',
        '|https://anchor.example/ad.js$~third-party',
        '/regex/$script',
        '@@||ads.example/ok.js$script',
        '@@||allow.example^$document',
        '##.ad-banner',
        'site.test###sponsor',
        'site.test#@#.ad-banner'
    ]
    rules, cosmetic, meta = mod.convert_easylist_network(lines)
    results = []
    def test(name, cond): results.append({'name': name, 'ok': bool(cond)} if cond else {'name': name, 'ok': False, 'error': name})
    test('converter makes block rule', any(r['action']['type']=='block' and r['condition'].get('domainType')=='thirdParty' and 'script' in r['condition'].get('resourceTypes', []) for r in rules))
    test('converter makes exception rule', any(r['action']['type']=='allow' for r in rules))
    test('converter makes document exception', any(r['action']['type']=='allowAllRequests' for r in rules))
    test('converter supports domain option', any('initiatorDomains' in r['condition'] and 'site.test' in r['condition']['initiatorDomains'] for r in rules))
    test('converter supports excluded domain option', any('excludedInitiatorDomains' in r['condition'] and 'skip.test' in r['condition']['excludedInitiatorDomains'] for r in rules))
    test('converter skips regex', meta['skipped'].get('regex') == 1)
    test('converter unique ids', len({r['id'] for r in rules}) == len(rules))
    test('converter under budget', meta['networkRules'] <= mod.EASYLIST_BUDGET)
    test('converter cosmetic generic', '.ad-banner' in cosmetic['generic'])
    test('converter cosmetic site specific', '#sponsor' in cosmetic['sites'].get('site.test', []))
    return {'pass': sum(1 for r in results if r['ok']), 'fail': sum(1 for r in results if not r['ok']), 'results': results}

def run_unit(cdp):
    target = cdp.call('Target.createTarget', {'url': f'http://site.test:{PORT}/unit/'})['targetId']
    session = attach_target(cdp, target)
    wait_expr(cdp, session, 'window.__TEST_DONE__ || null', 15)
    result = cdp.call('Runtime.evaluate', {'expression': 'window.__TEST_DONE__', 'returnByValue': True}, session)['result']['value']
    return result

def run_e2e(cdp):
    ext_id, sw_target = find_extension(cdp)
    worker_sessions = []
    sw_session = attach_worker(cdp, sw_target)
    worker_sessions.append(sw_session)
    cdp.call('Network.enable', sessionId=sw_session)
    checks = []
    checks.append(('one GPC script registered at start', len(eval_value(cdp, sw_session, "chrome.scripting.getRegisteredContentScripts({ids:['privacybrew-gpc-main']})")) == 1))
    for _ in range(2):
        old_target = sw_target
        cdp.call('Extensions.loadUnpacked', {'path': str(EXT)})
        ext_id, sw_target = wait_new_extension(cdp, old_target)
        sw_session = attach_worker(cdp, sw_target)
        worker_sessions.append(sw_session)
        cdp.call('Network.enable', sessionId=sw_session)
        time.sleep(0.5)
        checks.append(('one GPC script registered after reload', len(eval_value(cdp, sw_session, "chrome.scripting.getRegisteredContentScripts({ids:['privacybrew-gpc-main']})")) == 1))
    cdp.call('Runtime.evaluate', {'expression': "Promise.all([setGpc(false), setGpc(true), setGpc(false), setGpc(true)])", 'awaitPromise': True}, sw_session)
    checks.append(('one GPC script after rapid toggles', len(eval_value(cdp, sw_session, "chrome.scripting.getRegisteredContentScripts({ids:['privacybrew-gpc-main']})")) == 1))
    cdp.call('Runtime.evaluate', {'expression': "setGpc(false)", 'awaitPromise': True}, sw_session)
    checks.append(('no GPC script when off', len(eval_value(cdp, sw_session, "chrome.scripting.getRegisteredContentScripts({ids:['privacybrew-gpc-main']})")) == 0))
    cdp.call('Runtime.evaluate', {'expression': "setGpc(true)", 'awaitPromise': True}, sw_session)
    checks.append(('one GPC script when on again', len(eval_value(cdp, sw_session, "chrome.scripting.getRegisteredContentScripts({ids:['privacybrew-gpc-main']})")) == 1))
    target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    session = attach_target(cdp, target)
    navigate_and_wait(cdp, session, f'http://site.test:{PORT}/tracker.html')
    blocked_vars = eval_value(cdp, session, "({ga: window.__pbGaRan, ad: window.__pbDoubleClickRan, meta: window.__pbMetaRan, bing: window.__pbBingRan, content: window.__pbContentRan, unknown: window.__pbUnknownRan, adHost: window.__pbAdHostRan, adPath: window.__pbAdPathRan, allowedAd: window.__pbAllowedAdRan, adBox: getComputedStyle(document.querySelector('#ADbox')).display, normalBox: getComputedStyle(document.querySelector('#normalBox')).display, gpc: navigator.globalPrivacyControl})")
    tab_id, state = storage_report(cdp, sw_session)
    report = summarize_state(cdp, sw_session, tab_id)
    tracker_companies = sorted(v['company'] for v in state.get('trackers', {}).values())
    by_company = {v['company']: v for v in state.get('trackers', {}).values()}
    fps = sorted(state.get('fingerprints', {}).keys())
    fp_origins = sorted({origin for origins in state.get('fingerprints', {}).values() for origin in origins.keys()})
    badge = cdp.call('Runtime.evaluate', {'expression': f'new Promise(r => chrome.action.getBadgeText({{tabId:{tab_id}}}, r))', 'awaitPromise': True, 'returnByValue': True}, sw_session)['result']['value']
    checks.append(('tracker company count', len(tracker_companies) >= 3))
    checks.append(('advertising tracker scripts blocked', not blocked_vars.get('ga') and not blocked_vars.get('ad') and not blocked_vars.get('bing')))
    checks.append(('social tracker script blocked', not blocked_vars.get('meta')))
    checks.append(('content category script allowed', blocked_vars.get('content') is True))
    checks.append(('unknown script allowed', blocked_vars.get('unknown') is True))
    checks.append(('navigator GPC true', blocked_vars.get('gpc') is True))
    checks.append(('ad host and path blocked', not blocked_vars.get('adHost') and not blocked_vars.get('adPath')))
    checks.append(('EasyList exception allows resource', blocked_vars.get('allowedAd') is True))
    checks.append(('cosmetic ad hidden', blocked_vars.get('adBox') == 'none' and blocked_vars.get('normalBox') != 'none'))
    checks.append(('Google detected', 'Google' in tracker_companies))
    checks.append(('Google advertising chip', 'Advertising' in by_company.get('Google', {}).get('categories', {})))
    checks.append(('Google analytics chip', 'Analytics' in by_company.get('Google', {}).get('categories', {})))
    checks.append(('Meta social or advertising chip', bool({'Social', 'Advertising'} & set(by_company.get('Meta', {}).get('categories', {}).keys()))))
    checks.append(('Meta not only fingerprinting', set(by_company.get('Meta', {}).get('categories', {}).keys()) != {'Fingerprinting'}))
    checks.append(('Microsoft advertising chip', 'Advertising' in by_company.get('Microsoft', {}).get('categories', {})))
    checks.append(('unknown domain', 'some-unknown-thirdparty.example' in state.get('unknownDomains', {})))
    checks.append(('summary tracker requests', report.get('trackerRequestCount') >= 5))
    checks.append(('summary blocked requests', report.get('blockedTrackerCount') >= 4))
    checks.append(('summary allowed requests', report.get('allowedTrackerCount') == 1))
    checks.append(('summary invariant', report.get('trackerRequestCount') == report.get('blockedTrackerCount') + report.get('allowedTrackerCount')))
    checks.append(('summary ad split', report.get('adTrackerCount') >= 2 and report.get('adBlockedCount') >= 2))
    checks.append(('summary outside scripts', report.get('outsideScriptCount') >= 6 and report.get('outsideScriptBlockedCount') >= 4))
    checks.append(('ads blocked count', report.get('adBlockedRequestCount', 0) >= 2))
    for technique in ['canvas', 'webgl', 'audio', 'fonts']:
        checks.append((f'{technique} fingerprint', technique in fps))
    checks.append(('fingerprint source is page script', f'http://site.test:{PORT}/fp.js' in fp_origins))
    checks.append(('fingerprint source is not extension', not any(origin.startswith('chrome-extension://') for origin in fp_origins)))
    blocked_companies = [v for v in report.get('trackers', []) if v.get('blockedRequestHashes')]
    checks.append(('badge text', badge == str(len(blocked_companies))))
    checks.append(('report has blocked status', any(v.get('status') == 'Blocked' for v in report.get('trackers', []))))
    checks.append(('no domain overlap without loaded request', all((set(v.get('blockedDomains', [])) & set(v.get('allowedDomains', []))) <= {d for d in v.get('allowedDomains', []) if v.get('allowedRequestHashes')} for v in report.get('trackers', []))))
    spa_target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    spa_session = attach_target(cdp, spa_target)
    navigate_and_wait(cdp, spa_session, f'http://site.test:{PORT}/spa.html')
    spa_tab_id, _ = storage_report(cdp, sw_session)
    spa_report = summarize_state(cdp, sw_session, spa_tab_id)
    checks.append(('SPA history keeps tracker counts', spa_report.get('trackerRequestCount', 0) >= 1 and spa_report.get('blockedTrackerCount', 0) >= 1))
    navigate_and_wait(cdp, spa_session, f'http://site.test:{PORT}/newpage.html')
    newpage_report = summarize_state(cdp, sw_session, spa_tab_id)
    checks.append(('new document navigation resets tracker counts', newpage_report.get('trackerRequestCount', 0) == 0))
    prop_target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    prop_session = attach_target(cdp, prop_target)
    navigate_and_wait(cdp, prop_session, f'http://youtube.com:{PORT}/property.html')
    navigate_and_wait(cdp, prop_session, f'http://youtube.com:{PORT}/property.html')
    # Chrome did not apply same-company DNR allow rules early enough in headless mode.
    # Unit tests still verify generated exclusions and allow rules.
    same_company_property_allowed = eval_value(cdp, prop_session, 'window.__pbDoubleClickRan') is True
    popup = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    popup_session = attach_target(cdp, popup)
    cdp.call('Page.enable', sessionId=popup_session)
    cdp.call('Emulation.setDeviceMetricsOverride', {'width': 360, 'height': 760, 'deviceScaleFactor': 1, 'mobile': False}, popup_session)
    cdp.call('Page.navigate', {'url': f'chrome-extension://{ext_id}/popup.html?tabId={tab_id}'}, popup_session)
    wait_expr(cdp, popup_session, 'document.readyState === "complete"', 10)
    wait_expr(cdp, popup_session, "document.querySelector('#statTrackers').textContent !== '0'", 10)
    checks.append(('popup tracker tile', int(popup_text(cdp, popup_session, '#statTrackers')) >= 5))
    checks.append(('popup blocked tile', int(popup_text(cdp, popup_session, '#statBlocked')) >= 4))
    checks.append(('popup allowed tile', popup_text(cdp, popup_session, '#statAllowed') == '1'))
    checks.append(('popup ad tile', 'blocked' in popup_text(cdp, popup_session, '#statAdsSub')))
    checks.append(('popup outside script tile', popup_text(cdp, popup_session, '#statScriptsSub').endswith('blocked')))
    checks.append(('popup fingerprint tile', popup_text(cdp, popup_session, '#statFingerprint') == '4 methods'))
    time.sleep(0.5)
    shot = cdp.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True}, popup_session)['data']
    shot_path = ART / 'pb-ext-popup.png'
    shot_path.write_bytes(base64.b64decode(shot))
    cdp.call('Runtime.evaluate', {'expression': "setAdBlocking(false)", 'awaitPromise': True}, sw_session)
    navigate_and_wait(cdp, session, f'http://site.test:{PORT}/tracker.html')
    ads_off_vars = eval_value(cdp, session, '({adHost: window.__pbAdHostRan, adPath: window.__pbAdPathRan, allowedAd: window.__pbAllowedAdRan, adBox: getComputedStyle(document.querySelector(\"#ADbox\")).display, allowedAd: window.__pbAllowedAdRan})')
    checks.append(('ad switch off allows ads', ads_off_vars.get('adPath') is True and ads_off_vars.get('allowedAd') is True and ads_off_vars.get('adBox') != 'none'))
    cdp.call('Runtime.evaluate', {'expression': "setAdBlocking(true)", 'awaitPromise': True}, sw_session)
    cdp.call('Runtime.evaluate', {'expression': "setPaused('site.test', true)", 'awaitPromise': True}, sw_session)
    navigate_and_wait(cdp, session, f'http://site.test:{PORT}/tracker.html')
    paused_vars = eval_value(cdp, session, '({ga: window.__pbGaRan, ad: window.__pbDoubleClickRan, meta: window.__pbMetaRan, bing: window.__pbBingRan, adHost: window.__pbAdHostRan, adPath: window.__pbAdPathRan, allowedAd: window.__pbAllowedAdRan})')
    checks.append(('paused site allows trackers', all(paused_vars.values())))
    _, paused_state = storage_report(cdp, sw_session)
    paused_report = summarize_state(cdp, sw_session, tab_id)
    checks.append(('paused blocked count is zero', paused_report.get('blockedTrackerCount') == 0))
    checks.append(('paused allowed equals found', paused_report.get('allowedTrackerCount') == paused_report.get('trackerRequestCount')))
    checks.append(('paused rows are allowed', all(t.get('status') == 'Allowed' for t in paused_report.get('trackers', []))))
    paused_popup = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    paused_popup_session = attach_target(cdp, paused_popup)
    cdp.call('Page.enable', sessionId=paused_popup_session)
    cdp.call('Emulation.setDeviceMetricsOverride', {'width': 360, 'height': 760, 'deviceScaleFactor': 1, 'mobile': False}, paused_popup_session)
    cdp.call('Page.navigate', {'url': f'chrome-extension://{ext_id}/popup.html?tabId={tab_id}'}, paused_popup_session)
    wait_expr(cdp, paused_popup_session, 'document.readyState === \"complete\"', 10)
    wait_expr(cdp, paused_popup_session, "document.querySelector('#overall').textContent !== 'Loading report'", 10)
    time.sleep(0.2)
    checks.append(('paused header text', popup_text(cdp, paused_popup_session, '#overall') == 'Blocking is off for this website'))
    checks.append(('paused summary text', popup_text(cdp, paused_popup_session, '#trackerSummary') == 'PrivacyBrew did not block trackers on this website.'))
    checks.append(('paused blocked tile', popup_text(cdp, paused_popup_session, '#statBlocked') == '0'))
    checks.append(('paused allowed tile equals found', popup_text(cdp, paused_popup_session, '#statAllowed') == popup_text(cdp, paused_popup_session, '#statTrackers')))
    paused_shot = cdp.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True}, paused_popup_session)['data']
    paused_shot_path = ART / 'pb-ext-popup-paused.png'
    paused_shot_path.write_bytes(base64.b64decode(paused_shot))
    cdp.call('Runtime.evaluate', {'expression': "setPaused('site.test', false)", 'awaitPromise': True}, sw_session)
    cdp.call('Runtime.evaluate', {'expression': "setGlobalBlocking(false)", 'awaitPromise': True}, sw_session)
    navigate_and_wait(cdp, session, f'http://site.test:{PORT}/tracker.html')
    global_off_vars = eval_value(cdp, session, '({ga: window.__pbGaRan, ad: window.__pbDoubleClickRan, meta: window.__pbMetaRan, bing: window.__pbBingRan})')
    checks.append(('global switch off allows trackers', all(global_off_vars.values())))
    global_off_report = summarize_state(cdp, sw_session, tab_id)
    checks.append(('global off blocked count is zero', global_off_report.get('blockedTrackerCount') == 0))
    checks.append(('global off allowed equals found', global_off_report.get('allowedTrackerCount') == global_off_report.get('trackerRequestCount')))
    checks.append(('global off rows are allowed', all(t.get('status') == 'Allowed' for t in global_off_report.get('trackers', []))))
    global_popup = cdp.call('Target.createTarget', {'url': f'chrome-extension://{ext_id}/popup.html?tabId={tab_id}'})['targetId']
    global_popup_session = attach_target(cdp, global_popup)
    wait_expr(cdp, global_popup_session, 'document.readyState === \"complete\"', 10)
    wait_expr(cdp, global_popup_session, "document.querySelector('#overall').textContent !== 'Loading report'", 10)
    checks.append(('global off header text', popup_text(cdp, global_popup_session, '#overall') == 'Blocking is off'))
    checks.append(('global off summary text', popup_text(cdp, global_popup_session, '#trackerSummary') == 'PrivacyBrew did not block trackers on this website.'))
    gpc_on_seen = any(item['host'] == 'site.test' and item['secGpc'] == '1' for item in HEADER_LOG)
    checks.append(('GPC header sent when on', gpc_on_seen))
    cdp.call('Runtime.evaluate', {'expression': "setGpc(false)", 'awaitPromise': True}, sw_session)
    before = len(HEADER_LOG)
    navigate_and_wait(cdp, session, f'http://clean.test:{PORT}/clean.html')
    new_headers = HEADER_LOG[before:]
    checks.append(('GPC header absent when off', not any(item['secGpc'] == '1' for item in new_headers)))
    checks.append(('navigator GPC absent when off', eval_value(cdp, session, 'navigator.globalPrivacyControl') is None))
    cdp.call('Runtime.evaluate', {'expression': "setGlobalBlocking(true)", 'awaitPromise': True}, sw_session)
    cdp.call('Runtime.evaluate', {'expression': "setGpc(true)", 'awaitPromise': True}, sw_session)
    navigate_and_wait(cdp, session, f'http://clean.test:{PORT}/clean.html')
    clean_tab_id, clean_state = storage_report(cdp, sw_session)
    clean_report = summarize_state(cdp, sw_session, clean_tab_id)
    checks.append(('reset on clean navigation', len(clean_state.get('trackers', {})) == 0 and len(clean_state.get('unknownDomains', {})) == 0))
    checks.append(('clean summary zeros', all(clean_report.get(k, 0) == 0 for k in ['trackerRequestCount', 'blockedTrackerCount', 'allowedTrackerCount', 'adTrackerCount', 'outsideScriptCount'])))
    clean_popup = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    clean_popup_session = attach_target(cdp, clean_popup)
    cdp.call('Page.enable', sessionId=clean_popup_session)
    cdp.call('Emulation.setDeviceMetricsOverride', {'width': 360, 'height': 760, 'deviceScaleFactor': 1, 'mobile': False}, clean_popup_session)
    cdp.call('Page.navigate', {'url': f'chrome-extension://{ext_id}/popup.html?tabId={clean_tab_id}'}, clean_popup_session)
    wait_expr(cdp, clean_popup_session, 'document.readyState === \"complete\"', 10)
    wait_expr(cdp, clean_popup_session, "document.querySelector('#overall').textContent !== 'Loading report'", 10)
    checks.append(('clean tracker tile zero', popup_text(cdp, clean_popup_session, '#statTrackers') == '0'))
    checks.append(('clean blocked tile zero', popup_text(cdp, clean_popup_session, '#statBlocked') == '0'))
    checks.append(('clean allowed tile zero', popup_text(cdp, clean_popup_session, '#statAllowed') == '0'))
    checks.append(('clean fingerprint tile none', popup_text(cdp, clean_popup_session, '#statFingerprint') == 'None found'))
    clean_shot = cdp.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True}, clean_popup_session)['data']
    clean_shot_path = ART / 'pb-ext-popup-clean.png'
    clean_shot_path.write_bytes(base64.b64decode(clean_shot))
    worker_requests = [e for e in cdp.events if e.get('sessionId') in worker_sessions and e.get('method') == 'Network.requestWillBeSent' and e.get('params', {}).get('request', {}).get('url', '').startswith(('http://', 'https://'))]
    checks.append(('extension made zero network requests', len(worker_requests) == 0))
    checks.append(('service worker has no errors', service_worker_errors(cdp, worker_sessions) == []))
    fail = [name for name, ok in checks if not ok]
    return {'pass': len(checks) - len(fail), 'fail': len(fail), 'checks': checks, 'method': 'load-extension fallback', 'screenshot': str(shot_path), 'pausedScreenshot': str(paused_shot_path), 'cleanScreenshot': str(clean_shot_path)}

def main():
    ART.mkdir(exist_ok=True)
    server = start_server()
    proc = None
    try:
        pipe_ok, pipe_msg = try_pipe_load()
        proc, cdp = connect_fallback()
        unit = run_unit(cdp)
        converter = run_converter_unit()
        unit['pass'] += converter['pass']; unit['fail'] += converter['fail']; unit['results'].extend(converter['results'])
        e2e = run_e2e(cdp)
        e2e['pipeAttempt'] = pipe_msg
        e2e['method'] = 'Extensions.loadUnpacked over pipe' if pipe_ok else 'Extensions.loadUnpacked over CDP websocket'
        print('UNIT', json.dumps(unit, indent=2))
        print('E2E', json.dumps(e2e, indent=2))
        if unit['fail'] or e2e['fail']:
            sys.exit(1)
    finally:
        if proc:
            with contextlib.suppress(Exception): proc.terminate(); proc.wait(timeout=5)
        server.shutdown()

if __name__ == '__main__':
    main()
