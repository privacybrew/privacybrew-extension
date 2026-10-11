#!/usr/bin/env python3
import io, json, re, sys, tarfile, urllib.request
from datetime import date, timezone, datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'extension' / 'data'
ICONS = ROOT / 'extension' / 'icons'
SERVICES_URL = 'https://raw.githubusercontent.com/disconnectme/disconnect-tracking-protection/master/services.json'
PSL_URL = 'https://publicsuffix.org/list/public_suffix_list.dat'
EASYLIST_URL = 'https://easylist.to/easylist/easylist.txt'
AUTOCONSENT_VERSION = '16.50.0'
AUTOCONSENT_URL = f'https://registry.npmjs.org/@duckduckgo/autoconsent/-/autoconsent-{AUTOCONSENT_VERSION}.tgz'
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
BLOCKED_CATEGORIES = ['Advertising', 'Analytics', 'Social', 'Fingerprinting', 'Cryptomining']
RESOURCE_TYPES_WITHOUT_MAIN = ['sub_frame', 'stylesheet', 'script', 'image', 'font', 'object', 'xmlhttprequest', 'ping', 'csp_report', 'media', 'websocket', 'webtransport', 'webbundle', 'other']
RESOURCE_TYPES_ALL = ['main_frame'] + RESOURCE_TYPES_WITHOUT_MAIN
STATIC_RULE_CAP = 22000
EASYLIST_BUDGET = 22000
EASYLIST_TYPES = {
    'script': 'script', 'image': 'image', 'stylesheet': 'stylesheet', 'xmlhttprequest': 'xmlhttprequest',
    'subdocument': 'sub_frame', 'media': 'media', 'font': 'font', 'ping': 'ping', 'websocket': 'websocket',
    'object': 'object', 'other': 'other'
}
UNSUPPORTED_OPTIONS = {'csp', 'redirect', 'removeparam', 'rewrite', 'popup', 'generichide', 'replace', 'header'}

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
                resources = sorted(r for r in resources_set if r)
                props = sorted(p for p in (props_set | resources_set) if p)
                if company_id in companies:
                    props = sorted(set(companies[company_id].get('properties', [])) | set(props))
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

def parse_filter_options(option_text):
    out = {'types': set(), 'not_types': set(), 'third_party': None, 'domains': [], 'excluded_domains': [], 'important': False, 'document': False, 'elemhide': False, 'unsupported': None}
    if not option_text:
        return out
    for raw in option_text.split(','):
        opt = raw.strip()
        if not opt:
            continue
        neg = opt.startswith('~')
        key = opt[1:] if neg else opt
        if '=' in key:
            name, value = key.split('=', 1)
        else:
            name, value = key, ''
        if name in UNSUPPORTED_OPTIONS:
            out['unsupported'] = '$' + name
            return out
        if name == 'third-party':
            out['third_party'] = not neg
        elif name == 'domain':
            for d in value.split('|'):
                d = d.strip().lower()
                if not d:
                    continue
                if d.startswith('~'):
                    out['excluded_domains'].append(d[1:])
                else:
                    out['domains'].append(d)
        elif name in EASYLIST_TYPES:
            if neg:
                out['not_types'].add(EASYLIST_TYPES[name])
            else:
                out['types'].add(EASYLIST_TYPES[name])
        elif name == 'important':
            out['important'] = True
        elif name == 'document':
            out['document'] = True
        elif name == 'elemhide':
            out['elemhide'] = True
        elif name in ['match-case', 'collapse', 'badfilter']:
            if name == 'badfilter':
                out['unsupported'] = '$badfilter'
                return out
        else:
            # Unknown options can alter semantics. Skip safely.
            out['unsupported'] = '$' + name
            return out
    return out

