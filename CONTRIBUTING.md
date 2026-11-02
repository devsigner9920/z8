# Contributing

Documentation: [English](README.md) | [한국어](README.ko.md)

Z8 is an Android development terminal that has not reached a stable release. Small fixes and reproducible issue reports are welcome. Before implementing a large feature, describe the problem and user flow so its scope can be agreed. The product focuses on local development environments and official CLI execution. See [release status](docs/RELEASE_STATUS.md) for its current scope.

## Development environment

Follow [BUILDING.md](BUILDING.md) to prepare your tools. The setup scripts currently target macOS ARM64 and require Python 3.12 or later and Git. Runtime source builds use a Linux Docker environment.

- `overlay/`: Z8 Android sources, resources, and files applied to upstream
- `tools/`: Source preparation, builds, runtime preparation, and release verification
- `runtime/`: Linux environment and explicit CLI installation and execution scripts
- `tests/`: Regression checks run on the development host
- `tools/sources.lock.json`: Pinned upstream commits

`upstream/` contains the pinned original sources. `.local/build-src` and `.local/build-candidate` are generated output. Make changes in `overlay/` or the relevant preparation tool. Review provenance, hashes, and license notices when changing dependencies or versions.

## Changes and validation

Describe the problem, user-visible behavior changes, checks performed, and remaining limitations in your PR. Include screenshots without private information for UI changes and reproduction conditions for bug fixes. Use synthetic data instead of real accounts or credentials.

Run the host test suite from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

You can also check an individual area. For example, the preview data deletion state tests are:

```sh
python3 -m unittest discover -s tests -p 'test_preview_data.py' -v
```

Some checks require a prepared JDK, Gradle, or the pinned upstream checkout. Do not report tests skipped because of missing tools as passed. The APK build command separately runs terminal-emulator unit tests and checks signing, app identity, ABI, SDK, and other artifact properties. For UI, process, or PRoot changes, also test on a dedicated emulator or test device. Record the Android version, ABI, APK hash, and paths exercised. Test scripts may install apps or modify test projects; verify their target device and prerequisites first.

For app-owned text, follow the [language guide](docs/LOCALIZATION.md). Keep English and Korean consent and data-handling explanations equivalent, and preserve commands and user content.

The source publication CI runs `test_release_compliance.py`, `test_public_source.py`, `test_release_build.py`, `test_native_alignment.py`, and `test_signing_identity.py`. These check contracts such as source distribution and prevention of key disclosure. They do not replace a complete app build, device testing, or store release verification.

The workflow also runs `test_language.py` and `test_codex_launch.py` for language preferences and CLI consent behavior. These are host checks, not Android UI tests.

Prioritize checks that reproduce the relevant failure. Do not mark unperformed checks complete or reuse results from a different APK as evidence for a new build. Do not add account login or external service operations as default automated test steps.

## Files to publish

Do not include signing keys, tokens, `.env`, CLI credentials, user projects, or logs and screenshots containing private paths. `.local/`, `upstream/`, `artifacts/`, and internal `reports/` are development outputs and are not part of ordinary contributions. Provide only reviewed, minimal log excerpts needed to reproduce an issue. Use the [private reporting procedure](SECURITY.md) for security vulnerabilities instead of public issues.

## Contribution licensing

Submit only code and materials you have the right to provide. New contributions to Z8 are provided under the project's GPL-3.0-only terms. Modifications to existing files or modules with separate licenses retain those terms and notices. Include the original source, license, and copyright notices when bringing in external code.

No separate CLA or copyright assignment is currently required. File and module exceptions follow the [third-party notices](THIRD_PARTY_NOTICES.md) and original file notices.
