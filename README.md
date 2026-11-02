# Z8

**English** | [한국어](README.ko.md)

A development terminal for running Linux tools and official AI CLIs on an unrooted Android device. Z8 provides project environments, multiple terminal sessions, and local web previews.

**Z8 is under development. A stable app release and Play Store launch have not been completed.** Source publication and store release are separate steps. Read the [current validation scope and limitations](docs/RELEASE_STATUS.md) before using it.

The app starts in English regardless of the device language. Choose **Settings → App language → 한국어** to switch to Korean. See [app language](docs/LOCALIZATION.md) for persistence, existing sessions, and contribution guidance.

## What can you do?

- Keep separate HOME directories, source files, and Linux environments for each project, with multiple terminal sessions.
- Run Python, Node.js, Git, gh, tmux, and build tools on your device. Use terminal tools for file editing and Git operations.
- Preview development servers at `localhost:port` inside the app. Open external links and authentication flows in the device browser.
- Explicitly install official CLIs such as Codex and Claude Code and authenticate with your own accounts. Compatibility and limitations vary by tool and version.

Z8 provides an environment for running official CLIs. It does not offer a hosted AI service, proxy model requests, provide shared accounts, or resell usage. Network activity, accounts, charges, and terms for AI features depend on the external tools and services you use. Z8 is not an official product of Termux, OpenAI, or Anthropic.

## Environment and limitations

| Item | Current configuration |
| --- | --- |
| Android | Configured for Android 9 / API 28 and later |
| CPU | ARM64 (`arm64-v8a`) |
| Target / compile SDK | 36 / 36 |
| Development environment | Local PRoot Linux; no root or separate Termux app required |
| Screens | Designed around foldables and tablets, with session navigation adapting to window size |

The minimum SDK is not a compatibility guarantee. Preparing the base environment requires downloads and storage, and each project keeps a separate writable environment.

**PRoot is not a security VM or a security boundary between projects.** Projects share the Android kernel and app UID. Untrusted commands or code run by AI tools can affect data accessible to the app. Codex's default Linux sandbox did not work in the tested PRoot environment; do not expect the same isolation as on a conventional Linux host.

The app currently focuses on local execution. It does not provide SSH host management or remote session connections.

## Build and contribute

The [build guide](BUILDING.md) explains toolchain setup, diagnostic APKs, Linux runtime builds, and submission candidates. The current toolchain setup targets macOS ARM64; runtime source compilation uses a Linux Docker environment.

```sh
python3 tools/setup-toolchain.py
python3 tools/prepare-app.py --mode diagnostic
python3 tools/generate-release-notices.py --allow-incomplete
python3 tools/build-app.py --mode diagnostic
```

These commands produce a diagnostic APK without a Linux environment. `--allow-incomplete` permits development notice generation; it does not complete release review. Follow the runtime instructions in the build guide for project Linux environments. Build tools are installed under `.local/`, with outputs under `artifacts/`.

- [Contributing and tests](CONTRIBUTING.md)
- [Private security reporting](SECURITY.md)
- [Release status and validation limits](docs/RELEASE_STATUS.md)
- [Source publication procedure](docs/OPEN_SOURCE_RELEASE.md)
- [Project Linux environment](runtime/guest/README.md)

## License

The Z8 application is based on Termux app code. Its default license is **GPL-3.0-only**; the [full license text](LICENSE) is included. Portions with separate file or module licenses and exceptions, including Apache-2.0 and MIT, retain their original terms. Read the [third-party notices](THIRD_PARTY_NOTICES.md) and individual file notices.

Optional CLIs, Ubuntu packages, and other dependencies have their own licenses and terms. Publishing a source repository alone does not fulfill every binary distribution obligation. See the [release licensing guide](docs/RELEASE_LICENSES.md) for preparing corresponding source and notices when distributing binaries.
