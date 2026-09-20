# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply S10 encoder caller workarounds and a bounded process-name read to exactly GZH3 libstagefright.

This is a
compatibility policy, not proof of encoder feature support or runtime safety.
"""
import hashlib
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
import tempfile

# Input follows the common camera ro.product.model -> ro.boot.em.model rewrite.
BEFORE = 'd5c4f346faf41952d7ec0a8b85f724f86c69d2cc68a6fd4ef7bc5a34c745b6f7'
AFTER = '9351f11df3df96ce3531117c65ee56bda54fb3491b594d90f8b21f9baf613ae8'
CHANGES = ((0xddbc0, bytes.fromhex('22feff17'), bytes.fromhex('19000014')),
           (0xdd48c, bytes.fromhex('604d0034'), bytes.fromhex('1f2003d5')),
           # Two observed callers provide 255 bytes; fread's result indexes a NUL write.
           # Limit payload to 254, retaining space for that terminator.
           (0xe11e4, bytes.fromhex('02408052'), bytes.fromhex('c21f8052')))


def transform(data):
    digest = hashlib.sha256(data).hexdigest()
    if digest == AFTER:
        return data
    if digest != BEFORE:
        raise ValueError('unrecognized stagefright input SHA-256: ' + digest)
    if data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 183:
        raise ValueError('expected little-endian AArch64 ELF64')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    result = bytearray(data)
    for va, old, new in CHANGES:
        offsets = []
        for i in range(count):
            kind, flags, offset, addr, _, length, _, _ = struct.unpack_from('<IIQQQQQQ', data, phoff + i * size)
            if kind == 1 and flags & 1 and addr <= va and va + len(old) <= addr + length:
                offsets.append(offset + va - addr)
        if len(offsets) != 1 or va % 4:
            raise ValueError('ambiguous or unaligned executable address')
        offset = offsets[0]
        if data[offset:offset + len(old)] != old:
            raise ValueError('unexpected original instruction')
        result[offset:offset + len(old)] = new
    result = bytes(result)
    if len(result) != len(data) or hashlib.sha256(result).hexdigest() != AFTER:
        raise ValueError('unexpected complete output digest')
    return result


def apply(path):
    path = Path(os.path.abspath(path))
    for parent in reversed(path.parents):
        if parent.is_symlink() or not parent.is_dir():
            raise ValueError('unsupported parent path: ' + str(parent))
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise ValueError('expected regular file without hard links')
    original = path.read_bytes()
    result = transform(original)
    if result == original:
        print('S10 stagefright: verified post-patch state')
        return
    fd, name = tempfile.mkstemp(prefix='.s10-stagefright-', dir=path.parent)
    os.close(fd)
    try:
        shutil.copy2(path, name, follow_symlinks=False)
        Path(name).write_bytes(result)
        if path.read_bytes() != original:
            raise ValueError('input changed during patch planning')
        os.replace(name, path)
    finally:
        if os.path.lexists(name):
            os.unlink(name)
    print('S10 stagefright: applied GZH3 caller changes and bounded process-name read')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('usage: s10_stagefright.py FILE')
        apply(sys.argv[1])
    except (OSError, ValueError, struct.error) as error:
        print('S10 stagefright: ' + str(error), file=sys.stderr)
        sys.exit(1)
