import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('native_alignment', ROOT / 'tools/native_alignment.py')
native = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(native)


def elf(*, alignment=16384, offset=0, address=0, machine=183, kind=1):
    data = bytearray(120)
    data[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<H', data, 18, machine)
    struct.pack_into('<Q', data, 32, 64)
    struct.pack_into('<HH', data, 54, 56, 1)
    struct.pack_into('<IIQQQQQQ', data, 64, kind, 5, offset, address, 0, 1, 1, alignment)
    return bytes(data)


class NativePageCompatibility(unittest.TestCase):
    def test_arm64_loads_accept_large_page_alignment_and_matching_offsets(self):
        self.assertEqual(native.inspect_elf(elf())[0]['alignment'], 16384)
        self.assertEqual(native.inspect_elf(elf(alignment=65536, offset=8, address=65544))[0]['offset'], 8)

    def test_incompatible_or_malformed_loads_are_rejected(self):
        inputs = [elf(alignment=4096), elf(offset=1), elf(alignment=20000), elf(machine=62),
                  elf(offset=128), elf(kind=0x6474e552), elf()[:100], b'not elf']
        for data in inputs:
            with self.subTest(data=data[:8]):
                with self.assertRaises(ValueError): native.inspect_elf(data)

    def test_runtime_requires_loader_and_every_library_to_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.apk'
            def write(items):
                with zipfile.ZipFile(path, 'w') as archive:
                    for name, data in items: archive.writestr(name, data)
            write([('lib/arm64-v8a/libtermux.so', elf())])
            self.assertEqual(len(native.inspect_apk(path, runtime=False)), 1)
            with self.assertRaises(ValueError): native.inspect_apk(path, runtime=True)
            write([('lib/arm64-v8a/libproot-loader.so', elf()), ('lib/arm64-v8a/libtermux.so', elf(alignment=4096))])
            with self.assertRaises(ValueError): native.inspect_apk(path, runtime=True)
            write([('lib/arm64-v8a/libproot-loader.so', elf())])
            self.assertEqual(len(native.inspect_apk(path, runtime=True)), 1)


if __name__ == '__main__':
    unittest.main()
