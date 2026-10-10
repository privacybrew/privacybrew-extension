# Data sources

Fetched on 2026-10-10.

## Disconnect tracking protection data

- Source: https://raw.githubusercontent.com/disconnectme/disconnect-tracking-protection/master/services.json
- License: CC-BY-NC-SA-4.0
- Output: `disconnect.json`
- Notes: PrivacyBrew maps Disconnect categories to plain category chips. Email and EmailAggressive map to Other. Anti-fraud and ConsentManagers map to Other. Disconnect maps to Social.
- Category priority: Advertising, Social, Analytics, Cryptomining, Fingerprinting, Content, Other. A domain in more than one category uses the highest-priority match.
- See `THIRD_PARTY_LICENSES.md`. The upstream data file includes the full license notice.

## Public Suffix List

- Source: https://publicsuffix.org/list/public_suffix_list.dat
- License: MPL-2.0
- Output: `psl.json`
- Notes: The generated file includes ICANN and PRIVATE rules, wildcard rules, and exception rules.
