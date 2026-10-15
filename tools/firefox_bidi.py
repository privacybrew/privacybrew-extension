#!/usr/bin/env python3
"""Safe headless Firefox launcher and a small WebDriver BiDi client.

Safety rules (a graphics stack freeze was seen with GPU-accelerated Firefox):
- headless by default, software rendering, no GPU acceleration;
- one Firefox at a time, started in its own process group;
- hard time limit, and the whole process group is killed in close().
"""
import base64, contextlib, json, os, re, shutil, signal, subprocess, threading, time
from pathlib import Path
import websocket

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts'
GECKO_ID = 'privacybrew@privacybrew.app'
EXT_UUID = '6f1c2a4e-8b3d-4e5f-9a7c-1d2e3f4a5b6c'
POPUP_ORIGIN = f'moz-extension://{EXT_UUID}'

GRAPHICS_PREFS = {
    'gfx.webrender.software': True,
    'layers.acceleration.disabled': True,
    'media.hardware-video-decoding.enabled': False,
    'gfx.canvas.accelerated': False,
    'webgl.force-enabled': False,
}
SAFE_ENV = {'MOZ_HEADLESS': '1', 'LIBGL_ALWAYS_SOFTWARE': '1', 'MOZ_WEBRENDER': '0'}


def base_prefs(hosts):
    prefs = dict(GRAPHICS_PREFS)
    prefs.update({
        'extensions.webextensions.uuids': json.dumps({GECKO_ID: EXT_UUID}),
        'extensions.autoDisableScopes': 0,
        'privacy.trackingprotection.enabled': False,
        'privacy.trackingprotection.pbmode.enabled': False,
        'privacy.trackingprotection.socialtracking.enabled': False,
        'privacy.trackingprotection.cryptomining.enabled': False,
        'privacy.trackingprotection.fingerprinting.enabled': False,
        'browser.contentblocking.category': 'custom',
        'network.cookie.cookieBehavior': 0,
        'cookiebanners.service.mode': 0,
        'cookiebanners.service.mode.privateBrowsing': 0,
        'toolkit.telemetry.enabled': False,
        'toolkit.telemetry.unified': False,
        'toolkit.telemetry.archive.enabled': False,
        'datareporting.policy.dataSubmissionEnabled': False,
        'datareporting.healthreport.uploadEnabled': False,
        'app.update.enabled': False,
        'app.update.auto': False,
        'browser.shell.checkDefaultBrowser': False,
        'browser.startup.homepage_override.mstone': 'ignore',
        'browser.aboutwelcome.enabled': False,
        'browser.newtabpage.enabled': False,
        'browser.startup.page': 0,
        'network.dns.localDomains': ','.join(hosts),
        'network.proxy.type': 0,
        'network.captive-portal-service.enabled': False,
        'network.connectivity-service.enabled': False,
        'browser.safebrowsing.malware.enabled': False,
        'browser.safebrowsing.phishing.enabled': False,
        'browser.safebrowsing.downloads.enabled': False,
        'browser.safebrowsing.update.enabled': False,
        'extensions.getAddons.cache.enabled': False,
        'extensions.update.enabled': False,
        'extensions.systemAddon.update.enabled': False,
        'services.settings.server': 'http://127.0.0.1:9/',
        'browser.region.network.url': '',
        'browser.region.update.enabled': False,
        'dom.security.https_first': False,
        'dom.security.https_first_pbm': False,
        'network.stricttransportsecurity.preloadlist': False,
        'browser.tabs.warnOnClose': False,
        'remote.prefs.recommended': True,
        # Extension page and content console messages go to stdout, so tests can find errors.
        'devtools.console.stdout.content': True,
        'devtools.console.stdout.chrome': True,
    })
    return prefs


def own_running_firefox():
    """PIDs of Firefox processes that use a profile under artifacts/ (test browsers)."""
    out = subprocess.run(['pgrep', '-f', 'firefox.*artifacts'], capture_output=True, text=True).stdout.split()
    pids = []
    for pid in out:
        with contextlib.suppress(Exception):
            argv = (Path('/proc') / pid / 'cmdline').read_bytes().split(b'\0')
            if b'firefox' in Path(argv[0].decode()).name.encode() and any(b'artifacts' in a for a in argv):
                pids.append(int(pid))
    return pids


class BiDiError(RuntimeError):
    pass


