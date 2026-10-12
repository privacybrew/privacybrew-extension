#!/usr/bin/env python3
import base64, contextlib, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
from urllib.parse import urlparse
import websocket

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / 'extension'
OUT = ROOT / 'artifacts' / 'pb-realtest'
DOCS = ROOT / 'docs'
WINDOW = '1280,900'
NORMAL_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.8037.97 Safari/537.36'
UA_METADATA = {
  'brands': [{'brand': 'Chromium', 'version': '154'}, {'brand': 'Google Chrome', 'version': '154'}, {'brand': 'Not=A?Brand', 'version': '24'}],
  'fullVersionList': [{'brand': 'Chromium', 'version': '154.0.8037.97'}, {'brand': 'Google Chrome', 'version': '154.0.8037.97'}, {'brand': 'Not=A?Brand', 'version': '24.0.0.0'}],
  'fullVersion': '154.0.8037.97',
  'platform': 'Linux',
  'platformVersion': '6.0.0',
  'architecture': 'x86',
  'model': '',
  'mobile': False
}
BLOCK_TEXT = ['access denied', 'unknown error', 'something went wrong', 'err_', "this site can't be reached", 'captcha', 'are you a robot', 'verify you are human']
MAX_WAIT = 25
IDLE_WAIT = 6
HEADLESS = '--headed' not in sys.argv
SLOW = '--slow' in sys.argv
if not HEADLESS and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
    raise SystemExit('--headed needs DISPLAY or WAYLAND_DISPLAY')

SITES = [
  ('news','cnn.com'),('news','bbc.com'),('news','nytimes.com'),('news','theguardian.com'),('news','foxnews.com'),('news','washingtonpost.com'),('news','reuters.com'),
  ('shopping','amazon.com'),('shopping','ebay.com'),('shopping','walmart.com'),('shopping','target.com'),('shopping','bestbuy.com'),('shopping','etsy.com'),('shopping','ikea.com'),
  ('video_music','youtube.com'),('video_music','twitch.tv'),('video_music','vimeo.com'),('video_music','spotify.com'),('video_music','imdb.com'),
  ('finance','chase.com'),('finance','bankofamerica.com'),('finance','paypal.com'),('finance','wellsfargo.com'),
  ('travel_maps','booking.com'),('travel_maps','expedia.com'),('travel_maps','airbnb.com'),('travel_maps','google.com/maps'),
  ('social_forums','reddit.com'),('social_forums','x.com'),('social_forums','linkedin.com'),('social_forums','pinterest.com'),('social_forums','quora.com'),('social_forums','stackoverflow.com'),('social_forums','medium.com'),
  ('lifestyle','allrecipes.com'),('lifestyle','weather.com'),('lifestyle','accuweather.com'),('lifestyle','webmd.com'),
  ('gov_edu','usa.gov'),('gov_edu','irs.gov'),('gov_edu','wikipedia.org'),
  ('tech','github.com'),('tech','apple.com'),('tech','microsoft.com'),('tech','cnet.com'),('tech','theverge.com'),
  ('heavy_ads','dailymail.co.uk'),('heavy_ads','forbes.com'),('heavy_ads','buzzfeed.com'),('heavy_ads','msn.com')
]

class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=20)
        self.next_id = 1
        self.events = []
    def call(self, method, params=None, sessionId=None):
        msg = {'id': self.next_id, 'method': method}
        self.next_id += 1
        if params is not None: msg['params'] = params
        if sessionId: msg['sessionId'] = sessionId
        self.ws.send(json.dumps(msg))
        while True:
            data = json.loads(self.ws.recv())
            if data.get('id') == msg['id']:
                if 'error' in data:
                    raise RuntimeError(f'{method}: {data["error"]}')
                return data.get('result', {})
            self.events.append(data)
    def close(self):
        with contextlib.suppress(Exception): self.ws.close()

def slug(site):
    return re.sub(r'[^a-z0-9]+', '-', site.lower()).strip('-')

def wait_devtools(proc, timeout=20):
    deadline = time.time() + timeout
    text = ''
    while time.time() < deadline:
        line = proc.stderr.readline()
        if line:
            text += line
            if 'DevTools listening on ' in line:
                return line.strip().split('DevTools listening on ', 1)[1]
    raise RuntimeError('Chrome DevTools URL not found: ' + text[-1000:])

