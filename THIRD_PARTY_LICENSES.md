# Third-party licenses

## Disconnect tracking protection data

- Source: https://raw.githubusercontent.com/disconnectme/disconnect-tracking-protection/master/services.json
- Project: https://github.com/disconnectme/disconnect-tracking-protection
- License: CC-BY-NC-SA-4.0
- Use: Generated tracker company and domain data in `extension/data/disconnect.json`.

The extension code is GPLv3. The Disconnect data stays in a separate generated file under its own license. The license is Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International. It is non-commercial and share-alike.

## Public Suffix List

- Source: https://publicsuffix.org/list/public_suffix_list.dat
- Project: https://publicsuffix.org/
- License: MPL-2.0
- Use: Generated suffix rules in `extension/data/psl.json`.

The Public Suffix List data stays in a separate generated file under MPL-2.0.

## Python Pillow

- Project: https://python-pillow.org/
- License: Historical Permission Notice and Disclaimer.
- Use: Build-time icon generation only.

## EasyList

- Source: https://easylist.to/easylist/easylist.txt
- Project: https://easylist.to/
- License: GPL-3.0-only or CC-BY-SA-3.0
- Use: Generated ad blocking rules in `extension/rules/ads_easylist.json` and cosmetic selectors in `extension/data/easylist_cosmetic.json`.

EasyList data stays in generated files under its own license.

## DuckDuckGo Autoconsent

- Source: https://registry.npmjs.org/@duckduckgo/autoconsent/-/autoconsent-16.50.0.tgz
- Version: 16.50.0
- Project: https://github.com/duckduckgo/autoconsent
- License: MPL-2.0
- Use: Vendored unmodified content script and compact rules in `extension/vendor/autoconsent/`.

Autoconsent files stay under MPL-2.0. PrivacyBrew glue code stays under GPLv3.
