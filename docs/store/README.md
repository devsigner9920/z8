# Play Store submission materials

Updated on 2026-11-15. English (`en-US`) is the primary listing language;
`ko-KR` is an optional Korean localization. These files prepare the listing;
they do not submit or publish it. Recheck the copy against the final candidate
and the current Console form before submission.

The current release notes and [published preparation ZIP](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc8/z8-play-store-preparation.zip)
refer to **0.1.0-rc8**, version code **9**. The ZIP contains 64 files, including
five actual English screenshots, English/Korean copy, four demonstration videos
and scoped emulator evidence. Its [separate checksum](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc8/store-SHA256SUMS)
and [independent review](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc8/store-bundle-independent.json)
identify the exact bytes. Earlier releases retain their own immutable evidence;
none of this is a completed Play submission.

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
The current unpacked submission directory is
`artifacts/play-store/2026-11-15/rc8/submission/`; it is outside the public source
tree. The ZIP's `capture-manifest.json` binds the five English listing images to
the final APK. These 1080 × 1920 PNGs are RGB 24-bit without alpha; all RGB pixels
match the retained original captures. Original emulator captures and four
unmodified videos are included separately for reviewers. The existing brand
icon/feature graphic retain their original provenance. Korean text is prepared;
Korean listing screenshots and tablet screenshots are not claimed.

Use the ZIP's actual manifest, not the suggested filenames in the older capture
plan. The setup/deletion videos show natural completion, the tools video shows
Stop tasks (retry completed outside the clip), and the terminal video shows
notification Exit. Private phone authentication captures and app binaries are
excluded. The ZIP documents its own emulator scope; phone/provider QA is in the
separate final release record.

Asset requirements checked on 2026-11-15:

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
The detailed [Data safety and foreground-service worksheet](play-console-data-safety.md)
provides concrete draft answers and distinguishes remaining operator/Console work.
They distinguish known implementation facts from declarations still requiring
review. Do not convert an unconfirmed answer into a declaration to advance the
form. Keep final candidate hashes and QA evidence with the release package.
The [November 15 policy and license review](../compliance/2026-11-15/README.md)
retains its historical rc6 baseline with explicit rc7/rc8 follow-ups. See
[current release status](../RELEASE_STATUS.md) for the exact latest candidate and
remaining gates; supplemental documents do not replace historical artifacts.
