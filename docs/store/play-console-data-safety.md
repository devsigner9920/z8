# Play Console worksheet — rc6

**rc7 follow-up:** [implemented client notices](../compliance/2026-11-15/implementation.md)
add project-local acknowledgment records, install-time data/terms links and a
notice before app-created client sessions. Provider binaries/authentication and
telemetry settings are unchanged. The [new provider evidence](../compliance/2026-11-15/follow-up-provider-data.md)
narrows the data-control assessment and confirms ordinary Gmail without automatic
forwarding. Artifact/video identities below remain rc6; bind final answers to
the actual rc7 candidate before submission.

Updated **November 15, 2026**. This is an evidence-based preparation worksheet,
not submitted answers or Google approval. No Console setting changed.
Use the [review summary](../compliance/2026-11-15/README.md),
[privacy review](../compliance/2026-11-15/privacy-review.md),
[provider review](../compliance/2026-11-15/provider-review.md) and
[policy review](../compliance/2026-11-15/play-policy-review.md) when resolving
open items. Reconcile any other active Play versions before submission.

## Exact artifact

| Item | Reviewed value |
| --- | --- |
| Release | `v0.1.0-rc6`, version code `7`, package `dev.devsigner.z8` |
| Source commit | `131ce7f3d83b6671121f1f0dedbcbda439f92905` |
| APK SHA-256 | `bed7761c4777ffb31f3009ef58e8a074b79b97d0fe4e77730f06c6f233ea31d7` |
| AAB SHA-256 | `4d426219d125bc7f380223e3295c157676e631b3a835a78af6944781a8b5eabd` |

The final AAB manifest **contains** `android.webkit.WebView.MetricsOptOut=true`.
It disables WebView usage statistics, **not crash reporting**. Safe Browsing
remains enabled. The APK is development-signed and the AAB unsigned; this
worksheet does not make them upload-ready.

## Current behavior

- Fresh setup unpacks an included Debian base and provides an offline shell.
  Python, Git, Node and external clients require explicit tool actions.
  Existing Ubuntu environments/templates and user files remain preserved;
  not every upgraded installation or newly cloned project becomes Debian.
- Daily public-version checks default **off**. Opting in permits a check when
  the app opens, at most once per 24-hour attempt interval. **Check now** is a
  separate one-time action. Neither path installs or updates software.
- Metadata requests use fixed official HTTPS endpoints for GitHub/OpenAI,
  Anthropic and Node.js. They attach no project files/names, credentials,
  installed-tool inventory or app-generated identifier. Recipients still see
  connection/request metadata, including IP addresses. Results stay local;
  there is no scheduled background checker.
- Managed Claude launches disable its native auto-updater. User commands and
  custom programs remain separate. No Z8 account backend, model proxy,
  advertising SDK or Z8-operated analytics/error-upload path was identified.

## Data safety mapping

Google's [form guidance](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en)
counts relevant off-device third-party handling as collection, regardless of
whether Z8 owns a server. Local-only processing is excluded. A user-directed
**sharing** exception does not remove **collection**. Ephemeral collection still
enters the form. These are working classifications, not ready-to-copy answers.

| Flow | Established handling | Form treatment / remaining evidence |
| --- | --- | --- |
| Local shell, projects and notifications | Source, HOME, history, credentials, preferences and notification records stay local unless a tool transmits them | Local-only use is outside collection. Do not declare every imaginable terminal payload. |
| Offline base preparation | Included files are unpacked locally | No package download is needed for the initial shell. |
| Optional metadata and tool downloads | Official services receive request paths/version/architecture and network metadata | Establish actual recipient use/retention. IP receipt alone does not establish precise location or a device-ID category; declare inferred location if actually used that way. These actions are avoidable while using the offline shell. |
| Supported Codex/Claude use | The selected client can send account identifiers, prompts, source context, output and diagnostics directly to its provider | Resolve **User IDs**, actual content/file types and applicable diagnostics/identifiers per supported version/settings. Installation and authenticated-task QA do not prove a complete telemetry inventory. |
| User programs and local preview | User commands and page JavaScript/subresources may contact services; local WebView cookies/storage stay on-device | Classify supported, observed flows and page ownership. Controlled content and Google's open-web exception differ. External top-level navigation uses the device browser. |
| Android/WebView reporting | Platform/provider reporting may transmit crash information under platform settings | Confirm applicable **Crash logs**, **Diagnostics** and identifiers against actual provider behavior. The manifest opt-out is not an all-diagnostics opt-out. |
| Support email | Gmail receives the user's email address, message, replies and volunteered attachments for the operator | Assess these actual support types within the form's scope; do not infer access to the user's mailbox or browser history. See retention below. |

