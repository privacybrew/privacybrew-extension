#!/usr/bin/env python3
import base64, contextlib, http.server, json, shutil, subprocess, threading, time, textwrap
from pathlib import Path
from urllib.parse import urlparse
import websocket
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / 'extension'
OUT = ROOT / 'store' / 'screenshots'
PROMO = ROOT / 'store' / 'promo-small-440x280.png'
PORT = 8876
HEADLESS = '--headed' not in __import__('sys').argv
if not HEADLESS and not (__import__('os').environ.get('DISPLAY') or __import__('os').environ.get('WAYLAND_DISPLAY')):
    raise SystemExit('--headed needs DISPLAY or WAYLAND_DISPLAY')
HOSTS = ['news.example', 'shop.example', 'www.google-analytics.com', 'static.doubleclick.net', 'connect.facebook.net', 'bat.bing.com', 'googleads.g.doubleclick.net']
BG = '#120a1a'; PANEL = '#1f1329'; BORDER = '#3a2c4a'; ACC = '#9b6dd1'; GREEN = '#5fae96'; TEXT = '#f0eaf7'; DIM = '#b8a8c9'
FONT_BIG = ImageFont.truetype('DejaVuSans-Bold.ttf', 54)
FONT_MED = ImageFont.truetype('DejaVuSans-Bold.ttf', 34)
FONT = ImageFont.truetype('DejaVuSans.ttf', 25)
FONT_SMALL = ImageFont.truetype('DejaVuSans.ttf', 20)

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def send(self, body, ctype='text/html'):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(200); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        host = self.headers.get('Host','').split(':')[0]
        path = urlparse(self.path).path
        if host == 'news.example':
            return self.send(f'''<!doctype html><title>News Example</title><style>body{{font:20px system-ui;margin:0;background:#f7f4fb;color:#1f1329}}main{{padding:48px;max-width:900px}}.hero{{font-size:52px;font-weight:800}}.ad{{padding:18px;background:#eee;border:2px dashed #9b6dd1;margin:20px 0}}</style><main><div class="hero">News Example</div><p>This local fixture loads trackers, ads, and fingerprint scripts for store images.</p><div class="ad" id="ADbox">Ad space</div><script src="http://www.google-analytics.com:{PORT}/ga.js"></script><script src="http://static.doubleclick.net:{PORT}/ad.js"></script><script src="http://connect.facebook.net:{PORT}/social.js"></script><script src="http://bat.bing.com:{PORT}/bing.js"></script><script src="http://googleads.g.doubleclick.net:{PORT}/pagead/ad.js"></script><script>const c=document.createElement('canvas');c.width=32;c.height=32;c.getContext('2d').getImageData(0,0,32,32);</script><p>Local story list. No real website data is used.</p></main>''')
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
    args=['google-chrome',*(['--headless=new'] if HEADLESS else []),'--no-first-run','--no-default-browser-check',f'--user-data-dir={profile}','--remote-debugging-port=0','--remote-allow-origins=*','--enable-unsafe-extension-debugging','--window-size=1280,900','--host-resolver-rules='+','.join(f'MAP {h} 127.0.0.1' for h in HOSTS),'about:blank']
    proc=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
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
    return proc, cdp, ext, sw, profile

def attach(cdp, target): return cdp.call('Target.attachToTarget', {'targetId':target, 'flatten':True})['sessionId']
def evalv(cdp, session, expr): return cdp.call('Runtime.evaluate', {'expression':expr, 'awaitPromise':True, 'returnByValue':True}, session).get('result',{}).get('value')
def wait(cdp, session):
    end=time.time()+15
    while time.time()<end:
        if evalv(cdp, session, 'document.readyState') == 'complete': return
        time.sleep(.2)

def shot(cdp, session):
    data=cdp.call('Page.captureScreenshot', {'format':'png'}, session)['data']
    tmp = ROOT/'artifacts'/'tmp-shot.png'
    tmp.write_bytes(base64.b64decode(data))
    return Image.open(tmp).convert('RGBA')

