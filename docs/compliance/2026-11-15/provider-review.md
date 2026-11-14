# Provider review: Codex and Claude Code in Z8 rc6

Later work: [rc7 implementation](implementation.md) adds the recommended app
disclosures and links; [provider-data evidence](follow-up-provider-data.md)
examines version-specific diagnostic controls. The original rc6 assessment below
retains its artifact scope.

Reviewed November 15, 2026 (Asia/Seoul). This is a source, artifact and current
provider-document review for the local-terminal product, not a provider approval
or a completed Google Play declaration. No provider inquiry, account change,
payment or model request was made during this review.

## Reviewed release and conclusion

- Source commit: `131ce7f3d83b6671121f1f0dedbcbda439f92905`.
- Version: `0.1.0-rc6`, code `7`.
- APK SHA-256: `bed7761c4777ffb31f3009ef58e8a074b79b97d0fe4e77730f06c6f233ea31d7`.
- AAB SHA-256: `4d426219d125bc7f380223e3295c157676e631b3a835a78af6944781a8b5eabd`.
- The local test APK is development-signed; the AAB is unsigned. This review
  does not change `uploadReady: false`.

**The reviewed provider documents support a route for Z8 to help users install
and run the official clients locally with their own accounts.** This conclusion
depends on the boundaries below. It is not a right to supply shared subscriptions,
resell model access, use provider branding as Z8 branding, or relicense external
clients under GPL. The review found no stated requirement for a separate vendor
preapproval for this exact terminal-only arrangement beyond the applicable
standard terms and their conditions.

The concrete improvements are clearer links to provider terms/privacy before
installation, accessible Codex license/notice information, and version-specific
telemetry evidence before final Data safety answers. These are distinguished
below from an established license breach: the evidence does not establish that
the current direct-download arrangement is prohibited.

## Actual implementation boundary

The following was checked against the pinned source, not inferred from the app
description:

| Path | Observed behavior |
| --- | --- |
| `runtime/guest/install-ai.sh` and `ai-tools.lock.json` | Explicit install downloads from official GitHub/OpenAI release URLs or `downloads.claude.ai`. Baselines are Codex 0.160.0 and Claude Code 2.1.285. Manual updates select an exact version; they do not change trust keys automatically. |
| Installer integrity | Codex package contents are checked and retained. Claude's official signed manifest is verified using `gpgv`, the pinned key hash and fingerprint, then the binary's checksum/size is checked. Files are installed unchanged and exposed through a managed symlink. Existing custom/modified installations are preserved. |
| APK and nested `assets/z8/guest/rootfs.zip` | Direct inspection found no executable named `codex`, `claude` or `codex-code-mode-host`; the app carries installer/launcher scripts and metadata. This targeted inspection is consistent with the release inventory, not a claim that filename inspection alone can identify arbitrary renamed software. |
| `Z8EnvironmentActivity`, `Z8ToolCatalog`, `Z8ToolManager` | Tool download requires a project-specific confirmation. The screen identifies the external official client and separate account/terms requirements. |
| `guest-task.sh`, `cli-profile.sh`, `codex-launch.py` | Claude runs as `command claude`. Codex uses a separate compatibility launcher; neither path supplies provider credentials or a Z8 inference endpoint. |
| `Z8BrowserBridge`, `Z8BrowserPane`, `browser-open.py` | Live terminal browser requests use an authenticated local transport. External sign-in pages open in browser-owned Custom Tabs, not the app's preview WebView. Auth URLs are ephemeral; tab labels use the host. No provider OAuth token exchange or provider-credential collector was found in these app paths. |
| `Z8Guest.java:579` | Managed project launches set `DISABLE_AUTOUPDATER=1`. This is not an authentication restriction. Users can still change their environment or run their own update commands. |
| `Z8ToolUpdates` | Daily public-version checks default off; Check now is explicit. Requests fetch fixed public endpoints and do not attach project contents, credentials or installed-tool inventories. |

