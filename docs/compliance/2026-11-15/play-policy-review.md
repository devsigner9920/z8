# Google Play policy review — published rc6

Reviewed **2026-11-15** against source commit
`131ce7f3d83b6671121f1f0dedbcbda439f92905`, tag `v0.1.0-rc6`, version code 7.
APK: `bed7761c4777ffb31f3009ef58e8a074b79b97d0fe4e77730f06c6f233ea31d7`.
AAB: `4d426219d125bc7f380223e3295c157676e631b3a835a78af6944781a8b5eabd`.

This review records official requirements, observed implementation and reasoned
interpretations separately. It does not grant Google approval, change the
published artifacts, submit a Console declaration, contact a provider, or
approve third-party licenses/contracts. The product remains a local terminal
and development environment for tools chosen by users.

## Decision

**A transparent ordinary Play submission remains a defensible route.** The
native-download interpretation is a material review uncertainty, not an
established categorical prohibition of this PRoot terminal. Do not represent
this review or another app's listing as confirmation that an exception applies.
Finalize the actual Data safety and foreground-service declarations before
submitting; the current rc6 worksheet separates verified behavior from pending
classification decisions and is not a ready-to-copy declaration.

| Priority | Finding | Practical disposition |
| --- | --- | --- |
| High review uncertainty | Optional APT, Node and CLI downloads contain native code; the applicable execution exception is not conclusively resolved for this design | Disclose every supported path and use the documented terminal submission basis; retain a contingency if review rejects the execution model |
| Required submission work | Data safety needs the current optional-provider, metadata and platform-reporting matrix | Complete the per-flow assessment; neither blanket “no collection” nor every conceivable shell payload is justified |
| Medium review uncertainty | All terminal, unpacking and tool-operation work currently uses `specialUse` | Explain the distinct work and interruption impact, include trigger/stop demonstrations, and address overlap with transfer/local-processing types |
| Conditional requirement | AI-content policy applicability depends on the delivered product/feature, not the absence of a Z8 model server alone | Preserve the general-purpose terminal rationale; if treated as a generative-AI feature, meet its reporting and content safeguards |
| Targeted improvement | CLI installation confirms source/dependencies/terms, while detailed content-transmission disclosure mainly sits in privacy/settings | Evaluate the actual first-use provider disclosure; add concise disclosure before the affected flow if unexpected sensitive-data handling is present |

## 1. Executable delivery and device/network abuse

