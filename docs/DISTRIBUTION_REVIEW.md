# Distribution review

Current review: [November 15, 2026 policy and license assessment](compliance/2026-11-15/README.md).
This document retains the **November 14** distribution evidence and unsent
historical inquiry drafts. The linked assessment addresses the published rc6
release; historical rc3/rc4 findings below are not final-rc6 QA or legal clearance.

This records the distribution evidence and remaining decisions for
Z8, a **free local terminal host for official CLIs**, with no advertising or
in-app purchases. Z8 does not operate an AI service, proxy model requests,
provide shared accounts, or resell provider usage. Users install optional CLIs
and sign in through those tools with their own accounts.

The source publication and local binary candidates are **not a Play-approved release**.
Technical tests and generated license reports do not constitute store approval
or settle contracts. The maintainer already confirmed rights to the Z8 logo and
Prism artwork on 2026-11-02; that question is not being reopened. See
[license scope](../LICENSES/README.md) and [release status](RELEASE_STATUS.md).

The immutable rc6 tag points to `131ce7f3d83b6671121f1f0dedbcbda439f92905`.
All 16 public source/store assets were verified by anonymous downloads; none
is an installable APK or AAB. The exact candidate identities and scoped tests
are in [release status](RELEASE_STATUS.md#published-rc6-source-and-exact-candidate-evidence).
The current [license review](compliance/2026-11-15/license-review.md) identifies
the concrete coroutines gap and finite reconstruction work, rather than
classifying all 23 unsupplemented JAR collections as missing source. The
[provider review](compliance/2026-11-15/provider-review.md) distinguishes
recorded operator assent, unchanged official clients and individual user rights.
Post-release privacy/retention documentation does not modify the tag, source
archive or earlier binary evidence.

## Current Debian delivery decision

The maintainer explicitly selected a fresh Debian base for new installations
on November 14. The current image lock uses Debian 13.7 ARM64 from the official
[Debian Docker build artifacts](https://docker.debian.net/), pinned to artifact
commit `3b26c3995c7fae47d95ba678632a3520e97054f7` and source-layer SHA-256
`23b69c48ce5c2a6fb0681d959fa700427ad2a7cf7e6be5d25249170a1853d7ad`.
The image is normalized for Z8 and carries separately licensed packages; the
artifact repository's license does not replace those package licenses.
Current package source collection is distribution-aware and must match this
image's exact package versions and retained source indexes.

The rc5 and rc6 candidates replace the bundled Ubuntu image rather than renaming it.
Existing Ubuntu projects and prepared bases on upgraded installations remain
intact. New projects on those installations can continue using their existing
base; the app does not silently convert or delete environments. Fresh installs
prepare Debian. Keep emulator fresh-install evidence separate from physical
upgrade tests that retain an Ubuntu environment.

Z8 identifies the environment truthfully and uses its own product name and
artwork. Debian's registered trademark belongs to Software in the Public
Interest, Inc. Z8 has no affiliation with or endorsement from the Debian
project. This follows the factual-reference route in the
[Debian trademark policy](https://www.debian.org/trademark), while preserving
package copyright notices and source obligations. This removes the modified
Ubuntu image from the new distributed binary; it does not erase historical
Ubuntu obligations or constitute universal legal clearance.

## Historical rc3 reviewed version

The historical runtime findings below concern the retained **rc3** candidate.
The subsequent rc4 submission-preparation work adds first-run disclosure links,
updates operator attribution, and prepares store assets. The November 14
follow-up below also records a current, evidence-based Play submission route;
it is not a store approval or a contractual attestation. Each changed artifact
requires its own integrity and QA evidence. See
[current release status](RELEASE_STATUS.md).

| Item | Reviewed identity |
| --- | --- |
| Reviewed source revision | `9f90cd9dfddbeb3eede73df185470b1e4b134967` |
| Android package | `dev.devsigner.z8` |
| Candidate | `0.1.0-rc3`, version code `4` |
| AAB SHA-256 | `d865a7b27211f3f7f485f7e60f5d1250b4dc963570937a56291690ae7a8d283c` |
| APK SHA-256 | `fc01569149d879bc8fa0c2dd41ec995497bd9439a974b6f16f58b470d64c9625` |
| Bundled guest | Ubuntu Base `24.04.5`, ARM64, normalization version `1` |
| Guest ZIP SHA-256 | `38463da28ca71e6be8ef36c0ff0f5a4da558eee3577cfd7b30e14c0ce6d4ef54` |

The APK contains the normalized guest and installer scripts/metadata. Inspection
of APK and nested guest paths found no `codex`, `claude`, or
`codex-code-mode-host` executable. The optional installer downloads Codex
`0.160.0` and Claude Code `2.1.285` from their official distribution endpoints.

The published rc3 sources add
dated notices to modified upstream files, collect exact runtime Maven sources and
preserve 19 historical guest source files. The retained-input reconstruction
reproduced the historical guest ZIP and manifest hashes exactly. Maven source
JAR collection and version-matched upstream archives still require a review of
resource/build-script completeness; unresolved records must remain visible.

The November 14 follow-up left these retained binaries and their published
source archive unchanged. It updated the review basis and added signature
verification for the subsequent rc5/rc6 installers. Each new candidate needs
its own source/notices integrity checks and relevant validation.
Follow the [release licensing procedure](RELEASE_LICENSES.md); an older report
must not be reused as clearance for a changed build.

Detailed observations and ready-to-copy inquiry text are private internal
records under `reports/compliance/2026-11-14/distribution/`. The maintainer reported
completion of the previous practical-testing item on November 14. This is an
operator statement, not a new automated or independently witnessed device run;
the exact build and detailed results still belong in the release QA record.

## Outcome and next action

| Topic | Evidence established | Remaining action |
| --- | --- | --- |
| Product scope | Local development terminal; official user-authenticated CLIs; no model proxy, shared account, ads or IAP | Preserve this description in the listing and review notes |
| Play executable downloads | Native downloads and PRoot architecture are disclosed; current Play Termux provides a relevant implementation comparator | Use the reasoned submission basis below for ordinary Play review; do not claim a confirmed exception or require a separate inquiry |
| Guest distribution | Current source selects a fresh Debian image; exact source inventories and scoped setup/preservation tests exist; historical Ubuntu images and existing user environments are separately retained | Preserve version-specific evidence and finish the stated final-device coverage; do not transfer rc4 QA automatically |
| Claude Code | Operator assent through Anthropic's standard Commercial Terms flow was recorded on November 14; final rc6 installation/update checks verified the signed manifest and unchanged binary | Preserve the technical conditions and terms evidence; this is not provider endorsement or an authenticated-workflow compatibility result |

The maintainer requested registration and release preparation instead of sending
inquiries; the prepared inquiries remain **unsent**. Resolve the distribution
questions from applicable evidence while preserving the local-terminal behavior. Removing an
install button, renaming native binaries or describing PRoot as a VM would not
change the underlying facts. Do not mark release-policy decisions complete
merely because this document or an inquiry exists. A vendor inquiry is an
evidence route, not a universally required advance-approval procedure.

## Current submission basis and remaining decisions

**Google Play execution policy.** Google's
[Device and Network Abuse policy](https://support.google.com/googleplay/android-developer/answer/16559646?hl=en)
restricts executable downloads outside Play and includes a VM/interpreter
exception. Z8's post-install downloads include native Linux packages and ELF
CLIs. [PRoot](https://proot-me.github.io/) translates system calls using `ptrace`;
this same-architecture configuration is not a separate-kernel VM. A Python
downloader does not make its native payload interpreted code. The official
policy does not explicitly resolve this particular execution model or define a
separate-kernel/CPU-emulation test. Their absence alone is not a rejection. This is a
material Play review risk, not a finding that all terminal apps are prohibited.
The concrete question is how Google applies the exception to these disclosed
flows. User consent, hashes, successful execution tests, or removing only a CLI
installation shortcut do not answer it. A documented ordinary submission is
the selected review route; a separate advance support inquiry is not stated as
a policy prerequisite.

The November 14 follow-up found a current implementation comparator, beyond an
old terminal-app anecdote. The [Termux Play listing](https://play.google.com/store/apps/details?id=com.termux&hl=en)
was publicly available, showed an October 9, 2026 update, and described apt
package installation. The [Play-specific maintainer repository](https://github.com/termux-play-store)
documents its target-SDK, permission and sharedUserId changes. Its
[launcher at commit `fea9fe2`](https://github.com/termux-play-store/termux-apps/blob/fea9fe2cfc484c621e5bf7e42875dab3277b8f90/termux-app/src/main/java/com/termux/app/TermuxShellUtils.java)
routes app-private ELF execution through the Android system linker. The Play
package repository also contains [PRoot](https://github.com/termux-play-store/termux-packages/blob/master/packages/proot/build.sh)
and [PRoot-Distro](https://github.com/termux-play-store/termux-packages/blob/master/packages/proot-distro/build.sh)
recipes; recipe presence alone does not prove a currently served, working or
individually approved package. The [upstream installation guide](https://github.com/termux/termux-app#google-play-store-experimental-branch)
identifies this as a separate experimental Play branch.

This is evidence supporting a reasoned submission attempt with Z8's local
terminal design. It is not a Google-issued interpretation, transferable
approval, or proof that every Z8 flow matches Termux. No categorical rewrite
into a remote terminal or separate-kernel VM follows from the public policy.
Retain the factual native-download disclosure and address the actual review
outcome rather than recording an unsent inquiry as the only way forward.

The current rc6 flows are explicit selected-tool apt installation in
[`tool-manager.sh`](../runtime/guest/tool-manager.sh), the separate native Node download
in [`install-node.py`](../runtime/guest/install-node.py), and the native CLI
downloads in [`install-ai.sh`](../runtime/guest/install-ai.sh). The host also uses
Android's system linker through
[`Z8RuntimeLauncher`](../overlay/app/src/main/java/com/termux/app/Z8RuntimeLauncher.java)
and a bundled PRoot loader through
[`Z8Guest`](../overlay/app/src/main/java/com/termux/app/Z8Guest.java).
All these paths, including user/provider CLI updates, belong in the disclosure.
The absence of DEX loading does not alone exempt native Linux executables.
The ordinary guest-to-app browser and notification paths use the app-owned,
token-checked message bridges in `Z8AttentionBridge` and `Z8BrowserBridge`.
That is useful evidence about indirect integration, not a claim that PRoot
prevents arbitrary same-UID guest code from reaching Android resources. The
[AOSP architecture](https://source.android.com/docs/core/architecture)
distinguishes framework APIs, native libraries and kernel access; neither
equating every Linux syscall with a Java API call nor claiming that all native
code is isolated would accurately describe this design.

If the exception does not cover this design, the real alternatives are a
different local execution architecture, delivery of all relevant native code
through supported Play code modules with external native installation/update
paths removed, or a remote-terminal product. Each changes compatibility or
scope and requires a new candidate and testing. Play Asset Delivery is not a
native-code workaround: its [official overview](https://developer.android.com/guide/playcore/asset-delivery)
excludes executable code. No such redesign has been made in this follow-up.

### Historical Ubuntu assessment and alternatives, before the Debian decision

The following assessment records the modified Ubuntu image delivered with rc3
and the alternatives considered on November 14. It is retained for those
artifacts and existing environments; rc5/rc6 distribute the Debian image
described above. Statements about an unimplemented migration describe that
earlier assessment, not the current release.

**Ubuntu distribution basis.** The
[Canonical IPR policy](https://canonical.com/legal/intellectual-property-policy)
(page dated 2015-07-15, checked 2026-11-14) distinguishes unmodified redistribution
from modified distributions and addresses trademarks/recompilation. It also
expressly preserves rights under individual component licenses. Z8's
[guest preparer](../tools/prepare-guest.py) changes `bash.bashrc`, adds managed
files, normalizes archive metadata and repackages the image; Ubuntu identity
remains. It is not an unchanged mirror. Identify any existing Canonical
arrangement covering this image, or document a defensible distribution and
trademark basis. A complete component-source package alone does not settle this
question. Do not remove attribution or declare all component rights invalid.

A comparison with the pinned official Base archive found that 2,561 of its
2,562 original regular files, including all 722 ELF files, retain their bytes;
`etc/bash.bashrc` changes. Packaging also removes 12 setuid/setgid modes,
materializes two hard links and records 194 symlinks separately. Added Z8 files
and the visible Ubuntu identification still make the delivered image modified.
The reviewed rc3 app distributed the modified ZIP itself; later on-device apt,
Node and optional-tool downloads are separate flows. This finding does not
declare all modified Ubuntu redistribution unlawful, or negate rights granted
by the individual component licenses.

Delivering only the byte-identical official Base archive, with Z8-owned files
and patch instructions separate and applied during the user's installation,
is a reasonable interpretation to assess against the policy's unmodified
redistribution and personal/internal modification provisions. It is more closely
aligned with that wording than shipping the already modified ZIP, but this
review does not certify Canonical's interpretation or a trademark licence.
Merely adding an original tar next to the current modified ZIP would not make
that modified image unmodified. Preserve notices, identify the customized
environment accurately and avoid an endorsement claim.

The host core already contains tar and gzip. This alternative can preserve the
Ubuntu package/runtime versions, prepared-base identity and existing projects;
it nevertheless needs a verified original-archive installer, staged overlay
application and final-tree equivalence/security tests. At that assessment, the
Android guest installer accepted only the normalized ZIP; no original-archive
path had been implemented.

A fresh Debian base is the other concrete option. Debian's
[derivatives guidance](https://www.debian.org/derivatives/) expressly supports
independently branded modifications, subject to component licences and
[trademark conditions](https://www.debian.org/trademark). A read-only assessment
verified the November 4 Debian 13.7 ARM64 input identified by
[Debian's Docker provenance page](https://docker.debian.net/), and matched all
78 embedded packages to exact source versions. At that assessment, no Debian
migration had been made. It would change the guest runtime and source inventory
and require fresh setup/CLI tests. Existing Ubuntu project HOME/source/rootfs
must remain intact.
The assessed prepared-base cache did not compare its distribution to the
bundled image; a lock-only change would therefore retain Ubuntu for existing
templates. Changing the cache identity also needs care to avoid blocking old
projects behind the global setup screen. Select and test that compatibility
behavior explicitly rather than relabeling an Ubuntu filesystem as Debian.

### Claude Code operator terms and retained signature evidence

Current
[Claude Code legal documentation](https://code.claude.com/docs/en/legal-and-compliance)
expressly covers products that preinstall **or run** Claude Code. Its standard
route requires [Commercial Terms](https://www.anthropic.com/legal/commercial-terms),
an unmodified binary with authentication methods intact, and users who
authenticate and pay directly. It also permits users to sign into the unmodified
CLI with their own Claude subscriptions. On November 14, the operator explicitly
authorized and completed Anthropic's standard Platform onboarding assent to the
Commercial Terms and Usage Policy. The actual assent and completed dashboard
flow were recorded privately, without publishing personal identity or account
details. This supplies the previously missing operator-assent evidence; it is
not an Anthropic endorsement, negotiated exception, or confirmation of every
deployment condition. Non-bundling alone was not the terms basis. This does not
imply that Z8 is an AI service, that subscription login must
be replaced with an API gateway, or that every deployment needs a separately
negotiated agreement. Plain-text compatibility descriptions must not imply
provider endorsement.

The source and retained rc3 guest were checked for these technical conditions:
the installer checks the official manifest and binary hashes, publishes a
symlink to the unchanged binary, and the UI launches `command claude` without
authentication-forcing flags. It does not install a Z8 account gateway or a
provider-credential collector. These technical conditions remain separate from
the newly recorded operator assent and must stay true in each release. The
operator-assent record contains the applicable account/terms evidence privately;
the public developer display name is not used as proof of legal identity.

The subsequent rc5/rc6 installers verify Claude's exact release-manifest
signature and signing-key fingerprint before binary download or execution,
including explicit reinstalls. The earlier rc3/rc4 recipes only checked pinned
manifest/binary hashes; those historical artifacts have not been relabeled.
[Claude setup documentation](https://code.claude.com/docs/en/setup) describes that
verification. On November 14, the existing ARM64 guest `gpgv` 2.4.4 successfully
verified the pinned 2.1.285 manifest, including a fresh official HTTPS metadata
download, against primary fingerprint
`31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE`. Altered manifest bytes, an altered
signature and a wrong expected identity were rejected. The verifier uses a
private temporary home and explicit hash-pinned keyring; no provider executable,
authentication or model call was part of this check. This ADB-root-started PRoot
metadata test is not ordinary app-session installation QA. The pinned key is
not a live revocation service; the publisher's key changes still require
maintainer review. Keep the distinction between
installer pins and subsequent vendor/user updates, and do not claim official Android support from Linux ARM64
compatibility tests.

## Google Play technical inquiry — DRAFT, NOT SENT

**No external transmission is authorized by this document or the review request.**
An operator must choose whether and where to send this draft. It is a factual
inquiry, not evidence of acceptance.

Official route: [Play Console Help](https://play.google.com/console/help), linked
from [Get Developer Support](https://support.google.com/googleplay/android-developer/answer/10357403?hl=en).
Use the developer account's Help menu where available. Do not use an enforcement
appeal or select an inaccurate account status for an unpublished app inquiry.

Subject: Device and Network Abuse exception — local ARM64 PRoot terminal

We are preparing Z8 (`dev.devsigner.z8`, `0.1.0-rc3`, version code 4), a free
Android terminal with no ads or in-app purchases. It targets API 36 and runs under the ordinary app UID without
root. The APK supplies the Android host runtime, PRoot and its native guest
loader, plus a Linux root filesystem. The proposed Play distribution would use
Play for application updates.

After user-initiated setup, the local environment downloads Linux packages using
apt and a pinned native Node.js archive. Users may also explicitly install
unmodified official Codex and Claude Code CLIs directly from their publishers
and authenticate with their own accounts.
These downloads include native ARM64 executables and shared libraries. They run
under PRoot's ELF loader and syscall translation against the Android kernel;
this is not QEMU CPU emulation or a separate-kernel VM. The host launches native
programs using Android's system linker and bundles the PRoot ELF loader in its
native libraries. The environment shares the app UID and is not represented as
a security boundary between projects.

The Android application does not download replacement APKs or DEX updates.
Users can install further Linux tools, and a CLI's own update command may
download native code separately from Z8 application updates. We are disclosing
these flows as well as the initial installer.

Does this execution model qualify for the VM/interpreter exception in the
Device and Network Abuse policy? If it does not, which of these native-code
delivery/execution paths must change for a Play-distributed version? Would a
fixed native tool catalog delivered exclusively through AAB/Play Feature
Delivery, with APK-controlled native execution and no external native-code
installation or update path, address this restriction? We can
provide the architecture, exact artifact identities and a demonstration of
installation, execution, permissions and termination. We are seeking guidance
on the disclosed behavior, not treating technical compatibility as approval.

Public source: https://github.com/devsigner9920/z8/tree/9f90cd9dfddbeb3eede73df185470b1e4b134967

Candidate AAB SHA-256: d865a7b27211f3f7f485f7e60f5d1250b4dc963570937a56291690ae7a8d283c

Developer display name: romi. Contact: ethsy2462@gmail.com.

## Canonical redistribution inquiry — DRAFT, NOT SENT

**No external transmission is authorized.** No Canonical approval or agreement
is asserted by this draft.

Official route: [Canonical trademark enquiries](https://canonical.com/legal/terms-and-policies/contact-us),
linked from section 8 of the IPR policy. Enter the real operator details; a
public developer nickname does not establish a legal name or company.

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

Public source: https://github.com/devsigner9920/z8/tree/9f90cd9dfddbeb3eede73df185470b1e4b134967

Normalized guest SHA-256: 38463da28ca71e6be8ef36c0ff0f5a4da558eee3577cfd7b30e14c0ce6d4ef54

Developer display name: romi. Contact: ethsy2462@gmail.com.