def launch(name, extension=False):
    profile = OUT / f'profile-{name}'
    if profile.exists(): shutil.rmtree(profile)
    profile.mkdir(parents=True, exist_ok=True)
    args = [
      'google-chrome',*(['--headless=new'] if HEADLESS else []),'--no-first-run','--no-default-browser-check',
      f'--user-data-dir={profile}','--remote-debugging-port=0','--remote-allow-origins=*',
      '--disable-sync','--disable-background-networking','--disable-component-update',
      f'--window-size={WINDOW}', f'--user-agent={NORMAL_UA}'
    ]
    if extension:
        args += ['--enable-unsafe-extension-debugging']
    args += ['about:blank']
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    cdp = CDP(wait_devtools(proc))
    ext_id = None
    sw_session = None
    worker_sessions = []
    if extension:
        ext_id = cdp.call('Extensions.loadUnpacked', {'path': str(EXT)})['id']
        ext_id, sw_target = find_extension(cdp)
        sw_session = attach(cdp, sw_target)
        worker_sessions.append(sw_session)
        cdp.call('Runtime.enable', sessionId=sw_session)
    return proc, cdp, ext_id, sw_session, worker_sessions, profile

def attach(cdp, target_id):
    return cdp.call('Target.attachToTarget', {'targetId': target_id, 'flatten': True})['sessionId']

def find_extension(cdp, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for t in cdp.call('Target.getTargets')['targetInfos']:
            if t.get('type') == 'service_worker' and t.get('url','').endswith('/background.js'):
                return t['url'].split('/')[2], t['targetId']
        time.sleep(0.2)
    raise RuntimeError('extension worker not found')

def eval_value(cdp, session, expr, timeout=10):
    return cdp.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True, 'timeout': timeout * 1000}, session).get('result', {}).get('value')

def set_blocking(cdp, sw_session, enabled):
    expr = f"setGlobalBlocking({str(enabled).lower()})"
    cdp.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True}, sw_session)

def summarize_report(cdp, sw_session, tab_id):
    expr = f"(async()=>{{const s=await getState({tab_id});const set=await getSettings();return s?applySettingsToSummary(PB.Report.summarize(s),set):null;}})()"
    return eval_value(cdp, sw_session, expr) or {}

def service_worker_errors(cdp, sessions):
    errors = []
    for e in cdp.events:
        if e.get('sessionId') not in sessions: continue
        if e.get('method') == 'Runtime.exceptionThrown': errors.append(e.get('params',{}).get('exceptionDetails',{}).get('text','exception'))
        if e.get('method') == 'Runtime.consoleAPICalled' and e.get('params',{}).get('type') in ['error','assert']:
            args = e.get('params',{}).get('args',[])
            errors.append(' '.join(str(a.get('value', a.get('description',''))) for a in args))
    return errors

def drain_events(cdp):
    old = len(cdp.events)
    deadline = time.time() + 0.1
    while time.time() < deadline:
        cdp.ws.settimeout(0.02)
        try: cdp.events.append(json.loads(cdp.ws.recv()))
        except Exception: break
    cdp.ws.settimeout(20)
    return old, len(cdp.events)

