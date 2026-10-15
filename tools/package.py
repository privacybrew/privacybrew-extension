#!/usr/bin/env python3
# Usage: python3 tools/package.py [--target chrome|firefox]
# chrome (default): dist/privacybrew-extension-<version>.zip from dist/package-work/
# firefox: dist/privacybrew-extension-firefox-<version>.zip from dist/package-work-firefox/
import argparse, hashlib, json, os, re, shutil, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'extension'
DIST = ROOT / 'dist'
WORK = DIST / 'package-work'
EXCLUDE_DIRS = {'_metadata', '__pycache__'}
EXCLUDE_SUFFIXES = {'.map', '.pyc'}
TARGET = 'chrome'

# Icon sizes that only the Firefox manifest uses. The Chrome ZIP keeps its original file set.
FIREFOX_ONLY_FILES = {'icons/icon-64.png', 'icons/icon-96.png'}
GECKO_ID = 'privacybrew@privacybrew.app'
# 140 is the first Firefox (and an ESR) with data_collection_permissions, which AMO
# requires for new add-ons. Everything else needs 128 or lower: content_scripts world,
# scripting world MAIN, matchOriginAsFallback and DNR domainType are 128; storage.session
# is 115; DNR requestDomains/initiatorDomains/modifyHeaders/session rules are 113.
GECKO_MIN_VERSION = '140.0'
# Firefox for Android supports data_collection_permissions from 142.
GECKO_ANDROID_MIN_VERSION = '142.0'
# Firefox DNR does not know these resource types and rejects rules that use them.
FIREFOX_UNSUPPORTED_RESOURCE_TYPES = {'webtransport', 'webbundle'}
FIREFOX_BACKGROUND_SCRIPTS = ['lib/psl.js', 'lib/disconnect.js', 'lib/report.js', 'background.js']

DEBUG_BLOCK = re.compile(r'\n?\s*// DEBUG_START\n.*?\n\s*// DEBUG_END\n?', re.S)

def copy_tree():
    if WORK.exists(): shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    for src in SRC.rglob('*'):
        rel = src.relative_to(SRC)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if src.is_dir():
            continue
        if src.suffix in EXCLUDE_SUFFIXES or src.name == '.DS_Store':
            continue
        if TARGET == 'chrome' and rel.as_posix() in FIREFOX_ONLY_FILES:
            continue
        dest = WORK / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        if rel.as_posix() == 'background.js':
            text = data.decode('utf-8')
            text = text.replace('const DEBUG_REPORT_MESSAGES = true;', 'const DEBUG_REPORT_MESSAGES = false;')
            text = DEBUG_BLOCK.sub('\n', text)
            data = text.encode('utf-8')
        if rel.as_posix() == 'popup.js':
            text = data.decode('utf-8')
            text = text.replace('const DEBUG_POPUP_TAB_OVERRIDE = true;', 'const DEBUG_POPUP_TAB_OVERRIDE = false;')
            data = text.encode('utf-8')
        if TARGET == 'firefox' and rel.as_posix() == 'manifest.json':
            data = (json.dumps(firefox_manifest(json.loads(data)), indent=2) + '\n').encode('utf-8')
        if TARGET == 'firefox' and rel.parts[0] == 'rules' and rel.name != 'metadata.json':
            data = json.dumps(firefox_rules(json.loads(data)), separators=(',', ':')).encode('utf-8')
        dest.write_bytes(data)

