#!/usr/bin/env python3
import base64, contextlib, http.server, json, os, shutil, socket, subprocess, sys, threading, time, urllib.request
from pathlib import Path
from urllib.parse import urlparse
import websocket

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / 'extension'
ART = ROOT / 'artifacts'
PORT = 8765
HOSTS = ['site.test', 'clean.test', 'www.google-analytics.com', 'static.doubleclick.net', 'connect.facebook.net', 'bat.bing.com', 'cdn.some-unknown-thirdparty.example']

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
<h1>Tracker page</h1>'''
            return self.end(body)
        if host == 'clean.test' and path in ['/', '/clean.html']:
            return self.end('<!doctype html><title>Clean page</title><h1>Clean page</h1>')
        if path.endswith('.js'):
            headers = {}
            if host == 'static.doubleclick.net':
                headers['Set-Cookie'] = 'pbtest=1; SameSite=None'
            if host == 'cdn.some-unknown-thirdparty.example':
                body = 'window.unknownLoaded = true;'
            else:
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
    time.sleep(1.5)

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

def run_unit(cdp):
    target = cdp.call('Target.createTarget', {'url': f'http://site.test:{PORT}/unit/'})['targetId']
    session = attach_target(cdp, target)
    wait_expr(cdp, session, 'window.__TEST_DONE__ || null', 15)
    result = cdp.call('Runtime.evaluate', {'expression': 'window.__TEST_DONE__', 'returnByValue': True}, session)['result']['value']
    return result

def run_e2e(cdp):
    ext_id, sw_target = find_extension(cdp)
    sw_session = attach_target(cdp, sw_target)
    cdp.call('Network.enable', sessionId=sw_session)
    target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    session = attach_target(cdp, target)
    navigate_and_wait(cdp, session, f'http://site.test:{PORT}/tracker.html')
    tab_id, state = storage_report(cdp, sw_session)
    tracker_companies = sorted(v['company'] for v in state.get('trackers', {}).values())
    fps = sorted(state.get('fingerprints', {}).keys())
    badge = cdp.call('Runtime.evaluate', {'expression': f'new Promise(r => chrome.action.getBadgeText({{tabId:{tab_id}}}, r))', 'awaitPromise': True, 'returnByValue': True}, sw_session)['result']['value']
    checks = []
    checks.append(('tracker company count', len(tracker_companies) >= 3))
    checks.append(('Google detected', 'Google' in tracker_companies))
    checks.append(('third party cookie', 'doubleclick.net' in state.get('cookieDomains', {})))
    checks.append(('unknown domain', 'some-unknown-thirdparty.example' in state.get('unknownDomains', {})))
    for technique in ['canvas', 'webgl', 'audio', 'fonts']:
        checks.append((f'{technique} fingerprint', technique in fps))
    checks.append(('badge text', badge == str(len(state.get('trackers', {})))))
    popup = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    popup_session = attach_target(cdp, popup)
    cdp.call('Page.enable', sessionId=popup_session)
    cdp.call('Emulation.setDeviceMetricsOverride', {'width': 360, 'height': 760, 'deviceScaleFactor': 1, 'mobile': False}, popup_session)
    cdp.call('Page.navigate', {'url': f'chrome-extension://{ext_id}/popup.html?tabId={tab_id}'}, popup_session)
    wait_expr(cdp, popup_session, 'document.readyState === "complete"', 10)
    time.sleep(0.5)
    shot = cdp.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True}, popup_session)['data']
    shot_path = ART / 'pb-ext-popup.png'
    shot_path.write_bytes(base64.b64decode(shot))
    navigate_and_wait(cdp, session, f'http://clean.test:{PORT}/clean.html')
    _, clean_state = storage_report(cdp, sw_session)
    checks.append(('reset on clean navigation', len(clean_state.get('trackers', {})) == 0 and len(clean_state.get('unknownDomains', {})) == 0))
    worker_requests = [e for e in cdp.events if e.get('sessionId') == sw_session and e.get('method') == 'Network.requestWillBeSent' and e.get('params', {}).get('request', {}).get('url', '').startswith(('http://', 'https://'))]
    checks.append(('extension made zero network requests', len(worker_requests) == 0))
    fail = [name for name, ok in checks if not ok]
    return {'pass': len(checks) - len(fail), 'fail': len(fail), 'checks': checks, 'method': 'load-extension fallback', 'screenshot': str(shot_path)}

def main():
    ART.mkdir(exist_ok=True)
    server = start_server()
    proc = None
    try:
        pipe_ok, pipe_msg = try_pipe_load()
        proc, cdp = connect_fallback()
        unit = run_unit(cdp)
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
