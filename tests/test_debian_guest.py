"""Immutable Debian OCI input, safe normalization and legacy lock boundaries."""
import base64
import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('debian_guest', ROOT / 'tools/prepare-guest.py')
guest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guest)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class DebianGuestInputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        shutil.copytree(ROOT / 'runtime', self.root / 'runtime')
        self.lock_path = self.root / 'runtime/guest/image.lock.json'
        self.lock = json.loads(self.lock_path.read_text())
        self.os_release = b'ID=debian\nVERSION_ID="13"\nVERSION_CODENAME=trixie\nDEBIAN_VERSION_FULL=13.7\n'
        self.apt_sources = b'Types: deb\nURIs: http://deb.debian.org/debian\nSuites: trixie\nSigned-By: /usr/share/keyrings/debian-archive-keyring.pgp\n'
        self.notice = b'Upstream package copyright and licensing notice.\n'
        self.bashrc = b'# original Debian bash startup\nshopt -s checkwinsize\n'
        payloads = {'usr/bin/bash': b'fixture-bash', 'usr/bin/env': b'fixture-env',
            'usr/lib/os-release': self.os_release, 'etc/debian_version': b'13.7\n',
            'etc/apt/sources.list.d/debian.sources': self.apt_sources,
            'usr/share/doc/fixture/copyright': self.notice, 'etc/bash.bashrc': self.bashrc}
        parents = {str(parent) + '/' for name in payloads for parent in Path(name).parents if str(parent) != '.'}
        tar_bytes = io.BytesIO()
        with tarfile.open(fileobj=tar_bytes, mode='w') as archive:
            for name in sorted(parents):
                entry = tarfile.TarInfo(name); entry.type = tarfile.DIRTYPE; entry.mode = 0o755
                archive.addfile(entry)
            for name, data in sorted(payloads.items()):
                entry = tarfile.TarInfo(name); entry.mode = 0o644; entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        self.plain = tar_bytes.getvalue()
        self.compressed = gzip.compress(self.plain, mtime=0)
        self.lock['source'].update(sha256=digest(self.compressed), bytes=len(self.compressed), ociRootfsDiffId=digest(self.plain))
        self.cache = self.root / '.local/guest-cache' / ('debian-' + self.lock['source']['sha256'])
        self.cache.mkdir(parents=True)
        self.source = self.cache / 'rootfs.tar.gz'; self.source.write_bytes(self.compressed)
        self.index_path = self.cache / 'index.json'
        self.config = {'os': 'linux', 'architecture': 'arm64', 'variant': 'v8',
            'rootfs': {'type': 'layers', 'diff_ids': ['sha256:' + digest(self.plain)]}}
        self.manifest = {'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.manifest.v1+json',
            'layers': [{'mediaType': 'application/vnd.oci.image.layer.v1.tar+gzip',
                'digest': 'sha256:' + digest(self.compressed), 'size': len(self.compressed)}]}
        self.platform = {'os': 'linux', 'architecture': 'arm64', 'variant': 'v8'}
        self.write_oci()
        self.patch_root = mock.patch.object(guest, 'ROOT', self.root)
        self.patch_lock = mock.patch.object(guest, 'LOCK_PATH', self.lock_path)
        self.patch_root.start(); self.patch_lock.start()
        self.addCleanup(self.patch_root.stop); self.addCleanup(self.patch_lock.stop)

    def write_oci(self):
        def descriptor(value, kind):
            data = (json.dumps(value, separators=(',', ':')) + '\n').encode()
            return {'mediaType': kind, 'digest': 'sha256:' + digest(data), 'size': len(data),
                'data': base64.b64encode(data).decode()}
        config = descriptor(self.config, 'application/vnd.oci.image.config.v1+json')
        self.manifest['config'] = config
        manifest = descriptor(self.manifest, 'application/vnd.oci.image.manifest.v1+json')
        manifest['platform'] = self.platform
        index = {'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.index.v1+json', 'manifests': [manifest]}
        encoded = (json.dumps(index) + '\n').encode()
        self.index_path.write_bytes(encoded)
        self.lock['source'].update(ociIndexSha256=digest(encoded), ociIndexBytes=len(encoded),
            ociConfigSha256=config['digest'].split(':')[1], ociManifestSha256=manifest['digest'].split(':')[1])
        self.lock_path.write_text(json.dumps(self.lock, indent=2) + '\n')

    def test_default_debian_and_explicit_legacy_ubuntu_lock(self):
        self.assertEqual(guest.read_lock()['distribution'], 'debian')
        legacy = ROOT / 'runtime/guest/legacy/ubuntu-24.04.5.lock.json'
        old = guest.read_lock(legacy)
        self.assertEqual(old['distribution'], 'ubuntu')
        self.assertEqual(old['source']['sha256'], 'a91d5a93010193712d346d761372b7c9db6dfcf093893161c64ca107f05914f2')
        with self.assertRaisesRegex(guest.GuestError, 'requires --lock'):
            guest.build(self.root / 'historical.json')

    def test_oci_graph_and_both_layer_hashes_then_safe_build(self):
        guest.verify_debian_oci(self.index_path, self.source, self.lock)
        result = guest.build()
        path = Path(result['manifest'])
        self.assertIn('debian-13.7-arm64', str(path))
        archive, manifest = guest.verify_manifest(path)
        self.assertEqual(manifest['sourceIndexes'], self.lock['sourceIndexes'])
        with zipfile.ZipFile(archive) as output:
            for name, expected in [('usr/lib/os-release', self.os_release),
                    ('etc/apt/sources.list.d/debian.sources', self.apt_sources),
                    ('usr/share/doc/fixture/copyright', self.notice)]:
                self.assertEqual(output.read(name), expected)
            self.assertTrue(output.read('etc/bash.bashrc').startswith(self.bashrc + b'\n# z8 interactive defaults'))
            self.assertEqual(output.read('usr/local/lib/z8/install-ai.sh'), (ROOT/'runtime/guest/install-ai.sh').read_bytes())
        self.assertFalse(result['packagesProvisioned'])
        self.assertEqual(result['deviceExecution'], 'NOT_TESTED')
        with self.assertRaisesRegex(guest.GuestError, 'pinned image'):
            guest.verify_manifest(path, ROOT / 'runtime/guest/legacy/ubuntu-24.04.5.lock.json')

    def test_mutated_pinned_bytes_cannot_enter_normalization(self):
        for path in (self.index_path, self.source):
            with self.subTest(path=path.name):
                saved = path.read_bytes(); path.write_bytes(saved + b'tamper')
                with mock.patch.object(guest, 'normalize') as normalize:
                    with self.assertRaises(guest.GuestError):
                        guest.build()
                    normalize.assert_not_called()
                path.write_bytes(saved)

    def test_self_consistent_oci_hashes_do_not_bypass_architecture_or_layer_binding(self):
        for kind in ('platform', 'config-architecture', 'layer-hash', 'layer-size', 'uncompressed-hash'):
            with self.subTest(kind=kind):
                config, manifest, platform, lock = copy.deepcopy((self.config, self.manifest, self.platform, self.lock))
                if kind == 'platform': self.platform['architecture'] = 'amd64'
                if kind == 'config-architecture': self.config['architecture'] = 'amd64'
                if kind == 'layer-hash': self.manifest['layers'][0]['digest'] = 'sha256:' + '0' * 64
                if kind == 'layer-size': self.manifest['layers'][0]['size'] += 1
                if kind == 'uncompressed-hash':
                    self.config['rootfs']['diff_ids'] = ['sha256:' + '0' * 64]
                    self.lock['source']['ociRootfsDiffId'] = '0' * 64
                self.write_oci()
                with self.assertRaises(guest.GuestError):
                    guest.verify_debian_oci(self.index_path, self.source, self.lock)
                self.config, self.manifest, self.platform, self.lock = config, manifest, platform, lock
                self.write_oci()

    def test_embedded_manifest_digest_is_checked_even_with_new_outer_hash(self):
        data = json.loads(self.index_path.read_text())
        manifest = data['manifests'][0]
        manifest['data'] = base64.b64encode(base64.b64decode(manifest['data']) + b' ').decode()
        encoded = json.dumps(data).encode()
        self.index_path.write_bytes(encoded)
        self.lock['source'].update(ociIndexSha256=digest(encoded), ociIndexBytes=len(encoded))
        with self.assertRaisesRegex(guest.GuestError, 'embedded descriptor'):
            guest.verify_debian_oci(self.index_path, self.source, self.lock)

    def test_pins_reject_moving_revisions_foreign_urls_and_duplicate_source_indexes(self):
        mutations = [lambda lock: lock['source'].update(url=lock['source']['url'].replace(lock['provenance']['artifactCommit'], 'master')),
            lambda lock: lock['source'].update(ociIndexSha256='abc'),
            lambda lock: lock['source'].update(bytes=True),
            lambda lock: lock['sourceIndexes'][0].update(url='https://example.com/Sources.xz'),
            lambda lock: lock['sourceIndexes'].__setitem__(0, lock['sourceIndexes'][1])]
        for mutation in mutations:
            value = copy.deepcopy(self.lock); mutation(value); self.lock_path.write_text(json.dumps(value))
            with self.assertRaises(guest.GuestError): guest.read_lock()
        self.assertFalse(guest.allowed_download_url('https://raw.githubusercontent.com/attacker/repo/a/rootfs.tar.gz'))
        self.assertFalse(guest.allowed_download_url('http://cdimage.ubuntu.com/file'))

    def test_false_debian_release_identity_prevents_artifact_publication(self):
        self.lock['release'] = '13.8'; self.lock_path.write_text(json.dumps(self.lock))
        with self.assertRaisesRegex(guest.GuestError, 'release identity'):
            guest.build()
        self.assertEqual(list((self.root/'artifacts/guest').glob('*/*/manifest.json')), [])

    def test_redirect_cannot_visit_http_or_foreign_hosts_before_final_hash_check(self):
        handler = guest.OfficialGuestRedirect()
        for url in ('http://cdimage.ubuntu.com/file', 'https://example.com/rootfs.tar.gz',
                    'https://raw.githubusercontent.com/attacker/repo/manifest.json'):
            with self.subTest(url=url), self.assertRaisesRegex(guest.GuestError, 'redirect'):
                handler.redirect_request(None, None, 302, 'Found', {}, url)


if __name__ == '__main__':
    unittest.main()
