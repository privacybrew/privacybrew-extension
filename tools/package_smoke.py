#!/usr/bin/env python3
import contextlib, json, shutil, sys, time
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'dist' / 'package-work'
spec = importlib.util.spec_from_file_location('run_tests', str(ROOT / 'tools/run_tests.py'))
rt = importlib.util.module_from_spec(spec); spec.loader.exec_module(rt)

def latest_report(cdp, sw_session):
    obj = cdp.call('Runtime.evaluate', {'expression': 'new Promise(r=>chrome.storage.session.get(null,r))', 'awaitPromise': True, 'returnByValue': True}, sw_session)['result'].get('value') or {}
    tabs = {k:v for k,v in obj.items() if k.startswith('tab:')}
    if not tabs: return None, None
    key = sorted(tabs, key=lambda k: tabs[k].get('updatedAt', 0))[-1]
    tab_id = int(key.split(':')[1])
    expr = f"(async()=>{{const s=await getState({tab_id});const set=await getSettings();return s?applySettingsToSummary(PB.Report.summarize(s),set):null;}})()"
    report = cdp.call('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True}, sw_session)['result'].get('value') or {}
    return tab_id, report

def main():
    if not PKG.exists():
        raise SystemExit('Run tools/package.py first')
    old_ext = rt.EXT
    rt.EXT = PKG
    server = rt.start_server()
    proc = None
    try:
        proc, cdp = rt.connect_fallback()
        ext_id, sw_target = rt.find_extension(cdp)
        sw_session = rt.attach_worker(cdp, sw_target)
        target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
        session = rt.attach_target(cdp, target)
        rt.navigate_and_wait(cdp, session, f'http://site.test:{rt.PORT}/tracker.html')
        _, report = latest_report(cdp, sw_session)
        checks = []
        checks.append(('packaged trackers found', report.get('trackerRequestCount', 0) >= 5))
        checks.append(('packaged ads counted', report.get('adBlockedRequestCount', 0) >= 1))
        cookie_target = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
        cookie_session = rt.attach_target(cdp, cookie_target)
        rt.navigate_and_wait(cdp, cookie_session, f'http://site.test:{rt.PORT}/cookiebot.html')
        checks.append(('packaged cookie rejected', rt.eval_value(cdp, cookie_session, 'window.__rejectClicked === true') is True))
        popup = cdp.call('Target.createTarget', {'url': f'chrome-extension://{ext_id}/popup.html'})['targetId']
        popup_session = rt.attach_target(cdp, popup)
        cdp.call('Page.enable', sessionId=popup_session)
        rt.wait_expr(cdp, popup_session, 'document.readyState === "complete"', 10)
        current = cdp.call('Runtime.evaluate', {'expression': 'location.href', 'returnByValue': True}, popup_session)['result'].get('value', '')
        checks.append(('packaged popup renders', current.endswith('/popup.html')))
        errors = rt.service_worker_errors(cdp, [sw_session])
        checks.append(('packaged worker has no errors', errors == []))
        failed = [name for name, ok in checks if not ok]
        print(json.dumps({'pass': len(checks)-len(failed), 'fail': len(failed), 'checks': checks}, indent=2))
        if failed: raise SystemExit(1)
    finally:
        rt.EXT = old_ext
        if proc:
            with contextlib.suppress(Exception): proc.terminate(); proc.wait(timeout=5)
        server.shutdown()

if __name__ == '__main__': main()
