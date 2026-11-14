# Play Console worksheet — rc8 preparation

**Current rc8 scope:** final candidate `0.1.0-rc8`, version code `9`, uses
separate finite-work and interactive-terminal foreground services. The service
description below covers that implementation. Its exact identities are:

| Item | Current rc8 value |
| --- | --- |
| Source commit | `b180705dc91a321674d697bea6ae9f6cfa95f501` |
| APK SHA-256 | `0634cdd49f1c4c4ed64a63e6352327090618c16767bb0d721aed3584040f7395` |
| AAB SHA-256 | `b99dfab5910e3ee2a5c350f1a94479e3f4d2072cec7e108887ef0f0357bcde8b` |

The [rc8 source-compliance report](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc8/release-compliance.json)
is **VERIFIED** for this AAB, its notices and matching public corresponding
source. [Independent public-source verification](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc8/public-source-release.json)
confirms the published source bytes and commit. This is a bounded technical
source-delivery result, not Google approval or completion of the privacy
declaration. The APK is development-signed and this AAB unsigned; this worksheet
does not make either upload-ready. Device/provider QA and demonstration scopes
remain identified separately in the release-specific reports.

**rc7 follow-up:** [implemented client notices](../compliance/2026-11-15/implementation.md)
add project-local acknowledgment records, install-time data/terms links and a
notice before app-created client sessions. Provider binaries/authentication and
telemetry settings are unchanged. The [new provider evidence](../compliance/2026-11-15/follow-up-provider-data.md)
narrows the data-control assessment and confirms ordinary Gmail without automatic
forwarding. Artifact identities below describe rc7. The linked rc6 videos remain
historical reference evidence and are not relabeled as recordings of rc7.
The [final rc7 review](../compliance/2026-11-15/final-review.json) adds physical
upgrade/Codex task checks and fresh offline Debian setup, with exact artifact
identities. These functional checks do not finish the data-flow classification.
The [bounded final privacy assessment](../compliance/2026-11-15/support-and-data-safety-final.md)
now supplies concrete draft answers below. The unresolved consumer-Gmail
country particulars concern operator support processing, not an invented
in-app email collector.

Updated **November 15, 2026**. This is an evidence-based preparation worksheet,
not submitted answers or Google approval. No Console setting changed.
Use the [review summary](../compliance/2026-11-15/README.md),
[privacy review](../compliance/2026-11-15/privacy-review.md),
[provider review](../compliance/2026-11-15/provider-review.md) and
[policy review](../compliance/2026-11-15/play-policy-review.md) when resolving
open items. Reconcile any other active Play versions before submission.

## Historical exact artifact — rc7

| Item | Reviewed value |
| --- | --- |
| Release | `v0.1.0-rc7`, version code `8`, package `dev.devsigner.z8` |
| Source commit | `9b13ee5998305c2985f998e805bf524adf33b5af` |
| APK SHA-256 | `9d53696df74a542cd99d5fc78bf5559b60d2ae689cfc46d2b475b78ec550f0e8` |
| AAB SHA-256 | `46ec5946029652d341701dc65cc0644a8761ec638ae5309d0546d5f2415ce5e1` |

The [independent artifact verification](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc7/final-artifact-independent.json)
binds these files to their source, notices and actual dependencies. The final
AAB manifest **contains** `android.webkit.WebView.MetricsOptOut=true`.
It disables WebView usage statistics, **not crash reporting**. Safe Browsing
remains enabled. The APK is development-signed and the AAB unsigned; this
worksheet does not make them upload-ready.

This table remains the immutable rc7 evidence boundary. It does not identify
rc8. Record final rc8 artifact, source, compliance and QA bindings in the
release-specific verification reports after the source snapshot and build;
do not insert a source archive's own final hash into that same snapshot.

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
enters the form. The following choices are a prepared draft for the stated
behavior, not a submitted declaration or Google approval.

