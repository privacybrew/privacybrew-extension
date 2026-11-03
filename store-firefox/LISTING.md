# Firefox Add-ons (AMO) listing

Paste these into the listing fields on addons.mozilla.org.

## Name

PrivacyBrew: Tracker & Ad Blocker

## Add-on URL (slug)

privacybrew

## Summary (250 characters max)

The universe ain't giving you signs. They're targeted ads. See who tracks you and block trackers, ads and cookie pop-ups.

(120 characters. It is the same text as the package description.)

## Description

The universe ain't giving you signs. They're targeted ads, dear.

Ads follow you because trackers follow you. PrivacyBrew shows who sees your visit to each website, in simple words, and stops them. Everything runs in Firefox. Nothing is sent to us.

Each website gets a report card with five parts: trackers, ads, outside scripts, cookies and fingerprinting. Open a part to see the details. The Trackers part names each company and tells you what it does. The Ads part lists each ad request that PrivacyBrew blocked and the ad company behind it. The Scripts part lists each script that comes from another website.

You decide which outside scripts run. On each website, you can block or allow one script, or block or allow all outside scripts. A choice for one script wins over the choice for all. Your choices stay in Firefox, and Undo removes them.

PrivacyBrew blocks known trackers and ads from the start. It answers cookie pop-ups with "Reject all" or with only necessary cookies, and it never selects "Accept all". Where it can, it hides messages that ask you to turn off your ad blocker. It asks each website not to sell or share your data (Global Privacy Control). Do Not Track is optional.

The power button turns PrivacyBrew off for one website, for a while, or until you turn it on again.

PrivacyBrew has no account, no analytics and no ads. The code is open source (GPLv3): https://github.com/privacybrew/privacybrew-extension

PrivacyBrew needs access to all websites. It must see the requests on each page to find and block trackers. If you remove this access in the add-on settings, the PrivacyBrew window shows a button to allow it again.

PrivacyBrew works next to Firefox Enhanced Tracking Protection. Firefox can block some trackers before PrivacyBrew sees them. Those requests do not show in the PrivacyBrew report.

Limits: PrivacyBrew finds known trackers and ads only. It cannot block all video ads. "Block all" can break parts of a website, for example a login or a video. If a website breaks, allow the script that it needs, or turn PrivacyBrew off for that website.

Lists: Disconnect tracker list (CC BY-NC-SA 4.0), EasyList. Cookie pop-up rules: DuckDuckGo autoconsent (MPL-2.0).

Also from PrivacyBrew: the Android app and the free Browser Privacy Check at https://privacybrew.app

## Categories

Privacy & Security

## Tags

privacy, tracker blocker, ad blocker, cookie banner, GPC

## Support and links

- Homepage: https://privacybrew.app/extension.html
- Support site: https://privacybrew.app/feedback.html
- Support email: privacybrew@protonmail.com
- Privacy policy: https://privacybrew.app/privacy.html

## License

GNU General Public License v3.0 (GPLv3)

## Data collection

None. The manifest declares `"data_collection_permissions": {"required": ["none"]}`.

## Images

- Icon: comes from the package (`icons/icon-64.png`, `icons/icon-128.png`).
- Screenshots (1280x800, in order): `store-firefox/screenshots/01` to `05`. See `store-firefox/screenshots/README.md` for captions.
