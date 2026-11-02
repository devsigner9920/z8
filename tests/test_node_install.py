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
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('z8_node', ROOT / 'runtime/guest/install-node.py')
node = importlib.util.module_from_spec(spec)
spec.loader.exec_module(node)


class NodeInstallerTests(unittest.TestCase):
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
            with patch.object(node.urllib.request, 'urlopen', side_effect=[OSError('interrupted'), Response(payload)]), patch.object(node.time, 'sleep'):
                node.download('https://nodejs.org/dist/fixture', output, digest, 100)
                self.assertEqual(output.read_bytes(), payload)
            with patch.object(node.urllib.request, 'urlopen', return_value=Response(payload)):
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    node.download('https://nodejs.org/dist/fixture', output, '0' * 64, 100)
            with patch.object(node.urllib.request, 'urlopen', return_value=Response(payload)):
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
            with patch.object(node, 'versions') as verify, patch.object(node, 'download') as download:
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
            with patch.object(node, 'versions'), patch.object(node, 'download') as download:
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
            with patch.object(node, 'versions'), patch.object(node, 'download') as download:
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
            self.assertEqual(actual['python'], '-')
            self.assertEqual(actual['node'], 'v24.21.0')
            self.assertEqual(actual['codex'], '-')
            single = subprocess.run(['/bin/bash', '-c', source, 'probe', 'node'], capture_output=True, text=True)
            self.assertEqual(single.stdout, 'node\tv24.21.0\n')

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
            self.assertEqual(result.stdout, 'node\t?\n')
