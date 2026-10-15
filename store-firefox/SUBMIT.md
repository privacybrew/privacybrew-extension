# Firefox Add-ons (AMO) submit checklist

## Before you start

1. Make sure the release commit is on GitHub. AMO reviewers read the code there.
2. Build and test:

   ```sh
   python3 tools/check_ste.py
   python3 tools/run_tests_firefox.py
   python3 tools/package.py --target firefox
   ```

   Upload `dist/privacybrew-extension-firefox-1.0.0.zip`. Write down its SHA-256 (the package step prints it).
3. Make the source archive for reviewers:

   ```sh
   git archive --format=zip -o dist/privacybrew-extension-source-1.0.0.zip HEAD
   ```

4. In `store-firefox/SOURCE.md`, replace `COMMIT_PLACEHOLDER` with the commit (`git rev-parse HEAD`) if it is not filled in yet.

## Submit

1. Sign in at https://addons.mozilla.org/developers/ with a Firefox account. Use privacybrew@protonmail.com. Turn on two-step authentication if AMO asks for it.
2. Read and accept the Firefox Add-on Distribution Agreement and the Add-on Policies (first time only).
3. Select **Submit a New Add-on**.
4. "How to Distribute this Version": select **On this site**. Select **Continue**.
5. Upload `dist/privacybrew-extension-firefox-1.0.0.zip`.
6. Compatible platforms: select **Firefox** only. Do not select Firefox for Android yet (see "Firefox for Android" below).
7. Wait for the automatic validation. Read the warnings. Expected warnings:
   - `new Function` in `background.js` (the allowlisted autoconsent snippets, see `SOURCE.md`).
   - `innerHTML` or similar in `vendor/autoconsent/content.bundle.js` (unmodified third-party code).
   There must be no errors. Select **Continue**.
8. "Do you need to submit source code?": select **Yes**. Upload `dist/privacybrew-extension-source-1.0.0.zip`. Reason: `vendor/autoconsent/content.bundle.js` is a bundled file from npm, and the rules are generated. `SOURCE.md` in the archive explains all of it.
9. Describe the add-on. Copy the fields from `store-firefox/LISTING.md`:
   - Name, add-on URL (slug), summary, description.
   - Categories: Privacy & Security.
   - Support email: privacybrew@protonmail.com. Support website: https://privacybrew.app/feedback.html.
   - License: GNU General Public License v3.0.
   - Privacy policy: select "This add-on has a privacy policy" and paste the link or text from https://privacybrew.app/privacy.html.
   - Data collection: the manifest declares none. AMO shows "This add-on does not collect data". Do not change it.
10. Notes to reviewer: paste the text below.
11. Select **Submit Version**.
12. After submission, open the listing in the Developer Hub and add:
    - Homepage: https://privacybrew.app/extension.html.
    - Screenshots from `store-firefox/screenshots/` in order, with the captions from `store-firefox/screenshots/README.md`.
    - Tags from `store-firefox/LISTING.md`.

## Notes to reviewer (paste)

```
PrivacyBrew blocks trackers and ads with Declarative Net Request static rules and shows a per-site report.
Source: https://github.com/privacybrew/privacybrew-extension (commit in SOURCE.md). Rebuild with Python 3 only:
  python3 tools/package.py --target firefox
Details are in store-firefox/SOURCE.md in the source archive.

- No remote code. No network requests of our own. No data collection.
- vendor/autoconsent/ is unmodified @duckduckgo/autoconsent 16.50.0 from npm (MPL-2.0).
- background.js runs autoconsent "eval" snippets with scripting.executeScript (world MAIN) only when the code
  string equals a snippet in vendor/autoconsent/eval-snippets.json, which ships in the add-on. All other code is refused.
- data/*.json, data/*.css and rules/*.json are generated from Disconnect, EasyList and the Public Suffix List.
- Host permission *://*/* is needed to see and block tracker requests on every website.

To test: open a news website, then open the PrivacyBrew toolbar button. The report shows trackers found and blocked.
```

## Firefox for Android

Do not select Firefox for Android until it is tested on a phone. When it is ready:

1. Add `"gecko_android": {"strict_min_version": "142.0"}` to `browser_specific_settings` in `firefox_manifest()` in `tools/package.py`. Firefox for Android supports `data_collection_permissions` from 142.
2. Test on a phone (popup size, badge, cookie pop-ups, power menu, "Allow access" notice).
3. Upload a new version and select both platforms.

## After approval

- Add the AMO link to `README.md` and to https://privacybrew.app/extension.html.
- Record the date, version and ZIP SHA-256 in the Status section below.

## Status

- Not submitted yet.
