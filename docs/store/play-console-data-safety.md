# Play Console Data safety and foreground-service worksheet

Prepared 2026-11-14. English is the primary submission language. This is a
source-based draft, not a submitted declaration or a finding of Play approval.
No provider login, model request or Console change was performed for this review.

## Build and evidence boundary

The artifact inspected was rc4, version code 5:

- APK SHA-256: `4da85d8f53ff3ebadcc46ebf90bef6db6051ece321a6cd31f561fb25ca95b425`
- AAB SHA-256: `d78a518dace647e4e279a1a6cfe8080ee2940b0ff77d86d0d8c05c9dab9b7278`
- Current source additionally sets `android.webkit.WebView.MetricsOptOut=true`.
  This change requires a new candidate and inspection of its merged manifest.
  It does not retroactively change rc4 or disable all WebView crash reporting.
- The next candidate is being rebuilt with Debian 13.7 (trixie) as its bundled
  base. The rc4 image and traffic observations below remain historical Ubuntu
  evidence. Do not apply their hashes or successful tests to the new image.

### Pending Debian candidate differences

The new bundled base uses the official `deb.debian.org/debian` and
`deb.debian.org/debian-security` repositories. Existing Ubuntu projects and
their HOME/source remain in place; no project conversion, prepared-template
deletion or global setup-reset migration is introduced. A previously prepared
Ubuntu template is still used for new projects on that existing installation.
Debian is the fresh-install default, not a claim that all installations or all
new projects after an update have been converted. The physical-device update
will exercise preserved Ubuntu; fresh Debian runtime testing is planned on a
dedicated emulator, so physical-device Debian behavior remains unverified.

For **initial setup through `Z8SetupDownloadProxy`**, current source upgrades
allowed APT HTTP requests to HTTPS on port 443 using Android's default trust
store and explicit HTTPS hostname verification. Both DNS and the socket stay
on the selected Android network. The guest-to-proxy HTTP leg is loopback only;
existing guest APT configuration is not rewritten. This permits a minimal
Debian image to install CA certificates without an off-device HTTP bootstrap.
Only Debian archive/security and legacy Ubuntu package paths are accepted for
this upgrade. Redirects are not automatically followed; a subsequent allowed
HTTP request is upgraded again. CONNECT continues to carry the guest's TLS.

Host tests use actual TLS fixtures and reject a trusted certificate for the
wrong host and an untrusted certificate for the correct host. They also cover
both Debian paths, legacy Ubuntu routing and redirect behavior. Android
candidate integration and fresh Debian installation still require verification.
This improvement is limited to requests routed through that setup proxy:
project-level installers invoked without it and user commands do not inherit
an all-transfers-encrypted guarantee.

Reconcile this worksheet with the final artifact, active Play versions,
[public privacy policy](../privacy.html), actual provider versions/settings,
and the questions displayed by Console. The previous candidate's runtime
tests do not establish the new candidate's behavior automatically.

## Official rules used

Google counts off-device transfers, including relevant third-party code;
local-only processing is excluded. Controlled WebView content differs from
open-web browsing. Ephemeral transfers still enter the form. Sharing has
exceptions, including reasonably expected user-directed transfers; an exception
to sharing does not itself exempt collection. Optional collection must be
avoidable by all users. IP classification depends on actual use, not merely
the existence of an IP address. Encryption is assessed across in-scope
transfers. See Google's [Data safety definitions and form guidance](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en).

The labels below are **working classifications**, not Google rulings for a
general-purpose terminal. Google's [code-review guidance](https://developer.android.com/privacy-and-security/declare-data-use)
also identifies forms, account flows, WebViews and third-party components as
areas to inspect. A permission list alone is insufficient.

## What this candidate actually exposes

Z8 provides local terminals, project storage, environment preparation, local
web preview, notifications and settings. It has no Z8 account backend, model
proxy, advertising SDK or app-operated analytics/error-upload path identified
in this review. That finding does **not** settle all third-party transmissions.

The repository retains `Z8GitHubActivity`, `Z8GitHub` and `Z8GitActivity` source.
Their code can invoke `gh api GET /user`, query repositories/PRs/issues, clone
over HTTPS, and POST draft-PR/review content. However, **rc4 does not register
the Git/GitHub activities in its APK manifest and the current navigation does
not expose them**. The preparation test explicitly checks their absence.
Do not describe this dormant UI as an active rc4 feature or declare its POST
traffic as observed current behavior. Reassess it if a later build enables it.
Users can separately run Git or `gh` in a terminal.

## Data-flow mapping