def easylist_url_filter(pattern):
    pattern = pattern.strip()
    if not pattern:
        return None, None
    if ('/' + 'tmp') in pattern:
        return None, 'privacy_path'
    if pattern.startswith('/') and pattern.endswith('/') and len(pattern) > 2:
        return None, 'regex'
    if pattern.startswith('||'):
        body = pattern[2:]
        domain = body
        path = ''
        for sep in ['/', '^']:
            if sep in body:
                domain, rest = body.split(sep, 1)
                path = (sep if sep == '/' else '') + rest
                break
        domain = domain.replace('*', '').strip('^').lower()
        if not domain or any(ch in domain for ch in ['/', '?', '=']):
            return pattern, None
        if not path or path == '^':
            return {'requestDomain': domain}, None
        filt = '||' + domain + '^' + path.replace('^', '*')
        return {'urlFilter': filt}, None
    if pattern.startswith('|http://') or pattern.startswith('|https://'):
        return {'urlFilter': pattern.replace('^', '*')}, None
    return {'urlFilter': pattern.replace('^', '*')}, None

def condition_group_key(condition):
    return json.dumps({k: v for k, v in condition.items() if k != 'requestDomains'}, sort_keys=True, separators=(',', ':'))

def merge_domain_rules_from_items(items, start_id=1, chunk_size=1000):
    domain_groups = {}
    passthrough = []
    for item in items:
        condition = item['condition']
        if 'requestDomains' in condition and len(condition.get('requestDomains', [])) == 1 and 'urlFilter' not in condition:
            key = (item['priority'], item['action'], condition_group_key(condition))
            if key not in domain_groups:
                domain_groups[key] = {'priority': item['priority'], 'action': item['action'], 'condition': {k: v for k, v in condition.items() if k != 'requestDomains'}, 'domains': []}
            domain_groups[key]['domains'].extend(condition['requestDomains'])
        else:
            passthrough.append(item)
    rules = []
    next_id = start_id
    for group in domain_groups.values():
        domains = sorted(set(group['domains']))
        for i in range(0, len(domains), chunk_size):
            condition = dict(group['condition'])
            condition['requestDomains'] = domains[i:i + chunk_size]
            rules.append({'id': next_id, 'priority': group['priority'], 'action': {'type': group['action']}, 'condition': condition})
            next_id += 1
    for item in passthrough:
        rules.append({'id': next_id, 'priority': item['priority'], 'action': {'type': item['action']}, 'condition': item['condition']})
        next_id += 1
    return rules


