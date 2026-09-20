#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Match HWC1 audio HAL's HDMI stream selector to GZD7 MULTI_CH (bit 25).

HWC1 tests bit 24 before selecting the HDMI stream. GZD7 passes bit 25,
which otherwise falls through to 'requested to open un-supported output'.
Only the pinned ARM32 HAL instruction is changed; profiles and formats stay
under the existing policy and driver negotiation. Device playback must still
be tested after rebuilding.
"""
import hashlib
from pathlib import Path
import sys

ORIGINAL_SHA256 = '7866ba84edbbf9ed6120924a2fc1bdb434725efc56bb872f4ace896d71657cbd'
PATCHED_SHA256 = '15e023959e4eb24cb248d6d63075b8807a6d4c216f008d87f50bbe6a9c9fadea'
OFFSET = 0xd78a  # VA 0xe78a: lsls.w r0,r10,#7 -> #6; following BMI is unchanged.
BEFORE = bytes.fromhex('5feaca10')
AFTER = bytes.fromhex('5fea8a10')


def patched(data):
    digest = hashlib.sha256(data).hexdigest()
    if digest == PATCHED_SHA256:
        return data
    if digest != ORIGINAL_SHA256 or data[OFFSET:OFFSET+4] != BEFORE:
        raise ValueError('unregistered audio HAL; refusing version-dependent patch')
    result = data[:OFFSET] + AFTER + data[OFFSET+4:]
    if hashlib.sha256(result).hexdigest() != PATCHED_SHA256:
        raise ValueError('unexpected patched audio HAL hash')
    return result


def apply(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('audio HAL must be a regular file')
    # Preserve ownership, mode and xattrs on the work-tree inode.
    with path.open('r+b') as stream:
        source = stream.read()
        result = patched(source)
        if result != source:
            stream.seek(0)
            stream.write(result)
            stream.flush()
    if path.read_bytes() != result:
        raise ValueError('audio HAL write verification failed')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('usage: s10_hdmi_audio.py AUDIO_PRIMARY_EXYNOS9820')
        apply(Path(sys.argv[1]))
    except (OSError, ValueError) as exc:
        sys.exit('S10 HDMI audio: ' + str(exc))
