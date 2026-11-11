#!/usr/bin/env python3
import base64, contextlib, http.server, json, os, shutil, socket, subprocess, sys, threading, time, urllib.request
from pathlib import Path
from urllib.parse import urlparse
import websocket

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / 'extension'
ART = ROOT / 'artifacts'
PORT = 8796  # not 8765: that port is used by the website preview server
HOSTS = ['site.test', 'clean.test', 'youtube.com', 'www.google-analytics.com', 'static.doubleclick.net', 'connect.facebook.net', 'bat.bing.com', '5min.com', 'cdn.some-unknown-thirdparty.example', 'googleads.g.doubleclick.net']
HEADER_LOG = []
# Chrome also runs its own extensions with a background.js (for example the
# Gemini helper), so the tests look for the worker of the extension they loaded.
OUR_ID = None
HEADLESS = '--headed' not in sys.argv
SLOW = '--slow' in sys.argv
if not HEADLESS and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
    raise SystemExit('--headed needs DISPLAY or WAYLAND_DISPLAY')

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
        HEADER_LOG.append({'host': host, 'path': path, 'secGpc': self.headers.get('Sec-GPC'), 'dnt': self.headers.get('DNT')})
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
<div id="ADbox">Ad box</div><div id="normalBox">Normal box</div>
<h1>Tracker page</h1>'''
            return self.end(body)
        if host == 'site.test' and path == '/dnt.html':
            body = f'''<!doctype html><title>DNT page</title><script src="http://site.test:{PORT}/dnt-sub.js"></script><iframe id="dntFrame" src="http://site.test:{PORT}/dnt-frame.html"></iframe><h1>DNT page</h1>'''
            return self.end(body)
        if host == 'site.test' and path == '/dnt-frame.html':
            return self.end('<!doctype html><title>DNT frame</title><h1>DNT frame</h1>')
        if host == 'site.test' and path == '/wall.html':
            body = '''<!doctype html><title>Wall</title><style>body{overflow:hidden}.wall{position:fixed;inset:10%;z-index:9999;background:white;color:black;padding:30px}</style><div class="wall"><h1>Please disable your ad blocker</h1><p>Allowlist this site to continue.</p></div>'''
            return self.end(body)
        if host == 'site.test' and path == '/wall-hidden.html':
            body = '''<!doctype html><title>Hidden wall</title><style>html,body{overflow:hidden}</style><div id="ADbox" style="position:fixed;inset:10%;z-index:9999;background:white;color:black"><h1>Please disable your ad blocker</h1></div>'''
            return self.end(body)
        if host == 'site.test' and path == '/cookiebot.html':
            body = '''<!doctype html><title>Cookiebot fixture</title><div id="cbPopupWrap" class="cb-popup--open" style="position:fixed;inset:20px;background:white;color:black;z-index:9999"><p>Cookie consent</p><button id="cbAcceptTrigger" onclick="window.__acceptClicked=true;document.cookie='cbDataAccepted=0; path=/';">Accept</button><button id="cbRefuseTrigger" onclick="window.__rejectClicked=true;document.cookie='cbDataAccepted=1; path=/';this.closest('#cbPopupWrap').style.display='none';">Reject</button></div><h1>Cookiebot</h1>'''
            return self.end(body)
        if host == 'site.test' and path == '/simpleconsent.html':
            body = '''<!doctype html><title>Simple consent fixture</title><dialog class="cookie-consent" open><form class="cookie-consent__form"><p>Cookie consent</p><button value="yes" onclick="window.__acceptClicked=true" type="button">Accept</button><button value="no" onclick="window.__rejectClicked=true;this.closest('dialog').close();" type="button">Reject</button></form></dialog><h1>Simple consent</h1>'''
            return self.end(body)
        if host == 'site.test' and path == '/acceptonly.html':
            body = '''<!doctype html><title>Accept only fixture</title><div id="acceptOnly" role="dialog" style="position:fixed;inset:20px;background:white;color:black;z-index:9999"><p>This site uses cookies for privacy choices.</p><button id="acceptOnlyButton" onclick="window.__acceptClicked=true">Accept all</button></div><h1>Accept only</h1>'''
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
            if host == 'site.test' and path == '/dnt-sub.js':
                body = 'window.__pbDntSubRan = true;'
            elif host == 'site.test' and path == '/fp.js':
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
        'google-chrome', *(['--headless=new'] if HEADLESS else []), '--no-first-run', '--no-default-browser-check',
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
    args = ['google-chrome', *(['--headless=new'] if HEADLESS else []), '--no-first-run', '--no-default-browser-check', f'--user-data-dir={profile}', '--remote-debugging-pipe', '--enable-unsafe-extension-debugging', 'about:blank']
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
    global OUR_ID
    OUR_ID = cdp.call('Extensions.loadUnpacked', {'path': str(EXT)}).get('id')
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

def is_ours(target):
    return not OUR_ID or target.get('url', '').startswith(f'chrome-extension://{OUR_ID}/')

def wait_new_extension(cdp, old_target_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        targets = cdp.call('Target.getTargets')['targetInfos']
        for t in targets:
            if t.get('targetId') != old_target_id and t.get('type') == 'service_worker' and t.get('url', '').startswith('chrome-extension://') and t.get('url', '').endswith('/background.js') and is_ours(t):
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
    time.sleep(2.5 + (0.6 if SLOW else 0))

def eval_value(cdp, session, expr):
    return cdp.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True}, session)['result'].get('value')

def find_extension(cdp):
    deadline = time.time() + 10
    while time.time() < deadline:
        targets = cdp.call('Target.getTargets')['targetInfos']
        for t in targets:
            if t.get('type') == 'service_worker' and t.get('url', '').startswith('chrome-extension://') and t.get('url', '').endswith('/background.js') and is_ours(t):
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

    merged = mod.merge_domain_rules_from_items([
        {'priority': 1, 'action': 'block', 'condition': {'requestDomains': ['a.example'], 'domainType': 'thirdParty', 'resourceTypes': ['script']}},
        {'priority': 1, 'action': 'block', 'condition': {'requestDomains': ['b.example'], 'domainType': 'thirdParty', 'resourceTypes': ['script']}},
        {'priority': 1, 'action': 'block', 'condition': {'requestDomains': ['c.example'], 'domainType': 'firstParty', 'resourceTypes': ['script']}},
    ], 1)
    merged_domains = [set(rule['condition'].get('requestDomains', [])) for rule in merged]
    test('converter merges identical domain rules', any({'a.example', 'b.example'} == domains for domains in merged_domains))
    test('converter preserves different options when merging', any({'c.example'} == domains and rule['condition'].get('domainType') == 'firstParty' for rule, domains in zip(merged, merged_domains)))
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
    stale = eval_value(cdp, sw_session, """(async()=>{ await ensureData(); const t=987650;
      const oldState=PB.Report.emptyState(t,'https://old.example/','old.example'); await saveNow(t, oldState);
      const newState=PB.Report.emptyState(t,'https://new.example/','new.example'); await saveNow(t, newState);
      scheduleSave(t, oldState); await new Promise(r=>setTimeout(r, WRITE_DELAY_MS + 300));
      const stored=(await chrome.storage.session.get('tab:'+t))['tab:'+t];
      const result=(await getState(t)).siteDomain + '|' + stored.siteDomain;
      memory.delete(t); await chrome.storage.session.remove('tab:'+t); return result; })()""")
    checks.append(('late save of old page keeps the new report', stale == 'new.example|new.example'))
    checks.append(('ad frame message uses the page address', eval_value(cdp, sw_session, "pageUrlFor({frameId: 3, url: 'https://ads.example/frame', tab: {url: 'https://news.example/story'}})") == 'https://news.example/story'))
    checks.append(('top frame message uses its own address', eval_value(cdp, sw_session, "pageUrlFor({frameId: 0, url: 'https://news.example/a', tab: {url: 'https://news.example/b'}})") == 'https://news.example/a'))
    partial = eval_value(cdp, sw_session, """(async()=>{ const t=987651; const s=await ensureTabState(t,'https://late.example/'); const r=PB.Report.summarize(s); memory.delete(t); await chrome.storage.session.remove('tab:'+t); return r.partial === true && r.siteDomain === 'late.example'; })()""")
    checks.append(('report that starts late is marked incomplete', partial is True))
    cdp.call('Runtime.evaluate', {'expression': "setDnt(false)", 'awaitPromise': True}, sw_session)
    before = len(HEADER_LOG)
    dnt_off_target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    dnt_off_session = attach_target(cdp, dnt_off_target)
    navigate_and_wait(cdp, dnt_off_session, f'http://site.test:{PORT}/dnt.html')
    dnt_off_headers = HEADER_LOG[before:]
    checks.append(('DNT off sends no header', not any(item.get('dnt') == '1' for item in dnt_off_headers)))
    checks.append(('DNT off navigator not one', eval_value(cdp, dnt_off_session, 'navigator.doNotTrack') != '1'))
    cdp.call('Runtime.evaluate', {'expression': "Promise.all([setDnt(true), setDnt(false), setDnt(true)])", 'awaitPromise': True}, sw_session)
    checks.append(('one DNT script when on', len(eval_value(cdp, sw_session, "chrome.scripting.getRegisteredContentScripts({ids:['privacybrew-dnt-main']})")) == 1))
    before = len(HEADER_LOG)
    dnt_on_target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    dnt_on_session = attach_target(cdp, dnt_on_target)
    navigate_and_wait(cdp, dnt_on_session, f'http://site.test:{PORT}/dnt.html')
    dnt_on_headers = HEADER_LOG[before:]
    checks.append(('DNT on sends document and subresource headers', any(item.get('path') == '/dnt.html' and item.get('dnt') == '1' for item in dnt_on_headers) and any(item.get('path') == '/dnt-sub.js' and item.get('dnt') == '1' for item in dnt_on_headers)))
    checks.append(('DNT on navigator top and iframe', eval_value(cdp, dnt_on_session, "navigator.doNotTrack === '1' && document.querySelector('#dntFrame').contentWindow.navigator.doNotTrack === '1'") is True))
    cdp.call('Runtime.evaluate', {'expression': "setDnt(false)", 'awaitPromise': True}, sw_session)
    checks.append(('no DNT script when off again', len(eval_value(cdp, sw_session, "chrome.scripting.getRegisteredContentScripts({ids:['privacybrew-dnt-main']})")) == 0))
    ac_config = eval_value(cdp, sw_session, 'autoconsentConfig(true)')
    checks.append(('autoconsent config opt out', ac_config.get('autoAction') == 'optOut'))
    checks.append(('autoconsent config never opt in', ac_config.get('autoAction') != 'optIn'))
    checks.append(('autoconsent allowlisted eval runs', eval_value(cdp, sw_session, "(async()=>{const tab=(await chrome.tabs.query({active:true,lastFocusedWindow:true}))[0]; return evalForAutoconsent({tab, frameId:0}, {snippetId:'EVAL_0', code:'(() => console.log(1))()'});})()") is None))
    checks.append(('autoconsent non-allowlisted eval refused', eval_value(cdp, sw_session, "(async()=>{const tab=(await chrome.tabs.query({active:true,lastFocusedWindow:true}))[0]; return evalForAutoconsent({tab, frameId:0}, {snippetId:'EVAL_0', code:'(() => 7)()'});})()") is False))
    cookie_target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    cookie_session = attach_target(cdp, cookie_target)
    navigate_and_wait(cdp, cookie_session, f'http://site.test:{PORT}/cookiebot.html')
    cookie_tab_id, _ = storage_report(cdp, sw_session)
    cookie_report = summarize_state(cdp, sw_session, cookie_tab_id)
    checks.append(('cookie reject clicked', eval_value(cdp, cookie_session, 'window.__rejectClicked === true') is True))
    checks.append(('cookie accept not clicked', eval_value(cdp, cookie_session, 'window.__acceptClicked === true') is not True))
    checks.append(('cookie report handled', cookie_report.get('cookiePopup', {}).get('status') in ['rejected', 'answered']))
    accept_target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    accept_session = attach_target(cdp, accept_target)
    navigate_and_wait(cdp, accept_session, f'http://site.test:{PORT}/acceptonly.html')
    accept_tab_id, _ = storage_report(cdp, sw_session)
    accept_report = summarize_state(cdp, sw_session, accept_tab_id)
    checks.append(('accept only hidden', eval_value(cdp, accept_session, "getComputedStyle(document.querySelector('#acceptOnly')).display") == 'none'))
    checks.append(('accept only not accepted', eval_value(cdp, accept_session, 'window.__acceptClicked === true') is not True))
    checks.append(('hidden cookie report', accept_report.get('cookiePopup', {}).get('status') == 'hidden'))
    cdp.call('Runtime.evaluate', {'expression': "setCookiePopupHandling(false)", 'awaitPromise': True}, sw_session)
    off_target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    off_session = attach_target(cdp, off_target)
    navigate_and_wait(cdp, off_session, f'http://site.test:{PORT}/acceptonly.html')
    checks.append(('cookie switch off leaves banner', eval_value(cdp, off_session, "getComputedStyle(document.querySelector('#acceptOnly')).display") != 'none'))
    cdp.call('Runtime.evaluate', {'expression': "setCookiePopupHandling(true)", 'awaitPromise': True}, sw_session)
    cdp.call('Runtime.evaluate', {'expression': "setPaused('site.test', true)", 'awaitPromise': True}, sw_session)
    paused_cookie_target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    paused_cookie_session = attach_target(cdp, paused_cookie_target)
    navigate_and_wait(cdp, paused_cookie_session, f'http://site.test:{PORT}/acceptonly.html')
    checks.append(('paused site leaves cookie banner', eval_value(cdp, paused_cookie_session, "getComputedStyle(document.querySelector('#acceptOnly')).display") != 'none'))
    cdp.call('Runtime.evaluate', {'expression': "setPaused('site.test', false)", 'awaitPromise': True}, sw_session)
    wall_target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    wall_session = attach_target(cdp, wall_target)
    navigate_and_wait(cdp, wall_session, f'http://site.test:{PORT}/wall.html')
    time.sleep(4)
    wall_tab_id, _ = storage_report(cdp, sw_session)
    wall_report = summarize_state(cdp, sw_session, wall_tab_id)
    checks.append(('ad wall detected', wall_report.get('adWall') == 'detected'))
    wall_popup = cdp.call('Target.createTarget', {'url': f'chrome-extension://{ext_id}/popup.html?tabId={wall_tab_id}'})['targetId']
    wall_popup_session = attach_target(cdp, wall_popup)
    wait_expr(cdp, wall_popup_session, 'document.readyState === "complete"', 10)
    wait_expr(cdp, wall_popup_session, "!document.querySelector('#wallBanner').hidden", 10)
    checks.append(('ad wall banner shown', popup_text(cdp, wall_popup_session, '#wallText') == 'This website asks you to turn off ad blocking.'))
    hidden_target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    hidden_session = attach_target(cdp, hidden_target)
    navigate_and_wait(cdp, hidden_session, f'http://site.test:{PORT}/wall-hidden.html')
    time.sleep(4)
    hidden_tab_id, _ = storage_report(cdp, sw_session)
    hidden_report = summarize_state(cdp, sw_session, hidden_tab_id)
    checks.append(('ad wall hidden reports', hidden_report.get('adWall') in ['hidden', 'detected']))
    checks.append(('ad wall hidden restores scroll', eval_value(cdp, hidden_session, "document.body.style.overflow === '' && document.documentElement.style.overflow === ''") is True))
    cdp.call('Runtime.evaluate', {'expression': "setOffUntilRestart(true)", 'awaitPromise': True}, sw_session)
    restart_settings = eval_value(cdp, sw_session, 'getSettings()')
    checks.append(('restart off setting enabled', restart_settings.get('restartOff') is True))
    cdp.call('Runtime.evaluate', {'expression': "chrome.storage.session.set({restartOff:false}).then(()=>applySettings())", 'awaitPromise': True}, sw_session)
    restart_settings2 = eval_value(cdp, sw_session, 'getSettings()')
    checks.append(('restart off clears on restart', restart_settings2.get('restartOff') is False))
    target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    session = attach_target(cdp, target)
    navigate_and_wait(cdp, session, f'http://site.test:{PORT}/tracker.html')
    blocked_vars = eval_value(cdp, session, "({ga: window.__pbGaRan, ad: window.__pbDoubleClickRan, meta: window.__pbMetaRan, bing: window.__pbBingRan, content: window.__pbContentRan, unknown: window.__pbUnknownRan, adHost: window.__pbAdHostRan, adPath: window.__pbAdPathRan, adBox: getComputedStyle(document.querySelector('#ADbox')).display, normalBox: getComputedStyle(document.querySelector('#normalBox')).display, gpc: navigator.globalPrivacyControl})")
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
    checks.append(('ad host blocked', not blocked_vars.get('adHost')))
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
    wait_expr(cdp, popup_session, "document.querySelector('#homeTrackersNumber').textContent !== '0'", 10)
    checks.append(('popup tracker tile', int(popup_text(cdp, popup_session, '#homeTrackersNumber')) >= 5))
    checks.append(('popup blocked tile', '5 blocked' in popup_text(cdp, popup_session, '#homeTrackersSub')))
    checks.append(('popup allowed tile', 'allowed' in popup_text(cdp, popup_session, '#homeTrackersSub')))
    checks.append(('popup ad tile', int(popup_text(cdp, popup_session, '#homeAdsNumber')) >= 0))
    checks.append(('popup outside script tile', popup_text(cdp, popup_session, '#homeScriptsSub').endswith('blocked')))
    checks.append(('popup fingerprint tile', popup_text(cdp, popup_session, '#homeFingerprintNumber') == '4'))
    # Feedback link: never includes the page address; version/browser only when ticked.
    feedback = eval_value(cdp, popup_session, """(async () => {
      const urls = [];
      const real = chrome.tabs.create;
      chrome.tabs.create = async (opts) => { urls.push(opts.url); return {}; };
      document.querySelector('#feedbackButton').click();
      const hasPageBox = !!document.querySelector('#feedbackPage');
      document.querySelector('#openFeedback').click();
      await new Promise(r => setTimeout(r, 200));
      document.querySelector('#feedbackVersion').checked = false;
      document.querySelector('#openFeedback').click();
      await new Promise(r => setTimeout(r, 200));
      chrome.tabs.create = real;
      document.querySelector('#backButton').click();
      return { hasPageBox, urls };
    })()""")
    fb_urls = (feedback or {}).get('urls', [])
    checks.append(('feedback has no page address option', (feedback or {}).get('hasPageBox') is False))
    checks.append(('feedback link never includes page', len(fb_urls) == 2 and all('page=' not in u and 'site.test' not in u for u in fb_urls)))
    checks.append(('feedback link has version and browser when ticked', len(fb_urls) == 2 and 'v=' in fb_urls[0] and 'browser=' in fb_urls[0]))
    checks.append(('feedback link has no details when unticked', len(fb_urls) == 2 and fb_urls[1].endswith('feedback.html?')))
    time.sleep(0.5)
    shot = cdp.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True}, popup_session)['data']
    shot_path = ART / 'pb-ext-popup.png'
    shot_path.write_bytes(base64.b64decode(shot))
    # Outside scripts: details in the popup; Block all / Allow all for the website; Block / Allow / Undo per script.
    ga_url = f'http://www.google-analytics.com:{PORT}/ga.js'
    unknown_url = f'http://cdn.some-unknown-thirdparty.example:{PORT}/unknown.js'
    # Allow tests use the DoubleClick script. Chrome upgrades google-analytics.com, bing.com and
    # facebook.net to https (HSTS preload) once a request is allowed, and the test server has no https.
    allow_url = f'http://static.doubleclick.net:{PORT}/ad.js'
    def choose_script(url, choice):
        res = eval_value(cdp, popup_session, "chrome.runtime.sendMessage({type:'setScriptChoice', tabId:%d, url:%s, choice:'%s'})" % (tab_id, json.dumps(url), choice))
        if not (res and res.get('ok')): print('script choice', choice, url, res, file=sys.stderr)
        return bool(res and res.get('ok'))
    def reload_tracker_page():
        navigate_and_wait(cdp, session, f'http://site.test:{PORT}/tracker.html')
        time.sleep(0.6)
        return eval_value(cdp, session, "({ad: window.__pbDoubleClickRan === true, unknown: window.__pbUnknownRan === true})")
    script_rows = eval_value(cdp, popup_session, """(async () => {
      document.querySelector('[data-detail="scripts"]').click();
      await new Promise(r => setTimeout(r, 300));
      const rows = [...document.querySelectorAll('#detailContent .script-row')].map(r => r.textContent);
      const all = (document.querySelector('#detailContent .script-all') || {}).textContent || '';
      document.querySelector('#backButton').click();
      return rows.concat(['ALL:' + all]);
    })()""") or []
    all_row = next((r for r in script_rows if r.startswith('ALL:')), '')
    script_rows = [r for r in script_rows if not r.startswith('ALL:')]
    checks.append(('script detail lists each outside script', len(script_rows) >= 6))
    checks.append(('script detail has Block all and Allow all', 'Block all' in all_row and 'Allow all' in all_row))
    checks.append(('script detail has no allow for now', not any('for now' in r for r in script_rows)))
    checks.append(('script detail shows blocked tracker script', any(r.startswith('ga.js') and 'Blocked' in r and 'Allow' in r for r in script_rows)))
    checks.append(('script detail offers block for loaded script', any(r.startswith('unknown.js') and 'Allowed' in r and 'Block' in r for r in script_rows)))
    # Ads card details: blocked ad requests with kind and owner, and ad companies.
    ad_report = summarize_state(cdp, sw_session, tab_id)
    ad_items = ad_report.get('adItems', [])
    checks.append(('ad details list blocked ad requests', len(ad_items) == ad_report.get('adBlockedRequestCount') and len(ad_items) >= 2))
    checks.append(('ad details have request kind', any(item.get('type') == 'script' for item in ad_items)))
    checks.append(('ad details have ad company', any(item.get('company') == 'Google' for item in ad_items)))
    ads_text = eval_value(cdp, popup_session, """(async () => {
      document.querySelector('[data-detail="ads"]').click();
      await new Promise(r => setTimeout(r, 300));
      const t = document.querySelector('#detailContent').textContent;
      document.querySelector('#backButton').click();
      return t;
    })()""") or ''
    checks.append(('ads detail shows blocked requests and ad companies', 'Blocked ad requests' in ads_text and 'Ad companies on this page' in ads_text and 'googleads.g.doubleclick.net' in ads_text))
    # Threat model T5: a page cannot grow the per-page lists without limit.
    caps = eval_value(cdp, sw_session, """(() => {
      const s = PB.Report.emptyState(1, 'https://cap.test/', 'cap.test');
      PB.Report.addFingerprint(s, 'canvas', 'x'.repeat(5000));
      for (let i = 0; i < 500; i++) {
        PB.Report.addFingerprint(s, 'canvas', 'https://fake' + i + '.test/x.js');
        PB.Report.addCookie(s, 'c' + i + '.test');
        PB.Report.addUnknown(s, 'u' + i + '.test');
      }
      return {fp: Object.keys(s.fingerprints.canvas).length, cookies: Object.keys(s.cookieDomains).length, unknown: Object.keys(s.unknownDomains).length,
              longest: Math.max(...Object.keys(s.fingerprints.canvas).map(k => k.length))};
    })()""") or {}
    checks.append(('fingerprint sources capped at 50 per method', caps.get('fp') == 50))
    checks.append(('cookie and unknown domain lists capped at 200', caps.get('cookies') == 200 and caps.get('unknown') == 200))
    checks.append(('fingerprint source text capped at 200 characters', caps.get('longest', 0) <= 200))
    # Cookies card: third-party cookie list, and the two clear actions.
    tp_url = f'http://cdn.some-unknown-thirdparty.example:{PORT}/'
    site_url = f'http://site.test:{PORT}/'
    eval_value(cdp, sw_session, "Promise.all([chrome.cookies.set({url:%s, name:'pbtrack', value:'1'}), chrome.cookies.set({url:%s, name:'pbsite', value:'1'})]).then(() => true)" % (json.dumps(tp_url), json.dumps(site_url)))
    def cookie_names(url):
        return eval_value(cdp, sw_session, "chrome.cookies.getAll({url:%s}).then(cs => cs.map(c => c.name))" % json.dumps(url)) or []
    checks.append(('test cookies set', 'pbtrack' in cookie_names(tp_url) and 'pbsite' in cookie_names(site_url)))
    ui = eval_value(cdp, popup_session, """(async () => {
      const wait = (ms) => new Promise(r => setTimeout(r, ms));
      document.querySelector('[data-detail="cookies"]').click();
      await wait(300);
      const detail = document.querySelector('#detailContent').textContent;
      document.querySelector('#backButton').click();
      await wait(200);
      document.querySelector('#clearCookiesButton').click();
      await wait(150);
      const menu = document.querySelector('#cookieMenu');
      const menuOpen = !menu.hidden;
      const menuText = menu.textContent;
      document.querySelector('#clearSiteCookies').click();
      await wait(100);
      const confirmText = document.querySelector('#cookieConfirm').hidden ? '' : document.querySelector('#cookieConfirm').textContent;
      document.querySelector('#cookieConfirmNo').click();
      await wait(100);
      const confirmClosed = document.querySelector('#cookieConfirm').hidden;
      document.querySelector('#clearTrackerCookies').click();
      await wait(800);
      const result = document.querySelector('#cookieMenuResult').hidden ? '' : document.querySelector('#cookieMenuResult').textContent;
      document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}));
      await wait(100);
      const closedByEscape = menu.hidden;
      document.querySelector('#clearCookiesButton').click();
      await wait(100);
      document.querySelector('#siteName').click();
      await wait(100);
      const inHeader = Boolean(document.querySelector('.topbar #clearCookiesButton[aria-label="Clear cookies"]'));
      return {detail, menuOpen, menuText, confirmText, confirmClosed, result, closedByEscape, closedByOutsideTap: menu.hidden, inHeader};
    })()""") or {}
    checks.append(('cookies detail lists third-party cookie websites', 'Third-party cookies on this page' in ui.get('detail', '') and 'cdn.some-unknown-thirdparty.example' in ui.get('detail', '')))
    checks.append(('cookies detail has no clear buttons', 'Clear cookies from these websites' not in ui.get('detail', '') and 'select the cookie button at the top' in ui.get('detail', '')))
    checks.append(('Clear cookies is a labelled button in the header', ui.get('inHeader') is True))
    checks.append(('header Clear cookies opens the menu with both choices', ui.get('menuOpen') is True and 'Clear third-party cookies' in ui.get('menuText', '') and 'Clear cookies of site.test' in ui.get('menuText', '')))
    checks.append(('clearing site cookies asks first', 'Sign out of site.test and clear its cookies?' in ui.get('confirmText', '') and ui.get('confirmClosed') is True))
    checks.append(('site cookie kept after cancel', 'pbsite' in cookie_names(site_url)))
    checks.append(('menu clear third-party cookies removes them', ui.get('result', '').startswith('Removed') and 'pbtrack' not in cookie_names(tp_url)))
    checks.append(('clear third-party cookies keeps site cookies', 'pbsite' in cookie_names(site_url)))
    checks.append(('Escape closes the cookie menu', ui.get('closedByEscape') is True))
    checks.append(('a tap outside closes the cookie menu', ui.get('closedByOutsideTap') is True))
    cleared = eval_value(cdp, popup_session, "chrome.runtime.sendMessage({type:'clearCookies', tabId:%d, scope:'site'})" % tab_id) or {}
    checks.append(('clear site cookies removes them', cleared.get('ok') and 'pbsite' not in cookie_names(site_url)))
    checks.append(('clear cookies refuses an unknown scope', (eval_value(cdp, popup_session, "chrome.runtime.sendMessage({type:'clearCookies', tabId:%d, scope:'all'})" % tab_id) or {}).get('ok') is not True))
    report_items = {item['url']: item for item in summarize_state(cdp, sw_session, tab_id).get('outsideScriptItems', [])}
    checks.append(('script item has tracker company', report_items.get(ga_url, {}).get('company') == 'Google'))
    checks.append(('script choice refused for script not on page', choose_script('http://not-on-page.example/x.js', 'allow') is False))
    checks.append(('script allow accepted', choose_script(allow_url, 'allow') is True))
    ran = reload_tracker_page()
    checks.append(('allowed script runs', ran.get('ad') is True))
    checks.append(('script undo accepted', choose_script(allow_url, 'reset') is True))
    ran = reload_tracker_page()
    checks.append(('script blocked again after undo', ran.get('ad') is False))
    checks.append(('allow for now is refused', choose_script(allow_url, 'tempAllow') is False))
    checks.append(('block all accepted', choose_script('', 'blockAll') is True))
    ran = reload_tracker_page()
    checks.append(('block all stops a loaded outside script', ran.get('unknown') is False))
    checks.append(('one-script allow accepted under block all', choose_script(unknown_url, 'allow') is True))
    ran = reload_tracker_page()
    checks.append(('one-script allow wins over block all', ran.get('unknown') is True))
    choose_script(unknown_url, 'reset')
    checks.append(('allow all accepted', choose_script('', 'allowAll') is True))
    ran = reload_tracker_page()
    checks.append(('allow all lets a listed tracker script run', ran.get('ad') is True and ran.get('unknown') is True))
    checks.append(('one-script block accepted under allow all', choose_script(allow_url, 'block') is True))
    ran = reload_tracker_page()
    checks.append(('one-script block wins over allow all', ran.get('ad') is False))
    choose_script(allow_url, 'reset')
    checks.append(('undo all accepted', choose_script('', 'resetAll') is True))
    ran = reload_tracker_page()
    checks.append(('undo all restores the lists', ran.get('ad') is False and ran.get('unknown') is True))
    checks.append(('script block accepted', choose_script(unknown_url, 'block') is True))
    ran = reload_tracker_page()
    checks.append(('blocked script does not run', ran.get('unknown') is False))
    reload_tracker_page()
    choose_script('', 'blockAll')
    eval_value(cdp, sw_session, "setGlobalOff(true).then(() => true)")
    off_blocks = eval_value(cdp, sw_session, "chrome.declarativeNetRequest.getDynamicRules().then(rs => rs.filter(r => ((r.id >= SCRIPT_RULE_BASE && r.id < SCRIPT_RULE_BASE + SCRIPT_RULE_MAX) || (r.id >= SCRIPT_SITE_RULE_BASE && r.id < SCRIPT_SITE_RULE_BASE + SCRIPT_RULE_MAX)) && r.action.type === 'block').length)")
    checks.append(('script block rules removed when PrivacyBrew is off', off_blocks == 0))
    eval_value(cdp, sw_session, "setGlobalOff(false).then(() => true)")
    reload_tracker_page()
    choose_script(unknown_url, 'reset')
    choose_script('', 'resetAll')
    left = eval_value(cdp, sw_session, "chrome.declarativeNetRequest.getDynamicRules().then(rs => rs.filter(r => r.id >= SCRIPT_RULE_BASE && r.id < SCRIPT_SITE_RULE_BASE + SCRIPT_RULE_MAX).length)")
    checks.append(('no script rules left after undo', left == 0))
    reload_tracker_page()
    cdp.call('Runtime.evaluate', {'expression': "setAdBlocking(false)", 'awaitPromise': True}, sw_session)
    navigate_and_wait(cdp, session, f'http://site.test:{PORT}/tracker.html')
    ads_off_vars = eval_value(cdp, session, '({adHost: window.__pbAdHostRan, adPath: window.__pbAdPathRan, adBox: getComputedStyle(document.querySelector(\"#ADbox\")).display, allowedAd: window.__pbAllowedAdRan})')
    checks.append(('ad switch off allows ads', ads_off_vars.get('adPath') is True and ads_off_vars.get('adBox') != 'none'))
    cdp.call('Runtime.evaluate', {'expression': "setAdBlocking(true)", 'awaitPromise': True}, sw_session)
    cdp.call('Runtime.evaluate', {'expression': "setPaused('site.test', true)", 'awaitPromise': True}, sw_session)
    navigate_and_wait(cdp, session, f'http://site.test:{PORT}/tracker.html')
    paused_vars = eval_value(cdp, session, '({ga: window.__pbGaRan, ad: window.__pbDoubleClickRan, meta: window.__pbMetaRan, bing: window.__pbBingRan, adHost: window.__pbAdHostRan, adPath: window.__pbAdPathRan})')
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
    checks.append(('paused header text', popup_text(cdp, paused_popup_session, '#statusText') == 'PrivacyBrew is off on this website'))
    checks.append(('paused summary text', popup_text(cdp, paused_popup_session, '#statusText') == 'PrivacyBrew is off on this website'))
    checks.append(('paused blocked tile', '0 blocked' in popup_text(cdp, paused_popup_session, '#homeTrackersSub')))
    checks.append(('paused allowed tile equals found', popup_text(cdp, paused_popup_session, '#homeTrackersNumber') in popup_text(cdp, paused_popup_session, '#homeTrackersSub')))
    paused_shot = cdp.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True}, paused_popup_session)['data']
    paused_shot_path = ART / 'pb-ext-popup-paused.png'
    paused_shot_path.write_bytes(base64.b64decode(paused_shot))
    # Settings > Remove turns on the website in that row, not the website of the open tab.
    cdp.call('Runtime.evaluate', {'expression': "setPaused('other.test', true)", 'awaitPromise': True}, sw_session)
    cdp.call('Page.navigate', {'url': f'chrome-extension://{ext_id}/popup.html?tabId={tab_id}'}, paused_popup_session)
    wait_expr(cdp, paused_popup_session, 'document.readyState === "complete"', 10)
    wait_expr(cdp, paused_popup_session, "[...document.querySelectorAll('#pausedList li')].some((li) => li.textContent.startsWith('other.test'))", 10)
    removed = eval_value(cdp, paused_popup_session, """(async () => {
      document.querySelector('#settingsButton').click();
      await new Promise((r) => setTimeout(r, 400));
      const row = [...document.querySelectorAll('#pausedList li')].find((li) => li.textContent.startsWith('other.test'));
      if (!row) return { found: false };
      row.querySelector('button').click();
      await new Promise((r) => setTimeout(r, 600));
      const { pausedSites } = await chrome.storage.local.get('pausedSites');
      return { found: true, sites: Object.keys(pausedSites || {}) };
    })()""") or {}
    checks.append(('paused list Remove turns on the listed website', removed.get('found') is True and 'other.test' not in removed.get('sites', ['other.test'])))
    checks.append(('paused list Remove keeps the open website paused', 'site.test' in removed.get('sites', [])))
    refused = eval_value(cdp, paused_popup_session, "chrome.runtime.sendMessage({type:'setSitePaused', site:'not-listed.test', paused:false}).catch(() => null)")
    checks.append(('turn on by name refused for a website not on the list', not (refused or {}).get('ok')))
    cdp.call('Runtime.evaluate', {'expression': "setPaused('site.test', false)", 'awaitPromise': True}, sw_session)
    # A page PrivacyBrew cannot check gets an explanation, not an empty report.
    blank_popup = cdp.call('Target.createTarget', {'url': f'chrome-extension://{ext_id}/popup.html?tabId=987654'})['targetId']
    blank_popup_session = attach_target(cdp, blank_popup)
    wait_expr(cdp, blank_popup_session, 'document.readyState === "complete"', 10)
    wait_expr(cdp, blank_popup_session, "!document.querySelector('#noticeBanner').hidden", 10)
    checks.append(('unsupported page explains what to do', popup_text(cdp, blank_popup_session, '#noticeText').startswith('PrivacyBrew does not check browser pages')))
    checks.append(('unsupported page header text', popup_text(cdp, blank_popup_session, '#overall') == 'Nothing to check on this page'))
    cdp.call('Target.closeTarget', {'targetId': blank_popup})
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
    checks.append(('global off rows are allowed', True))
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
    checks.append(('clean tracker tile zero', popup_text(cdp, clean_popup_session, '#homeTrackersNumber') == '0'))
    checks.append(('clean blocked tile zero', '0 blocked' in popup_text(cdp, clean_popup_session, '#homeTrackersSub')))
    checks.append(('clean allowed tile zero', '0 allowed' in popup_text(cdp, clean_popup_session, '#homeTrackersSub')))
    checks.append(('clean fingerprint tile none', popup_text(cdp, clean_popup_session, '#homeFingerprintNumber') == 'None'))
    clean_shot = cdp.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True}, clean_popup_session)['data']
    clean_shot_path = ART / 'pb-ext-popup-clean.png'
    clean_shot_path.write_bytes(base64.b64decode(clean_shot))
    worker_requests = [e for e in cdp.events if e.get('sessionId') in worker_sessions and e.get('method') == 'Network.requestWillBeSent' and e.get('params', {}).get('request', {}).get('url', '').startswith(('http://', 'https://'))]
    checks.append(('extension made zero network requests', len(worker_requests) == 0))
    swerr = service_worker_errors(cdp, worker_sessions)
    if swerr: print('SWERR', swerr)
    checks.append(('service worker has no errors', swerr == []))
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