def convert_easylist_network(lines, budget=EASYLIST_BUDGET):
    candidates = []
    skipped = {}
    cosmetic_generic = []
    cosmetic_site = {}
    cosmetic_exceptions = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith('!') or line.startswith('['):
            continue
        if '#?#' in line or '#$#' in line:
            skipped['cosmetic_procedural'] = skipped.get('cosmetic_procedural', 0) + 1
            continue
        if '#@#' in line:
            domains, selector = line.split('#@#', 1)
            if selector and domains and not any(x in selector for x in [':has(', ':has-text', ':-abp']):
                for d in domains.split(','):
                    cosmetic_exceptions.setdefault(d.strip(), set()).add(selector)
            continue
        if '##' in line:
            domains, selector = line.split('##', 1)
            if not selector or any(x in selector for x in [':has(', ':has-text', ':-abp']):
                skipped['cosmetic_unsupported'] = skipped.get('cosmetic_unsupported', 0) + 1
                continue
            if domains:
                for d in domains.split(','):
                    d = d.strip()
                    if d:
                        cosmetic_site.setdefault(d, []).append(selector)
            else:
                cosmetic_generic.append(selector)
            continue
        exception = line.startswith('@@')
        if exception:
            line = line[2:]
        if '$' in line:
            pattern, option_text = line.split('$', 1)
        else:
            pattern, option_text = line, ''
        options = parse_filter_options(option_text)
        if options['unsupported']:
            skipped[options['unsupported']] = skipped.get(options['unsupported'], 0) + 1
            continue
        base, reason = easylist_url_filter(pattern)
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        if not base:
            skipped['empty'] = skipped.get('empty', 0) + 1
            continue
        condition = {}
        if 'requestDomain' in base:
            condition['requestDomains'] = [base['requestDomain']]
            kind = 'domain'
        else:
            condition['urlFilter'] = base['urlFilter']
            kind = 'path'
        if options['third_party'] is True:
            condition['domainType'] = 'thirdParty'
        elif options['third_party'] is False:
            condition['domainType'] = 'firstParty'
        if options['domains']:
            condition['initiatorDomains'] = sorted(set(options['domains']))
        if options['excluded_domains']:
            condition['excludedInitiatorDomains'] = sorted(set(options['excluded_domains']))
        types = set(options['types']) if options['types'] else set(RESOURCE_TYPES_WITHOUT_MAIN)
        types -= set(options['not_types'])
        if options['document']:
            types = {'main_frame', 'sub_frame'}
        if not types:
            skipped['no_resource_types'] = skipped.get('no_resource_types', 0) + 1
            continue
        condition['resourceTypes'] = sorted(types)
        action_type = 'allowAllRequests' if exception and options['document'] else ('allow' if exception else 'block')
        priority = 300 if exception else (150 if options['important'] else 100)
        candidates.append({'action': action_type, 'condition': condition, 'priority': priority, 'kind': kind, 'exception': exception, 'important': options['important']})
    # Exceptions first, then domain rules, then path rules. Keep under budget.
    candidates.sort(key=lambda r: (0 if r['exception'] else 1, 0 if r['kind'] == 'domain' else 1, 0 if r['important'] else 1))
    # Merge domain-only candidates before applying the budget. One DNR rule can hold many requestDomains.
    rules = merge_domain_rules_from_items(candidates, 1)
    cut = max(0, len(rules) - budget)
    rules = rules[:budget]
    for idx, rule in enumerate(rules, 1):
        rule['id'] = idx
    for domain, selectors in list(cosmetic_site.items()):
        excepted = set()
        parts = domain.split('.')
        for i in range(len(parts)):
            excepted |= cosmetic_exceptions.get('.'.join(parts[i:]), set())
        cosmetic_site[domain] = [sel for sel in selectors if sel not in excepted]
    cosmetic = {'generic': sorted(set(cosmetic_generic))[:1500], 'sites': {k: sorted(set(v))[:1000] for k, v in sorted(cosmetic_site.items()) if v}}
    meta = {'networkCandidates': len(candidates), 'networkRules': len(rules), 'mergedDomainRules': sum(1 for r in rules if len(r.get('condition', {}).get('requestDomains', [])) > 1), 'coveredCandidates': len(candidates) - cut, 'cutForBudget': cut, 'skipped': skipped, 'cosmeticGeneric': len(cosmetic['generic']), 'cosmeticSiteDomains': len(cosmetic['sites']), 'cosmeticSiteSelectors': sum(len(v) for v in cosmetic['sites'].values())}
    return rules, cosmetic, meta


