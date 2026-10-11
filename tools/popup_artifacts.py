#!/usr/bin/env python3
import base64, contextlib, json, shutil, subprocess, time
from pathlib import Path
import websocket

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / 'extension'
ART = ROOT / 'artifacts'
ART.mkdir(exist_ok=True)

class CDP:
    def __init__(self, ws): self.ws = websocket.create_connection(ws, timeout=20); self.i=1
    def call(self, method, params=None, sessionId=None):
        msg={'id':self.i,'method':method}; self.i+=1
        if params is not None: msg['params']=params
        if sessionId: msg['sessionId']=sessionId
        self.ws.send(json.dumps(msg))
        while True:
            data=json.loads(self.ws.recv())
            if data.get('id')==msg['id']:
                if 'error' in data: raise RuntimeError(data['error'])
                return data.get('result',{})

def launch():
    prof=ART/'popup-artifacts-profile'; shutil.rmtree(prof, ignore_errors=True); prof.mkdir()
    proc=subprocess.Popen(['google-chrome','--headless=new','--no-first-run','--no-default-browser-check',f'--user-data-dir={prof}','--remote-debugging-port=0','--remote-allow-origins=*','--enable-unsafe-extension-debugging','--window-size=500,700','about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    ws=''; end=time.time()+20
    while time.time()<end:
        line=proc.stderr.readline()
        if 'DevTools listening on ' in line: ws=line.split('DevTools listening on ',1)[1].strip(); break
    cdp=CDP(ws); ext=cdp.call('Extensions.loadUnpacked', {'path': str(EXT)})['id']
    sw=None
    for _ in range(50):
        for t in cdp.call('Target.getTargets')['targetInfos']:
            if t.get('url','').endswith('/background.js'):
                sw=cdp.call('Target.attachToTarget', {'targetId':t['targetId'], 'flatten':True})['sessionId']; cdp.call('Runtime.enable', sessionId=sw); break
        if sw: break
        time.sleep(.2)
    return proc, cdp, ext, sw, prof

def attach(cdp,target): return cdp.call('Target.attachToTarget', {'targetId':target,'flatten':True})['sessionId']
def eval_sw(cdp,sw,expr): return cdp.call('Runtime.evaluate', {'expression':expr,'awaitPromise':True,'returnByValue':True}, sw).get('result',{}).get('value')

def create_state(cdp, sw, tab_id, site='news.example', cookie='none', state='normal'):
    adwall = "PB.Report.setAdWall(s, 'detected');" if state in ['wall', 'worst'] else ''
    paused = "{'news.example': true}" if state in ['paused', 'worst'] else "{}"
    global_off = 'true' if state == 'global' else 'false'
    temp_until = 'Date.now()+15*60000' if state == 'temp' else '0'
    expr=f"""(async()=>{{
await ensureData();
const s=PB.Report.emptyState({tab_id}, 'https://{site}/', '{site}');
s.status='ok';
PB.Report.addTracker(s, disconnect.find('www.google-analytics.com'), 'www.google-analytics.com', 'blocked', 'https://www.google-analytics.com/a.js');
PB.Report.addTracker(s, disconnect.find('static.doubleclick.net'), 'static.doubleclick.net', 'blocked', 'https://static.doubleclick.net/ad.js');
PB.Report.addTracker(s, disconnect.find('connect.facebook.net'), 'connect.facebook.net', 'blocked', 'https://connect.facebook.net/s.js');
PB.Report.addTracker(s, disconnect.find('bat.bing.com'), 'bat.bing.com', 'allowed', 'https://bat.bing.com/b.js');
PB.Report.addAdBlocked(s, 'https://googleads.g.doubleclick.net/pagead/ad.js');
PB.Report.addOutsideScript(s, 'https://cdn.news.example/story.js', 'allowed');
PB.Report.addFingerprint(s, 'canvas', 'https://{site}/fp.js');
PB.Report.addFingerprint(s, 'webgl', 'https://{site}/fp.js');
PB.Report.addCookie(s, 'static.doubleclick.net');
if ('{cookie}'==='rejected') PB.Report.setCookiePopup(s, 'rejected', {{cmp:'OneTrust'}});
{adwall}
await chrome.storage.session.set({{['tab:{tab_id}']:s}});
await chrome.storage.local.set({{pausedSites: {paused}, globalOff: {global_off}, tempOffUntil: {temp_until}}});

return s;
}})()"""
    res = cdp.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True}, sw)
    if 'exceptionDetails' in res:
        raise RuntimeError(res['exceptionDetails'])

