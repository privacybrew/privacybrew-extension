# Chrome Web Store: Privacy practices tab (paste-ready)

## Single purpose
PrivacyBrew shows a plain-language privacy report card for the website the user is on, and protects the user on that website: it blocks known trackers and ads, answers cookie pop-ups with "reject", and can ask websites not to sell the user's data. All of this runs locally in the browser. Nothing is sent to PrivacyBrew.

## webRequest
PrivacyBrew observes (does not modify) the network requests of the page the user opens. It needs this to count known trackers, outside scripts and third-party cookies for the report card, and to see which requests Chrome blocked (net::ERR_BLOCKED_BY_CLIENT). The results stay in the browser and are cleared when the user leaves the page. Only website names and paths are kept; query strings and tracking IDs are never stored.

## webNavigation
Used to know when the main page of a tab changes, so the report card starts fresh for each new page and is not reset by same-page address changes. No browsing history is stored or sent.

## storage
Used to keep the user's settings (for example blocking on or off, and the websites where the user turned PrivacyBrew off) in chrome.storage.local, and the report for each open tab in chrome.storage.session, which Chrome clears when the browser closes. No data leaves the browser.

## declarativeNetRequest
Used to block known tracker and ad requests with static rule lists that ship inside the extension (Disconnect tracker list, EasyList). Also used to add the "Sec-GPC: 1" and optional "DNT: 1" privacy request headers when the user turns them on, and to allow all requests on websites where the user paused PrivacyBrew. Chrome applies the rules; the extension does not read page content to do this.

## scripting
Used to register small scripts that ship with the extension: they set navigator.globalPrivacyControl and navigator.doNotTrack when the user turns those requests on, and they run the bundled DuckDuckGo autoconsent rules to answer cookie pop-ups with "reject". Autoconsent can only run a fixed list of code snippets bundled in the package; any other code is refused. No remote code is loaded.

## alarms
Used for the "Turn off for a while" option (15 minutes or 1 hour). An alarm turns protection back on when the time ends, even if the popup is closed. No data is collected or sent.

## Host permission (<all_urls>)
Trackers and ads can appear on any website, so PrivacyBrew needs access to the websites the user opens to block them, to build the report card for that website, to detect fingerprinting scripts, to hide empty ad spaces and to answer cookie pop-ups. All processing happens in the browser. PrivacyBrew has no server and does not collect or send browsing data. The user can turn PrivacyBrew off for any website.

## Remote code
No, I am not using remote code. All JavaScript, rule lists and the autoconsent rules are bundled in the package.

## Data usage
Leave all data types unticked. PrivacyBrew processes page requests locally to show the report card and to block trackers; this data is not collected, stored on a server, or sent to the developer or anyone else.
Feedback: the popup's Feedback link opens privacybrew.app/feedback.html only when the user clicks it. The extension version and browser name are passed if the user leaves that box ticked; the page address (website and path only) only if the user ticks that box. The user then chooses to submit the form on the website (handled by Tally). This is user-initiated and described in the privacy policy.

Certifications: tick all three.

## Privacy policy URL
https://privacybrew.app/privacy.html