| Flow | Established handling | Form treatment / remaining evidence |
| --- | --- | --- |
| Local shell, projects and notifications | Source, HOME, history, credentials, preferences and notification records stay local unless a tool transmits them | Local-only use is outside collection. Do not declare every imaginable terminal payload. |
| Offline base preparation | Included files are unpacked locally | No package download is needed for the initial shell. |
| Optional metadata and tool downloads | Official services receive request paths/version/architecture and network metadata | Optional; no project data or Z8-generated identifier is attached. An IP address alone is not precise location or an Android advertising ID. Supported providers' documented IP-based area determination supports the approximate-location row below. |
| Supported Codex/Claude use | The selected client sends account identifiers, prompts, source context and output to its provider; documented metrics/error paths depend on version/settings | Include the actual categories below. The offline terminal is usable without installing/signing into these clients, so their collection is optional. Do not label provider-retained content ephemeral. |
| User programs and local preview | User commands and page JavaScript/subresources may contact services; local WebView cookies/storage stay on-device | Classify supported, observed flows and page ownership. Controlled content and Google's open-web exception differ. External top-level navigation uses the device browser. |
| Z8's WebView crash reporting | Google's documented WebView path can send crash stacks and an app-specific pseudonymous token when the user permits platform diagnostics | Include Crash logs and Device or other IDs as optional analytics in this draft; exclude unrelated OS/Play/browser telemetry. See the system-service distinction in the final assessment. |
| Support email | The app hands only the public recipient address to an external email app; that app composes/sends the user's message | Exclude from Z8 app collection on this implementation. The operator's later Gmail processing remains covered by the privacy policy and Korean-law assessment. No subject/body/log/attachment is exported by Z8. |

Dormant Git/GitHub activities are not registered or reachable in this release.
Their possible API POSTs are not current UI behavior. Terminal Git or other
user-selected tools need their own factual scope when assessed.

### Prepared form choices

| Question | Draft answer and basis |
| --- | --- |
| Does the app collect or share any listed user data? | **Yes.** Supported clients run in the app environment and transmit task/account data; lack of a Z8 backend does not change this. |
| Is collection required? | **Optional** for the rows below: the core offline terminal needs none of these transmissions. Client diagnostics can occur before a model task, so “optional” means the client/feature can be avoided, not that every packet has a Send button. WebView reporting depends on its optional use and the platform diagnostics choice. |
| Is it processed ephemerally? | **No** for the declared rows. The evidence does not justify an ephemeral-retention exception for provider content, account records or diagnostics. |
| Is there an advertising purpose? | **No established Z8 advertising/marketing purpose.** Do not select an ad purpose merely because a provider's general policy covers other products with ads. |
| Does Z8 provide an app account? | **No.** The operator provides no cross-device user identity/account service. Official clients authenticate to the user's separate provider account. This follows Google's [app-account definition](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en-GB); it is not an exemption for a future Z8 account merely because its registration page is external. |
| Deletion request mechanism | The public privacy URL supplies operator support-data requests and local deletion instructions, plus directs external-provider records to their providers. Describe this exact scope; do not promise that Z8 deletes all provider accounts or logs. Do not claim automatic deletion within 90 days of collection: support retention is 90 days **after resolution**, and is manual. |
| Independent security validation badge | **No.** Internal testing/review is not an approved MASA assessment. |

The data-type choices below are based on the current
[provider evidence](../compliance/2026-11-15/follow-up-provider-data.md), not on
every category in a provider's company-wide privacy policy. All listed rows
are **collected, optional, non-ephemeral**. “Sharing exception” means the
specific user-directed transfer is excluded from sharing; it never changes
the collection answer.

