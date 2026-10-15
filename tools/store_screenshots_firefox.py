#!/usr/bin/env python3
"""AMO screenshots (1280x800) taken in headless Firefox with the PACKAGED Firefox build.

Usage: python3 tools/store_screenshots_firefox.py [--no-build]
Output: store-firefox/screenshots/*.png

The pages are local fixtures (news.example, shop.example) from tools/store_screenshots.py.
The numbers in the popup come from real page loads, not from made-up report data.
"""
import contextlib, importlib.util, json, shutil, sys, time
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from firefox_bidi import Firefox  # noqa: E402

argv = list(sys.argv)
sys.argv = [sys.argv[0]]  # the imported tools read sys.argv for --headed
spec = importlib.util.spec_from_file_location('store_screenshots', str(ROOT / 'tools/store_screenshots.py'))
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)
import run_tests_firefox as rtf  # noqa: E402
sys.argv = argv

OUT = ROOT / 'store-firefox' / 'screenshots'
TMP = ROOT / 'artifacts' / 'ff-store-shot.png'
PORT = ss.PORT
HIDE_SCROLLBARS = "(() => { const st = document.createElement('style'); st.textContent = '* { scrollbar-width: none !important; }'; document.documentElement.appendChild(st); return true; })()"


def grab(ff, ctx, clip=None, scale=1):
    ff.screenshot(ctx, TMP, clip=clip, scale=scale)
    return Image.open(TMP).convert('RGBA')


def popup_image(s, target, action=None):
    pop = s.popup_for(target)
    s.ff.eval(pop, HIDE_SCROLLBARS)
    if action:
        s.ff.eval(pop, action + '; true')
        time.sleep(0.6)
    img = grab(s.ff, pop, clip=(0, 0, 380, 580), scale=2)
    s.ff.close_tab(pop)
    return img


def slide(path, title, body, img):
    """Like store_screenshots.slide, but the frame matches the 380x580 popup, so no empty strip shows."""
    im = ss.bg()
    d = ss.ImageDraw.Draw(im)
    ss.draw_wrapped(d, (70, 135), title, ss.FONT_BIG, ss.TEXT, 620)
    ss.draw_wrapped(d, (74, 270), body, ss.FONT, ss.DIM, 610)
    w = 390
    h = 28 + round((w - 28) * img.height / img.width)
    ss.frame(im, img, (790, (800 - h) // 2), (w, h))
    im.convert('RGB').save(path)


def page_tab(s, url):
    ctx = s.ff.new_tab()
    s.ff.set_viewport(ctx, 900, 620)
    s.ff.navigate(ctx, url)
    time.sleep(3)
    return ctx


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rtf.build_and_unpack('--no-build' in sys.argv)
    server = ss.start_server()
    ff = None
    try:
        prefs = {'network.proxy.type': 1, 'network.proxy.http': '127.0.0.1', 'network.proxy.http_port': rtf.DEAD_PROXY,
                 'network.proxy.ssl': '127.0.0.1', 'network.proxy.ssl_port': rtf.DEAD_PROXY,
                 'network.proxy.no_proxies_on': ','.join(ss.HOSTS) + ',localhost,127.0.0.1'}
        ff = Firefox('store-shots', ss.HOSTS, time_limit=420, extra_prefs=prefs)
        ff.install(rtf.EXT_DIR)
        time.sleep(2)
        s = rtf.Suite(ff)

        news = page_tab(s, f'http://news.example:{PORT}/')
        tab_id, _ = s.latest(f'http://news.example:{PORT}/')
        rep = s.summary(tab_id)
        print('news.example report:', {k: rep.get(k) for k in ['trackerRequestCount', 'blockedTrackerCount', 'allowedTrackerCount', 'adBlockedRequestCount', 'trackerCount']})
        if not rep.get('blockedTrackerCount'):
            raise SystemExit('No blocked trackers on news.example. Stop.')
        report = popup_image(s, news)
        controls = popup_image(s, news, "document.querySelector('#settingsButton').click()")
        companies = popup_image(s, news, "document.querySelector('[data-detail=trackers]').click(); setTimeout(() => { const d = document.querySelector('details'); if (d) d.open = true; }, 50)")

        s.bg('b.setCookiePopupHandling(false)')
        shop = page_tab(s, f'http://shop.example:{PORT}/')
        before = grab(ff, shop)
        s.bg('b.setCookiePopupHandling(true)')
        ff.navigate(shop, f'http://shop.example:{PORT}/')
        time.sleep(4)
        seen = ff.evalj(shop, "({rejected: !!window.__rejectClicked, accepted: !!window.__acceptClicked, visible: (() => { const b = document.querySelector('.banner'); return !!b && getComputedStyle(b).display !== 'none' && b.offsetHeight > 0; })()})")
        print('after banner state:', seen)
        if seen['accepted'] or seen['visible'] or not seen['rejected']:
            raise SystemExit('Extension did not handle the fixture banner: ' + json.dumps(seen))
        after = grab(ff, shop)

        slide(OUT / '01-report-card.png', 'See the privacy story', 'A plain-language report card for each website.\nTrackers, ads, cookies, and fingerprinting in one place.', report)
        slide(OUT / '02-blocking-controls.png', 'Control each protection', 'Block trackers and ads by default.\nSend privacy requests to websites.', controls)
        ss.cookie_slide(OUT / '03-cookie-popups.png', before, after, None)
        slide(OUT / '04-companies-detail.png', 'See company details', 'Rows show Blocked or Allowed.\nOpen details to see request domains.', companies)
        ss.local(OUT / '05-local-by-design.png')
        for p in sorted(OUT.glob('*.png')):
            with Image.open(p) as im:
                print(p.relative_to(ROOT), im.size)
                if im.size != (1280, 800):
                    raise SystemExit(f'{p.name} is not 1280x800')
    finally:
        if ff:
            ff.close()
        server.shutdown()
        shutil.rmtree(rtf.EXT_DIR, ignore_errors=True)
        with contextlib.suppress(FileNotFoundError):
            TMP.unlink()


if __name__ == '__main__':
    main()
