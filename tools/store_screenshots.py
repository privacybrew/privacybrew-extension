#!/usr/bin/env python3
import base64, contextlib, http.server, json, shutil, subprocess, threading, time
from pathlib import Path
from urllib.parse import urlparse
import websocket
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / 'dist' / 'package-work'
OUT = ROOT / 'store' / 'screenshots'
PROMO = ROOT / 'store' / 'promo-small-440x280.png'
PORT = 8876
HOSTS = ['news.example', 'shop.example', 'www.google-analytics.com', 'static.doubleclick.net', 'connect.facebook.net', 'bat.bing.com', 'googleads.g.doubleclick.net']
BG = '#120a1a'; PANEL = '#1f1329'; PANEL2 = '#281a35'; BORDER = '#3a2c4a'; ACC = '#9b6dd1'; GREEN = '#5fae96'; WARN = '#e8a87c'; TEXT = '#f0eaf7'; DIM = '#b8a8c9'

try:
    FONT_BIG = ImageFont.truetype('DejaVuSans-Bold.ttf', 52)
    FONT_MED = ImageFont.truetype('DejaVuSans-Bold.ttf', 34)
    FONT = ImageFont.truetype('DejaVuSans.ttf', 25)
    FONT_SMALL = ImageFont.truetype('DejaVuSans.ttf', 20)
except Exception:
    FONT_BIG = FONT_MED = FONT = FONT_SMALL = None

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def send(self, body, ctype='text/html'):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(200); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        host = self.headers.get('Host','').split(':')[0]
        path = urlparse(self.path).path
        if host == 'news.example':
            return self.send(f'''<!doctype html><title>News Example</title><style>body{{font:20px system-ui;margin:0;background:#f7f4fb;color:#1f1329}}main{{padding:48px;max-width:900px}}.hero{{font-size:52px;font-weight:800}}.ad{{padding:18px;background:#eee;border:2px dashed #9b6dd1;margin:20px 0}}</style><main><div class="hero">Morning privacy report</div><p>This local fixture loads trackers, ads, and fingerprint scripts for the store images.</p><div class="ad" id="ADbox">Ad space</div><script src="http://www.google-analytics.com:{PORT}/ga.js"></script><script src="http://static.doubleclick.net:{PORT}/ad.js"></script><script src="http://connect.facebook.net:{PORT}/social.js"></script><script src="http://bat.bing.com:{PORT}/bing.js"></script><script src="http://googleads.g.doubleclick.net:{PORT}/pagead/ad.js"></script><script>const c=document.createElement('canvas');c.width=32;c.height=32;c.getContext('2d').getImageData(0,0,32,32);</script><p>Local story list. No real website data is used.</p></main>''')
        if host == 'shop.example':
            return self.send('''<!doctype html><title>Shop Example</title><style>body{font:22px system-ui;margin:0;background:#f7f4fb;color:#1f1329}main{padding:46px}.product{font-size:48px;font-weight:800}.banner{position:fixed;left:80px;right:80px;bottom:60px;background:#1f1329;color:#f0eaf7;border-radius:20px;padding:28px;box-shadow:0 18px 50px #0008}.banner button{font:20px system-ui;padding:12px 18px;margin-right:12px;border-radius:999px;border:0}.reject{background:#5fae96}.accept{background:#e8a87c}</style><main><div class="product">Shop Example</div><p>A local shopping fixture with a cookie choice banner.</p></main><div id="onetrust-consent-sdk" class="banner"><div id="onetrust-banner-sdk"><strong>Cookie choices</strong><p>We use cookies to improve this local fixture.</p><button class="ot-pc-refuse-all-handler reject" onclick="window.__rejectClicked=true;document.querySelector('.banner').style.display='none'">Reject optional cookies</button><button class="accept" onclick="window.__acceptClicked=true">Accept all</button></div></div>''')
        if path.endswith('.js'):
            return self.send('window.__fixtureLoaded=true;', 'application/javascript')
        self.send_response(404); self.end_headers()

def start_server():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start(); return server

class CDP:
    def __init__(self, ws): self.ws = websocket.create_connection(ws, timeout=20); self.i = 1; self.events=[]
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
            self.events.append(data)

def launch():
    profile = ROOT / 'artifacts' / 'store-screenshot-profile'
    if profile.exists(): shutil.rmtree(profile)
    profile.mkdir(parents=True)
    args=['google-chrome','--headless=new','--no-first-run','--no-default-browser-check',f'--user-data-dir={profile}','--remote-debugging-port=0','--remote-allow-origins=*','--enable-unsafe-extension-debugging','--window-size=1280,900','--host-resolver-rules='+','.join(f'MAP {h} 127.0.0.1' for h in HOSTS),'about:blank']
    proc=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    ws=''
    end=time.time()+20
    while time.time()<end:
        line=proc.stderr.readline()
        if 'DevTools listening on ' in line: ws=line.split('DevTools listening on ',1)[1].strip(); break
    cdp=CDP(ws)
    ext=cdp.call('Extensions.loadUnpacked', {'path': str(EXT)})['id']
    sw=None
    for _ in range(50):
        for t in cdp.call('Target.getTargets')['targetInfos']:
            if t.get('url','').endswith('/background.js'):
                sw=cdp.call('Target.attachToTarget', {'targetId':t['targetId'], 'flatten':True})['sessionId']; cdp.call('Runtime.enable', sessionId=sw); break
        if sw: break
        time.sleep(.2)
    return proc, cdp, ext, sw, profile

