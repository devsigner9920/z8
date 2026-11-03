# Distribution review

Review date: **2026-11-04**. This records the remaining distribution questions for
Z8, a **free local terminal host for official CLIs**, with no advertising or
in-app purchases. Z8 does not operate an AI service, proxy model requests,
provide shared accounts, or resell provider usage. Users install optional CLIs
and sign in through those tools with their own accounts.

The source publication and local binary candidates are **not a Play-approved release**.
Technical tests and generated license reports do not constitute store approval
or settle contracts. The maintainer already confirmed rights to the Z8 logo and
Prism artwork on 2026-11-02; that question is not being reopened. See
[license scope](../LICENSES/README.md) and [release status](RELEASE_STATUS.md).

## Exact reviewed version and work in progress

| Item | Reviewed identity |
| --- | --- |
| Source HEAD | `be0a82c8ddc33a44c7f4bda77a8d369db75949a9` |
| Android package | `dev.devsigner.z8` |
| Candidate | `0.1.0-rc2`, version code `3` |
| APK SHA-256 | `135e2713dacb6c97b42c2c39f3a23e7a04eea99ac89d05bd02ff45ecbce42054` |
| Bundled guest | Ubuntu Base `24.04.5`, ARM64, normalization version `1` |
| Guest ZIP SHA-256 | `38463da28ca71e6be8ef36c0ff0f5a4da558eee3577cfd7b30e14c0ce6d4ef54` |

The APK contains the normalized guest and installer scripts/metadata. Inspection
of APK and nested guest paths found no `codex`, `claude`, or
`codex-code-mode-host` executable. The optional installer downloads Codex
`0.160.0` and Claude Code `2.1.285` from their official distribution endpoints.

The follow-up sources are configured as `0.1.0-rc3`, version code `4`. They add
dated notices to modified upstream files, collect exact runtime Maven sources and
preserve 19 historical guest source files. The retained-input reconstruction
reproduced the historical guest ZIP and manifest hashes exactly. Maven source
JAR collection and version-matched upstream archives still require a review of
resource/build-script completeness; unresolved records must remain visible.

These changes are not represented by the reviewed rc2 APK hash above. Each new
candidate needs its own source/notices integrity checks and relevant validation.
Follow the [release licensing procedure](RELEASE_LICENSES.md); an older report
must not be reused as clearance for a changed build.

Detailed observations are a private internal verification record:
`reports/compliance/2026-11-04/policy-audit/audit.json`.

## Decisions that remain

