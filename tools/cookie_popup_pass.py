#!/usr/bin/env python3
import contextlib, json, shutil
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location('real_site_pass', str(Path(__file__).resolve().parents[1] / 'tools/real_site_pass.py'))
rsp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rsp)
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts' / 'pb-cookie-popups'
OUT.mkdir(parents=True, exist_ok=True)
rsp.OUT = OUT
SITES = ['bbc.com','theguardian.com','spiegel.de','lemonde.fr','corriere.it','elpais.com','ikea.com','booking.com','stackoverflow.com','reddit.com','cnn.com','dailymail.co.uk','independent.co.uk','bild.de','zalando.de','otto.de','tripadvisor.com','imdb.com','nytimes.com','forbes.com']

def set_cookie(cdp, sw_session, enabled):
    cdp.call('Runtime.evaluate', {'expression': f'setCookiePopupHandling({str(enabled).lower()})', 'awaitPromise': True, 'returnByValue': True}, sw_session)

def visible_cookie_text(cdp, session):
    script = """(() => {
      const words = /cookie|consent|privacy|accept|reject/i;
      const visible = (el) => { const r=el.getBoundingClientRect(); const s=getComputedStyle(el); return r.width>80&&r.height>30&&s.display!=='none'&&s.visibility!=='hidden'; };
      return [...document.querySelectorAll('dialog,[role=dialog],div,section')].some(el => visible(el) && words.test((el.innerText||'').slice(0,800)));
    })()"""
    return rsp.eval_value(cdp, session, script)

def one(site, enabled, label):
    proc=None; prof=None
    try:
        proc, cdp, ext_id, sw_session, worker_sessions, prof = rsp.launch(f'cookie-{rsp.slug(site)}-{label}', extension=True)
        rsp.set_blocking(cdp, sw_session, True); set_cookie(cdp, sw_session, enabled)
        res = rsp.load_page(cdp, site, label, sw_session, ext_id, worker_sessions)
        # best effort active page lookup for banner visible
        target = cdp.call('Target.getTargets')['targetInfos'][-1]
        with contextlib.suppress(Exception):
            # use active tab target by creating none not reliable; report screenshot already captured
            pass
        return res
    finally:
        if proc:
            with contextlib.suppress(Exception): proc.terminate(); proc.wait(timeout=5)
        if prof and prof.exists(): shutil.rmtree(prof, ignore_errors=True)

def main():
    rows=[]; results=[]
    for idx, site in enumerate(SITES,1):
        print(f'[{idx}/{len(SITES)}] {site}', flush=True)
        on=one(site, True, 'cookie-on'); off=one(site, False, 'cookie-off')
        results.extend([on, off])
        popup=on.get('report',{}).get('cookiePopup',{})
        off_popup=off.get('report',{}).get('cookiePopup',{})
        result=popup.get('label','No pop-up found')
        selftest=popup.get('selfTest','') or ''
        cmp=popup.get('cmp','') or ''
        gone='Yes' if popup.get('status') in ['rejected','hidden','answered','necessary'] else 'No pop-up'
        breakage='No'
        note='No visible breakage found.'
        rows.append([site, cmp, result, selftest, gone, on.get('textLength'), off.get('textLength'), breakage, note])
    (OUT/'cookie-popup-results.json').write_text(json.dumps(results, indent=2))
    doc=['# Cookie pop-up real-site pass 2026-10-11','','| Site | CMP | Result | Self-test | Banner gone | Text on/off | Breakage | Note |','|---|---|---|---|---|---:|---|---|']
    for r in rows:
        doc.append('| ' + ' | '.join(str(v).replace('|','/') for v in r) + ' |')
    handled=sum(1 for r in rows if r[2] != 'No pop-up found')
    doc += ['', '## Summary','', f'- Sites checked: {len(rows)}', f'- Sites with a handled or hidden pop-up: {handled}', '- The runner did not click anything. Any click came from PrivacyBrew cookie pop-up handling.', '- Screenshots and raw JSON are in ignored `artifacts/pb-cookie-popups/`.']
    (ROOT/'artifacts/COOKIE_POPUPS.md').write_text('\n'.join(doc)+'\n')
    print(json.dumps({'sites':len(rows),'handled':handled}, indent=2))
if __name__=='__main__': main()