**Official rule.** Play restricts app self-updates and external executable-code
downloads. It includes an exception for code running in a VM/interpreter that
provides indirect Android API access; native code is expressly included in the
violation examples. User initiation is not a separately stated download
exception. The policy also prohibits unauthorized interference and service/API
use contrary to the service's terms.
[Device and Network Abuse](https://support.google.com/googleplay/android-developer/answer/16559646?hl=en).

**Observed rc6 paths.**

- The Android host, PRoot loader and Debian base are included. `provision.sh`
  prepares an offline shell; it no longer performs the old full tool download.
- `tool-manager.sh` explicitly invokes APT and the Node/Codex/Claude installers.
  Selected versions and official-host integrity checks constrain the managed
  installers. The downloaded payloads still include ARM64 ELF executables and
  libraries. Python as the downloader does not change their payload type.
- Daily checks are opt-in, metadata-only and foreground-triggered. They cannot
  install a release. Users must confirm tool downloads/updates. Normal managed
  sessions set `DISABLE_AUTOUPDATER=1`; this is not a general prohibition of
  commands or custom configuration chosen by users.
- `Z8Guest` launches PRoot with project/HOME mounts and the same Android app
  permissions. `Z8RuntimeLauncher` uses the system linker where needed. User
  commands and provider tools can also fetch code. There is no APK/DEX updater
  in these inspected paths.

**Interpretation.** The policy does not define a separate-kernel or CPU-emulation
test. PRoot's architecture therefore neither proves an exception nor proves
rejection. Project separation and hashes support security; they do not settle
this classification. No advance support inquiry is stated as a prerequisite.
The already selected ordinary submission route remains reasonable.

**Current comparator, independently rechecked.** The public
[Termux Play listing](https://play.google.com/store/apps/details?id=com.termux&hl=en)
continues to describe APT package installation; the page rendered an October 10,
2026 update date during this review. Its
[Play-specific maintainer repository](https://github.com/termux-play-store)
describes a separate codebase adapted to current target-SDK and permission
requirements. The
[pinned launcher implementation](https://github.com/termux-play-store/termux-apps/blob/fea9fe2cfc484c621e5bf7e42875dab3277b8f90/termux-app/src/main/java/com/termux/app/TermuxShellUtils.java#L77-L88)
uses the Android linker for private ELF files. The Play package tree also has
[PRoot](https://github.com/termux-play-store/termux-packages/blob/master/packages/proot/build.sh)
and [PRoot-Distro](https://github.com/termux-play-store/termux-packages/blob/master/packages/proot-distro/build.sh)
recipes. These are relevant primary implementation evidence, not a Google
interpretation, proof of each currently served package, or transferable Z8
approval. The listing's Data safety claims likewise cannot be copied to Z8.

**Concrete paths.** Submit the actual local-terminal architecture with the
existing factual native-download review notes and exact build evidence. If
Google rejects that interpretation, reassess the stated reason rather than
renaming binaries or hiding install buttons. Genuine alternatives include
Play-delivered native code with external native installation/update paths
removed, a suitably bounded interpreter design, or remote execution. Each is a
substantial product/engineering change and needs its own review. Keeping the
full local edition on another authorized distribution channel is also a
separate distribution choice, not a way to conceal behavior in the Play build.
Play Asset Delivery is unsuitable for native executable payloads: Google's
[asset-pack description](https://developer.android.com/guide/playcore/asset-delivery)
excludes executable code.

Security checks remain useful independently. Google's
[dynamic-code-loading guidance](https://developer.android.com/privacy-and-security/risks/dynamic-code-loading)
recommends minimizing dynamic loading, trusted storage/sources and integrity
validation; those mitigations do not grant a Play-policy exception. The managed
installers use HTTPS, fixed official sources, hashes, staged publication and
preservation of modified installations. Claude additionally verifies its signed
manifest. User-installed programs do not automatically inherit all these checks.

## 2. Foreground services

**Official requirements.** FGS use must serve a relevant core feature, be
user-initiated or perceptible, be stoppable, need timely/continuous execution
for the expected experience, and last only as long as needed. Declaring a
permission alone does not establish eligibility.
[FGS policy](https://support.google.com/googleplay/android-developer/answer/16559646?hl=en).

Android documents `specialUse` for valid use cases outside the other types and
reviews the manifest's free-form subtype explanation. `dataSync` expressly
covers transfers and some local processing. A shared Java service does not by
itself decide the right type for every operation.
[Android service types](https://developer.android.com/develop/background-work/services/fgs/service-types#special-use).

**Observed.** The generated manifest declares `specialUse` and explains terminal
sessions, environment preparation and selected tool installation. Service hooks
release foreground lifetime when execution is idle. `Z8ToolManager` begins only
from an explicit request, checks the selected network, stops its proxy on
connection loss, and requires explicit retry. Operation notifications distinguish
installation/update and return to the relevant project's Tools screen. Metadata
checks use ordinary asynchronous foreground work, not an FGS or background
scheduler.

**Assessment and next action.** An interactive shell, build or local server has
a credible immediacy/continuity rationale. Initial unpacking and a standalone
package download should receive their own explanation; they overlap Google's
transfer/local-processing examples. Explain whether the operation is an
inseparable terminal installation transaction and why the alternatives do not
fit. If the implementation instead separates pure downloads, assess
user-initiated data-transfer jobs or `dataSync` for that phase and retest the
changed service behavior. Do not add `dataSync` solely as a declaration shortcut.

The Console declaration needs functionality, interruption/deferral impact,
use-case selection and a video showing the user trigger for each declared
feature. Include background continuation and the real stop control. Google
accepts a video link in the guidance; it does not certify GitHub MP4 hosting or
require YouTube there. Test the final URL in the actual form and as a signed-out
reviewer.
[FGS declaration guidance](https://support.google.com/googleplay/android-developer/answer/13392821?hl=en).
The separate [preview](https://support.google.com/googleplay/android-developer/answer/16965181?hl=en)
changes geofencing on January 27, 2027; it is not a current new restriction on
this terminal.

## 3. Personal/sensitive data and declarations

**Official rule.** Google's User Data policy expressly includes third-party AI
products/services/code. The app remains responsible for compliant data handling;
not owning the recipient server is insufficient. Unexpected personal/sensitive
data access or transmission needs normal-flow prominent disclosure and prior
affirmative consent. A privacy-policy link alone does not meet that conditional
requirement. Sensitive transfers require appropriate cryptographic protection.
[User Data policy](https://support.google.com/googleplay/android-developer/answer/10144311?hl=en).

**Observed.** Offline base preparation, local source/HOME storage and notification
history do not themselves upload project data. Version checks send public
requests to GitHub, Anthropic and Node.js without credentials, project names,
files or installed-tool lists; ordinary connection metadata still reaches them.
The opt-in dialog and Check now area explain this. The optional CLIs use the
user's provider accounts and can transmit prompts, code and command output;
provider defaults/diagnostics require their own assessment. The proxy upgrades
its narrowly allowed APT HTTP requests to validated upstream TLS, but arbitrary
shell traffic is not universally forced through it.

**Concrete gap to resolve.** `Z8EnvironmentActivity.confirm()` explains packages,
source, terms/accounts and the download choice. `openTool()` can launch an
installed client directly. The detailed prompt/code/diagnostic disclosure is in
`Z8AboutActivity` and the web privacy policy. Verify what the exact provider
version shows before its first relevant transfer, including diagnostics before
login. If additional sensitive use is unexpected, add a concise provider-specific
first-use disclosure/choice in the normal launch path. The existing Codex
local-mode prompt authorizes execution without its Linux sandbox; it is not a
substitute for data disclosure. This is a targeted conditional gap, not a claim
that every terminal command needs a new consent dialog.

**Form boundary.** Google's Data safety definition covers relevant off-device
third-party transfers; local-only processing is excluded. Optional collection
requires genuine user choice. A user-directed sharing exception is not a general
collection exception. The controlled-WebView and open-web cases also differ.
Classify actual supported flows, recipients, purposes and provider settings;
do not select all imaginable data types based on arbitrary user scripts, or
assume IP automatically means precise location/device ID. Do not assert universal
in-transit encryption from artifact-download HTTPS alone.
[Data safety guidance](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en).

The preview has JavaScript/DOM storage enabled, external top-level navigation
handoff, file/content access disabled, no added JavaScript interface in the
inspected pane, and Safe Browsing enabled. Page subresources may contact outside
hosts. The final manifest's `WebView.MetricsOptOut=true` disables usage statistics,
not all crash reports; platform settings and provider behavior remain relevant.
[WebView reporting documentation](https://developer.android.com/develop/ui/views/layout/webapps/webview-privacy).

Finalize the current flow matrix and account/deletion answers with the separate
privacy/provider review. Z8's local deletion and provider logout do not delete
cloud conversations, provider accounts or provider-held logs.

## 4. AI-generated-content applicability

**Official scope.** Google's guidance includes conversational AI when chatbot
interaction is central, and identifies limited-scope exclusions such as AI
improving an existing productivity feature. It does not expressly classify a
general-purpose terminal that launches separately installed official clients.
[AI policy scope guidance](https://support.google.com/googleplay/android-developer/answer/14094294?hl=en).

**Assessment.** Z8 supplies terminal/project tooling, not a model service,
shared account or response proxy. This supports the terminal/productivity
submission rationale. However, the catalog specifically installs/opens Codex
and Claude, the listing promotes those workflows, and generated output is
visible inside the app. Product naming or a statement that Z8 is “not AI” alone
cannot settle the classification. Do not invent a hosted AI feature or claim a
confirmed exemption; describe the actual optional client boundary in review
notes and answer Console questions accordingly.

**Conditional consequence.** If Google treats these workflows as an AI-generation
feature, its policy requires prevention of restricted/deceptive content and
in-app offensive-content reporting without leaving the app, with reports used
for moderation. Z8 currently has support email, not a verified in-app content
reporting/moderation workflow; an external email handoff is insufficient for
that specific requirement. A provider CLI's own feedback command must be
examined before claiming it satisfies developer reporting.
[AI-Generated Content policy](https://support.google.com/googleplay/android-developer/answer/13985936?hl=en).

The viable response is either substantiate the general-purpose terminal scope
in ordinary review, or implement a real reporting/moderation integration for
an in-scope feature and assess its privacy implications. A superficial report
button cannot by itself establish content safety. Provider contracts and their
own usage rules remain separate, as covered by the parallel review.

## Code and evidence boundary

Relevant files were read at the reviewed commit:

- `tools/prepare-app.py`: permissions, manifest/service type, WebView opt-out,
  exported-component restrictions and service lifetime patches.
- `runtime/guest/provision.sh`, `tool-manager.sh`, `install-node.py`,
  `install-ai.sh`, `codex-launch.py`: offline base, actual external native
  downloads, explicit updates, integrity checks and project-local consent.
- `Z8Guest.java`, `Z8RuntimeLauncher.java`, `Z8ToolManager.java`,
  `Z8PreparationNotification.java`: execution boundary, work ownership and stop.
- `Z8EnvironmentActivity.java`, `Z8SettingsActivity.java`, `Z8ToolUpdates.java`,
  `Z8ToolUpdateLifecycle.java`, `Z8AboutActivity.java`: visible controls, metadata
  traffic and disclosure placement.
- `Z8BrowserPane.java`, `Z8BrowserUrls.java`, `docs/privacy.html`,
  `docs/store/review-notes.txt`, and `docs/DISTRIBUTION_REVIEW.md`.

The published rc6 source and tag were independently verified. Existing private
`rc6-final` QA establishes final binary/notices identity and specific runtime
workflows, including one authenticated Codex task on the preceding rc6 build
followed by final-build version/login/file/test preservation and QA logout.
It does not establish a provider-wide telemetry inventory, all-device behavior,
AI-content safeguards, or Google Play approval. No new account/model request or
Console mutation was performed for this policy review.
