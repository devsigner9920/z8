"""Inspect packaged Android ARM64 ELF load segments without executing them."""
import struct
import zipfile


def inspect_elf(data):
    if (len(data) < 64 or data[:6] != b'\x7fELF\x02\x01'
            or struct.unpack_from('<H', data, 18)[0] != 183):
        raise ValueError('Expected a little-endian ARM64 ELF64 image')
    offset = struct.unpack_from('<Q', data, 32)[0]
    entry_size, count = struct.unpack_from('<HH', data, 54)
    if not count or entry_size < 56 or offset + entry_size * count > len(data):
        raise ValueError('Invalid ELF program header table')
    loads = []
    for index in range(count):
        start = offset + index * entry_size
        kind = struct.unpack_from('<I', data, start)[0]
        if kind != 1:  # Only PT_LOAD constrains mmap page alignment; not GNU_RELRO.
            continue
        file_offset, address, _, file_size, memory_size, alignment = struct.unpack_from('<QQQQQQ', data, start + 8)
        if (alignment < 16384 or alignment & (alignment - 1)
                or file_offset % 16384 != address % 16384
                or file_size > memory_size or file_offset + file_size > len(data)):
            raise ValueError('ELF PT_LOAD is not valid for 16 KiB pages')
        loads.append({'offset': file_offset, 'virtualAddress': address, 'alignment': alignment})
    if not loads:
        raise ValueError('ELF contains no loadable segment')
    return loads


def inspect_apk(path, *, runtime):
    records = []
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.startswith('lib/') and name.endswith('.so')]
        if not names or len(names) != len(set(names)):
            raise ValueError('APK native libraries are absent or ambiguous')
        if runtime and 'lib/arm64-v8a/libproot-loader.so' not in names:
            raise ValueError('Runtime APK must package its PRoot loader')
        for name in sorted(names):
            if not name.startswith('lib/arm64-v8a/'):
                raise ValueError('Unexpected native ABI: ' + name)
            try:
                loads = inspect_elf(archive.read(name))
            except ValueError as error:
                raise ValueError(name + ': ' + str(error)) from error
            records.append({'path': name, 'loadSegments': loads})
    return records