def firefox_manifest(chrome):
    m = dict(chrome)
    m.pop('minimum_chrome_version', None)
    m['background'] = {'scripts': list(FIREFOX_BACKGROUND_SCRIPTS)}
    icons = dict(m['icons']); icons['64'] = 'icons/icon-64.png'; icons['96'] = 'icons/icon-96.png'
    m['icons'] = dict(sorted(icons.items(), key=lambda kv: int(kv[0])))
    action = dict(m['action']); default_icon = dict(action['default_icon'])
    default_icon['64'] = 'icons/icon-64.png'; default_icon['96'] = 'icons/icon-96.png'
    action['default_icon'] = dict(sorted(default_icon.items(), key=lambda kv: int(kv[0])))
    m['action'] = action
    m['browser_specific_settings'] = {
        'gecko': {
            'id': GECKO_ID,
            'strict_min_version': GECKO_MIN_VERSION,
            'data_collection_permissions': {'required': ['none']}
        },
        'gecko_android': {'strict_min_version': GECKO_ANDROID_MIN_VERSION}
    }
    return m

def firefox_rules(rules):
    out = []
    for rule in rules:
        rule = json.loads(json.dumps(rule))
        cond = rule.get('condition', {})
        for key in ['resourceTypes', 'excludedResourceTypes']:
            if key in cond:
                cond[key] = [t for t in cond[key] if t not in FIREFOX_UNSUPPORTED_RESOURCE_TYPES]
                if not cond[key]:
                    if key == 'resourceTypes':
                        rule = None
                        break
                    del cond[key]
        if rule is not None:
            out.append(rule)
    return out

def manifest_files(manifest):
    files = set()
    if manifest.get('background', {}).get('service_worker'):
        files.add(manifest['background']['service_worker'])
    for script in manifest.get('background', {}).get('scripts', []):
        files.add(script)
    action = manifest.get('action', {})
    if action.get('default_popup'): files.add(action['default_popup'])
    for icon_map in [action.get('default_icon', {}), manifest.get('icons', {})]:
        for v in icon_map.values(): files.add(v)
    for cs in manifest.get('content_scripts', []):
        for js in cs.get('js', []): files.add(js)
        for css in cs.get('css', []): files.add(css)
    for rr in manifest.get('declarative_net_request', {}).get('rule_resources', []):
        files.add(rr['path'])
    for war in manifest.get('web_accessible_resources', []):
        for res in war.get('resources', []): files.add(res)
    return files

def validate():
    manifest = json.loads((WORK / 'manifest.json').read_text())
    assert manifest['manifest_version'] == 3
    assert re.fullmatch(r'\d+\.\d+\.\d+', manifest['version']), manifest['version']
    for f in manifest_files(manifest):
        if not (WORK / f).exists():
            raise SystemExit(f'Manifest references missing file: {f}')
    meta = json.loads((WORK / 'rules/metadata.json').read_text())
    if meta['totalStaticRulesWithEasyList'] > meta['staticRuleCap']:
        raise SystemExit('Rule total exceeds cap')
    if TARGET == 'chrome':
        if 'service_worker' not in manifest['background'] or 'browser_specific_settings' in manifest:
            raise SystemExit('Chrome manifest must use a service worker and no Gecko settings')
        for f in FIREFOX_ONLY_FILES:
            if (WORK / f).exists(): raise SystemExit(f'Firefox-only file in Chrome package: {f}')
    if TARGET == 'firefox':
        validate_firefox(manifest)
    for rel in [p.relative_to(WORK).as_posix() for p in WORK.rglob('*') if p.is_file()]:
        text = None
        path = WORK / rel
        try: text = path.read_text('utf-8')
        except Exception: continue
        if '/home/' in text:
            raise SystemExit(f'Personal path found in {rel}')
        if rel not in {'data/psl.json', 'lib/psl.js'} and ('localhost' in text or '127.0.0.1' in text or any(x in text for x in ['site.test', 'clean.test', '.test/', '.test:'])):
            raise SystemExit(f'Test host found in {rel}')
        if rel.endswith(('.js', '.html', '.json')) and ('debugGetReport' in text or 'tabId=' in text):
            raise SystemExit(f'Debug hook found in {rel}')
        if rel.endswith(('.js', '.html')) and re.search(r'<script[^>]+https?://', text, re.I):
            raise SystemExit(f'Remote script URL found in {rel}')
        if rel.endswith('.js') and ('eval(' in text or 'new Function' in text):
            # Autoconsent is vendored MPL code. It uses fixed snippets bundled with the extension.
            if not (rel.startswith('vendor/autoconsent/') or rel == 'background.js'):
                raise SystemExit(f'Dynamic eval found in {rel}')
    return manifest, meta

