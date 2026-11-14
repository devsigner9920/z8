# Distribution review

Review date: **2026-11-14**. This records the distribution evidence and remaining decisions for
Z8, a **free local terminal host for official CLIs**, with no advertising or
in-app purchases. Z8 does not operate an AI service, proxy model requests,
provide shared accounts, or resell provider usage. Users install optional CLIs
and sign in through those tools with their own accounts.

The source publication and local binary candidates are **not a Play-approved release**.
Technical tests and generated license reports do not constitute store approval
or settle contracts. The maintainer already confirmed rights to the Z8 logo and
Prism artwork on 2026-11-02; that question is not being reopened. See
[license scope](../LICENSES/README.md) and [release status](RELEASE_STATUS.md).

## Exact reviewed version

The runtime-specific findings below concern the retained **rc3** candidate. The
subsequent rc4 submission-preparation work adds first-run disclosure links,
updates operator attribution, and prepares store assets; it does not resolve the
distribution questions below. Each rc4 artifact requires fresh integrity and QA
evidence. See [current release status](RELEASE_STATUS.md).

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

The November 14 follow-up changes documentation, not these retained binaries or
their published source archive. Each new candidate needs its own source/notices
integrity checks and relevant validation.
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
| Play executable downloads | apt packages, Node and optional CLI downloads contain native code; PRoot uses the host kernel | Obtain a documented basis for the exception or change delivery/execution; a factual support inquiry is prepared below |
| Ubuntu | The bundled image is modified, while upstream executables and notices are preserved | Establish the applicable aggregate/trademark basis; a narrowly scoped Canonical inquiry is prepared below |
| Claude Code | Official binary is hash-checked and not patched; the launcher does not force an authentication method or proxy usage | Confirm the operator's Commercial Terms basis; an end user's personal subscription alone does not establish it |

The maintainer requested registration and release preparation instead of sending
inquiries; the prepared inquiries remain **unsent**. Resolve the distribution
questions from applicable evidence while preserving the local-terminal behavior. Removing an
install button, renaming native binaries or describing PRoot as a VM would not
change the underlying facts. Do not mark release-policy decisions complete
merely because this document or an inquiry exists. A vendor inquiry is an
evidence route, not a universally required advance-approval procedure.

## Decisions that remain

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
The concrete question is whether these disclosed flows qualify for the stated
exception. User consent, hashes, successful execution tests, or removing only a
CLI installation shortcut do not answer it.

The relevant flows are the apt stage in
[`provision.sh`](../runtime/guest/provision.sh), the separate native Node download
in [`install-node.py`](../runtime/guest/install-node.py), and the native CLI
downloads in [`install-ai.sh`](../runtime/guest/install-ai.sh). The host also uses
Android's system linker through
[`Z8RuntimeLauncher`](../overlay/app/src/main/java/com/termux/app/Z8RuntimeLauncher.java)
and a bundled PRoot loader through
[`Z8Guest`](../overlay/app/src/main/java/com/termux/app/Z8Guest.java).
All these paths, including user/provider CLI updates, belong in the disclosure.
The absence of DEX loading does not alone exempt native Linux executables.

If the exception does not cover this design, the real alternatives are a
different local execution architecture, delivery of all relevant native code
through supported Play code modules with external native installation/update
paths removed, or a remote-terminal product. Each changes compatibility or
scope and requires a new candidate and testing. Play Asset Delivery is not a
native-code workaround: its [official overview](https://developer.android.com/guide/playcore/asset-delivery)
excludes executable code. No such redesign has been made in this follow-up.

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
Delivering the original archive plus a separate on-device overlay is a possible
engineering option, not an already confirmed interpretation of Canonical's
policy. A fresh Debian base would remove this particular Ubuntu-image dependency
but needs new image, package/source, installer and CLI validation; changing a
name or deleting attribution is not that migration.

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

The source and retained rc3 guest were checked for these technical conditions:
the installer checks the official manifest and binary hashes, publishes a
symlink to the unchanged binary, and the UI launches `command claude` without
authentication-forcing flags. It does not install a Z8 account gateway or a
provider-credential collector. This code review does not prove the operator has
accepted a contract. Record the actual contracting person/entity, applicable
terms or agreement, effective date and evidence privately; do not infer a legal
identity from the public display name `romi` or accept terms automatically.

One concrete tooling improvement is available without changing the product:
verify Claude's exact release-manifest signature and signing-key fingerprint
when updating the pins. The current recipe verifies pinned HTTPS manifest and
binary hashes but records that detached-signature verification was not done.
[Claude setup documentation](https://code.claude.com/docs/en/setup) describes that
verification. On November 14 the public manifest, detached signature and key
were available for the pinned version; the manifest matches the existing lock
and the key fingerprint matches the documentation. This is not a successful
cryptographic signature-verification result. Keep the distinction between
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
