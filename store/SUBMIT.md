# Chrome Web Store submit checklist

1. Run `python3 tools/package.py`.
2. Upload `dist/privacybrew-extension-1.0.0.zip`.
3. Paste the listing text from `store/LISTING.md`.
4. Upload screenshots from `store/screenshots/`.
5. Upload `store/promo-small-440x280.png` as the small promo tile.
6. Paste privacy answers from `store/PRIVACY_PRACTICES.md`.
7. Distribution: public.
8. Regions: all regions, unless you choose a smaller launch.
9. Pricing: free.
10. Trader status: use the existing non-trader declaration.

## Review notes

Broad host permissions can cause a longer in-depth review. The permission text explains why all websites are needed.

PrivacyBrew uses no remote code. Autoconsent snippets are bundled and allowlisted.

## After approval

TODO: Update the website button from Coming soon to the Chrome Web Store URL.