class Firefox:
    def __init__(self, name, hosts, headed=False, time_limit=600, extra_prefs=None, window=(1280, 900), extra_args=()):
        if own_running_firefox():
            raise SystemExit('A test Firefox (firefox.*artifacts) already runs. Stop it first.')
        self.profile = ART / f'firefox-{name}'
        shutil.rmtree(self.profile, ignore_errors=True)
        self.profile.mkdir(parents=True)
        prefs = base_prefs(hosts)
        prefs['remote.experimental.enabled'] = True
        prefs.update(extra_prefs or {})
        (self.profile / 'user.js').write_text(''.join(f'user_pref({json.dumps(k)}, {json.dumps(v)});\n' for k, v in prefs.items()))
        env = dict(os.environ)
        env.update(SAFE_ENV)
        # --remote-allow-system-access lets BiDi run code in the browser window (chrome scope).
        # BiDi cannot navigate a tab to moz-extension:// URLs, so the browser window opens them.
        args = ['firefox', '--no-remote', '--remote-allow-system-access', '--remote-debugging-port=0', '--profile', str(self.profile),
                f'--width={window[0]}', f'--height={window[1]}', *extra_args]
        if headed:
            env.pop('MOZ_HEADLESS', None)
        else:
            args.insert(1, '--headless')
        self.lines = []
        self.closed = False
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace',
                                     env=env, start_new_session=True)
        threading.Thread(target=self._read, daemon=True).start()
        self.deadline = time.time() + time_limit
        self.watchdog = threading.Thread(target=self._watch, daemon=True)
        self.watchdog.start()
        self.ws = None
        self.next_id = 1
        self.events = []
        try:
            url = self._wait_ws(60)
            self.ws = websocket.create_connection(url + '/session', timeout=60, suppress_origin=True)
            self.call('session.new', {'capabilities': {'alwaysMatch': {'acceptInsecureCerts': True}}})
        except Exception:
            self.close()
            raise

    def _read(self):
        for line in self.proc.stdout:
            self.lines.append(line.rstrip('\n'))

    def _watch(self):
        while not self.closed:
            if time.time() > self.deadline:
                print('FIREFOX TIME LIMIT REACHED: killing Firefox')
                self.kill()
                return
            time.sleep(1)

    def _wait_ws(self, timeout):
        end = time.time() + timeout
        while time.time() < end:
            for line in list(self.lines):
                m = re.search(r'WebDriver BiDi listening on (ws://\S+)', line)
                if m:
                    return m.group(1)
            if self.proc.poll() is not None:
                break
            time.sleep(0.2)
        raise RuntimeError('Firefox did not print the BiDi URL. Output:\n' + '\n'.join(self.lines[-30:]))

    def call(self, method, params=None, timeout=60):
        msg_id = self.next_id
        self.next_id += 1
        self.ws.settimeout(timeout)
        self.ws.send(json.dumps({'id': msg_id, 'method': method, 'params': params or {}}))
        while True:
            data = json.loads(self.ws.recv())
            if data.get('id') == msg_id:
                if data.get('type') == 'error' or 'error' in data:
                    raise BiDiError(f'{method}: {data.get("error")}: {data.get("message")}')
                return data.get('result', {})
            self.events.append(data)

    # Helpers
    def install(self, path):
        return self.call('webExtension.install', {'extensionData': {'type': 'path', 'path': str(Path(path).resolve())}})['extension']

    def new_tab(self, url=None):
        ctx = self.call('browsingContext.create', {'type': 'tab'})['context']
        if url:
            self.navigate(ctx, url)
        return ctx

    def chrome_context(self):
        return self.call('browsingContext.getTree', {'moz:scope': 'chrome', 'maxDepth': 0})['contexts'][0]['context']

    def content_contexts(self):
        return {c['context']: c['url'] for c in self.call('browsingContext.getTree', {'maxDepth': 0})['contexts']}

    def open_extension_tab(self, url, select=True, timeout=20):
        """Open a moz-extension:// page in a new tab and return its BiDi context.

        With select=False the tab opens in the background, so the active tab stays the same.
        """
        before = set(self.content_contexts())
        code = ('(() => { const t = gBrowser.addTab(' + json.dumps(url) +
                ', {triggeringPrincipal: Services.scriptSecurityManager.getSystemPrincipal()});' +
                (' gBrowser.selectedTab = t;' if select else '') + ' return true; })()')
        self.eval(self.chrome_context(), code)
        end = time.time() + timeout
        while time.time() < end:
            for ctx, cur in self.content_contexts().items():
                if ctx not in before and cur.startswith('moz-extension://'):
                    self.wait(ctx, 'document.readyState === "complete"', timeout)
                    return ctx
            time.sleep(0.2)
        raise RuntimeError('Extension tab did not open: ' + url)

    def activate(self, ctx):
        try:
            self.call('browsingContext.activate', {'context': ctx})
        except BiDiError as e:
            if 'privileged' not in str(e):
                raise
            self._select_privileged_tab(ctx)

    def _select_privileged_tab(self, ctx):
        # BiDi cannot activate extension tabs. Mark the tab title, then select it from the browser window.
        marker = f'pb-select-{time.time_ns()}'
        old = self.eval(ctx, f'(() => {{ const t = document.title; document.title = {json.dumps(marker)}; return t; }})()')
        try:
            self.wait(self.chrome_context(), '(() => { const t = gBrowser.tabs.find((x) => x.linkedBrowser.contentTitle === ' +
                      json.dumps(marker) + '); if (t) gBrowser.selectedTab = t; return Boolean(t); })()', 10)
        finally:
            self.eval(ctx, f'document.title = {json.dumps(old)}; true')

    def close_tab(self, ctx):
        with contextlib.suppress(Exception):
            self.call('browsingContext.close', {'context': ctx})

    def navigate(self, ctx, url, wait='complete'):
        return self.call('browsingContext.navigate', {'context': ctx, 'url': url, 'wait': wait})

    def set_viewport(self, ctx, width, height):
        self.call('browsingContext.setViewport', {'context': ctx, 'viewport': {'width': width, 'height': height}})

    def screenshot(self, ctx, path, clip=None, scale=1):
        params = {'context': ctx}
        if clip:
            params['clip'] = {'type': 'box', 'x': clip[0], 'y': clip[1], 'width': clip[2], 'height': clip[3]}
        try:
            data = self.call('browsingContext.captureScreenshot', params)['data']
        except BiDiError as e:
            if 'privileged' not in str(e):
                raise
            # Extension tab: select it and draw a snapshot from the browser window.
            self._select_privileged_tab(ctx)
            x, y, w, h = clip or (0, 0, 1280, 900)
            url = self.eval(self.chrome_context(), f'''(async () => {{
              const wg = gBrowser.selectedBrowser.browsingContext.currentWindowGlobal;
              const bmp = await wg.drawSnapshot(new DOMRect({x}, {y}, {w}, {h}), {scale}, 'white');
              const c = document.createElementNS('http://www.w3.org/1999/xhtml', 'canvas');
              c.width = bmp.width; c.height = bmp.height;
              c.getContext('2d').drawImage(bmp, 0, 0);
              return c.toDataURL('image/png');
            }})()''')
            data = url.split(',', 1)[1]
        Path(path).write_bytes(base64.b64decode(data))

    def eval(self, ctx, expr, timeout=60):
        res = self.call('script.evaluate', {'expression': expr, 'target': {'context': ctx}, 'awaitPromise': True,
                                            'resultOwnership': 'none'}, timeout)
        if res.get('type') == 'exception':
            details = res.get('exceptionDetails', {})
            raise BiDiError('script error: ' + str(details.get('text')) + ' in ' + expr[:200])
        return from_remote(res.get('result'))

    def evalj(self, ctx, expr, timeout=60):
        """Evaluate an expression (may be a promise) and return it through JSON."""
        text = self.eval(ctx, f'(async () => JSON.stringify(await ({expr})))()', timeout)
        return None if text is None else json.loads(text)

    def wait(self, ctx, expr, timeout=15):
        end = time.time() + timeout
        last = None
        while time.time() < end:
            with contextlib.suppress(BiDiError):
                last = self.eval(ctx, expr)
                if last:
                    return last
            time.sleep(0.2)
        raise RuntimeError(f'Timed out waiting for: {expr} last={last}')

    def kill(self):
        with contextlib.suppress(Exception):
            os.killpg(self.proc.pid, signal.SIGTERM)
        try:
            self.proc.wait(timeout=10)
        except Exception:
            with contextlib.suppress(Exception):
                os.killpg(self.proc.pid, signal.SIGKILL)
            with contextlib.suppress(Exception):
                self.proc.wait(timeout=10)

    def close(self, keep_profile=False):
        if self.ws:
            with contextlib.suppress(Exception):
                self.ws.settimeout(10)
                self.call('browser.close', timeout=10)
            with contextlib.suppress(Exception):
                self.ws.close()
        try:
            self.proc.wait(timeout=15)
        except Exception:
            pass
        # Kill any child still in the group (content processes), then the group itself.
        self.kill()
        self.closed = True
        if not keep_profile:
            shutil.rmtree(self.profile, ignore_errors=True)


def from_remote(v):
    """Convert a BiDi RemoteValue to a Python value."""
    if v is None:
        return None
    t = v.get('type')
    if t in ('undefined', 'null'):
        return None
    if t in ('string', 'boolean'):
        return v.get('value')
    if t == 'number':
        val = v.get('value')
        if isinstance(val, str):
            return {'NaN': float('nan'), 'Infinity': float('inf'), '-Infinity': float('-inf'), '-0': 0}.get(val, val)
        return val
    if t == 'bigint':
        return int(v.get('value'))
    if t == 'array' or t == 'set':
        return [from_remote(x) for x in v.get('value', [])]
    if t in ('object', 'map'):
        out = {}
        for k, val in v.get('value', []):
            key = k if isinstance(k, str) else from_remote(k)
            out[key] = from_remote(val)
        return out
    return v.get('value', {'__type__': t})
