#!/usr/bin/env python3
"""Install the pinned build tools into .local; never replace host tools."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'
LOCK = json.loads((ROOT / 'tools/toolchain.lock.json').read_text())


def download(item, name, algorithm):
    target = LOCAL / 'downloads' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    def valid():
        return target.exists() and hashlib.file_digest(target.open('rb'), algorithm).hexdigest() == item[algorithm]
    if not valid():
        partial = target.with_suffix(target.suffix + '.partial')
        subprocess.run(['curl', '--fail', '--location', '--retry', '3', '--output', str(partial), item['url']], check=True)
        partial.replace(target)
    if not valid():
        raise RuntimeError(f'Checksum mismatch: {target}')
    return target


def main():
    if sys.version_info < (3, 12):
        sys.exit('Python 3.12 or newer is required for verified downloads and safe tar extraction.')
    if (platform.system(), platform.machine()) != ('Darwin', 'arm64'):
        sys.exit('This lock is for macOS ARM64. Supply a separate host lock before installing.')
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jdk_job = pool.submit(download, LOCK['jdk'], 'jdk.tar.gz', 'sha256')
        cli_job = pool.submit(download, LOCK['commandLineTools'], 'android-commandline.zip', 'sha1')
        jdk_archive, cli_archive = jdk_job.result(), cli_job.result()
    jdk = LOCAL / 'jdk'
    if not (jdk / 'Contents/Home/bin/java').exists():
        staging = LOCAL / 'jdk-extract'
        staging.mkdir(exist_ok=True)
        with tarfile.open(jdk_archive) as archive:
            archive.extractall(staging, filter='data')
        directories = list(staging.iterdir())
        if len(directories) != 1:
            raise RuntimeError('Unexpected JDK archive layout')
        directories[0].rename(jdk)
        staging.rmdir()
    sdk = LOCAL / 'android-sdk'
    cli = sdk / 'cmdline-tools/latest'
    if not (cli / 'bin/sdkmanager').exists():
        staging = LOCAL / 'android-cli-extract'
        staging.mkdir(exist_ok=True)
        # zipfile does not restore executable permissions; restore them explicitly.
        with zipfile.ZipFile(cli_archive) as archive:
            archive.extractall(staging)
        cli.parent.mkdir(parents=True, exist_ok=True)
        (staging / 'cmdline-tools').rename(cli)
        staging.rmdir()
    for executable in (cli / 'bin').iterdir():
        executable.chmod(0o755)
    env = os.environ.copy()
    env['JAVA_HOME'] = str(jdk / 'Contents/Home')
    env['ANDROID_HOME'] = str(sdk)
    env['ANDROID_USER_HOME'] = str(LOCAL / 'android-user')
    env['PATH'] = str(jdk / 'Contents/Home/bin') + os.pathsep + env['PATH']
    manager = str(cli / 'bin/sdkmanager')
    subprocess.run([manager, '--sdk_root=' + str(sdk), '--licenses'], input='y\n' * 100, text=True, env=env, check=True)
    subprocess.run([manager, '--sdk_root=' + str(sdk), *LOCK['sdkPackages']], env=env, check=True)
    subprocess.run([str(jdk / 'Contents/Home/bin/java'), '-version'], check=True)
    print('Toolchain ready in', LOCAL, flush=True)


if __name__ == '__main__':
    main()
