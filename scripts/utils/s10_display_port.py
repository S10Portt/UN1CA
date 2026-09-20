#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""GZH3 SurfaceFlinger: only check a supplied identification port for duplicates.

Legacy composer clients can return UNSUPPORTED without setting outPort. GZH3
checks that zero-initialized byte before assigning the legacy primary/secondary
port. Keep duplicate checking for valid identification data, missing-data
rejection in generalized mode, and the legacy two-display limit.
"""
import hashlib
from pathlib import Path
import sys

ORIGINAL_SHA256 = '86c628ec94691bd78a19136468190cfa85cd183d3144c9e861d1b76831861f43'
PATCHED_SHA256 = '6017fe96033a1a4801cc708b694c8774ecf8aa7b2c29b57ccc2c7de7adc4cf31'
# File offsets equal virtual addresses in this pinned executable's .text.
# Save the canary before the new branch. w21's port copy is no longer needed:
# the duplicate-error log reads the already-saved port byte from the stack.
EDITS = (
    (0x4526ac, bytes.fromhex('f503022a'), bytes.fromhex('e80700f9')),  # mov w21,w2 -> str x8,[sp,#8]
    (0x4526b0, bytes.fromhex('e80700f9'), bytes.fromhex('e3020034')),  # cbz w3,0x45270c
    (0x4526d0, bytes.fromhex('a41e0012'), bytes.fromhex('e4134039')),  # ldrb w4,[sp,#4]
)


def patched(data):
    digest = hashlib.sha256(data).hexdigest()
    if digest == PATCHED_SHA256:
        return data
    if digest != ORIGINAL_SHA256:
        raise ValueError('unregistered SurfaceFlinger; refusing version-dependent patch')
    result = bytearray(data)
    for offset, before, after in EDITS:
        if result[offset:offset+4] != before:
            raise ValueError('SurfaceFlinger instruction mismatch')
        result[offset:offset+4] = after
    result = bytes(result)
    if hashlib.sha256(result).hexdigest() != PATCHED_SHA256:
        raise ValueError('unexpected patched SurfaceFlinger hash')
    return result


def apply(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('SurfaceFlinger must be a regular file')
    # In-place write keeps the work-tree file's mode, ownership and xattrs.
    with path.open('r+b') as stream:
        source = stream.read()
        result = patched(source)
        if result != source:
            stream.seek(0)
            stream.write(result)
            stream.flush()
    if path.read_bytes() != result:
        raise ValueError('SurfaceFlinger write verification failed')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('usage: s10_display_port.py SURFACEFLINGER')
        apply(Path(sys.argv[1]))
    except (OSError, ValueError) as exc:
        sys.exit('S10 display port: ' + str(exc))