def load_page(cdp, site, mode, sw_session=None, ext_id=None, worker_sessions=None):
    url = 'https://' + site if not site.startswith('http') else site
    if '/' not in site.replace('https://','').replace('http://',''):
        url = 'https://' + site + '/'
    target = cdp.call('Target.createTarget', {'url':'about:blank'})['targetId']
    session = attach(cdp, target)
    cdp.call('Page.enable', sessionId=session)
    cdp.call('Runtime.enable', sessionId=session)
    cdp.call('Network.enable', sessionId=session)
    with contextlib.suppress(Exception):
        cdp.call('Network.setUserAgentOverride', {'userAgent': NORMAL_UA, 'userAgentMetadata': UA_METADATA}, session)
    cdp.call('Performance.enable', sessionId=session)
    start_idx = len(cdp.events)
    start = time.time()
    error = None
    with contextlib.suppress(Exception): cdp.call('Page.navigate', {'url': url}, session)
    load_seen = False
    last_event_time = time.time()
    deadline = start + MAX_WAIT
    while time.time() < deadline:
        cdp.ws.settimeout(0.2)
        try:
            e = json.loads(cdp.ws.recv())
            cdp.events.append(e)
            if e.get('sessionId') == session:
                if e.get('method') in ['Network.requestWillBeSent','Network.loadingFinished','Network.loadingFailed']:
                    last_event_time = time.time()
                if e.get('method') == 'Page.loadEventFired':
                    load_seen = True
                    load_time = time.time() - start
            continue
        except Exception:
            pass
        if SLOW:
            time.sleep(0.6)
        if load_seen and time.time() - last_event_time >= IDLE_WAIT:
            break
    idle_time = time.time() - start
    if not load_seen:
        load_time = None
    drain_events(cdp)
    events = cdp.events[start_idx:]
    requests = {}
    failed = {}
    bytes_sum = 0
    console_errors = 0
    exceptions = 0
    for e in events:
        if e.get('sessionId') != session: continue
        m = e.get('method'); p = e.get('params', {})
        if m == 'Network.requestWillBeSent':
            requests[p.get('requestId')] = p.get('request', {}).get('url')
        elif m == 'Network.loadingFinished':
            bytes_sum += int(p.get('encodedDataLength') or 0)
        elif m == 'Network.loadingFailed':
            failed[p.get('errorText','unknown')] = failed.get(p.get('errorText','unknown'), 0) + 1
        elif m == 'Runtime.exceptionThrown':
            exceptions += 1
        elif m == 'Runtime.consoleAPICalled' and p.get('type') in ['error','assert']:
            console_errors += 1
    metrics = cdp.call('Performance.getMetrics', sessionId=session).get('metrics', [])
    metric_map = {m['name']: m.get('value') for m in metrics}
    navtiming = eval_value(cdp, session, "(() => { const n = performance.getEntriesByType('navigation')[0]; return n ? {domContentLoadedMs: Math.round(n.domContentLoadedEventEnd), loadEventMs: Math.round(n.loadEventEnd)} : {}; })()") or {}
    visible = eval_value(cdp, session, "(() => { const vis = e => { const r=e.getBoundingClientRect(); const s=getComputedStyle(e); return r.width>1 && r.height>1 && s.visibility!=='hidden' && s.display!=='none'; }; const text=(document.body&&document.body.innerText||''); return {title:document.title||'', textSample:text.slice(0,2000), textLength:text.length, images:[...document.images].filter(vis).length, videos:[...document.querySelectorAll('video')].filter(vis).length, iframes:[...document.querySelectorAll('iframe')].filter(vis).length, finalUrl:location.href}; })()") or {}
    shot_path = OUT / f'{slug(site)}-{mode}.png'
    with contextlib.suppress(Exception):
        shot = cdp.call('Page.captureScreenshot', {'format':'png'}, session)['data']
        shot_path.write_bytes(base64.b64decode(shot))
    report = {}
    badge = ''
    if sw_session:
        tab_id = eval_value(cdp, sw_session, "new Promise(r=>chrome.tabs.query({active:true,lastFocusedWindow:true}, tabs=>r(tabs[0]&&tabs[0].id)))")
        if tab_id is None:
            final_url = visible.get('finalUrl', '')
            tab_id = eval_value(cdp, sw_session, f"new Promise(r=>chrome.tabs.query({{}}, tabs=>{{ const hit=tabs.filter(t=>t.url=== {json.dumps(final_url)}).pop(); r(hit&&hit.id); }}))")
        if tab_id is not None:
            report = summarize_report(cdp, sw_session, int(tab_id))
            with contextlib.suppress(Exception):
                badge = eval_value(cdp, sw_session, f"new Promise(r=>chrome.action.getBadgeText({{tabId:{int(tab_id)}}}, r))") or ''
    sw_errors = service_worker_errors(cdp, worker_sessions or [])
    return {
      'site': site, 'mode': mode, 'ok': error is None, 'error': error,
      'loadTimeMs': round(load_time*1000) if load_time else None,
      'idleTimeMs': round(idle_time*1000), 'domContentLoadedMs': navtiming.get('domContentLoadedMs'), 'loadEventMs': navtiming.get('loadEventMs'), 'requestCount': len(requests), 'bytes': bytes_sum,
      'failed': failed, 'consoleErrors': console_errors, 'exceptions': exceptions,
      'title': visible.get('title',''), 'textSample': visible.get('textSample',''), 'textLength': visible.get('textLength',0), 'images': visible.get('images',0), 'videos': visible.get('videos',0), 'iframes': visible.get('iframes',0), 'finalUrl': visible.get('finalUrl',''),
      'JSHeapUsedSize': metric_map.get('JSHeapUsedSize'), 'TaskDuration': metric_map.get('TaskDuration'),
      'report': report, 'badge': badge, 'storageBytes': len(json.dumps(eval_value(cdp, sw_session, 'new Promise(r=>chrome.storage.session.get(null,r))') or {})) if sw_session else None, 'swErrors': sw_errors, 'screenshot': str(shot_path.relative_to(ROOT))
    }