| Implemented path | Data and destination | Working form treatment | Required evidence or limit |
| --- | --- | --- | --- |
| Project storage and shell | Names, source files, HOME, history, settings and tool credentials remain in app storage unless a command/tool sends them | Local-only use is outside collection; do not mark every stored file as uploaded | `Z8Projects`, `Z8Guest`, `Z8ProjectRemoval`; inspect the selected tool before extending this conclusion |
| Local notification integration | Event/time and project/session identifiers are recorded locally; original prompt text is not copied to notification history | Local-only records are outside collection | `Z8AttentionInbox`, bridge/hook code; provider-side hook behavior is separate |
| Initial environment preparation | Distribution package requests (rc4 Ubuntu; next bundled base Debian), package paths/version/architecture, ordinary request/network metadata reach distribution servers; Node downloads reach nodejs.org | Request metadata/IP use needs provider-specific classification. Setup is needed for the usable development environment; clicking Start alone does not make every setup data type optional | `Z8InitialSetup`, `Z8SetupDownloadProxy`, `provision.sh`, `install-node.py`; provider logging/retention is not established by local code |
| Optional CLI download | Explicit installer retrieves pinned Codex/Claude artifacts from official hosts | Separate download metadata from later account/content traffic; installation is optional | `install-ai.sh` validates HTTPS hosts, hashes and sizes. It does not prove later tool telemetry, retention or encryption |
| Supported optional CLI use | User-selected provider may receive account credentials/identifiers, prompts, source context, command output and diagnostics | Candidate types to verify: **User IDs**, **Other in-app messages / Other user-generated content**, **Files and docs**, and provider-specific diagnostics/IDs. Select only types actually transmitted by the tested version/settings | No authenticated candidate trace was obtained in this review. Do not infer every possible category from what arbitrary user code could send. Do not assume user installation creates a blanket collection exception |
| User-run Git, gh, packages and other programs | Chosen commands can contact their chosen services; Git upload may include source, commit author details and messages | Record the tested workflow and applicable types; do not declare all imaginable user programs as built-in Z8 collection | Current shell permits user programs; the dormant GitHub UI is not a substitute for observing the terminal workflow |
| Built-in local preview | WebView stores cookies/site storage/cache; loopback page code can itself contact external hosts | Loopback storage/traffic stays local. Evaluate page-controlled external traffic separately; do not automatically treat all local development pages as either Z8-owned content or Google's open-web exception | `Z8BrowserUrls`, `Z8BrowserPane`: localhost top-level preview, JavaScript/DOM storage enabled, external top-level URLs routed to browser; subresource behavior and page ownership still matter |
| Android WebView reporting | Platform reporting may send diagnostics to Google under the user's platform setting | Review **Crash logs**, **Diagnostics**, **App interactions**, and pseudonymous **Device or other IDs** against actual provider behavior; this is separate from Z8's own analytics claim | See platform qualification below; classification and optional status need final provider/settings evidence |
| External browser and support email | Browser handles external sites/sign-in; email client sends a user-written support message to the operator | Assess the explicit handoff and operator's received support data separately. Z8 does not collect the entire browser history or mailbox merely by opening an intent | `Z8BrowserPane`, `Z8AboutActivity`, privacy policy; do not claim remote provider accounts are deleted by Z8 |

Potential content categories are alternatives to resolve from the real
payload, not instructions to select all of them. A typed PR review, a model
conversation and an uploaded source file are different flows. If GitHub UI
is enabled later, account verification, list queries, clone and each POST
must receive their own entries. Its account check actually sends a request;
it is not just reading a local login flag.

## Collection, sharing, purposes and choice

Do not submit **No data collected** merely because Z8 has no server. Equally,
do not report every conceivable sensitive category a user could place in a
terminal. The final answer must cover the supported, in-scope behavior and
provider settings established for the release.

For verified optional account/content flows, proposed purposes are **App
functionality** and, where actually applicable, **Account management**.
Provider diagnostics may require **Analytics** or other purposes after its
documentation/settings review. No advertising/marketing purpose has been
established for Z8 itself. Do not label a provider Z8's service provider merely
because its API is used; the operator does not control those services' data
practices.

A user's explicit send/upload action may support a sharing exception for the
expected recipient and payload. It does not automatically cover unrelated
diagnostics, background transmissions or recipient onward use. Preserve a
per-flow explanation before selecting “not shared.” Provider retention is
unverified here: do not mark account/content transfers ephemeral based on the
absence of a Z8 database.

## Encryption: confirmed scope and open questions

