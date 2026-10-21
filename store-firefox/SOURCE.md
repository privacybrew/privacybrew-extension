# Source code notes for AMO reviewers

PrivacyBrew is open source (GPLv3).

- Repository: https://github.com/privacybrew/privacybrew-extension
- Commit: 3ca7fbb90c683ce736e01f31cfc63ec13aad75cb
- Uploaded file: `privacybrew-extension-firefox-1.0.3.zip`

## What is in the ZIP

The ZIP is the `extension/` folder of the repository, with three build changes made by `tools/package.py --target firefox`:

1. `manifest.json`: `background.scripts` instead of a service worker, `browser_specific_settings.gecko` (id, `strict_min_version`, `data_collection_permissions`), and 64 and 96 pixel icons.
2. `rules/*.json`: the `webtransport` and `webbundle` resource types are removed. Firefox does not support them.
3. Debug hooks for the test runner are removed (`DEBUG_REPORT_MESSAGES`, `DEBUG_POPUP_TAB_OVERRIDE`, and the code between `// DEBUG_START` and `// DEBUG_END`).

No file is minified, obfuscated or made by a bundler of ours. There is no remote code.

## Rebuild the ZIP

You need only Python 3.10 or newer. The build uses the Python standard library. It does not download anything.

```sh
git clone https://github.com/privacybrew/privacybrew-extension.git
cd privacybrew-extension
git checkout 3ca7fbb90c683ce736e01f31cfc63ec13aad75cb
python3 tools/package.py --target firefox
```

The output is `dist/privacybrew-extension-firefox-1.0.3.zip`. The work folder is `dist/package-work-firefox/`. ZIP timestamps differ from build to build, so compare the files, not the ZIP hash:

```sh
mkdir uploaded && cd uploaded && unzip -q ../privacybrew-extension-firefox-1.0.3.zip && cd ..
diff -r uploaded dist/package-work-firefox
```

## Third-party code: `vendor/autoconsent/`

These files come unmodified from the npm package `@duckduckgo/autoconsent` version 16.50.0 (MPL-2.0):

- Package: https://www.npmjs.com/package/@duckduckgo/autoconsent/v/16.50.0
- Tarball: https://registry.npmjs.org/@duckduckgo/autoconsent/-/autoconsent-16.50.0.tgz
- Project: https://github.com/duckduckgo/autoconsent
- License: `vendor/autoconsent/LICENSE`

| File in the ZIP | File in the npm tarball |
| --- | --- |
| `vendor/autoconsent/content.bundle.js` | `package/dist/addon-mv3/content.bundle.js` |
| `vendor/autoconsent/compact-rules.json` | `package/rules/compact-rules.json` |
| `vendor/autoconsent/LICENSE` | `package/LICENSE` |
| `vendor/autoconsent/package.json` | `package/package.json` |

`vendor/autoconsent/eval-snippets.json` is ours. `tools/build_data.py` makes it from `content.bundle.js`. It lists the fixed code snippets that autoconsent rules can ask to run (see the next section).

To check a file:

```sh
curl -sLO https://registry.npmjs.org/@duckduckgo/autoconsent/-/autoconsent-16.50.0.tgz
tar xzf autoconsent-16.50.0.tgz
cmp package/dist/addon-mv3/content.bundle.js dist/package-work-firefox/vendor/autoconsent/content.bundle.js
```

## Generated block lists: `data/*.json`, `data/*.css`, `rules/*.json`

`tools/build_data.py` downloads public lists and converts them to JSON data and Declarative Net Request rules. The generated files are in the repository. You do not need to run `build_data.py` to rebuild the ZIP. The lists change every day, so a new run gives different files.

| File | Source | License |
| --- | --- | --- |
| `data/disconnect.json`, `rules/block_*.json`, `rules/allow_same_company.json` | Disconnect tracking protection, https://github.com/disconnectme/disconnect-tracking-protection | CC BY-NC-SA 4.0 |
| `data/psl.json` | Public Suffix List, https://publicsuffix.org/ | MPL-2.0 |
| `rules/ads_easylist.json`, `data/easylist_*.json`, `data/easylist_generic.css` | EasyList, https://easylist.to/ (and the EasyList anti-adblock list) | GPLv3 or CC BY-SA 3.0 |
| `rules/gpc_headers.json`, `rules/dnt_headers.json` | Written by `build_data.py` (adds `Sec-GPC: 1` or `DNT: 1`) | GPLv3 |

`data/SOURCES.md` in the ZIP lists the exact source URLs and dates. `THIRD_PARTY_LICENSES.md` in the repository has the full license notes.

## Why `background.js` uses `scripting.executeScript` with `world: "MAIN"` and `new Function`

Some autoconsent cookie pop-up rules must read page variables (for example `window.Didomi`). The autoconsent content script then sends an `eval` message with a snippet ID and the code.

`evalForAutoconsent()` in `background.js` does this:

1. It loads `vendor/autoconsent/eval-snippets.json`. This allowlist ships in the ZIP.
2. It runs the code only if the code is exactly the same string as the allowlisted snippet for that ID. Else it answers `false` and runs nothing.
3. It runs the snippet with `scripting.executeScript` in the main world of the same tab and frame that sent the message.

So only fixed strings that ship in the add-on can run. No code comes from the network or from the page. The Firefox test suite checks that a changed snippet is refused (`tools/run_tests_firefox.py`, "autoconsent non-allowlisted eval refused").

## Other main-world scripts

- `content-main.js` (manifest `content_scripts`, `world: "MAIN"`): watches canvas, WebGL, audio and font APIs that fingerprinting scripts use. It sends only the method name and script address to `content-bridge.js` with a `CustomEvent`.
- `gpc-main.js` and `dnt-main.js` (registered with `scripting.registerContentScripts`, `world: "MAIN"`): set `navigator.globalPrivacyControl` to `true` and `navigator.doNotTrack` to `"1"` when the user turns these on.

## Tests

`python3 tools/run_tests_firefox.py` builds the ZIP, installs it in headless Firefox with WebDriver BiDi and runs the end-to-end tests on local fixture pages. It sends no traffic to the internet.
