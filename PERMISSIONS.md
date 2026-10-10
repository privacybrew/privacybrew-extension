# Permissions

PrivacyBrew uses the smallest permission set for this prototype.

## `webRequest`

PrivacyBrew observes page requests and response headers. It uses this to find known tracker domains and third-party `Set-Cookie` headers. Blocking uses `declarativeNetRequest`.

## `webNavigation`

PrivacyBrew resets the report when the top-level page changes. This keeps each tab report tied to the current website.

## `storage`

PrivacyBrew stores per-tab reports in `chrome.storage.session`. It stores blocking and GPC settings in `chrome.storage.local`. Data stays local to the browser.

## `declarativeNetRequest`

PrivacyBrew blocks known tracker and ad requests with static rules. It also sends the `Sec-GPC: 1` header when the GPC setting is on.

## `scripting`

PrivacyBrew registers or removes one small main-world content script for GPC. This avoids a first-load race when the GPC setting changes.

## Host permissions: `<all_urls>`

PrivacyBrew must observe requests on any website the user opens. This permission also lets the content script watch fingerprinting APIs on pages.

## No `tabs` permission

The extension does not request the `tabs` permission. It uses the active tab ID from the popup and navigation events in the service worker.

## `declarativeNetRequestFeedback`

PrivacyBrew uses matched-rule events to count ad requests blocked by EasyList. This keeps ad counts separate from tracker counts.
