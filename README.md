# PrivacyBrew browser extension

PrivacyBrew is a Chrome Manifest V3 prototype for Chrome, Edge, Brave, and Opera. It shows a plain-language privacy report card for the current website.

This prototype blocks known trackers by default. It also detects third-party cookie attempts and some fingerprint methods. The extension makes no network requests of its own and uses only local data files.

## Load the extension

1. Open `chrome://extensions`.
2. Turn on developer mode.
3. Select **Load unpacked**.
4. Choose the `extension/` folder in this repo.
5. Open a website and then open the PrivacyBrew toolbar popup.

## Rebuild data

Run:

```sh
python3 tools/build_data.py
```

The script downloads data files only at build time. It writes generated JSON to `extension/data/` and static blocking rules to `extension/rules/`. It records sources in `extension/data/SOURCES.md`.

## Run tests

Run:

```sh
python3 tools/run_tests.py
```

The test runner starts local HTTP servers and headless Chrome. It maps test host names to `127.0.0.1`, so tracker test requests do not go to the real internet.


## Licenses

The extension code is GPLv3. See `LICENSE`.

The Disconnect data file is CC BY-NC-SA 4.0. It is a separate generated file under its own license. It is non-commercial and share-alike.

The Public Suffix List data file is MPL-2.0. It is a separate generated file under its own license.

## Blocking

PrivacyBrew uses Manifest V3 `declarativeNetRequest` static rules. Tracker blocking and ad blocking are on by default.

Blocked tracker categories are Advertising, Analytics, Social, Fingerprinting, and Cryptomining. Content is not blocked because pages often need embedded video, maps, and other page parts. Ads are blocked with EasyList network rules and cosmetic hiding rules. The build merges compatible domain rules and keeps the total static rules under a 22000-rule cap.

PrivacyBrew uses same-company allow rules from Disconnect properties. This lets a company website load its own company resources.

You can pause blocking for one website. You can also turn tracker and ad blocking off for all websites. Reload the page after you change blocking.

The toolbar badge shows the number of blocked tracker companies on the current page. Ads are counted separately from trackers. A request can be both a tracker and an ad.

PrivacyBrew counts distinct tracker requests by origin and path. It removes query strings and fragments before storage. This keeps tracking IDs out of local reports and reduces retry noise.

## GPC

The GPC setting is on by default. It sends `Sec-GPC: 1` with browser requests. It also sets `navigator.globalPrivacyControl` to true in page scripts.

PrivacyBrew uses a dynamic main-world content script for this setting. This avoids a first-load race after you turn GPC off or on.

## Report labels

PrivacyBrew counts distinct tracker companies seen on the page.

- 0 to 2 companies: Little tracking found.
- 3 to 5 companies: Some tracking.
- 6 or more companies: A lot of tracking.
- Fingerprinting pushes the label up one level.


## Tracker categories

A tracker domain can appear in more than one Disconnect category. PrivacyBrew uses this priority order: Advertising, Social, Analytics, Cryptomining, Fingerprinting, Content, Other.

Email and EmailAggressive map to Other. Anti-fraud and ConsentManagers map to Other. Disconnect maps to Social.

## Fingerprinting signals

The content script watches these browser APIs without changing results:

- Canvas readout through `toDataURL`, `toBlob`, or `getImageData`.
- WebGL graphics card readout through debug renderer APIs.
- Audio readout through `OfflineAudioContext.startRendering`.
- Font probing after 20 distinct measured font families.

Tiny canvases under 16 by 16 pixels are ignored. Small icons and layout checks can otherwise create false positives.

## Limits

PrivacyBrew blocks known trackers only. It can miss new companies, hidden redirects, or tracking that does not use the watched APIs. Some websites can break. Turn off blocking for that website if this happens. PrivacyBrew does not clear cookies or stop fingerprinting yet.

## Future work

- Add cookie controls.
- Add stronger fingerprint protection.
- Add user settings and report history.

## Rule priorities

| Priority | Rule type | Purpose |
|---:|---|---|
| 10000 | Per-site pause | Allow requests on a paused website. |
| 300 | EasyList exceptions | Keep allowed ad resources working. |
| 150 | EasyList important blocks | Block high-priority ad filters. |
| 100 | EasyList blocks | Block ad requests, including same-company ads. |
| 3 | Same-company session allow | Keep non-ad company resources working on company-owned sites. |
| 2 | Same-company static allow | Keep non-ad company resources working. |
| 1 | Tracker blocks and GPC | Block known trackers and send GPC. |
