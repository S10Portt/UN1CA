#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Execute original/patched HWC1 output selection with Unicorn (not playback).

Usage: python3 -B scripts/tests/check_s10_hdmi_audio_arm.py ORIGINAL_AUDIO_HAL
Install Unicorn outside the checkout. All test files use temporary storage.
"""
import itertools
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'utils'))
from s10_hdmi_audio import patched, apply, OFFSET
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R5,
    UC_ARM_REG_R7, UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_R12,
    UC_ARM_REG_SP, UC_ARM_REG_PC,
)

DESTINATIONS = {
    0xe7e2: 'hdmi', 0xe7fe: 'default', 0xe956: 'direct',
    0xea9e: 'primary', 0xec56: 'fast', 0xecba: 'deep',
    0xe7b4: 'unsupported',
}


def run(image, flags, device):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(0, 0x30000)
    uc.mem_write(0, image[:0x8ba0])
    uc.mem_write(0x9ba0, image[0x8ba0:0x17090])
    regs = {UC_ARM_REG_R2: 123, UC_ARM_REG_R3: 456,
            UC_ARM_REG_R5: 0x20000, UC_ARM_REG_R7: device,
            UC_ARM_REG_R10: flags, UC_ARM_REG_R11: 0x21000,
            UC_ARM_REG_R12: 0x22000, UC_ARM_REG_SP: 0x28000}
    for reg, value in regs.items():
        uc.reg_write(reg, value)
    result = []

    def hook(u, pc, size, unused):
        if pc in DESTINATIONS:
            result.append(DESTINATIONS[pc])
            u.emu_stop()

    uc.hook_add(UC_HOOK_CODE, hook)
    # CMP flags,#0 through selector; includes the unchanged zero-flag path.
    uc.emu_start(0xe775, 0x18000, count=40)
    assert len(result) == 1, hex(uc.reg_read(UC_ARM_REG_PC))
    for reg, value in regs.items():
        assert uc.reg_read(reg) == value
    return result[0]


def expected(flags, device, bit):
    if flags == 0:
        return 'hdmi' if device == 0x400 else 'default'
    if flags & (1 << bit):
        return 'hdmi'
    for mask, name in ((1, 'direct'), (2, 'primary'), (4, 'fast'), (8, 'deep')):
        if flags & mask:
            return name
    return 'unsupported'


def main(path):
    source = Path(path).read_bytes()
    result = patched(source)
    assert result != source, 'supply the original HAL'
    assert [i for i, pair in enumerate(zip(source, result)) if pair[0] != pair[1]] == [OFFSET+2]
    assert patched(result) == result
    flags_set = set(range(256)) | {1 << bit for bit in range(32)}
    flags_set |= {low | high for low in range(16)
                  for high in (1 << 24, 1 << 25, (1 << 24) | (1 << 25))}
    cases = 0
    for flags, device in itertools.product(sorted(flags_set), (0x400, 2)):
        assert run(source, flags, device) == expected(flags, device, 24)
        assert run(result, flags, device) == expected(flags, device, 25)
        cases += 2
    assert run(source, 0x2000000, 0x400) == 'unsupported'
    assert run(result, 0x2000000, 0x400) == 'hdmi'
    try:
        patched(source[:-1])
    except ValueError:
        pass
    else:
        raise AssertionError('unknown HAL accepted')
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / 'audio.so'
        output.write_bytes(source)
        output.chmod(0o640)
        os.setxattr(output, 'user.patch_test', b'preserved')
        apply(output)
        apply(output)
        assert output.read_bytes() == result
        assert output.stat().st_mode & 0o777 == 0o640
        assert os.getxattr(output, 'user.patch_test') == b'preserved'
        link = Path(tmp) / 'link.so'
        link.symlink_to(output)
        try:
            apply(link)
        except ValueError:
            pass
        else:
            raise AssertionError('symlink accepted')
    print(f'PASS: {cases} ARM output-selection cases; hash, idempotence, metadata and symlink checks')


if __name__ == '__main__':
    main(sys.argv[1])