def median(vals):
    vals = sorted(v for v in vals if isinstance(v, (int,float)))
    if not vals: return None
    return vals[len(vals)//2]


def validity(row):
    if row.get('error'):
        return False, 'load error'
    text = ((row.get('title') or '') + ' ' + (row.get('textSample') or '')).lower()
    if any(marker in text for marker in BLOCK_TEXT):
        return False, 'site blocked the test browser'
    if (row.get('textLength') or 0) >= 1000:
        return True, ''
    if (row.get('requestCount') or 0) >= 20 and (row.get('textLength') or 0) >= 100:
        return True, ''
    return False, 'site blocked the test browser'

def selected_sites():
    filt = os.environ.get('REALSITE_FILTER')
    if not filt:
        return SITES
    wanted = {item.strip() for item in filt.split(',') if item.strip()}
    return [(cat, site) for cat, site in SITES if site in wanted]

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    results = []
    # Baseline browser.
    proc_b = proc_e = None
    profiles = []
    try:
        proc_b, cdp_b, _, _, _, prof_b = launch('baseline', extension=False); profiles.append(prof_b)
        proc_e, cdp_e, ext_id, sw_session, worker_sessions, prof_e = launch('extension', extension=True); profiles.append(prof_e)
        sites = selected_sites()
        for idx, (cat, site) in enumerate(sites, 1):
            print(f'[{idx}/{len(sites)}] {site}', flush=True)
            try:
                results.append(dict(category=cat, **load_page(cdp_b, site, 'base')))
            except Exception as e:
                results.append({'category':cat,'site':site,'mode':'base','error':str(e)})
            try:
                set_blocking(cdp_e, sw_session, True)
                results.append(dict(category=cat, **load_page(cdp_e, site, 'on', sw_session, ext_id, worker_sessions)))
            except Exception as e:
                results.append({'category':cat,'site':site,'mode':'on','error':str(e)})
            try:
                set_blocking(cdp_e, sw_session, False)
                results.append(dict(category=cat, **load_page(cdp_e, site, 'off', sw_session, ext_id, worker_sessions)))
            except Exception as e:
                results.append({'category':cat,'site':site,'mode':'off','error':str(e)})
    finally:
        for proc in [proc_b, proc_e]:
            if proc:
                with contextlib.suppress(Exception): proc.terminate(); proc.wait(timeout=5)
        for profile in profiles:
            if profile.exists(): shutil.rmtree(profile, ignore_errors=True)
    (OUT / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    by_site = {}
    for r in results: by_site.setdefault(r['site'], {})[r['mode']] = r
    rows = []
    invalid = []
    overheads = []
    suspects = []
    for site, modes in by_site.items():
        base, on, off = modes.get('base',{}), modes.get('on',{}), modes.get('off',{})
        valid, reason = validity(base)
        if not valid:
            invalid.append((site, reason))
            rows.append([site, on.get('category','') or base.get('category',''), 'Not tested', '', '', '', '', 'Not tested', reason])
            continue
        if base.get('idleTimeMs') and on.get('idleTimeMs'):
            overheads.append(on['idleTimeMs'] - base['idleTimeMs'])
        txt_on, txt_off = on.get('textLength',0), off.get('textLength',0)
        breakage = 'No'
        note = 'No extension-specific breakage found.'
        if txt_off and txt_on < txt_off * 0.45 and txt_on < (base.get('textLength') or 0) * 0.45:
            breakage = 'Check'; note = 'Much less visible text with blocking on.'; suspects.append(site)
        if on.get('exceptions',0) > off.get('exceptions',0) + 5 and on.get('exceptions',0) > base.get('exceptions',0) + 5:
            breakage = 'Check'; note = 'More page exceptions with blocking on.'; suspects.append(site)
        report = on.get('report') or {}
        rows.append([site, on.get('category',''), base.get('idleTimeMs'), on.get('idleTimeMs'), off.get('idleTimeMs'), report.get('trackerRequestCount',0), report.get('blockedTrackerCount',0), breakage, note])
    doc = ['# Real-site test pass 2026-10-10', '', 'Screenshots and raw JSON are in ignored `artifacts/pb-realtest/`.', '', '| Site | Category | Baseline idle ms | Blocking on idle ms | Blocking off idle ms | Trackers found | Blocked | Breakage | Note |', '|---|---:|---:|---:|---:|---:|---:|---|---|']
    for row in rows:
        doc.append('| ' + ' | '.join('' if v is None else str(v).replace('|','/') for v in row) + ' |')
    doc += ['', '## Aggregate', '', f'- Sites tested: {len(by_site)}', f'- Valid sites: {len(by_site) - len(invalid)} / {len(by_site)}', f'- Median idle overhead vs baseline on valid sites: {median(overheads)} ms', f'- Worst idle overhead vs baseline on valid sites: {max(overheads) if overheads else None} ms', f'- Breakage suspects on valid sites: {", ".join(sorted(set(suspects))) if suspects else "None flagged by automated checks"}.', f'- Not tested sites: {", ".join(site for site, _ in invalid) if invalid else "None"}.', '- Counts can vary between visits on ad-heavy sites. With blocking on, blocked scripts cannot load more trackers. Some pages also retry or use fallback requests.']
    (ROOT / 'artifacts' / 'REALSITE_TEST.md').write_text('\n'.join(doc) + '\n', encoding='utf-8')
    print(json.dumps({'sites': len(by_site), 'medianOverheadMs': median(overheads), 'worstOverheadMs': max(overheads) if overheads else None, 'suspects': sorted(set(suspects))[:20]}, indent=2))

if __name__ == '__main__':
    main()
