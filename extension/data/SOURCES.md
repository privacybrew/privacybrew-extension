# Data sources

Fetched on 2026-10-11.

## Disconnect tracking protection data

- Source: https://raw.githubusercontent.com/disconnectme/disconnect-tracking-protection/master/services.json
- License: CC-BY-NC-SA-4.0
- Output: `disconnect.json`
- Notes: PrivacyBrew maps Disconnect categories to plain category chips. Email and EmailAggressive map to Other. Anti-fraud and ConsentManagers map to Other. Disconnect maps to Social.
- Category priority: Advertising, Social, Analytics, Cryptomining, Fingerprinting, Content, Other. A domain in more than one category uses the highest-priority match.
- Blocking: Advertising, Analytics, Social, Fingerprinting, and Cryptomining rules are blocked. Content is not blocked because pages often need embedded content to work.
- Same-company requests: generated block rules use `excludedInitiatorDomains`. A static allow ruleset also uses `initiatorDomains`. Both use Disconnect properties for that company.
- Rule counts: {'Advertising': 1273, 'Analytics': 358, 'Social': 14, 'Fingerprinting': 169, 'Cryptomining': 14} with 1828 block rules and 1719 same-company allow rules.
- See `THIRD_PARTY_LICENSES.md`. The upstream data file includes the full license notice.

## EasyList

- Source: https://easylist.to/easylist/easylist.txt
- License: GPL-3.0-only or CC-BY-SA-3.0
- Output: `../rules/ads_easylist.json` and `easylist_cosmetic.json`
- Notes: PrivacyBrew converts supported network filters to DNR rules. Unsupported filters are skipped and counted in `../rules/metadata.json`.

## DuckDuckGo Autoconsent

- Source: https://registry.npmjs.org/@duckduckgo/autoconsent/-/autoconsent-16.50.0.tgz
- Version: 16.50.0
- License: MPL-2.0
- Output: `../vendor/autoconsent/`
- Notes: Vendored files are unmodified and remain under MPL-2.0.

## Public Suffix List

- Source: https://publicsuffix.org/list/public_suffix_list.dat
- License: MPL-2.0
- Output: `psl.json`
- Notes: The generated file includes ICANN and PRIVATE rules, wildcard rules, and exception rules.