def open_page(cdp, url, w=900, h=620):
    target=cdp.call('Target.createTarget', {'url':'about:blank'})['targetId']; sess=attach(cdp,target); cdp.call('Page.enable', sessionId=sess); cdp.call('Emulation.setDeviceMetricsOverride', {'width':w,'height':h,'deviceScaleFactor':1,'mobile':False}, sess); cdp.call('Page.navigate', {'url':url}, sess); wait(cdp,sess); time.sleep(2.5); return sess

def tab_id_for_url(cdp, sw, prefix):
    return evalv(cdp, sw, f"new Promise(r=>chrome.tabs.query({{}}, tabs=>{{const hit=tabs.filter(t=>(t.url||'').startsWith('{prefix}')).pop(); r(hit&&hit.id);}}))")

def create_state(cdp, sw, tab_id, site='news.example', cookie='none'):
    expr=f'''(async()=>{{await ensureData(); const s=PB.Report.emptyState({tab_id}, 'https://{site}/', '{site}'); s.status='ok';
PB.Report.addTracker(s, disconnect.find('www.google-analytics.com'), 'www.google-analytics.com', 'blocked', 'https://www.google-analytics.com/analytics.js');
PB.Report.addTracker(s, disconnect.find('static.doubleclick.net'), 'static.doubleclick.net', 'blocked', 'https://static.doubleclick.net/ad.js');
PB.Report.addTracker(s, disconnect.find('connect.facebook.net'), 'connect.facebook.net', 'blocked', 'https://connect.facebook.net/social.js');
PB.Report.addTracker(s, disconnect.find('bat.bing.com'), 'bat.bing.com', 'allowed', 'https://bat.bing.com/bing.js');
PB.Report.addAdBlocked(s, 'https://googleads.g.doubleclick.net/pagead/ad.js');
PB.Report.addOutsideScript(s, 'https://cdn.news.example/story.js', 'allowed');
PB.Report.addFingerprint(s, 'canvas', 'https://{site}/fingerprint.js'); PB.Report.addFingerprint(s, 'webgl', 'https://{site}/fingerprint.js');
PB.Report.addCookie(s, 'static.doubleclick.net'); if ('{cookie}'==='rejected') PB.Report.setCookiePopup(s, 'rejected', {{cmp:'OneTrust'}});
await chrome.storage.session.set({{['tab:{tab_id}']:s}}); await chrome.action.setBadgeText({{tabId:{tab_id}, text:'3'}});}})()'''
    cdp.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True}, sw)

def popup(cdp, ext, sw, tab_id, mode='home'):
    target=cdp.call('Target.createTarget', {'url': f'chrome-extension://{ext}/popup.html?tabId={tab_id}'})['targetId']; sess=attach(cdp,target); cdp.call('Page.enable', sessionId=sess); cdp.call('Emulation.setDeviceMetricsOverride', {'width':390,'height':650,'deviceScaleFactor':2,'mobile':False}, sess); wait(cdp,sess); time.sleep(.6)
    cdp.call('Runtime.evaluate', {'expression': "const st=document.createElement('style');st.textContent='::-webkit-scrollbar{display:none} body{scrollbar-width:none}';document.documentElement.appendChild(st);"}, sess)
    if mode == 'settings':
        cdp.call('Runtime.evaluate', {'expression': "document.querySelector('#settingsButton').click()"}, sess); time.sleep(.3)
    elif mode == 'companies':
        cdp.call('Runtime.evaluate', {'expression': "document.querySelector('[data-detail=trackers]').click(); setTimeout(()=>{const d=document.querySelector('details'); if(d)d.open=true},50);"}, sess); time.sleep(.4)
    elif mode == 'cookies':
        cdp.call('Runtime.evaluate', {'expression': "document.querySelector('[data-detail=cookies]').click()"}, sess); time.sleep(.3)
    return shot(cdp,sess)

