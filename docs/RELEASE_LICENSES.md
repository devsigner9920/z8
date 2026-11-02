# Release sources and license evidence

2026-11-01. These tools prepare and verify evidence. They do not accept provider
terms, approve Ubuntu branding, publish files, or give legal approval. A generated
inventory is not a claim that every license obligation has been satisfied.

## Outputs and order

1. Select the exact runtime and guest manifests used for the candidate. Inventory
   the packages installed in those ZIPs, not all available Termux recipes.

   ```sh
   python3 tools/collect-release-package-sources.py \
     --runtime-manifest artifacts/runtime/PROFILE/manifest.json \
     --guest-manifest artifacts/guest/IMAGE/manifest.json \
     --output artifacts/compliance/package-sources --fetch --allow-incomplete
   ```

   `--fetch` downloads checksum-pinned sources over HTTPS. Without it, existing
   downloads and cached Ubuntu source indexes are checked without network access.
   It preserves actual installed copyright files, collects source-archive license
   members without extracting source code, and writes `package-sources.json`.
   `--allow-incomplete` only changes the process exit code; unresolved evidence
   remains `INCOMPLETE`. It must never be interpreted as production approval.

2. Obtain the release's actual Gradle runtime dependency inventory. From the
   generated app checkout:

   ```sh
   ./gradlew --init-script /absolute/z8/tools/release-license.init.gradle \
     :app:z8ReleaseArtifacts \
     -Pz8ComplianceOutput=/absolute/z8/artifacts/compliance/gradle-artifacts.json
   ```

   This uses `releaseRuntimeClasspath`. A scan of every cached JAR would include
   unrelated/build-only dependencies and is not a substitute. The notice generator
   reads POM license declarations (including cached parent POMs) and embedded
   license/NOTICE files; missing declarations remain explicit review failures.
   Only external modules are resolved as binary artifacts. Local project modules
   are covered by the source snapshot, avoiding Android secondary-variant ambiguity.

3. Create the source ZIP, including verified package source payloads:

   Set `release/config.json` first, including a version-specific public source URL
   whose filename is chosen in advance, such as `/releases/2/z8-source.zip` on
   your real HTTPS host. The config itself is part of the source snapshot: putting
   the generated archive hash into that config URL would create a circular hash
   dependency. Upload the generated local ZIP to the preselected version URL and
   verify its exact bytes with `--check-source-url`. Changing the public config
   requires regenerating the source ZIP, notices and candidate before review.

   ```sh
   python3 tools/package-release-source.py \
     --package-sources artifacts/compliance/package-sources/package-sources.json \
     --output artifacts/compliance/source
   ```

   The archive includes the locked pristine Termux source exports, Z8 overlay,
   tools, runtime scripts, tests, documentation, public `release/config.json`,
   release decision/QA examples, and collected package sources. Actual private
   decision/QA records are not included in the public source archive.
   It does not copy `.local`, repository `.git` configuration, signing keys,
   `.env`, CLI credentials, or arbitrary build caches. Upstream public test keys
   are also excluded and the omission is recorded. Safe upstream relative
   symlinks are preserved as ZIP symlinks; use an extractor that preserves them.
   Local source symlinks fail rather than following files outside the source set.

   `source-manifest.json` records every file hash, mode, omission and input digest.
   The ZIP is deterministic for identical inputs. This does **not** assert a
   bit-for-bit reproducible APK or complete copyleft compliance. The existing
   preparers verify exact Git HEADs, so rerunning those preparers requires restoring
   the pinned upstream Git checkouts; source exports themselves contain no Git
   metadata. No private signing key is needed to modify the sources; use your own
   signing key for your build. Keep the source exports available even if upstream
   hosting changes. Before final release, prove the documented reconstruction path
   and resolve any missing source/build inputs.

4. Generate offline notices before the final APK/AAB build:

   ```sh
   python3 tools/generate-release-notices.py \
     --source-manifest artifacts/compliance/source/source-manifest.json \
     --package-sources artifacts/compliance/package-sources/package-sources.json \
     --gradle-artifacts artifacts/compliance/gradle-artifacts.json \
     --allow-incomplete
   ```

   The default destination is `overlay/app/src/main/assets/z8-licenses/`:
   `third-party-notices.txt` is UTF-8 text for the app's offline reader;
   `release-notices.json` records input hashes, components and unresolved issues.
   Both generated files are excluded from the source-input digest to avoid a
   circular hash dependency. Existing Material Icons source/license text remains.
   Rebuild after generation. Generate a fresh source snapshot/notices again if
   source, dependency versions or selected runtime images change.