**Google Play execution policy.** Google's
[Device and Network Abuse policy](https://support.google.com/googleplay/android-developer/answer/16559646?hl=en)
restricts executable downloads outside Play and includes a VM/interpreter
exception. Z8's post-install downloads include native Linux packages and ELF
CLIs. [PRoot](https://proot-me.github.io/) translates system calls using `ptrace`;
this same-architecture configuration is not a separate-kernel VM. A Python
downloader does not make its native payload interpreted code. The official
policy does not explicitly resolve this particular execution model. This is a
material Play review risk, not a finding that all terminal apps are prohibited.
The concrete question is whether these disclosed flows qualify for the stated
exception. User consent, hashes, successful execution tests, or removing only a
CLI installation shortcut do not answer it.

**Ubuntu distribution basis.** The
[Canonical IPR policy](https://canonical.com/legal/intellectual-property-policy)
(page dated 2015-07-15, checked 2026-11-04) distinguishes unmodified redistribution
from modified distributions and addresses trademarks/recompilation. It also
expressly preserves rights under individual component licenses. Z8's
[guest preparer](../tools/prepare-guest.py) changes `bash.bashrc`, adds managed
files, normalizes archive metadata and repackages the image; Ubuntu identity
remains. It is not an unchanged mirror. Identify any existing Canonical
arrangement covering this image, or document a defensible distribution and
trademark basis. A complete component-source package alone does not settle this
question. Do not remove attribution or declare all component rights invalid.

**Claude Code operator terms.** Current
[Claude Code legal documentation](https://code.claude.com/docs/en/legal-and-compliance)
expressly covers products that preinstall **or run** Claude Code. Its standard
route requires [Commercial Terms](https://www.anthropic.com/legal/commercial-terms),
an unmodified binary with authentication methods intact, and users who
authenticate and pay directly. It also permits users to sign into the unmodified
CLI with their own Claude subscriptions. Identify the legal person operating Z8
and its applicable terms basis. Non-bundling alone does not establish that
basis. This does not imply that Z8 is an AI service, that subscription login must
be replaced with an API gateway, or that every deployment needs a separately
negotiated agreement. Plain-text compatibility descriptions must not imply
provider endorsement.

One concrete tooling improvement is available without changing the product:
verify Claude's exact release-manifest signature and signing-key fingerprint
when updating the pins. The current recipe verifies pinned HTTPS manifest and
binary hashes but records that detached-signature verification was not done.
[Claude setup documentation](https://code.claude.com/docs/en/setup) describes that
verification. Keep the distinction between installer pins and subsequent
vendor/user updates, and do not claim official Android support from Linux ARM64
compatibility tests.

## Google Play technical inquiry — DRAFT, NOT SENT

**No external transmission is authorized by this document or the review request.**
An operator must choose whether and where to send this draft. It is a factual
inquiry, not evidence of acceptance.

Subject: Device and Network Abuse exception — local ARM64 PRoot terminal

We are preparing Z8 (`dev.devsigner.z8`), a free Android terminal with no ads or
in-app purchases. It targets API 36 and runs under the ordinary app UID without
root. The APK supplies the Android host runtime, PRoot and its native guest
loader, plus a Linux root filesystem. The proposed Play distribution would use
Play for application updates.

After user-initiated setup, the local environment downloads Linux packages using
apt. Users may also explicitly install unmodified official Codex and Claude Code
CLIs directly from their publishers and authenticate with their own accounts.
These downloads include native ARM64 executables and shared libraries. They run
under PRoot's ELF loader and syscall translation against the Android kernel;
this is not QEMU CPU emulation or a separate-kernel VM. The environment shares
the app UID and is not represented as a security boundary between projects.

Does this execution model qualify for the VM/interpreter exception in the
Device and Network Abuse policy? If it does not, which of these native-code
delivery/execution paths must change for a Play-distributed version? We can
provide the architecture, exact artifact identities and a demonstration of
installation, execution, permissions and termination. We are seeking guidance
on the disclosed behavior, not treating technical compatibility as approval.

## Canonical redistribution inquiry — DRAFT, NOT SENT

**No external transmission is authorized.** No Canonical approval or agreement
is asserted by this draft.

Subject: Normalized Ubuntu Base image inside an Android terminal application

We are preparing Z8, a free Android terminal application with no ads or in-app
purchases. It currently includes Ubuntu Base 24.04.5 ARM64 from the
[official archive](https://cdimage.ubuntu.com/ubuntu-base/releases/24.04/release/ubuntu-base-24.04.5-base-arm64.tar.gz)
for local execution under PRoot, without a guest kernel.

Our packaging retains upstream program bytes and component notices but strips
special permission bits, materializes hard links, records symlinks for safe
installation, modifies `etc/bash.bashrc`, and adds Z8 startup/install scripts.
The result is delivered as a normalized ZIP inside the APK. Ubuntu identification
remains in `usr/lib/os-release`. The application is called Z8; we do not claim
Canonical certification or endorsement. We are separately preparing the notices
and corresponding source required by the component licenses.

Under sections 2–4 of your IPR policy, what permission or agreement, if any, is
required for this exact modified-image distribution? Please distinguish the
aggregate/trademark conditions from rights under individual component licenses.
If this packaging requires a different arrangement, would distributing the
unaltered official Base archive and applying our changes only on the user's
device meet the unmodified-redistribution route? We can provide the precise
normalization recipe and archive identities for your assessment.