Source: [the reviewed tree](https://github.com/devsigner9920/z8/tree/131ce7f3d83b6671121f1f0dedbcbda439f92905).
The private final QA record separately verifies the installed APK hash, Claude
2.1.285 → 2.1.311 update and official signature, and direct notification return.
Those tests establish installation/integrity behavior, not Claude account access
or an authenticated model workflow. No private account evidence is published here.

## OpenAI Codex

The pinned repository [LICENSE](https://github.com/openai/codex/blob/rust-v0.160.0/LICENSE)
is Apache-2.0; [NOTICE](https://github.com/openai/codex/blob/rust-v0.160.0/NOTICE)
contains OpenAI and Ratatui attribution. Apache-2.0 permits source/object
redistribution subject to its license, attribution, modification-notice and
applicable NOTICE conditions; it does not grant general trademark rights.
The repository's current LICENSE was also checked and is Apache-2.0.
Do not treat this as a blanket license for every bundled third-party component:
the installed release package includes separate voice-component notices and
licenses, which Z8's member-preserving installer retains.

[OpenAI's Terms of Use](https://openai.com/policies/terms-of-use/) separately
govern service access, prohibit account sharing and circumvention of service
limits/protective measures, and recognize separate open-source licenses.
The [Services Agreement](https://openai.com/policies/services-agreement/) governs
API/business use and separately restricts credential sharing and resale.
Consequently, a software license does not give Z8 users free model usage or the
operator's account entitlement.

Official [Codex authentication documentation](https://learn.chatgpt.com/docs/auth)
supports personal ChatGPT sign-in and API-key sign-in for local CLI work, with
different billing and data policies. Z8 preserves these flows. The analysis is
ordinary use of the official client, not a claim that Z8 has implemented or been
registered for a separate Sign in with ChatGPT integration. A future app-level
chat UI, token broker or inference proxy requires a new review.

### Codex local mode is a scoped security choice

The launcher asks for affirmative consent, stores that choice for the selected
project, provides a reset command, and displays the active mode. Only eligible
interactive invocations receive `--no-daemon --sandbox danger-full-access`.
Noninteractive execution, authentication subcommands, unknown options and
explicit policy selections pass through without silently adding that mode.
It does not change the user's approval-policy configuration or provider binary.

Official [sandbox guidance](https://learn.chatgpt.com/docs/agent-approvals-security)
documents this mode but warns that it removes the sandbox boundary. Thus this
is **not a global bypass**, nor evidence of bypassing provider account limits.
It remains a material local security tradeoff: project consent scopes the saved
choice, not an enforceable isolation boundary between Z8 projects. Existing UI
disclosure correctly warns that file/shell/network work may occur without
further prompts and other Z8 projects are not guaranteed protection. Preserve
that warning; never describe PRoot as an equivalent replacement security sandbox.

## Anthropic Claude Code

The [Claude Code repository license](https://github.com/anthropics/claude-code/blob/main/LICENSE.md)
is proprietary and references Anthropic's Commercial Terms; it is not covered
by Z8's GPL license.

The current [Claude Code legal page](https://code.claude.com/docs/en/legal-and-compliance)
expressly covers products that preinstall **or run** Claude Code. Its standard
route requires operator Commercial Terms, the unmodified published binary with
all built-in authentication methods available, and direct end-user
authentication/billing. It permits accurate plain-text statements that a product
runs Claude Code. It separately forbids offering Claude.ai login as the host
app's own authentication or routing consumer-subscription requests on users'
behalf. **Inference:** Z8's official-client terminal flow fits the former pattern;
non-bundling alone would not satisfy these conditions. The code review found no
forced API-only login, Z8-funded account or inference intermediary.

The private operator-assent record confirms electronic Commercial Terms assent
on November 14 through the standard Platform flow. The recorded
[terms version](https://www.anthropic.com/legal/archive/af81645b-040b-485c-a4a0-3205ccfb3792)
and [current Commercial Terms](https://www.anthropic.com/legal/commercial-terms)
both display June 17, 2025. This establishes the previously missing operator
action, not endorsement, a negotiated exception, or rights for every end user.
Ongoing conditions, usage/region policies and any applicable supplemental terms
remain relevant. The operator's identity and account details are intentionally
excluded from this public record.

The user's account remains separate. [Claude authentication](https://code.claude.com/docs/en/authentication)
documents subscription, Console and supported cloud-provider choices.
[Consumer Terms](https://www.anthropic.com/legal/consumer-terms) impose their own
eligibility, including age and no account sharing; API/organizational use has
its applicable commercial agreement. Do not promise that every free account,
country, device or subscription has the required access. A general development
terminal's availability does not override those provider-specific conditions.

## Trademarks and product presentation

The store title, app icon and feature graphic use Z8's own branding. The store
description says the app is not an official OpenAI or Anthropic product. Catalog
labels identify the external clients rather than naming a Z8-branded feature
after them; that is the descriptive-use interpretation used here.

[OpenAI brand guidelines](https://openai.com/brand/) prohibit misleading
endorsement and incorporating provider branding into the app's own identity.
[Anthropic trademark guidelines](https://www.anthropic.com/legal/trademark-guidelines)
are restrictive for other mark/logo uses. Keep the specific plain-text
compatibility permission from Claude's legal page separate from permission for
logos or co-branding. The review does not authorize a provider logo, a
“Claude-powered” Z8 brand, or claims of official Android support.

## Data, telemetry and update behavior

Running the process locally does not keep model work offline. The current Z8
privacy text accurately separates Z8-operated analytics from external clients,
browser/platform reporting, download requests and provider processing.

[Codex configuration documentation](https://learn.chatgpt.com/docs/config-file/config-advanced)
describes built-in usage/health metrics and an `analytics.enabled` control,
separate from opt-in OpenTelemetry export. [Claude data-usage documentation](https://code.claude.com/docs/en/data-usage)
describes network model requests, operational telemetry, error reporting and
feedback/transcript sharing, with behavior varying by account, version and
settings. Consumer training choices and commercial handling also differ.
Z8 does not configure these telemetry controls globally; its own “no analytics”
statement must continue to mean **no Z8-operated analytics**.

The [Claude setup documentation](https://code.claude.com/docs/en/setup#disable-auto-updates)
documents `DISABLE_AUTOUPDATER=1`, while preserving manual update commands.
Z8 already sets it for managed launches, so no missing auto-update suppression
was established. A user-modified shell or independently installed tool can
behave differently; do not extend the app's update guarantee to arbitrary tools.

Current provider documentation is not a packet-level audit of every supported
binary. The earlier version/signature checks do not prove which diagnostics are
sent before or after sign-in. Final Play Data safety classification must use the
supported flows and actual version/settings evidence; “optional download” is
not a blanket reason to omit third-party data transmission.

## Concrete changes and release decisions

| Priority | Recommended action | Reason and acceptance evidence |
| --- | --- | --- |
| Before final disclosure sign-off | Add browser links to each provider's terms and privacy/data documentation beside the installer notice. State that accounts, charges and provider data handling are separate. | `Z8EnvironmentActivity.java:254` currently gives a generic notice without these links. Let users inspect terms before downloading; retain the provider's own onboarding rather than pretending a Z8 checkbox accepts every provider agreement. |
| Before final disclosure sign-off | Add a short external-client telemetry explanation and official controls to the privacy/help page; verify representative supported-client traffic/settings using a clean test profile. | Existing text is broadly accurate, but neither installation QA nor source review supplies a complete telemetry inventory. Record observed types and limits; do not claim all diagnostic traffic is disabled. |
| License hygiene | Make pinned Codex LICENSE/NOTICE accessible from the optional-client help/install record, preserving upstream component notices. | The configured official package has no top-level LICENSE/NOTICE members although component notices are retained. A link/copy improves attribution access. This is not a finding that direct upstream downloading is already unauthorized. Any future Z8 mirror, bundled CLI or modified distribution requires a full artifact-specific redistribution review. |
| Preserve as release invariants | Unchanged Claude binary; all official auth methods; own end-user accounts; no resale/proxy; neutral branding; explicit scoped Codex local-mode consent; no silent provider-policy change. | Add regression checks only when these paths change. Operator assent does not replace these technical conditions. |
| Keep factual marketing | Describe a local development terminal; external tools have separate accounts, network behavior, licenses and compatibility limits. | Current English description already follows this direction. Do not describe the whole optional-tool collection as GPL, universally supported or provider-approved. |

No runtime, account or store setting was changed by this review. These findings
supplement the historical distribution review; they do not rewrite older
artifact evidence or turn a published source prerelease into an approved app.