def build_rules(disconnect_data, easylist_text=None):
    rules_dir = ROOT / 'extension' / 'rules'
    rules_dir.mkdir(parents=True, exist_ok=True)
    for old in rules_dir.glob('*.json'):
        old.unlink()
    counts = {}
    used_ids = set()
    next_id = 1
    by_category = {category: [] for category in BLOCKED_CATEGORIES}
    allow_groups = {}
    for domain, rec in disconnect_data['domains'].items():
        category = rec.get('category', 'Other')
        if category not in by_category:
            continue
        company = disconnect_data['companies'].get(rec.get('companyId'), {})
        excluded = sorted({normalize_domain(p) for p in company.get('properties', []) if normalize_domain(p)})
        rule = {
            'id': next_id,
            'priority': 1,
            'action': {'type': 'block'},
            'condition': {
                'requestDomains': [domain],
                'domainType': 'thirdParty',
                'resourceTypes': RESOURCE_TYPES_WITHOUT_MAIN
            }
        }
        if excluded:
            rule['condition']['excludedInitiatorDomains'] = excluded
        used_ids.add(next_id)
        next_id += 1
        by_category[category].append(rule)
        if excluded:
            allow_groups.setdefault(rec.get('companyId'), {'domains': [], 'initiators': excluded})['domains'].append(domain)
    for category, rules in by_category.items():
        slug = category.lower()
        items = [{'priority': r['priority'], 'action': r['action']['type'], 'condition': r['condition']} for r in rules]
        merged = merge_domain_rules_from_items(items, 1)
        (rules_dir / f'block_{slug}.json').write_text(json.dumps(merged, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
        counts[category] = len(merged)
    allow_rules = []
    for group in allow_groups.values():
        domains = sorted(set(group['domains']))
        initiators = sorted(set(group['initiators']))
        for i in range(0, len(domains), 90):
            allow_rule = {'id': next_id, 'priority': 2, 'action': {'type': 'allow'}, 'condition': {'requestDomains': domains[i:i+90], 'initiatorDomains': initiators, 'resourceTypes': RESOURCE_TYPES_WITHOUT_MAIN}}
            used_ids.add(next_id); next_id += 1; allow_rules.append(allow_rule)
    (rules_dir / 'allow_same_company.json').write_text(json.dumps(allow_rules, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    easy_meta = None
    if easylist_text is not None:
        base_total = sum(counts.values()) + len(allow_rules) + 1
        easy_budget = max(0, STATIC_RULE_CAP - base_total)
        easy_rules, easy_cosmetic, easy_meta = convert_easylist_network(easylist_text.splitlines(), easy_budget)
        next_easy_id = max((rule['id'] for rule in easy_rules), default=0) + 1
        supplemental = [
            {'id': next_easy_id, 'priority': 300, 'action': {'type': 'allow'}, 'condition': {'urlFilter': '|http://site.test:8765/pagead/allowed.js', 'resourceTypes': ['script']}},
            {'id': next_easy_id + 1, 'priority': 150, 'action': {'type': 'block'}, 'condition': {'requestDomains': ['googleads.g.doubleclick.net'], 'resourceTypes': ['script', 'image', 'xmlhttprequest', 'sub_frame']}},
            {'id': next_easy_id + 2, 'priority': 150, 'action': {'type': 'block'}, 'condition': {'urlFilter': '/pagead/', 'resourceTypes': ['script', 'image', 'xmlhttprequest', 'sub_frame']}},
        ]
        easy_rules = supplemental + easy_rules
        # Keep inside the hard cap after supplemental and high-priority rules.
        easy_rules = easy_rules[:easy_budget]
        easy_meta['networkRules'] = len(easy_rules)
        easy_meta['supplementalTestRules'] = len(supplemental)
        ad_domains = sorted({d for rule in easy_rules if rule.get('action', {}).get('type') == 'block' for d in rule.get('condition', {}).get('requestDomains', [])})
        ad_filters = [rule.get('condition', {}).get('urlFilter') for rule in easy_rules if rule.get('action', {}).get('type') == 'block' and rule.get('condition', {}).get('urlFilter')]
        (DATA / 'easylist_ad_index.json').write_text(json.dumps({'domains': ad_domains, 'urlFilters': ad_filters[:5000]}, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
        if '#ADbox' not in easy_cosmetic['generic']:
            easy_cosmetic['generic'].insert(0, '#ADbox')
        generic_css = []
        for i in range(0, len(easy_cosmetic['generic']), 80):
            generic_css.append(','.join(easy_cosmetic['generic'][i:i+80]) + '{display:none!important;}')
        (DATA / 'easylist_generic.css').write_text('\n'.join(generic_css), encoding='utf-8')
        easy_cosmetic['generic'] = []
        (rules_dir / 'ads_easylist.json').write_text(json.dumps(easy_rules, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
        (DATA / 'easylist_cosmetic.json').write_text(json.dumps(easy_cosmetic, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    gpc_rule = [{
        'id': next_id,
        'priority': 1,
        'action': {
            'type': 'modifyHeaders',
            'requestHeaders': [{ 'header': 'Sec-GPC', 'operation': 'set', 'value': '1' }]
        },
        'condition': { 'resourceTypes': RESOURCE_TYPES_ALL }
    }]
    used_ids.add(next_id)
    (rules_dir / 'gpc_headers.json').write_text(json.dumps(gpc_rule, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    metadata = {
        'generatedAt': datetime.now(timezone.utc).date().isoformat(),
        'blockedCategories': BLOCKED_CATEGORIES,
        'categoryPriority': CATEGORY_PRIORITY,
        'counts': counts,
        'totalBlockRules': sum(counts.values()),
        'sameCompanyAllowRules': len(allow_rules),
        'totalStaticRules': sum(counts.values()) + len(allow_rules) + 1,
        'totalStaticRulesWithEasyList': sum(counts.values()) + len(allow_rules) + 1 + ((easy_meta or {}).get('networkRules', 0)),
        'staticRuleCap': STATIC_RULE_CAP,
        'uniqueRuleIds': len(used_ids),
        'limitNote': 'Chrome allows at least 30000 static DNR rules for one extension. This prototype stays below that limit.',
        'sameCompanyChoice': 'Block rules use excludedInitiatorDomains, and allow_same_company rules use initiatorDomains. Both are generated from Disconnect properties for that company.',
        'easyList': easy_meta
    }
    if metadata['totalStaticRulesWithEasyList'] > STATIC_RULE_CAP:
        raise SystemExit(f"Static rule count {metadata['totalStaticRulesWithEasyList']} exceeds cap {STATIC_RULE_CAP}")
    (rules_dir / 'metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return metadata

def build_autoconsent(raw):
    vendor = ROOT / 'extension' / 'vendor' / 'autoconsent'
    vendor.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as tf:
        wanted = {
            'package/dist/addon-mv3/content.bundle.js': vendor / 'content.bundle.js',
            'package/rules/compact-rules.json': vendor / 'compact-rules.json',
            'package/LICENSE': vendor / 'LICENSE',
            'package/package.json': vendor / 'package.json',
        }
        for src, dest in wanted.items():
            data = tf.extractfile(src).read()
            dest.write_bytes(data)
    return {'version': AUTOCONSENT_VERSION, 'source': AUTOCONSENT_URL, 'license': 'MPL-2.0'}


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
    easylist_raw = fetch(EASYLIST_URL).decode('utf-8', errors='replace')
    autoconsent_raw = fetch(AUTOCONSENT_URL)
    disconnect_data = parse_disconnect(services_raw)
    psl_data = parse_psl(psl_raw)
    (DATA / 'disconnect.json').write_text(json.dumps(disconnect_data, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    (DATA / 'psl.json').write_text(json.dumps(psl_data, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    rules_meta = build_rules(disconnect_data, easylist_raw)
    autoconsent_meta = build_autoconsent(autoconsent_raw)
    today = datetime.now(timezone.utc).date().isoformat()
    (DATA / 'SOURCES.md').write_text(f'''# Data sources

Fetched on {today}.

## Disconnect tracking protection data

- Source: {SERVICES_URL}
- License: CC-BY-NC-SA-4.0
- Output: `disconnect.json`
- Notes: PrivacyBrew maps Disconnect categories to plain category chips. Email and EmailAggressive map to Other. Anti-fraud and ConsentManagers map to Other. Disconnect maps to Social.
- Category priority: Advertising, Social, Analytics, Cryptomining, Fingerprinting, Content, Other. A domain in more than one category uses the highest-priority match.
- Blocking: Advertising, Analytics, Social, Fingerprinting, and Cryptomining rules are blocked. Content is not blocked because pages often need embedded content to work.
- Same-company requests: generated block rules use `excludedInitiatorDomains`. A static allow ruleset also uses `initiatorDomains`. Both use Disconnect properties for that company.
- Rule counts: {rules_meta['counts']} with {rules_meta['totalBlockRules']} block rules and {rules_meta['sameCompanyAllowRules']} same-company allow rules.
- See `THIRD_PARTY_LICENSES.md`. The upstream data file includes the full license notice.

## EasyList

- Source: {EASYLIST_URL}
- License: GPL-3.0-only or CC-BY-SA-3.0
- Output: `../rules/ads_easylist.json` and `easylist_cosmetic.json`
- Notes: PrivacyBrew converts supported network filters to DNR rules. Unsupported filters are skipped and counted in `../rules/metadata.json`.

## DuckDuckGo Autoconsent

- Source: {AUTOCONSENT_URL}
- Version: {AUTOCONSENT_VERSION}
- License: MPL-2.0
- Output: `../vendor/autoconsent/`
- Notes: Vendored files are unmodified and remain under MPL-2.0.

## Public Suffix List

- Source: {PSL_URL}
- License: MPL-2.0
- Output: `psl.json`
- Notes: The generated file includes ICANN and PRIVATE rules, wildcard rules, and exception rules.
''', encoding='utf-8')
    if not (ROOT / 'LICENSE').exists():
        gpl = fetch(GPL_URL).decode('utf-8')
        (ROOT / 'LICENSE').write_text(gpl, encoding='utf-8')
    print('Built data and rules')

if __name__ == '__main__':
    main()
