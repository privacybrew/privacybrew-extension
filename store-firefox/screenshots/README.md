# Screenshot order and captions

1. `01-report-card.png` - A plain-language report card with summary numbers.
2. `02-blocking-controls.png` - Blocking settings and privacy requests.
3. `03-cookie-popups.png` - Cookie pop-up handling before and after.
4. `04-companies-detail.png` - Company detail rows with blocked and allowed status.
5. `05-local-by-design.png` - Local processing and no remote code.

`python3 tools/store_screenshots_firefox.py` makes these images. It runs headless Firefox with the packaged Firefox build on local fixtures (news.example and shop.example). The numbers come from real page loads of these fixtures. No real website or personal data appears.