def popup_element(cdp, ext, tab_id, selector):
    target=cdp.call('Target.createTarget', {'url': f'chrome-extension://{ext}/popup.html?tabId={tab_id}'})['targetId']; sess=attach(cdp,target); cdp.call('Page.enable', sessionId=sess); cdp.call('Emulation.setDeviceMetricsOverride', {'width':390,'height':900,'deviceScaleFactor':2,'mobile':False}, sess); wait(cdp,sess); time.sleep(.6)
    box=cdp.call('Runtime.evaluate', {'expression': f"(()=>{{const r=document.querySelector('{selector}').getBoundingClientRect();return [r.x,r.y+scrollY,r.width,r.height]}})()", 'returnByValue':True}, sess)['result']['value']
    data=cdp.call('Page.captureScreenshot', {'format':'png','captureBeyondViewport':True,'clip':{'x':box[0],'y':box[1],'width':box[2],'height':box[3],'scale':1}}, sess)['data']
    tmp = ROOT/'artifacts'/'tmp-shot.png'; tmp.write_bytes(base64.b64decode(data)); return Image.open(tmp).convert('RGBA')

def bg():
    im=Image.new('RGBA',(1280,800),BG); glow=Image.new('RGBA',(1280,800),(0,0,0,0)); d=ImageDraw.Draw(glow); d.ellipse((520,-220,1450,620), fill=(155,109,209,72)); return Image.alpha_composite(im, glow.filter(ImageFilter.GaussianBlur(70)))
def draw_wrapped(d, xy, text, font, fill, width, linegap=8):
    x,y=xy
    for para in text.split('\n'):
        line=''
        for word in para.split():
            test=(line+' '+word).strip()
            if d.textbbox((0,0),test,font=font)[2] > width and line:
                d.text((x,y),line,font=font,fill=fill); y += font.size + linegap; line=word
            else: line=test
        if line: d.text((x,y),line,font=font,fill=fill); y += font.size + linegap
    return y

def frame(base,img,xy,size):
    x,y=xy; w,h=size; sh=Image.new('RGBA',base.size,(0,0,0,0)); sd=ImageDraw.Draw(sh); sd.rounded_rectangle((x+14,y+18,x+w+14,y+h+18),24,fill=(0,0,0,95)); base.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))
    d=ImageDraw.Draw(base); d.rounded_rectangle((x,y,x+w,y+h),24,fill=PANEL,outline=BORDER,width=3); img.thumbnail((w-28,h-28), Image.Resampling.LANCZOS); base.alpha_composite(img,(x+14,y+14))
def slide(path,title,body,img):
    im=bg(); d=ImageDraw.Draw(im); draw_wrapped(d,(70,135),title,FONT_BIG,TEXT,620); draw_wrapped(d,(74,270),body,FONT,DIM,610); frame(im,img,(790,85),(390,630)); im.convert('RGB').save(path)
def cookie_slide(path,before,after,card):
    im=bg(); d=ImageDraw.Draw(im); draw_wrapped(d,(70,44),'Cookie pop-up help',FONT_BIG,TEXT,1100); draw_wrapped(d,(72,114),'PrivacyBrew rejects optional cookies for you. It never selects Accept all.',FONT,DIM,1140)
    d.text((70,176),'Before',font=FONT_MED,fill=TEXT); d.text((670,176),'After',font=FONT_MED,fill=TEXT)
    # page shots are 900x620; frame inner size keeps that ratio so no empty strip shows
    frame(im,before,(70,222),(540,372)); frame(im,after,(670,222),(540,372))
    d.text((70,628),'Without PrivacyBrew:',font=FONT_MED,fill=DIM); d.text((70,676),'the banner asks you to choose.',font=FONT,fill=DIM)
    d.text((670,628),'With PrivacyBrew:',font=FONT_MED,fill=TEXT)
    d.text((670,676),'it selected Reject for you.',font=FONT,fill=DIM)
    frame(im,card,(1010,610),(150,130)); im.convert('RGB').save(path)
