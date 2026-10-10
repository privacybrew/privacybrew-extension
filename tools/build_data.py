#!/usr/bin/env python3
import json, re, sys, urllib.request
from datetime import date, timezone, datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'extension' / 'data'
ICONS = ROOT / 'extension' / 'icons'
SERVICES_URL = 'https://raw.githubusercontent.com/disconnectme/disconnect-tracking-protection/master/services.json'
PSL_URL = 'https://publicsuffix.org/list/public_suffix_list.dat'
GPL_URL = 'https://www.gnu.org/licenses/gpl-3.0.txt'

CATEGORY_MAP = {
    'Advertising': 'Advertising',
    'Analytics': 'Analytics',
    'Social': 'Social',
    'Content': 'Content',
    'Disconnect': 'Social',
    'FingerprintingGeneral': 'Fingerprinting',
    'FingerprintingInvasive': 'Fingerprinting',
    'Cryptomining': 'Cryptomining',
    'CryptominingGeneral': 'Cryptomining',
    'CryptominingInvasive': 'Cryptomining',
    'Email': 'Other',
    'EmailAggressive': 'Other',
    'Anti-fraud': 'Other',
    'ConsentManagers': 'Other',
}
CATEGORY_PRIORITY = ['Advertising', 'Social', 'Analytics', 'Cryptomining', 'Fingerprinting', 'Content', 'Other']
PRIORITY_INDEX = {name: i for i, name in enumerate(CATEGORY_PRIORITY)}

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'PrivacyBrew data builder'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def normalize_domain(value):
    value = value.strip().lower().rstrip('.')
    value = re.sub(r'^https?://', '', value)
    value = value.split('/')[0].split(':')[0]
    if value.startswith('*.'):
        value = value[2:]
    return value

def parse_disconnect(raw):
    data = json.loads(raw)
    categories = data.get('categories', data)
    domains = {}
    companies = {}
    for source_cat, entries in categories.items():
        chip = CATEGORY_MAP.get(source_cat, 'Other')
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for company, payload in entry.items():
                if not isinstance(payload, dict):
                    continue
                company_id = re.sub(r'[^a-z0-9]+', '-', company.lower()).strip('-') or 'company'
                props_set = set()
                resources_set = set()
                if 'properties' in payload or 'resources' in payload:
                    props_set.update(normalize_domain(p) for p in payload.get('properties', []))
                    resources_set.update(normalize_domain(r) for r in payload.get('resources', []))
                else:
                    for prop, resources in payload.items():
                        props_set.add(normalize_domain(prop))
                        if isinstance(resources, list):
                            resources_set.update(normalize_domain(r) for r in resources)
                        elif isinstance(resources, str):
                            resources_set.add(normalize_domain(resources))
                props = sorted(p for p in props_set if p)
                resources = sorted(r for r in resources_set if r)
                companies[company_id] = {'name': company, 'properties': props}
                for domain in resources:
                    prev = domains.get(domain)
                    rec = {'companyId': company_id, 'company': company, 'category': chip, 'sourceCategory': source_cat}
                    if prev is None or PRIORITY_INDEX[chip] < PRIORITY_INDEX.get(prev['category'], 99):
                        domains[domain] = rec
    return {
        'generatedAt': datetime.now(timezone.utc).date().isoformat(),
        'source': SERVICES_URL,
        'license': 'CC-BY-NC-SA-4.0',
        'licenseText': data.get('license', ''),
        'categoryMap': CATEGORY_MAP,
        'categoryPriority': CATEGORY_PRIORITY,
        'domains': dict(sorted(domains.items())),
        'companies': dict(sorted(companies.items())),
    }

def parse_psl(text):
    normal, wildcard, exception = [], [], []
    section = 'ICANN'
    for raw in text.splitlines():
        line = raw.strip()
        if line == '// ===BEGIN PRIVATE DOMAINS===':
            section = 'PRIVATE'
            continue
        if not line or line.startswith('//'):
            continue
        bucket = normal
        body = line
        if line.startswith('!'):
            bucket = exception; body = line[1:]
        elif line.startswith('*.'):
            bucket = wildcard; body = line[2:]
        bucket.append(body.lower())
    return {
        'generatedAt': datetime.now(timezone.utc).date().isoformat(),
        'source': PSL_URL,
        'license': 'MPL-2.0',
        'normal': sorted(set(normal)),
        'wildcard': sorted(set(wildcard)),
        'exception': sorted(set(exception)),
    }

def make_icons():
    ICONS.mkdir(parents=True, exist_ok=True)
    for size in (16, 32, 48, 128):
        scale = size / 128
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = int(22 * scale)
        d.rounded_rectangle([0, 0, size-1, size-1], radius=r, fill='#1f1329', outline='#3a2c4a', width=max(1, int(3*scale)))
        # Crisp P glyph without depending on system fonts.
        x = int(38*scale); y = int(27*scale); w = max(4, int(14*scale))
        d.rounded_rectangle([x, y, x+w, int(101*scale)], radius=max(1, int(5*scale)), fill='#9b6dd1')
        d.rounded_rectangle([x, y, int(88*scale), int(63*scale)], radius=max(1, int(18*scale)), fill='#9b6dd1')
        d.rounded_rectangle([int(53*scale), int(38*scale), int(75*scale), int(52*scale)], radius=max(1, int(7*scale)), fill='#1f1329')
        img.save(ICONS / f'icon-{size}.png')

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    services_raw = fetch(SERVICES_URL).decode('utf-8')
    psl_raw = fetch(PSL_URL).decode('utf-8')
    (DATA / 'disconnect.json').write_text(json.dumps(parse_disconnect(services_raw), separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    (DATA / 'psl.json').write_text(json.dumps(parse_psl(psl_raw), separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    today = datetime.now(timezone.utc).date().isoformat()
    (DATA / 'SOURCES.md').write_text(f'''# Data sources

Fetched on {today}.

## Disconnect tracking protection data

- Source: {SERVICES_URL}
- License: CC-BY-NC-SA-4.0
- Output: `disconnect.json`
- Notes: PrivacyBrew maps Disconnect categories to plain category chips. Email and EmailAggressive map to Other. Anti-fraud and ConsentManagers map to Other. Disconnect maps to Social.
- Category priority: Advertising, Social, Analytics, Cryptomining, Fingerprinting, Content, Other. A domain in more than one category uses the highest-priority match.
- See `THIRD_PARTY_LICENSES.md`. The upstream data file includes the full license notice.

## Public Suffix List

- Source: {PSL_URL}
- License: MPL-2.0
- Output: `psl.json`
- Notes: The generated file includes ICANN and PRIVATE rules, wildcard rules, and exception rules.
''', encoding='utf-8')
    gpl = fetch(GPL_URL).decode('utf-8')
    (ROOT / 'LICENSE').write_text(gpl, encoding='utf-8')
    make_icons()
    print('Built data and icons')

if __name__ == '__main__':
    main()
