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
7. Distribution: public.
8. Regions: all regions, unless you choose a smaller launch.
9. Pricing: free.
10. Trader status: use the existing non-trader declaration.

## Review notes

Broad host permissions can cause a longer in-depth review. The permission text explains why all websites are needed.

PrivacyBrew uses no remote code. Autoconsent snippets are bundled and allowlisted.

## After approval

TODO: Update the website button from Coming soon to the Chrome Web Store URL.
