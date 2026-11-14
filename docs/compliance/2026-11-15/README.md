# Z8 rc6 policy and license review

Reviewed November 15, 2026. Z8 remains a **local Android terminal and Linux
development environment**, with optional official tools using the user's own
accounts. It is free, with no advertising, in-app purchases, model proxy or
shared provider subscription. This review preserves that product scope.

**Conclusion:** continuing preparation for an ordinary, transparent Play
submission is reasonable. The reviewed provider terms support the official
client arrangement subject to their conditions. The current candidate is
**not ready to be represented as a source-complete, upload-ready release**:
one concrete source omission and bounded reconstruction work remain, alongside
Data safety and foreground-service declaration work. Native-download policy
application remains a material Play review uncertainty.

## Exact baseline

| Item | Reviewed identity |
| --- | --- |
| Source/tag | [`131ce7f3d83b6671121f1f0dedbcbda439f92905`](https://github.com/devsigner9920/z8/tree/131ce7f3d83b6671121f1f0dedbcbda439f92905), `v0.1.0-rc6` |
| App | `dev.devsigner.z8`, `0.1.0-rc6`, version code 7, ARM64, min SDK 28, target SDK 36 |
| Local QA APK SHA-256 | `bed7761c4777ffb31f3009ef58e8a074b79b97d0fe4e77730f06c6f233ea31d7` |
| Unsigned AAB SHA-256 | `4d426219d125bc7f380223e3295c157676e631b3a835a78af6944781a8b5eabd` |
| Public corresponding-source package SHA-256 | `36ff81fc7dd0f9444fff57dab523b8464278a0b1329706348a07f47e0786d10d` |
| Source-input digest | `60b922fb61c0609db66eee91ffd4710a870f083bd6cf66450acde0444fb0af65` |

The [source/preparation prerelease](https://github.com/devsigner9920/z8/releases/tag/v0.1.0-rc6)
contains 16 verified source/store assets and no installable APK or AAB. Its tag,
archives, candidate hashes and QA evidence remain unchanged. This subsequent
review updates repository documentation and the live privacy policy; it does
not silently replace the source package or claim new app runtime tests.

## Findings and concrete next work

| Status | Finding | Next work / completion evidence |
| --- | --- | --- |
| Concrete source gap | The final APK carries Coroutines `DebugProbesKt.bin`; its exact editable source/regeneration inputs and three consumer-rule files are absent from the retained source collection. | Add the pinned inputs and a working reconstruction recipe; verify their relation to the actual shipped library. Details and hashes are in the [license review](license-review.md). |
| Bounded source verification | Kotlin's underlying builtins sources are already retained; build/source-set/serializer mapping or a justified System Library analysis remains. Other JARs already retain substantial sources and POM chains. | Complete a functional reconstruction map and top-level public-input build procedure. Do not treat all 23 JAR collections as proven omissions, require bit-identical rebuilds without cause, or replace evidence with a human-review checkbox. |
| Provider route established, ongoing conditions | Codex's software license and Claude's official product-use terms support unchanged official clients with direct user authentication/billing. The operator's standard Anthropic Commercial Terms assent was recorded previously. | Preserve notices, authentication choices and trademark separation. Add readily accessible provider terms/privacy and Codex license/notice links. No separate vendor approval requirement was found for this arrangement. See [provider review](provider-review.md). |
| Required declaration work | Optional CLI contents, provider diagnostics and platform reports are distinct from Z8-operated analytics. | Finalize the exact version/settings data-flow matrix and Console answers. Verify first-use disclosure and add normal-flow consent where unexpected sensitive handling requires it. See [privacy review](privacy-review.md) and [current worksheet](../../store/play-console-data-safety.md). |
| Operator privacy work | Support retention was unspecified; the operator chose deletion 90 days after resolution. Gmail handling and deletion scope are now disclosed. | Carry out the [manual retention procedure](support-retention.md). Establish applicable operator/overseas-processing particulars for launch countries; the general provider-policy link is not a complete transfer assessment. |
| Play interpretation risk | Optional native Linux downloads and PRoot do not have an expressly confirmed exception for Z8. Current Play terminal implementations support a reasoned submission attempt. | Disclose actual native delivery/execution and submit through ordinary review. Another app's presence is not transferable approval. Do not require an unsolicited advance inquiry or mislabel PRoot a security VM. See [Play review](play-policy-review.md). |
| Foreground-service justification | Interactive terminal continuity has a credible `specialUse` rationale. Standalone downloading/unpacking overlaps transfer/local-processing service types. | Explain the actual phases and alternatives; use the three exact rc6 videos within their recorded scopes. Change service architecture only if that assessment requires it, then retest. |
| Conditional AI-content scope | The product supplies terminal tooling, not model access; optional AI-client output is nevertheless visible in the app. | Retain the factual terminal/productivity rationale. If Google applies its AI-generation policy to the feature, meet its reporting/moderation requirements; do not claim a confirmed exemption based on the product label alone. |

The source review did not establish an incompatible license in the shipped
combination. Inventory labels are upstream declarations, not substitutes for
the original file licenses. In particular, coarse talloc/PRoot recipe labels
must not be used to invent a GPL-version conflict. Logo/Prism GPL publication
rights were already confirmed by the maintainer; external clients remain under
their own licenses, and Claude Code is not relicensed under Z8's GPL.

## Changes made by this review

- Updated the English/Korean privacy policy with support data, purpose, Gmail,
  90-day post-resolution retention, controlled-copy deletion and rights contact.
  Provider backups and sender copies are explicitly separate.
- Added the support retention operating procedure; **no deletion automation or
  mailbox action** was performed.
- Replaced the stale rc4 Data safety worksheet with the rc6 facts and remaining
  decisions; corrected release-status and store-material references.
- Added separate Play, provider, license and privacy assessments with primary
  sources, artifact identities and attainable follow-up actions.

This is a technical and policy assessment, not a legal opinion, provider
endorsement, Play approval or completed declaration. It does not sign or publish
an app binary. Separate practical gates remain in [release status](../../RELEASE_STATUS.md),
including upload-signing readiness, exact final device validation and the actual
Console requirements. No provider inquiries were sent.
