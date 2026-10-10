#!/usr/bin/env python3
import json, shutil, contextlib, subprocess, time
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location('real_site_pass', str(Path(__file__).resolve().parents[1] / 'tools/real_site_pass.py'))
rsp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rsp)
ROOT = Path(__file__).resolve().parents[1]
SITES = ['youtube.com','dailymail.co.uk','forbes.com','cnn.com','allrecipes.com','weather.com','theverge.com','amazon.com','bbc.com','wikipedia.org']
OUT = ROOT / 'artifacts' / 'pb-realtest-ads'
OUT.mkdir(parents=True, exist_ok=True)
# Reuse real_site_pass output dir so screenshots land in existing ignored folder for review too.
rsp.OUT = OUT

def set_ad(cdp, sw_session, enabled):
    cdp.call('Runtime.evaluate', {'expression': f'setAdBlocking({str(enabled).lower()})', 'awaitPromise': True, 'returnByValue': True}, sw_session)

def main():
    proc = None; profiles=[]; rows=[]; results=[]
    try:
        proc, cdp, ext_id, sw_session, worker_sessions, prof = rsp.launch('ads-recheck', extension=True); profiles.append(prof)
        for i, site in enumerate(SITES, 1):
            print(f'[{i}/{len(SITES)}] {site}', flush=True)
            rsp.set_blocking(cdp, sw_session, True); set_ad(cdp, sw_session, True)
            on = rsp.load_page(cdp, site, 'ads-on', sw_session, ext_id, worker_sessions); results.append(on)
            rsp.set_blocking(cdp, sw_session, True); set_ad(cdp, sw_session, False)
            off = rsp.load_page(cdp, site, 'ads-off', sw_session, ext_id, worker_sessions); results.append(off)
            rep_on, rep_off = on.get('report',{}), off.get('report',{})
            breakage = 'No'
            note = 'No visible breakage found.'
            if off.get('textLength') and on.get('textLength',0) < off['textLength'] * 0.45:
                breakage = 'Check'; note = 'Much less text with ad blocking on.'
            rows.append([site,on.get('idleTimeMs'),off.get('idleTimeMs'),on.get('textLength'),off.get('textLength'),on.get('images'),off.get('images'),rep_on.get('adBlockedRequestCount',0),rep_on.get('trackerRequestCount',0),breakage,note,rep_on.get('adCosmeticMaxMs',0)])
    finally:
        if proc:
            with contextlib.suppress(Exception): proc.terminate(); proc.wait(timeout=5)
        for p in profiles:
            if p.exists(): shutil.rmtree(p, ignore_errors=True)
    (OUT / 'ads-recheck-results.json').write_text(json.dumps(results, indent=2))
    doc = ['# Ad blocking real-site re-check 2026-10-10','','| Site | Ads on idle ms | Ads off idle ms | Text on/off | Images on/off | Ads blocked | Trackers found | Breakage | Note | Cosmetic max ms |','|---|---:|---:|---:|---:|---:|---:|---|---|---:|']
    for r in rows:
        doc.append(f'| {r[0]} | {r[1]} | {r[2]} | {r[3]}/{r[4]} | {r[5]}/{r[6]} | {r[7]} | {r[8]} | {r[9]} | {r[10]} | {r[11]} |')
    vals=[r[1]-r[2] for r in rows if isinstance(r[1],int) and isinstance(r[2],int)]
    doc += ['', '## Summary','', f'- Sites checked: {len(rows)}', f'- Median ads-on idle delta vs ads-off: {sorted(vals)[len(vals)//2] if vals else None} ms', f'- Worst ads-on idle delta vs ads-off: {max(vals) if vals else None} ms', f'- Highest cosmetic script time: {max(r[11] for r in rows) if rows else 0} ms', '- YouTube homepage was checked only. This does not test or claim video-ad blocking.']
    (ROOT / 'docs/ADS_RECHECK_2026-10-10.md').write_text('\n'.join(doc)+'\n')
    print(json.dumps({'sites': len(rows), 'maxCosmeticMs': max(r[11] for r in rows) if rows else 0}, indent=2))
if __name__ == '__main__': main()
