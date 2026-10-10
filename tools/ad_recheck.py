#!/usr/bin/env python3
import contextlib, json, shutil, statistics
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location('real_site_pass', str(Path(__file__).resolve().parents[1] / 'tools/real_site_pass.py'))
rsp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rsp)
ROOT = Path(__file__).resolve().parents[1]
SITES = ['youtube.com','dailymail.co.uk','forbes.com','cnn.com','allrecipes.com','weather.com','theverge.com','amazon.com','bbc.com','wikipedia.org']
OUT = ROOT / 'artifacts' / 'pb-realtest-ads'
OUT.mkdir(parents=True, exist_ok=True)
rsp.OUT = OUT

def set_ad(cdp, sw_session, enabled):
    cdp.call('Runtime.evaluate', {'expression': f'setAdBlocking({str(enabled).lower()})', 'awaitPromise': True, 'returnByValue': True}, sw_session)

def one_load(site, mode, run):
    proc = None; prof = None
    try:
        proc, cdp, ext_id, sw_session, worker_sessions, prof = rsp.launch(f'ads-{rsp.slug(site)}-{mode}-{run}', extension=True)
        rsp.set_blocking(cdp, sw_session, True)
        set_ad(cdp, sw_session, mode == 'ads-on')
        return rsp.load_page(cdp, site, f'{mode}-{run}', sw_session, ext_id, worker_sessions)
    finally:
        if proc:
            with contextlib.suppress(Exception): proc.terminate(); proc.wait(timeout=5)
        if prof and prof.exists(): shutil.rmtree(prof, ignore_errors=True)

def med(values):
    vals=[v for v in values if isinstance(v,(int,float))]
    return int(statistics.median(vals)) if vals else None

def main():
    rows=[]; results=[]
    for i, site in enumerate(SITES, 1):
        print(f'[{i}/{len(SITES)}] {site}', flush=True)
        site_results={'ads-on': [], 'ads-off': []}
        order=['ads-on','ads-off','ads-off','ads-on','ads-on','ads-off']
        for idx, mode in enumerate(order, 1):
            res=one_load(site, mode, idx)
            site_results[mode].append(res); results.append(res)
        on=site_results['ads-on']; off=site_results['ads-off']
        on_rep=max(on, key=lambda r: (r.get('report') or {}).get('adBlockedRequestCount',0)).get('report') or {}
        on_text=med([r.get('textLength') for r in on]); off_text=med([r.get('textLength') for r in off])
        on_img=med([r.get('images') for r in on]); off_img=med([r.get('images') for r in off])
        breakage='No'; note='No visible breakage found.'
        if off_text and on_text is not None and on_text < off_text*0.45:
            breakage='Check'; note='Much less text with ad blocking on.'
        rows.append({
            'site':site,
            'onDcl':med([r.get('domContentLoadedMs') for r in on]), 'offDcl':med([r.get('domContentLoadedMs') for r in off]),
            'onLoad':med([r.get('loadEventMs') for r in on]), 'offLoad':med([r.get('loadEventMs') for r in off]),
            'onReq':med([r.get('requestCount') for r in on]), 'offReq':med([r.get('requestCount') for r in off]),
            'onBytes':med([r.get('bytes') for r in on]), 'offBytes':med([r.get('bytes') for r in off]),
            'text':f'{on_text}/{off_text}', 'images':f'{on_img}/{off_img}',
            'ads':on_rep.get('adBlockedRequestCount',0), 'trackers':on_rep.get('trackerRequestCount',0),
            'breakage':breakage, 'note':note, 'cosmetic':max([((r.get('report') or {}).get('adCosmeticMaxMs') or 0) for r in on] or [0])
        })
    (OUT/'ads-recheck-results.json').write_text(json.dumps(results, indent=2))
    doc=['# Ad blocking real-site re-check 2026-10-10','', '| Site | DCL ads on/off ms | Load ads on/off ms | Requests on/off | Bytes on/off | Text on/off | Images on/off | Ads blocked | Trackers found | Breakage | Note | Cosmetic max ms |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|']
    for r in rows:
        doc.append(f"| {r['site']} | {r['onDcl']}/{r['offDcl']} | {r['onLoad']}/{r['offLoad']} | {r['onReq']}/{r['offReq']} | {r['onBytes']}/{r['offBytes']} | {r['text']} | {r['images']} | {r['ads']} | {r['trackers']} | {r['breakage']} | {r['note']} | {r['cosmetic']} |")
    dcl=[r['onDcl']-r['offDcl'] for r in rows if r['onDcl'] is not None and r['offDcl'] is not None]
    load=[r['onLoad']-r['offLoad'] for r in rows if r['onLoad'] is not None and r['offLoad'] is not None]
    req=[r['onReq']-r['offReq'] for r in rows if r['onReq'] is not None and r['offReq'] is not None]
    doc += ['', '## Summary','', f'- Sites checked: {len(rows)} with 3 fresh-profile runs per mode.', f'- Median DOMContentLoaded delta ads on vs off: {med(dcl)} ms', f'- Median load event delta ads on vs off: {med(load)} ms', f'- Median request-count delta ads on vs off: {med(req)}', f"- Highest cosmetic script time: {max(r['cosmetic'] for r in rows) if rows else 0} ms", '- YouTube homepage was checked only. This does not test or claim video-ad blocking.']
    (ROOT/'docs/ADS_RECHECK_2026-10-10.md').write_text('\n'.join(doc)+'\n')
    print(json.dumps({'sites':len(rows),'medianDclDelta':med(dcl),'medianLoadDelta':med(load),'medianRequestDelta':med(req),'maxCosmeticMs':max(r['cosmetic'] for r in rows) if rows else 0}, indent=2))
if __name__=='__main__': main()