def validate_firefox(manifest):
    if 'service_worker' in manifest['background'] or manifest['background'].get('scripts') != FIREFOX_BACKGROUND_SCRIPTS:
        raise SystemExit('Firefox manifest must use background.scripts')
    if 'minimum_chrome_version' in manifest:
        raise SystemExit('Firefox manifest must not have minimum_chrome_version')
    gecko = manifest.get('browser_specific_settings', {}).get('gecko', {})
    if gecko.get('id') != GECKO_ID or gecko.get('strict_min_version') != GECKO_MIN_VERSION:
        raise SystemExit('Firefox manifest has wrong Gecko id or version')
    if gecko.get('data_collection_permissions') != {'required': ['none']}:
        raise SystemExit('Firefox manifest must declare no data collection')
    if manifest.get('browser_specific_settings', {}).get('gecko_android', {}).get('strict_min_version') != GECKO_ANDROID_MIN_VERSION:
        raise SystemExit('Firefox manifest has wrong Android version')
    if manifest.get('host_permissions') != ['*://*/*']:
        raise SystemExit('Firefox manifest host permissions changed')
    chrome = json.loads((SRC / 'manifest.json').read_text())
    for key in ['name', 'description', 'version', 'homepage_url', 'permissions', 'content_scripts', 'declarative_net_request', 'web_accessible_resources']:
        if manifest.get(key) != chrome.get(key):
            raise SystemExit(f'Firefox manifest differs from Chrome manifest in {key}')
    # The background page loads these with <script> tags in order. background.js must not
    # call importScripts unguarded, because it does not exist in a Firefox background page.
    bg = (WORK / 'background.js').read_text()
    if re.search(r'^importScripts\(', bg, re.M):
        raise SystemExit('background.js calls importScripts without a guard')
    total = 0
    for rr in manifest['declarative_net_request']['rule_resources']:
        rules = json.loads((WORK / rr['path']).read_text())
        total += len(rules)
        for rule in rules:
            cond = rule.get('condition', {})
            bad = set(cond.get('resourceTypes', []) + cond.get('excludedResourceTypes', [])) & FIREFOX_UNSUPPORTED_RESOURCE_TYPES
            if bad: raise SystemExit(f'{rr["path"]} rule {rule.get("id")} uses {sorted(bad)}')
    # Firefox guarantees 30000 static rules (GUARANTEED_MINIMUM_STATIC_RULES).
    if total > 30000:
        raise SystemExit(f'Firefox static rules {total} exceed 30000')

def make_zip(manifest):
    version = manifest['version']
    name = f'privacybrew-extension-firefox-{version}.zip' if TARGET == 'firefox' else f'privacybrew-extension-{version}.zip'
    out = DIST / name
    if out.exists(): out.unlink()
    files = [p for p in WORK.rglob('*') if p.is_file()]
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            z.write(p, p.relative_to(WORK).as_posix())
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(json.dumps({'zip': str(out), 'files': len(files), 'bytes': out.stat().st_size, 'sha256': digest}, indent=2))
    return out, files, digest

def main():
    global TARGET, WORK
    parser = argparse.ArgumentParser(description='Build the PrivacyBrew store ZIP.')
    parser.add_argument('--target', choices=['chrome', 'firefox'], default='chrome')
    TARGET = parser.parse_args().target
    if TARGET == 'firefox':
        WORK = DIST / 'package-work-firefox'
    DIST.mkdir(exist_ok=True)
    copy_tree()
    manifest, meta = validate()
    make_zip(manifest)

if __name__ == '__main__': main()
