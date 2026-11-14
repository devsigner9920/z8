# Follow-up: provider data controls and Gmail support

Reviewed November 15, 2026. Scope: the [published rc6](README.md), its pinned
Codex **0.160.0** / Claude Code **2.1.285**, and tested updates Codex **0.169.0** /
Claude Code **2.1.311**. This supplements [provider](provider-review.md) and
[privacy](privacy-review.md) reviews. It is not a completed Data safety form.
No account, credentials, mailbox, provider setting or runtime was changed;
no login, model request, vendor inquiry or payment was made for this follow-up.

## What is now established

- Z8's managed sessions set `DISABLE_AUTOUPDATER=1`; the rc6 launch/installer
  sources do **not** set provider telemetry opt-outs or edit Codex/Claude user
  configuration. A user's own configuration can differ.
- Exact Codex source confirms separate analytics, metrics and log/trace controls
  in both supported versions, including an important difference between them.
- Claude's current official documentation specifies account-dependent defaults
  and control side effects. The previous signed-binary/version tests establish
  the installed releases, not telemetry delivery or enforcement of every control.
- The operator confirms **ordinary free Gmail, with no automatic forwarding**.
  The service entity can be identified; actual mailbox processing countries
  and a complete Korean overseas-processing basis cannot be invented from that.

## Provider evidence matrix

“Source” means published source at the stated revision, not a reproduced binary
or captured production packet. “Documentation” means the current provider page;
where it describes newer features, it is not automatically proof about older
binaries. Z8's installed receipts and earlier QA confirm versions/integrity only.

| Flow | Default / timing evidence | Controls and remaining boundary |
| --- | --- | --- |
| Z8 version metadata | Off until daily-check opt-in or explicit Check now; fixed public endpoints, no account/project/content inventory | Its switch controls Z8's check, not the installed client's own connections. Download requests expose normal IP/request metadata. |
| Codex built-in usage/health metrics | Official documentation says enabled by default for ordinary CLI use. Both source versions select the built-in Statsig metrics exporter unless configured otherwise; log/trace exporters default to none | `analytics.enabled=false` disables OpenAI analytics. A generic statement that all telemetry defaults off confuses metrics with optional OTel logs/traces. |
| Codex configured OTel export | Logs and traces default off; a configured collector is separate | In 0.160.0 the analytics flag also gates metrics export; in 0.169.0 it gates only the built-in Statsig exporter. Set `otel.metrics_exporter="none"` separately to disable an explicit custom metrics exporter. |
| Codex product analytics / pre-login | Both versions' analytics-event sender returns without an available authentication context. A separate metrics pipeline exists, with startup instrumentation and its own gate | The authenticated-event guard does not prove no pre-login connections or startup metrics. No clean-profile network capture was performed here. Other client startup/update/service requests remain a bounded verification item. |
| Claude direct-provider metrics | Current docs describe default-on operational metrics for direct Anthropic API use; third-party-provider defaults differ | `DISABLE_TELEMETRY=1`; includes feature-flag effects. Do not apply a single account/provider default to all users. |
| Claude errors | Current docs limit default reporting to Pro/Max/Ultra sign-in, v2.1.198+, direct API, without ZDR/HIPAA; both reviewed versions meet only the version condition | `DISABLE_ERROR_REPORTING=1`. Account/rollout conditions and actual pre-login behavior remain unobserved. Do not report error uploading as established for the unauthenticated QA session. |
| Provider task content / feedback | Model use sends task context to the selected provider. User feedback can send additional conversation/code material | Diagnostic opt-outs do not make model use offline or remove account-specific retention/training rules. Distinguish explicit feedback, default diagnostics and normal task processing. |

### Codex: exact source and safe controls

Official tags resolved to these commits during the review:

- `rust-v0.160.0` → `a956835d020762cb2b570053af06f643a11c0ecc`.
- `rust-v0.169.0` → `d32063f96c2dff1dc96af839b3952abb6acfeda4`.

