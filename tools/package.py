#!/usr/bin/env python3
import hashlib, json, os, re, shutil, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'extension'
DIST = ROOT / 'dist'
WORK = DIST / 'package-work'
EXCLUDE_DIRS = {'_metadata', '__pycache__'}
EXCLUDE_SUFFIXES = {'.map', '.pyc'}

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
        dest.write_bytes(data)

def manifest_files(manifest):
    files = set()
    if manifest.get('background', {}).get('service_worker'):
        files.add(manifest['background']['service_worker'])
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
    assert manifest['version'] == '1.0.0'
    for f in manifest_files(manifest):
        if not (WORK / f).exists():
            raise SystemExit(f'Manifest references missing file: {f}')
    meta = json.loads((WORK / 'rules/metadata.json').read_text())
    if meta['totalStaticRulesWithEasyList'] > meta['staticRuleCap']:
        raise SystemExit('Rule total exceeds cap')
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

def make_zip(manifest):
    version = manifest['version']
    out = DIST / f'privacybrew-extension-{version}.zip'
    if out.exists(): out.unlink()
    files = [p for p in WORK.rglob('*') if p.is_file()]
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            z.write(p, p.relative_to(WORK).as_posix())
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(json.dumps({'zip': str(out), 'files': len(files), 'bytes': out.stat().st_size, 'sha256': digest}, indent=2))
    return out, files, digest

def main():
    DIST.mkdir(exist_ok=True)
    copy_tree()
    manifest, meta = validate()
    make_zip(manifest)

if __name__ == '__main__': main()
