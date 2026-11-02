#!/usr/bin/env bash
# Executed only inside the pinned package-builder, never on the Android device.
set -euo pipefail
cd /home/builder/termux-packages
if [[ $(id -u) == 0 ]]; then
  # QEMU user emulation cannot perform sudo's setuid transition. Initialize only
  # our two dedicated build volumes, then drop to the normal builder account.
  mkdir -p /data /home/builder/.termux-build
  chown builder:builder /data /home/builder/.termux-build
  exec runuser -u builder -- bash "$0" "$@"
fi
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || {
  echo 'z8 runtime: expected Linux x86_64 builder' >&2; exit 2;
}
[[ $(id -un) == builder ]] || { echo 'Expected builder account' >&2; exit 2; }
profile=${1:?profile required}
case "$profile" in
  core) additions=tmux,proot ;;
  workspace) additions=tmux,proot,proot-distro ;;
  *) echo 'Unknown bootstrap profile' >&2; exit 64 ;;
esac

# Volumes are dedicated to this source/overlay/image fingerprint. No host /data
# or Docker socket is mounted, and no host sysctl is changed.
[[ -w /data && -w /home/builder/.termux-build ]]
export TERMUX_INSTALL_DEPS=false
export TERMUX_PKG_MAKE_PROCESSES=${Z8_BUILD_JOBS:-4}
export SOURCE_DATE_EPOCH=${Z8_SOURCE_DATE_EPOCH:?source date required}
export TZ=UTC
export LC_ALL=C.UTF-8
unset TERMUX_PACKAGES_OFFLINE TERMUX_NDK_VERSION_NUM TERMUX_NDK_REVISION

# Validate the actual derived identity/toolchain before any package build.
set +u
. scripts/properties.sh
set -u
[[ $TERMUX_APP__PACKAGE_NAME == dev.devsigner.z8 ]]
[[ $TERMUX_PREFIX == /data/data/dev.devsigner.z8/files/usr ]]
[[ $TERMUX_REPO_APP__PACKAGE_NAME == com.termux ]]
[[ $TERMUX_NDK_VERSION == 30 ]]
grep -q '^Pkg.Revision = 30\.' "$NDK/source.properties"
"$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/clang" --version

# Optional dependency reuse is restricted by the host preparer to the identical
# source lock, image, recipes and published .deb checksums. No maintainer scripts
# run, no repository is enabled, and the changed PRoot package is never seeded.
if [[ -f z8-dependency-seed.json ]]; then
  python3 - <<'PY'
import hashlib, json, pathlib, subprocess
seed = json.loads(pathlib.Path('z8-dependency-seed.json').read_text())
assert seed['schemaVersion'] == 1 and seed['rebuiltPackages'] == ['proot']
markers = pathlib.Path('/data/data/.built-packages')
markers.mkdir(parents=True, exist_ok=True)
for record in seed['packages']:
    archive = pathlib.Path('output') / record['archive']
    assert archive.name == record['archive'] and not archive.is_symlink()
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == record['sha256']
    name = subprocess.check_output(['dpkg-deb', '-f', str(archive), 'Package'], text=True).strip()
    version = subprocess.check_output(['dpkg-deb', '-f', str(archive), 'Version'], text=True).strip()
    arch = subprocess.check_output(['dpkg-deb', '-f', str(archive), 'Architecture'], text=True).strip()
    assert name != 'proot' and '/' not in name and arch in ('aarch64', 'all')
    payload = subprocess.Popen(['dpkg-deb', '--fsys-tarfile', str(archive)], stdout=subprocess.PIPE)
    try:
        subprocess.run(['tar', '-x', '--no-same-owner', '--no-overwrite-dir', '-C', '/', '-f', '-'],
                       stdin=payload.stdout, check=True)
    finally:
        payload.stdout.close()
    assert payload.wait() == 0
    (markers / name).write_text(version + '\n')
print('Verified source-built dependency packages reused:', len(seed['packages']), flush=True)
PY
fi

# Reuse only this fingerprint's source-built dependency markers. No -i/-I or
# repository bootstrap generator is used. Failed builds can be resumed.
bash scripts/build-bootstraps.sh --architectures aarch64 --add "$additions"
test -s bootstrap-aarch64.zip