| Path | What the implementation establishes |
| --- | --- |
| Node and managed optional CLI artifacts | HTTPS URLs with host checks; artifact hashes provide integrity checks |
| Ubuntu packages in the inspected rc4 image | The actual embedded `rootfs.zip` contains `ubuntu.sources` with `URIs: http://ports.ubuntu.com/ubuntu-ports/`. The setup proxy permits HTTP port 80 as well as HTTPS CONNECT. Package signatures/hashes do not encrypt the request |
| Pending Debian candidate's initial setup proxy | Current source upgrades exact allowed APT paths to certificate- and hostname-verified TLS:443; local guest-to-proxy HTTP remains on-device. This is not a statement about rc4 or commands outside that proxy, and Android integration is not yet verified |
| Local preview | HTTP loopback is supported; this is on-device traffic, not proof of unencrypted off-device collection |
| User programs and chosen development pages | Their transport is not universally enforced by the Android network-security XML. HTTPS artifact delivery does not establish the transport of later CLI requests |
| Dormant GitHub UI | Code specifies github.com HTTPS/API paths, but this UI is absent from rc4's registered activities |

Google also discusses user-directed transfers to independently operated
services in its [encryption guidance](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en#zippy=%2Cother-app-and-data-disclosures).
Determine which transfers fall within that rule before answering. The current
evidence does not support an unconditional **all data encrypted in transit**
claim. It also does not establish that every arbitrary command's destination
must be treated as a Z8 server. Document the chosen scope and any remaining
HTTP request-metadata classification explicitly.

## WebView reporting qualification

Android documents user-consented WebView usage statistics and crash reports,
including separate pseudonymous tokens. `MetricsOptOut=true` disables usage
statistics, **not crash reporting**. The inspected rc4 manifest lacks that
flag; the next-build source adds it. Verify the final merged manifest and
provider behavior before declaring the corresponding data types or claiming
all automatic diagnostics are disabled. Safe Browsing remains enabled; this
change does not disable that protection.
[Official WebView privacy documentation](https://developer.android.com/develop/ui/views/layout/webapps/webview-privacy).

## Account and deletion answers

Z8 has no own-account registration. External provider eligibility/login is a
separate flow, so do not invent a Z8 account deletion website. Review the exact
Console account-creation question against the final external sign-in path.

The app offers project deletion and shared-preview-data deletion. Both were
observed on rc4; project deletion stops its processes and preserves other
projects. These are local controls, not evidence that cloud conversations,
GitHub content, support emails or provider logs are erased. The operator's
privacy contact can receive requests about information the operator holds;
provider-held information requires the provider's process. Finalize the form's
deletion answer only after documenting that scope.

## Foreground-service declaration and video

The manifest-generation source declares `specialUse` for user-started terminal
sessions and development-environment preparation. Proposed explanation:

> Users start terminal sessions to run local development commands and may
> continue using other Android apps while those commands run. Deferring a
> command prevents the immediate terminal interaction the user requested.
> Interrupting it can terminate a shell, build or local development server.
> Users can close terminals or stop the app; notification availability follows
> Android notification settings. Initial environment preparation is also a
> user-started task and can continue while the user switches apps.

Use this wording only with the final manifest and tests. Do not claim Android
guarantees indefinite background execution or restoration of terminated shells.

Google's FGS instructions require a video link showing the user steps that
trigger each declared feature. The page does not prescribe YouTube or certify
GitHub-hosted direct MP4 URLs. An anonymously reachable direct video is a
reasonable link candidate, **not a guarantee of Console acceptance**. Check
that the actual form accepts it and that a signed-out reviewer can play it;
otherwise provide a reviewer-accessible streaming link. Requirements for
background-location videos are not automatically FGS requirements.
[Official FGS declaration instructions](https://support.google.com/googleplay/android-developer/answer/13392821?hl=en).

Existing evidence: `foreground-service-demo.mp4`, 79.01 seconds, 1104 × 920,
SHA-256 `7653da4cceccf47a29a2edee021d795bbf893fdc690ad584a7757fe368d51f0d`.
The planned rc5 standalone asset and `docs/review.html` playback page are not
yet published or verified by this worksheet; insert their final URLs only
after publication and anonymous playback checks.
It shows a command in an already open terminal, Home/background, return with
progress, then Android's Active apps Stop control. The app notification's
Exit action is captured separately. It does **not** show opening the initial
terminal session or starting environment preparation. Add trigger/initial-setup
coverage before relying on it for both declared FGS features; do not describe
the existing clip as covering those unrecorded steps. A video URL by itself
also does not replace the functionality, interruption-impact and use-case
answers in the declaration.

## Items to close before Console submission

- Record the final candidate hash and merged-manifest metrics opt-out result.
- Resolve the specific supported CLI/provider transmission defaults and
  platform-reporting scope; retain a payload/category/purpose/recipient matrix.
- Resolve download request metadata, provider retention and the encryption
  answer. Update public policy if the settled facts require more specific text.
- Recheck that Git/GitHub activities remain unavailable; reassess if enabled.
- Review deletion/contact handling and the exact account-creation wording.
- Add complete FGS trigger coverage and verify the submitted video URL without
  authentication. Mark all remaining uncertainty as unresolved, not PASS.