def attach(cdp, target):
    return cdp.call('Target.attachToTarget', {'targetId':target, 'flatten':True})['sessionId']

def evalv(cdp, session, expr):
    return cdp.call('Runtime.evaluate', {'expression':expr, 'awaitPromise':True, 'returnByValue':True}, session).get('result',{}).get('value')

def wait(cdp, session):
    end=time.time()+15
    while time.time()<end:
        if evalv(cdp, session, 'document.readyState') == 'complete': return
        time.sleep(.2)

def screenshot(cdp, session, path, full=True):
    data=cdp.call('Page.captureScreenshot', {'format':'png', 'captureBeyondViewport': full}, session)['data']
    path.write_bytes(base64.b64decode(data)); return Image.open(path).convert('RGBA')

def create_popup_state(cdp, sw, tab_id, site='news.example', cookie='none'):
    expr=f'''(async()=>{{
      await ensureData();
      const s=PB.Report.emptyState({tab_id}, 'https://{site}/', '{site}'); s.status='ok';
      PB.Report.addTracker(s, disconnect.find('www.google-analytics.com'), 'www.google-analytics.com', 'blocked', 'https://www.google-analytics.com/analytics.js');
      PB.Report.addTracker(s, disconnect.find('static.doubleclick.net'), 'static.doubleclick.net', 'blocked', 'https://static.doubleclick.net/ad.js');
      PB.Report.addTracker(s, disconnect.find('connect.facebook.net'), 'connect.facebook.net', 'blocked', 'https://connect.facebook.net/social.js');
      PB.Report.addTracker(s, disconnect.find('bat.bing.com'), 'bat.bing.com', 'blocked', 'https://bat.bing.com/bing.js');
      PB.Report.addAdBlocked(s, 'https://googleads.g.doubleclick.net/pagead/ad.js');
      PB.Report.addOutsideScript(s, 'https://cdn.news.example/story.js', 'allowed');
      PB.Report.addFingerprint(s, 'canvas', 'https://{site}/fingerprint.js');
      PB.Report.addFingerprint(s, 'webgl', 'https://{site}/fingerprint.js');
      PB.Report.addCookie(s, 'static.doubleclick.net');
      if ('{cookie}'==='rejected') PB.Report.setCookiePopup(s, 'rejected', {{cmp:'OneTrust'}});
      await chrome.storage.session.set({{['tab:{tab_id}']:s}});
      await chrome.action.setBadgeText({{tabId:{tab_id}, text:'3'}});
    }})()'''
    cdp.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True}, sw)

def popup_image(cdp, ext, sw, scroll=None, open_details=False, cookie='none'):
    target=cdp.call('Target.createTarget', {'url': f'chrome-extension://{ext}/popup.html'})['targetId']; sess=attach(cdp,target); cdp.call('Page.enable', sessionId=sess); cdp.call('Emulation.setDeviceMetricsOverride', {'width':390,'height':760,'deviceScaleFactor':2,'mobile':False}, sess); wait(cdp,sess)
    tab_id=evalv(cdp, sw, f"new Promise(r=>chrome.tabs.query({{}}, tabs=>{{ const hits=tabs.filter(t=>(t.url||'').startsWith('chrome-extension://{ext}/popup.html')); r(hits[hits.length-1] && hits[hits.length-1].id); }}))")
    create_popup_state(cdp, sw, tab_id, cookie=cookie)
    cdp.call('Page.navigate', {'url': f'chrome-extension://{ext}/popup.html'}, sess); wait(cdp,sess); time.sleep(.6)
    if open_details:
        cdp.call('Runtime.evaluate', {'expression': "document.querySelector('#trackersCard details') && (document.querySelector('#trackersCard details').open=true); document.querySelector('#trackersCard').scrollIntoView();"}, sess); time.sleep(.2)
    elif scroll:
        cdp.call('Runtime.evaluate', {'expression': f"document.querySelector('{scroll}').scrollIntoView();"}, sess); time.sleep(.2)
    tmp=ROOT/'artifacts'/'store-popup.png'
    return screenshot(cdp,sess,tmp,False)

def page_image(cdp, url, path):
    target=cdp.call('Target.createTarget', {'url':'about:blank'})['targetId']; sess=attach(cdp,target); cdp.call('Page.enable', sessionId=sess); cdp.call('Emulation.setDeviceMetricsOverride', {'width':900,'height':620,'deviceScaleFactor':1,'mobile':False}, sess); cdp.call('Page.navigate', {'url':url}, sess); wait(cdp,sess); time.sleep(3); return screenshot(cdp,sess,path,False)

