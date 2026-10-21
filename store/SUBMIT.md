# Chrome Web Store submit checklist

1. Run `python3 tools/package.py`.
2. Upload `dist/privacybrew-extension-1.0.0.zip`.
3. Paste the listing text from `store/LISTING.md`.
4. Upload screenshots from `store/screenshots/`.
5. Upload `store/promo-small-440x280.png` as the small promo tile.
   Upload `store/marquee-1400x560.png` as the marquee image (optional; used only if Google features the extension).
   Upload `store/store-icon-128.png` as the store icon (96x96 artwork with 16 px transparent padding, per Chrome guidelines).
6. Additional fields: Homepage https://privacybrew.app/extension.html, Support URL https://privacybrew.app/feedback.html.
7. Paste privacy answers from `store/PRIVACY_PRACTICES.md`.
8. Distribution: public.
9. Regions: all regions, unless you choose a smaller launch.
10. Pricing: free.
11. Trader status: use the existing non-trader declaration.

## Review notes

Broad host permissions can cause a longer in-depth review. The permission text explains why websites (http and https) are needed.

PrivacyBrew uses no remote code. Autoconsent snippets are bundled and allowlisted.

## After approval

TODO: Update the website button from Coming soon to the Chrome Web Store URL.


## Status

- 2026-10-12: Version 1.0.0 submitted to the Chrome Web Store for review.
  ZIP SHA-256: 56525c94c5e301b2be8d03d761d63d3e0abf0fc3e570ddc688617e5f2145ddd0
  Expect an in-depth review (broad host permissions). Watch privacybrew@protonmail.com.
- 2026-10-14: Approved and published: https://chromewebstore.google.com/detail/privacybrew-tracker-ad-bl/hdhjekomkdacaliekmmdilaanalclhib
  Website buttons and README updated with the store link.
- 2026-10-15: Version 1.0.1 prepared. Power menu shows the active option, one option at a time,
  tap the active option to turn on again. Notice when site access is limited. Firefox compatibility
  in shared code. Same permissions and file list as 1.0.0.
  ZIP SHA-256: 36003575bbd1cf99cb885bf1844fb651cd3fc4aae425268c4ba752b56c67697d
- 2026-10-17: Version 1.0.1 rejected ("Red Potassium": trackers, cookie pop-ups and report card not
  reproducible). Causes found in a reviewer simulation with the packaged ZIP (also in 1.0.0):
  - A tab that was open before install showed an empty report or the name of an ad domain
    (a message from an ad frame created the report).
  - After moving to a new website, a late event from the old page could bring back the old report.
  - Many websites show no cookie pop-up to visitors in the US.
- 2026-10-17: Version 1.0.2 prepared with fixes: the report always uses the website of the tab, a late
  save from the old page is ignored, and the popup shows "Reload this page to see its full report."
  with a Reload page button when the report started late. Same permissions and file list as 1.0.0.
  ZIP SHA-256: e473aac048e7b488a687c4e84754786cdbc02f0469e09516b407ea37c7d397cb

## Test instructions for reviewers (paste)

```
1. Install PrivacyBrew, then open a NEW tab (or reload open tabs). Pages that were open before
   install show "Reload this page to see its full report." with a Reload page button.
2. Report card and trackers: open https://www.dailymail.co.uk or https://www.forbes.com, wait for the
   page to load, then select the PrivacyBrew icon. The report shows trackers found and blocked, ads
   blocked, outside scripts and cookies. The icon badge shows the number of blocked companies.
3. Cookie pop-ups: many websites show no cookie pop-up to visitors in the US. Use a new private window
   (Allow in Incognito) or clear cookies, then open https://stackoverflow.com (Cookies: Rejected) or
   https://www.theguardian.com (Cookies: Hidden). PrivacyBrew never selects "Accept all".
No account or login is needed.
```
- 2026-10-20: Version 1.0.2 approved and published on the Chrome Web Store (owner confirmed).

