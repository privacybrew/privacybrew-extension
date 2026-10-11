# Chrome Web Store privacy practices

## Single purpose

PrivacyBrew gives a local privacy report card and blocks known trackers, ads, and cookie pop-ups in the browser.

## Permission justifications

### Host permission: `<all_urls>`

PrivacyBrew must observe and classify requests on websites the user opens. It also needs page access for local fingerprint detection, cookie pop-up handling, and cosmetic ad hiding.

### `webRequest`

Used to observe requests, response headers, blocked request errors, and third-party cookie attempts. PrivacyBrew does not send this data anywhere.

### `webNavigation`

Used to reset the local report when the top-level page changes.

### `storage`

Used for local settings and per-tab reports. Data stays in the browser.

### `declarativeNetRequest`

Used to block known tracker and ad requests and to send GPC and DNT request headers when enabled.

### `scripting`

Used for bundled GPC, DNT, and cookie pop-up handling scripts. Autoconsent eval requests are restricted to fixed snippets that ship with the extension.

## Remote code

No. PrivacyBrew does not use remote code. All scripts, rules, and Autoconsent snippets are bundled in the extension package.

## Data disclosure answers

PrivacyBrew processes web browsing activity locally to make the report card and blocking decisions. It does not collect, transmit, sell, or share user data.

Recommended Chrome Web Store data checkbox answer:
- Web browsing activity: not collected. It is processed locally only.
- Personally identifiable information: not collected.
- Authentication information: not collected.
- Financial and payment information: not collected.
- Health information: not collected.
- Personal communications: not collected.
- Location: not collected.
- Web history: not collected.
- User activity: not collected.
- Website content: not collected.

## Certifications

- I do not sell or transfer user data to third parties.
- I do not use or transfer user data for purposes unrelated to the single purpose.
- I do not use or transfer user data to determine creditworthiness or for lending.

## Privacy policy URL

https://privacybrew.app/privacy.html
