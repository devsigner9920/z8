# Preparing a public GitHub source release

Documentation: [English](../README.md) | [한국어](../README.ko.md)

November 2, 2026. This procedure distinguishes publishing a source repository from releasing app binaries. The operator's display name is **romi**, and the public contact is **ethsy2462@gmail.com**. The designated GitHub account is `devsigner9920`. Before remote operations, verify the actual login and repository owner returned by the connected tool. An account name alone does not establish that a repository exists or that access has been granted.

## What to publish

- Z8's `overlay/`, `runtime/`, `tools/`, `tests/`, `docs/`, and public build settings.
- The root `LICENSE` (GPL-3.0-only), original notices and exceptions in `LICENSES/`, `THIRD_PARTY_NOTICES.md`, and contribution and security reporting guides.
- Source distribution checks under `.github/`. These do not automatically publish, sign, or upload releases.
- The logo, Prism images, and regeneration inputs. On November 2, 2026, the maintainer confirmed modification and redistribution rights and GPL publication. Third-party assets such as Material Icons retain their original licenses.

Exclude `.git/`, `.local/`, `artifacts/`, `reports/`, `design-qa.md`, credential files, signing keys, completed operator review records, and notices generated for earlier releases from the public repository. Regenerate public notices using the sources and packages that will actually be distributed.

## Create a source folder for review

```sh
python3 tools/prepare-public-repo.py
```

The command creates a source folder identified by its hash, a ZIP, and a per-file SHA-256 inventory under `artifacts/public-repo/`. It does not make Git commits, create remote repositories, or upload files. Existing identical outputs are not overwritten. Use a fresh `--output` path for another verification run.

The tool selects paths explicitly and checks sensitive filenames, symbolic links, excessive file sizes, and some known authentication token patterns. Detection messages show only the filename and category. Pattern checks are not a guarantee that all sensitive information has been removed. Review the inventory and actual contents before initial publication. Use this public source folder rather than the entire working directory.

## Connect the repository

The public repository is [devsigner9920/z8](https://github.com/devsigner9920/z8). When working with an existing repository, read its contents and confirm that it is the intended project first. Do not blindly overwrite files or branches, or change visibility.

The public preparation ZIP is intended for an ordinary GitHub source repository. GitHub's automatically generated Source code ZIP also contains only the repository files at that revision. Neither replaces a binary's corresponding source distribution that includes the bundled runtime packages.

After verifying the account and repository, upload the public files as the initial commit, then read back the remote inventory and commit to verify them. Do not put tokens or keys in this document, commit GitHub passwords, or include credentials in remote URLs.

## Source checks

GitHub Actions' `Source distribution checks` uses Python 3.12 to verify public source and license inclusion, secret exclusion, signing and distribution boundaries, and native alignment validators. Actions are pinned to exact commits and use only `contents: read`. This workflow does not perform a full Android build or physical-device testing. The Groovy check that needs a local cache may be skipped in a clean environment; do not report a skipped check as passed.

The workflow also checks language preferences and both CLI consent languages on the host. It does not exercise Android screens.

Run the same checks locally:

```sh
python3 -m unittest discover -s tests -p test_public_source.py -v
python3 -m unittest discover -s tests -p test_release_compliance.py -v
python3 -m unittest discover -s tests -p test_release_build.py -v
python3 -m unittest discover -s tests -p test_native_alignment.py -v
python3 -m unittest discover -s tests -p test_signing_identity.py -v
python3 -m unittest discover -s tests -p test_language.py -v
python3 -m unittest discover -s tests -p test_codex_launch.py -v
```

## Privacy policy and release source URLs

The privacy policy is maintained in [privacy.html](privacy.html), with a [Korean translation](privacy.ko.html). The default published URL is the [Z8 Privacy Policy](https://devsigner9920.github.io/z8/privacy.html). GitHub Pages uses the `docs/` folder on `main`. Confirm that the URL opens without authentication before distributing the app. The [earlier draft](PRIVACY_POLICY_DRAFT.ko.md) is reference material.

The app's `sourceUrl` must directly download the complete corresponding source ZIP for that version. Once the real repository and tag are fixed, choose a filename such as `releases/download/<tag>/z8-source.zip` in advance. Putting the source ZIP's own hash in the source configuration creates a circular dependency. Attach the locally generated ZIP, whose filename contains a hash, to the Release under the fixed name `z8-source.zip`.

The current configuration targets `v0.1.0-rc2` and the source asset `z8-source.zip`. Verify the public download after publishing it. Publishing a source preview does not mean an APK/AAB has been distributed or that final corresponding source review is complete. The earlier `v0.1.0-rc1` source preview and its device validation records remain historical references.

## Before publishing app binaries

1. Finalize the real policy and source URLs and release settings.
2. Follow the [corresponding source procedure](RELEASE_LICENSES.md) to create a ZIP including the exact host/guest package sources, generate notices, and rebuild the candidate APK/AAB.
3. Link the source ZIP and distribution artifact hashes, notices, and manifests, and verify public downloads.
4. Complete the necessary device, authentication, and policy checks for that new candidate. Read [release status](RELEASE_STATUS.md); do not present an older candidate's results as tests of current files.

Completing source publication preparation is not Google Play submission, provider approval, or a guarantee of binary reproducibility. Do not include development or upload keys in public sources. Follow the [build procedure](../BUILDING.md) and [third-party notices](../THIRD_PARTY_NOTICES.md) as well.
