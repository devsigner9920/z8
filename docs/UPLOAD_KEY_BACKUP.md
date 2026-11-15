# Private upload-key backup

The upload key and its password must never enter Git, public release assets, email attachments or an unencrypted cloud upload. This operational procedure supplements the immutable rc8 source; it does not modify an app binary or register a key with Play.

`tools/backup-upload-key.py` uses macOS's native AES-256 disk-image encryption. It includes exactly the four existing upload-identity files and creates a separate high-entropy recovery password outside that image. The recovery password must be held in an independent password manager or on paper, accessible without the original Mac. Do not store it with the cloud image or paste it into a chat.

Create a new backup directory; the tool refuses to overwrite one:

```sh
python3 tools/backup-upload-key.py create --directory .local/key-backups/NEW_BACKUP
```

Upload only the generated `.dmg` to the maintainer's verified, restricted private account. Confirm both the signed-in account and owner-only access before and after uploading. Do not use a connected account merely because a tool is available. Retain the actual external file identity in a private receipt, never in the public repository.

Download the real external copy through that same authorized account. Verify its hash against the staged image, keep the downloaded copy owner-only, and restore-check it:

```sh
python3 tools/backup-upload-key.py verify \
  --directory .local/key-backups/NEW_BACKUP \
  --downloaded /absolute/path/to/private/downloaded-copy.dmg
```

The verifier checks encryption and exact file hashes, mounts read-only, matches the public certificate, signs an inert temporary JAR using the restored private key and verifies the signature strictly. It then ejects the temporary volume. It does not run the JAR, upload it or replace the original key. Passwords pass through process input/environment, not command arguments or printed results.

The tool verifies the supplied copy; the operator must separately establish that it came from the external destination and confirm independent recovery-password custody. A local restore test alone is not an off-device backup. Do not set `externalBackupVerified` until those distinct checks are recorded. Play registration is a separate field and remains unchanged by backup work.

A recovery on another Mac uses the saved outer password to open the image. Copy its four files to a private directory and confirm the certificate before use. The image contains the original PKCS#12 password, so recovery does not depend on the lost original working folder. Keep the original identity and encrypted backup intact during testing. A native `.dmg` assumes access to macOS for this recovery procedure.