def open_popup(cdp, ext, sw, name, action=None, state='normal'):
    target=cdp.call('Target.createTarget', {'url': f'chrome-extension://{ext}/popup.html'})['targetId']; sess=attach(cdp,target); cdp.call('Page.enable', sessionId=sess); cdp.call('Emulation.setDeviceMetricsOverride', {'width':380,'height':580,'deviceScaleFactor':1,'mobile':False}, sess)
    time.sleep(.5)
    tab_id = 424242 + abs(hash(name)) % 10000
    create_state(cdp, sw, tab_id, state=state)
    cdp.call('Page.navigate', {'url': f'chrome-extension://{ext}/popup.html?tabId={tab_id}'}, sess); time.sleep(.8)
    if action:
        cdp.call('Runtime.evaluate', {'expression': action}, sess); time.sleep(.5)
    data=cdp.call('Page.captureScreenshot', {'format':'png'}, sess)['data']
    (ART/name).write_bytes(base64.b64decode(data))
    clipped=cdp.call('Runtime.evaluate', {'expression': "[...document.querySelectorAll('body *:not(script):not(style)')].filter(e=>{const r=e.getBoundingClientRect();return r.bottom>581&&!e.closest('.detail-scroll')&&!e.closest('#settingsView')&&e.id!=='homeView'}).length", 'returnByValue':True}, sess)['result'].get('value')
    footer_ok=cdp.call('Runtime.evaluate', {'expression': "(()=>{const v=document.querySelector('.view:not([hidden])')||document;const f=document.querySelector('.home-footer');if(!f||f.offsetParent===null)return true;return [...f.querySelectorAll('a,button')].every(e=>e.getBoundingClientRect().bottom<=580)})()", 'returnByValue':True}, sess)['result'].get('value')
    print(name, 'clipped=', clipped, 'footer_visible=', footer_ok)
    FAILURES.extend([f'{name}: {clipped} clipped elements'] if clipped else [])
    FAILURES.extend([f'{name}: footer not fully visible'] if footer_ok is False else [])

FAILURES=[]

if __name__=='__main__':
    proc=None; prof=None
    try:
        proc,cdp,ext,sw,prof=launch()
        open_popup(cdp,ext,sw,'pb-ext-home.png')
        open_popup(cdp,ext,sw,'pb-ext-detail-trackers.png', "document.querySelector('[data-detail=trackers]').click(); setTimeout(()=>{const d=document.querySelector('details'); if(d)d.open=true},50)")
        open_popup(cdp,ext,sw,'pb-ext-settings.png', "document.querySelector('#settingsButton').click()")
        open_popup(cdp,ext,sw,'pb-ext-power-menu.png', "document.querySelector('#powerButton').click()")
        open_popup(cdp,ext,sw,'pb-ext-power-menu-while.png', "document.querySelector('#powerButton').click(); document.querySelector('#forAWhileButton').click()")
        open_popup(cdp,ext,sw,'pb-ext-feedback.png', "document.querySelector('#feedbackButton').click()")
        open_popup(cdp,ext,sw,'pb-ext-worst-case.png', state='worst')
        open_popup(cdp,ext,sw,'pb-ext-wall.png', state='wall')
        open_popup(cdp,ext,sw,'pb-ext-global-off.png', state='global')
        if FAILURES:
            raise SystemExit('Popup layout check failed:\n' + '\n'.join(FAILURES))
        print('Popup layout check passed')
    finally:
        if proc:
            with contextlib.suppress(Exception): proc.terminate(); proc.wait(timeout=5)
        if prof: shutil.rmtree(prof, ignore_errors=True)
