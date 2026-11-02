# Reporting security issues

Documentation: [English](README.md) | [한국어](README.ko.md)

If you find a vulnerability or possible exposure of private information, report it privately to **[ethsy2462@gmail.com](mailto:ethsy2462@gmail.com)**. Do not post exploitable details or confidential information in public issues, PRs, or comments.

## What to include

- The affected source commit, or app version and APK SHA-256
- Android version, CPU architecture, and relevant settings
- Minimal reproduction steps using synthetic data, with expected and actual behavior
- Expected impact and minimal logs or screenshots with sensitive information removed

**Do not send passwords, API keys, sign-in tokens or cookies, signing keys, actual CLI credential files, or entire user source trees.** Include only the minimum information needed to explain the issue in your initial report. Revoke or replace exposed credentials with the relevant service rather than sending the credentials themselves.

Do not test against other people's accounts, devices, or projects, or access or modify their data. Use a dedicated emulator and synthetic materials where possible. Disclosure timing and any additional information needed will be coordinated after reviewing the report.

## Support scope

Z8 has not reached a stable release. A list of supported stable versions and a long-term security support period have not yet been established. Reports are reviewed against current development sources. There is no guaranteed response or fix deadline, or promise of patches for previous test APKs. This document does not establish a bug bounty or promise compensation.

PRoot is not a security isolation mechanism between projects. See [release status](docs/RELEASE_STATUS.md) for access available to code running under the same app UID and known execution limitations. For vulnerabilities in an external CLI or package itself, also check that provider's reporting procedure. Contact us at the address above if the issue involves Z8's installation, execution, preview, or data handling.