5. Verify the final AAB/APK before publishing it:

   ```sh
   python3 tools/verify-release-compliance.py \
     --artifact /absolute/final-candidate.aab \
     --source-manifest artifacts/compliance/source/source-manifest.json \
     --package-sources artifacts/compliance/package-sources/package-sources.json \
     --notices overlay/app/src/main/assets/z8-licenses/release-notices.json \
     --gradle-artifacts artifacts/compliance/gradle-artifacts.json \
     --runtime-manifest artifacts/runtime/PROFILE/manifest.json \
     --guest-manifest artifacts/guest/IMAGE/manifest.json \
     --source-url https://YOUR-REAL-DOMAIN/EXACT-SOURCE-ARCHIVE.zip \
     --check-source-url --review /absolute/release-license-review.json \
     --output artifacts/compliance/verification.json
   ```

   Replace the example URL; it is not a deployed source location. The verifier
   checks the exact source ZIP over credential-free HTTPS. A landing-page based
   source offer is possible legally, but is not verified by this direct-archive
   implementation; do not fake a successful result for another delivery method.
   `VERIFIED` means this tool's evidence checks passed, not Google approval.
   Default exit status is 2 when blocked. Candidate builds can use
   `--allow-incomplete`, but retain the `BLOCKED` status and blocker list.

## Human review record

The notice generator accepts `--review` only for a real, recorded review of exact
inputs. It must contain `schemaVersion: 1`, `noticesInputs` exactly matching the
generated notice report's `inputs`, a nonempty `reviewedBy`, `reviewedAt` in
YYYY-MM-DD format, and true `sourceClosureReviewed` / `noticeCompletenessReviewed`.
This record is never generated or filled with an invented reviewer. It addresses
the release review requirement only; it does not waive missing source payloads,
unknown licenses, incorrect hashes or inaccessible source URLs. Supply the same
record to the final verifier.

Review the actual license text, source/header attributions, static linking,
Maven/native dependencies, modification notices and any per-file exceptions.
Recorded human review is evidence of a process, not a replacement for the license
obligations. Keep operator/Anthropic terms and Canonical distribution decisions
separate; a user's app checkbox cannot resolve the operator's contract obligations.

## Known conservative boundaries

- Ubuntu package source name/version comes from the shipped dpkg status, including
  an explicit `Source: name (version)` when present. The collector matches exact
  versions in noble/main, noble-updates/main and noble-security/main Sources indexes.
  `--ubuntu-snapshot 20260908T120000Z` selects the official Ubuntu historical
  snapshot for an image built on that date (select the date matching your image).
  Historical payload URLs retain the snapshot base, instead of silently pointing
  to a current mirror that may have removed that version.
  `--ubuntu-index` can supply an archived exact index. An absent historical version
  stays missing; a newer version is not substituted. Index bytes and source payload
  hashes are recorded. Index OpenPGP signatures are **not** validated by this tool.
- Termux recipes are parsed as data. Shell substitutions are never executed. Simple
  pinned source arrays and GNU bash/readline patch series are supported. Dynamic
  recipe expressions, unpinned Git checkouts and additional build-time fetches need
  exact reviewed source evidence. `SKIP_CHECKSUM` is not treated as a verified hash.
  If a matching original build cache still exists, export only the exact source
  tree with `git archive`, never its `.git` directory or the entire cache. Supply
  `--retained-git-sources CAPTURE.json` with the selected runtime archive SHA and
  per-component package id/version, recipe SHA, full source commit, relative
  archive filename, archive SHA, upstream attribution URL and capture method.
  This supplements source provenance; retained cache contents alone are not an
  independent proof of bit-for-bit binary reproducibility. Source-closure review
  remains required. Captured archives are copied into the published source ZIP.
  Effective runtime overlay files are copied individually from the matching
  generated build tree only after their hashes match provenance. If the packaging
  script changed since the binary build, `--historical-packaging-script FILE`
  supplies the preserved original; only the exact recorded hash is accepted.
  Dependency-seeded runtimes retain both original and new build-input sets.
- The source ZIP includes verified downloads, not just URLs. Missing files remain
  blockers. Do not publish only the small application source ZIP while leaving the
  native/guest source payloads on a developer's computer.
- A package license label or an installed copyright file does not prove complete
  source closure. `legalCompletenessReviewed` remains false in the machine-generated
  collector report. Separate independent CLI downloads are not falsely described
  as APK-embedded binaries.
- All-source GitHub publication is not the only permissible source delivery
  approach. Whichever compliant approach the maintainer selects must remain
  available for the required period and match the distributed binary.

The work is validated with `python3 -m unittest discover -s tests -p
test_release_compliance.py -v`. Tests cover credential exclusion, deterministic
archives, symlink refusal, source/member tampering, exact Ubuntu version matching,
nonexecution of recipe substitutions, and incomplete notice reports.
