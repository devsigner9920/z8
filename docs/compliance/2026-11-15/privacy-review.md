# Privacy review — rc6 and support retention

Reviewed November 15, 2026 against the [rc6 source and artifacts](README.md).
This assessment separates local app behavior, external-provider behavior and
operator-held support mail. It is not a completed Data safety declaration or
an assertion of compliance in every launch country.

## Established behavior

- Fresh preparation supplies an offline Debian shell. Additional tools and
  updates require an explicit action. Daily public-version checks default off;
  enabling them permits foreground checks at most once per 24 hours. Check now
  is a separate one-time action. No project contents, credentials, installed-tool
  inventory or app-generated identifier is attached to those metadata requests.
- The app has no own-account backend, model proxy, advertising SDK or identified
  Z8-operated analytics/error-upload path. These findings do not exclude
  transmissions by installed CLIs, package servers, web content or Android.
- The final AAB manifest disables app backup and includes
  `android.webkit.WebView.MetricsOptOut=true`. The latter disables WebView usage
  statistics, **not crash reporting**. Platform choices and WebView-provider
  behavior still matter. [Android's reporting documentation](https://developer.android.com/develop/ui/views/layout/webapps/webview-privacy).
- Project names, files, HOME, shell history, tool credentials and notification
  records are local unless a command/tool transmits them. Project separation
  does not provide a security boundary between programs with Z8's app permissions.
- The local preview restricts top-level URLs to loopback and hands external
  navigation to the browser. JavaScript and subresources of the user's page can
  still contact external hosts. Clearing preview data does not delete source
  files or external-browser logins.
- App/project deletion and provider logout do not delete provider accounts,
  cloud conversations or remote logs. Z8 has no own registration service to
  which an invented account-deletion endpoint should be attached.

Evidence: `Z8ToolUpdates`, `Z8EnvironmentActivity`, `Z8BrowserUrls`,
`Z8BrowserPane`, `Z8AboutActivity`, `Z8ProjectRemoval`, the exact candidate's
merged manifest, and the scoped QA described in [release status](../../RELEASE_STATUS.md).

## Support retention: corrected in this review

The operator selected **90 days after inquiry resolution**. The
[English](../../privacy.html) and [Korean](../../privacy.ko.html) policies now
identify support email, messages, voluntarily supplied attachments and replies;
their support purpose; Gmail handling; the retention period; permanent deletion
of controlled correspondence/working copies; and access, correction and early
deletion requests through the support contact.

The [operating procedure](support-retention.md) is manual. No mailbox was read
or deleted, and no automatic deletion job was created. The operator must actually
carry out the due-date review and deletion. Google may retain provider-side
copies during its separate deletion/backup process, so the policy does not
promise that every Google backup disappears on day 90.
[Google retention information](https://policies.google.com/technologies/retention?hl=en).

## Data safety and first-use disclosure

The [updated Console worksheet](../../store/play-console-data-safety.md) maps
each supported flow. Local-only data is outside collection; relevant off-device
third-party handling needs assessment. A user-directed sharing exception is not
an exception from collection. Optional status must reflect a real choice; rc6's
offline base helps establish that choice for additional tools. Classify actual
payloads, uses and recipients rather than every possible shell command.
[Google's form guidance](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en).

The remaining evidence concerns exact installed-provider versions and settings:
account/content transfers, default diagnostics, identifiers, purposes and any
pre-login requests. Codex usage-health reporting and Claude telemetry/error
reporting must not be conflated with optional OpenTelemetry or with Z8's own
absence of analytics. See the [provider review](provider-review.md). An update
to an external client can change this evidence without updating the Android APK.

The install dialog already describes external packages, dependencies, separate
terms/accounts and the download action. Detailed prompt/code/output/diagnostic
information is mainly in Settings and the privacy policy. Verify the official
client's first-use flow; add a concise provider-specific disclosure before any
unexpected personal/sensitive-data transmission. Include direct terms/privacy
links and a meaningful choice. This is conditional on the actual handling, not
a finding that all terminal commands require repeated consent. The Codex local
execution-mode choice concerns command isolation and cannot replace a data-use
disclosure. [Google User Data policy](https://support.google.com/googleplay/android-developer/answer/10144311?hl=en).

## Country and operator obligations still to establish

| Area | Finding and bounded follow-up |
| --- | --- |
| Korean support processing | The policy now supplies the previously missing support retention and deletion rule. Confirm the lawful basis and appropriate controller/privacy-responsibility contact details for the actual operator; the public display name and email alone do not settle every statutory item. Do not publish private registration information without deciding the necessary public business contact. |
| Overseas handling of operator support mail | Gmail is disclosed, but the actual recipient arrangement, processing countries, timing/method, purpose/period and refusal information have not been established for Z8's use. Assess the applicable statutory transfer route and publish the required particulars. A general link to Google's privacy policy is not itself the completed transfer assessment. |
| User-selected external clients | Separate the user's own provider relationship from processing undertaken by the Z8 operator. Do not assume every direct user CLI request is an operator-to-processor transfer, or that moving a request into an external CLI removes all Play responsibilities. |
| Global availability | Select the actual countries and age audience, then check applicable provider availability and local privacy/consumer requirements. English-first text alone is not a complete global launch assessment. No all-country compliance conclusion is made here. |

For Korea, [PIPA Article 30](https://law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1034056209)
requires a processing policy covering purposes, retention/destruction, applicable
third parties/processors, rights and responsible contact information.
[Article 28-8](https://law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1020398611)
provides several overseas-transfer routes. Separate consent is one route;
necessary contractual outsourcing/storage with the specified notice is another.
This review does not assume a route applies merely because support is free.

## Release disposition

The support-policy omission is corrected. Final provider/platform classifications,
normal-flow disclosure needs and operator transfer particulars remain open.
Do not copy a blanket “no collection,” “all diagnostics disabled,” “all traffic
encrypted,” or “all remote data deleted” claim into Console. No app binary,
account, provider settings or Console declaration changed in this review.