The versioned configuration resolvers select no log/trace exporter and Statsig
metrics by default: [0.160.0](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/core/src/config/otel.rs),
[0.169.0](https://github.com/openai/codex/blob/d32063f96c2dff1dc96af839b3952abb6acfeda4/codex-rs/core/src/config/otel.rs).
The analytics/metrics gating difference is explicit in
[0.160.0 initialization](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/core/src/otel_init.rs) versus
[0.169.0 initialization](https://github.com/openai/codex/blob/d32063f96c2dff1dc96af839b3952abb6acfeda4/codex-rs/core/src/otel_init.rs).
The [0.169.0 built-in exporter](https://github.com/openai/codex/blob/d32063f96c2dff1dc96af839b3952abb6acfeda4/codex-rs/otel/src/config.rs)
uses `https://ab.chatgpt.com/otlp/v1/metrics`; its debug-build suppression is not
a release-build privacy guarantee. The authentication guard is present in the
[0.160.0](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/analytics/src/client.rs) and
[0.169.0](https://github.com/openai/codex/blob/d32063f96c2dff1dc96af839b3952abb6acfeda4/codex-rs/analytics/src/client.rs)
product-event senders. These are distinct paths.

[Official configuration guidance](https://learn.chatgpt.com/docs/config-file/config-advanced#metrics)
describes usage/health metrics separately from OTel and permits disabling
feedback uploads. Inform users how to merge chosen settings into their existing
`~/.codex/config.toml`; do not replace that file or silently add duplicate tables:

```toml
[analytics]
enabled = false

[otel]
exporter = "none"
trace_exporter = "none"
metrics_exporter = "none"
```

`[feedback] enabled=false` is a separate optional choice, not a prerequisite for
using Z8. These controls do not disable necessary model/authentication traffic,
user tools, or all optional client features. Do not promise that provider terms
or model-training preferences are changed by them.

Implementation caution: rc6's compatibility adapter deliberately passes through
explicit Codex configuration arguments. Adding `-c ...` to its launch command
without reviewing that adapter changes which local-mode path runs. Prefer
informational instructions now; any later Z8 control needs explicit scope,
existing-config preservation and exact-version tests. Do not change sandbox,
authentication or safety settings to implement a diagnostics preference.

### Claude: documented scope, not a packet audit

[Anthropic's data-usage page](https://code.claude.com/docs/en/data-usage)
describes metrics as excluding code/prompts/file paths, and error reports as
redacted internal errors/stacks sent over TLS. It describes account-specific
training/retention and explicit feedback separately. That does not establish
Google's “no collection” category or prove every payload of the tested binaries.

The [environment reference](https://code.claude.com/docs/en/env-vars) documents
`DISABLE_TELEMETRY=1` and `DISABLE_ERROR_REPORTING=1`. For these variables,
`0` or `false` also disables reporting: **unset** them to restore the default.
`DISABLE_TELEMETRY` also affects feature-flag fetching and related functionality.
The broader `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` changes more features,
including feedback, release notes and some checks; it is not an offline mode.
Keep it a separately explained choice rather than silently forcing it globally.
Current docs introduce some other controls after 2.1.311; do not backport their
names or assume their availability from the latest page alone.

The [network documentation](https://code.claude.com/docs/en/network-config)
identifies startup connectivity checks, authentication endpoints, optional
telemetry hosts and conditional startup release-note requests. These establish
why “no network before a model prompt” is unsafe wording; they do not establish
which requests occurred during our earlier first-run QA. Model, authentication,
MCP/plugin and user-command traffic is outside a telemetry opt-out's guarantee.
Keep provider safety checks enabled; do not disable WebFetch protection merely
to reduce the apparent network inventory.

## Concrete UX work supported by this evidence

Before an app-driven first launch, show the provider name and this bounded
message, with Cancel and Continue plus Terms and Privacy/data-control links:

> Using this optional client can send your prompts, source context, command
> output, account information and diagnostics directly to its provider,
> depending on your account, version and settings. Accounts and any charges
> are separate. Z8 does not operate the model service. You can keep using the
> terminal without this client.

The CLI may choose source context; do not say only manually selected files are
transmitted. State that Continue acknowledges the Z8 notice, not that it accepts
provider contracts. Keep all official authentication options. A notice revision
and known installed version can scope acknowledgment; changes require renewed
notice. Unknown/custom installations should not inherit an old verified-version
claim. Manually typed terminal commands cannot universally be intercepted.

Make the same information accessible before install and later in Tools. Keep
Codex's pinned LICENSE/NOTICE accessible there. Link
[Codex data controls](https://learn.chatgpt.com/docs/config-file/config-advanced#metrics),
[Claude data usage](https://code.claude.com/docs/en/data-usage) and the applicable
provider terms/privacy pages. This is a disclosure improvement, not proof that
every default data flow has been measured. A future optional diagnostics switch
must explain its scope and side effects, preserve user settings and be tested
against each managed version. No such switch is claimed for rc6.

## Gmail: established facts and remaining evidence

Final update: [support and Data safety assessment](support-and-data-safety-final.md)
records a bounded legitimate-interest basis for ordinary support collection/use
and concrete draft form answers. Country particulars for the actual consumer
mailbox remain unestablished; that issue is not solved by a user guessing a
country or accepting a generic checkbox.

The user confirms ordinary **free Gmail** and **no automatic forwarding** for
`ethsy2462@gmail.com`. Do not invent Workspace enrollment, a signed processor
addendum, a selected data region, a third-party forwarding destination, or a
mailbox country based on the address. The no-forwarding fact does not establish
all access/delegation/client settings; none were inspected.

[Korean consumer terms](https://policies.google.com/terms?hl=ko&gl=kr) identify
**Google LLC**, 1600 Amphitheatre Parkway, Mountain View, California 94043, USA.
The [Korean Google privacy policy](https://policies.google.com/privacy?hl=ko)
includes received email content and worldwide processing and supplies the
privacy contact `googlekrsupport@google.com`. The entity's US address is **not**
evidence that the mailbox is processed only in the United States.

Google's [data-region coverage](https://knowledge.workspace.google.com/admin/compliance/data-covered-by-data-regions)
is limited to specified Workspace editions/data/states and does not establish
region controls for this ordinary free mailbox. Even a supported edition's
at-rest option is not universal regional processing of logs, caches and support
access. The [Cloud Data Processing Addendum](https://cloud.google.com/terms/data-processing-addendum/)
applies through its covered customer agreement; reading its public page does
not make it the operator's consumer Gmail contract.

### What can truthfully be documented now

| Item | Established information |
| --- | --- |
| Service/recipient | Google LLC's Gmail service; Korean terms/address and public privacy contact above |
| Operator purpose | Receiving, storing and answering support requests |
| Data | Sender email address, message, voluntary attachments and replies; minimize any additionally supplied personal information |
| Timing/method | Email delivery and reply over network services, with continuing mailbox storage; no automatic forwarding |
| Operator retention | Handling plus 90 days after resolution, then manual permanent deletion of controlled mail/working copies; earlier requests handled through the support contact |
| Provider retention | Separate Google deletion/backup procedures; not a promise that all provider copies disappear at the operator's deadline |
| Country scope / transfer basis | The distinct Article 28-8 country/route evidence remains unestablished for this actual mailbox; do not fill “US only” or an inferred global data-center list. The limited Article 15 collection/use basis is recorded in the final assessment. |

This table can support accurate privacy text, but it is **not a completed
statutory overseas-transfer notice**. The existing [support procedure](support-retention.md)
remains manual; no mailbox purge or automation was performed.

### Bounded route to close the remaining issue

[PIPA Article 28-8(1)](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1029334743)
provides several routes, including separate consent and necessary contractual
outsourcing/storage with notice. The latter requires a real necessity/basis;
free app support alone does not prove it. The
[required particulars](https://law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1033215841)
include data, destination countries, timing/method, recipient/contact,
purpose/period and refusal method/effect. A generic checkbox cannot cure
unidentified mandatory particulars.

The [PIPC explanation](https://pipc.go.kr/np/default/page.do?mCode=D060040000)
distinguishes a foreign provider's direct collection from an operator's overseas
provision/outsourcing/storage. Do not assume this removes the operator's mailbox
obligations merely because the user sends mail directly to Gmail. Conversely,
do not automatically call every user's own CLI-provider relationship a Z8
operator-to-processor transfer.

1. **Completed in the final assessment:** record the purpose/necessity/balancing
   analysis supporting Article 15(1)(6) for minimal requested support; identify
   the operator's privacy/support contact. No private registration data or
   fictional separate department is published.
2. Complete the applicable Gmail country/overseas-route evidence from
   evidence that actually applies to this service, if available. No vendor
   inquiry is required by this review, and none was sent. Until established,
   keep the unresolved fields visible in the internal checklist rather than
   claiming the Google policy link completed them.
3. This review does not mandate purchasing or migrating to another provider.
   The user has excluded new inquiries, purchases and migration from the
   current work. Public evidence did not establish this consumer service's
   actual country scope, so do not claim complete overseas-storage compliance.
   Any later alternative must be assessed on its own facts before adoption;
   do not move or forward existing messages automatically.
4. Meanwhile minimize support intake: do not request passwords, tokens, full
   private repositories or unnecessary sensitive attachments. Offer redacted
   examples. This reduces exposure; it does not replace the remaining
   overseas-route evidence or make public issue posting a suitable private-
   support substitute.

No all-country launch clearance follows from these changes. The final
assessment closes the generic support collection/use basis and turns the
supported-provider evidence into specific draft choices. The remaining Gmail
country/overseas-route issue is finite; a universal traffic inventory of every
hypothetical terminal program is not required to complete this review.