def bg():
    im=Image.new('RGB',(1280,800),BG).convert('RGBA')
    glow=Image.new('RGBA',(1280,800),(0,0,0,0)); d=ImageDraw.Draw(glow)
    d.ellipse((520,-220,1450,620), fill=(155,109,209,70)); glow=glow.filter(ImageFilter.GaussianBlur(70))
    return Image.alpha_composite(im,glow)

def text(draw, xy, s, font, fill=TEXT): draw.text(xy,s,font=font,fill=fill)
def frame(base, img, xy, size):
    x,y=xy; w,h=size
    shadow=Image.new('RGBA',base.size,(0,0,0,0)); sd=ImageDraw.Draw(shadow); sd.rounded_rectangle((x+14,y+18,x+w+14,y+h+18),24,fill=(0,0,0,90)); shadow=shadow.filter(ImageFilter.GaussianBlur(18)); base.alpha_composite(shadow)
    d=ImageDraw.Draw(base); d.rounded_rectangle((x,y,x+w,y+h),24,fill=PANEL,outline=BORDER,width=3)
    img.thumbnail((w-28,h-28), Image.Resampling.LANCZOS); base.alpha_composite(img,(x+14,y+14))

def make_slide(path, title, lines, popup):
    im=bg(); d=ImageDraw.Draw(im); text(d,(70,120),title,FONT_BIG); yy=210
    for l in lines: text(d,(74,yy),l,FONT, DIM); yy+=42
    frame(im,popup,(720,70),(430,660)); im.convert('RGB').save(path)

def make_cookie_slide(path,before,after,popup):
    im=bg(); d=ImageDraw.Draw(im); text(d,(70,60),'Cookie pop-up help',FONT_BIG); text(d,(72,122),'PrivacyBrew tries to reject optional cookies.',FONT,DIM)
    text(d,(120,185),'Before',FONT_MED); text(d,(690,185),'After',FONT_MED)
    frame(im,before,(70,230),(520,390)); frame(im,after,(670,230),(520,390)); frame(im,popup,(875,165),(290,500)); im.convert('RGB').save(path)

def make_local(path):
    im=bg(); d=ImageDraw.Draw(im); icon=Image.open(ROOT/'extension/icons/icon-128.png').convert('RGBA').resize((120,120)); im.alpha_composite(icon,(90,90)); text(d,(240,112),'Local by design',FONT_BIG)
    cards=[('No account','PrivacyBrew does not need a login.'),('No analytics','It does not send usage data to us.'),('No remote code','Rules and scripts ship in the extension.')]
    y=280
    for h,b in cards:
        d.rounded_rectangle((100,y,1180,y+110),24,fill=PANEL,outline=BORDER,width=2); text(d,(140,y+22),h,FONT_MED,ACC); text(d,(140,y+62),b,FONT,DIM); y+=140
    im.convert('RGB').save(path)

def promo(path):
    im=Image.new('RGB',(440,280),BG).convert('RGBA'); d=ImageDraw.Draw(im); d.rounded_rectangle((18,18,422,262),28,fill=PANEL,outline=BORDER,width=2)
    icon=Image.open(ROOT/'extension/icons/icon-128.png').convert('RGBA').resize((76,76)); im.alpha_composite(icon,(42,52)); text(d,(135,55),'PrivacyBrew',FONT_MED); text(d,(42,150),'Block trackers and ads.',FONT); text(d,(42,190),'See a plain-language report.',FONT_SMALL,DIM); im.convert('RGB').save(path)

def main():
    if not EXT.exists(): subprocess.run(['python3','tools/package.py'], cwd=ROOT, check=True)
    OUT.mkdir(parents=True, exist_ok=True); (ROOT/'artifacts').mkdir(exist_ok=True)
    server=start_server(); proc=None
    try:
        proc,cdp,ext,sw,profile=launch()
        report=popup_image(cdp,ext,sw)
        controls=popup_image(cdp,ext,sw,scroll='#controlsCard')
        companies=popup_image(cdp,ext,sw,open_details=True)
        before=page_image(cdp,f'http://shop.example:{PORT}/',ROOT/'artifacts'/'store-before.png')
        # Use fixture page after extension has handled it.
        after=page_image(cdp,f'http://shop.example:{PORT}/',ROOT/'artifacts'/'store-after.png')
        popup_cookie=popup_image(cdp,ext,sw,cookie='rejected')
        make_slide(OUT/'01-report-card.png','See the privacy story',['A plain-language report card for each website.','Trackers, ads, cookies and fingerprinting in one place.'],report)
        make_slide(OUT/'02-blocking-controls.png','Control each protection',['Block trackers and ads by default.','Send privacy requests to websites.'],controls)
        make_cookie_slide(OUT/'03-cookie-popups.png',before,after,popup_cookie)
        make_slide(OUT/'04-companies-detail.png','See which companies appear',['Company rows show Blocked or Allowed.','Open details to see request domains.'],companies)
        make_local(OUT/'05-local-by-design.png')
        promo(PROMO)
    finally:
        if proc:
            with contextlib.suppress(Exception): proc.terminate(); proc.wait(timeout=5)
        server.shutdown()
        with contextlib.suppress(Exception): shutil.rmtree(ROOT/'artifacts'/'store-screenshot-profile')

if __name__=='__main__': main()
