# PrivacyBrew browser extension

**Install:** [PrivacyBrew on the Chrome Web Store](https://chromewebstore.google.com/detail/privacybrew-tracker-ad-bl/hdhjekomkdacaliekmmdilaanalclhib) (works in Chrome, Edge and Brave).

**Firefox:** Firefox Add-ons link coming soon. See [Firefox](#firefox).

PrivacyBrew is a Manifest V3 prototype for Chrome, Edge, Brave, Opera, and Firefox. It shows a plain-language privacy report card for the current website.

This prototype blocks known trackers by default. It handles many cookie pop-ups, blocks ads, and detects third-party cookie attempts and some fingerprint methods. The extension makes no network requests of its own and uses only local data files.

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

Cookie pop-up handling is on by default. No dynamic cookie-rule code is downloaded or run. PrivacyBrew only runs fixed Autoconsent snippets that ship with the extension.

Cookie pop-up handling is on by default. PrivacyBrew tries to reject optional cookies. If there is no reject choice or settings path, it hides the pop-up and sends no choice to the site. It never clicks accept all. Per-site pause also turns this off for that website.

The GPC setting is on by default. It sends `Sec-GPC: 1` with browser requests. It also sets `navigator.globalPrivacyControl` to true in page scripts.

The DNT setting is off by default. If you turn it on, PrivacyBrew sends `DNT: 1` and sets `navigator.doNotTrack` to `1`. Website pause and global blocking do not turn off GPC or DNT because they are privacy requests, not blocking rules.

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

## Package for Chrome Web Store

Run:

```sh
python3 tools/package.py
python3 tools/package_smoke.py
```

The ZIP is written to `dist/`. The package step strips debug hooks and validates manifest files, rules, host strings, local paths, remote script use, and static rule counts.

Minimum Chrome version is 119. PrivacyBrew uses Manifest V3, dynamic content scripts with `world: "MAIN"`, `matchOriginAsFallback`, `chrome.storage.session`, and Declarative Net Request rule features used by current Chrome stores.

## Firefox

**Install:** Firefox Add-ons link coming soon (FIREFOX_ADDON_URL).

The same `extension/` code runs in Firefox 140 or newer, and in Firefox for Android 142 or newer. `tools/package.py --target firefox` makes the Firefox build:

```sh
python3 tools/package.py --target firefox
```

The ZIP is `dist/privacybrew-extension-firefox-<version>.zip`. The build changes only these things:

- `manifest.json`: `background.scripts` (Firefox has no extension service workers), `browser_specific_settings.gecko` with the id `privacybrew@privacybrew.app`, `strict_min_version` 140.0, `browser_specific_settings.gecko_android` with `strict_min_version` 142.0, and `data_collection_permissions` `none`, and 64 and 96 pixel icons. Firefox 140 is the first version (and an ESR) with `data_collection_permissions`, which AMO needs for new add-ons. All other APIs need Firefox 128 or older.
- `rules/*.json`: removes the `webtransport` and `webbundle` resource types. Firefox does not know them.

To try it without a store, open `about:debugging#/runtime/this-firefox`, select **Load Temporary Add-on**, and choose `manifest.json` in `dist/package-work-firefox/`.

Differences that the shared code handles at run time:

| Topic | Chrome | Firefox | How PrivacyBrew handles it |
| --- | --- | --- | --- |
| Background | Service worker with `importScripts` | Event page with `background.scripts` | `importScripts` runs only if it exists. |
| Blocked request error in `webRequest.onErrorOccurred` | `net::ERR_BLOCKED_BY_CLIENT` | `NS_ERROR_ABORT` | Both count as blocked. |
| DNR resource types | Has `webtransport`, `webbundle` | Does not | Dynamic rules use only types in `declarativeNetRequest.ResourceType`. |
| `onHeadersReceived` option `extraHeaders` | Needed for `Set-Cookie` | Not known | Added only when the browser has it. |
| Duplicate content script error | "Duplicate script ID" | "already registered" | Both are ignored. |
| Host access | Granted at install | Granted at install (Firefox 127+), but the user can remove it | The popup shows "PrivacyBrew needs access to websites to protect you." with an **Allow access** button. |
| Scroll bars | `::-webkit-scrollbar` | `scrollbar-width`, `scrollbar-color` | A Firefox-only `@supports` rule. |
| Feedback browser label | From `userAgentData` | From the user agent | Shows "Firefox <version>". |

Firefox tests (headless Firefox, WebDriver BiDi, the packaged Firefox build, local fixtures only):

```sh
python3 tools/run_tests_firefox.py
```

The runner uses software rendering and no GPU acceleration, runs one Firefox at a time, and stops Firefox after 10 minutes at most. To watch the tests, add `--headed --slow`. A headed run opens a Firefox window on your screen.

`python3 tools/store_screenshots_firefox.py` makes the AMO screenshots in `store-firefox/screenshots/`. The AMO submit kit is in `store-firefox/`.

## Popup layout check

`python3 tools/popup_artifacts.py` renders each popup view at 380x580, saves screenshots to `artifacts/`, and fails if any content is cut off or the footer is not visible.