| Data type | Included flow | Purpose | Sharing draft |
| --- | --- | --- | --- |
| User IDs | Provider account identity/authorization used by the signed-in official CLI, including authenticated Codex product-event requests | App functionality; account management; analytics | Yes for the authenticated automatic analytics path. The specific user-directed sign-in/task transfer has a sharing exception, but that does not remove this row's other use. |
| Other in-app messages | User task prompts and conversation/command-output context sent by the selected client | App functionality; analytics for provider service/model improvement where the account/settings allow it | No for the expected user-directed task/feedback transfer. This is the chat-content category; do not double-count the same prompt as Other user-generated content. |
| Files and docs | Source files, filenames and other project documents included in task context | App functionality; analytics for permitted provider service/model improvement | No for the expected user-directed client task. Context may be selected by the client, not only manually attached. |
| Photos | Images/screenshots the user supplies to supported official client image-input features | App functionality; analytics for permitted provider service/model improvement | No for that user-directed input. This does not claim Android photo-library permission, camera access or background gallery scanning. |
| App interactions | Supported client usage/feature events and usage metrics, distinct from Z8-operated analytics | Analytics | Yes for automatic third-party diagnostic/usage handling; do not rely on a task-send exception for it. |
| Diagnostics | Supported client latency, reliability and technical health metrics | Analytics | Yes for automatic third-party handling. |
| Crash logs | Supported Claude error/stack reports under documented eligible account/settings; Z8 WebView crash reports under the platform choice | Analytics | Yes in this draft; do not assume every automatic report is an explicitly directed task transfer. |
| Device or other IDs | WebView's per-app crash token; any supported client installation/session identifier used to associate diagnostic records | Analytics | Yes for those pseudonymous diagnostic identifiers. Do not claim collection of IMEI, advertising ID or MAC address. |
| Approximate location | Provider determination of a general area from a connection IP, where documented for supported account/service use | Fraud prevention, security and compliance; app functionality where the provider uses area for service behavior | Yes for automatic inference/third-party handling; no precise/GPS location is requested by Z8. |

