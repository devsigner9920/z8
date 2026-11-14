# Play Store submission materials

Prepared on 2026-11-14. English (`en-US`) is the primary listing language;
`ko-KR` is an optional Korean localization. These files prepare the listing;
they do not submit or publish it. Recheck the copy against the final candidate
and the current Console form before submission.

## Copy and account settings

Use each locale's `title.txt`, `short-description.txt`, `full-description.txt`
and `release-notes.txt` as plain text, without their final newline. The release
notes describe the initial test release and must not be presented as a stable
release announcement. Character counts are recorded in `validation.json`.
GitHub is the canonical source and release location. Include these materials
in the reviewed source revision, and publish each release's matching source and
notices there. A source prerelease is not a binary distribution or Play approval.

| Setting | Prepared value |
| --- | --- |
| App name | Z8: Development Terminal |
| Default language | English (United States), `en-US` |
| App / game | App |
| Proposed category | Tools; confirm against the available Console categories |
| Developer display name | Romi Ethsy |
| Support email | ethsy2462@gmail.com |
| Website | https://devsigner9920.github.io/z8/ |
| Privacy policy | https://devsigner9920.github.io/z8/privacy.html |
| Korean privacy policy | https://devsigner9920.github.io/z8/privacy.ko.html |
| Source repository | https://github.com/devsigner9920/z8 |
| Z8 price / monetization plan | Free, no ads, no in-app purchases, as instructed by the maintainer |
| Package | `dev.devsigner.z8` |

The developer's account-wide monetization plan does not change Z8's pricing.
Do not copy a private contact phone number into a public field without the
maintainer choosing its public use. Confirm the deployed policy's operator name
and links after publishing website updates.

The app name, short description and full description allow at most 30, 80 and
4,000 characters respectively. Avoid misleading capability or affiliation
claims and promotional ranking/price language in metadata. The prepared copy
describes local terminal functionality and optional external tools; it does
not advertise Z8 as an AI model service.
Sources: [listing fields](https://support.google.com/googleplay/android-developer/answer/9859152?hl=en),
[metadata policy](https://support.google.com/googleplay/android-developer/answer/9898842?hl=en).
Release notes allow 500 Unicode characters per language. Paste them inside
the language tags shown by Console when using its combined release-notes field.
[Release-note instructions](https://support.google.com/googleplay/android-developer/answer/9859348?hl=en).

## Images

Use actual captures of the final tested app; never render a mock terminal or
invent successful provider sign-in. A proposed capture order and alt text are
in `screenshot-plan.json`. Root-level capture results must identify the actual
candidate, screen dimensions and files before upload. A plan entry is not
evidence that its screen was captured.
The local capture/output directory for this preparation is
`artifacts/play-store/2026-11-14/`; it is intentionally outside the public source
tree. Its actual asset manifest, when produced, governs which captures exist
and which final candidate they depict.

Asset requirements checked on 2026-11-14:

- App icon: 512 × 512, 32-bit PNG, at most 1,024 KB.
- Feature graphic: 1,024 × 500, JPEG or RGB PNG without alpha.
- Screenshots: at least two in total, up to eight per device type; JPEG or RGB
  PNG, dimensions 320–3,840, longest side no more than twice the shortest.
- For screenshot-based recommendation eligibility, prepare at least four app
  screenshots at 1,080 × 1,920 portrait or 1,920 × 1,080 landscape. This exceeds
  the basic listing minimum.
- Use real app UI, readable text, and no ranking, download-count or promotional
  claims. Keep credentials and personal data out of captures. Tablet assets
  must depict an actual tablet layout.

Source: [Google Play preview assets](https://support.google.com/googleplay/android-developer/answer/9866151?hl=en).
The Console may expose additional fields for selected device types.

## Review and release

Use `submission-checklist.md` and `review-notes.txt` for the next Console steps.
They distinguish known implementation facts from declarations still requiring
review. Do not convert an unconfirmed answer into a declaration to advance the
form. Keep final candidate hashes and QA evidence with the release package.
