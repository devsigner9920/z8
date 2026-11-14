"""Pinned guest Node distribution validation; no host package installation."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('z8_node', ROOT / 'runtime/guest/install-node.py')
node = importlib.util.module_from_spec(spec)
spec.loader.exec_module(node)


class NodeInstallerTests(unittest.TestCase):
    def test_selected_release_uses_official_24_lts_index_and_exact_checksum(self):
        item = {'version': 'v24.22.0', 'npm': '11.20.0', 'lts': 'Krypton', 'files': ['linux-arm64']}
        sums = ('a' * 64 + '  node-v24.22.0-linux-arm64.tar.xz\n').encode()
        def fetch(url, limit):
            self.assertIn(url, ('https://nodejs.org/dist/index.json', 'https://nodejs.org/dist/v24.22.0/SHASUMS256.txt'))
            return json.dumps([item]).encode() if url.endswith('index.json') else sums
        with patch.object(node, 'metadata', side_effect=fetch):
            result = node.selected_lock('v24.22.0')
            self.assertEqual(result['sha256'], 'a' * 64)
            self.assertEqual(result['checksumsSha256'], hashlib.sha256(sums).hexdigest())
            self.assertTrue(result['selectedRelease'])
            item['lts'] = False
            with self.assertRaises(ValueError): node.selected_lock('v24.22.0')
            item['lts'] = 'Krypton'; item['files'] = ['linux-x64']
            with self.assertRaises(ValueError): node.selected_lock('v24.22.0')
            item['files'] = ['linux-arm64']; sums += sums
            with self.assertRaises(ValueError): node.selected_lock('v24.22.0')
        with patch.object(node, 'metadata') as fetch:
            for value in ('v26.0.0', 'v24.01.0', 'latest', 'v24.22.0;id', '../v24.22.0'):
                with self.assertRaises(ValueError): node.selected_lock(value)
            fetch.assert_not_called()

    def test_official_redirect_cannot_downgrade_or_leave_distribution_host(self):
        for target in ('http://nodejs.org/dist/x', 'https://evil.invalid/dist/x', 'https://nodejs.org/other/x'):
            with self.assertRaises(ValueError):
                node.OfficialRedirect().redirect_request(None, None, 302, '', {}, target)

    def test_modified_managed_node_and_custom_current_are_not_updated(self):
        data = node.lock_data(ROOT / 'runtime/guest/node.lock.json')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'node'; version = root / data['version']; version.mkdir(parents=True)
            binary = version / 'node'; binary.write_bytes(b'validated original')
            node.write_receipt(version, data); node.verify_managed(version)
            receipt = json.loads((version / '.z8-node-receipt.json').read_text())
            self.assertEqual((receipt['manager'], receipt['version'], receipt['npm']), ('z8-node-v1', data['version'], data['npm']))
            current = root / 'current'; current.symlink_to(data['version'])
            binary.write_bytes(b'user change')
            newer = dict(data, version='v24.22.0', selectedRelease=True)
            with patch.object(node, 'download') as download, self.assertRaisesRegex(ValueError, 'Preserving modified'):
                node._install_locked(root, Path(temporary) / 'bin', newer)
            download.assert_not_called(); self.assertEqual(current.readlink(), Path(data['version']))
            self.assertEqual(binary.read_bytes(), b'user change')
            current.unlink(); current.symlink_to('../user-node')
            with self.assertRaisesRegex(ValueError, 'unrecognized'):
                node._install_locked(root, Path(temporary) / 'bin', newer)
            self.assertEqual(current.readlink(), Path('../user-node'))

    def test_legacy_node_requires_exact_archive_bytes_before_receipt_or_update(self):
        data = node.lock_data(ROOT / 'runtime/guest/node.lock.json')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); installed = root / data['version']; installed.mkdir()
            (installed / 'node').write_bytes(b'original')
            def extract(_archive, target, _prefix):
                target.mkdir(parents=True); (target / 'node').write_bytes(b'original'); return target
            with patch.object(node, 'download') as download, patch.object(node, 'extract', side_effect=extract):
                node.verify_managed(installed)
                self.assertEqual(download.call_args.args[2], data['sha256'])
                (installed / 'node').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'modified legacy'):
                    node.verify_managed(installed)
            self.assertFalse((installed / '.z8-node-receipt.json').exists())

    def test_user_selection_changed_during_download_is_preserved(self):
        old = node.lock_data(ROOT / 'runtime/guest/node.lock.json')
        new = dict(old, version='v24.22.0', selectedRelease=True,
            url='https://nodejs.org/dist/v24.22.0/node-v24.22.0-linux-arm64.tar.xz')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'node'; prior = root / old['version']; prior.mkdir(parents=True)
            (prior / 'node').write_bytes(b'original'); node.write_receipt(prior, old)
            current = root / 'current'; current.symlink_to(old['version'])
            def download(_url, target, _hash, _limit):
                target.write_text(new['sha256'] + '  node-v24.22.0-linux-arm64.tar.xz\n')
            def extract(_archive, target, _prefix):
                target.mkdir(parents=True); (target / 'node').write_bytes(b'new')
                current.unlink(); current.symlink_to('../user-selected-node'); return target
            with patch.object(node, 'download', side_effect=download), patch.object(node, 'extract', side_effect=extract), patch.object(node, 'versions'):
                with self.assertRaisesRegex(ValueError, 'selection changed'):
                    node._install_locked(root, Path(temporary) / 'bin', new)
            self.assertEqual(current.readlink(), Path('../user-selected-node'))
            self.assertEqual((prior / 'node').read_bytes(), b'original')

    def test_lock_and_host_guard(self):
        lock = node.lock_data(ROOT / 'runtime/guest/node.lock.json')
        self.assertEqual(lock['version'], 'v24.21.0')
        for url in ('http://nodejs.org/dist/a', 'https://evil.example/dist/a', 'https://nodejs.org@evil.example/dist/a'):
            with self.assertRaises(ValueError):
                node.official(url)
        with patch.object(node.platform, 'system', return_value='Darwin'):
            with self.assertRaisesRegex(ValueError, 'marked ARM64'):
                node.install()

    def test_download_hash_size_and_retry(self):
        class Response(io.BytesIO):
            def geturl(self):
                return 'https://nodejs.org/dist/fixture'
        payload = b'archive-fixture'
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'download'
            opener = types.SimpleNamespace(open=unittest.mock.Mock(side_effect=[OSError('interrupted'), Response(payload)]))
            with patch.object(node.urllib.request, 'build_opener', return_value=opener), patch.object(node.time, 'sleep'):
                node.download('https://nodejs.org/dist/fixture', output, digest, 100)
                self.assertEqual(output.read_bytes(), payload)
            with patch.object(node.urllib.request, 'build_opener', return_value=types.SimpleNamespace(open=lambda *a, **k: Response(payload))):
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    node.download('https://nodejs.org/dist/fixture', output, '0' * 64, 100)
            with patch.object(node.urllib.request, 'build_opener', return_value=types.SimpleNamespace(open=lambda *a, **k: Response(payload))):
                with self.assertRaisesRegex(ValueError, 'size limit'):
                    node.download('https://nodejs.org/dist/fixture', output, digest, 2)

    def archive(self, path, extra=(), arm64=True):
        header = b'\x7fELF\x02\x01' + b'\0' * 12 + (183 if arm64 else 62).to_bytes(2, 'little')
        with tarfile.open(path, 'w:xz') as archive:
            file = tarfile.TarInfo('node-v24.21.0-linux-arm64/bin/node')
            file.size = len(header); file.mode = 0o755
            archive.addfile(file, io.BytesIO(header))
            for name, target in extra:
                file = tarfile.TarInfo(name)
                file.type = tarfile.SYMTYPE; file.linkname = target
                archive.addfile(file)

    def test_extract_symlink_traversal_and_architecture(self):
        prefix = 'node-v24.21.0-linux-arm64'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'node.tar.xz'
            self.archive(source, [(prefix + '/bin/npm', '../lib/npm.js')])
            target = node.extract(source, root / 'valid', prefix)
            self.assertTrue((target / 'bin/node').is_file())
            for name, link in ((prefix + '/escape', '../../outside'), (prefix + '/escape', '/outside'), ('../escape', 'x')):
                self.archive(source, [(name, link)])
                with self.assertRaises(ValueError):
                    node.extract(source, root / 'bad', prefix)
            self.archive(source, arm64=False)
            with self.assertRaisesRegex(ValueError, 'ARM64'):
                node.extract(source, root / 'wrong-arch', prefix)

    def test_version_probes_fail_closed(self):
        lock = node.lock_data(ROOT / 'runtime/guest/node.lock.json')
        with patch.object(node.subprocess, 'check_output', side_effect=['v24.21.0\n', '11.19.0\n']):
            node.versions(Path('/fixture'), lock)
        with patch.object(node.subprocess, 'check_output', return_value='v18.0.0\n'):
            with self.assertRaisesRegex(ValueError, 'differs'):
                node.versions(Path('/fixture'), lock)
        with patch.object(node.subprocess, 'check_output', side_effect=subprocess.TimeoutExpired('node', 30)):
            with self.assertRaises(subprocess.TimeoutExpired):
                node.versions(Path('/fixture'), lock)

    def test_resume_published_version_restores_missing_links_without_download(self):
        lock = node.lock_data(ROOT / 'runtime/guest/node.lock.json')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'node'
            root.mkdir()
            (root / lock['version']).mkdir()
            bindir = Path(temporary) / 'bin'
            bindir.mkdir()
            # A hard kill after the version rename / first command link must be
            # recoverable without another network fetch or changing the version.
            (bindir / 'node').symlink_to('/opt/z8/node/current/bin/node')
            with patch.object(node, 'versions') as verify, patch.object(node, 'verify_managed'), patch.object(node, 'download') as download:
                node._install_locked(root, bindir, lock)
                verify.assert_called_once_with(root / lock['version'], lock)
                download.assert_not_called()
            self.assertEqual((root / 'current').readlink(), Path(lock['version']))
            for name in ('node', 'npm', 'npx'):
                self.assertEqual((bindir / name).readlink(), Path('/opt/z8/node/current/bin/' + name))

    def test_resume_does_not_trust_invalid_published_version_or_replace_user_command(self):
        lock = node.lock_data(ROOT / 'runtime/guest/node.lock.json')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'node'
            root.mkdir()
            (root / lock['version']).mkdir()
            bindir = Path(temporary) / 'bin'
            bindir.mkdir()
            with patch.object(node, 'versions', side_effect=ValueError('failed validation')), patch.object(node, 'download') as download:
                with self.assertRaisesRegex(ValueError, 'failed validation'):
                    node._install_locked(root, bindir, lock)
                download.assert_not_called()
            self.assertFalse((root / 'current').exists())
            (bindir / 'npm').write_text('user-owned command')
            with patch.object(node, 'versions'), patch.object(node, 'verify_managed'), patch.object(node, 'download') as download:
                with self.assertRaisesRegex(ValueError, 'Preserving existing'):
                    node._install_locked(root, bindir, lock)
                download.assert_not_called()
            self.assertEqual((bindir / 'npm').read_text(), 'user-owned command')

    def test_stale_temporary_pointer_from_killed_process_does_not_block_resume(self):
        lock = node.lock_data(ROOT / 'runtime/guest/node.lock.json')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'node'
            root.mkdir()
            (root / lock['version']).mkdir()
            stale = root / ('.current-' + str(node.os.getpid()))
            stale.symlink_to(lock['version'])
            with patch.object(node, 'versions'), patch.object(node, 'verify_managed'), patch.object(node, 'download') as download:
                node._install_locked(root, Path(temporary) / 'bin', lock)
                download.assert_not_called()
            self.assertEqual((root / 'current').readlink(), Path(lock['version']))
            self.assertTrue(stale.is_symlink())

    def test_interrupted_node_staging_cleanup_requires_matching_owner_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'node'
            root.mkdir()
            outside = Path(temporary) / 'preserved'
            outside.mkdir()
            (outside / 'source').write_text('user source')
            owned = root / '.install-abcdefgh'
            owned.mkdir()
            (owned / '.z8-node-staging').write_text('z8-node-staging-v1\n' + owned.name + '\n')
            (owned / 'partial-archive').write_bytes(b'partial')
            (owned / 'link').symlink_to(outside, target_is_directory=True)
            unknown = root / '.install-ijklmnop'
            unknown.mkdir()
            (unknown / 'download').write_bytes(b'preserve')
            linked = root / '.install-qrstuvwx'
            linked.symlink_to(outside, target_is_directory=True)
            node._remove_interrupted_staging(root)
            self.assertFalse(owned.exists())
            self.assertEqual((outside / 'source').read_text(), 'user source')
            self.assertEqual((unknown / 'download').read_bytes(), b'preserve')
            self.assertTrue(linked.is_symlink())

    def test_failed_tool_that_prints_version_is_not_ready(self):
        source = (ROOT / 'runtime/guest/probe-tools.sh').read_text()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for command, code in {'python3': 'printf "Python 3.12\\n"; exit 1', 'node': 'printf "v24.21.0\\n"; exit 0'}.items():
                path = root / command
                path.write_text('#!/bin/bash\n' + code + '\n'); path.chmod(0o755)
            timeout = root / 'timeout'
            timeout.write_text('#!/bin/bash\nshift 3\nexec "$@"\n'); timeout.chmod(0o755)
            source = '\n'.join('export PATH=' + str(root) if line.startswith('export PATH=') else line for line in source.splitlines())
            result = subprocess.run(['/bin/bash', '-c', source], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            actual = dict(line.split('\t', 1) for line in result.stdout.splitlines())
            # A present command that fails is unknown/broken, not absent.
            self.assertEqual(actual['python'], '?')
            self.assertEqual(actual['node'], 'v24.21.0')
            self.assertEqual(actual['codex'], '-')
            single = subprocess.run(['/bin/bash', '-c', source, 'probe', 'node'], capture_output=True, text=True)
            self.assertEqual(single.stdout, 'node\tv24.21.0\nnpm\t-\n')

    def test_aggregate_probe_has_one_deadline(self):
        source = (ROOT / 'runtime/guest/probe-tools.sh').read_text()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            timeout = root / 'timeout'
            timeout.write_text('#!/bin/bash\n/bin/sleep 2\nprintf "slow-version\\n"\n'); timeout.chmod(0o755)
            python = root / 'python3'
            python.write_text('#!/bin/bash\nexit 0\n'); python.chmod(0o755)
            # Reduce the production deadline for a bounded integration fixture.
            source = source.replace('SECONDS + 90', 'SECONDS + 1')
            source = '\n'.join('export PATH=' + str(root) if line.startswith('export PATH=') else line for line in source.splitlines())
            result = subprocess.run(['/bin/bash', '-c', source], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 124)
            self.assertEqual(sum('slow-version' in line for line in result.stdout.splitlines()), 1)


    def test_tool_timeout_is_unknown_not_missing(self):
        source = (ROOT / 'runtime/guest/probe-tools.sh').read_text()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, code in {'timeout': 'exit 124', 'node': 'exit 0'}.items():
                executable = root / name
                executable.write_text('#!/bin/bash\n' + code + '\n'); executable.chmod(0o755)
            source = '\n'.join('export PATH=' + str(root) if line.startswith('export PATH=') else line for line in source.splitlines())
            result = subprocess.run(['/bin/bash', '-c', source, 'probe', 'node'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, 'node\t?\nnpm\t-\n')
