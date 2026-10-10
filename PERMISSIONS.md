# Permissions

PrivacyBrew uses the smallest permission set for this prototype.

## `webRequest`

PrivacyBrew observes page requests and response headers. It uses this to find known tracker domains and third-party `Set-Cookie` headers. It does not block or change requests.

## `webNavigation`

PrivacyBrew resets the report when the top-level page changes. This keeps each tab report tied to the current website.

## `storage`

PrivacyBrew stores per-tab reports in `chrome.storage.session`. This helps the report survive service worker restarts. Data stays local to the browser session.

## Host permissions: `<all_urls>`

PrivacyBrew must observe requests on any website the user opens. This permission also lets the content script watch fingerprinting APIs on pages.

## No `tabs` permission

The extension does not request the `tabs` permission. It uses the active tab ID from the popup and navigation events in the service worker.
