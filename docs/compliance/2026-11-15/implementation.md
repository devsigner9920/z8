# rc7 follow-up implementation

November 15, 2026. This follows the [rc6 review](README.md). The rc6 tag,
archives and QA remain unchanged. These changes use `0.1.0-rc7`, code 8,
with a separate corresponding-source URL and candidate-specific evidence.

## External-client choices

Tools now exposes provider terms, privacy/data controls and license information.
Codex LICENSE/NOTICE links use recognized version tags, with a labeled current-
repository fallback for unknown versions. Consumer and commercial/API terms are
separate choices. Install/update confirmation also explains possible download
and version-validation connections and diagnostics before sign-in.

App-created Codex and Claude sessions show a notice about prompts, source
context, command output, account information and diagnostics before accepting
the launch request. Cancel or dismiss does not start the client. Ordinary
terminals and other tools continue normally. Acknowledgment is local to the
project, recorded installation and notice revision. Unknown/custom installations
are not remembered. Availability, active tool work and installation changes are
checked again after a browser visit; deleted projects and stopped services cannot
reuse prepared launch requests.

Receipt/file metadata detect ordinary installation changes, not binary integrity
or a security boundary. Continue acknowledges Z8's information, not a provider
contract. It does not change telemetry settings, authentication choices or
official binaries. Codex local-execution consent remains separate. Manually typed
terminal commands are not universally intercepted by these app controls.
The [provider-data follow-up](follow-up-provider-data.md) records version-specific
diagnostic defaults, controls and evidence limits.

## Source delivery

The collector retains the exact Coroutines sources and build/resource inputs
identified in the audit, checking correspondence with source JARs and actual
binary resources. Rebuilding the missing probe from its preferred source with
a pinned compiler produced exactly the shipped 1,738 bytes and SHA-256
`158a19eb94aa2f3e2f459db69ee10276c73b945dd6c5f8fc223cf2d85e2b5e33`.
This is a successful probe reconstruction, not a full dependency/app
reproducibility claim. Kotlin evidence separately records source matches,
original build inputs and its precise release-version substitution.
See the [source procedure](../../RELEASE_LICENSES.md) for inputs and commands.

The [bounded Java reconstruction recipe](../../source-reconstruction-jars.md)
compiled all 788 retained Java sources for Guava, Commons IO and two CommonMark
libraries without their original completed JARs on the classpath. The four
outputs passed functional tests and resource/license preservation checks.
Compiler/target adaptations and synthetic-class differences are recorded;
this is not an identical-binary or full ABI-compatibility claim.

The Android builder and preparer accept exported `upstream/termux-app` without
reconstituting `.git`. They verify every upstream file against the source
manifest, reject changed/missing/extra files and symlinks, and restore recorded
executable modes on the generated copy. The ZIP's independent checksum is the
authenticity anchor. Users can edit Z8's overlay while retaining the baseline.
Native runtime reconstruction and repackaging keep their separate procedures.

## Privacy operations and remaining work

English/Korean web and offline notices reflect ordinary free Gmail, no automatic
forwarding and deletion of controlled support records 90 days after resolution.
The [procedure](support-retention.md) is manual; no mailbox action or automation
was performed. New launch-notice choices are stored locally. Google LLC's service
identity is established, but the consumer mailbox's actual overseas-processing
particulars and applicable legal basis remain unresolved. A US corporate address
or a generic policy link does not establish them.

Host checks and Android compilation validate the implementation; release evidence
must identify the tested APK/AAB. Neither successful collection nor a compiled
app alone attests full source closure. Finish the supported-provider/platform
Data safety classification, support-processing particulars, foreground-service
justification and applicable device/Console/signing checks before production.
Native-download policy application still requires ordinary Play review. This
follow-up does not create a model service or publish an installable app binary.
