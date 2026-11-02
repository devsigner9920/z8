# Third-party source and modifications

## Application license

As of 2026-11-02, Z8-authored source code, modifications, build/runtime scripts and
tests in this repository are distributed under **GPL-3.0-only**, unless a file
carries a more specific notice. The complete license is in [LICENSE](LICENSE).
Z8 incorporates the GPL-3.0-only Termux app. Existing third-party licenses,
exceptions and copyright notices remain in effect; the combined application is
not offered under an MIT-only license.

- Upstream: <https://github.com/termux/termux-app>.
- Pinned app revision: `8629e632fcb95da272221be327db653fb24befe9`, recorded in
  [sources.lock.json](tools/sources.lock.json).
- Original app notice, copied verbatim: [termux-app.NOTICE.md](LICENSES/termux-app.NOTICE.md).
- Original shared-module notice, copied verbatim: [termux-shared.NOTICE.md](LICENSES/termux-shared.NOTICE.md).
- Local full license texts, scope and source-header notices: [LICENSES](LICENSES/README.md).

The terminal emulator/view include Apache-2.0 code from Android Terminal
Emulator. The shared module has a general MIT declaration and GPL-3.0-only,
GPL-2.0-only with the Classpath exception, Apache-2.0 and file-specific exceptions.
For example, `ArgumentTokenizer.java` retains its DrJava/JavaPLT/Rice University
three-clause BSD-style notice. Original copyright and license headers are
preserved in the source; [collected header notices](LICENSES/termux-source-headers.txt)
make these core notices readable without a local upstream checkout.

## Modifications and corresponding source

Z8 changes are expressed in `tools/prepare-app.py`, the other build/runtime tools,
`runtime/` and `overlay/`. They include application identity and filesystem prefix,
navigation and terminal input, runtime and guest installation, Android execution
compatibility, session/project management, preview and data-deletion controls,
privacy and license presentation, and release preparation. Original upstream
source headers and license files are retained. The locked pristine upstream
sources and these modifications form the prepared application source.

Distribution of GPL-covered object code must include an appropriate way for its
recipients to obtain the complete corresponding source under the applicable
license, including the modified sources and required build inputs. Publishing
only a link to the unmodified Termux project does not provide Z8's modifications.
The license does not require publishing every private development file or all
Git history. Private signing material, credentials and unrelated user projects
are excluded from the release source archive.

The source packaging, package-source collection, notice generation and verification
steps are documented in [RELEASE_LICENSES.md](docs/RELEASE_LICENSES.md). The
release source manifest identifies the exact source snapshot, and the generated
offline notice is packaged at `assets/z8-licenses/third-party-notices.txt`.
The configured source URL must provide the actual corresponding release source
distribution. A default GitHub source archive may omit the separately collected
upstream and package sources; publish the prepared release source archive too.

Debug APKs, release candidates and any upload artifacts are identified by their
own build metadata. A successful build, an open-source repository or generated
notices do not themselves establish license completeness, provider-contract
clearance or Google Play approval. Unresolved release evidence remains explicit
and blocks production verification.

## Assets and runtime dependencies

The maintainer, using the public developer name **romi**, confirmed on
2026-11-02 that they have the rights to publish the Z8 logo and Prism theme
background under GPL-3.0-only. These assets, including the Z8-generated branding
and launcher variants identified in [LICENSES/README.md](LICENSES/README.md),
are distributed under GPL-3.0-only. This is the recorded maintainer rights
confirmation; no additional copyright-owner identity has been asserted here.

The native navigation uses Google Material Icons Outlined under Apache-2.0,
pinned to revision `737e3324305806514d7909874fa1818ae1808232`. Original vector paths
are retained; the theme tint was removed and the fill normalized for runtime
tinting. Exact sources, hashes and the full license are in
[ICON_SOURCES.md](docs/design/ICON_SOURCES.md), also packaged in the APK at
`assets/z8-licenses/material-icons.md`.

Android/Gradle/JDK, Maven dependencies and bundled native packages retain their
respective licenses. Their presence does not relabel every component as GPL.
Release notices and source inventories describe the dependencies actually used
by that release.

The optional guest image is normalized from the pinned official Ubuntu Base
ARM64 archive. Original package copyright/license files remain in the image,
and its manifest records the upstream URL and SHA-256. Runtime builds also embed
packages compiled for Z8's own prefix from the pinned Termux package recipes,
preserving installed notices and build provenance. Diagnostic builds contain no
native bootstrap; they may include the verified guest image for installer testing.

## Independently installed CLI tools

Claude Code and Codex binaries are not embedded in the app's APK/AAB. When the
user explicitly requests installation, the guest installer downloads pinned
native artifacts from their official distributors. Codex retains its Apache-2.0
license, and Claude Code remains governed by Anthropic's applicable terms. This
repository does not relicense either tool or grant permission to redistribute
Claude Code. Tool login, account access and any provider subscription remain
separate from app installation.