Dormant Git/GitHub activities are not registered or reachable in this release.
Their possible API POSTs are not current UI behavior. Terminal Git or other
user-selected tools need their own factual scope when assessed.

### Answers requiring a final decision

- **Collected/shared:** do not select blanket “No data collected” based on no
  Z8 server. Document supported recipients/payloads. An expected explicit send
  may qualify for a sharing exception; unrelated diagnostics do not
  automatically inherit it.
- **Types/purposes:** choose actual message/content/file categories, not every
  theoretical script. App functionality and applicable account management are
  likely purposes for verified client flows; analytics needs actual diagnostic
  evidence. No Z8 advertising purpose was established.
- **Optional/required:** optional tools can be avoided, but check pre-login and
  default reporting behavior. Do not assume provider retention is ephemeral.
- **Provider evidence:** record client version, account/settings, pre-login
  behavior, diagnostic types/IDs, purposes and controls. Codex usage/health
  reporting is distinct from opt-in OpenTelemetry; Claude telemetry, errors
  and feedback differ by settings/account. Reassess relevant client updates,
  rather than every possible user program.

## Encryption and disclosure

Managed APT requests routed through `Z8SetupDownloadProxy` upgrade allowed
Debian/legacy Ubuntu HTTP paths to off-device TLS with Android trust and
hostname verification. The guest-to-proxy HTTP leg is loopback only. HTTPS
CONNECT preserves guest TLS. Native tool downloads and metadata use HTTPS.
This covers those managed paths, not all later client requests.

Google's [encryption FAQ](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en)
separately recognizes apps that let users transfer data to independently
operated services. Apply that scope before deciding the answer: arbitrary
user HTTP commands alone do not establish “No,” and HTTPS installer downloads
alone do not establish “Yes” for all in-scope collection. Record relevant
provider/platform transport evidence and the reasoning used.

[Android's WebView documentation](https://developer.android.com/develop/ui/views/layout/webapps/webview-privacy)
confirms usage opt-out does not disable crash reports. Do not claim all automatic
reporting is disabled. Unexpected personal/sensitive-data handling requires
normal-flow disclosure and affirmative choice before it; buried policy text or
Codex execution-mode consent is not a substitute.
[Google User Data policy](https://support.google.com/googleplay/android-developer/answer/10144311?hl=en).

## Retention and deletion

The operator adopted support-mail retention of **handling time plus 90 days
after resolution**. The updated [public policy](../privacy.html) and
[manual procedure](../compliance/2026-11-15/support-retention.md) cover permanent
deletion of operator-controlled correspondence/working copies and earlier
requests. Gmail's provider-side deletion/backups and senders' copies are
separate. No automatic deletion job was created. This web-policy/operating-rule
update does not alter the frozen APK.

Project and shared-preview-data deletion are local controls. They do not delete
provider accounts, cloud content or support mail. Z8 has no own registration
service; assess the exact account-creation question against external sign-in
rather than inventing a Z8 deletion endpoint. Operator contact and overseas
support-processing particulars remain in the privacy review.

## Foreground-service declaration

The manifest uses `specialUse` for user-started terminal work, base preparation
and selected tool operations. Explain each feature's trigger, user benefit,
interruption impact and stop path. Interactive shells need immediate execution;
interruption can terminate commands or servers. Background continuity is not a
promise of indefinite execution or automatic restoration.

Standalone downloading/unpacking overlaps Android's `dataSync` examples;
sharing a service class does not itself justify `specialUse`. Retain the
feature-specific explanation and review the [service types](https://developer.android.com/develop/background-work/services/fgs/service-types#special-use).
Metadata checks are not a scheduled foreground service.

These final-candidate videos have public, anonymous byte/hash verification.
The [reviewer page](https://devsigner9920.github.io/z8/review.html) supplies playback:

| Video | Actual scope |
| --- | --- |
| [Offline setup — 126.75 s](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc6/foreground-service-setup-0.1.0-rc6.mp4) | Start/setup disclosure, offline preparation and first shell; no Stop demonstration. |
| [Terminal — 67.89 s](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc6/foreground-service-terminal-0.1.0-rc6.mp4) | User trigger, background continuity and Android Stop. |
| [Selected tools — 134.65 s](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc6/foreground-service-tools-0.1.0-rc6.mp4) | Confirmed Claude update, background progress, notification return and natural completion; no Stop/retry demonstration. |

Google requires [feature explanations and trigger video links](https://support.google.com/googleplay/android-developer/answer/13392821?hl=en).
Its instructions do not mandate YouTube or preapprove GitHub MP4 hosting.
Confirm the actual form accepts reviewer-accessible links; reachability does
not establish FGS eligibility. Complete unresolved data classifications,
disclosure assessment and service-type rationale before submitting.