def local(path):
    im=bg(); d=ImageDraw.Draw(im); icon=Image.open(ROOT/'extension/icons/icon-128.png').convert('RGBA').resize((120,120)); im.alpha_composite(icon,(90,90)); d.text((240,112),'Local by design',font=FONT_BIG,fill=TEXT)
    y=270
    for h,b in [('No account','PrivacyBrew does not need a login.'),('No analytics','It does not send usage data to us.'),('No remote code','Rules and scripts ship in the extension.')]:
        d.rounded_rectangle((80,y,1200,y+125),24,fill=PANEL,outline=BORDER,width=2); d.text((130,y+24),h,font=FONT_MED,fill=ACC); d.text((130,y+72),b,font=FONT,fill=DIM); y+=145
    im.convert('RGB').save(path)
def promo(path):
    im=Image.new('RGBA',(440,280),BG); d=ImageDraw.Draw(im); d.rounded_rectangle((18,18,422,262),28,fill=PANEL,outline=BORDER,width=2); icon=Image.open(ROOT/'extension/icons/icon-128.png').convert('RGBA').resize((76,76)); im.alpha_composite(icon,(42,52)); d.text((135,55),'PrivacyBrew',font=FONT_MED,fill=TEXT); d.text((42,150),'Block trackers and ads.',font=FONT,fill=TEXT); d.text((42,190),'See a plain-language report.',font=FONT_SMALL,fill=DIM); im.convert('RGB').save(path)

def main():
    OUT.mkdir(parents=True, exist_ok=True); (ROOT/'artifacts').mkdir(exist_ok=True); server=start_server(); proc=None
    try:
        proc,cdp,ext,sw,profile=launch()
        news=open_page(cdp,f'http://news.example:{PORT}/'); news_tab=tab_id_for_url(cdp,sw,'http://news.example'); create_state(cdp,sw,news_tab)
        report=popup(cdp,ext,sw,news_tab,'home'); controls=popup(cdp,ext,sw,news_tab,'settings'); companies=popup(cdp,ext,sw,news_tab,'companies')
        cdp.call('Runtime.evaluate', {'expression':'setCookiePopupHandling(false)', 'awaitPromise':True}, sw)
        before_s=open_page(cdp,f'http://shop.example:{PORT}/'); before=shot(cdp,before_s)
        cdp.call('Runtime.evaluate', {'expression':'setCookiePopupHandling(true)', 'awaitPromise':True}, sw)
        after_s=open_page(cdp,f'http://shop.example:{PORT}/'); time.sleep(4)
        # The extension must handle the banner itself. Stop if it did not.
        seen=cdp.call('Runtime.evaluate', {'expression':"JSON.stringify({rejected:!!window.__rejectClicked, accepted:!!window.__acceptClicked, visible:(()=>{const b=document.querySelector('.banner');return !!b && getComputedStyle(b).display!=='none' && b.offsetHeight>0})()})", 'returnByValue':True}, after_s)['result']['value']
        print('after banner state:', seen)
        st=json.loads(seen)
        if st['accepted'] or st['visible']: raise SystemExit('Extension did not handle the fixture banner: '+seen)
        after=shot(cdp,after_s)
        shop_tab=tab_id_for_url(cdp,sw,'http://shop.example'); create_state(cdp,sw,shop_tab,'shop.example','rejected'); cookie_popup=popup(cdp,ext,sw,shop_tab,'cookies')
        slide(OUT/'01-report-card.png','See the privacy story','A plain-language report card for each website.\nTrackers, ads, cookies, and fingerprinting in one place.',report)
        slide(OUT/'02-blocking-controls.png','Control each protection','Block trackers and ads by default.\nSend privacy requests to websites.',controls)
        cookie_slide(OUT/'03-cookie-popups.png',before,after,cookie_popup)
        slide(OUT/'04-companies-detail.png','See company details','Rows show Blocked or Allowed.\nOpen details to see request domains.',companies)
        local(OUT/'05-local-by-design.png'); promo(PROMO)
    finally:
        if proc:
            with contextlib.suppress(Exception): proc.terminate(); proc.wait(timeout=5)
        server.shutdown(); shutil.rmtree(ROOT/'artifacts'/'store-screenshot-profile', ignore_errors=True)
if __name__=='__main__': main()
