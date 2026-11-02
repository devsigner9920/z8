# License scope and preserved notices

Z8-authored source code, modifications, build/runtime scripts and tests in this
repository are distributed under **GNU GPL version 3 only**, identified as
`GPL-3.0-only`, unless a file carries a more specific license notice. The full
license is in [../LICENSE](../LICENSE). This declaration does not change the
licenses or copyright notices of third-party code and assets.

The Z8 logo, its generated branding/launcher variants, and the Prism theme
background reference are also distributed under GPL-3.0-only. On 2026-11-02,
the maintainer, using the public developer name **romi**, confirmed having the
rights to publish both the Z8 logo and Prism background under those terms.
The covered artwork is under `docs/design/brand/`,
`overlay/app/src/main/res/mipmap-*/ic_launcher*.png`,
`overlay/app/src/main/res/drawable-nodpi/z8_launcher_foreground.png`, and
`overlay/app/src/main/assets/z8/design/prism-reference.png`.
This recorded maintainer confirmation does not change the separate Apache-2.0
license of the Google Material Icons assets.

Z8 incorporates the Termux app at revision
`8629e632fcb95da272221be327db653fb24befe9`, as recorded in
[sources.lock.json](../tools/sources.lock.json). The original license notices are
copied here so they remain readable without the ignored `upstream/` checkout.
Original source headers remain in the pinned source and prepared application.

| Component or notice | License and local text |
| --- | --- |
| Termux app and Z8 application modifications | GPL-3.0-only; [full text](../LICENSE), [verbatim Termux notice](termux-app.NOTICE.md) |
| Termux terminal emulator/view portions | Apache-2.0 according to the upstream app notice; [full text](Apache-2.0.txt) |
| `termux-shared` general license | MIT, subject to the upstream file/directory exceptions; [MIT text](MIT.txt), [verbatim shared-module notice](termux-shared.NOTICE.md) |
| `termux-shared/.../termux/` files | GPL-3.0-only unless the file or directory specifies another license, as the shared-module notice explains |
| Identified libcore/ojluni-derived filesystem files | GPL-2.0-only WITH Classpath-exception-2.0; [full license and exception](GPL-2.0-only-with-Classpath-exception-2.0.txt), [original source headers](termux-source-headers.txt) |
| `StreamGobbler.java` and `PopupWindowCompatGingerbread.java` | Apache-2.0; their Chainfire and Android Open Source Project notices are retained in [source headers](termux-source-headers.txt) |
| `ArgumentTokenizer.java` | The DrJava/JavaPLT/Rice University three-clause BSD-style permission and disclaimer appear verbatim in [source headers](termux-source-headers.txt); this file-specific notice is retained independently of the module's general MIT description |
| Google Material Icons Outlined | Apache-2.0; [icon provenance and notices](../overlay/app/src/main/assets/z8-licenses/material-icons.md) |
| Z8 logo/launcher artwork and Prism background reference listed above | GPL-3.0-only, based on the maintainer's 2026-11-02 rights confirmation; [full text](../LICENSE) |

The copied `termux-app.NOTICE.md` and `termux-shared.NOTICE.md` are byte-for-byte
upstream documents. Their original relative links refer to the upstream tree.
The corresponding pinned pages are
[Termux app LICENSE.md](https://github.com/termux/termux-app/blob/8629e632fcb95da272221be327db653fb24befe9/LICENSE.md)
and [termux-shared LICENSE.md](https://github.com/termux/termux-app/blob/8629e632fcb95da272221be327db653fb24befe9/termux-shared/LICENSE.md).

## Text provenance

- `../LICENSE` preserves the complete GNU GPLv3 text supplied as
  `usr/share/common-licenses/GPL-3` in the verified Ubuntu guest source evidence.
  Canonical license text: <https://www.gnu.org/licenses/gpl-3.0.html>.
- `Apache-2.0.txt` preserves the complete Apache License 2.0 text supplied as
  `usr/share/common-licenses/Apache-2.0` in the same evidence.
  Canonical license text: <https://www.apache.org/licenses/LICENSE-2.0>.
- `MIT.txt` is the standard MIT license template from the SPDX License List:
  <https://github.com/spdx/license-list-data/blob/main/text/MIT.txt>.
  Its template placeholders do not name a new copyright owner. Actual upstream
  copyright notices and file-specific terms remain applicable.
- `GPL-2.0-only-with-Classpath-exception-2.0.txt` is the unmodified OpenJDK license
  at tag `jdk-17+35`:
  <https://github.com/openjdk/jdk/blob/jdk-17%2B35/LICENSE>.
  The exception applies only to the source files whose notices grant it.
- `termux-source-headers.txt` reproduces the nine copyright-bearing comment
  blocks in the pinned Termux `terminal-emulator`, `terminal-view` and
  `termux-shared` main Java/C sources, with their original file paths. It is an
  additional notice index, not a replacement for the source headers.

GPL text appendices contain sample notices for applying the license. Z8's
selection is GPL version 3 **only**; the sample wording does not change that
selection. No new copyright-owner name has been inserted into these texts.

## Release-specific dependencies

Bundled native packages, the Ubuntu guest, Maven dependencies and independently
installed CLI tools have their own notices and terms. This directory is not a
claim that all of them use the application's GPL license. The release source
archive and generated offline notices are assembled and verified using
[RELEASE_LICENSES.md](../docs/RELEASE_LICENSES.md). A source repository alone is
not a substitute for supplying the corresponding source of the actual binary
release and preserving its applicable notices.
