#!/usr/bin/env python3
"""Project-local Linux build backend for ARM Macs; never part of the Android app."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'
LIMA_VERSION = '2.2.1'
LIMA_SHA256 = '9e9eacce88f37e185c346bad73aa6136f738d8cdf8c3bb23cd42b071824bc66e'
IMAGE_URL = 'https://cloud-images.ubuntu.com/minimal/releases/resolute/release-20261002/ubuntu-26.04-minimal-cloudimg-arm64.img'
IMAGE_SHA256 = '768d6339844cb8a86c7287e9ac7b9d71ddc391531ad2521b72d22f0833660b01'
NAME = 'z8-builder'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true', help='Download Lima and create/start the dedicated 8 GiB / 6 CPU / 80 GiB VM')
    args = parser.parse_args()
    if (platform.system(), platform.machine()) != ('Darwin', 'arm64'):
        parser.error('This optional backend is for ARM Macs; use Docker directly on Linux.')
    binary = LOCAL / 'lima/bin/limactl'
    env = dict(os.environ, LIMA_HOME=str(LOCAL / 'linux-vm'))
    if not args.install:
        if not binary.is_file():
            parser.error('Lima is not installed. Use --install to provision it.')
        subprocess.run([str(binary), 'list', '--json'], env=env, check=True)
        return
    LOCAL.mkdir(exist_ok=True)
    archive = LOCAL / f'downloads/lima-{LIMA_VERSION}-Darwin-arm64.tar.gz'
    archive.parent.mkdir(exist_ok=True)
    if not archive.is_file():
        pending = archive.with_suffix('.part')
        subprocess.run(['curl', '-fL', '--retry', '3', f'https://github.com/lima-vm/lima/releases/download/v{LIMA_VERSION}/{archive.name}', '-o', str(pending)], check=True)
        if hashlib.sha256(pending.read_bytes()).hexdigest() != LIMA_SHA256:
            raise RuntimeError('Lima archive checksum mismatch; refusing installation')
        pending.replace(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != LIMA_SHA256:
        raise RuntimeError('Cached Lima archive checksum mismatch')
    if not binary.is_file():
        (LOCAL / 'lima').mkdir(exist_ok=True)
        with tarfile.open(archive) as source:
            source.extractall(LOCAL / 'lima', filter='data')
    config = LOCAL / 'z8-builder.yaml'
    config.write_text(f'''# Build-only VM. No Mac home or credentials are shared.
vmType: vz
arch: aarch64
cpus: 6
memory: 8GiB
disk: 80GiB
images:
- location: {IMAGE_URL}
  arch: aarch64
  digest: sha256:{IMAGE_SHA256}
mountType: virtiofs
mounts:
- location: {json.dumps(str(ROOT))}
  writable: true
containerd:
  system: false
  user: false
vmOpts:
  vz:
    rosetta:
      enabled: false
      binfmt: false
param:
  internal_netplanOptional: "true"
provision:
- mode: system
  script: |
    #!/bin/bash
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends docker.io qemu-user-binfmt binfmt-support ca-certificates
    systemctl enable --now docker
    systemctl restart systemd-binfmt
probes:
- script: |
    #!/bin/sh
    sudo docker info >/dev/null
  hint: Check guest /var/log/cloud-init-output.log.
''')
    existing = LOCAL / f'linux-vm/{NAME}/lima.yaml'
    command = [str(binary), 'start', '--tty=false']
    command += [NAME] if existing.is_file() else [f'--name={NAME}', str(config)]
    subprocess.run(command, env=env, check=True)
    wrapper = LOCAL / 'bin/docker-z8'
    wrapper.parent.mkdir(exist_ok=True)
    wrapper.write_text('#!/bin/sh\nset -eu\n'
        + f'z8_repo_dir={shlex.quote(str(ROOT))}\n'
        + 'export LIMA_HOME="$z8_repo_dir/.local/linux-vm"\n'
        + 'exec "$z8_repo_dir/.local/lima/bin/limactl" shell z8-builder -- sudo docker "$@"\n')
    wrapper.chmod(0o755)
    subprocess.run([str(wrapper), 'version'], check=True)
    print(f'Use Z8_DOCKER={wrapper} with tools/build-runtime.sh. The Android app does not use this VM.')


if __name__ == '__main__':
    main()
