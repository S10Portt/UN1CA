#!/usr/bin/env python3
"""Check S10's observed EROFS header contract in raw or Android sparse images.

No filesystem creation or mount. This is not an inode, checksum, SELinux or AVB
verifier. Sparse structure and logical size are checked; CRC payload is not.
"""
import argparse
import json
from pathlib import Path
import struct


def read_exact(f, n):
    b = f.read(n)
    if len(b) != n:
        raise ValueError('truncated image')
    return b


def inspect(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('expected a regular image')
    size = path.stat().st_size
    with path.open('rb') as f:
        magic = read_exact(f, 4)
        f.seek(0)
        if magic == b'\x3a\xff\x26\xed':
            _, major, minor, fh, ch, block, blocks, chunks, crc = struct.unpack('<I4H4I', read_exact(f, 28))
            if major != 1 or minor != 0 or fh < 28 or ch < 12 or block != 4096 or not blocks or not chunks:
                raise ValueError('unsupported sparse header')
            f.seek(fh)
            prefix = bytearray()
            expanded = 0
            for _ in range(chunks):
                kind, reserved, count, total = struct.unpack('<2H2I', read_exact(f, 12))
                if total < ch:
                    raise ValueError('invalid sparse chunk size')
                f.seek(ch - 12, 1)
                payload = total - ch
                length = count * block
                need = max(0, min(length, 4096 - expanded))
                if kind == 0xcac1:
                    if payload != length or count == 0:
                        raise ValueError('invalid raw chunk')
                    prefix.extend(read_exact(f, need))
                    f.seek(payload - need, 1)
                elif kind == 0xcac2:
                    if payload != 4 or count == 0:
                        raise ValueError('invalid fill chunk')
                    fill = read_exact(f, 4)
                    prefix.extend((fill * ((need + 3) // 4))[:need])
                elif kind == 0xcac3:
                    if payload or count == 0 or need:
                        raise ValueError('hole in EROFS header or invalid hole chunk')
                elif kind == 0xcac4:
                    if payload != 4 or count != 0:
                        raise ValueError('invalid CRC chunk')
                    read_exact(f, 4)
                else:
                    raise ValueError('unknown sparse chunk')
                expanded += length
                if f.tell() > size or expanded > blocks * block:
                    raise ValueError('sparse chunk exceeds bounds')
            if f.tell() != size or expanded != blocks * block:
                raise ValueError('sparse total mismatch or trailing bytes')
            logical = expanded
            encoding = 'sparse'
        else:
            prefix = read_exact(f, 4096)
            logical = size
            encoding = 'raw'
    if len(prefix) < 1152:
        raise ValueError('missing EROFS superblock')
    sb = prefix[1024:1152]
    if struct.unpack_from('<I', sb)[0] != 0xe0f5e1e2:
        raise ValueError('not an EROFS image')
    incompat = struct.unpack_from('<I', sb, 80)[0]
    distance = struct.unpack_from('<H', sb, 84)[0]
    # Deliberately narrower than the kernel's 0x3 mask: reproduce working 3.1.1.
    if sb[12] != 12 or sb[13] != 0 or incompat != 1 or distance != 65535:
        raise ValueError('EROFS differs from S10 4KiB / legacy LZ4 / incompat=0x1 contract')
    fs_bytes = struct.unpack_from('<I', sb, 36)[0] * 4096
    if fs_bytes < 4096 or fs_bytes > logical or logical % 4096:
        raise ValueError('EROFS size exceeds logical image or is unaligned')
    return {'encoding': encoding, 'logical_bytes': logical, 'filesystem_bytes': fs_bytes,
            'feature_compat': hex(struct.unpack_from('<I', sb, 8)[0]),
            'feature_incompat': hex(incompat), 'block_size': 4096,
            'scope': 'header/size/structural compatibility only; contents and AVB unverified'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path)
    p.add_argument('--max-bytes', type=int)
    a = p.parse_args()
    result = inspect(a.image)
    if a.max_bytes is not None and (a.max_bytes <= 0 or result['logical_bytes'] > a.max_bytes):
        raise ValueError('image exceeds measured partition limit')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, struct.error) as error:
        raise SystemExit('S10 EROFS rejected: ' + str(error))