Image inputs are an existing documented capability of the official
[Codex CLI](https://learn.chatgpt.com/docs/cli/reference) and
[Claude Code](https://code.claude.com/docs/en/common-workflows#work-with-images),
not a proposed Z8 upload feature. General-area inference is described by
[OpenAI](https://openai.com/policies/row-privacy-policy/) and
[Anthropic](https://www.anthropic.com/legal/privacy).
The content-purpose rows cover the union of supported account choices, including
provider service/model improvement when allowed by the user's controls;
they do not assert that every API/business account permits training. See
[Claude Code's account-specific training rules](https://code.claude.com/docs/en/data-usage).
This improvement use is recorded as analytics in the draft, not Z8 advertising
or a claim that the Z8 operator receives the content.

Do **not** add Emails, Contacts, phone number, payment details, health data,
installed-app inventory, browsing history, audio/video or precise location
solely because a user could put such material in an arbitrary file or command.
The external-email support button does not collect Email address/Emails.
Provider-only account registration/payment data entered in the external browser
is also not automatically app collection. If a supported in-app path actually
transmits a separate email/name field, add that specific field; account identity
is currently covered by User IDs rather than inferred from every possible
provider registration field.

The sharing draft deliberately does not assert that OpenAI/Anthropic are Z8's
contracted service providers. They provide the user's own selected services.
The versioned [Codex product-event sender](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/analytics/src/client.rs#L951)
attaches account authentication headers to its event POST; the User IDs row is
therefore not limited to user-directed sign-in or declared anonymously.
The app-driven notice names provider/account/content/diagnostic handling and
allows Cancel, but is an acknowledgment, not a universal statutory consent or
an interception of manually typed commands. A broad “nothing is shared” claim
would erase the separate automatic reporting rows.

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
alone do not establish “Yes” for all in-scope collection.

**Prepared encryption answer: Yes for the supported managed/default service
paths**, applying that independent-service scope. The managed proxy/download
paths above enforce TLS; official clients use provider HTTPS endpoints, and
Claude documents TLS for metrics, errors and feedback. Stock Android WebView's
crash uploader uses HTTPS, as linked in the final assessment. This does not
promise encryption for a user-configured HTTP endpoint, user-written server,
external mail route or arbitrary terminal command. Reassess this answer if Z8
itself adds a non-TLS transmitting path; do not change it merely because the
terminal can run a user-directed HTTP client.

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
update is distinct from the frozen APK's local behavior and does not constitute
an automatic mailbox-deletion service.

Project and shared-preview-data deletion are local controls. They do not delete
provider accounts, cloud content or support mail. Z8 has no own registration
service; assess the exact account-creation question against external sign-in
rather than inventing a Z8 deletion endpoint. The
[final support assessment](../compliance/2026-11-15/support-and-data-safety-final.md)
records the limited collection/use basis and isolates the remaining consumer-
Gmail country/overseas-route evidence. No universal provider packet audit is
required by this worksheet. Reconcile the actual submitted build and any other
active Play versions before entering these answers.

## Foreground-service declaration

The rc8 implementation separates two services. Each promotes only for its own
work; it does not enable both types for every operation. Explain the trigger,
user benefit, interruption impact and stop path for each declared feature.

| Service/type | User trigger and actual work | Completion and interruption |
| --- | --- | --- |
| `TermuxService` / `specialUse` | The user opens a terminal and starts an interactive PTY. Immediate shell/command execution and background continuity support terminal commands and local servers. | The terminal notification lasts while real interactive sessions, or their requested shutdown verification, remain. Ending terminal work can terminate commands/servers; reopening never replays them. |
| `Z8PreparationService` / `dataSync` | Explicit initial setup, project environment preparation, selected tool install/update, or confirmed whole-project deletion. Work is finite local extraction/copying/file processing or package download/verification/setup. | The separate notification exposes **Stop tasks**. Android timeout or this action cancels active/queued finite work without stopping unrelated interactive terminals. Retry is explicit. The service ends when no finite jobs remain. |

Whole-project deletion is destructive: once file removal starts, Stop tasks
can leave a partially deleted project. Already deleted files cannot be restored;
the user can retry to remove the remainder. Cancelling before file removal
preserves the files. Do not use a blanket “all files are preserved” explanation
for deletion interruption. Android's **Active apps > Stop** ends the whole app
and is distinct from the finite-work notification action.

These changes address the implementation issue identified in the rc7 review;
they do not alter that release or establish Play eligibility. Review Android's
[dataSync and specialUse definitions](https://developer.android.com/develop/background-work/services/fgs/service-types)
against the matching final artifact and actual demonstrations. Background
continuity is not indefinite execution or automatic restoration. No boot-started
service or scheduled background metadata checker is used.

These historical rc6 videos have public, anonymous byte/hash verification.
They are not evidence for rc8's new service separation or Stop tasks behavior.
The [reviewer page](https://devsigner9920.github.io/z8/review.html) supplies playback:

| Video | Actual scope |
| --- | --- |
| [Offline setup — 126.75 s](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc6/foreground-service-setup-0.1.0-rc6.mp4) | Start/setup disclosure, offline preparation and first shell; no Stop demonstration. |
| [Terminal — 67.89 s](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc6/foreground-service-terminal-0.1.0-rc6.mp4) | User trigger, background continuity and Android Stop. |
| [Selected tools — 134.65 s](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc6/foreground-service-tools-0.1.0-rc6.mp4) | Confirmed Claude update, background progress, notification return and natural completion; no Stop/retry demonstration. |

Google requires [feature explanations and trigger video links](https://support.google.com/googleplay/android-developer/answer/13392821?hl=en).
Its instructions do not mandate YouTube or preapprove GitHub MP4 hosting.
Confirm the actual form accepts reviewer-accessible links; reachability does
not establish FGS eligibility. Attach matching final rc8 trigger/background/stop
recordings and reconcile the prepared data answers, disclosure assessment and
service-type rationale before submitting.
